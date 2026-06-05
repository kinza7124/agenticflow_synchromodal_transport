"""
Task definitions — concise prompts to reduce token usage per LLM call.
"""
from crewai import Task


class SynchromodalTasks:

    def identify_disturbances(self, agent, disturbances) -> Task:
        # Keep the disturbance description short; the agent doesn't need
        # the full object repr — just the key facts.
        disturbance_summary = str(disturbances)[:800]  # hard cap
        return Task(
            description=(
                f"Disturbances detected:\n{disturbance_summary}\n\n"
                "Identify which shipment IDs are affected and must be replanned. "
                "Return ONLY a comma-separated list of shipment IDs."
            ),
            expected_output="Comma-separated list of shipment IDs, e.g.: S1, S2, S3",
            agent=agent,
        )

    def negotiate_route(self, agent, shipment_id: str, shipment_info: dict = None) -> Task:
        """
        shipment_info (optional): pre-fetched dict with origin, destination,
        release_time, due_time so the agent doesn't need to query Neo4j for basics.
        """
        context = ""
        if shipment_info:
            context = (
                f"Shipment details: origin={shipment_info.get('origin_id')}, "
                f"destination={shipment_info.get('dest_id')}, "
                f"release={shipment_info.get('s', {}).get('release_time')}h, "
                f"due={shipment_info.get('s', {}).get('due_time')}h, "
                f"volume={shipment_info.get('s', {}).get('volume')} TEU.\n"
            )

        return Task(
            description=(
                f"{context}"
                f"Find the best route for shipment {shipment_id}:\n"
                "1. Call Pathfinding Tool: 'ORIGIN,DEST,RELEASE_TIME,DUE_TIME'\n"
                "2. For the top path, call Service Capacity Tool for each arc.\n"
                "3. Call Cost Calculator Tool: 'SHIPMENT_ID:ARC1,ARC2,...'\n"
                "4. Return the recommended arc list and total cost."
            ),
            expected_output=(
                f"Recommended arc IDs for {shipment_id} and estimated total cost in euros."
            ),
            agent=agent,
        )

    def finalize_replanning(self, agent, proposals: list) -> Task:
        # Summarise proposals compactly — avoid dumping full CrewOutput objects
        proposal_lines = []
        for p in proposals:
            sid = p.get("shipment_id", "?")
            result = p.get("result", "")
            # CrewOutput has a .raw attribute; fall back to str()
            result_text = getattr(result, "raw", str(result))[:300]
            proposal_lines.append(f"- {sid}: {result_text}")
        proposals_text = "\n".join(proposal_lines)

        return Task(
            description=(
                "Review the routing proposals below and produce a final report.\n\n"
                f"{proposals_text}\n\n"
                "Check for capacity conflicts (multiple shipments on the same arc). "
                "Output a structured report: shipment → assigned arcs → cost, "
                "plus total network cost and modal split percentages."
            ),
            expected_output=(
                "Structured replanning report with per-shipment assignments, "
                "total cost, and modal split (barge %, rail %, truck %)."
            ),
            agent=agent,
        )
