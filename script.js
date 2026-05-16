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
                        'background-color': '#3b82f6',
                        'label': 'data(label)',
                        'color': '#fff',
                        'text-valign': 'center',
                        'text-halign': 'center',
                        'font-size': '10px',
                        'width': '40px',
                        'height': '40px',
                        'overlay-padding': '6px',
                        'z-index': '10'
                    }
                },
                {
                    selector: 'node[type="Terminal"]',
                    style: { 'background-color': '#10b981', 'shape': 'round-rectangle' }
                },
                {
                    selector: 'node[type="Service"]',
                    style: { 'background-color': '#f59e0b', 'shape': 'triangle' }
                },
                {
                    selector: 'node[type="Shipment"]',
                    style: { 'background-color': '#ef4444', 'shape': 'diamond' }
                },
                {
                    selector: 'edge',
                    style: {
                        'width': 2,
                        'line-color': '#475569',
                        'target-arrow-color': '#475569',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier',
                        'label': 'data(label)',
                        'font-size': '8px',
                        'color': '#94a3b8',
                        'text-rotation': 'autorotate'
                    }
                }
            ],
            layout: {
                name: 'cose',
                animate: true
            }
        });
    }

    // Mermaid initialization
    mermaid.initialize({ 
        startOnLoad: false, 
        theme: 'dark',
        securityLevel: 'loose',
        flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' }
    });

    async function renderWorkflow() {
        const element = document.querySelector('.mermaid');
        if (element) {
            const graphDefinition = `
                graph TD
                    Start((Start)) --> Load[Load Network]
                    Load --> Detect[Detect Disturbances]
                    Detect --> Negotiate[Run Negotiation]
                    Negotiate --> Finalize[Finalize]
                    Finalize --> End((End))
                    
                    classDef default fill:#1e293b,stroke:#334155,color:#f8fafc;
                    classDef active fill:#3b82f6,stroke:#fff,color:#fff;
                    classDef completed fill:#10b981,stroke:#fff,color:#fff;
            `;
            const { svg } = await mermaid.render('workflow-svg', graphDefinition);
            element.innerHTML = svg;
        }
    }

    async function fetchNeo4jGraph() {
        try {
            console.log('Fetching Neo4j graph...');
            const response = await fetch('/api/neo4j');
            const data = await response.json();
            console.log('Graph data received:', data);
            
            if (cy) {
                cy.elements().remove();
                cy.add(data.elements);
                cy.layout({ name: 'cose', animate: true, padding: 30 }).run();
            } else {
                initGraph(data.elements);
            }
        } catch (error) {
            console.error('Error fetching Neo4j graph:', error);
        }
    }

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
                affectedCount.textContent = data.affected.length;
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
    renderWorkflow();
    fetchNeo4jGraph();
});
