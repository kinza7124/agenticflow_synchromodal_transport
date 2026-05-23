"""
Synchromodal Model
Self-contained clean dataclasses and network model container for the agentic synchromodal workflow,
completely decoupled from the MILP mathematical solver.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any
import networkx as nx
import matplotlib.pyplot as plt

@dataclass
class Terminal:
    id: str
    name: str
    type: str
    lat: float
    lon: float

@dataclass
class Service:
    id: str
    mode: str  # barge, rail, truck
    capacity: float
    fixed_cost: float
    variable_cost: float
    cancellation_cost: float
    itinerary: List[str]
    departure_time: float
    arrival_time: float
    traverse_time: float

@dataclass
class Arc:
    id: str
    from_terminal: str
    to_terminal: str
    service_id: str
    departure_time: float
    arrival_time: float
    traverse_time: float
    variable_cost: float

@dataclass
class Shipment:
    id: str
    origin: str
    destination: str
    volume: float
    release_time: float
    due_time: float
    latest_time: float
    early_penalty: float
    late_penalty: float

@dataclass
class Disturbance:
    type: str  # late_release, service_delay, volume_change
    affected_id: str  # shipment_id or service_id
    time: float
    new_volume: float = 0.0


class SynchromodalTransportationModel:
    def __init__(self, name: str = "Synchromodal Network"):
        self.name = name
        self.terminals: Dict[str, Terminal] = {}
        self.services: Dict[str, Service] = {}
        self.shipments: Dict[str, Shipment] = {}
        self.arcs: Dict[str, Arc] = {}
        self.disturbances: List[Disturbance] = []
        self.buffer_time: Dict[str, float] = {}
        
        self.transshipment_cost_per_teu = 23.89
        self.transshipment_time_hours = 1.0

    def add_terminal(self, terminal: Terminal):
        self.terminals[terminal.id] = terminal

    def add_service(self, service: Service):
        self.services[service.id] = service

    def add_shipment(self, shipment: Shipment):
        self.shipments[shipment.id] = shipment

    def add_arc(self, arc: Arc):
        self.arcs[arc.id] = arc

    def add_disturbance(self, disturbance: Disturbance):
        self.disturbances.append(disturbance)

    def clear_arcs(self):
        self.arcs.clear()


def visualize_network(model: SynchromodalTransportationModel, title: str = "Synchromodal Network"):
    """
    Draw a clean, beautiful visualization of the synchromodal network
    without any dependency on external solver engines.
    """
    G = nx.DiGraph()
    pos = {}
    node_colors = []
    
    # 1. Add terminals
    for t_id, t in model.terminals.items():
        G.add_node(t_id, label=t.name, type=t.type)
        pos[t_id] = (t.lon, t.lat)
        if t.type == 'port' or t_id == 'POR':
            node_colors.append('#10b981')  # Emerald green for port
        else:
            node_colors.append('#3b82f6')  # Blue for hubs
            
    # 2. Add edges
    edge_list = []
    for arc_id, arc in model.arcs.items():
        svc = model.services.get(arc.service_id)
        mode = svc.mode if svc else 'truck'
        G.add_edge(arc.from_terminal, arc.to_terminal, mode=mode, id=arc_id)
        edge_list.append((arc.from_terminal, arc.to_terminal, mode))

    plt.figure(figsize=(10, 8))
    
    # Draw nodes
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=800, alpha=0.9)
    
    # Draw edges with mode-specific styles
    for u, v, mode in edge_list:
        if mode == 'barge':
            edge_color = '#0284c7'  # Cyan for barge
            style = 'solid'
            width = 2.5
        elif mode == 'rail':
            edge_color = '#f59e0b'  # Amber for rail
            style = 'dashed'
            width = 2.0
        else:
            edge_color = '#64748b'  # Slate for truck
            style = 'dotted'
            width = 1.2
            
        nx.draw_networkx_edges(
            G, pos, edgelist=[(u, v)], 
            edge_color=edge_color, style=style, width=width,
            arrows=True, arrowsize=12, connectionstyle='arc3,rad=0.1'
        )
        
    # Draw labels
    nx.draw_networkx_labels(G, pos, font_size=9, font_weight='bold', font_color='#ffffff')
    
    plt.title(title, fontsize=12, fontweight='bold', pad=15)
    plt.axis('off')
    plt.tight_layout()
    plt.savefig("Synchromodal_Network_-_Agentic_Replan_network.png", dpi=300, bbox_inches='tight')
    plt.close()
