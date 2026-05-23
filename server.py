"""
FastAPI server — optimized with connection-pooling, lazy workflow init,
and structured error responses.
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

import os
import logging
from contextlib import asynccontextmanager

import anyio
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from neo4j_manager import Neo4jManager
from workflow import create_replanning_workflow, redact_api_keys
from synchromodal_dataset_loader import load_dataset_from_excel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App lifecycle — initialise heavy objects once at startup
# ---------------------------------------------------------------------------

_manager: Neo4jManager = None
_workflow_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _manager, _workflow_app
    _manager = Neo4jManager()
    _workflow_app = create_replanning_workflow()
    logger.info("Neo4j manager and workflow initialised.")
    yield
    if _manager:
        _manager.close()
    logger.info("Neo4j connection closed.")


app = FastAPI(title="Synchromodal Replanning API", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

if os.path.exists("style.css"):
    app.mount("/static", StaticFiles(directory="."), name="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def get_index():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/workflow")
async def get_workflow_graph():
    """Returns the LangGraph structure for front-end visualisation."""
    nodes = [
        {"id": "load_network",        "label": "Load Network"},
        {"id": "detect_disturbances", "label": "Detect Disturbances"},
        {"id": "run_negotiation",     "label": "Run Negotiation"},
        {"id": "finalize",            "label": "Finalize"},
        {"id": "END",                 "label": "End"},
    ]
    edges = [
        {"source": "load_network",        "target": "detect_disturbances"},
        {"source": "detect_disturbances", "target": "run_negotiation"},
        {"source": "run_negotiation",     "target": "finalize"},
        {"source": "finalize",            "target": "END"},
    ]
    return {"nodes": nodes, "edges": edges}


@app.get("/api/neo4j")
async def get_neo4j_graph():
    """Returns all nodes and relationships from Neo4j in Cytoscape format."""
    if not _manager or not _manager.driver:
        return {"elements": []}

    try:
        # Single query — fetch everything in one round-trip
        results = _manager.query(
            """
            MATCH (n)
            OPTIONAL MATCH (n)-[r]->(m)
            RETURN
                n,
                labels(n)  AS n_labels,
                id(n)      AS n_int_id,
                r,
                type(r)    AS r_type,
                id(r)      AS r_int_id,
                m,
                id(m)      AS m_int_id
            """
        )

        nodes: dict = {}
        edges: list = []

        for record in results:
            n = record.get("n")
            if n is None:
                continue

            n_id = str(n.get("id") or record.get("n_int_id"))
            if n_id not in nodes:
                label = (record.get("n_labels") or ["Node"])[0]
                nodes[n_id] = {
                    "data": {
                        "id": n_id,
                        "label": f"{label}: {n.get('name') or n_id}",
                        "type": label,
                        **{k: v for k, v in dict(n).items() if k != "id"},
                    }
                }

            m = record.get("m")
            r = record.get("r")
            if m is not None and r is not None:
                m_id = str(m.get("id") or record.get("m_int_id"))
                r_id = str(record.get("r_int_id"))
                edges.append(
                    {
                        "data": {
                            "id": r_id,
                            "source": n_id,
                            "target": m_id,
                            "label": record.get("r_type", ""),
                        }
                    }
                )

        return {"elements": list(nodes.values()) + edges}

    except Exception as e:
        logger.exception("Error fetching Neo4j graph data")
        return {"elements": [], "error": str(e)}


@app.post("/api/run")
async def run_workflow(dataset: str = "7nodes.xlsx"):
    """
    Triggers the replanning workflow.

    Query param `dataset` selects which file from the Dataset folder to use.
    Defaults to 7nodes.xlsx (Rotterdam case study).
    """
    dataset_path = os.path.join("Dataset", dataset)
    if not os.path.exists(dataset_path):
        raise HTTPException(
            status_code=404,
            detail=f"Dataset '{dataset}' not found in Dataset folder.",
        )

    try:
        model, _ = load_dataset_from_excel(dataset_path)

        # Apply Case 1 disturbance: 2-hour late release
        for s in model.shipments.values():
            s.release_time = 9.0

        initial_state = {
            "network_model": model,
            "neo4j_manager": _manager,
            "disturbances": model.disturbances,
            "affected_shipments": [],
            "proposals": [],
            "final_report": "",
            "status": "started",
        }

        # Run blocking workflow in a thread pool so FastAPI stays responsive
        result = await anyio.to_thread.run_sync(
            lambda: _workflow_app.invoke(initial_state)
        )

        return {
            "status": result.get("status", "completed"),
            "final_report": result.get("final_report", "No report generated"),
            "affected_shipments": result.get("affected_shipments", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        clean_err = redact_api_keys(str(e))
        logger.error(f"Workflow execution failed: {clean_err}")
        raise HTTPException(status_code=500, detail=clean_err)


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
