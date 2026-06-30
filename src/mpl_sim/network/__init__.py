"""Network package — Phase 7A/7B/7C/10I + Phase 13E–13H + Phase 14A–14G +
Block 15A.1 + Block 15A.2 + Block 15A.3 + Block 15B.1 + Block 15B.2 + Block 15B.3 +
Block 15C-A (15C.1 + 15C.2 + 15C.3) + Block 15C-B (15C.4 + 15C.5) +
Block 15D-A (hydraulic closure primitives) +
Block 15D-B (thermal closure primitives) +
Block 15D-C (closure integration and sufficiency diagnostics) +
Block 15E-A (configurable scenario builder foundation MVP) +
Block 15E-B (configurable physical residual selection MVP) +
Block 15F-A (configurable algebraic residual assembly foundation MVP) +
Block 15F-B (configurable algebraic residual selection integration MVP) +
Block 15G-A (explicit configurable residual blueprint assembly foundation MVP) +
Block 15G-B (explicit residual blueprint selection workflow integration MVP).

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

Block 15C-B exports (15C.4 + 15C.5 — branch residual assembly and parallel evaluation MVP):

  Explicit scalar parameters:
    ParallelTopologyResidualParameters

  Frozen assembled object:
    ParallelTopologyPhysicalResidualAssembly

  Deterministic factory:
    build_parallel_topology_physical_residuals

  Frozen evaluation result:
    ParallelTopologyEvaluationResult

  Deterministic residual evaluator:
    evaluate_parallel_topology_residuals

  Simple serializable summary builder:
    build_parallel_topology_report

  Note: Solving is explicitly deferred.  ParallelTopologySolveRequest and
  ParallelTopologySolveResult are not implemented in Block 15C-B.

Block 15D-A exports (hydraulic closure primitives MVP):

  Closure kind enum:
    HydraulicClosureKind

  Closure union type alias:
    HydraulicClosureDeclaration

  Concrete closure types:
    ImposedMassFlowClosure
    ImposedBranchSplitClosure
    ImposedPressureClosure
    LinearPressureDropClosure
    QuadraticPressureDropClosure
    PressureCompatibilityClosure

  Closure residual set:
    HydraulicClosureResidualSet

  Closure residual set factory:
    build_hydraulic_closure_residuals

  Diagnostics category enum:
    HydraulicClosureCategory

  Diagnostics declaration:
    HydraulicClosureDiagnostic

  Diagnostics result:
    HydraulicClosureDiagnosticResult

  Diagnostics functions:
    evaluate_hydraulic_closure_sufficiency
    make_two_branch_parallel_diagnostic

  Note: Block 15D-A introduces explicit algebraic closure primitives only.
  It is not property-backed, not correlation-backed, not HX-backed.
  It does not execute production components, does not assemble SystemState,
  does not construct FluidState, and does not add generic solve(network) or
  NetworkGraph.solve().  Imposed split closures are user-imposed constraints,
  not predicted branch distribution.

Block 15D-B exports (thermal closure primitives MVP):

  Closure kind enum:
    ThermalClosureKind

  Closure union type alias:
    ThermalClosureDeclaration

  Concrete closure types:
    FixedHeatRateClosure
    ImposedEnthalpyClosure
    ImposedTemperatureLikeClosure
    SensibleHeatRateClosure
    EnthalpyFlowHeatRateClosure
    EffectivenessHeatRateClosure
    RecuperatorEnergyBalanceClosure

  Closure residual set:
    ThermalClosureResidualSet

  Closure residual set factory:
    build_thermal_closure_residuals

  Diagnostics category enum:
    ThermalClosureCategory

  Diagnostics declaration:
    ThermalClosureDiagnostic

  Diagnostics result:
    ThermalClosureDiagnosticResult

  Diagnostics functions:
    evaluate_thermal_closure_sufficiency
    make_basic_thermal_loop_diagnostic
    make_recuperator_thermal_diagnostic

  Note: Block 15D-B introduces explicit algebraic thermal closure primitives
  only.  It is not property-backed, not correlation-backed, not HX-backed.
  Imposed enthalpy and temperature-like closures are user-imposed scalar
  constraints, not thermodynamic property calculations.  Sensible heat and
  enthalpy-flow closures are explicit algebraic relations with caller-supplied
  values.  Effectiveness and recuperator closures do not represent real HX
  models.  Block 15D-B does not execute production components, does not
  assemble SystemState, does not construct FluidState, and does not add
  generic solve(network) or NetworkGraph.solve().  Real LMTD/NTU/UA, HTC,
  phase, quality, saturation, and HX-backed closures remain deferred.

Block 15D-C exports (closure integration and sufficiency diagnostics MVP):

  Domain label enum:
    ClosureDomain

  Combined residual set:
    CombinedClosureResidualSet

  Evaluation result:
    CombinedClosureEvaluationResult

  Diagnostic result:
    CombinedClosureDiagnosticResult

  Factory function:
    build_combined_closure_residuals

  Evaluation functions:
    evaluate_combined_closure_residuals
    evaluate_combined_closure_sufficiency

  Report function:
    build_combined_closure_report

  Note: Block 15D-C combines hydraulic (15D-A) and thermal (15D-B) closure
  residual sets into a unified combined layer.  It provides combined residual
  evaluation, combined category-presence diagnostics, and plain report
  generation.  It is evaluation/reporting only; it does NOT solve the combined
  system.  Category sufficiency does NOT imply equation rank, DAE solvability,
  or physical predictiveness.  Block 15D-C is not property-backed, not
  correlation-backed, and not HX-backed.  It does not execute production
  components, does not assemble SystemState, does not construct FluidState,
  and does not add generic solve(network) or NetworkGraph.solve().  Later
  blocks remain responsible for configurable scenarios, production component
  adapters, property/correlation/HX-backed closures, combined physical residual
  assembly, and physically predictive solves.

Block 15E-A exports (configurable scenario builder foundation MVP):

  Component role enum:
    ScenarioComponentRole

  Spec types:
    ScenarioComponentSpec
    ScenarioNodeSpec
    ScenarioConnectionSpec
    ScenarioBranchSpec
    ConfigurableScenarioSpec

  Build result:
    ConfigurableScenarioBuildResult

  Factory functions:
    build_configurable_scenario
    build_configurable_scenario_report

  Note: Block 15E-A introduces explicit configurable scenario declarations
  that can describe simple loop and two-branch MPL-like network scenarios.
  Roles are declaration metadata only and do not trigger physics.  The builder
  produces a NetworkGraph, NetworkResidualAssembly, and NetworkBindingContext
  from an explicit spec.  Unknown and residual names are generated
  deterministically following existing naming conventions (mdot:<id>, P:<id>,
  mass_balance:<id>, pressure_drop:<id>).  Block 15E-A does not infer closures
  automatically, does not evaluate physical residuals, does not execute
  production components, does not assemble SystemState, does not construct
  FluidState, and does not add generic solve(network) or NetworkGraph.solve().
  It is not property-backed, not correlation-backed, and not HX-backed.
  Later blocks remain responsible for configurable physical residual selection,
  production component adapters, property/correlation/HX-backed closures,
  combined physical residual assembly, and physically predictive solves.

Block 15E-B exports (configurable physical residual selection MVP):

  Mode enum:
    ConfigurableResidualMode

  Request:
    ConfigurableResidualSelectionRequest

  Compatibility result:
    ConfigurableResidualCompatibilityResult

  Selection result:
    ConfigurableResidualSelectionResult

  Functions:
    select_configurable_residual_strategy
    evaluate_selected_configurable_residuals
    build_configurable_residual_selection_report

  Note: Block 15E-B adds an explicit, user-controlled residual-selection layer
  for configurable scenario declarations.  Residual modes (DECLARATION_ONLY,
  FIXED_SINGLE_LOOP_ALGEBRAIC, FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
  CLOSURE_ONLY) must be explicitly requested by the caller; no mode is chosen
  automatically from component roles or component_type.  Roles remain
  declaration metadata only and do not trigger physics dispatch.  Block 15E-B
  does not infer closures from roles.  It does not infer physical equations
  from roles.  It can reuse existing fixed single-loop and fixed two-branch
  evaluation-only residual layers only when structurally compatible and
  explicitly selected.  It can evaluate closure-only residuals only when
  closure sets are explicitly supplied.  Block 15E-B does not solve.  It is
  not property-backed, not correlation-backed, not HX-backed.  It does not
  execute production components, does not assemble SystemState, does not
  construct FluidState, and does not add generic solve(network) or
  NetworkGraph.solve().  Later blocks remain responsible for: configurable
  physical residual assembly beyond known fixed MVPs; production component
  adapters; property/correlation/HX-backed closures; rank/solvability analysis;
  physically predictive solves.

Block 15F-A exports (configurable algebraic residual assembly foundation MVP):

  Kind enum:
    ConfigurableAlgebraicResidualKind

  Declaration union type alias:
    ConfigurableAlgebraicResidualDeclaration

  Concrete declaration types:
    MassBalanceResidualDeclaration
    PressureDifferenceResidualDeclaration
    ImposedPressureResidualDeclaration
    ImposedMassFlowResidualDeclaration
    EnthalpyFlowResidualDeclaration

  Residual set:
    ConfigurableAlgebraicResidualSet

  Evaluation result:
    ConfigurableAlgebraicResidualEvaluationResult

  Functions:
    build_configurable_algebraic_residual_set
    evaluate_configurable_algebraic_residuals
    validate_algebraic_residuals_against_scenario
    build_configurable_algebraic_residual_report

  Note: Block 15F-A adds explicit user-declared algebraic residual declarations
  for configurable scenarios.  Residuals are declared with explicit unknown names
  and scalar parameters; none are inferred from component roles or graph topology.
  Evaluation requires an explicit call over an explicit unknown-value mapping.
  Block 15F-A is property-free, correlation-free, and HX-model-free.  It does
  not execute production components, does not assemble SystemState, does not
  construct FluidState, does not call CoolProp or PropertyBackend, and does not
  solve.  No generic solve(network) or NetworkGraph.solve() is added.  Later
  blocks remain responsible for: richer configurable physical residual assembly;
  production component adapters; property/correlation/HX-backed closures;
  rank/solvability analysis; physically predictive solves.

Block 15F-B exports (configurable algebraic residual selection integration MVP):

  The Block 15F-B exports are integrated into the existing Block 15E-B symbols.
  No new runtime modules are added.

  New residual-selection mode:
    ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC

  Extended request field:
    ConfigurableResidualSelectionRequest.algebraic_residual_set
    ConfigurableResidualSelectionRequest.algebraic_unknown_values

  Extended result evaluation type:
    ConfigurableResidualSelectionResult.evaluation_result may now also be a
    ConfigurableAlgebraicResidualEvaluationResult (in addition to existing types).

  Extended report flags:
    build_configurable_residual_selection_report now includes:
      residuals_inferred_from_roles: False
      residuals_inferred_from_topology: False

  Note: Block 15F-B integrates the 15F-A algebraic residual foundation into the
  15E-B residual-selection layer.  It adds one explicit user-requested algebraic
  residual selection mode (CONFIGURABLE_ALGEBRAIC).  Algebraic residuals must be
  supplied explicitly via ConfigurableAlgebraicResidualSet.  They are validated
  against scenario unknown names only.  No residuals are inferred from roles.
  No residuals are inferred from topology.  No closures are inferred from roles.
  No solve is added.  No property/correlation/HX-backed execution is added.
  No production component execution is added.  No SystemState is assembled.
  No FluidState is constructed.  Later blocks remain responsible for: richer
  physical residual assembly; production component adapters;
  property/correlation/HX-backed closures; rank/solvability analysis;
  physically predictive solves.

Block 15G-A exports (explicit configurable residual blueprint assembly foundation MVP):

  Blueprint kind enum:
    ConfigurableResidualBlueprintKind

  Blueprint union type alias:
    ConfigurableResidualBlueprintDeclaration

  Concrete blueprint types:
    MassBalanceResidualBlueprint
    PressureDifferenceResidualBlueprint
    ImposedPressureResidualBlueprint
    ImposedMassFlowResidualBlueprint
    EnthalpyFlowResidualBlueprint

  Blueprint set:
    ConfigurableResidualBlueprintSet

  Blueprint set factory:
    build_configurable_residual_blueprint_set

  Build result:
    ConfigurableResidualBlueprintBuildResult

  Builder function:
    build_configurable_algebraic_residuals_from_blueprints

  Report function:
    build_configurable_residual_blueprint_report

  Note: Block 15G-A adds an explicit configurable residual blueprint layer that
  translates scenario-level IDs (component IDs, node IDs) into 15F-A algebraic
  residual declarations.  Blueprints are user-declared; none are inferred from
  component roles or graph topology.  Translation uses deterministic naming
  conventions: mdot:<component_id> and P:<node_id>.  Translated blueprints
  produce a ConfigurableAlgebraicResidualSet that is directly usable with the
  existing 15F-B CONFIGURABLE_ALGEBRAIC selection mode.  Scenario unknown-name
  validation is identifier-level only.  Block 15G-A does not solve.  It does not
  add property/correlation/HX-backed execution.  It does not execute production
  components.  It does not assemble SystemState.  It does not construct FluidState.
  It does not add generic solve(network) or NetworkGraph.solve().  Later blocks
  remain responsible for: richer physical residual assembly; production component
  adapters; property/correlation/HX-backed closures; rank/solvability analysis;
  physically predictive solves.

Block 15G-B exports (explicit residual blueprint selection workflow integration MVP):

  Workflow request:
    ConfigurableResidualBlueprintWorkflowRequest

  Workflow result:
    ConfigurableResidualBlueprintWorkflowResult

  Workflow helper:
    build_configurable_residual_selection_from_blueprints

  Workflow report function:
    build_configurable_residual_blueprint_workflow_report

  Note: Block 15G-B adds a small workflow integration layer that wires
  Block 15G-A explicit residual blueprints into the Block 15F-B
  CONFIGURABLE_ALGEBRAIC residual selection mode.  Workflow input remains
  user-declared: an explicit ConfigurableScenarioBuildResult, explicit
  blueprints, and optional explicit unknown values.  The workflow builds the
  15G-A blueprint result and passes the generated algebraic residual set into
  the 15F-B CONFIGURABLE_ALGEBRAIC selection request.  Evaluation remains
  optional and requires evaluate=True plus explicit unknown values.  No
  blueprints are inferred from roles.  No blueprints are inferred from
  topology.  No residuals are inferred from roles.  No residuals are inferred
  from topology.  No closures are inferred from roles.  No solve is added.
  No property/correlation/HX-backed execution is added.  No production
  component execution is added.  No SystemState is assembled.  No FluidState
  is constructed.  No generic solve(network) or NetworkGraph.solve() is
  added.  Later blocks remain responsible for: richer physical residual
  assembly; production component adapters; property/correlation/HX-backed
  closures; rank/solvability analysis; physically predictive solves.

MUST NOT import from solvers/.
"""

