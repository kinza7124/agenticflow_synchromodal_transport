# Neo4j Setup Guide

## Option A — Neo4j Desktop (recommended for local dev)

1. **Download** Neo4j Desktop from https://neo4j.com/download/
2. **Install** and open it.
3. Click **"New Project"** → **"Add"** → **"Local DBMS"**.
4. Set a name (e.g., `synchromodal`) and a password (remember it).
5. Click **"Start"** to launch the database.
6. The default connection is `bolt://localhost:7687`, user `neo4j`.

---

## Option B — Docker (no installer needed)

```bash
docker run \
  --name neo4j-synchro \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/yourpassword \
  -e NEO4J_PLUGINS='["apoc"]' \
  neo4j:5
```

Open the browser UI at http://localhost:7474 and log in with `neo4j / yourpassword`.

---

## Option C — Neo4j AuraDB Free (easiest, no install, runs in browser) ⭐ Recommended

No Docker, no installer — everything runs in your browser.

1. Go to https://neo4j.com/cloud/aura-free/ and create a free account.
2. Click **"New Instance"** → choose **AuraDB Free**, pick a region, give it a name.
3. It spins up in ~2 minutes.
4. **Important:** when the instance is created a dialog shows your auto-generated password — **copy it immediately**, it will not be shown again.
5. Your connection URI will look like: `neo4j+s://xxxxxxxx.databases.neo4j.io`
6. From the Aura console click **"Open"** to launch the Neo4j Browser (Cypher query UI) directly in your browser tab.

### Free tier limits (more than enough for this project)

| Limit | Value |
|---|---|
| Nodes | 200,000 |
| Relationships | 400,000 |
| Storage | 512 MB |
| Instances | 1 free |

### Important — URI format

AuraDB uses `neo4j+s://` (TLS encrypted), **not** `bolt://`. The Python driver handles this automatically. Just make sure your `.env` uses the full URI copied from the Aura console:

```env
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_generated_password
```

---

## Configure the project

Edit (or create) the `.env` file in the project root:

```env
# Neo4j connection
NEO4J_URI=bolt://localhost:7687        # or neo4j+s://xxxx.databases.neo4j.io for Aura
NEO4J_USER=neo4j
NEO4J_PASSWORD=yourpassword

# Google Gemini API key (get one at https://aistudio.google.com/app/apikey)
GOOGLE_API_KEY=your_gemini_api_key

# Optional: override the LLM model (default: gemini/gemini-2.0-flash)
# CREWAI_LLM_MODEL=gemini/gemini-1.5-flash

# Optional: max shipments to replan per run (default: 3, to stay within free quota)
# MAX_SHIPMENTS_PER_RUN=3
```

---

## Install APOC plugin (optional but recommended)

APOC enables the fast batch-delete used in `clear_database()`.

**Neo4j Desktop:** Open your DBMS → Plugins tab → Install APOC.

**Docker:** Already included via `NEO4J_PLUGINS='["apoc"]'` above.

**AuraDB:** APOC is pre-installed.

If APOC is not available, the code automatically falls back to a simple
`MATCH (n) DETACH DELETE n` — it works but is slower on large graphs.

---

## Verify the connection

```bash
python - <<'EOF'
from neo4j_manager import Neo4jManager
m = Neo4jManager()
print("Connected:", m.driver is not None)
m.close()
EOF
```

You should see: `Connected: True`

---

## Run the server

```bash
pip install -r requirements_agentic.txt
python server.py
```

Open http://localhost:8000 in your browser.

---

## Useful Cypher queries (Neo4j Browser)

```cypher
// See all nodes
MATCH (n) RETURN n LIMIT 50

// See the transportation network after a workflow run
MATCH (t:Terminal) RETURN t

// Check shipment assignments
MATCH (s:Shipment)-[:ASSIGNED_TO]->(a:Arc) RETURN s.id, a.id, s.status

// Check arc capacity usage
MATCH (a:Arc)<-[:ASSIGNED_TO]-(s:Shipment)
RETURN a.id, sum(s.volume) AS used_volume
ORDER BY used_volume DESC
```
