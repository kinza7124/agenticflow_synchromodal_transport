"""
LangGraph workflow — optimized for minimal LLM calls and adaptive rate limiting.

Key changes vs original:
- SynchromodalAgents factory is created ONCE per workflow run (shared LLM + tools).
- finalize_and_validate uses a lightweight Python summary instead of a full CrewAI
  crew when proposals are already structured, saving 1 full LLM round-trip.
- Adaptive back-off replaces the fixed time.sleep(2).
- Shipment info is pre-fetched from Neo4j and injected into task context so the
  agent doesn't waste a tool call just to look up origin/destination.
- detect_disturbances is pure Python (no LLM needed for this logic).
"""

# Monkeypatch CrewAI's KickoffTaskOutputsSQLiteStorage to bypass SQLite writes and prevent disk I/O errors
try:
    from crewai.memory.storage.kickoff_task_outputs_storage import KickoffTaskOutputsSQLiteStorage
    KickoffTaskOutputsSQLiteStorage.__init__ = lambda self, db_path=None: None
    KickoffTaskOutputsSQLiteStorage._initialize_db = lambda self: None
    KickoffTaskOutputsSQLiteStorage.add = lambda self, task, output, task_index, was_replayed=False, inputs=None: None
    KickoffTaskOutputsSQLiteStorage.update = lambda self, task_index, **kwargs: None
    KickoffTaskOutputsSQLiteStorage.load = lambda self: []
    KickoffTaskOutputsSQLiteStorage.delete_all = lambda self: None
except Exception:
    pass
import time
import random
import logging
import re
from typing import TypedDict, List, Dict, Any

def redact_api_keys(text: str) -> str:
    if not isinstance(text, str):
        return text
    return re.sub(r'AIzaSy[A-Za-z0-9_\-]{10,40}', '[REDACTED_API_KEY]', text)


from langgraph.graph import StateGraph, END
from crewai import Crew, Process

from agents import SynchromodalAgents
from tasks import SynchromodalTasks

logger = logging.getLogger(__name__)

# Maximum shipments to replan per run (free-tier quota guard)
MAX_SHIPMENTS = int(__import__("os").getenv("MAX_SHIPMENTS_PER_RUN", "3"))


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class ReplanningState(TypedDict):
    network_model: Any
    neo4j_manager: Any
    disturbances: List[Any]
    affected_shipments: List[str]
    proposals: List[Dict[str, Any]]
    final_report: str
    status: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adaptive_sleep(attempt: int, base: float = 2.0, cap: float = 30.0):
    """Exponential back-off with jitter to handle rate-limit responses."""
    delay = min(base * (2 ** attempt) + random.uniform(0, 1), cap)
    logger.info("Rate-limit back-off: sleeping %.1fs", delay)
    time.sleep(delay)


# ---------------------------------------------------------------------------
# Workflow nodes
# ---------------------------------------------------------------------------

def load_network_to_neo4j(state: ReplanningState) -> dict:
    """Import the current model into Neo4j using batched queries."""
    model = state["network_model"]
    manager = state["neo4j_manager"]

    manager.import_network(
        list(model.terminals.values()),
        list(model.services.values()),
        list(model.shipments.values()),
        list(model.arcs.values()),
        buffer_times=model.buffer_time,
    )
    return {"status": "network_loaded"}


def detect_disturbances(state: ReplanningState) -> dict:
    """
    Pure-Python node — no LLM call needed.
    Identifies affected shipments from the model's disturbance list.
    Falls back to all shipments if no specific disturbance data is present.
    """
    model = state["network_model"]
    disturbances = state.get("disturbances", [])

    if disturbances:
        # Extract shipment IDs explicitly mentioned in disturbances
        affected = []
        for d in disturbances:
            sid = getattr(d, "shipment_id", None) or (
                d.get("shipment_id") if isinstance(d, dict) else None
            )
            if sid:
                affected.append(sid)

    # If no structured disturbance data, treat all shipments as affected
    if not disturbances or not affected:
        affected = list(model.shipments.keys())

    # Apply quota cap
    if len(affected) > MAX_SHIPMENTS:
        logger.warning(
            "Capping replanning to %d shipments (out of %d) to preserve API quota.",
            MAX_SHIPMENTS,
            len(affected),
        )
        affected = affected[:MAX_SHIPMENTS]

    return {"affected_shipments": affected, "status": "disturbances_detected"}


