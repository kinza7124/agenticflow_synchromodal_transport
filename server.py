import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any
import uvicorn
from neo4j_manager import Neo4jManager
from workflow import create_replanning_workflow
from synchromodal_dataset_loader import load_dataset_from_excel
import json

from fastapi.concurrency import run_in_threadpool
import anyio

app = FastAPI()

# Global manager instance
manager = Neo4jManager()
workflow_app = create_replanning_workflow()

class WorkflowState(BaseModel):
    status: str
    report: str = ""

@app.get("/api/workflow")
async def get_workflow_graph():
    """Returns the LangGraph structure."""
    nodes = [
        {"id": "load_network", "label": "Load Network"},
        {"id": "detect_disturbances", "label": "Detect Disturbances"},
        {"id": "run_negotiation", "label": "Run Negotiation"},
        {"id": "finalize", "label": "Finalize"},
        {"id": "END", "label": "End"}
    ]
    edges = [
        {"source": "load_network", "target": "detect_disturbances"},
        {"source": "detect_disturbances", "target": "run_negotiation"},
        {"source": "run_negotiation", "target": "finalize"},
        {"source": "finalize", "target": "END"}
    ]
    return {"nodes": nodes, "edges": edges}

@app.get("/api/neo4j")
async def get_neo4j_graph():
    """Returns all nodes and relationships from Neo4j in Cytoscape format."""
    if not manager.driver:
        return {"elements": []}
    
    try:
        query = """
        MATCH (n)
        OPTIONAL MATCH (n)-[r]->(m)
        RETURN n, r, m
        """
        results = manager.query(query)
        
        nodes = {}
        edges = []
        
        for record in results:
            n = record['n']
            if n:
                # Get ID safely across different driver versions
                node_id = n.get('id') or n.element_id if hasattr(n, 'element_id') else str(n.id)
                if node_id not in nodes:
                    label = list(n.labels)[0] if n.labels else "Node"
                    nodes[node_id] = {
                        "data": {
                            "id": node_id,
                            "label": f"{label}: {n.get('name') or node_id}",
                            "type": label,
                            **dict(n)
                        }
                    }
            
            m = record['m']
            r = record['r']
            if m and r:
                m_id = m.get('id') or m.element_id if hasattr(m, 'element_id') else str(m.id)
                r_id = r.element_id if hasattr(r, 'element_id') else str(r.id)
                edges.append({
                    "data": {
                        "id": r_id,
                        "source": node_id,
                        "target": m_id,
                        "label": r.type
                    }
                })
                
        return {"elements": list(nodes.values()) + edges}
    except Exception as e:
        print(f"Error fetching Neo4j data: {e}")
        return {"elements": []}

@app.post("/api/run")
async def run_workflow():
    """Triggers the replanning workflow in a background thread."""
    try:
        # Load dataset
        dataset_path = os.path.join("Dataset", "7nodes.xlsx")
        if not os.path.exists(dataset_path):
            dataset_path = os.path.join("Dataset (1)", "7nodes (1).xlsx")
        
        if not os.path.exists(dataset_path):
            raise HTTPException(status_code=404, detail="Dataset not found")
            
        model, _ = load_dataset_from_excel(dataset_path)
        
        # Apply Case 1 Disturbance
        for s in model.shipments.values():
            s.release_time = 9.0
            
        initial_state = {
            "network_model": model,
            "neo4j_manager": manager,
            "disturbances": model.disturbances,
            "affected_shipments": [],
            "proposals": [],
            "final_report": "",
            "status": "started"
        }
        
        # Run the workflow in a thread to avoid blocking FastAPI
        result = await anyio.to_thread.run_sync(workflow_app.invoke, initial_state)
        
        return {
            "status": "completed",
            "final_report": result.get("final_report", "No report generated"),
            "affected": result.get("affected_shipments", [])
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def get_index():
    with open("index.html", "r") as f:
        return HTMLResponse(content=f.read())

# Serve static files if they exist
if os.path.exists("style.css"):
    app.mount("/static", StaticFiles(directory="."), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
