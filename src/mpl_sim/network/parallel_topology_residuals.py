"""Parallel topology branch residual assembly and evaluation — Block 15C-B.

Provides explicit parameterized algebraic residual equations for the fixed
two-branch parallel topology declared in Block 15C-A
(``ParallelTopologyScenario``).

This module bridges the 15C-A declaration to a physical-style residual
evaluation using the existing Phase 14A/14C/14D contribution infrastructure.
All residual equations are explicit and parameterized.

No production component physics, no property lookup, no CoolProp, no
PropertyBackend, no correlations, no HX models, no SystemState, no FluidState.

Topology (from Block 15C-A):
    accumulator → pump → [branch_a / branch_b] → [merge_a / merge_b]
        → condenser → accumulator

Nodes:
    n_acc_out   : accumulator outlet / pump inlet
    n_pump_out  : pump outlet / split point
    n_a_out     : branch A outlet
    n_b_out     : branch B outlet
    n_merge_out : merge point / condenser inlet
    n_cond_out  : condenser outlet / accumulator inlet

Residual equations and sign convention
---------------------------------------
All residuals equal zero at a consistent solution.

Mass-balance residuals (one per node, attributed to a component callback):

    mass_balance:n_cond_out   owned by accumulator
        = mdot_condenser - mdot_accumulator
    mass_balance:n_acc_out    owned by pump
        = mdot_accumulator - mdot_pump
    mass_balance:n_pump_out   owned by merge_a (split node equation)
        = mdot_pump - mdot_branch_a - mdot_branch_b
    mass_balance:n_a_out      owned by branch_a
        = mdot_branch_a - mdot_merge_a
    mass_balance:n_b_out      owned by branch_b
        = mdot_branch_b - mdot_merge_b
    mass_balance:n_merge_out  owned by merge_b (merge node equation)
        = mdot_merge_a + mdot_merge_b - mdot_condenser

Pressure residuals (one per component, explicit parameterized equations):

    pressure_drop:accumulator  owned by accumulator
        = P_n_acc_out - accumulator_pressure_reference
          Zero iff P_n_acc_out equals the reference pressure.
    pressure_drop:pump          owned by pump
        = P_n_pump_out - P_n_acc_out - pump_pressure_rise
          Zero iff outlet exceeds inlet by pump_pressure_rise.
    pressure_drop:branch_a      owned by branch_a
        = P_n_a_out - P_n_pump_out + branch_a_pressure_drop
          Zero iff inlet exceeds outlet by branch_a_pressure_drop.
    pressure_drop:branch_b      owned by branch_b
        = P_n_b_out - P_n_pump_out + branch_b_pressure_drop
          Zero iff inlet exceeds outlet by branch_b_pressure_drop.
    pressure_drop:merge_a       owned by merge_a
        = P_n_merge_out - P_n_a_out + merge_a_pressure_drop
          Zero iff branch_a outlet exceeds merge outlet by merge_a_pressure_drop.
    pressure_drop:merge_b       owned by merge_b
        = P_n_merge_out - P_n_b_out + merge_b_pressure_drop
          Zero iff branch_b outlet exceeds merge outlet by merge_b_pressure_drop.
    pressure_drop:condenser     owned by condenser
        = P_n_cond_out - P_n_merge_out + condenser_pressure_drop
          Zero iff merge outlet exceeds condenser outlet by condenser_pressure_drop.

Consistent solution (all 13 residuals = 0):
    Any total mass flow m > 0 and branch split (a, m-a) with 0 < a < m satisfy
    the mass-balance equations.  The pressure equations require the branch
    pressure-drop compatibility condition:
        branch_a_pressure_drop + merge_a_pressure_drop
        == branch_b_pressure_drop + merge_b_pressure_drop
    When the compatibility condition holds, the unique pressure solution is:
        P_n_acc_out   = accumulator_pressure_reference
        P_n_pump_out  = accumulator_pressure_reference + pump_pressure_rise
        P_n_a_out     = P_n_pump_out - branch_a_pressure_drop
        P_n_b_out     = P_n_pump_out - branch_b_pressure_drop
        P_n_merge_out = P_n_a_out - merge_a_pressure_drop
                      = P_n_b_out - merge_b_pressure_drop   (same value)
        P_n_cond_out  = P_n_merge_out - condenser_pressure_drop

Note on underdeterminacy
--------------------------
The mass-balance equations have rank 5 (not 6) because their sum is
identically zero for any flow network.  The full 13-residual system therefore
has two free mass-flow parameters:
  (1) the total mass-flow level;
  (2) the branch split ratio.

The pressure equations have 7 entries for 6 unknowns and are overdetermined
unless the branch compatibility condition holds.

Because of these two structural properties, a physically meaningful solver
would require two explicit mass-flow closure constraints plus explicit pressure
compatibility handling.  Those closures must come from caller-imposed
constraints or later physical laws; they are not gauges that this MVP may
invent.  Solving is therefore explicitly deferred.  Evaluation and report
remain fully supported.

Contribution attribution (component → residuals owned):
    accumulator : mass_balance:n_cond_out + pressure_drop:accumulator
    pump        : mass_balance:n_acc_out  + pressure_drop:pump
    branch_a    : mass_balance:n_a_out   + pressure_drop:branch_a
    branch_b    : mass_balance:n_b_out   + pressure_drop:branch_b
    merge_a     : mass_balance:n_pump_out + pressure_drop:merge_a
    merge_b     : mass_balance:n_merge_out + pressure_drop:merge_b
    condenser   : pressure_drop:condenser  (pressure only; no mass-balance residual)

Architecture constraints enforced here
---------------------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop, or mpl_sim.solvers.
MUST NOT import CoolProp or any property engine.
MUST NOT store FluidState, SystemState, mdot values, pressure values, or
    enthalpy values in structural objects.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT call PropertyBackend, CorrelationRegistry, or HeatExchangerModelRegistry.
MUST NOT implement solve(network) or NetworkGraph.solve().
MUST NOT execute production component physics.
MUST NOT infer physics from component_type.
MUST NOT write files or depend on pandas, matplotlib, or numpy.

Exported names
--------------
ParallelTopologyResidualParameters         — explicit scalar parameters
ParallelTopologyPhysicalResidualAssembly   — frozen assembled object
build_parallel_topology_physical_residuals — deterministic factory
ParallelTopologyEvaluationResult           — frozen evaluation result
evaluate_parallel_topology_residuals       — deterministic residual evaluator
build_parallel_topology_report             — simple serializable summary builder

Solving is explicitly deferred.  ParallelTopologySolveRequest and
ParallelTopologySolveResult are NOT implemented in this block.  The solve path
over Phase 13H remains deferred to a later block.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.contribution_adapters import (
    ComponentContribution,
    ComponentContributionAdapter,
    ComponentContributionAdapterSet,
    ComponentContributionContext,
    build_physical_adapters_from_contributions,
)
from mpl_sim.network.contribution_contract import ContributionResidualMap
from mpl_sim.network.parallel_topology_scenario import (
    ParallelTopologyResidualNames,
    ParallelTopologyScenario,
    ParallelTopologyUnknownNames,
)
from mpl_sim.network.physical_adapters import build_network_residual_evaluators
from mpl_sim.network.residual_evaluation import (
    NetworkUnknownValues,
    evaluate_network_residuals,
)

# ---------------------------------------------------------------------------
# ParallelTopologyResidualParameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelTopologyResidualParameters:
    """Explicit scalar parameters for the parallel-topology physical residuals.

    All seven parameters must be supplied explicitly; there are no defaults.
    All parameters must be finite, real, non-bool numeric scalars.

    Sign convention (see module docstring for the full residual equations):
      pump_pressure_rise             : positive value raises pressure at pump
                                       outlet relative to inlet (Pa)
      branch_a_pressure_drop         : positive value drops pressure along
                                       branch A (Pa)
      branch_b_pressure_drop         : positive value drops pressure along
                                       branch B (Pa)
      merge_a_pressure_drop          : positive value drops pressure from
                                       branch A outlet to merge outlet (Pa)
      merge_b_pressure_drop          : positive value drops pressure from
                                       branch B outlet to merge outlet (Pa)
      condenser_pressure_drop        : positive value drops pressure across
                                       the condenser (Pa)
      accumulator_pressure_reference : absolute pressure level at the
                                       accumulator outlet node (Pa); anchors
                                       the loop reference

    Branch pressure compatibility condition
    ----------------------------------------
    The pressure system has a consistent solution (all 7 pressure residuals
    simultaneously zero) if and only if:
        branch_a_pressure_drop + merge_a_pressure_drop
        == branch_b_pressure_drop + merge_b_pressure_drop

    This condition is NOT enforced by the parameter constructor; it is the
    caller's responsibility.  Evaluating at parameters that violate it will
    yield non-zero pressure_drop:merge_a and/or pressure_drop:merge_b residuals
    even at an otherwise consistent point.

    Validation
    ----------
    - All fields must be int or float; bool is rejected.
    - All fields must be finite (NaN and ±inf are rejected).
    - All fields are stored as float after validation.
    - Signs are not constrained: values are explicit signed algebraic
      parameters, not correlation-backed physical laws.
    - No physical defaults, no Kv/Cv, no flow-split laws, no correlations.
    """

    accumulator_pressure_reference: float
    pump_pressure_rise: float
    branch_a_pressure_drop: float
    branch_b_pressure_drop: float
    merge_a_pressure_drop: float
    merge_b_pressure_drop: float
    condenser_pressure_drop: float

    def __post_init__(self) -> None:
        _fields = (
            ("accumulator_pressure_reference", self.accumulator_pressure_reference),
            ("pump_pressure_rise", self.pump_pressure_rise),
            ("branch_a_pressure_drop", self.branch_a_pressure_drop),
            ("branch_b_pressure_drop", self.branch_b_pressure_drop),
            ("merge_a_pressure_drop", self.merge_a_pressure_drop),
            ("merge_b_pressure_drop", self.merge_b_pressure_drop),
            ("condenser_pressure_drop", self.condenser_pressure_drop),
        )
        for field_name, value in _fields:
            if isinstance(value, bool):
                raise TypeError(
                    f"ParallelTopologyResidualParameters.{field_name} must not be "
                    f"bool; got {value!r}"
                )
            if not isinstance(value, (int, float)):
                raise TypeError(
                    f"ParallelTopologyResidualParameters.{field_name} must be a "
                    f"real numeric (int or float); got {type(value).__name__!r}"
                )
            if not math.isfinite(value):
                raise ValueError(
                    f"ParallelTopologyResidualParameters.{field_name} must be "
                    f"finite; got {value!r}"
                )
            object.__setattr__(self, field_name, float(value))


# ---------------------------------------------------------------------------
# ParallelTopologyPhysicalResidualAssembly
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelTopologyPhysicalResidualAssembly:
    """Frozen parallel-topology physical residual assembly.

    Produced by build_parallel_topology_physical_residuals.  Contains:
      - the Block 15C-A scenario declaration;
      - explicit scalar parameters for the 13 residual equations;
      - a ContributionResidualMap (structural: contribution name → residual name);
      - a ComponentContributionAdapterSet (evaluation: callback per component);
      - optional caller metadata.

    Does not contain SystemState, FluidState, property backends, correlations,
    HX models, or production component objects.

    Evaluation path:
        physical_adapter_set = build_physical_adapters_from_contributions(
            self.scenario.binding_context, self.adapter_set
        )
        evaluators = build_network_residual_evaluators(
            self.scenario.assembly, physical_adapter_set
        )
        result = evaluate_network_residuals(
            self.scenario.assembly, evaluators, NetworkUnknownValues(uv)
        )

    Fields
    ------
    scenario     : Block 15C-A ParallelTopologyScenario declaration
    parameters   : explicit ParallelTopologyResidualParameters
    residual_map : ContributionResidualMap documenting attribution of
                   (component_id, contribution_name) → declared residual name
    adapter_set  : ComponentContributionAdapterSet with one adapter per component;
                   each callback computes its component's residuals explicitly
    metadata     : optional caller-supplied metadata; defensively copied
    """

    scenario: ParallelTopologyScenario
    parameters: ParallelTopologyResidualParameters
    residual_map: ContributionResidualMap
    adapter_set: ComponentContributionAdapterSet
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, ParallelTopologyScenario):
            raise TypeError(
                "ParallelTopologyPhysicalResidualAssembly.scenario must be a "
                f"ParallelTopologyScenario; got {type(self.scenario).__name__!r}"
            )
        if not isinstance(self.parameters, ParallelTopologyResidualParameters):
            raise TypeError(
                "ParallelTopologyPhysicalResidualAssembly.parameters must be a "
                "ParallelTopologyResidualParameters; "
                f"got {type(self.parameters).__name__!r}"
            )
        if not isinstance(self.residual_map, ContributionResidualMap):
            raise TypeError(
                "ParallelTopologyPhysicalResidualAssembly.residual_map must be a "
                f"ContributionResidualMap; got {type(self.residual_map).__name__!r}"
            )
        if not isinstance(self.adapter_set, ComponentContributionAdapterSet):
            raise TypeError(
                "ParallelTopologyPhysicalResidualAssembly.adapter_set must be a "
                "ComponentContributionAdapterSet; "
                f"got {type(self.adapter_set).__name__!r}"
            )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ParallelTopologyPhysicalResidualAssembly.metadata must be a "
                    f"Mapping or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# build_parallel_topology_physical_residuals
# ---------------------------------------------------------------------------


def build_parallel_topology_physical_residuals(
    scenario: object,
    parameters: object,
    *,
    metadata: object = None,
) -> ParallelTopologyPhysicalResidualAssembly:
    """Build a deterministic parallel-topology physical residual assembly.

    Creates explicit parameterized algebraic contribution adapters for the
    fixed scenario declared in Block 15C-A.  All residuals are explicit and
    parameterized; no property lookup, no correlations, no component execution.

    The factory is deterministic: calling it twice with equal scenario and
    parameters objects produces structurally identical assemblies.

    Contribution attribution (7 components → 13 residuals):
      accumulator : mass_balance:n_cond_out  + pressure_drop:accumulator
      pump        : mass_balance:n_acc_out   + pressure_drop:pump
      branch_a    : mass_balance:n_a_out     + pressure_drop:branch_a
      branch_b    : mass_balance:n_b_out     + pressure_drop:branch_b
      merge_a     : mass_balance:n_pump_out  + pressure_drop:merge_a
      merge_b     : mass_balance:n_merge_out + pressure_drop:merge_b
      condenser   : pressure_drop:condenser  (pressure only)

    Parameters
    ----------
    scenario : ParallelTopologyScenario
        The Block 15C-A fixed two-branch parallel topology scenario.
    parameters : ParallelTopologyResidualParameters
        Explicit scalar parameters for the residual equations.
    metadata : Mapping[str, object] | None
        Optional caller-supplied metadata; defensively copied.

    Returns
    -------
    ParallelTopologyPhysicalResidualAssembly
        Frozen assembly with residual_map and adapter_set for evaluation.

    Raises
    ------
    TypeError
        If scenario is not a ParallelTopologyScenario.
        If parameters is not a ParallelTopologyResidualParameters.
        If metadata is not a Mapping or None.
    """
    if not isinstance(scenario, ParallelTopologyScenario):
        raise TypeError(
            "build_parallel_topology_physical_residuals: scenario must be a "
            f"ParallelTopologyScenario; got {type(scenario).__name__!r}"
        )
    if not isinstance(parameters, ParallelTopologyResidualParameters):
        raise TypeError(
            "build_parallel_topology_physical_residuals: parameters must be a "
            "ParallelTopologyResidualParameters; "
            f"got {type(parameters).__name__!r}"
        )
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "build_parallel_topology_physical_residuals: metadata must be a "
            f"Mapping or None; got {type(metadata).__name__!r}"
        )

    cids = scenario.component_ids
    un: ParallelTopologyUnknownNames = scenario.unknown_names
    rn: ParallelTopologyResidualNames = scenario.residual_names

    # Build ContributionResidualMap documenting the attribution.
    residual_map = ContributionResidualMap(
        {
            (cids.accumulator, "mass_balance"): rn.mass_balance_n_cond_out,
            (cids.accumulator, "pressure_drop"): rn.pressure_drop_accumulator,
            (cids.pump, "mass_balance"): rn.mass_balance_n_acc_out,
            (cids.pump, "pressure_drop"): rn.pressure_drop_pump,
            (cids.branch_a, "mass_balance"): rn.mass_balance_n_a_out,
            (cids.branch_a, "pressure_drop"): rn.pressure_drop_branch_a,
            (cids.branch_b, "mass_balance"): rn.mass_balance_n_b_out,
            (cids.branch_b, "pressure_drop"): rn.pressure_drop_branch_b,
            (cids.merge_a, "mass_balance"): rn.mass_balance_n_pump_out,
            (cids.merge_a, "pressure_drop"): rn.pressure_drop_merge_a,
            (cids.merge_b, "mass_balance"): rn.mass_balance_n_merge_out,
            (cids.merge_b, "pressure_drop"): rn.pressure_drop_merge_b,
            (cids.condenser, "pressure_drop"): rn.pressure_drop_condenser,
        }
    )

    # Build contribution adapters in scenario component insertion order.
    adapter_set = ComponentContributionAdapterSet(
        adapters=(
            ComponentContributionAdapter(
                instance_id=cids.accumulator,
                callback=_make_accumulator_callback(un, rn, parameters),
            ),
            ComponentContributionAdapter(
                instance_id=cids.pump,
                callback=_make_pump_callback(un, rn, parameters),
            ),
            ComponentContributionAdapter(
                instance_id=cids.branch_a,
                callback=_make_branch_a_callback(un, rn, parameters),
            ),
            ComponentContributionAdapter(
                instance_id=cids.branch_b,
                callback=_make_branch_b_callback(un, rn, parameters),
            ),
            ComponentContributionAdapter(
                instance_id=cids.merge_a,
                callback=_make_merge_a_callback(un, rn, parameters),
            ),
            ComponentContributionAdapter(
                instance_id=cids.merge_b,
                callback=_make_merge_b_callback(un, rn, parameters),
            ),
            ComponentContributionAdapter(
                instance_id=cids.condenser,
                callback=_make_condenser_callback(un, rn, parameters),
            ),
        )
    )

    return ParallelTopologyPhysicalResidualAssembly(
        scenario=scenario,
        parameters=parameters,
        residual_map=residual_map,
        adapter_set=adapter_set,
        metadata=metadata,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# ParallelTopologyEvaluationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParallelTopologyEvaluationResult:
    """Frozen result of evaluating parallel-topology residuals at given unknown values.

    Does not contain SystemState, FluidState, property backends, or
    production component objects.  Does not write files.

    Fields
    ------
    scenario          : Block 15C-A ParallelTopologyScenario
    parameters        : Block 15C-B ParallelTopologyResidualParameters
    unknown_values    : read-only copy of the supplied unknown values (13 entries)
    residual_values   : read-only residual-name → value map in declaration order
    residual_names    : tuple of residual names in scenario declaration order
    max_abs_residual  : max absolute residual (L-infinity norm, unscaled)
    l2_residual       : L2 norm of raw residual values
    metadata          : optional caller-supplied metadata; defensively copied
    """

    scenario: ParallelTopologyScenario
    parameters: ParallelTopologyResidualParameters
    unknown_values: MappingProxyType
    residual_values: MappingProxyType
    residual_names: tuple
    max_abs_residual: float
    l2_residual: float
    metadata: MappingProxyType | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, ParallelTopologyScenario):
            raise TypeError(
                "ParallelTopologyEvaluationResult.scenario must be a "
                f"ParallelTopologyScenario; got {type(self.scenario).__name__!r}"
            )
        if not isinstance(self.parameters, ParallelTopologyResidualParameters):
            raise TypeError(
                "ParallelTopologyEvaluationResult.parameters must be a "
                "ParallelTopologyResidualParameters; "
                f"got {type(self.parameters).__name__!r}"
            )
        object.__setattr__(self, "unknown_values", MappingProxyType(dict(self.unknown_values)))
        object.__setattr__(self, "residual_values", MappingProxyType(dict(self.residual_values)))
        if not isinstance(self.residual_names, tuple):
            object.__setattr__(self, "residual_names", tuple(self.residual_names))
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ParallelTopologyEvaluationResult.metadata must be a "
                    f"Mapping or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# evaluate_parallel_topology_residuals
# ---------------------------------------------------------------------------


def evaluate_parallel_topology_residuals(
    scenario: object,
    parameters: object,
    unknown_values: object,
    *,
    metadata: object = None,
) -> ParallelTopologyEvaluationResult:
    """Evaluate all 13 parallel-topology residuals at explicit unknown values.

    Deterministic helper that:
    - validates all inputs;
    - builds the 15C-B physical residual assembly internally;
    - evaluates residuals using existing Phase 14A/13G infrastructure;
    - returns a frozen ParallelTopologyEvaluationResult;
    - preserves residual ordering from the scenario;
    - does not solve;
    - does not execute production components;
    - does not infer physics from component_type.

    Parameters
    ----------
    scenario : ParallelTopologyScenario
        The Block 15C-A fixed two-branch parallel topology scenario.
    parameters : ParallelTopologyResidualParameters
        Explicit scalar parameters for the 13 residual equations.
    unknown_values : Mapping[str, float]
        Explicit unknown values; must cover the 13 scenario unknowns exactly.
        All values must be finite, non-bool numeric.
    metadata : Mapping[str, object] | None
        Optional caller-supplied metadata; defensively copied.

    Returns
    -------
    ParallelTopologyEvaluationResult
        Frozen result with residual values, ordering, and norms.

    Raises
    ------
    TypeError
        If scenario, parameters, or unknown_values has the wrong type.
        If any unknown value is bool or non-numeric.
        If metadata is not a Mapping or None.
    ValueError
        If unknown_values does not cover the scenario unknowns exactly.
        If any unknown value is NaN or infinite.
    """
    _CALLER = "evaluate_parallel_topology_residuals"

    if not isinstance(scenario, ParallelTopologyScenario):
        raise TypeError(
            f"{_CALLER}: scenario must be a ParallelTopologyScenario; "
            f"got {type(scenario).__name__!r}"
        )
    if not isinstance(parameters, ParallelTopologyResidualParameters):
        raise TypeError(
            f"{_CALLER}: parameters must be a ParallelTopologyResidualParameters; "
            f"got {type(parameters).__name__!r}"
        )
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            f"{_CALLER}: metadata must be a Mapping or None; " f"got {type(metadata).__name__!r}"
        )

    validated_uv = _validate_unknown_values(_CALLER, scenario, unknown_values)

    phys_assembly = build_parallel_topology_physical_residuals(scenario, parameters)
    physical_adapter_set = build_physical_adapters_from_contributions(
        scenario.binding_context,
        phys_assembly.adapter_set,
    )
    evaluators = build_network_residual_evaluators(scenario.assembly, physical_adapter_set)
    scales = {name: 1.0 for name in scenario.assembly.residuals.names()}

    eval_result = evaluate_network_residuals(
        assembly=scenario.assembly,
        unknown_values=NetworkUnknownValues(values=validated_uv),
        evaluators=evaluators,
        scales=scales,
    )

    res_names = tuple(scenario.residual_names.all_names())
    res_values: dict[str, float] = {ev.spec.name: ev.value for ev in eval_result.evaluations}

    return ParallelTopologyEvaluationResult(
        scenario=scenario,
        parameters=parameters,
        unknown_values=MappingProxyType(validated_uv),
        residual_values=MappingProxyType(res_values),
        residual_names=res_names,
        max_abs_residual=eval_result.max_abs_scaled,
        l2_residual=eval_result.l2_scaled,
        metadata=metadata,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# build_parallel_topology_report
# ---------------------------------------------------------------------------


def build_parallel_topology_report(
    result: object,
) -> dict[str, object]:
    """Build a simple serializable summary from a parallel-topology evaluation result.

    Returns a plain dict with scenario symbolic identifiers, unknown values,
    residual values, norms, and an explicit MVP/fixed-topology note.

    Does not write files.  Does not depend on pandas, matplotlib, or numpy.
    All values in the returned dict are str, float, bool, int, list, or dict.

    Parameters
    ----------
    result : ParallelTopologyEvaluationResult
        Result from evaluate_parallel_topology_residuals.

    Returns
    -------
    dict[str, object]
        Plain serializable summary.

    Raises
    ------
    TypeError
        If result is not a ParallelTopologyEvaluationResult.
    """
    if not isinstance(result, ParallelTopologyEvaluationResult):
        raise TypeError(
            "build_parallel_topology_report: result must be a "
            "ParallelTopologyEvaluationResult; "
            f"got {type(result).__name__!r}"
        )

    scenario = result.scenario
    params = result.parameters
    return {
        "kind": "evaluation",
        "mvp_note": (
            "Block 15C-B fixed parallel-topology algebraic MVP — "
            "not arbitrary topology simulation; solving deferred"
        ),
        "topology": (
            "accumulator -> pump -> [branch_a/branch_b] "
            "-> [merge_a/merge_b] -> condenser -> accumulator"
        ),
        "component_ids": {
            "accumulator": scenario.component_ids.accumulator.value,
            "pump": scenario.component_ids.pump.value,
            "branch_a": scenario.component_ids.branch_a.value,
            "branch_b": scenario.component_ids.branch_b.value,
            "merge_a": scenario.component_ids.merge_a.value,
            "merge_b": scenario.component_ids.merge_b.value,
            "condenser": scenario.component_ids.condenser.value,
        },
        "node_ids": {
            "n_acc_out": scenario.node_ids.n_acc_out.value,
            "n_pump_out": scenario.node_ids.n_pump_out.value,
            "n_a_out": scenario.node_ids.n_a_out.value,
            "n_b_out": scenario.node_ids.n_b_out.value,
            "n_merge_out": scenario.node_ids.n_merge_out.value,
            "n_cond_out": scenario.node_ids.n_cond_out.value,
        },
        "parameters": {
            "accumulator_pressure_reference": params.accumulator_pressure_reference,
            "pump_pressure_rise": params.pump_pressure_rise,
            "branch_a_pressure_drop": params.branch_a_pressure_drop,
            "branch_b_pressure_drop": params.branch_b_pressure_drop,
            "merge_a_pressure_drop": params.merge_a_pressure_drop,
            "merge_b_pressure_drop": params.merge_b_pressure_drop,
            "condenser_pressure_drop": params.condenser_pressure_drop,
        },
        "unknown_values": dict(result.unknown_values),
        "residual_names": list(result.residual_names),
        "residual_values": dict(result.residual_values),
        "max_abs_residual": result.max_abs_residual,
        "l2_residual": result.l2_residual,
        "converged": None,
        "reason": "solve deferred — see block_15c_b_note",
        "block_15c_b_note": (
            "Solving is deferred: the 7 mass-flow unknowns are underdetermined "
            "by 2 degrees of freedom (total flow + branch split), and the 7 "
            "pressure equations for 6 unknowns are overdetermined unless the "
            "branch compatibility condition holds. Phase 13H requires a square "
            "determined system. A physically meaningful solve requires two "
            "explicit mass-flow closure constraints and explicit pressure "
            "compatibility handling; this MVP does not invent them."
        ),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_unknown_values(
    caller: str,
    scenario: ParallelTopologyScenario,
    values: object,
) -> dict[str, float]:
    """Validate unknown_values against scenario declarations. Returns a plain dict."""
    if not isinstance(values, Mapping):
        raise TypeError(
            f"{caller}: unknown_values must be a Mapping[str, float]; "
            f"got {type(values).__name__!r}"
        )
    declared = set(scenario.unknown_names.all_names())
    provided: set[str] = set(values.keys())  # type: ignore[union-attr]
    missing = declared - provided
    if missing:
        raise ValueError(
            f"{caller}: unknown_values missing for declared unknowns: " f"{sorted(missing)!r}"
        )
    extra = provided - declared
    if extra:
        raise ValueError(
            f"{caller}: unknown_values contain names not in scenario: " f"{sorted(extra)!r}"
        )
    out: dict[str, float] = {}
    for name in scenario.unknown_names.all_names():
        val = values[name]  # type: ignore[index]
        if isinstance(val, bool):
            raise TypeError(
                f"{caller}: value for unknown {name!r} must not be bool; " f"got {val!r}"
            )
        if not isinstance(val, (int, float)):
            raise TypeError(
                f"{caller}: value for unknown {name!r} must be numeric; "
                f"got {type(val).__name__!r}"
            )
        if not math.isfinite(float(val)):
            raise ValueError(
                f"{caller}: value for unknown {name!r} must be finite; " f"got {val!r}"
            )
        out[name] = float(val)
    return out


# ---------------------------------------------------------------------------
# Private callback factories
# ---------------------------------------------------------------------------


def _make_accumulator_callback(
    un: ParallelTopologyUnknownNames,
    rn: ParallelTopologyResidualNames,
    parameters: ParallelTopologyResidualParameters,
) -> Callable[[ComponentContributionContext], ComponentContribution]:
    """Return the contribution callback for the accumulator component.

    Residuals owned by accumulator:
        mass_balance:n_cond_out   = mdot_condenser - mdot_accumulator
        pressure_drop:accumulator = P_n_acc_out - accumulator_pressure_reference
    """
    _mdot_acc = un.mdot_accumulator
    _mdot_cond = un.mdot_condenser
    _P_acc_out = un.P_n_acc_out
    _r_mb = rn.mass_balance_n_cond_out
    _r_pd = rn.pressure_drop_accumulator
    _P_ref = parameters.accumulator_pressure_reference

    def _callback(ctx: ComponentContributionContext) -> ComponentContribution:
        uv = ctx.unknown_values
        return ComponentContribution(
            residual_values={
                _r_mb: uv[_mdot_cond] - uv[_mdot_acc],
                _r_pd: uv[_P_acc_out] - _P_ref,
            }
        )

    return _callback


def _make_pump_callback(
    un: ParallelTopologyUnknownNames,
    rn: ParallelTopologyResidualNames,
    parameters: ParallelTopologyResidualParameters,
) -> Callable[[ComponentContributionContext], ComponentContribution]:
    """Return the contribution callback for the pump component.

    Residuals owned by pump:
        mass_balance:n_acc_out = mdot_accumulator - mdot_pump
        pressure_drop:pump     = P_n_pump_out - P_n_acc_out - pump_pressure_rise
    """
    _mdot_acc = un.mdot_accumulator
    _mdot_pump = un.mdot_pump
    _P_acc_out = un.P_n_acc_out
    _P_pump_out = un.P_n_pump_out
    _r_mb = rn.mass_balance_n_acc_out
    _r_pd = rn.pressure_drop_pump
    _pump_rise = parameters.pump_pressure_rise

    def _callback(ctx: ComponentContributionContext) -> ComponentContribution:
        uv = ctx.unknown_values
        return ComponentContribution(
            residual_values={
                _r_mb: uv[_mdot_acc] - uv[_mdot_pump],
                _r_pd: uv[_P_pump_out] - uv[_P_acc_out] - _pump_rise,
            }
        )

    return _callback


def _make_branch_a_callback(
    un: ParallelTopologyUnknownNames,
    rn: ParallelTopologyResidualNames,
    parameters: ParallelTopologyResidualParameters,
) -> Callable[[ComponentContributionContext], ComponentContribution]:
    """Return the contribution callback for branch A.

    Residuals owned by branch_a:
        mass_balance:n_a_out  = mdot_branch_a - mdot_merge_a
        pressure_drop:branch_a = P_n_a_out - P_n_pump_out + branch_a_pressure_drop
    """
    _mdot_ba = un.mdot_branch_a
    _mdot_ma = un.mdot_merge_a
    _P_pump_out = un.P_n_pump_out
    _P_a_out = un.P_n_a_out
    _r_mb = rn.mass_balance_n_a_out
    _r_pd = rn.pressure_drop_branch_a
    _ba_drop = parameters.branch_a_pressure_drop

    def _callback(ctx: ComponentContributionContext) -> ComponentContribution:
        uv = ctx.unknown_values
        return ComponentContribution(
            residual_values={
                _r_mb: uv[_mdot_ba] - uv[_mdot_ma],
                _r_pd: uv[_P_a_out] - uv[_P_pump_out] + _ba_drop,
            }
        )

    return _callback


def _make_branch_b_callback(
    un: ParallelTopologyUnknownNames,
    rn: ParallelTopologyResidualNames,
    parameters: ParallelTopologyResidualParameters,
) -> Callable[[ComponentContributionContext], ComponentContribution]:
    """Return the contribution callback for branch B.

    Residuals owned by branch_b:
        mass_balance:n_b_out  = mdot_branch_b - mdot_merge_b
        pressure_drop:branch_b = P_n_b_out - P_n_pump_out + branch_b_pressure_drop
    """
    _mdot_bb = un.mdot_branch_b
    _mdot_mb = un.mdot_merge_b
    _P_pump_out = un.P_n_pump_out
    _P_b_out = un.P_n_b_out
    _r_mb = rn.mass_balance_n_b_out
    _r_pd = rn.pressure_drop_branch_b
    _bb_drop = parameters.branch_b_pressure_drop

    def _callback(ctx: ComponentContributionContext) -> ComponentContribution:
        uv = ctx.unknown_values
        return ComponentContribution(
            residual_values={
                _r_mb: uv[_mdot_bb] - uv[_mdot_mb],
                _r_pd: uv[_P_b_out] - uv[_P_pump_out] + _bb_drop,
            }
        )

    return _callback


def _make_merge_a_callback(
    un: ParallelTopologyUnknownNames,
    rn: ParallelTopologyResidualNames,
    parameters: ParallelTopologyResidualParameters,
) -> Callable[[ComponentContributionContext], ComponentContribution]:
    """Return the contribution callback for the merge_a element.

    Residuals owned by merge_a:
        mass_balance:n_pump_out = mdot_pump - mdot_branch_a - mdot_branch_b
            (split node equation: pump outlet splits to both branches)
        pressure_drop:merge_a   = P_n_merge_out - P_n_a_out + merge_a_pressure_drop
    """
    _mdot_pump = un.mdot_pump
    _mdot_ba = un.mdot_branch_a
    _mdot_bb = un.mdot_branch_b
    _P_a_out = un.P_n_a_out
    _P_merge_out = un.P_n_merge_out
    _r_mb = rn.mass_balance_n_pump_out
    _r_pd = rn.pressure_drop_merge_a
    _ma_drop = parameters.merge_a_pressure_drop

    def _callback(ctx: ComponentContributionContext) -> ComponentContribution:
        uv = ctx.unknown_values
        return ComponentContribution(
            residual_values={
                _r_mb: uv[_mdot_pump] - uv[_mdot_ba] - uv[_mdot_bb],
                _r_pd: uv[_P_merge_out] - uv[_P_a_out] + _ma_drop,
            }
        )

    return _callback


def _make_merge_b_callback(
    un: ParallelTopologyUnknownNames,
    rn: ParallelTopologyResidualNames,
    parameters: ParallelTopologyResidualParameters,
) -> Callable[[ComponentContributionContext], ComponentContribution]:
    """Return the contribution callback for the merge_b element.

    Residuals owned by merge_b:
        mass_balance:n_merge_out = mdot_merge_a + mdot_merge_b - mdot_condenser
            (merge node equation: both branches deliver to condenser)
        pressure_drop:merge_b    = P_n_merge_out - P_n_b_out + merge_b_pressure_drop
    """
    _mdot_ma = un.mdot_merge_a
    _mdot_mb = un.mdot_merge_b
    _mdot_cond = un.mdot_condenser
    _P_b_out = un.P_n_b_out
    _P_merge_out = un.P_n_merge_out
    _r_mb = rn.mass_balance_n_merge_out
    _r_pd = rn.pressure_drop_merge_b
    _mb_drop = parameters.merge_b_pressure_drop

    def _callback(ctx: ComponentContributionContext) -> ComponentContribution:
        uv = ctx.unknown_values
        return ComponentContribution(
            residual_values={
                _r_mb: uv[_mdot_ma] + uv[_mdot_mb] - uv[_mdot_cond],
                _r_pd: uv[_P_merge_out] - uv[_P_b_out] + _mb_drop,
            }
        )

    return _callback


def _make_condenser_callback(
    un: ParallelTopologyUnknownNames,
    rn: ParallelTopologyResidualNames,
    parameters: ParallelTopologyResidualParameters,
) -> Callable[[ComponentContributionContext], ComponentContribution]:
    """Return the contribution callback for the condenser component.

    Residuals owned by condenser (pressure only; all mass-balance residuals
    are attributed to other components):
        pressure_drop:condenser = P_n_cond_out - P_n_merge_out + condenser_pressure_drop
    """
    _P_merge_out = un.P_n_merge_out
    _P_cond_out = un.P_n_cond_out
    _r_pd = rn.pressure_drop_condenser
    _cond_drop = parameters.condenser_pressure_drop

    def _callback(ctx: ComponentContributionContext) -> ComponentContribution:
        uv = ctx.unknown_values
        return ComponentContribution(
            residual_values={
                _r_pd: uv[_P_cond_out] - uv[_P_merge_out] + _cond_drop,
            }
        )

    return _callback
