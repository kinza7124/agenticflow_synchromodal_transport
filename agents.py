from crewai import Agent
from langchain_google_genai import ChatGoogleGenerativeAI
from tools import Neo4jSearchTool, PathfindingTool, ServiceCapacityTool, CostCalculatorTool
import os

class SynchromodalAgents:
    def __init__(self, neo4j_manager):
        self.manager = neo4j_manager
        
        # Using the latest stable Flash model (better quota availability)
        self.llm = "gemini/gemini-flash-latest"
        
        # Set all possible environment variables to avoid key/version issues
        if os.getenv("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = os.getenv("GOOGLE_API_KEY")
            os.environ["GEMINI_API_KEY"] = os.getenv("GOOGLE_API_KEY")
        
        # Initialize tools with the manager
        self.search_tool = Neo4jSearchTool(manager=self.manager)
        self.path_tool = PathfindingTool(manager=self.manager)
        self.capacity_tool = ServiceCapacityTool(manager=self.manager)
        self.cost_tool = CostCalculatorTool(manager=self.manager)

    def logistics_coordinator(self):
        return Agent(
            role='Logistics Coordinator',
            goal='Ensure all shipments are replanned efficiently and costs are minimized after disturbances.',
            backstory="""You are a veteran logistics manager at the Port of Rotterdam. 
            You oversee the entire hinterland network and coordinate between different shipment agents 
            and service operators to maintain a high modal split for sustainable transport (barge and rail) 
            while meeting strict delivery deadlines.""",
            tools=[self.search_tool, self.path_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=True
        )

    def shipment_agent(self, shipment_id):
        return Agent(
            role=f'Shipment Agent for {shipment_id}',
            goal=f'Find the best transportation route for shipment {shipment_id} that respects time windows and minimizes total cost.',
            backstory=f"You represent the interests of shipment {shipment_id}. IMPORTANT: Always use technical IDs (like 'POR', 'DUIS', 'v0001') in your tools. Do NOT use city names. Use Pathfinding Tool with terminal IDs to find routes. You prefer barge or rail for lower costs but will switch to truck if deadlines are at risk.",
            tools=[self.path_tool, self.cost_tool, self.capacity_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )

    def service_operator(self, service_mode):
        return Agent(
            role=f'{service_mode.capitalize()} Service Operator',
            goal=f'Optimize the utilization of {service_mode} services and report capacity accurately.',
            backstory=f"""You manage the {service_mode} network. 
            You aim to fill your services to maximum capacity while ensuring on-time departures. 
            You provide real-time updates on delays and capacity availability to the coordinator and shipment agents.""",
            tools=[self.search_tool, self.capacity_tool],
            llm=self.llm,
            verbose=True,
            allow_delegation=False
        )
