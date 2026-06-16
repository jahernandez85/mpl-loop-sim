"""Network package -- Phase 7A/7B/7C/10I: topology, validation, assembly, pressure reference.

Exports:

  Identity primitives:
    NetworkId, NodeId, ConnectionId

  Topology data objects:
    NetworkNode, NetworkConnection, NetworkTopology

  Pressure-reference wiring (Phase 10I):
    PressureReferenceWiring

  Validation:
    NetworkValidationResult, validate_topology

  Assembly (Phase 7C):
    NetworkAssembly, assemble_network

MUST NOT import from solvers/.
"""

from mpl_sim.network.assembly import NetworkAssembly, assemble_network
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
    # Identity primitives
    "NetworkId",
    "NodeId",
    "ConnectionId",
    # Topology data objects
    "NetworkNode",
    "NetworkConnection",
    "NetworkTopology",
    # Pressure-reference wiring
    "PressureReferenceWiring",
    # Validation
    "NetworkValidationResult",
    "validate_topology",
    # Assembly
    "NetworkAssembly",
    "assemble_network",
]
