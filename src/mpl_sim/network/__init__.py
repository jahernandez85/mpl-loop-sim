"""Network package — Phase 7A/7B/7C/10I + Phase 13E–13H + Phase 14A–14D.

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

Phase 13H exports (configurable network solver v1):

  Solver configuration:
    NetworkSolveConfig

  Solve result:
    NetworkSolveResult

  Solver entry point:
    solve_network_residual_problem

Phase 14A exports (physical residual adapter foundation):

  Adapter context:
    PhysicalResidualContext

  Single adapter:
    PhysicalResidualAdapter

  Adapter collection:
    PhysicalResidualAdapterSet

  Builder function:
    build_network_residual_evaluators

Phase 14B exports (component binding and state-vector mapping foundation):

  Binding declaration:
    ComponentBinding

  Binding collection:
    ComponentBindingSet

  State/unknown name mapping:
    ComponentStateMap

  Binding context:
    NetworkBindingContext

  Builder function:
    build_binding_context

Phase 14C exports (minimal component contribution adapter foundation):

  Contribution context:
    ComponentContributionContext

  Contribution result:
    ComponentContribution

  Single contribution adapter:
    ComponentContributionAdapter

  Contribution adapter collection:
    ComponentContributionAdapterSet

  Builder function:
    build_physical_adapters_from_contributions

Phase 14D exports (component contribution contract adapter prep):

  Contribution record value object:
    ContributionRecord

  Contribution record collection:
    ContributionRecordSet

  Contribution-to-residual name mapping:
    ContributionResidualMap

  Conversion function:
    map_contribution_records_to_component_contribution

MUST NOT import from solvers/.
"""

from mpl_sim.network.assembly import NetworkAssembly, assemble_network
from mpl_sim.network.component_binding import (
    ComponentBinding,
    ComponentBindingSet,
    ComponentStateMap,
    NetworkBindingContext,
    build_binding_context,
)
from mpl_sim.network.contribution_adapters import (
    ComponentContribution,
    ComponentContributionAdapter,
    ComponentContributionAdapterSet,
    ComponentContributionContext,
    build_physical_adapters_from_contributions,
)
from mpl_sim.network.contribution_contract import (
    ContributionRecord,
    ContributionRecordSet,
    ContributionResidualMap,
    map_contribution_records_to_component_contribution,
)
from mpl_sim.network.graph import (
    ComponentInstance,
    ComponentInstanceId,
    GraphNode,
    GraphNodeId,
    NetworkGraph,
)
from mpl_sim.network.physical_adapters import (
    PhysicalResidualAdapter,
    PhysicalResidualAdapterSet,
    PhysicalResidualContext,
    build_network_residual_evaluators,
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
from mpl_sim.network.solver import (
    NetworkSolveConfig,
    NetworkSolveResult,
    solve_network_residual_problem,
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
    # Phase 13H solver configuration
    "NetworkSolveConfig",
    # Phase 13H solve result
    "NetworkSolveResult",
    # Phase 13H solver entry point
    "solve_network_residual_problem",
    # Phase 14A adapter context
    "PhysicalResidualContext",
    # Phase 14A single adapter
    "PhysicalResidualAdapter",
    # Phase 14A adapter collection
    "PhysicalResidualAdapterSet",
    # Phase 14A builder function
    "build_network_residual_evaluators",
    # Phase 14B binding declaration
    "ComponentBinding",
    # Phase 14B binding collection
    "ComponentBindingSet",
    # Phase 14B state/unknown name mapping
    "ComponentStateMap",
    # Phase 14B binding context
    "NetworkBindingContext",
    # Phase 14B builder function
    "build_binding_context",
    # Phase 14C contribution context
    "ComponentContributionContext",
    # Phase 14C contribution result
    "ComponentContribution",
    # Phase 14C single contribution adapter
    "ComponentContributionAdapter",
    # Phase 14C contribution adapter collection
    "ComponentContributionAdapterSet",
    # Phase 14C builder function
    "build_physical_adapters_from_contributions",
    # Phase 14D contribution record value object
    "ContributionRecord",
    # Phase 14D contribution record collection
    "ContributionRecordSet",
    # Phase 14D contribution-to-residual name mapping
    "ContributionResidualMap",
    # Phase 14D conversion function
    "map_contribution_records_to_component_contribution",
]
