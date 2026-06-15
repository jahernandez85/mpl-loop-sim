"""Network package — Phase 7A/7B: topology primitives and validation.

Exports:

  Identity primitives:
    NetworkId, NodeId, ConnectionId

  Topology data objects:
    NetworkNode, NetworkConnection, NetworkTopology

  Validation:
    NetworkValidationResult, validate_topology

MUST NOT import from solvers/.
"""

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
]
