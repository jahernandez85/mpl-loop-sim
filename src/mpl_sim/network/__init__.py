"""Network package — Phase 7A/7B/7C/10I + Phase 13E–13H + Phase 14A–14G +
Block 15A.1 + Block 15A.2 + Block 15A.3 + Block 15B.1 + Block 15B.2 + Block 15B.3 +
Block 15C-A (15C.1 + 15C.2 + 15C.3).

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

Phase 14E exports (controlled toy component execution harness):

  Toy execution context:
    ToyComponentExecutionContext

  Single toy executor:
    ToyComponentExecutor

  Toy executor collection:
    ToyComponentExecutorSet

  Toy execution driver:
    execute_toy_component_contributions

  Convenience conversion wrapper:
    build_component_contribution_from_toy_execution

Phase 14G exports (production component contribution contract inspection):

  Contract status constants:
    ProductionComponentContractStatus

  Signature description value object:
    ProductionComponentContributionSignature

  Inspection result value object:
    ProductionComponentInspectionResult

  Inspection functions:
    inspect_production_component_contract
    inspect_known_production_component_contracts

Phase 14F exports (minimal component-like contribution provider adapter):

  Provider execution context:
    ComponentProviderExecutionContext

  Provider protocol:
    ComponentContributionProviderProtocol

  Single provider binding:
    ComponentContributionProviderBinding

  Provider binding collection:
    ComponentContributionProviderSet

  Provider execution driver:
    execute_component_provider_contributions

  Convenience conversion wrapper:
    build_component_contribution_from_provider_execution

Block 15A.1 exports (production component bridge boundary MVP):

  Bridge execution context:
    ProductionBridgeExecutionContext

  Bridge protocol:
    ProductionContributionBridgeProtocol

  Single bridge binding:
    ProductionComponentBridgeBinding

  Bridge binding collection:
    ProductionComponentBridgeSet

  Bridge execution driver:
    execute_production_bridge_contributions

  Convenience conversion wrapper:
    build_component_contribution_from_production_bridge_execution

Block 15A.2 exports (read-only unknown/state bridge MVP):

  Full unknown-vector view:
    ReadOnlyUnknownView

  Component-scoped unknown view:
    ComponentUnknownView

  Node-scoped unknown view:
    NodeUnknownView

  Factory function:
    build_readonly_unknown_view

Block 15A.3 exports (controlled production-like bridge path MVP):

  Production-like execution context (includes ReadOnlyUnknownView):
    ProductionLikeBridgeContext

  Production-like producer protocol:
    ProductionLikeRecordProducerProtocol

  Single production-like binding:
    ProductionLikeComponentBinding

  Production-like binding collection:
    ProductionLikeComponentSet

  Production-like execution driver:
    execute_production_like_contributions

  Convenience conversion wrapper:
    build_component_contribution_from_production_like_execution

Block 15B.1 exports (fixed single-loop scenario declaration MVP):

  Component ID container:
    FixedSingleLoopComponentIds

  Node ID container:
    FixedSingleLoopNodeIds

  Unknown name container:
    FixedSingleLoopUnknownNames

  Residual name container:
    FixedSingleLoopResidualNames

  Scenario container:
    FixedSingleLoopScenario

  Factory function:
    build_fixed_single_loop_scenario

Block 15B.2 exports (fixed single-loop physical residual assembly MVP):

  Explicit scalar parameters:
    FixedSingleLoopResidualParameters

  Frozen assembled object:
    FixedSingleLoopPhysicalResidualAssembly

  Deterministic factory:
    build_fixed_single_loop_physical_residuals

  Thin convenience wrapper:
    build_component_contribution_from_fixed_single_loop_residuals

Block 15B.3 exports (fixed single-loop evaluate/solve/report MVP):

  Frozen evaluation result:
    FixedSingleLoopEvaluationResult

  Frozen solve request:
    FixedSingleLoopSolveRequest

  Frozen solve result:
    FixedSingleLoopSolveResult

  Deterministic residual evaluator:
    evaluate_fixed_single_loop_residuals

  Thin solver wrapper:
    solve_fixed_single_loop_residuals

  Simple serializable summary builder:
    build_fixed_single_loop_report

Block 15C.1 exports (junction / manifold declaration foundation):

  Junction role enum:
    JunctionRole

  Split/merge junction declaration:
    JunctionDeclaration

  Manifold with named branch port nodes:
    ManifoldDeclaration

Block 15C.2 exports (parallel branch topology declaration):

  Branch identifier:
    TopologyBranchId

  Single branch declaration:
    ParallelBranchDeclaration

  Component ID container:
    ParallelTopologyComponentIds

  Node ID container:
    ParallelTopologyNodeIds

  Unknown name container:
    ParallelTopologyUnknownNames

  Residual name container:
    ParallelTopologyResidualNames

  Scenario container:
    ParallelTopologyScenario

  Factory function:
    build_parallel_topology_scenario

Block 15C.3 exports (valve / local pressure-loss element declaration):

  Valve declaration:
    ValveDeclaration

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
from mpl_sim.network.component_provider_adapters import (
    ComponentContributionProviderBinding,
    ComponentContributionProviderProtocol,
    ComponentContributionProviderSet,
    ComponentProviderExecutionContext,
    build_component_contribution_from_provider_execution,
    execute_component_provider_contributions,
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
from mpl_sim.network.fixed_single_loop_residuals import (
    FixedSingleLoopPhysicalResidualAssembly,
    FixedSingleLoopResidualParameters,
    build_component_contribution_from_fixed_single_loop_residuals,
    build_fixed_single_loop_physical_residuals,
)
from mpl_sim.network.fixed_single_loop_runner import (
    FixedSingleLoopEvaluationResult,
    FixedSingleLoopSolveRequest,
    FixedSingleLoopSolveResult,
    build_fixed_single_loop_report,
    evaluate_fixed_single_loop_residuals,
    solve_fixed_single_loop_residuals,
)
from mpl_sim.network.fixed_single_loop_scenario import (
    FixedSingleLoopComponentIds,
    FixedSingleLoopNodeIds,
    FixedSingleLoopResidualNames,
    FixedSingleLoopScenario,
    FixedSingleLoopUnknownNames,
    build_fixed_single_loop_scenario,
)
from mpl_sim.network.graph import (
    ComponentInstance,
    ComponentInstanceId,
    GraphNode,
    GraphNodeId,
    NetworkGraph,
)
from mpl_sim.network.parallel_topology_scenario import (
    ParallelBranchDeclaration,
    ParallelTopologyComponentIds,
    ParallelTopologyNodeIds,
    ParallelTopologyResidualNames,
    ParallelTopologyScenario,
    ParallelTopologyUnknownNames,
    TopologyBranchId,
    build_parallel_topology_scenario,
)
from mpl_sim.network.physical_adapters import (
    PhysicalResidualAdapter,
    PhysicalResidualAdapterSet,
    PhysicalResidualContext,
    build_network_residual_evaluators,
)
from mpl_sim.network.production_component_bridge import (
    ProductionBridgeExecutionContext,
    ProductionComponentBridgeBinding,
    ProductionComponentBridgeSet,
    ProductionContributionBridgeProtocol,
    build_component_contribution_from_production_bridge_execution,
    execute_production_bridge_contributions,
)
from mpl_sim.network.production_component_inspection import (
    ProductionComponentContractStatus,
    ProductionComponentContributionSignature,
    ProductionComponentInspectionResult,
    inspect_known_production_component_contracts,
    inspect_production_component_contract,
)
from mpl_sim.network.production_like_bridge import (
    ProductionLikeBridgeContext,
    ProductionLikeComponentBinding,
    ProductionLikeComponentSet,
    ProductionLikeRecordProducerProtocol,
    build_component_contribution_from_production_like_execution,
    execute_production_like_contributions,
)
from mpl_sim.network.readonly_state_bridge import (
    ComponentUnknownView,
    NodeUnknownView,
    ReadOnlyUnknownView,
    build_readonly_unknown_view,
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
from mpl_sim.network.topology_declarations import (
    JunctionDeclaration,
    JunctionRole,
    ManifoldDeclaration,
    ValveDeclaration,
)
from mpl_sim.network.toy_component_execution import (
    ToyComponentExecutionContext,
    ToyComponentExecutor,
    ToyComponentExecutorSet,
    build_component_contribution_from_toy_execution,
    execute_toy_component_contributions,
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
    # Phase 14E toy execution context
    "ToyComponentExecutionContext",
    # Phase 14E single toy executor
    "ToyComponentExecutor",
    # Phase 14E toy executor collection
    "ToyComponentExecutorSet",
    # Phase 14E toy execution driver
    "execute_toy_component_contributions",
    # Phase 14E convenience conversion wrapper
    "build_component_contribution_from_toy_execution",
    # Phase 14G contract status constants
    "ProductionComponentContractStatus",
    # Phase 14G signature description value object
    "ProductionComponentContributionSignature",
    # Phase 14G inspection result value object
    "ProductionComponentInspectionResult",
    # Phase 14G inspection functions
    "inspect_production_component_contract",
    "inspect_known_production_component_contracts",
    # Phase 14F provider execution context
    "ComponentProviderExecutionContext",
    # Phase 14F provider protocol
    "ComponentContributionProviderProtocol",
    # Phase 14F single provider binding
    "ComponentContributionProviderBinding",
    # Phase 14F provider binding collection
    "ComponentContributionProviderSet",
    # Phase 14F provider execution driver
    "execute_component_provider_contributions",
    # Phase 14F convenience conversion wrapper
    "build_component_contribution_from_provider_execution",
    # Block 15A.1 bridge execution context
    "ProductionBridgeExecutionContext",
    # Block 15A.1 bridge protocol
    "ProductionContributionBridgeProtocol",
    # Block 15A.1 single bridge binding
    "ProductionComponentBridgeBinding",
    # Block 15A.1 bridge binding collection
    "ProductionComponentBridgeSet",
    # Block 15A.1 bridge execution driver
    "execute_production_bridge_contributions",
    # Block 15A.1 convenience conversion wrapper
    "build_component_contribution_from_production_bridge_execution",
    # Block 15A.2 full unknown-vector view
    "ReadOnlyUnknownView",
    # Block 15A.2 component-scoped unknown view
    "ComponentUnknownView",
    # Block 15A.2 node-scoped unknown view
    "NodeUnknownView",
    # Block 15A.2 factory function
    "build_readonly_unknown_view",
    # Block 15A.3 production-like execution context
    "ProductionLikeBridgeContext",
    # Block 15A.3 production-like producer protocol
    "ProductionLikeRecordProducerProtocol",
    # Block 15A.3 single production-like binding
    "ProductionLikeComponentBinding",
    # Block 15A.3 production-like binding collection
    "ProductionLikeComponentSet",
    # Block 15A.3 production-like execution driver
    "execute_production_like_contributions",
    # Block 15A.3 convenience conversion wrapper
    "build_component_contribution_from_production_like_execution",
    # Block 15B.1 component ID container
    "FixedSingleLoopComponentIds",
    # Block 15B.1 node ID container
    "FixedSingleLoopNodeIds",
    # Block 15B.1 unknown name container
    "FixedSingleLoopUnknownNames",
    # Block 15B.1 residual name container
    "FixedSingleLoopResidualNames",
    # Block 15B.1 scenario container
    "FixedSingleLoopScenario",
    # Block 15B.1 factory function
    "build_fixed_single_loop_scenario",
    # Block 15B.2 explicit scalar parameters
    "FixedSingleLoopResidualParameters",
    # Block 15B.2 frozen assembled object
    "FixedSingleLoopPhysicalResidualAssembly",
    # Block 15B.2 deterministic factory
    "build_fixed_single_loop_physical_residuals",
    # Block 15B.2 thin convenience wrapper
    "build_component_contribution_from_fixed_single_loop_residuals",
    # Block 15B.3 frozen evaluation result
    "FixedSingleLoopEvaluationResult",
    # Block 15B.3 frozen solve request
    "FixedSingleLoopSolveRequest",
    # Block 15B.3 frozen solve result
    "FixedSingleLoopSolveResult",
    # Block 15B.3 deterministic residual evaluator
    "evaluate_fixed_single_loop_residuals",
    # Block 15B.3 thin solver wrapper
    "solve_fixed_single_loop_residuals",
    # Block 15B.3 simple serializable summary builder
    "build_fixed_single_loop_report",
    # Block 15C.1 junction role enum
    "JunctionRole",
    # Block 15C.1 split/merge junction declaration
    "JunctionDeclaration",
    # Block 15C.1 manifold with named branch port nodes
    "ManifoldDeclaration",
    # Block 15C.2 branch identifier
    "TopologyBranchId",
    # Block 15C.2 single branch declaration
    "ParallelBranchDeclaration",
    # Block 15C.2 component ID container
    "ParallelTopologyComponentIds",
    # Block 15C.2 node ID container
    "ParallelTopologyNodeIds",
    # Block 15C.2 unknown name container
    "ParallelTopologyUnknownNames",
    # Block 15C.2 residual name container
    "ParallelTopologyResidualNames",
    # Block 15C.2 scenario container
    "ParallelTopologyScenario",
    # Block 15C.2 factory function
    "build_parallel_topology_scenario",
    # Block 15C.3 valve declaration
    "ValveDeclaration",
]
