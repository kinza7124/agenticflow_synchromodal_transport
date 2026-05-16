from typing import TypedDict, List, Dict, Any, Annotated
from langgraph.graph import StateGraph, END
from neo4j_manager import Neo4jManager
from agents import SynchromodalAgents
from tasks import SynchromodalTasks
from crewai import Crew, Process
import os
import time

# Define the state of the workflow
class ReplanningState(TypedDict):
    network_model: Any  # The SynchromodalTransportationModel object
    neo4j_manager: Any
    disturbances: List[Any]
    affected_shipments: List[str]
    proposals: List[Dict[str, Any]]
    final_report: str
    status: str

def load_network_to_neo4j(state: ReplanningState):
    """Import the current model data into Neo4j."""
    model = state['network_model']
    manager = state['neo4j_manager']
    
    manager.clear_database()
    manager.import_network(
        list(model.terminals.values()),
        list(model.services.values()),
        list(model.shipments.values()),
        list(model.arcs.values())
    )
    return {"status": "network_loaded"}

def detect_disturbances(state: ReplanningState):
    """Identify which shipments need replanning based on disturbances."""
    # In a real scenario, this could be an agent task
    # For simplicity, we extract them from the model
    model = state['network_model']
    affected = [s_id for s_id in model.shipments.keys()] # Assume all for demo, or filter
    return {"affected_shipments": affected, "status": "disturbances_detected"}

def run_agentic_negotiation(state: ReplanningState):
    """Execute the CrewAI process to find new routes."""
    manager = state['neo4j_manager']
    agents_factory = SynchromodalAgents(manager)
    tasks_factory = SynchromodalTasks()
    
    coordinator = agents_factory.logistics_coordinator()
    
    all_proposals = []
    
    # Limit to 2 shipments for the demo to avoid hitting Gemini Free Tier limits (20 req/day)
    demo_shipments = state['affected_shipments'][:2]
    if len(state['affected_shipments']) > 2:
        print(f"\n>>> NOTE: Limiting replanning to 2 shipments (out of {len(state['affected_shipments'])}) to preserve API quota.")
    
    # For each affected shipment, run a micro-crew or task
    for s_id in demo_shipments:
        print(f"\n>>> Negotiating route for Shipment {s_id}...")
        shipment_agent = agents_factory.shipment_agent(s_id)
        negotiate_task = tasks_factory.negotiate_route(shipment_agent, s_id)
        
        crew = Crew(
            agents=[shipment_agent],
            tasks=[negotiate_task],
            verbose=True,
            process=Process.sequential
        )
        
        result = crew.kickoff()
        all_proposals.append({"shipment_id": s_id, "result": result})
        
        # Small delay to avoid rate limiting
        time.sleep(2)
        
    return {"proposals": all_proposals, "status": "negotiation_complete"}

def finalize_and_validate(state: ReplanningState):
    """Consolidate the results and validate against constraints."""
    manager = state['neo4j_manager']
    agents_factory = SynchromodalAgents(manager)
    tasks_factory = SynchromodalTasks()
    
    coordinator = agents_factory.logistics_coordinator()
    finalize_task = tasks_factory.finalize_replanning(coordinator, state['proposals'])
    
    crew = Crew(
        agents=[coordinator],
        tasks=[finalize_task],
        verbose=True
    )
    
    report = crew.kickoff()
    return {"final_report": report, "status": "completed"}

# Build the graph
def create_replanning_workflow():
    workflow = StateGraph(ReplanningState)
    
    # Add nodes
    workflow.add_node("load_network", load_network_to_neo4j)
    workflow.add_node("detect_disturbances", detect_disturbances)
    workflow.add_node("run_negotiation", run_agentic_negotiation)
    workflow.add_node("finalize", finalize_and_validate)
    
    # Set edges
    workflow.set_entry_point("load_network")
    workflow.add_edge("load_network", "detect_disturbances")
    workflow.add_edge("detect_disturbances", "run_negotiation")
    workflow.add_edge("run_negotiation", "finalize")
    workflow.add_edge("finalize", END)
    
    return workflow.compile()
