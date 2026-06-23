"""Fixed single-loop physical residual assembly — Block 15B.2.

Provides explicit parameterized algebraic residual equations for the fixed
minimal single-loop network declared in Block 15B.1.

This module is the bridge from the 15B.1 declaration to physical-style
residual evaluation using the existing Phase 14A/14C/14D contribution
infrastructure.  All residual equations are explicit and parameterized;
no production component physics, no property lookup, no CoolProp, no
PropertyBackend, no correlations, no HX models, no SystemState, no FluidState.

Topology (from Block 15B.1):
    accumulator → pump → evaporator → condenser → accumulator

Nodes:
    n_acc_out  : accumulator outlet / pump inlet
    n_pump_out : pump outlet / evaporator inlet
    n_evap_out : evaporator outlet / condenser inlet
    n_cond_out : condenser outlet / accumulator inlet

Residual equations and sign convention
---------------------------------------
All residuals equal zero at the consistent solution.

Mass-balance residuals (attributed to the component whose outlet feeds the node):
    mass_balance:n_cond_out  = mdot_condenser - mdot_accumulator
        (owned by accumulator — the accumulator outlet node is n_acc_out, so
         the closing-loop balance at n_cond_out is attributed here)
    mass_balance:n_acc_out   = mdot_accumulator - mdot_pump
        (owned by pump)
    mass_balance:n_pump_out  = mdot_pump - mdot_evaporator
        (owned by evaporator)
    mass_balance:n_evap_out  = mdot_evaporator - mdot_condenser
        (owned by condenser)

Pressure residuals (one per component, explicit parameterized equations):
    pressure_drop:accumulator = P_n_acc_out - accumulator_pressure_reference
        Accumulator sets the absolute pressure reference for the loop.
        (zero residual ⟺ P_n_acc_out equals the reference value)
    pressure_drop:pump        = P_n_pump_out - P_n_acc_out - pump_pressure_rise
        Pump raises pressure by pump_pressure_rise Pa.
        (zero residual ⟺ outlet pressure exceeds inlet by pump_pressure_rise)
    pressure_drop:evaporator  = P_n_evap_out - P_n_pump_out + evaporator_pressure_drop
        Evaporator drops pressure by evaporator_pressure_drop Pa.
        (zero residual ⟺ inlet pressure exceeds outlet by evaporator_pressure_drop)
    pressure_drop:condenser   = P_n_cond_out - P_n_evap_out + condenser_pressure_drop
        Condenser drops pressure by condenser_pressure_drop Pa.
        (zero residual ⟺ inlet pressure exceeds outlet by condenser_pressure_drop)

Consistent solution (all 8 residuals = 0):
    mdot_accumulator = mdot_pump = mdot_evaporator = mdot_condenser = m  (any m)
    P_n_acc_out  = accumulator_pressure_reference
    P_n_pump_out = accumulator_pressure_reference + pump_pressure_rise
    P_n_evap_out = accumulator_pressure_reference + pump_pressure_rise - evaporator_pressure_drop
    P_n_cond_out = accumulator_pressure_reference + pump_pressure_rise
                   - evaporator_pressure_drop - condenser_pressure_drop

Note: the mass-flow degree of freedom is not fixed by the pressure equations,
so the system has exactly one free parameter (m) for which the pressure
equations are satisfied.  A constraint fixing m would be needed for a unique
solution; no such constraint is added in this MVP.

Contribution attribution (each component owns one mass-balance + one pressure residual):
    accumulator : mass_balance:n_cond_out  + pressure_drop:accumulator
    pump        : mass_balance:n_acc_out   + pressure_drop:pump
    evaporator  : mass_balance:n_pump_out  + pressure_drop:evaporator
    condenser   : mass_balance:n_evap_out  + pressure_drop:condenser

Evaluation path (using existing Phase 14A/14C infrastructure):
    1. Obtain assembly.adapter_set (ComponentContributionAdapterSet)
    2. build_physical_adapters_from_contributions(scenario.binding_context, adapter_set)
       → PhysicalResidualAdapterSet
    3. build_network_residual_evaluators(scenario.assembly, physical_adapter_set)
       → tuple[NetworkResidualEvaluator, ...]
    4. evaluate_network_residuals(scenario.assembly, evaluators, NetworkUnknownValues(...))
       → NetworkResidualEvaluationResult

Block 15B.2 scope
-----------------
This block is fixed-architecture only.  It does NOT:
- Execute production components or call contribute(...).
- Assemble SystemState or create FluidState.
- Call CoolProp, PropertyBackend, correlations, or HX models.
- Implement arbitrary-topology simulation.
- Add generic solve(network) or NetworkGraph.solve().
- Fix the mass-flow degree of freedom (that remains for a later checkpoint).

Architecture boundaries (MUST NOT)
-----------------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop, or mpl_sim.solvers.
MUST NOT import CoolProp or any property engine.
MUST NOT import or invoke CorrelationRegistry or HeatExchangerModelRegistry.
MUST NOT import or reference SystemState, FluidState, or PropertyBackend.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT expose solve(network) or NetworkGraph.solve().
MUST NOT infer physics from component_type.

Exported names
--------------
FixedSingleLoopResidualParameters                          — explicit scalar parameters
FixedSingleLoopPhysicalResidualAssembly                    — frozen assembled object
build_fixed_single_loop_physical_residuals                 — deterministic factory
build_component_contribution_from_fixed_single_loop_residuals — thin convenience wrapper
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
)
from mpl_sim.network.contribution_contract import ContributionResidualMap
from mpl_sim.network.fixed_single_loop_scenario import (
    FixedSingleLoopResidualNames,
    FixedSingleLoopScenario,
    FixedSingleLoopUnknownNames,
)
from mpl_sim.network.graph import ComponentInstanceId

# ---------------------------------------------------------------------------
# FixedSingleLoopResidualParameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedSingleLoopResidualParameters:
    """Explicit scalar parameters for the fixed single-loop physical residuals.

    All four parameters must be supplied explicitly; there are no defaults.
    All parameters must be finite, real, non-bool numeric scalars.

    Sign convention (see module docstring for the full residual equations):
      pump_pressure_rise             : positive conventional value raises loop
                                       pressure (Pa)
      evaporator_pressure_drop       : positive conventional value drops loop
                                       pressure (Pa)
      condenser_pressure_drop        : positive conventional value drops loop
                                       pressure (Pa)
      accumulator_pressure_reference : absolute pressure level at the
                                       accumulator outlet node (Pa); anchors
                                       the loop

    Fields
    ------
    pump_pressure_rise             : pressure rise across pump (Pa)
    evaporator_pressure_drop       : pressure drop across evaporator (Pa)
    condenser_pressure_drop        : pressure drop across condenser (Pa)
    accumulator_pressure_reference : reference pressure at accumulator outlet (Pa)

    Validation
    ----------
    - All fields must be int or float; bool is rejected.
    - All fields must be finite (NaN and ±inf are rejected).
    - All fields are stored as float after validation.
    - Signs are not constrained in this MVP: values are explicit signed
      algebraic parameters, not correlation-backed physical laws.
    """

    pump_pressure_rise: float
    evaporator_pressure_drop: float
    condenser_pressure_drop: float
    accumulator_pressure_reference: float

    def __post_init__(self) -> None:
        _fields = (
            ("pump_pressure_rise", self.pump_pressure_rise),
            ("evaporator_pressure_drop", self.evaporator_pressure_drop),
            ("condenser_pressure_drop", self.condenser_pressure_drop),
            ("accumulator_pressure_reference", self.accumulator_pressure_reference),
        )
        for field_name, value in _fields:
            if isinstance(value, bool):
                raise TypeError(
                    f"FixedSingleLoopResidualParameters.{field_name} must not be "
                    f"bool; got {value!r}"
                )
            if not isinstance(value, (int, float)):
                raise TypeError(
                    f"FixedSingleLoopResidualParameters.{field_name} must be a "
                    f"real numeric (int or float); got {type(value).__name__!r}"
                )
            if not math.isfinite(value):
                raise ValueError(
                    f"FixedSingleLoopResidualParameters.{field_name} must be "
                    f"finite; got {value!r}"
                )
            object.__setattr__(self, field_name, float(value))


# ---------------------------------------------------------------------------
# FixedSingleLoopPhysicalResidualAssembly
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedSingleLoopPhysicalResidualAssembly:
    """Frozen fixed single-loop physical residual assembly.

    Produced by build_fixed_single_loop_physical_residuals.  Contains:
      - the Block 15B.1 scenario declaration;
      - explicit scalar parameters for the residual equations;
      - a ContributionResidualMap (structural: contribution name → residual name);
      - a ComponentContributionAdapterSet (evaluation: callback per component);
      - optional caller metadata.

    Does not contain SystemState, FluidState, property backends, correlations,
    HX models, or production component objects.

    Evaluation path (see module docstring):
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
    scenario     : Block 15B.1 FixedSingleLoopScenario declaration
    parameters   : explicit FixedSingleLoopResidualParameters
    residual_map : ContributionResidualMap mapping (component_id, contribution_name)
                   to the declared residual name
    adapter_set  : ComponentContributionAdapterSet with one adapter per component;
                   each adapter's callback computes two residuals (mass_balance +
                   pressure_drop) for its component
    metadata     : optional caller-supplied metadata; defensively copied
    """

    scenario: FixedSingleLoopScenario
    parameters: FixedSingleLoopResidualParameters
    residual_map: ContributionResidualMap
    adapter_set: ComponentContributionAdapterSet
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, FixedSingleLoopScenario):
            raise TypeError(
                "FixedSingleLoopPhysicalResidualAssembly.scenario must be a "
                f"FixedSingleLoopScenario; got {type(self.scenario).__name__!r}"
            )
        if not isinstance(self.parameters, FixedSingleLoopResidualParameters):
            raise TypeError(
                "FixedSingleLoopPhysicalResidualAssembly.parameters must be a "
                "FixedSingleLoopResidualParameters; "
                f"got {type(self.parameters).__name__!r}"
            )
        if not isinstance(self.residual_map, ContributionResidualMap):
            raise TypeError(
                "FixedSingleLoopPhysicalResidualAssembly.residual_map must be a "
                f"ContributionResidualMap; got {type(self.residual_map).__name__!r}"
            )
        if not isinstance(self.adapter_set, ComponentContributionAdapterSet):
            raise TypeError(
                "FixedSingleLoopPhysicalResidualAssembly.adapter_set must be a "
                "ComponentContributionAdapterSet; "
                f"got {type(self.adapter_set).__name__!r}"
            )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "FixedSingleLoopPhysicalResidualAssembly.metadata must be a "
                    f"Mapping or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# build_fixed_single_loop_physical_residuals
# ---------------------------------------------------------------------------


def build_fixed_single_loop_physical_residuals(
    scenario: object,
    parameters: object,
    *,
    metadata: object = None,
) -> FixedSingleLoopPhysicalResidualAssembly:
    """Build a deterministic fixed single-loop physical residual assembly.

    Creates explicit parameterized algebraic contribution adapters for the
    fixed scenario declared in Block 15B.1.  All residuals are explicit and
    parameterized; no property lookup, no correlations, no component execution.

    The factory is deterministic: calling it twice with equal scenario and
    parameters objects produces structurally identical assemblies.

    Parameters
    ----------
    scenario : FixedSingleLoopScenario
        The Block 15B.1 fixed single-loop scenario declaration.
    parameters : FixedSingleLoopResidualParameters
        Explicit scalar parameters for the residual equations.
    metadata : Mapping[str, object] | None
        Optional caller-supplied metadata; defensively copied.

    Returns
    -------
    FixedSingleLoopPhysicalResidualAssembly
        Frozen assembly with residual_map and adapter_set for evaluation.

    Raises
    ------
    TypeError
        If scenario is not a FixedSingleLoopScenario.
        If parameters is not a FixedSingleLoopResidualParameters.
        If metadata is not a Mapping or None.
    """
    if not isinstance(scenario, FixedSingleLoopScenario):
        raise TypeError(
            "build_fixed_single_loop_physical_residuals: scenario must be a "
            f"FixedSingleLoopScenario; got {type(scenario).__name__!r}"
        )
    if not isinstance(parameters, FixedSingleLoopResidualParameters):
        raise TypeError(
            "build_fixed_single_loop_physical_residuals: parameters must be a "
            f"FixedSingleLoopResidualParameters; "
            f"got {type(parameters).__name__!r}"
        )
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            "build_fixed_single_loop_physical_residuals: metadata must be a "
            f"Mapping or None; got {type(metadata).__name__!r}"
        )

    cids = scenario.component_ids
    un: FixedSingleLoopUnknownNames = scenario.unknown_names
    rn: FixedSingleLoopResidualNames = scenario.residual_names

    # Build ContributionResidualMap.
    # Contribution names "mass_balance" and "pressure_drop" per component map to
    # the assembly residual names declared in the Block 15B.1 scenario.
    residual_map = ContributionResidualMap(
        {
            (cids.accumulator, "mass_balance"): rn.mass_balance_n_cond_out,
            (cids.accumulator, "pressure_drop"): rn.pressure_drop_accumulator,
            (cids.pump, "mass_balance"): rn.mass_balance_n_acc_out,
            (cids.pump, "pressure_drop"): rn.pressure_drop_pump,
            (cids.evaporator, "mass_balance"): rn.mass_balance_n_pump_out,
            (cids.evaporator, "pressure_drop"): rn.pressure_drop_evaporator,
            (cids.condenser, "mass_balance"): rn.mass_balance_n_evap_out,
            (cids.condenser, "pressure_drop"): rn.pressure_drop_condenser,
        }
    )

    # Build contribution adapters — one per component, in scenario component order.
    # Each adapter's callback computes two residuals for its component:
    #   - one mass-balance residual at the closing node
    #   - one pressure residual from the explicit parameter
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
                instance_id=cids.evaporator,
                callback=_make_evaporator_callback(un, rn, parameters),
            ),
            ComponentContributionAdapter(
                instance_id=cids.condenser,
                callback=_make_condenser_callback(un, rn, parameters),
            ),
        )
    )

    return FixedSingleLoopPhysicalResidualAssembly(
        scenario=scenario,
        parameters=parameters,
        residual_map=residual_map,
        adapter_set=adapter_set,
        metadata=metadata,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# build_component_contribution_from_fixed_single_loop_residuals
# ---------------------------------------------------------------------------


def build_component_contribution_from_fixed_single_loop_residuals(
    component_id: object,
    assembly: object,
    unknown_values: object,
    *,
    metadata: object = None,
) -> ComponentContribution:
    """Return a Phase 14C ComponentContribution for one component.

    Thin convenience wrapper around the adapter_set in the assembly.
    Finds the adapter for component_id, builds a ComponentContributionContext
    from the scenario binding context and the supplied unknown values, calls the
    adapter callback, and returns the resulting ComponentContribution.

    This is NOT production component execution, NOT contribute(...), NOT
    SystemState assembly, NOT property lookup.  It is a direct call of the
    explicit algebraic callback registered for the requested component.

    Parameters
    ----------
    component_id : ComponentInstanceId
        ID of the component whose contribution to evaluate.
    assembly : FixedSingleLoopPhysicalResidualAssembly
        The assembled fixed-loop residual object from
        build_fixed_single_loop_physical_residuals.
    unknown_values : Mapping[str, float]
        Current unknown values keyed by unknown name string.
    metadata : Mapping[str, object] | None
        Optional metadata forwarded to the ComponentContributionContext.

    Returns
    -------
    ComponentContribution
        Phase 14C contribution result with residual_values for the requested
        component (two entries: mass_balance residual + pressure residual).

    Raises
    ------
    TypeError
        If component_id is not a ComponentInstanceId.
        If assembly is not a FixedSingleLoopPhysicalResidualAssembly.
        If unknown_values is not a Mapping.
    ValueError
        If component_id is not found in assembly.adapter_set.
    """
    if not isinstance(component_id, ComponentInstanceId):
        raise TypeError(
            "build_component_contribution_from_fixed_single_loop_residuals: "
            "component_id must be a ComponentInstanceId; "
            f"got {type(component_id).__name__!r}"
        )
    if not isinstance(assembly, FixedSingleLoopPhysicalResidualAssembly):
        raise TypeError(
            "build_component_contribution_from_fixed_single_loop_residuals: "
            "assembly must be a FixedSingleLoopPhysicalResidualAssembly; "
            f"got {type(assembly).__name__!r}"
        )
    if not isinstance(unknown_values, Mapping):
        raise TypeError(
            "build_component_contribution_from_fixed_single_loop_residuals: "
            "unknown_values must be a Mapping; "
            f"got {type(unknown_values).__name__!r}"
        )

    adapter = None
    for a in assembly.adapter_set.adapters:
        if a.instance_id == component_id:
            adapter = a
            break
    if adapter is None:
        raise ValueError(
            "build_component_contribution_from_fixed_single_loop_residuals: "
            f"no adapter found for component_id {component_id.value!r} in assembly"
        )

    ctx = ComponentContributionContext(
        binding_context=assembly.scenario.binding_context,
        unknown_values=dict(unknown_values),
        metadata=metadata,  # type: ignore[arg-type]
    )
    return adapter.callback(ctx)


# ---------------------------------------------------------------------------
# Private callback factories
# ---------------------------------------------------------------------------


def _make_accumulator_callback(
    un: FixedSingleLoopUnknownNames,
    rn: FixedSingleLoopResidualNames,
    parameters: FixedSingleLoopResidualParameters,
) -> Callable[[ComponentContributionContext], ComponentContribution]:
    """Return the contribution callback for the accumulator component.

    Residuals owned by accumulator:
        mass_balance:n_cond_out  = mdot_condenser - mdot_accumulator
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
    un: FixedSingleLoopUnknownNames,
    rn: FixedSingleLoopResidualNames,
    parameters: FixedSingleLoopResidualParameters,
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