from mpl_sim.network.assembly import NetworkAssembly, assemble_network
from mpl_sim.network.closure_integration import (
    ClosureDomain,
    CombinedClosureDiagnosticResult,
    CombinedClosureEvaluationResult,
    CombinedClosureResidualSet,
    build_combined_closure_report,
    build_combined_closure_residuals,
    evaluate_combined_closure_residuals,
    evaluate_combined_closure_sufficiency,
)
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
from mpl_sim.network.configurable_algebraic_residuals import (
    ConfigurableAlgebraicResidualDeclaration,
    ConfigurableAlgebraicResidualEvaluationResult,
    ConfigurableAlgebraicResidualKind,
    ConfigurableAlgebraicResidualSet,
    EnthalpyFlowResidualDeclaration,
    ImposedMassFlowResidualDeclaration,
    ImposedPressureResidualDeclaration,
    MassBalanceResidualDeclaration,
    PressureDifferenceResidualDeclaration,
    build_configurable_algebraic_residual_report,
    build_configurable_algebraic_residual_set,
    evaluate_configurable_algebraic_residuals,
    validate_algebraic_residuals_against_scenario,
)
from mpl_sim.network.configurable_residual_blueprint_workflows import (
    ConfigurableResidualBlueprintWorkflowRequest,
    ConfigurableResidualBlueprintWorkflowResult,
    build_configurable_residual_blueprint_workflow_report,
    build_configurable_residual_selection_from_blueprints,
)
from mpl_sim.network.configurable_residual_blueprints import (
    ConfigurableResidualBlueprintBuildResult,
    ConfigurableResidualBlueprintDeclaration,
    ConfigurableResidualBlueprintKind,
    ConfigurableResidualBlueprintSet,
    EnthalpyFlowResidualBlueprint,
    ImposedMassFlowResidualBlueprint,
    ImposedPressureResidualBlueprint,
    MassBalanceResidualBlueprint,
    PressureDifferenceResidualBlueprint,
    build_configurable_algebraic_residuals_from_blueprints,
    build_configurable_residual_blueprint_report,
    build_configurable_residual_blueprint_set,
)
from mpl_sim.network.configurable_residual_selection import (
    ConfigurableResidualCompatibilityResult,
    ConfigurableResidualMode,
    ConfigurableResidualSelectionRequest,
    ConfigurableResidualSelectionResult,
    build_configurable_residual_selection_report,
    evaluate_selected_configurable_residuals,
    select_configurable_residual_strategy,
)
from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioBuildResult,
    ConfigurableScenarioSpec,
    ScenarioBranchSpec,
    ScenarioComponentRole,
    ScenarioComponentSpec,
    ScenarioConnectionSpec,
    ScenarioNodeSpec,
    build_configurable_scenario,
    build_configurable_scenario_report,
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
from mpl_sim.network.hydraulic_closure_diagnostics import (
    HydraulicClosureCategory,
    HydraulicClosureDiagnostic,
    HydraulicClosureDiagnosticResult,
    evaluate_hydraulic_closure_sufficiency,
    make_two_branch_parallel_diagnostic,
)
from mpl_sim.network.hydraulic_closures import (
    HydraulicClosureDeclaration,
    HydraulicClosureKind,
    HydraulicClosureResidualSet,
    ImposedBranchSplitClosure,
    ImposedMassFlowClosure,
    ImposedPressureClosure,
    LinearPressureDropClosure,
    PressureCompatibilityClosure,
    QuadraticPressureDropClosure,
    build_hydraulic_closure_residuals,
)
from mpl_sim.network.parallel_topology_residuals import (
    ParallelTopologyEvaluationResult,
    ParallelTopologyPhysicalResidualAssembly,
    ParallelTopologyResidualParameters,
    build_parallel_topology_physical_residuals,
    build_parallel_topology_report,
    evaluate_parallel_topology_residuals,
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
from mpl_sim.network.thermal_closure_diagnostics import (
    ThermalClosureCategory,
    ThermalClosureDiagnostic,
    ThermalClosureDiagnosticResult,
    evaluate_thermal_closure_sufficiency,
    make_basic_thermal_loop_diagnostic,
    make_recuperator_thermal_diagnostic,
)
from mpl_sim.network.thermal_closures import (
    EffectivenessHeatRateClosure,
    EnthalpyFlowHeatRateClosure,
    FixedHeatRateClosure,
    ImposedEnthalpyClosure,
    ImposedTemperatureLikeClosure,
    RecuperatorEnergyBalanceClosure,
    SensibleHeatRateClosure,
    ThermalClosureDeclaration,
    ThermalClosureKind,
    ThermalClosureResidualSet,
    build_thermal_closure_residuals,
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
    # Block 15C-B explicit scalar parameters
    "ParallelTopologyResidualParameters",
    # Block 15C-B frozen assembled object
    "ParallelTopologyPhysicalResidualAssembly",
    # Block 15C-B deterministic factory
    "build_parallel_topology_physical_residuals",
    # Block 15C-B frozen evaluation result
    "ParallelTopologyEvaluationResult",
    # Block 15C-B deterministic residual evaluator
    "evaluate_parallel_topology_residuals",
    # Block 15C-B simple serializable summary builder
    "build_parallel_topology_report",
    # Block 15D-A closure kind enum
    "HydraulicClosureKind",
    # Block 15D-A closure union type alias
    "HydraulicClosureDeclaration",
    # Block 15D-A concrete closure types
    "ImposedMassFlowClosure",
    "ImposedBranchSplitClosure",
    "ImposedPressureClosure",
    "LinearPressureDropClosure",
    "QuadraticPressureDropClosure",
    "PressureCompatibilityClosure",
    # Block 15D-A closure residual set
    "HydraulicClosureResidualSet",
    # Block 15D-A closure residual set factory
    "build_hydraulic_closure_residuals",
    # Block 15D-A diagnostics category enum
    "HydraulicClosureCategory",
    # Block 15D-A diagnostics declaration
    "HydraulicClosureDiagnostic",
    # Block 15D-A diagnostics result
    "HydraulicClosureDiagnosticResult",
    # Block 15D-A diagnostics functions
    "evaluate_hydraulic_closure_sufficiency",
    "make_two_branch_parallel_diagnostic",
    # Block 15D-B closure kind enum
    "ThermalClosureKind",
    # Block 15D-B closure union type alias
    "ThermalClosureDeclaration",
    # Block 15D-B concrete closure types
    "FixedHeatRateClosure",
    "ImposedEnthalpyClosure",
    "ImposedTemperatureLikeClosure",
    "SensibleHeatRateClosure",
    "EnthalpyFlowHeatRateClosure",
    "EffectivenessHeatRateClosure",
    "RecuperatorEnergyBalanceClosure",
    # Block 15D-B closure residual set
    "ThermalClosureResidualSet",
    # Block 15D-B closure residual set factory
    "build_thermal_closure_residuals",
    # Block 15D-B diagnostics category enum
    "ThermalClosureCategory",
    # Block 15D-B diagnostics declaration
    "ThermalClosureDiagnostic",
    # Block 15D-B diagnostics result
    "ThermalClosureDiagnosticResult",
    # Block 15D-B diagnostics functions
    "evaluate_thermal_closure_sufficiency",
    "make_basic_thermal_loop_diagnostic",
    "make_recuperator_thermal_diagnostic",
    # Block 15D-C domain label enum
    "ClosureDomain",
    # Block 15D-C combined residual set
    "CombinedClosureResidualSet",
    # Block 15D-C evaluation result
    "CombinedClosureEvaluationResult",
    # Block 15D-C diagnostic result
    "CombinedClosureDiagnosticResult",
    # Block 15D-C factory function
    "build_combined_closure_residuals",
    # Block 15D-C evaluation functions
    "evaluate_combined_closure_residuals",
    "evaluate_combined_closure_sufficiency",
    # Block 15D-C report function
    "build_combined_closure_report",
    # Block 15E-A component role enum
    "ScenarioComponentRole",
    # Block 15E-A spec types
    "ScenarioComponentSpec",
    "ScenarioNodeSpec",
    "ScenarioConnectionSpec",
    "ScenarioBranchSpec",
    "ConfigurableScenarioSpec",
    # Block 15E-A build result
    "ConfigurableScenarioBuildResult",
    # Block 15E-A factory functions
    "build_configurable_scenario",
    "build_configurable_scenario_report",
    # Block 15E-B mode enum
    "ConfigurableResidualMode",
    # Block 15E-B request
    "ConfigurableResidualSelectionRequest",
    # Block 15E-B compatibility result
    "ConfigurableResidualCompatibilityResult",
    # Block 15E-B selection result
    "ConfigurableResidualSelectionResult",
    # Block 15E-B functions
    "select_configurable_residual_strategy",
    "evaluate_selected_configurable_residuals",
    "build_configurable_residual_selection_report",
    # Block 15F-A kind enum
    "ConfigurableAlgebraicResidualKind",
    # Block 15F-A declaration union type alias
    "ConfigurableAlgebraicResidualDeclaration",
    # Block 15F-A concrete declaration types
    "MassBalanceResidualDeclaration",
    "PressureDifferenceResidualDeclaration",
    "ImposedPressureResidualDeclaration",
    "ImposedMassFlowResidualDeclaration",
    "EnthalpyFlowResidualDeclaration",
    # Block 15F-A residual set
    "ConfigurableAlgebraicResidualSet",
    # Block 15F-A evaluation result
    "ConfigurableAlgebraicResidualEvaluationResult",
    # Block 15F-A functions
    "build_configurable_algebraic_residual_set",
    "evaluate_configurable_algebraic_residuals",
    "validate_algebraic_residuals_against_scenario",
    "build_configurable_algebraic_residual_report",
    # Block 15G-A blueprint kind enum
    "ConfigurableResidualBlueprintKind",
    # Block 15G-A blueprint union type alias
    "ConfigurableResidualBlueprintDeclaration",
    # Block 15G-A concrete blueprint types
    "MassBalanceResidualBlueprint",
    "PressureDifferenceResidualBlueprint",
    "ImposedPressureResidualBlueprint",
    "ImposedMassFlowResidualBlueprint",
    "EnthalpyFlowResidualBlueprint",
    # Block 15G-A blueprint set
    "ConfigurableResidualBlueprintSet",
    # Block 15G-A blueprint set factory
    "build_configurable_residual_blueprint_set",
    # Block 15G-A build result
    "ConfigurableResidualBlueprintBuildResult",
    # Block 15G-A builder function
    "build_configurable_algebraic_residuals_from_blueprints",
    # Block 15G-A report function
    "build_configurable_residual_blueprint_report",
    # Block 15G-B workflow request
    "ConfigurableResidualBlueprintWorkflowRequest",
    # Block 15G-B workflow result
    "ConfigurableResidualBlueprintWorkflowResult",
    # Block 15G-B workflow helper
    "build_configurable_residual_selection_from_blueprints",
    # Block 15G-B workflow report function
    "build_configurable_residual_blueprint_workflow_report",
]
