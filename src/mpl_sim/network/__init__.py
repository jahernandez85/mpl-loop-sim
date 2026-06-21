"""Network package — Phase 7A/7B/7C/10I + Phase 13E + Phase 13F + Phase 13G.

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

Phase 13F exports (network residual assembly foundation):

  Declaration types:
    NetworkUnknownDeclaration, NetworkResidualDeclaration

  Collection types:
    NetworkUnknownSet, NetworkResidualSet

  Assembly result:
    NetworkResidualAssembly

  Factory function:
    assemble_network_residuals

Phase 13G exports (network residual evaluation foundation):

  Unknown value map:
    NetworkUnknownValues

  Residual evaluator:
    NetworkResidualEvaluator

  Evaluation result:
    NetworkResidualEvaluationResult

  Evaluation function:
    evaluate_network_residuals

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
from mpl_sim.network.residual_assembly import (
    NetworkResidualAssembly,
    NetworkResidualDeclaration,
    NetworkResidualSet,
    NetworkUnknownDeclaration,
    NetworkUnknownSet,
    assemble_network_residuals,
)
from mpl_sim.network.residual_evaluation import (
    NetworkResidualEvaluationResult,
    NetworkResidualEvaluator,
    NetworkUnknownValues,
    evaluate_network_residuals,
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
    # Phase 13F residual assembly declaration types
    "NetworkUnknownDeclaration",
    "NetworkResidualDeclaration",
    # Phase 13F residual assembly collection types
    "NetworkUnknownSet",
    "NetworkResidualSet",
    # Phase 13F assembly result
    "NetworkResidualAssembly",
    # Phase 13F factory function
    "assemble_network_residuals",
    # Phase 13G unknown value map
    "NetworkUnknownValues",
    # Phase 13G residual evaluator
    "NetworkResidualEvaluator",
    # Phase 13G evaluation result
    "NetworkResidualEvaluationResult",
    # Phase 13G evaluation function
    "evaluate_network_residuals",
]
