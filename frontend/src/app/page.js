"use client";

import React, { useState, useEffect, useRef } from "react";
import styles from "./page.module.css";

const API_BASE = "http://127.0.0.1:8000";

const DATASETS = [
  "7nodes.xlsx",
  "8nodes.xlsx",
  "9nodes.xlsx",
  "10nodes.xlsx",
  "10nodes_6S.xlsx",
  "10nodes_7S.xlsx",
  "10nodes_8S.xlsx",
  "10nodes_9S.xlsx",
  "10nodes_10S.xlsx",
  "10nodes_15S.xlsx",
  "fully_connected.xlsx",
  "line_ntw.xlsx",
  "ring_ntw.xlsx",
  "star_ntw.xlsx",
  "tree_ntw.xlsx"
];

export default function Home() {
  const [selectedDataset, setSelectedDataset] = useState("7nodes.xlsx");
  const [status, setStatus] = useState("idle"); // idle, running, completed, error
  const [currentStep, setCurrentStep] = useState(0); // 0: idle, 1: load, 2: detect, 3: negotiate, 4: finalize
  const [report, setReport] = useState("");
  const [affectedCount, setAffectedCount] = useState(0);
  const [optStatus, setOptStatus] = useState("N/A");
  const [errorMsg, setErrorMsg] = useState("");
  
  const cyRef = useRef(null);
  const cyInstanceRef = useRef(null);

  // Initialize Cytoscape and fetch initial graph
  useEffect(() => {
    let active = true;

    async function initGraph() {
      if (typeof window === "undefined" || !cyRef.current) return;

      const cytoscapeModule = await import("cytoscape");
      const cytoscape = cytoscapeModule.default;

      if (!active) return;

      // Clean up previous instance
      if (cyInstanceRef.current) {
        cyInstanceRef.current.destroy();
      }

      cyInstanceRef.current = cytoscape({
        container: cyRef.current,
        style: [
          {
            selector: "node",
            style: {
              "background-color": "#475569",
              "label": "data(label)",
              "color": "#f8fafc",
              "text-valign": "bottom",
              "text-halign": "center",
              "text-margin-y": "8px",
              "font-family": "Outfit, sans-serif",
              "font-size": "10px",
              "font-weight": "bold",
              "width": "30px",
              "height": "30px",
              "overlay-padding": "6px",
              "z-index": "10"
            }
          },
          {
            selector: 'node[type="Terminal"]',
            style: { 
              "background-color": "#10b981", 
              "shape": "round-rectangle",
              "width": "45px",
              "height": "30px"
            }
          },
          {
            selector: 'node[type="Service"]',
            style: { 
              "background-color": "#f59e0b", 
              "shape": "triangle",
              "width": "35px",
              "height": "35px"
            }
          },
          {
            selector: 'node[type="Shipment"]',
            style: { 
              "background-color": "#ef4444", 
              "shape": "diamond",
              "width": "32px",
              "height": "32px"
            }
          },
          {
            selector: 'node[type="Arc"]',
            style: { 
              "background-color": "#06b6d4", 
              "shape": "hexagon",
              "width": "32px",
              "height": "32px"
            }
          },
          {
            selector: "edge",
            style: {
              "width": 1.5,
              "line-color": "#475569",
              "target-arrow-color": "#475569",
              "target-arrow-shape": "triangle",
              "arrow-scale": 1.0,
              "curve-style": "bezier",
              "label": "data(label)",
              "font-family": "Outfit, sans-serif",
              "font-size": "8px",
              "color": "#94a3b8",
              "text-rotation": "autorotate",
              "text-background-opacity": 0.85,
              "text-background-color": "#080c14",
              "text-background-padding": "2px",
              "text-background-shape": "roundrectangle",
              "text-border-color": "#334155",
              "text-border-width": 1
            }
          },
          {
            selector: 'edge[type="ASSIGNED_TO"]',
            style: {
              "width": 4,
              "line-color": "#d946ef",
              "target-arrow-color": "#d946ef",
              "target-arrow-shape": "chevron",
              "arrow-scale": 1.5,
              "line-style": "solid",
              "color": "#ffffff",
              "font-size": "10px",
              "font-weight": "bold",
              "text-background-color": "#d946ef",
              "text-background-opacity": 0.95,
              "text-background-padding": "4px",
              "z-index": "9999"
            }
          },
          {
            selector: 'edge[type="DEPARTURE_ARC"]',
            style: {
              "width": 1.5,
              "line-color": "#334155",
              "target-arrow-color": "#334155",
              "line-style": "solid"
            }
          },
          {
            selector: 'edge[type="ARRIVAL_ARC"]',
            style: {
              "width": 1.5,
              "line-color": "#334155",
              "target-arrow-color": "#334155",
              "line-style": "solid"
            }
          },
          {
            selector: 'edge[type="HAS_ARC"]',
            style: {
              "width": 1,
              "line-color": "#1e293b",
              "line-style": "dotted",
              "target-arrow-shape": "none"
            }
          },
          {
            selector: 'edge[type="ORIGINATES_AT"]',
            style: {
              "width": 1.2,
              "line-color": "#475569",
              "line-style": "dashed",
              "target-arrow-color": "#475569"
            }
          },
          {
            selector: 'edge[type="DESTINED_FOR"]',
            style: {
              "width": 1.2,
              "line-color": "#475569",
              "line-style": "dashed",
              "target-arrow-color": "#475569"
            }
          }
        ],
        layout: { name: "preset" }
      });

      // Fetch initial graph structure
      fetchGraph();
    }

    initGraph();

    // Resize handler
    const handleResize = () => {
      if (cyInstanceRef.current) {
        runCustomLayout(cyInstanceRef.current);
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      active = false;
      window.removeEventListener("resize", handleResize);
      if (cyInstanceRef.current) {
        cyInstanceRef.current.destroy();
      }
    };
  }, []);

  // Fetch Neo4j graph data from backend
  async function fetchGraph() {
    try {
      const response = await fetch(`${API_BASE}/api/neo4j`);
      if (!response.ok) throw new Error("Failed to fetch graph data");
      const data = await response.json();
      
      if (cyInstanceRef.current) {
        cyInstanceRef.current.elements().remove();
        
        const elements = data.elements || [];
        const nodeIds = new Set(elements.filter(el => !el.data.source && !el.data.target).map(el => el.data.id));
        const validElements = elements.filter(el => {
          if (el.data.source || el.data.target) {
            return nodeIds.has(el.data.source) && nodeIds.has(el.data.target);
          }
          return true;
        });

        cyInstanceRef.current.add(validElements);
        runCustomLayout(cyInstanceRef.current);
      }
    } catch (err) {
      console.error("Error fetching Neo4j graph:", err);
    }
  }

  // Geographic positioning layout rules
  function runCustomLayout(cyInstance) {
    if (!cyInstance) return;

    const terminals = cyInstance.nodes('[type="Terminal"]');
    if (terminals.length === 0) {
      cyInstance.layout({
        name: "cose",
        animate: true,
        padding: 40,
        nodeRepulsion: 8000
      }).run();
      return;
    }

    const width = 1000;
    const height = 500;
    
    let minLon = Infinity, maxLon = -Infinity;
    let minLat = Infinity, maxLat = -Infinity;
    
    terminals.forEach(n => {
      const lon = n.data("lon");
      const lat = n.data("lat");
      if (lon !== undefined && lat !== undefined) {
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
      }
    });

    if (minLon === Infinity) { minLon = 0; maxLon = 80; minLat = -20; maxLat = 20; }
    
    const lonRange = maxLon - minLon || 1;
    const latRange = maxLat - minLat || 1;
    
    terminals.forEach(n => {
      const lon = n.data("lon") || 0;
      const lat = n.data("lat") || 0;
      
      const x = 120 + ((lon - minLon) / lonRange) * (width - 240);
      const y = height - 100 - ((lat - minLat) / latRange) * (height - 200);
      
      n.position({ x, y });
    });

    const termPos = {};
    terminals.forEach(n => {
      termPos[n.data("id")] = n.position();
    });

    const arcs = cyInstance.nodes('[type="Arc"]');
    const arcCounts = {};
    
    arcs.forEach(n => {
      const fromId = n.data("from_terminal");
      const toId = n.data("to_terminal");
      
      if (fromId && toId && termPos[fromId] && termPos[toId]) {
        const p1 = termPos[fromId];
        const p2 = termPos[toId];
        
        let x = (p1.x + p2.x) / 2;
        let y = (p1.y + p2.y) / 2;
        
        const pairKey = [fromId, toId].sort().join("-");
        arcCounts[pairKey] = (arcCounts[pairKey] || 0) + 1;
        const count = arcCounts[pairKey];
        
        if (count > 1) {
          y += (count - 1) * 35 * (count % 2 === 0 ? 1 : -1);
        }
        
        n.position({ x, y });
      }
    });

    const services = cyInstance.nodes('[type="Service"]');
    services.forEach((n, index) => {
      const sId = n.data("id");
      const serviceArcs = cyInstance.nodes(`[type="Arc"][service_id="${sId}"]`);
      
      if (serviceArcs.length > 0) {
        const arcPos = serviceArcs[0].position();
        n.position({
          x: arcPos.x,
          y: arcPos.y - 45
        });
      } else {
        n.position({
          x: 150 + (index * 80),
          y: 60
        });
      }
    });

    const shipments = cyInstance.nodes('[type="Shipment"]');
    const shipCounts = {};
    
    shipments.forEach(n => {
      const orig = n.data("origin");
      if (orig && termPos[orig]) {
        const pos = termPos[orig];
        shipCounts[orig] = (shipCounts[orig] || 0) + 1;
        
        n.position({
          x: pos.x - 65,
          y: pos.y + (shipCounts[orig] - 1) * 35 - 30
        });
      } else {
        n.position({
          x: 100,
          y: 120
        });
      }
    });

    cyInstance.fit(40);
  }

  // Trigger replanning workflow on backend
  async function handleRunReplanning() {
    if (status === "running") return;
    
    setStatus("running");
    setErrorMsg("");
    setReport("");
    
    // Simulate steps as it executes
    setCurrentStep(1); // 1: load_network
    
    try {
      // Step 2 timer simulation
      setTimeout(() => {
        setCurrentStep(2); // 2: detect_disturbances
      }, 2000);

      // Step 3 timer simulation
      setTimeout(() => {
        setCurrentStep(3); // 3: run_negotiation
      }, 4000);

      const response = await fetch(`${API_BASE}/api/run?dataset=${selectedDataset}`, {
        method: "POST"
      });
      const data = await response.json();

      if (response.ok) {
        setCurrentStep(4); // 4: finalize
        setStatus("completed");
        setReport(data.final_report || "No report generated.");
        setAffectedCount((data.affected_shipments || []).length);
        setOptStatus("OPTIMIZED");
        
        // Refresh graph to display Assigned Paths
        setTimeout(fetchGraph, 800);
      } else {
        throw new Error(data.detail || "Workflow execution failed.");
      }
    } catch (err) {
      console.error(err);
      setStatus("error");
      setErrorMsg(err.message || "An unexpected error occurred during execution.");
      setCurrentStep(0);
    }
  }

  const handleDatasetChange = async (e) => {
    const val = e.target.value;
    setSelectedDataset(val);
    if (status === "running") return;
    
    try {
      const response = await fetch(`${API_BASE}/api/select_dataset?dataset=${val}`, {
        method: "POST"
      });
      if (response.ok) {
        setTimeout(fetchGraph, 300);
      } else {
        console.error("Failed to update active dataset in database");
      }
    } catch (err) {
      console.error("Error setting dataset:", err);
    }
  };

  const triggerResetLayout = () => {
    if (cyInstanceRef.current) {
      runCustomLayout(cyInstanceRef.current);
    }
  };

  return (
    <div className={styles.container}>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.brand}>
          <div className={styles.logoBadge}>RE</div>
          <h1>Synchromodal Control Tower</h1>
        </div>
        
        <div className={styles.controls}>
          <div className={styles.selectGroup}>
            <span className={styles.selectLabel}>Dataset</span>
            <select 
              className={styles.select}
              value={selectedDataset}
              onChange={handleDatasetChange}
              disabled={status === "running"}
            >
              {DATASETS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          </div>
          
          <button 
            className={styles.runBtn}
            onClick={handleRunReplanning}
            disabled={status === "running"}
          >
            {status === "running" ? "Optimizing..." : "Run Replanning"}
          </button>

          {status === "idle" && <div className={`${styles.badge} ${styles.badgeIdle}`}>System Idle</div>}
          {status === "running" && <div className={`${styles.badge} ${styles.badgeRunning}`}>Running Workflow</div>}
          {status === "completed" && <div className={`${styles.badge} ${styles.badgeSuccess}`}>Completed</div>}
          {status === "error" && <div className={`${styles.badge} ${styles.badgeError}`}>Error</div>}
        </div>
      </header>

      {/* Grid: Workflow (Left) & Neo4j (Right) */}
      <div className={styles.dashboardGrid}>
        
        {/* Left Side: LangGraph Steps */}
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <div className={styles.panelTitle}>
              <h2>LangGraph Orchestrator</h2>
              <span className={styles.panelSubtitle}>State Machine Node Execution</span>
            </div>
          </div>

          <div className={styles.workflowList}>
            {/* Step 1 */}
            <div className={`${styles.workflowStep} ${currentStep > 1 ? styles.stepCompleted : currentStep === 1 ? styles.stepActive : ""}`}>
              <div className={styles.stepConnector}></div>
              <div className={styles.stepIcon}>1</div>
              <div className={styles.stepContent}>
                <span className={styles.stepTitle}>Load Network</span>
                <span className={styles.stepDesc}>Parse dataset and bulk insert into Neo4j graph</span>
              </div>
            </div>

            {/* Step 2 */}
            <div className={`${styles.workflowStep} ${currentStep > 2 ? styles.stepCompleted : currentStep === 2 ? styles.stepActive : ""}`}>
              <div className={styles.stepConnector}></div>
              <div className={styles.stepIcon}>2</div>
              <div className={styles.stepContent}>
                <span className={styles.stepTitle}>Detect Disturbances</span>
                <span className={styles.stepDesc}>Identify shipment release delay windows</span>
              </div>
            </div>

            {/* Step 3 */}
            <div className={`${styles.workflowStep} ${currentStep > 3 ? styles.stepCompleted : currentStep === 3 ? styles.stepActive : ""}`}>
              <div className={styles.stepConnector}></div>
              <div className={styles.stepIcon}>3</div>
              <div className={styles.stepContent}>
                <span className={styles.stepTitle}>Run Negotiation</span>
                <span className={styles.stepDesc}>Execute CrewAI routing agentic loops via Groq API</span>
              </div>
            </div>

            {/* Step 4 */}
            <div className={`${styles.workflowStep} ${currentStep >= 4 ? styles.stepCompleted : ""}`}>
              <div className={styles.stepIcon}>4</div>
              <div className={styles.stepContent}>
                <span className={styles.stepTitle}>Finalize & Validate</span>
                <span className={styles.stepDesc}>Resolve capacity conflicts and record path links</span>
              </div>
            </div>
          </div>
        </section>

        {/* Right Side: Graph Renderer */}
        <section className={`${styles.panel} ${styles.graphPanel}`}>
          <div className={styles.panelHeader}>
            <div className={styles.panelTitle}>
              <h2>Neo4j Network Graph</h2>
              <span className={styles.panelSubtitle}>Physical terminals & active service routes</span>
            </div>
            <div className={styles.graphOverlay}>
              <button className={styles.iconBtn} onClick={fetchGraph} title="Reload Graph">🔄</button>
              <button className={styles.iconBtn} onClick={triggerResetLayout} title="Auto-Fit Layout">🔍</button>
            </div>
          </div>

          <div className={styles.graphContainer}>
            <div ref={cyRef} className={styles.cyCanvas}></div>

            {/* Legend Overlay */}
            <div className={styles.graphKey}>
              <div className={styles.keyItem}>
                <span className={`${styles.keyColor} ${styles.terminalColor}`}></span>
                <span>Terminal (Hub / Port)</span>
              </div>
              <div className={styles.keyItem}>
                <span className={`${styles.keyColor} ${styles.serviceColor}`}></span>
                <span>Service (Barge / Rail)</span>
              </div>
              <div className={styles.keyItem}>
                <span className={`${styles.keyColor} ${styles.shipmentColor}`}></span>
                <span>Shipment</span>
              </div>
              <div className={styles.keyItem}>
                <span className={`${styles.keyColor} ${styles.arcColor}`}></span>
                <span>Arc Route Connection</span>
              </div>
              <div className={styles.keyItem}>
                <span className={`${styles.keyColor} ${styles.assignedColor}`}></span>
                <span>Assigned Path (MIP/Agent)</span>
              </div>
            </div>
          </div>
        </section>

      </div>

      {/* Bottom Panel: Execution Results */}
      <section className={`${styles.panel} ${styles.resultsPanel}`}>
        <div className={styles.panelHeader}>
          <div className={styles.panelTitle}>
            <h2>Execution Results & Optimization Summary</h2>
            <span className={styles.panelSubtitle}>Consolidated coordinator reports</span>
          </div>
        </div>

        <div className={styles.resultsContent}>
          {/* Report Display Box */}
          <div className={styles.reportBox}>
            {status === "idle" && (
              <p className={styles.placeholder}>Workflow reports and logs will display here after execution...</p>
            )}
            
            {status === "running" && (
              <div className={styles.placeholder}>
                <span className={styles.runningLog}>🤖 Running agent negotiation... Executing Groq LLM cognitive loops. Please wait.</span>
              </div>
            )}
            
            {status === "completed" && (
              <pre>{report}</pre>
            )}

            {status === "error" && (
              <div className={styles.errorBox}>
                <h3>❌ Execution Failed</h3>
                <p>{errorMsg}</p>
                <div style={{ marginTop: "1rem", color: "var(--text-muted)", fontSize: "0.8rem" }}>
                  Please ensure your <code>.env</code> contains a valid <code>GROQ_API_KEY</code> and that the Neo4j instance is active.
                </div>
              </div>
            )}
          </div>

          {/* Stats Column */}
          <div className={styles.statsGrid}>
            <div className={styles.statCard}>
              <span className={styles.statLabel}>Affected Shipments</span>
              <span className={styles.statValue}>{affectedCount}</span>
            </div>

            <div className={styles.statCard}>
              <span className={styles.statLabel}>Optimization Status</span>
              <span className={styles.statValue}>{optStatus}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
