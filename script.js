document.addEventListener('DOMContentLoaded', () => {
    const runBtn = document.getElementById('runBtn');
    const refreshGraphBtn = document.getElementById('refreshGraphBtn');
    const statusBadge = document.getElementById('statusBadge');
    const reportContainer = document.getElementById('reportContainer');
    const affectedCount = document.getElementById('affectedCount');
    const optStatus = document.getElementById('optStatus');

    let cy = null;

    // Initialize Cytoscape
    function initGraph(elements) {
        cy = cytoscape({
            container: document.getElementById('cy'),
            elements: elements,
            style: [
                {
                    selector: 'node',
                    style: {
                        'background-color': '#475569',
                        'label': 'data(label)',
                        'color': '#f8fafc',
                        'text-valign': 'bottom',
                        'text-halign': 'center',
                        'text-margin-y': '8px',
                        'font-size': '10px',
                        'font-weight': 'bold',
                        'width': '30px',
                        'height': '30px',
                        'overlay-padding': '6px',
                        'z-index': '10'
                    }
                },
                {
                    selector: 'node[type="Terminal"]',
                    style: { 
                        'background-color': '#10b981', 
                        'shape': 'round-rectangle',
                        'width': '45px',
                        'height': '30px'
                    }
                },
                {
                    selector: 'node[type="Service"]',
                    style: { 
                        'background-color': '#f59e0b', 
                        'shape': 'triangle',
                        'width': '35px',
                        'height': '35px'
                    }
                },
                {
                    selector: 'node[type="Shipment"]',
                    style: { 
                        'background-color': '#ef4444', 
                        'shape': 'diamond',
                        'width': '32px',
                        'height': '32px'
                    }
                },
                {
                    selector: 'node[type="Arc"]',
                    style: { 
                        'background-color': '#06b6d4', 
                        'shape': 'hexagon',
                        'width': '32px',
                        'height': '32px'
                    }
                },
                {
                    selector: 'edge',
                    style: {
                        'width': 1.5,
                        'line-color': '#475569',
                        'target-arrow-color': '#475569',
                        'target-arrow-shape': 'triangle',
                        'arrow-scale': 1.0,
                        'curve-style': 'bezier',
                        'label': 'data(label)',
                        'font-size': '8px',
                        'color': '#94a3b8',
                        'text-rotation': 'autorotate',
                        'text-background-opacity': 0.8,
                        'text-background-color': '#0f172a',
                        'text-background-padding': '2px',
                        'text-background-shape': 'roundrectangle',
                        'text-border-color': '#334155',
                        'text-border-width': 1
                    }
                },
                {
                    selector: 'edge[type="ASSIGNED_TO"]',
                    style: {
                        'width': 4,
                        'line-color': '#d946ef',
                        'target-arrow-color': '#d946ef',
                        'target-arrow-shape': 'chevron',
                        'arrow-scale': 1.5,
                        'line-style': 'solid',
                        'color': '#ffffff',
                        'font-size': '10px',
                        'font-weight': 'bold',
                        'text-background-color': '#d946ef',
                        'text-background-opacity': 0.95,
                        'text-background-padding': '4px',
                        'z-index': '9999'
                    }
                },
                {
                    selector: 'edge[type="DEPARTURE_ARC"]',
                    style: {
                        'width': 1.5,
                        'line-color': '#334155',
                        'target-arrow-color': '#334155',
                        'line-style': 'solid'
                    }
                },
                {
                    selector: 'edge[type="ARRIVAL_ARC"]',
                    style: {
                        'width': 1.5,
                        'line-color': '#334155',
                        'target-arrow-color': '#334155',
                        'line-style': 'solid'
                    }
                },
                {
                    selector: 'edge[type="HAS_ARC"]',
                    style: {
                        'width': 1,
                        'line-color': '#1e293b',
                        'line-style': 'dotted',
                        'target-arrow-shape': 'none'
                    }
                },
                {
                    selector: 'edge[type="ORIGINATES_AT"]',
                    style: {
                        'width': 1.2,
                        'line-color': '#475569',
                        'line-style': 'dashed',
                        'target-arrow-color': '#475569'
                    }
                },
                {
                    selector: 'edge[type="DESTINED_FOR"]',
                    style: {
                        'width': 1.2,
                        'line-color': '#475569',
                        'line-style': 'dashed',
                        'target-arrow-color': '#475569'
                    }
                }
            ],
            layout: {
                name: 'preset'
            }
        });
        
        runCustomLayout(cy);
    }

    function runCustomLayout(cyInstance) {
        if (!cyInstance) return;

        const terminals = cyInstance.nodes('[type="Terminal"]');
        if (terminals.length === 0) {
            // Fallback to cose layout if no terminals exist
            cyInstance.layout({
                name: 'cose',
                animate: true,
                padding: 40,
                nodeRepulsion: 8000
            }).run();
            return;
        }

        // Virtual coordinates space for absolute positioning stability
        const width = 1000;
        const height = 500;
        
        // Find coordinate bounds to scale dynamically
        let minLon = Infinity, maxLon = -Infinity;
        let minLat = Infinity, maxLat = -Infinity;
        
        terminals.forEach(n => {
            const lon = n.data('lon');
            const lat = n.data('lat');
            if (lon !== undefined && lat !== undefined) {
                if (lon < minLon) minLon = lon;
                if (lon > maxLon) maxLon = lon;
                if (lat < minLat) minLat = lat;
                if (lat > maxLat) maxLat = lat;
            }
        });

        // Default bounds if not found
        if (minLon === Infinity) { minLon = 0; maxLon = 80; minLat = -20; maxLat = 20; }
        
        const lonRange = maxLon - minLon || 1;
        const latRange = maxLat - minLat || 1;
        
        // Position terminals geographically in virtual space
        terminals.forEach(n => {
            const lon = n.data('lon') || 0;
            const lat = n.data('lat') || 0;
            
            // Map to virtual canvas with padding
            const x = 120 + ((lon - minLon) / lonRange) * (width - 240);
            // Invert Y so higher latitude is higher on screen
            const y = height - 100 - ((lat - minLat) / latRange) * (height - 200);
            
            n.position({ x, y });
        });

        // Store positions of terminals for lookup
        const termPos = {};
        terminals.forEach(n => {
            termPos[n.data('id')] = n.position();
        });

        // Position Arcs at the midpoint of their terminals
        const arcs = cyInstance.nodes('[type="Arc"]');
        const arcCounts = {};
        
        arcs.forEach(n => {
            const fromId = n.data('from_terminal');
            const toId = n.data('to_terminal');
            
            if (fromId && toId && termPos[fromId] && termPos[toId]) {
                const p1 = termPos[fromId];
                const p2 = termPos[toId];
                
                let x = (p1.x + p2.x) / 2;
                let y = (p1.y + p2.y) / 2;
                
                // Offset multiple arcs between the same terminals
                const pairKey = [fromId, toId].sort().join('-');
                arcCounts[pairKey] = (arcCounts[pairKey] || 0) + 1;
                const count = arcCounts[pairKey];
                
                if (count > 1) {
                    y += (count - 1) * 35 * (count % 2 === 0 ? 1 : -1);
                }
                
                n.position({ x, y });
            }
        });

        // Position Services slightly offset above their first Arc
        const services = cyInstance.nodes('[type="Service"]');
        services.forEach((n, index) => {
            const sId = n.data('id');
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

        // Position Shipments elegantly near their origins
        const shipments = cyInstance.nodes('[type="Shipment"]');
        const shipCounts = {};
        
        shipments.forEach(n => {
            const orig = n.data('origin');
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

        // Fit and center with generous padding
        cyInstance.fit(40);
    }

    // Mermaid initialization — auto-render enabled for native performance
    mermaid.initialize({ 
        startOnLoad: true, 
        theme: 'dark',
        securityLevel: 'loose',
        flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' }
    });

    async function fetchNeo4jGraph() {
        try {
            console.log('Fetching Neo4j graph...');
            const response = await fetch('/api/neo4j');
            const data = await response.json();
            console.log('Graph data received:', data);
            
            if (cy) {
                cy.elements().remove();
                cy.add(data.elements);
                runCustomLayout(cy);
            } else {
                initGraph(data.elements);
            }
        } catch (error) {
            console.error('Error fetching Neo4j graph:', error);
        }
    }

    // Add a window resize handler to keep positions responsive
    window.addEventListener('resize', () => {
        if (cy) {
            runCustomLayout(cy);
        }
    });

    async function runWorkflow() {
        if (runBtn.disabled) return;
        
        runBtn.disabled = true;
        statusBadge.textContent = 'Running Workflow...';
        statusBadge.className = 'badge running';
        reportContainer.innerHTML = '<p class="running-log">Executing agentic replanning... please wait.</p>';

        try {
            const response = await fetch('/api/run', { method: 'POST' });
            const data = await response.json();

            if (response.ok) {
                statusBadge.textContent = 'Workflow Completed';
                statusBadge.className = 'badge success';
                reportContainer.innerHTML = `<pre>${data.final_report}</pre>`;
                affectedCount.textContent = (data.affected_shipments || []).length;
                optStatus.textContent = 'OPTIMIZED';
                
                // Refresh graph to show updates
                setTimeout(fetchNeo4jGraph, 500);
            } else {
                throw new Error(data.detail || 'Workflow failed');
            }
        } catch (error) {
            statusBadge.textContent = 'Workflow Failed';
            statusBadge.className = 'badge idle';
            reportContainer.innerHTML = `
                <div class="error-container" style="color: #ef4444; padding: 1rem;">
                    <h3 style="margin-bottom: 0.5rem;">❌ Workflow Execution Error</h3>
                    <p>${error.message}</p>
                    <div class="error-hint" style="margin-top: 1rem; padding: 1rem; background: rgba(239, 68, 68, 0.1); border-radius: 8px; border: 1px solid rgba(239, 68, 68, 0.2); font-size: 0.85rem; color: #f87171;">
                         <strong>Possible Issue:</strong> You might have exceeded your Gemini API quota (Free tier limit is 20 requests/day). 
                        Try again in a few minutes or check your <code>.env</code> file for a valid <code>GOOGLE_API_KEY</code>.
                    </div>
                </div>
            `;
            console.error('Error running workflow:', error);
        } finally {
            runBtn.disabled = false;
        }
    }

    runBtn.addEventListener('click', runWorkflow);
    refreshGraphBtn.addEventListener('click', fetchNeo4jGraph);

    // Initial load
    fetchNeo4jGraph();
});
