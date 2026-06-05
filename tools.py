"""
CrewAI Tools — optimized to minimize Neo4j round-trips per call.
"""
from crewai.tools import BaseTool
from typing import List, Any


class Neo4jSearchTool(BaseTool):
    name: str = "Neo4j Search Tool"
    description: str = (
        "Execute a raw Cypher query against the Neo4j transportation graph. "
        "Use for ad-hoc lookups not covered by other tools."
    )
    manager: Any = None

    def _run(self, query: str) -> str:
        if not self.manager:
            return "Neo4j manager not initialized."
        results = self.manager.query(query)
        return str(results[:20])  # cap output to avoid bloating LLM context


class PathfindingTool(BaseTool):
    name: str = "Pathfinding Tool"
    description: str = (
        "Find feasible transportation paths between two terminals within a time window. "
        "Input format: 'ORIGIN,DESTINATION,EARLIEST_HOUR,LATEST_HOUR' "
        "using terminal IDs (e.g., 'POR,DUIS,9.0,24.0'). "
        "Returns ranked paths with arc IDs and costs."
    )
    manager: Any = None

    def _run(self, input_str: str) -> str:
        """
        Accepts a comma-separated string: origin,destination,earliest,latest
        This avoids the LLM needing to pass 4 separate keyword arguments.
        """
        if not self.manager:
            return "Neo4j manager not initialized."
        try:
            parts = [p.strip() for p in input_str.split(",")]
            if len(parts) != 4:
                return (
                    "Invalid input. Expected: 'ORIGIN,DESTINATION,EARLIEST,LATEST' "
                    f"but got: '{input_str}'"
                )
            origin, destination, earliest, latest = parts
            paths = self.manager.find_feasible_paths(
                origin, destination, float(earliest), float(latest)
            )
        except Exception as e:
            return f"Error running pathfinding: {e}"

        if not paths:
            return (
                f"No feasible paths found between {origin} and {destination} "
                f"within [{earliest}, {latest}]. "
                "Verify terminal IDs are correct (e.g., 'POR', 'DUIS', 'T1')."
            )

        # Format concisely so the LLM gets structured, token-efficient output
        lines = [f"Found {len(paths)} path(s):"]
        for i, p in enumerate(paths[:5], 1):  # show top 5
            arc_ids = p.get("arc_ids", [])
            total_cost = p.get("total_cost", "?")
            arr_times = p.get("arr_times", [])
            last_arrival = arr_times[-1] if arr_times else "?"
            lines.append(
                f"  Path {i}: arcs={arc_ids}, total_cost=€{total_cost}, "
                f"arrival={last_arrival}h"
            )
        return "\n".join(lines)


class ServiceCapacityTool(BaseTool):
    name: str = "Service Capacity Tool"
    description: str = (
        "Check remaining capacity on a specific arc. "
        "Input: arc_id (e.g., 'v0001_POR_DUIS'). "
        "Returns available TEU, total capacity, and current utilisation."
    )
    manager: Any = None

    def _run(self, arc_id: str) -> str:
        if not self.manager:
            return "Neo4j manager not initialized."
        arc_id = arc_id.strip()
        data = self.manager.get_arc_with_capacity(arc_id)
        if not data:
            return f"Arc '{arc_id}' not found in the graph."

        capacity = data.get("capacity", 0)
        used = data.get("used_volume", 0)
        available = data.get("available", capacity - used)
        arc = data.get("a", {})
        return (
            f"Arc {arc_id}: capacity={capacity} TEU, used={used} TEU, "
            f"available={available} TEU | "
            f"departs={arc.get('departure_time')}h, arrives={arc.get('arrival_time')}h"
        )


class CostCalculatorTool(BaseTool):
    name: str = "Cost Calculator Tool"
    description: str = (
        "Calculate the total variable transport cost for a shipment along a list of arcs. "
        "Input format: 'SHIPMENT_ID:ARC_ID1,ARC_ID2,...' "
        "(e.g., 'S1:v0001_POR_DUIS,v0002_DUIS_MOE'). "
        "Returns the estimated cost in euros."
    )
    manager: Any = None

    def _run(self, input_str: str) -> str:
        if not self.manager:
            return "Neo4j manager not initialized."
        try:
            shipment_part, arcs_part = input_str.split(":", 1)
            shipment_id = shipment_part.strip()
            arc_ids = [a.strip() for a in arcs_part.split(",") if a.strip()]
        except ValueError:
            return (
                "Invalid input. Expected: 'SHIPMENT_ID:ARC_ID1,ARC_ID2,...' "
                f"but got: '{input_str}'"
            )

        # Single query: fetch shipment volume + all arc costs at once
        result = self.manager.query(
            """
            MATCH (s:Shipment {id: $shipment_id})
            WITH s.volume AS volume
            UNWIND $arc_ids AS arc_id
            MATCH (a:Arc {id: arc_id})
            RETURN volume, arc_id, a.variable_cost AS var_cost
            """,
            {"shipment_id": shipment_id, "arc_ids": arc_ids},
        )

        if not result:
            return f"Shipment '{shipment_id}' or one of the arcs not found."

        volume = result[0]["volume"]
        total_cost = sum(row["var_cost"] * volume for row in result if row["var_cost"])
        breakdown = ", ".join(
            f"{row['arc_id']}=€{row['var_cost'] * volume:.2f}" for row in result
        )
        return (
            f"Shipment {shipment_id} ({volume} TEU) via {arc_ids}: "
            f"total=€{total_cost:.2f} | breakdown: {breakdown}"
        )
