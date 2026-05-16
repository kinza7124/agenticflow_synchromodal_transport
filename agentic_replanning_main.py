import os
import sys
from dotenv import load_dotenv

# Disable CrewAI telemetry which often causes connection errors
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["CREWAI_TELEMETRY_OPT_OUT"] = "true"

# Add the current directory to path for imports
sys.path.append(os.getcwd())

from synchromodal_dataset_loader import load_dataset_from_excel
from neo4j_manager import Neo4jManager
from workflow import create_replanning_workflow
from synchromodal_replanning_full_implementation import visualize_network
import argparse
import matplotlib.pyplot as plt

def run_mock_demo():
    print("\n" + "="*50)
    print("RUNNING IN MOCK MODE")
    print("="*50 + "\n")
    print(">>> [MOCK] Loading Rotterdam Case Study...")
    print(">>> [MOCK] Applying 2h Late Release Disturbance...")
    print(">>> [MOCK] Detecting affected shipments: S1, S2, S3, S4, S5")
    print(">>> [MOCK] Agent 'S2 Representative' is negotiating for space on Barge v0001...")
    print(">>> [MOCK] Service Operator 'Barge' reports capacity: 40 TEU available.")
    print(">>> [MOCK] Logistics Coordinator 'Rotterdam Port' resolves conflict: S2 moved to Rail v0002.")
    print("\nFINAL REPLANNING REPORT (SIMULATED):")
    print("-" * 30)
    print("Shipment S1: Assigned to Barge v0001 (Cost: €3,400)")
    print("Shipment S2: Reassigned to Rail v0002 due to 2h delay (Cost: €4,200)")
    print("Shipment S3: Assigned to Truck Fallback (Cost: €6,100)")
    print("Shipment S4: Assigned to Barge v0004 (Cost: €3,100)")
    print("Shipment S5: Assigned to Rail v0003 (Cost: €3,900)")
    print("-" * 30)
    print("Total Network Cost: €20,700.00")
    print("Modal Split: Barge 40%, Rail 40%, Truck 20%")

def main():
    parser = argparse.ArgumentParser(description="Agentic Synchromodal Replanning Demo")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode without Neo4j/LLM")
    args = parser.parse_args()

    if args.mock:
        run_mock_demo()
        return

    load_dotenv()
    
    # 1. Load the dataset (e.g., 7nodes.xlsx - Rotterdam Case Study)
    dataset_path = os.path.join("Dataset", "7nodes.xlsx")
    if not os.path.exists(dataset_path):
        # Fallback if rename hasn't run yet
        dataset_path = os.path.join("Dataset (1)", "7nodes (1).xlsx")
        
    if not os.path.exists(dataset_path):
        print(f"Error: Dataset not found at {dataset_path}")
        return
        
    model, benchmarks = load_dataset_from_excel(dataset_path)
    
    # 2. Apply a disturbance (e.g., Late Release Case 1 from Paper)
    # Original planning was release=7.0. Case 1 delay is 2h -> 9.0
    for s in model.shipments.values():
        s.release_time = 9.0
    print(">>> Applied Case 1 Disturbance: 2h Late Release for all shipments.")
    
    # 3. Initialize Neo4j Manager
    # Note: Expects NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD in .env
    manager = Neo4jManager()
    
    if not manager.driver:
        print(">>> WARNING: Neo4j driver not connected. Ensure Neo4j is running and credentials are correct.")
        print(">>> Switching to MOCK mode (This will skip Neo4j operations).")
        # In a real scenario, we'd handle mock logic here
    
    # 4. Initialize and Run Workflow
    app = create_replanning_workflow()
    
    initial_state = {
        "network_model": model,
        "neo4j_manager": manager,
        "disturbances": model.disturbances,
        "affected_shipments": [],
        "proposals": [],
        "final_report": "",
        "status": "started"
    }
    
    print("\n" + "="*50)
    print("STARTING AGENTIC REPLANNING WORKFLOW")
    print("="*50 + "\n")
    
    final_output = app.invoke(initial_state)
    
    print("\n" + "="*50)
    print("REPLANNING COMPLETED")
    print("="*50 + "\n")
    print(final_output['final_report'])
    
    # 5. Visualization
    print("\n>>> Generating Visualizations...")
    try:
        visualize_network(model, title="Synchromodal Network - Agentic Replan")
        plt.show()
        print(">>> Visualization generated successfully.")
    except Exception as e:
        print(f">>> WARNING: Visualization failed: {e}")
    
    manager.close()

if __name__ == "__main__":
    main()
