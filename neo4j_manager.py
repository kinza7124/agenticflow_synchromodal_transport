import os
from neo4j import GraphDatabase
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class Neo4jManager:
    def __init__(self, uri: str = None, user: str = None, password: str = None):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.driver = None
        
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            # Test connection
            self.driver.verify_connectivity()
            print(f"Connected to Neo4j at {self.uri}")
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()

    def query(self, cypher: str, parameters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        if not self.driver:
            return []
        with self.driver.session() as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]

    def clear_database(self):
        """Delete all nodes and relationships."""
        self.query("MATCH (n) DETACH DELETE n")
        print("Database cleared.")

    def import_network(self, terminals: List[Any], services: List[Any], shipments: List[Any], arcs: List[Any]):
        """Import the transportation network into Neo4j."""
        if not self.driver:
            return

        print("Importing network data into Neo4j...")
        
        # 1. Create Terminals
        for t in terminals:
            self.query("""
                MERGE (n:Terminal {id: $id})
                SET n.name = $name, n.type = $type, n.lat = $lat, n.lon = $lon
            """, {"id": t.id, "name": t.name, "type": t.type, "lat": t.lat, "lon": t.lon})

        # 2. Create Services
        for s in services:
            self.query("""
                MERGE (v:Service {id: $id})
                SET v.mode = $mode, v.capacity = $capacity, v.fixed_cost = $fixed_cost, 
                    v.variable_cost = $variable_cost, v.cancellation_cost = $cancellation_cost,
                    v.departure_time = $departure_time, v.arrival_time = $arrival_time,
                    v.traverse_time = $traverse_time, v.status = 'operational'
            """, {
                "id": s.id, "mode": s.mode, "capacity": s.capacity, 
                "fixed_cost": s.fixed_cost, "variable_cost": s.variable_cost, 
                "cancellation_cost": s.cancellation_cost,
                "departure_time": s.departure_time, "arrival_time": s.arrival_time,
                "traverse_time": s.traverse_time
            })

        # 3. Create Arcs and link to Terminals and Services
        for a in arcs:
            self.query("""
                MATCH (from:Terminal {id: $from_id})
                MATCH (to:Terminal {id: $to_id})
                MATCH (v:Service {id: $service_id})
                MERGE (arc:Arc {id: $id})
                SET arc.departure_time = $departure_time, arc.arrival_time = $arrival_time,
                    arc.traverse_time = $traverse_time, arc.variable_cost = $variable_cost
                MERGE (from)-[:DEPARTURE_ARC]->(arc)
                MERGE (arc)-[:ARRIVAL_ARC]->(to)
                MERGE (v)-[:HAS_ARC]->(arc)
            """, {
                "id": a.id, "from_id": a.from_terminal, "to_id": a.to_terminal, 
                "service_id": a.service_id, "departure_time": a.departure_time, 
                "arrival_time": a.arrival_time, "traverse_time": a.traverse_time, 
                "variable_cost": a.variable_cost
            })

        # 4. Create Shipments
        for sh in shipments:
            self.query("""
                MATCH (origin:Terminal {id: $origin})
                MATCH (dest:Terminal {id: $destination})
                MERGE (s:Shipment {id: $id})
                SET s.volume = $volume, s.release_time = $release_time, 
                    s.due_time = $due_time, s.latest_time = $latest_time,
                    s.early_penalty = $early_penalty, s.late_penalty = $late_penalty,
                    s.status = 'pending'
                MERGE (s)-[:ORIGINATES_AT]->(origin)
                MERGE (s)-[:DESTINED_FOR]->(dest)
            """, {
                "id": sh.id, "origin": sh.origin, "destination": sh.destination,
                "volume": sh.volume, "release_time": sh.release_time,
                "due_time": sh.due_time, "latest_time": sh.latest_time,
                "early_penalty": sh.early_penalty, "late_penalty": sh.late_penalty
            })
        
        print("Data import complete.")

    def find_feasible_paths(self, origin_id: str, dest_id: str, earliest_start: float, latest_arrival: float) -> List[Dict[str, Any]]:
        """Find paths in the graph that satisfy time constraints."""
        # Simple pathfinding using Cypher
        # Note: This is a simplified version, real-world might need more complex logic for waits
        query = """
        MATCH p = (start:Terminal {id: $origin})-[:DEPARTURE_ARC|ARRIVAL_ARC*..10]->(end:Terminal {id: $dest})
        WITH p, relationships(p) as rels, nodes(p) as path_nodes
        WHERE ALL(idx in range(0, size(rels)-1) WHERE 
            CASE 
                WHEN type(rels[idx]) = 'DEPARTURE_ARC' THEN 
                    rels[idx].departure_time >= $earliest 
                WHEN type(rels[idx]) = 'ARRIVAL_ARC' THEN 
                    rels[idx].arrival_time <= $latest
                ELSE true
            END
        )
        RETURN p, [r in rels | r.id] as arc_ids, [r in rels | r.variable_cost] as costs
        """
        return self.query(query, {"origin": origin_id, "dest": dest_id, "earliest": earliest_start, "latest": latest_arrival})

    def get_service_status(self, service_id: str) -> Dict[str, Any]:
        result = self.query("MATCH (v:Service {id: $id}) RETURN v", {"id": service_id})
        return result[0]['v'] if result else {}

    def update_shipment_assignment(self, shipment_id: str, arc_ids: List[str]):
        """Mark shipment as assigned to specific arcs."""
        self.query("""
            MATCH (s:Shipment {id: $shipment_id})
            SET s.status = 'assigned', s.path = $arc_ids
        """, {"shipment_id": shipment_id, "arc_ids": arc_ids})
        
        for arc_id in arc_ids:
            self.query("""
                MATCH (s:Shipment {id: $shipment_id})
                MATCH (a:Arc {id: $arc_id})
                MERGE (s)-[:ASSIGNED_TO]->(a)
            """, {"shipment_id": shipment_id, "arc_id": arc_id})

if __name__ == "__main__":
    # Test stub
    manager = Neo4jManager()
    if manager.driver:
        manager.clear_database()
        manager.close()
