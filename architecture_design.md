# Architecture & System Design: Agentic Synchromodal Freight Replanning

This document provides a detailed breakdown of the system architecture, technology stack, agent personas, database modeling, and step-by-step workflow of the Synchromodal Control Tower application.

---

## 1. High-Level System Architecture

The application is split into three main layers:
1. **Presentation Layer (Frontend)**: Next.js dashboard providing real-time data visualization via Cytoscape.js.
2. **Orchestration & Execution Layer (FastAPI & LangGraph)**: The backend web server hosting the deterministic state machine and the LLM agent crews.
3. **Database & Cognitive Layer (Neo4j & Groq/Llama)**: A graph database representing the physical supply chain networks, queried dynamically by AI agents running on Llama-3.3.

---

## 2. Technology Stack

- **Frontend Framework**: **Next.js 16 (React, Vanilla CSS Modules)**
  - *Graph Rendering*: **Cytoscape.js** for rendering interactive nodes (Terminals, Services, Shipments, Arcs) and paths.
  - *Layout Engine*: Built-in geographical scaling layout that automatically maps longitude/latitude coordinates onto the browser's viewport.
- **Backend API**: **FastAPI (Python)** & **Uvicorn**
  - Handles CORS middlewares, coordinates asynchronous request threads, and triggers the optimization pipeline.
- **State Orchestrator**: **LangGraph (LangChain ecosystem)**
  - Used to define a deterministic `StateGraph` that manages system states, handles execution loops, and ensures strict workflow boundaries.
- **Multi-Agent Framework**: **CrewAI**
  - Organizes agents, tasks, and tools into cooperative groups (Crews) to achieve specific goals.
- **Database (Supply Chain Environment)**: **Neo4j / AuraDB (Graph Database)**
  - Used for storing transportation scheduling, terminals, service capacities, and shipment routing links. Connected via the `bolt` protocol. Includes a local **in-memory dict simulator fallback** if the database connection goes offline.
- **LLM Engine**: **Groq API (`Llama-3.3-70b-versatile`)**
  - Serves as the cognitive worker inside CrewAI. It dynamically decides which tools to call, parses tool outputs, and negotiates path routing based on supply chain constraints.

---

## 3. Database Graph Schema (Neo4j)

The transportation network is modeled as a directed graph representing physical infrastructure and scheduling timetables:

### Nodes
- **`:Terminal`**: Represents hubs, ports, and transshipment locations.
  - Properties: `id`, `name`, `type` (`port` or `hub`), `lat`, `lon`.
- **`:Service`**: Represents carrier routes (Barge lines, Rail operators, Truck fleets).
  - Properties: `id`, `mode` (`barge`, `rail`, `truck`), `capacity` (TEU), `fixed_cost`, `variable_cost`, `departure_time`, `arrival_time`.
- **`:Arc`**: Represents a scheduled transit leg between two terminals.
  - Properties: `id`, `from_terminal`, `to_terminal`, `service_id`, `departure_time`, `arrival_time`, `traverse_time`, `variable_cost`, `buffer_time`.
- **`:Shipment`**: Represents cargo that needs to be moved.
  - Properties: `id`, `origin`, `destination`, `volume` (TEU), `release_time`, `due_time`, `latest_time`, `early_penalty`, `late_penalty`, `status` (`pending`, `assigned`).

### Relationships
- `(:Terminal)-[:DEPARTURE_ARC]->(:Arc)`: Connects an origin terminal to its outgoing scheduled transit leg.
- `(:Arc)-[:ARRIVAL_ARC]->(:Terminal)`: Connects a transit leg to its destination terminal.
- `(:Service)-[:HAS_ARC]->(:Arc)`: Groups scheduled transit segments under their parent service carrier.
- `(:Shipment)-[:ORIGINATES_AT]->(:Terminal)`: Indicates where cargo begins.
- `(:Shipment)-[:DESTINED_FOR]->(:Terminal)`: Indicates the final cargo destination.
- `(:Shipment)-[:ASSIGNED_TO]->(:Arc)`: **(Dynamic)** Created at run time to record which scheduled legs were selected for the shipment.

---

## 4. Multi-Agent Personas & Tasks

To resolve transportation delays without writing rigid hardcoded algorithms, the system models the problem as a **Logistics Control Tower** using AI agents:

