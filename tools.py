from crewai.tools import BaseTool
from neo4j_manager import Neo4jManager
from typing import List, Dict, Any

class Neo4jSearchTool(BaseTool):
    name: str = "Neo4j Search Tool"
    description: str = "Search for paths and service statuses in the Neo4j transportation graph."
    manager: Any = None

    def _run(self, query: str) -> str:
        if not self.manager:
            return "Neo4j manager not initialized."
        results = self.manager.query(query)
        return str(results)

class PathfindingTool(BaseTool):
    name: str = "Pathfinding Tool"
    description: str = "Find feasible paths between terminals given time constraints. Use technical IDs (e.g., 'POR', 'DUIS')."
    manager: Any = None

    def _run(self, origin: str, destination: str, earliest: float, latest: float) -> str:
        """Finds feasible paths. IMPORTANT: Use Terminal IDs (e.g., 'POR', 'DUIS'), NOT city names."""
        if not self.manager:
            return "Neo4j manager not initialized."
        paths = self.manager.find_feasible_paths(origin, destination, float(earliest), float(latest))
        if not paths:
            return f"No feasible paths found between {origin} and {destination} within the given time windows. Try searching for terminal IDs if you used city names."
        return str(paths)

class ServiceCapacityTool(BaseTool):
    name: str = "Service Capacity Tool"
    description: str = "Check the remaining capacity of a specific service on a given arc."
    manager: Any = None

    def _run(self, service_id: str, arc_id: str) -> str:
        if not self.manager:
            return "Neo4j manager not initialized."
        # Query to get total volume assigned to this arc
        query = """
        MATCH (a:Arc {id: $arc_id})<-[:ASSIGNED_TO]-(s:Shipment)
        RETURN sum(s.volume) as used_volume
        """
        res = self.manager.query(query, {"arc_id": arc_id})
        used = res[0]['used_volume'] if res and res[0]['used_volume'] else 0
        
        # Get service capacity
        svc = self.manager.get_service_status(service_id)
        capacity = svc.get('capacity', 0)
        
        return f"Service {service_id} on arc {arc_id} has {capacity - used} TEU available out of {capacity}."

class CostCalculatorTool(BaseTool):
    name: str = "Cost Calculator Tool"
    description: str = "Calculate the total cost of a proposed path for a shipment."
    manager: Any = None

    def _run(self, shipment_id: str, arc_ids: List[str]) -> str:
        if not self.manager:
            return "Neo4j manager not initialized."
        
        # Get shipment volume
        shipment_query = "MATCH (s:Shipment {id: $id}) RETURN s"
        shipment = self.manager.query(shipment_query, {"id": shipment_id})[0]['s']
        volume = shipment['volume']
        
        total_var_cost = 0
        for arc_id in arc_ids:
            arc_query = "MATCH (a:Arc {id: $id}) RETURN a"
            arc = self.manager.query(arc_query, {"id": arc_id})[0]['a']
            total_var_cost += arc['variable_cost'] * volume
            
        # Simplified cost - in a real scenario we'd add transshipment and fixed costs
        return f"Total estimated variable cost for shipment {shipment_id} via {arc_ids} is €{total_var_cost:.2f}."
