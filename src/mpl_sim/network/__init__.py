"""Network package — Phase 7A/7B/7C: topology, validation, and assembly.

Exports:

  Identity primitives:
    NetworkId, NodeId, ConnectionId

  Topology data objects:
    NetworkNode, NetworkConnection, NetworkTopology

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
    # Validation
    "NetworkValidationResult",
    "validate_topology",
    # Assembly
    "NetworkAssembly",
    "assemble_network",
]
