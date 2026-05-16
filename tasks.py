from crewai import Task

class SynchromodalTasks:
    def identify_disturbances(self, agent, disturbances):
        return Task(
            description=f"""Analyze the following disturbances and identify which shipments and services are affected:
            {disturbances}
            Update the status of affected entities in the system and report back a list of shipments that need replanning.""",
            expected_output="A list of shipment IDs that require immediate replanning.",
            agent=agent
        )

    def negotiate_route(self, agent, shipment_id):
        return Task(
            description=f"""For shipment {shipment_id}, find a feasible path from its origin to destination.
            1. Use the Pathfinding Tool to find candidate paths.
            2. Check capacity for each leg of the path using the Service Capacity Tool.
            3. Calculate the total cost using the Cost Calculator Tool.
            4. Propose the best path (lowest cost + feasible) and justify your choice.""",
            expected_output=f"A recommended path (list of arc IDs) for shipment {shipment_id} and the estimated cost.",
            agent=agent
        )

    def finalize_replanning(self, agent, proposals):
        return Task(
            description=f"""Review all routing proposals for affected shipments:
            {proposals}
            Check for any capacity conflicts (where multiple shipments might be using the same remaining space).
            Provide a final, consolidated replanning report with the new assignments and total network cost.""",
            expected_output="A comprehensive replanning report including all shipment re-assignments and KPI impact.",
            agent=agent
        )
