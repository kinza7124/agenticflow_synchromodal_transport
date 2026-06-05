"""
Neo4j Manager — optimized with batched imports, corrected pathfinding, and robust in-memory database fallback.
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
        
        # In-memory storage fallback database
        self.terminals_db: Dict[str, Dict] = {}
        self.services_db: Dict[str, Dict] = {}
        self.arcs_db: Dict[str, Dict] = {}
        self.shipments_db: Dict[str, Dict] = {}
        self.assignments_db: Dict[str, List[str]] = {}
        
        self.connect()

    def connect(self):
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self.driver.verify_connectivity()
            print(f"Connected to Neo4j at {self.uri}")
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")
            print("Neo4j database offline. Activating IN-MEMORY simulator fallback mode.")
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()

    def query(self, cypher: str, parameters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        if not self.driver:
            # Simple simulation for CostCalculatorTool
            if "MATCH (s:Shipment {id: $shipment_id})" in cypher:
                shipment_id = parameters.get("shipment_id")
                arc_ids = parameters.get("arc_ids", [])
                s = self.shipments_db.get(shipment_id)
                results = []
                for aid in arc_ids:
                    a = self.arcs_db.get(aid)
                    results.append({
                        "volume": s["volume"] if s else 0,
                        "arc_id": aid,
                        "var_cost": a["variable_cost"] if a else 0.0
                    })
                return results
            return []

        with self.driver.session() as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]

    def clear_database(self):
        """Delete all nodes and relationships in batches to avoid memory issues."""
        if not self.driver:
            self.terminals_db.clear()
            self.services_db.clear()
            self.arcs_db.clear()
            self.shipments_db.clear()
            self.assignments_db.clear()
            print("In-memory database cleared.")
            return

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
        if not self.driver:
            self.clear_database()
            return
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
            print("Importing network data into in-memory database...")
            self.clear_database()
            self.terminals_db = {t.id: {"id": t.id, "name": t.name, "type": t.type, "lat": t.lat, "lon": t.lon} for t in terminals}
            self.services_db = {s.id: {
                "id": s.id, "mode": s.mode, "capacity": s.capacity, "fixed_cost": s.fixed_cost,
                "variable_cost": s.variable_cost, "cancellation_cost": s.cancellation_cost,
                "departure_time": s.departure_time, "arrival_time": s.arrival_time, "traverse_time": s.traverse_time
            } for s in services}
            self.arcs_db = {a.id: {
                "id": a.id, "from_terminal": a.from_terminal, "to_terminal": a.to_terminal, "service_id": a.service_id,
                "departure_time": a.departure_time, "arrival_time": a.arrival_time, "traverse_time": a.traverse_time,
                "variable_cost": a.variable_cost, "buffer_time": float(buffer_times.get(a.id, 0.0)) if buffer_times else 0.0
            } for a in arcs}
            self.shipments_db = {sh.id: {
                "id": sh.id, "origin": sh.origin, "destination": sh.destination, "volume": sh.volume,
                "release_time": sh.release_time, "due_time": sh.due_time, "latest_time": sh.latest_time,
                "early_penalty": sh.early_penalty, "late_penalty": sh.late_penalty, "status": "pending"
            } for sh in shipments}
            self.assignments_db = {}
            print("In-memory network data import complete.")
            return

        print("Importing network data into Neo4j (batched)...")
        try:
            self.clear_database()
        except Exception:
            self._clear_database_fallback()

        # 1. Terminals
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

        # 2. Services
        service_rows = [
            {
                "id": s.id, "mode": s.mode, "capacity": s.capacity, "fixed_cost": s.fixed_cost,
                "variable_cost": s.variable_cost, "cancellation_cost": s.cancellation_cost,
                "departure_time": s.departure_time, "arrival_time": s.arrival_time, "traverse_time": s.traverse_time
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

        # 3. Arcs
        buffer_times = buffer_times or {}
        arc_rows = [
            {
                "id": a.id, "from_id": a.from_terminal, "to_id": a.to_terminal, "service_id": a.service_id,
                "departure_time": a.departure_time, "arrival_time": a.arrival_time, "traverse_time": a.traverse_time,
                "variable_cost": a.variable_cost, "buffer_time": float(buffer_times.get(a.id, 0.0))
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

        # 4. Shipments
        shipment_rows = [
            {
                "id": sh.id, "origin": sh.origin, "destination": sh.destination, "volume": sh.volume,
                "release_time": sh.release_time, "due_time": sh.due_time, "latest_time": sh.latest_time,
                "early_penalty": sh.early_penalty, "late_penalty": sh.late_penalty
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
        if not self.driver:
            # Python in-memory pathfinding simulation
            paths = []
            
            # Direct paths
            for a_id, a in self.arcs_db.items():
                if a["from_terminal"] == origin_id and a["to_terminal"] == dest_id:
                    act_dep = max(a["departure_time"], earliest_start)
                    act_arr = act_dep + a["traverse_time"]
                    
                    # Buffer check: departure_time + buffer >= earliest_start
                    if a["departure_time"] + a["buffer_time"] >= earliest_start and act_arr <= latest_arrival:
                        paths.append({
                            "arc_ids": [a_id],
                            "costs": [a["variable_cost"]],
                            "dep_times": [act_dep],
                            "arr_times": [act_arr],
                            "total_cost": a["variable_cost"]
                        })
            
            # 2-hop paths (origin -> mid -> dest)
            for a1_id, a1 in self.arcs_db.items():
                if a1["from_terminal"] == origin_id:
                    mid = a1["to_terminal"]
                    for a2_id, a2 in self.arcs_db.items():
                        if a2["from_terminal"] == mid and a2["to_terminal"] == dest_id:
                            act_dep1 = max(a1["departure_time"], earliest_start)
                            act_arr1 = act_dep1 + a1["traverse_time"]
                            
                            # Account for transshipment buffer (1.0h)
                            act_dep2 = max(a2["departure_time"], act_arr1 + 1.0)
                            act_arr2 = act_dep2 + a2["traverse_time"]
                            
                            if (a1["departure_time"] + a1["buffer_time"] >= earliest_start and
                                a2["departure_time"] + a2["buffer_time"] >= act_arr1 + 1.0 and
                                act_arr2 <= latest_arrival):
                                paths.append({
                                    "arc_ids": [a1_id, a2_id],
                                    "costs": [a1["variable_cost"], a2["variable_cost"]],
                                    "dep_times": [act_dep1, act_dep2],
                                    "arr_times": [act_arr1, act_arr2],
                                    "total_cost": a1["variable_cost"] + a2["variable_cost"]
                                })
            
            paths.sort(key=lambda x: x["total_cost"])
            return paths[:10]

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
        if not self.driver:
            return self.services_db.get(service_id, {})
        result = self.query("MATCH (v:Service {id: $id}) RETURN v", {"id": service_id})
        return result[0]["v"] if result else {}

    def get_arc_with_capacity(self, arc_id: str) -> Dict[str, Any]:
        """Return arc properties plus current used volume."""
        if not self.driver:
            a = self.arcs_db.get(arc_id)
            if not a: return {}
            svc = self.services_db.get(a["service_id"])
            capacity = svc["capacity"] if svc else 0
            used = 0
            for sh_id, path in self.assignments_db.items():
                if arc_id in path:
                    sh = self.shipments_db.get(sh_id)
                    if sh:
                        used += sh["volume"]
            return {
                "a": a,
                "capacity": capacity,
                "used_volume": used,
                "available": capacity - used
            }

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
        if not self.driver:
            sh = self.shipments_db.get(shipment_id)
            if not sh: return {}
            return {
                "s": sh,
                "origin_id": sh["origin"],
                "dest_id": sh["destination"]
            }

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
        """Mark shipment as assigned to specific arcs."""
        if not self.driver:
            self.assignments_db[shipment_id] = arc_ids
            if shipment_id in self.shipments_db:
                self.shipments_db[shipment_id]["status"] = "assigned"
                self.shipments_db[shipment_id]["path"] = arc_ids
            return

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

    # ------------------------------------------------------------------
    # IN-MEMORY CYTOSCAPE ELEMENT BUILDER
    # ------------------------------------------------------------------

    def get_in_memory_cytoscape_elements(self) -> Dict[str, List]:
        nodes = []
        edges = []

        # Add terminals
        for t_id, t in self.terminals_db.items():
            nodes.append({
                "data": {
                    "id": t_id,
                    "label": f"Terminal: {t['name'] or t_id}",
                    "type": "Terminal",
                    **t
                }
            })

        # Add services
        for s_id, s in self.services_db.items():
            nodes.append({
                "data": {
                    "id": s_id,
                    "label": f"Service: {s_id}",
                    "type": "Service",
                    **s
                }
            })

        # Add shipments
        for sh_id, sh in self.shipments_db.items():
            nodes.append({
                "data": {
                    "id": sh_id,
                    "label": f"Shipment: {sh_id}",
                    "type": "Shipment",
                    **sh
                }
            })

        # Add arcs
        for a_id, a in self.arcs_db.items():
            nodes.append({
                "data": {
                    "id": a_id,
                    "label": f"Arc: {a_id}",
                    "type": "Arc",
                    **a
                }
            })

            # Connect terminals to arcs
            edges.append({
                "data": {
                    "id": f"dep_{a_id}",
                    "source": a["from_terminal"],
                    "target": a_id,
                    "label": "DEPARTURE_ARC",
                    "type": "DEPARTURE_ARC"
                }
            })
            edges.append({
                "data": {
                    "id": f"arr_{a_id}",
                    "source": a_id,
                    "target": a["to_terminal"],
                    "label": "ARRIVAL_ARC",
                    "type": "ARRIVAL_ARC"
                }
            })
            # Connect service to arc
            edges.append({
                "data": {
                    "id": f"svc_{a_id}",
                    "source": a["service_id"],
                    "target": a_id,
                    "label": "HAS_ARC",
                    "type": "HAS_ARC"
                }
            })

        # Add shipment relationships (ORIGINATES_AT, DESTINED_FOR)
        for sh_id, sh in self.shipments_db.items():
            edges.append({
                "data": {
                    "id": f"orig_{sh_id}",
                    "source": sh_id,
                    "target": sh["origin"],
                    "label": "ORIGINATES_AT",
                    "type": "ORIGINATES_AT"
                }
            })
            edges.append({
                "data": {
                    "id": f"dest_{sh_id}",
                    "source": sh_id,
                    "target": sh["destination"],
                    "label": "DESTINED_FOR",
                    "type": "DESTINED_FOR"
                }
            })

        # Add ASSIGNED_TO paths
        for sh_id, path in self.assignments_db.items():
            for aid in path:
                edges.append({
                    "data": {
                        "id": f"assign_{sh_id}_{aid}",
                        "source": sh_id,
                        "target": aid,
                        "label": "ASSIGNED_TO",
                        "type": "ASSIGNED_TO"
                    }
                })

        return {"elements": nodes + edges}


if __name__ == "__main__":
    manager = Neo4jManager()
    if manager.driver:
        manager.close()
