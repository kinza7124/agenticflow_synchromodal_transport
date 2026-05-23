"""
Neo4j Manager — optimized with batched imports and corrected pathfinding.
"""
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
        self.connect()

    def connect(self):
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
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
            self.connect()
        if not self.driver:
            return []
        with self.driver.session() as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]

    def clear_database(self):
        """Delete all nodes and relationships in batches to avoid memory issues."""
        if not self.driver:
            self.connect()
        if not self.driver:
            return
        # Batch delete to avoid heap exhaustion on large graphs
        with self.driver.session() as session:
            session.run(
                "CALL apoc.periodic.iterate("
                "  'MATCH (n) RETURN n',"
                "  'DETACH DELETE n',"
                "  {batchSize: 1000}"
                ") YIELD batches, total RETURN batches, total"
            )
        print("Database cleared.")

    def _clear_database_fallback(self):
        """Fallback clear without APOC."""
        self.query("MATCH (n) DETACH DELETE n")
        print("Database cleared (fallback).")

    # ------------------------------------------------------------------
    # BATCHED IMPORT
    # ------------------------------------------------------------------

    def import_network(
        self,
        terminals: List[Any],
        services: List[Any],
        shipments: List[Any],
        arcs: List[Any],
        buffer_times: Dict[str, float] = None,
    ):
        """Import the transportation network using batched UNWIND queries."""
        if not self.driver:
            self.connect()
        if not self.driver:
            return

        print("Importing network data into Neo4j (batched)...")

        # Try APOC clear first, fall back to simple delete
        try:
            self.clear_database()
        except Exception:
            self._clear_database_fallback()

        # 1. Terminals — single batched upsert
        terminal_rows = [
            {"id": t.id, "name": t.name, "type": t.type, "lat": t.lat, "lon": t.lon}
            for t in terminals
        ]
        self.query(
            """
            UNWIND $rows AS row
            MERGE (n:Terminal {id: row.id})
            SET n.name = row.name, n.type = row.type,
                n.lat  = row.lat,  n.lon  = row.lon
            """,
            {"rows": terminal_rows},
        )

        # 2. Services — single batched upsert
        service_rows = [
            {
                "id": s.id,
                "mode": s.mode,
                "capacity": s.capacity,
                "fixed_cost": s.fixed_cost,
                "variable_cost": s.variable_cost,
                "cancellation_cost": s.cancellation_cost,
                "departure_time": s.departure_time,
                "arrival_time": s.arrival_time,
                "traverse_time": s.traverse_time,
            }
            for s in services
        ]
        self.query(
            """
            UNWIND $rows AS row
            MERGE (v:Service {id: row.id})
            SET v.mode              = row.mode,
                v.capacity          = row.capacity,
                v.fixed_cost        = row.fixed_cost,
                v.variable_cost     = row.variable_cost,
                v.cancellation_cost = row.cancellation_cost,
                v.departure_time    = row.departure_time,
                v.arrival_time      = row.arrival_time,
                v.traverse_time     = row.traverse_time,
                v.status            = 'operational'
            """,
            {"rows": service_rows},
        )

        # 3. Arcs — batched upsert + relationships
        buffer_times = buffer_times or {}
        arc_rows = [
            {
                "id": a.id,
                "from_id": a.from_terminal,
                "to_id": a.to_terminal,
                "service_id": a.service_id,
                "departure_time": a.departure_time,
                "arrival_time": a.arrival_time,
                "traverse_time": a.traverse_time,
                "variable_cost": a.variable_cost,
                "buffer_time": float(buffer_times.get(a.id, 0.0)),
            }
            for a in arcs
        ]
        self.query(
            """
            UNWIND $rows AS row
            MATCH (from:Terminal {id: row.from_id})
            MATCH (to:Terminal   {id: row.to_id})
            MATCH (svc:Service   {id: row.service_id})
            MERGE (arc:Arc {id: row.id})
            SET arc.departure_time = row.departure_time,
                arc.arrival_time   = row.arrival_time,
                arc.traverse_time  = row.traverse_time,
                arc.variable_cost  = row.variable_cost,
                arc.from_terminal  = row.from_id,
                arc.to_terminal    = row.to_id,
                arc.service_id     = row.service_id,
                arc.buffer_time    = row.buffer_time
            MERGE (from)-[:DEPARTURE_ARC]->(arc)
            MERGE (arc)-[:ARRIVAL_ARC]->(to)
            MERGE (svc)-[:HAS_ARC]->(arc)
            """,
            {"rows": arc_rows},
        )

        # 4. Shipments — batched upsert + relationships
        shipment_rows = [
            {
                "id": sh.id,
                "origin": sh.origin,
                "destination": sh.destination,
                "volume": sh.volume,
                "release_time": sh.release_time,
                "due_time": sh.due_time,
                "latest_time": sh.latest_time,
                "early_penalty": sh.early_penalty,
                "late_penalty": sh.late_penalty,
            }
            for sh in shipments
        ]
        self.query(
            """
            UNWIND $rows AS row
            MATCH (origin:Terminal {id: row.origin})
            MATCH (dest:Terminal   {id: row.destination})
            MERGE (s:Shipment {id: row.id})
            SET s.volume        = row.volume,
                s.release_time  = row.release_time,
                s.due_time      = row.due_time,
                s.latest_time   = row.latest_time,
                s.early_penalty = row.early_penalty,
                s.late_penalty  = row.late_penalty,
                s.status        = 'pending'
            MERGE (s)-[:ORIGINATES_AT]->(origin)
            MERGE (s)-[:DESTINED_FOR]->(dest)
            """,
            {"rows": shipment_rows},
        )

        print("Data import complete.")

    # ------------------------------------------------------------------
    # PATHFINDING
    # ------------------------------------------------------------------

    def find_feasible_paths(
        self,
        origin_id: str,
        dest_id: str,
        earliest_start: float,
        latest_arrival: float,
    ) -> List[Dict[str, Any]]:
        """
        Find Arc-level paths that satisfy time constraints, accounting for 
        operational buffer delay windows.
        """
        # 1. 2-hop path query with transshipment handling time (1.0h) and buffer windows
        query = """
        MATCH (start:Terminal {id: $origin})
        MATCH (end:Terminal   {id: $dest})
        MATCH (start)-[:DEPARTURE_ARC]->(a1:Arc)-[:ARRIVAL_ARC]->(mid:Terminal)-[:DEPARTURE_ARC]->(a2:Arc)-[:ARRIVAL_ARC]->(end)
        WITH a1, a2,
             (CASE WHEN a1.departure_time >= $earliest THEN a1.departure_time ELSE $earliest END) AS act_dep1
        WITH a1, a2, act_dep1,
             (act_dep1 + a1.traverse_time) AS act_arr1
        WITH a1, a2, act_dep1, act_arr1,
             (CASE WHEN a2.departure_time >= (act_arr1 + 1.0) THEN a2.departure_time ELSE (act_arr1 + 1.0) END) AS act_dep2
        WITH a1, a2, act_dep1, act_arr1, act_dep2,
             (act_dep2 + a2.traverse_time) AS act_arr2
        WHERE a1.departure_time + coalesce(a1.buffer_time, 0.0) >= $earliest
          AND a2.departure_time + coalesce(a2.buffer_time, 0.0) >= act_arr1 + 1.0
          AND act_arr2 <= $latest
        RETURN [a1.id, a2.id] AS arc_ids,
               [a1.variable_cost, a2.variable_cost] AS costs,
               [act_dep1, act_dep2] AS dep_times,
               [act_arr1, act_arr2] AS arr_times,
               (a1.variable_cost + a2.variable_cost) AS total_cost
        ORDER BY total_cost ASC
        LIMIT 10
        """
        results = self.query(
            query,
            {
                "origin": origin_id,
                "dest": dest_id,
                "earliest": earliest_start,
                "latest": latest_arrival,
            },
        )

        # 2. Direct single-arc paths (origin → arc → dest) with buffer window
        direct_query = """
        MATCH (start:Terminal {id: $origin})-[:DEPARTURE_ARC]->(arc:Arc)-[:ARRIVAL_ARC]->(end:Terminal {id: $dest})
        WITH arc,
             (CASE WHEN arc.departure_time >= $earliest THEN arc.departure_time ELSE $earliest END) AS act_dep
        WITH arc, act_dep,
             (act_dep + arc.traverse_time) AS act_arr
        WHERE arc.departure_time + coalesce(arc.buffer_time, 0.0) >= $earliest
          AND act_arr <= $latest
        RETURN [arc.id] AS arc_ids,
               [arc.variable_cost] AS costs,
               [act_dep] AS dep_times,
               [act_arr] AS arr_times,
               arc.variable_cost AS total_cost
        ORDER BY total_cost ASC
        LIMIT 5
        """
        direct = self.query(
            direct_query,
            {
                "origin": origin_id,
                "dest": dest_id,
                "earliest": earliest_start,
                "latest": latest_arrival,
            },
        )

        return direct + results

    # ------------------------------------------------------------------
    # SERVICE / SHIPMENT HELPERS
    # ------------------------------------------------------------------

    def get_service_status(self, service_id: str) -> Dict[str, Any]:
        result = self.query("MATCH (v:Service {id: $id}) RETURN v", {"id": service_id})
        return result[0]["v"] if result else {}

    def get_arc_with_capacity(self, arc_id: str) -> Dict[str, Any]:
        """Return arc properties plus current used volume in one query."""
        result = self.query(
            """
            MATCH (a:Arc {id: $arc_id})
            OPTIONAL MATCH (a)<-[:ASSIGNED_TO]-(s:Shipment)
            WITH a, coalesce(sum(s.volume), 0) AS used_volume
            MATCH (svc:Service)-[:HAS_ARC]->(a)
            RETURN a, svc.capacity AS capacity, used_volume,
                   (svc.capacity - used_volume) AS available
            """,
            {"arc_id": arc_id},
        )
        return result[0] if result else {}

    def get_shipment_with_terminals(self, shipment_id: str) -> Dict[str, Any]:
        """Return shipment + origin/destination terminal IDs in one query."""
        result = self.query(
            """
            MATCH (s:Shipment {id: $id})-[:ORIGINATES_AT]->(o:Terminal),
                  (s)-[:DESTINED_FOR]->(d:Terminal)
            RETURN s, o.id AS origin_id, d.id AS dest_id
            """,
            {"id": shipment_id},
        )
        return result[0] if result else {}

    def update_shipment_assignment(self, shipment_id: str, arc_ids: List[str]):
        """Mark shipment as assigned to specific arcs (batched)."""
        self.query(
            """
            MATCH (s:Shipment {id: $shipment_id})
            SET s.status = 'assigned', s.path = $arc_ids
            """,
            {"shipment_id": shipment_id, "arc_ids": arc_ids},
        )
        # Batch-create ASSIGNED_TO relationships
        self.query(
            """
            UNWIND $arc_ids AS arc_id
            MATCH (s:Shipment {id: $shipment_id})
            MATCH (a:Arc {id: arc_id})
            MERGE (s)-[:ASSIGNED_TO]->(a)
            """,
            {"shipment_id": shipment_id, "arc_ids": arc_ids},
        )


if __name__ == "__main__":
    manager = Neo4jManager()
    if manager.driver:
        manager.close()