def _make_evaporator_callback(
    un: FixedSingleLoopUnknownNames,
    rn: FixedSingleLoopResidualNames,
    parameters: FixedSingleLoopResidualParameters,
) -> Callable[[ComponentContributionContext], ComponentContribution]:
    """Return the contribution callback for the evaporator component.

    Residuals owned by evaporator:
        mass_balance:n_pump_out   = mdot_pump - mdot_evaporator
        pressure_drop:evaporator  = P_n_evap_out - P_n_pump_out + evaporator_pressure_drop
    """
    _mdot_pump = un.mdot_pump
    _mdot_evap = un.mdot_evaporator
    _P_pump_out = un.P_n_pump_out
    _P_evap_out = un.P_n_evap_out
    _r_mb = rn.mass_balance_n_pump_out
    _r_pd = rn.pressure_drop_evaporator
    _evap_drop = parameters.evaporator_pressure_drop

    def _callback(ctx: ComponentContributionContext) -> ComponentContribution:
        uv = ctx.unknown_values
        return ComponentContribution(
            residual_values={
                _r_mb: uv[_mdot_pump] - uv[_mdot_evap],
                _r_pd: uv[_P_evap_out] - uv[_P_pump_out] + _evap_drop,
            }
        )

    return _callback


def _make_condenser_callback(
    un: FixedSingleLoopUnknownNames,
    rn: FixedSingleLoopResidualNames,
    parameters: FixedSingleLoopResidualParameters,
) -> Callable[[ComponentContributionContext], ComponentContribution]:
    """Return the contribution callback for the condenser component.

    Residuals owned by condenser:
        mass_balance:n_evap_out  = mdot_evaporator - mdot_condenser
        pressure_drop:condenser  = P_n_cond_out - P_n_evap_out + condenser_pressure_drop
    """
    _mdot_evap = un.mdot_evaporator
    _mdot_cond = un.mdot_condenser
    _P_evap_out = un.P_n_evap_out
    _P_cond_out = un.P_n_cond_out
    _r_mb = rn.mass_balance_n_evap_out
    _r_pd = rn.pressure_drop_condenser
    _cond_drop = parameters.condenser_pressure_drop

    def _callback(ctx: ComponentContributionContext) -> ComponentContribution:
        uv = ctx.unknown_values
        return ComponentContribution(
            residual_values={
                _r_mb: uv[_mdot_evap] - uv[_mdot_cond],
                _r_pd: uv[_P_cond_out] - uv[_P_evap_out] + _cond_drop,
            }
        )

    return _callback
