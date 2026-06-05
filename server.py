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
from fastapi.responses import HTMLResponse, RedirectResponse
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
    
    # Auto-import network on startup so the dashboard is populated immediately!
    try:
        dataset_path = os.path.join("Dataset", "7nodes.xlsx")
        if not os.path.exists(dataset_path):
            dataset_path = os.path.join("Dataset (1)", "7nodes (1).xlsx")
        if os.path.exists(dataset_path):
            logger.info("Auto-loading default dataset: %s", dataset_path)
            model, _ = load_dataset_from_excel(dataset_path)
            _manager.import_network(
                list(model.terminals.values()),
                list(model.services.values()),
                list(model.shipments.values()),
                list(model.arcs.values()),
                buffer_times=model.buffer_time,
            )
            logger.info("Database successfully pre-populated on startup.")
    except Exception as e:
        logger.error("Failed to pre-populate database on startup: %s", e)
        
    yield
    if _manager:
        _manager.close()
    logger.info("Neo4j connection closed.")


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Synchromodal Replanning API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            response = HTMLResponse(content=f.read())
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response
    else:
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Synchromodal Control Tower API</title>
            <style>
                body {
                    background-color: #0b0f19;
                    color: #f8fafc;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                }
                .container {
                    text-align: center;
                    padding: 2.5rem;
                    background: rgba(30, 41, 59, 0.4);
                    border-radius: 16px;
                    border: 1px solid #334155;
                    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.4);
                    backdrop-filter: blur(12px);
                    max-width: 550px;
                }
                h1 { color: #10b981; margin-top: 0; margin-bottom: 1rem; font-size: 1.8rem; }
                p { color: #94a3b8; font-size: 1rem; line-height: 1.6; margin: 0.5rem 0; }
                .btn {
                    display: inline-block;
                    margin-top: 1.5rem;
                    padding: 0.8rem 1.8rem;
                    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: 600;
                    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.2);
                    transition: all 0.2s ease;
                }
                .btn:hover {
                    background: linear-gradient(135deg, #059669 0%, #047857 100%);
                    transform: translateY(-1px);
                    box-shadow: 0 6px 16px rgba(16, 185, 129, 0.3);
                }
                code {
                    background-color: #1e293b;
                    padding: 0.2rem 0.5rem;
                    border-radius: 6px;
                    color: #f472b6;
                    font-family: Consolas, monospace;
                    font-size: 0.9rem;
                }
                .terminal-box {
                    text-align: left;
                    background: #090d16;
                    border: 1px solid #1e293b;
                    border-radius: 8px;
                    padding: 1rem;
                    margin: 1.5rem 0;
                    font-family: Consolas, monospace;
                    font-size: 0.85rem;
                    color: #38bdf8;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Synchromodal Control Tower API</h1>
                <p>The Python FastAPI backend is running successfully on port <code>8000</code>.</p>
                <p>To view the visual agentic dashboard, run the Next.js app in the frontend directory:</p>
                <div class="terminal-box">
                    <span style="color:#64748b;"># Open another terminal, navigate to the frontend, and run:</span><br>
                    cd frontend<br>
                    npm run dev
                </div>
                <p>Then open the dashboard in your web browser:</p>
                <a href="http://localhost:3000" target="_blank" class="btn">Open Web Dashboard (Port 3000)</a>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)


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


@app.post("/api/select_dataset")
async def select_dataset(dataset: str = "7nodes.xlsx"):
    """Imports the selected dataset into Neo4j and clears previous network data."""
    dataset_path = os.path.join("Dataset", dataset)
    if not os.path.exists(dataset_path):
        dataset_path = os.path.join("Dataset (1)", "7nodes (1).xlsx")
    if not os.path.exists(dataset_path):
        raise HTTPException(
            status_code=404,
            detail=f"Dataset '{dataset}' not found.",
        )
    try:
        model, _ = load_dataset_from_excel(dataset_path)
        _manager.import_network(
            list(model.terminals.values()),
            list(model.services.values()),
            list(model.shipments.values()),
            list(model.arcs.values()),
            buffer_times=model.buffer_time,
        )
        return {"status": "success", "message": f"Successfully loaded dataset {dataset}"}
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/neo4j")
async def get_neo4j_graph():
    """Returns all nodes and relationships from Neo4j in Cytoscape format."""
    if not _manager:
        return {"elements": []}

    if not _manager.driver:
        return _manager.get_in_memory_cytoscape_elements()

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
                            "type": record.get("r_type", ""),
                        }
                    }
                )

        return {"elements": list(nodes.values()) + edges}

    except Exception as e:
        logger.exception("Error fetching Neo4j graph data")
        return {"elements": [], "error": str(e)}


@app.post("/api/run")
async def run_workflow(dataset: str = "7nodes.xlsx", mock: bool = False):
    """
    Triggers the replanning workflow.

    Query param `dataset` selects which file from the Dataset folder to use.
    Defaults to 7nodes.xlsx (Rotterdam case study).
    """
    dataset_path = os.path.join("Dataset", dataset)
    if not os.path.exists(dataset_path):
        dataset_path = os.path.join("Dataset (1)", "7nodes (1).xlsx")
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

        # Auto-detect mock mode if GROQ_API_KEY is not set or placeholder
        groq_key = os.getenv("GROQ_API_KEY")
        is_mock = mock or not groq_key or "your_groq_api_key_here" in groq_key or groq_key.strip() == ""

        if is_mock:
            logger.info("Running workflow in MOCK mode...")
            # Import network to populate the active model in database
            _manager.import_network(
                list(model.terminals.values()),
                list(model.services.values()),
                list(model.shipments.values()),
                list(model.arcs.values()),
                buffer_times=model.buffer_time,
            )
            
            # Dynamically assign some shipments to arcs for visual paths on the map
            affected_shipments = list(model.shipments.keys())[:3]
            for sh_id in affected_shipments:
                sh = model.shipments[sh_id]
                assigned = []
                for arc_id, arc in model.arcs.items():
                    if arc.from_terminal == sh.origin:
                        assigned.append(arc_id)
                        break
                if assigned:
                    _manager.update_shipment_assignment(sh_id, assigned)

            # Build mock report
            final_report = (
                "=== MOCK REPLANNING REPORT ===\n\n"
                "Notice: Running in MOCK Mode (no GROQ_API_KEY configured in .env).\n"
                "This simulation replicates the optimization output of the LLM coordinator.\n\n"
                "Summary of Decisions:\n"
            )
            for sh_id, sh in model.shipments.items():
                assigned_ids = []
                if not _manager.driver:
                    assigned_ids = _manager.assignments_db.get(sh_id, [])
                else:
                    r = _manager.query("MATCH (s:Shipment {id:$id})-[:ASSIGNED_TO]->(a:Arc) RETURN a.id as id", {"id": sh_id})
                    assigned_ids = [row["id"] for row in r]
                
                if assigned_ids:
                    final_report += f"- Shipment {sh_id} ({sh.origin} -> {sh.destination}): Re-routed via Arcs: {', '.join(assigned_ids)} (Estimated Cost: €{len(assigned_ids)*2300:.2f})\n"
                else:
                    final_report += f"- Shipment {sh_id} ({sh.origin} -> {sh.destination}): Retained on standard scheduled barge service (Cost: €1,850.00)\n"
            
            final_report += "\nModal Split: Barge: 60%, Rail: 20%, Road: 20%\nOptimization status: OPTIMAL."
            
            return {
                "status": "completed (mock)",
                "final_report": final_report,
                "affected_shipments": affected_shipments,
            }

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
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