### 1. Shipment Agent (`agents.py`)
- **Persona**: A dedicated advocate representing a single cargo shipment. 
- **Goal**: Find the lowest-cost, feasible route from its origin to its destination.
- **Constraints**: Prefer environmentally sustainable modes (barge and rail); resort to truck fleets only if the cargo release delay puts delivery deadlines at risk.
- **Tools**:
  - *Pathfinding Tool*: Asks Neo4j for feasible path paths that fit the time window (accounting for transshipment buffer times).
  - *Service Capacity Tool*: Inquires about current available space (TEU) on scheduled legs.
  - *Cost Calculator Tool*: Evaluates total route pricing based on shipment volume.
- **Task (`tasks.py` -> `negotiate_route`)**:
  Call pathfinding tools, query capacity on candidate arcs, compute pricing, and output the recommended route proposals.

### 2. Logistics Coordinator (`agents.py`)
- **Persona**: The network supervisor overseeing the entire network (Port of Rotterdam).
- **Goal**: Review all shipment proposals, resolve capacity conflicts, and optimize global KPIs (modal split and total network cost).
- **Tools**:
  - *Neo4j Search Tool*: Performs raw Cypher queries to audit database state.
  - *Pathfinding Tool*: Re-evaluates routes if a cargo assignment must be shifted.
- **Task (`tasks.py` -> `finalize_replanning`)**:
  Examine all individual Shipment Agent proposals, identify over-allocated legs, resolve booking overlaps, write final assignments back to Neo4j, and report the network KPIs.

---

## 5. Step-by-Step System Workflow

The entire replanning pipeline executes sequentially as follows:

```
[User dropdown change]
       │
       ▼
1. /api/select_dataset
   - Clear database (Neo4j / AuraDB)
   - Parse selected Excel sheet (e.g. 8nodes.xlsx)
   - Auto-correct data anomalies (e.g. missing terminal nodes)
   - Bulk-import Terminals, Services, Arcs, and Shipments into database
   - Update Cytoscape Graph in Frontend
       │
[User click "Run Replanning"]
       │
       ▼
2. /api/run
   - Inject disturbance in-memory (e.g., set cargo release times to 9.0h)
   - Initialize LangGraph state machine
       │
       ▼
3. load_network node
   - Synchronize current network configuration to database
       │
       ▼
4. detect_disturbances node
   - Compare shipment release delays against baseline scheduled departures
   - Flag "affected shipments" and cap them to save API tokens
       │
       ▼
5. run_negotiation node
   - For each affected shipment, spin up a dedicated CrewAI Shipment Agent
   - Agents autonomously run pathfinding, capacity, and cost tools
   - Output routing recommendations
       │
       ▼
6. finalize node
   - Spawn a Logistics Coordinator Agent
   - The coordinator audits capacities, resolves double-bookings, and writes
     the final ASSIGNED_TO edges back to Neo4j / AuraDB
   - Generate structured report (modal split, cost, path breakdowns)
       │
       ▼
7. Update Dashboard
   - Reload graph from Neo4j (renders chosen routes in purple on Cytoscape canvas)
   - Display final report to user
```

---

## 6. Codebase File Directory Guide

- **`server.py`**: The entry point for the FastAPI server. Defines routes for database loading, fetching Cytoscape JSON structures, and invoking the LangGraph state machine.
- **`workflow.py`**: Compiles the LangGraph `StateGraph`. Defines the deterministic nodes (`load_network`, `detect_disturbances`, `run_negotiation`, `finalize`) and passes state payloads between them.
- **`agents.py`**: Configures the CrewAI personas, setting system instructions, backstory constraints, and binding the shared tool instances.
- **`tasks.py`**: Defines token-efficient task prompts for the CrewAI agent runs.
- **`tools.py`**: Houses the custom python tools called by the agents, translating agent instructions into Cypher graph queries.
- **`neo4j_manager.py`**: Exposes query execution APIs, bulk-delete actions, batched UNWIND queries, pathfinding algorithms, and the in-memory fallback dictionary database.
- **`synchromodal_dataset_loader.py`**: Parses Excel layouts. Crucially includes dynamic terminal addition to prevent database-to-UI relationship crashes when spreadsheets contain data anomalies.
- **`frontend/src/app/page.js`**: Home dashboard component. Initializes Cytoscape.js, dynamically scales geography positions, manages select API triggers, and filters elements to safeguard against rendering crashes.
