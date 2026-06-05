"""
Agent factory — LLM instance is created once and reused across all agents.
"""
import os
from functools import lru_cache
from crewai import Agent
from tools import Neo4jSearchTool, PathfindingTool, ServiceCapacityTool, CostCalculatorTool


class SynchromodalAgents:
    """
    Creates CrewAI agents that share a single LLM instance.

    The LLM string is resolved once at construction time.  All agents
    created from the same factory share the same tool instances, avoiding
    repeated object allocation.
    """

    # Model preference order: Use Groq API as requested by the user.
    _DEFAULT_MODEL = "groq/llama-3.3-70b-versatile"
    _FALLBACK_MODEL = "groq/llama3-70b-8192"

    def __init__(self, neo4j_manager):
        self.manager = neo4j_manager

        # Propagate Groq API key to LiteLLM / CrewAI env vars
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            os.environ["GROQ_API_KEY"] = api_key

        # Single LLM identifier — shared by all agents in this factory
        self.llm = os.getenv("CREWAI_LLM_MODEL", self._DEFAULT_MODEL)

        # Tool instances created once and reused
        self._search_tool = Neo4jSearchTool(manager=self.manager)
        self._path_tool = PathfindingTool(manager=self.manager)
        self._capacity_tool = ServiceCapacityTool(manager=self.manager)
        self._cost_tool = CostCalculatorTool(manager=self.manager)

    # ------------------------------------------------------------------
    # Agent constructors
    # ------------------------------------------------------------------

    def logistics_coordinator(self) -> Agent:
        return Agent(
            role="Logistics Coordinator",
            goal=(
                "Consolidate routing proposals from shipment agents, resolve "
                "capacity conflicts, and produce a final replanning report."
            ),
            backstory=(
                "You are a senior logistics manager at the Port of Rotterdam. "
                "You oversee the hinterland network and coordinate between shipment "
                "agents and service operators to maximise barge/rail modal split "
                "while meeting delivery deadlines."
            ),
            tools=[self._search_tool, self._path_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False,  # coordinator does not sub-delegate in finalize
            max_iter=5,              # cap reasoning loops to save tokens
        )

    def shipment_agent(self, shipment_id: str) -> Agent:
        return Agent(
            role=f"Shipment Agent {shipment_id}",
            goal=(
                f"Find the lowest-cost feasible route for shipment {shipment_id} "
                "that respects its release time and due time."
            ),
            backstory=(
                f"You represent shipment {shipment_id}. "
                "ALWAYS use terminal IDs (e.g., 'POR', 'DUIS', 'T1') — never city names. "
                "Use the Pathfinding Tool with format 'ORIGIN,DEST,EARLIEST,LATEST'. "
                "Prefer barge or rail; fall back to truck only if deadlines are at risk."
            ),
            tools=[self._path_tool, self._cost_tool, self._capacity_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
            max_iter=6,
        )

    def service_operator(self, service_mode: str) -> Agent:
        return Agent(
            role=f"{service_mode.capitalize()} Service Operator",
            goal=(
                f"Report accurate capacity for {service_mode} services and flag "
                "any arcs that are at or near full utilisation."
            ),
            backstory=(
                f"You manage the {service_mode} network. "
                "You aim to fill services to maximum capacity while ensuring "
                "on-time departures. Provide real-time capacity updates."
            ),
            tools=[self._search_tool, self._capacity_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
            max_iter=4,
        )