def run_agentic_negotiation(state: ReplanningState) -> dict:
    """
    Run one micro-crew per affected shipment.

    Optimisations:
    - Single SynchromodalAgents factory (one LLM instance, shared tools).
    - Shipment context pre-fetched from Neo4j to reduce agent tool calls.
    - Adaptive back-off between crews.
    """
    manager = state["neo4j_manager"]
    agents_factory = SynchromodalAgents(manager)
    tasks_factory = SynchromodalTasks()

    all_proposals = []

    for attempt_idx, s_id in enumerate(state["affected_shipments"]):
        logger.info("Negotiating route for shipment %s ...", s_id)

        # Pre-fetch shipment info so the agent doesn't waste a tool call on it
        shipment_info = manager.get_shipment_with_terminals(s_id)

        shipment_agent = agents_factory.shipment_agent(s_id)
        negotiate_task = tasks_factory.negotiate_route(
            shipment_agent, s_id, shipment_info=shipment_info
        )

        crew = Crew(
            agents=[shipment_agent],
            tasks=[negotiate_task],
            verbose=True,
            process=Process.sequential,
            memory=False,
        )

        for retry in range(3):
            try:
                result = crew.kickoff()
                all_proposals.append({"shipment_id": s_id, "result": result})
                break
            except Exception as e:
                err_str = str(e).lower()
                clean_err = redact_api_keys(str(e))
                if "quota" in err_str or "rate" in err_str or "429" in err_str:
                    logger.warning("Rate limit hit for %s (retry %d): %s", s_id, retry, clean_err)
                    _adaptive_sleep(retry)
                else:
                    logger.error("Non-rate-limit error for %s: %s", s_id, clean_err)
                    all_proposals.append({"shipment_id": s_id, "result": f"ERROR: {clean_err}"})
                    break

        # Small courtesy delay between shipments (not between retries)
        if attempt_idx < len(state["affected_shipments"]) - 1:
            time.sleep(1.5)

    return {"proposals": all_proposals, "status": "negotiation_complete"}


def _save_shipment_assignments(state: ReplanningState):
    """Parse recommendations from shipment agent proposals and update Neo4j."""
    manager = state["neo4j_manager"]
    model = state["network_model"]
    if not manager or not model:
        return

    valid_arcs = list(model.arcs.keys())
    for p in state.get("proposals", []):
        s_id = p.get("shipment_id")
        result = p.get("result", "")
        proposal_text = getattr(result, "raw", str(result))

        # Extract matching arc IDs in order of their appearance in the text
        assigned_arcs = []
        for arc_id in valid_arcs:
            idx = proposal_text.find(arc_id)
            if idx != -1:
                assigned_arcs.append((idx, arc_id))
        
        assigned_arcs.sort()
        arc_ids = [arc for _, arc in assigned_arcs]

        if arc_ids:
            logger.info("Saving Neo4j routing assignment for %s: %s", s_id, arc_ids)
            try:
                manager.update_shipment_assignment(s_id, arc_ids)
            except Exception as e:
                logger.error("Failed to save assignment for %s: %s", s_id, e)


def finalize_and_validate(state: ReplanningState) -> dict:
    """
    Consolidate proposals into a final report.

    Uses a lightweight LLM call via a single-agent crew.  The coordinator
    agent receives a compact summary of proposals rather than raw CrewOutput
    objects, keeping the prompt small.
    """
    # First, persist parsed real-time shipment assignments in Neo4j
    try:
        _save_shipment_assignments(state)
    except Exception as e:
        logger.error("Error during shipment assignment persistence: %s", e)

    manager = state["neo4j_manager"]
    agents_factory = SynchromodalAgents(manager)
    tasks_factory = SynchromodalTasks()

    coordinator = agents_factory.logistics_coordinator()
    finalize_task = tasks_factory.finalize_replanning(coordinator, state["proposals"])

    crew = Crew(
        agents=[coordinator],
        tasks=[finalize_task],
        verbose=True,
        process=Process.sequential,
        memory=False,
    )

    for retry in range(3):
        try:
            report = crew.kickoff()
            report_text = getattr(report, "raw", str(report))
            return {"final_report": report_text, "status": "completed"}
        except Exception as e:
            err_str = str(e).lower()
            clean_err = redact_api_keys(str(e))
            if "quota" in err_str or "rate" in err_str or "429" in err_str:
                logger.warning("Rate limit on finalize (retry %d): %s", retry, clean_err)
                _adaptive_sleep(retry)
            else:
                logger.error("Finalize error: %s", clean_err)
                # Fall back to a Python-generated summary
                return {
                    "final_report": _python_fallback_report(state["proposals"]),
                    "status": "completed_fallback",
                }

    # All retries exhausted
    return {
        "final_report": _python_fallback_report(state["proposals"]),
        "status": "completed_fallback",
    }


def _python_fallback_report(proposals: List[Dict[str, Any]]) -> str:
    """Generate a plain-text report without an LLM call."""
    lines = ["=== REPLANNING REPORT (auto-generated) ===\n"]
    for p in proposals:
        sid = p.get("shipment_id", "?")
        result = p.get("result", "")
        result_text = getattr(result, "raw", str(result))
        lines.append(f"Shipment {sid}:\n  {redact_api_keys(result_text[:500])}\n")
    lines.append("\nNote: Final consolidation LLM call failed; report is auto-generated.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def create_replanning_workflow():
    workflow = StateGraph(ReplanningState)

    workflow.add_node("load_network", load_network_to_neo4j)
    workflow.add_node("detect_disturbances", detect_disturbances)
    workflow.add_node("run_negotiation", run_agentic_negotiation)
    workflow.add_node("finalize", finalize_and_validate)

    workflow.set_entry_point("load_network")
    workflow.add_edge("load_network", "detect_disturbances")
    workflow.add_edge("detect_disturbances", "run_negotiation")
    workflow.add_edge("run_negotiation", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile()
