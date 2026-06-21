"""Network package — Phase 7A/7B/7C/10I + Phase 13E.

Phase 7A/7B/7C/10I exports (component-coupled topology):

  Identity primitives:
    NetworkId, NodeId, ConnectionId

  Topology data objects:
    NetworkNode, NetworkConnection, NetworkTopology

  Pressure-reference wiring:
    PressureReferenceWiring

  Validation:
    NetworkValidationResult, validate_topology

  Assembly:
    NetworkAssembly, assemble_network

Phase 13E exports (physics-free graph foundation):

  Graph identity primitives:
    GraphNodeId, ComponentInstanceId

  Graph element types:
    GraphNode, ComponentInstance

  Graph container:
    NetworkGraph

MUST NOT import from solvers/.
"""

from mpl_sim.network.assembly import NetworkAssembly, assemble_network
from mpl_sim.network.graph import (
    ComponentInstance,
    ComponentInstanceId,
    GraphNode,
    GraphNodeId,
    NetworkGraph,
)
from mpl_sim.network.topology import (
    ConnectionId,
    NetworkConnection,
    NetworkId,
    NetworkNode,
    NetworkTopology,
    NodeId,
    PressureReferenceWiring,
)
from mpl_sim.network.validation import (
    NetworkValidationResult,
    validate_topology,
)

__all__ = [
    # Phase 7 identity primitives
    "NetworkId",
    "NodeId",
    "ConnectionId",
    # Phase 7 topology data objects
    "NetworkNode",
    "NetworkConnection",
    "NetworkTopology",
    # Phase 7 pressure-reference wiring
    "PressureReferenceWiring",
    # Phase 7 validation
    "NetworkValidationResult",
    "validate_topology",
    # Phase 7 assembly
    "NetworkAssembly",
    "assemble_network",
    # Phase 13E graph identity primitives
    "GraphNodeId",
    "ComponentInstanceId",
    # Phase 13E graph element types
    "GraphNode",
    "ComponentInstance",
    # Phase 13E graph container
    "NetworkGraph",
]
