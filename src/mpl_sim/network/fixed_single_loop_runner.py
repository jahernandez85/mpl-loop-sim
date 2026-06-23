"""Fixed single-loop evaluate/solve/report MVP — Block 15B.3.

Provides a narrow helper layer that evaluates residuals, optionally solves the
fixed-loop algebraic residual problem using the existing Phase 13H callback-only
solver, and returns lightweight frozen result objects.

Consumes:
  - FixedSingleLoopScenario (Block 15B.1)
  - FixedSingleLoopResidualParameters (Block 15B.2)
  - FixedSingleLoopPhysicalResidualAssembly (Block 15B.2, built internally)

This is still fixed-scenario only.  It does NOT become arbitrary-topology
simulation, generic graph solving, or real production component execution.

Note on mass-flow underdeterminacy
-----------------------------------
The fixed single-loop residual system from Block 15B.2 has 8 residuals and
8 unknowns, but the 4 mass-balance equations are linearly dependent (their
sum is identically zero for any closed loop). The common mass-flow level is
therefore underdetermined. The solve helper treats the four explicit initial
mass-flow values as a fixed gauge: they must already satisfy continuity. It
then delegates the determined pressure subsystem to the existing Phase 13H
callback-only solver and re-evaluates all 8 original residuals.

Architecture constraints enforced here
---------------------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop, or mpl_sim.solvers.
MUST NOT import CoolProp or any property engine.
MUST NOT store FluidState, SystemState, or property backend objects.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT call PropertyBackend, CorrelationRegistry, or HeatExchangerModelRegistry.
MUST NOT implement a generic network solve function or attach solve() to NetworkGraph.
MUST NOT execute production component physics.
MUST NOT infer physics from component_type.

Exported names
--------------
FixedSingleLoopEvaluationResult       — frozen residual evaluation result
FixedSingleLoopSolveRequest           — frozen solve request
FixedSingleLoopSolveResult            — frozen solve result
evaluate_fixed_single_loop_residuals  — deterministic residual evaluator
solve_fixed_single_loop_residuals     — thin wrapper over Phase 13H solver
build_fixed_single_loop_report        — simple serializable summary builder
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.contribution_adapters import build_physical_adapters_from_contributions
from mpl_sim.network.fixed_single_loop_residuals import (
    FixedSingleLoopResidualParameters,
    build_fixed_single_loop_physical_residuals,
)
from mpl_sim.network.fixed_single_loop_scenario import FixedSingleLoopScenario
from mpl_sim.network.physical_adapters import build_network_residual_evaluators
from mpl_sim.network.residual_assembly import (
    NetworkResidualAssembly,
    NetworkResidualSet,
    NetworkUnknownSet,
)
from mpl_sim.network.residual_evaluation import (
    NetworkResidualEvaluator,
    NetworkUnknownValues,
    evaluate_network_residuals,
)
from mpl_sim.network.solver import NetworkSolveConfig, solve_network_residual_problem

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_unknown_values(
    caller: str,
    scenario: FixedSingleLoopScenario,
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
            f"{caller}: unknown_values missing for declared unknowns: {sorted(missing)!r}"
        )
    extra = provided - declared
    if extra:
        raise ValueError(
            f"{caller}: unknown_values contain names not in scenario: {sorted(extra)!r}"
        )
    out: dict[str, float] = {}
    for name in scenario.unknown_names.all_names():
        val = values[name]  # type: ignore[index]
        if isinstance(val, bool):
            raise TypeError(f"{caller}: value for unknown {name!r} must not be bool; got {val!r}")
        if not isinstance(val, (int, float)):
            raise TypeError(
                f"{caller}: value for unknown {name!r} must be numeric; "
                f"got {type(val).__name__!r}"
            )
        if not math.isfinite(float(val)):
            raise ValueError(f"{caller}: value for unknown {name!r} must be finite; got {val!r}")
        out[name] = float(val)
    return out


def _build_evaluators_and_scales(
    scenario: FixedSingleLoopScenario,
    parameters: FixedSingleLoopResidualParameters,
) -> tuple:
    """Build Phase 14A evaluators and uniform unit scales for the fixed-loop system."""
    phys_assembly = build_fixed_single_loop_physical_residuals(scenario, parameters)
    physical_adapter_set = build_physical_adapters_from_contributions(
        scenario.binding_context,
        phys_assembly.adapter_set,
    )
    evaluators = build_network_residual_evaluators(scenario.assembly, physical_adapter_set)
    scales = {name: 1.0 for name in scenario.assembly.residuals.names()}
    return evaluators, scales


# ---------------------------------------------------------------------------
# FixedSingleLoopEvaluationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedSingleLoopEvaluationResult:
    """Frozen result of evaluating fixed-loop residuals at given unknown values.

    Does not contain SystemState, FluidState, property backends, or
    production component objects.

    Fields
    ------
    scenario          : Block 15B.1 FixedSingleLoopScenario
    parameters        : Block 15B.2 FixedSingleLoopResidualParameters
    unknown_values    : read-only copy of the supplied unknown values
    residual_values   : read-only residual-name → value map in declaration order
    residual_names    : tuple of residual names in scenario declaration order
    max_abs_residual  : max absolute residual (L-infinity norm, unscaled)
    l2_residual       : L2 norm of raw residual values
    metadata          : optional caller-supplied metadata; defensively copied
    """

    scenario: FixedSingleLoopScenario
    parameters: FixedSingleLoopResidualParameters
    unknown_values: MappingProxyType
    residual_values: MappingProxyType
    residual_names: tuple
    max_abs_residual: float
    l2_residual: float
    metadata: MappingProxyType | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, FixedSingleLoopScenario):
            raise TypeError(
                "FixedSingleLoopEvaluationResult.scenario must be a "
                f"FixedSingleLoopScenario; got {type(self.scenario).__name__!r}"
            )
        if not isinstance(self.parameters, FixedSingleLoopResidualParameters):
            raise TypeError(
                "FixedSingleLoopEvaluationResult.parameters must be a "
                f"FixedSingleLoopResidualParameters; got {type(self.parameters).__name__!r}"
            )
        object.__setattr__(self, "unknown_values", MappingProxyType(dict(self.unknown_values)))
        object.__setattr__(self, "residual_values", MappingProxyType(dict(self.residual_values)))
        if not isinstance(self.residual_names, tuple):
            object.__setattr__(self, "residual_names", tuple(self.residual_names))
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "FixedSingleLoopEvaluationResult.metadata must be a "
                    f"Mapping or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# FixedSingleLoopSolveRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedSingleLoopSolveRequest:
    """Frozen request for solving fixed-loop algebraic residuals.

    Does not contain physical state objects, FluidState, or SystemState.

    Fields
    ------
    scenario               : Block 15B.1 FixedSingleLoopScenario
    parameters             : Block 15B.2 FixedSingleLoopResidualParameters
    initial_unknown_values : read-only initial guess covering all 8 unknowns
    solver_config          : Phase 13H NetworkSolveConfig
    metadata               : optional caller-supplied metadata; defensively copied

    Note on underdeterminacy
    -------------------------
    The 4 initial mass-flow values act as an explicit fixed gauge for the
    underdetermined common mass-flow level and must satisfy continuity.
    """

    scenario: FixedSingleLoopScenario
    parameters: FixedSingleLoopResidualParameters
    initial_unknown_values: MappingProxyType
    solver_config: NetworkSolveConfig
    metadata: MappingProxyType | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, FixedSingleLoopScenario):
            raise TypeError(
                "FixedSingleLoopSolveRequest.scenario must be a "
                f"FixedSingleLoopScenario; got {type(self.scenario).__name__!r}"
            )
        if not isinstance(self.parameters, FixedSingleLoopResidualParameters):
            raise TypeError(
                "FixedSingleLoopSolveRequest.parameters must be a "
                f"FixedSingleLoopResidualParameters; "
                f"got {type(self.parameters).__name__!r}"
            )
        if not isinstance(self.solver_config, NetworkSolveConfig):
            raise TypeError(
                "FixedSingleLoopSolveRequest.solver_config must be a "
                f"NetworkSolveConfig; got {type(self.solver_config).__name__!r}"
            )
        # Validate and freeze initial_unknown_values.
        raw = self.initial_unknown_values
        validated = _validate_unknown_values(
            "FixedSingleLoopSolveRequest",
            self.scenario,
            raw,
        )
        object.__setattr__(self, "initial_unknown_values", MappingProxyType(validated))
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "FixedSingleLoopSolveRequest.metadata must be a "
                    f"Mapping or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# FixedSingleLoopSolveResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedSingleLoopSolveResult:
    """Frozen result of attempting to solve fixed-loop algebraic residuals.

    Always returned regardless of convergence status.  Does not contain
    FluidState, SystemState, or production component objects.

    Fields
    ------
    request                : the FixedSingleLoopSolveRequest that produced this result
    converged              : True if the solver converged; False otherwise
    reason                 : human-readable status string from the Phase 13H solver
    iteration_count        : number of Newton iterations performed
    solved_unknown_values  : final unknown values (at convergence or max iterations)
    final_residual_values  : final residual-name → value in scenario declaration order
    residual_names         : tuple of residual names in scenario declaration order
    final_max_abs_residual : max absolute residual at the final iterate
    final_l2_residual      : L2 norm of final residual values
    residual_norm_history  : max_abs_residual per iteration or None
    metadata               : optional caller-supplied metadata; defensively copied

    Note on underdeterminacy
    -------------------------
    The solved mass-flow values are the request's explicit, continuity-
    consistent mass-flow gauge. The Phase 13H solver varies only pressures.
    """

    request: FixedSingleLoopSolveRequest
    converged: bool
    reason: str
    iteration_count: int
    solved_unknown_values: MappingProxyType
    final_residual_values: MappingProxyType
    residual_names: tuple
    final_max_abs_residual: float
    final_l2_residual: float
    residual_norm_history: tuple | None = None
    metadata: MappingProxyType | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, FixedSingleLoopSolveRequest):
            raise TypeError(
                "FixedSingleLoopSolveResult.request must be a "
                f"FixedSingleLoopSolveRequest; got {type(self.request).__name__!r}"
            )
        object.__setattr__(
            self,
            "solved_unknown_values",
            MappingProxyType(dict(self.solved_unknown_values)),
        )
        object.__setattr__(
            self,
            "final_residual_values",
            MappingProxyType(dict(self.final_residual_values)),
        )
        if not isinstance(self.residual_names, tuple):
            object.__setattr__(self, "residual_names", tuple(self.residual_names))
        if self.residual_norm_history is not None and not isinstance(
            self.residual_norm_history, tuple
        ):
            object.__setattr__(self, "residual_norm_history", tuple(self.residual_norm_history))
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "FixedSingleLoopSolveResult.metadata must be a "
                    f"Mapping or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# evaluate_fixed_single_loop_residuals
# ---------------------------------------------------------------------------


def evaluate_fixed_single_loop_residuals(
    scenario: object,
    parameters: object,
    unknown_values: object,
    *,
    metadata: object = None,
) -> FixedSingleLoopEvaluationResult:
    """Evaluate all 8 fixed-loop residuals at explicit unknown values.

    Deterministic helper that:
    - validates all inputs;
    - builds the 15B.2 physical residual assembly internally;
    - evaluates residuals using existing Phase 14A/13G infrastructure;
    - returns a frozen FixedSingleLoopEvaluationResult;
    - preserves residual ordering from the scenario;
    - does not solve;
    - does not execute production components;
    - does not infer physics from component_type.

    Parameters
    ----------
    scenario : FixedSingleLoopScenario
        The Block 15B.1 fixed single-loop scenario declaration.
    parameters : FixedSingleLoopResidualParameters
        Explicit scalar parameters for the residual equations.
    unknown_values : Mapping[str, float]
        Explicit unknown values; must cover the scenario unknowns exactly.
        All values must be finite, non-bool numeric.
    metadata : Mapping[str, object] | None
        Optional caller-supplied metadata; defensively copied.

    Returns
    -------
    FixedSingleLoopEvaluationResult
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
    _CALLER = "evaluate_fixed_single_loop_residuals"

    if not isinstance(scenario, FixedSingleLoopScenario):
        raise TypeError(
            f"{_CALLER}: scenario must be a FixedSingleLoopScenario; "
            f"got {type(scenario).__name__!r}"
        )
    if not isinstance(parameters, FixedSingleLoopResidualParameters):
        raise TypeError(
            f"{_CALLER}: parameters must be a FixedSingleLoopResidualParameters; "
            f"got {type(parameters).__name__!r}"
        )
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError(
            f"{_CALLER}: metadata must be a Mapping or None; " f"got {type(metadata).__name__!r}"
        )

    validated_uv = _validate_unknown_values(_CALLER, scenario, unknown_values)

    # Build physical assembly and evaluators via existing 15B.2 → 14A → 13G path.
    evaluators, scales = _build_evaluators_and_scales(scenario, parameters)

    eval_result = evaluate_network_residuals(
        assembly=scenario.assembly,
        unknown_values=NetworkUnknownValues(values=validated_uv),
        evaluators=evaluators,
        scales=scales,
    )

    # Collect residual values in scenario declaration order.
    res_names = tuple(scenario.residual_names.all_names())
    res_values: dict[str, float] = {ev.spec.name: ev.value for ev in eval_result.evaluations}

    return FixedSingleLoopEvaluationResult(
        scenario=scenario,
        parameters=parameters,
        unknown_values=MappingProxyType(validated_uv),
        residual_values=MappingProxyType(res_values),
        residual_names=res_names,
        # scale=1.0 throughout, so scaled == raw
        max_abs_residual=eval_result.max_abs_scaled,
        l2_residual=eval_result.l2_scaled,
        metadata=metadata,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# solve_fixed_single_loop_residuals
# ---------------------------------------------------------------------------


def solve_fixed_single_loop_residuals(
    request: object,
) -> FixedSingleLoopSolveResult:
    """Solve fixed-loop algebraic residuals via the Phase 13H callback-only solver.

    Thin wrapper over solve_network_residual_problem (Phase 13H).  Returns a
    FixedSingleLoopSolveResult regardless of convergence status; never raises
    for normal solver failure.

    The fixed loop has an underdetermined common mass-flow level. The request's
    explicit initial mass-flow values are therefore held fixed and must already
    satisfy all four continuity residuals. The existing Phase 13H solver varies
    only the four pressure unknowns against the four original Block 15B.2
    pressure residual callbacks. All eight original residuals are re-evaluated
    at the returned point.

    Parameters
    ----------
    request : FixedSingleLoopSolveRequest
        Frozen solve request with scenario, parameters, initial unknown values,
        and solver configuration.

    Returns
    -------
    FixedSingleLoopSolveResult
        Always returned. Inconsistent mass-flow gauges fail clearly without
        iteration; continuity-consistent requests solve the pressure subsystem.

    Raises
    ------
    TypeError
        If request is not a FixedSingleLoopSolveRequest.
    """
    if not isinstance(request, FixedSingleLoopSolveRequest):
        raise TypeError(
            "solve_fixed_single_loop_residuals: request must be a "
            f"FixedSingleLoopSolveRequest; got {type(request).__name__!r}"
        )

    scenario = request.scenario
    evaluators, scales = _build_evaluators_and_scales(scenario, request.parameters)
    initial_values = dict(request.initial_unknown_values)
    initial_evaluation = evaluate_network_residuals(
        assembly=scenario.assembly,
        unknown_values=NetworkUnknownValues(values=initial_values),
        evaluators=evaluators,
        scales=scales,
    )

    mass_residual_names = set(scenario.residual_names.all_names()[:4])
    mass_residual_max = max(
        abs(evaluation.value)
        for evaluation in initial_evaluation.evaluations
        if evaluation.spec.name in mass_residual_names
    )
    if mass_residual_max > request.solver_config.tolerance:
        final_res_values = {
            evaluation.spec.name: evaluation.value for evaluation in initial_evaluation.evaluations
        }
        return FixedSingleLoopSolveResult(
            request=request,
            converged=False,
            reason=(
                "initial mass-flow values must satisfy fixed-loop continuity; "
                "the common mass-flow level is an explicit fixed gauge"
            ),
            iteration_count=0,
            solved_unknown_values=MappingProxyType(initial_values),
            final_residual_values=MappingProxyType(final_res_values),
            residual_names=tuple(scenario.residual_names.all_names()),
            final_max_abs_residual=initial_evaluation.max_abs_scaled,
            final_l2_residual=initial_evaluation.l2_scaled,
            residual_norm_history=() if request.solver_config.record_history else None,
            metadata=request.metadata,
        )

    pressure_unknown_names = set(scenario.unknown_names.all_names()[4:])
    pressure_residual_names = set(scenario.residual_names.all_names()[4:])
    pressure_assembly = NetworkResidualAssembly(
        unknowns=NetworkUnknownSet(
            unknowns=tuple(
                declaration
                for declaration in scenario.assembly.unknowns.unknowns
                if declaration.name in pressure_unknown_names
            )
        ),
        residuals=NetworkResidualSet(
            residuals=tuple(
                declaration
                for declaration in scenario.assembly.residuals.residuals
                if declaration.name in pressure_residual_names
            )
        ),
    )
    fixed_mass_flows = {
        name: initial_values[name] for name in scenario.unknown_names.all_names()[:4]
    }
    pressure_evaluators: list[NetworkResidualEvaluator] = []
    for evaluator in evaluators:
        if evaluator.name not in pressure_residual_names:
            continue

        def evaluate_pressure_residual(
            pressure_values: Mapping[str, float],
            *,
            callback=evaluator.callback,
        ) -> float:
            full_values = dict(fixed_mass_flows)
            full_values.update(pressure_values)
            return callback(MappingProxyType(full_values))

        pressure_evaluators.append(
            NetworkResidualEvaluator(
                name=evaluator.name,
                callback=evaluate_pressure_residual,
            )
        )

    pressure_solve_result = solve_network_residual_problem(
        assembly=pressure_assembly,
        initial_values={
            name: initial_values[name] for name in scenario.unknown_names.all_names()[4:]
        },
        evaluators=pressure_evaluators,
        scales={name: 1.0 for name in scenario.residual_names.all_names()[4:]},
        config=request.solver_config,
    )
    final_values = dict(fixed_mass_flows)
    final_values.update(pressure_solve_result.final_unknown_values.values)
    final_evaluation = evaluate_network_residuals(
        assembly=scenario.assembly,
        unknown_values=NetworkUnknownValues(values=final_values),
        evaluators=evaluators,
        scales=scales,
    )
    converged = (
        pressure_solve_result.converged
        and final_evaluation.max_abs_scaled <= request.solver_config.tolerance
    )
    reason = pressure_solve_result.reason
    if pressure_solve_result.converged and not converged:
        reason = "pressure subsystem converged but full fixed-loop residual check failed"
    res_names = tuple(scenario.residual_names.all_names())
    final_res_values = {
        evaluation.spec.name: evaluation.value for evaluation in final_evaluation.evaluations
    }

    return FixedSingleLoopSolveResult(
        request=request,
        converged=converged,
        reason=reason,
        iteration_count=pressure_solve_result.iteration_count,
        solved_unknown_values=MappingProxyType(final_values),
        final_residual_values=MappingProxyType(final_res_values),
        residual_names=res_names,
        final_max_abs_residual=final_evaluation.max_abs_scaled,
        final_l2_residual=final_evaluation.l2_scaled,
        residual_norm_history=pressure_solve_result.residual_norm_history,
        metadata=request.metadata,
    )


# ---------------------------------------------------------------------------
# build_fixed_single_loop_report
# ---------------------------------------------------------------------------


def build_fixed_single_loop_report(
    result: object,
) -> dict[str, object]:
    """Build a simple serializable summary from an evaluation or solve result.

    Returns a plain dict with scenario symbolic identifiers, unknown values,
    residual values, norms, and (if applicable) convergence status.

    Does not write files.  Does not depend on pandas, matplotlib, or numpy.
    All values in the returned dict are str, float, bool, int, list, or dict.

    Parameters
    ----------
    result : FixedSingleLoopEvaluationResult | FixedSingleLoopSolveResult
        Result from evaluate_fixed_single_loop_residuals or
        solve_fixed_single_loop_residuals.

    Returns
    -------
    dict[str, object]
        Plain serializable summary.

    Raises
    ------
    TypeError
        If result is not a FixedSingleLoopEvaluationResult or
        FixedSingleLoopSolveResult.
    """
    if isinstance(result, FixedSingleLoopEvaluationResult):
        scenario = result.scenario
        return {
            "kind": "evaluation",
            "description": (
                "Block 15B.3 fixed-loop algebraic MVP — " "not arbitrary topology simulation"
            ),
            "topology": "accumulator -> pump -> evaporator -> condenser -> accumulator",
            "component_ids": {
                "accumulator": scenario.component_ids.accumulator.value,
                "pump": scenario.component_ids.pump.value,
                "evaporator": scenario.component_ids.evaporator.value,
                "condenser": scenario.component_ids.condenser.value,
            },
            "node_ids": {
                "n_acc_out": scenario.node_ids.n_acc_out.value,
                "n_pump_out": scenario.node_ids.n_pump_out.value,
                "n_evap_out": scenario.node_ids.n_evap_out.value,
                "n_cond_out": scenario.node_ids.n_cond_out.value,
            },
            "unknown_values": dict(result.unknown_values),
            "residual_names": list(result.residual_names),
            "residual_values": dict(result.residual_values),
            "max_abs_residual": result.max_abs_residual,
            "l2_residual": result.l2_residual,
            "converged": None,
            "reason": None,
            "iteration_count": None,
        }
    if isinstance(result, FixedSingleLoopSolveResult):
        scenario = result.request.scenario
        return {
            "kind": "solve",
            "description": (
                "Block 15B.3 fixed-loop algebraic MVP — " "not arbitrary topology simulation"
            ),
            "topology": "accumulator -> pump -> evaporator -> condenser -> accumulator",
            "component_ids": {
                "accumulator": scenario.component_ids.accumulator.value,
                "pump": scenario.component_ids.pump.value,
                "evaporator": scenario.component_ids.evaporator.value,
                "condenser": scenario.component_ids.condenser.value,
            },
            "node_ids": {
                "n_acc_out": scenario.node_ids.n_acc_out.value,
                "n_pump_out": scenario.node_ids.n_pump_out.value,
                "n_evap_out": scenario.node_ids.n_evap_out.value,
                "n_cond_out": scenario.node_ids.n_cond_out.value,
            },
            "unknown_values": dict(result.solved_unknown_values),
            "residual_names": list(result.residual_names),
            "residual_values": dict(result.final_residual_values),
            "max_abs_residual": result.final_max_abs_residual,
            "l2_residual": result.final_l2_residual,
            "converged": result.converged,
            "reason": result.reason,
            "iteration_count": result.iteration_count,
        }
    raise TypeError(
        "build_fixed_single_loop_report: result must be a "
        "FixedSingleLoopEvaluationResult or FixedSingleLoopSolveResult; "
        f"got {type(result).__name__!r}"
    )
