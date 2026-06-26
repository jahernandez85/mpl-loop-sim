"""Configurable physical residual selection — Block 15E-B.

Provides an explicit, user-controlled residual-selection layer for configurable
scenario declarations.  Allows a configurable scenario to request a known
residual assembly strategy explicitly without automatic role-based physics.

Modes
-----
DECLARATION_ONLY
    Accepts any valid ConfigurableScenarioBuildResult.  Returns selected mode
    and declaration objects.  Does not evaluate physical residuals.

FIXED_SINGLE_LOOP_ALGEBRAIC
    Allowed only if the configurable scenario structurally matches the existing
    fixed single-loop MVP conventions (conventional component/node IDs in order).
    Must be explicitly requested.  May reuse existing fixed-loop evaluation-only
    API.  Does NOT call solve_fixed_single_loop_residuals.

FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC
    Allowed only if the configurable scenario structurally matches the existing
    15C fixed two-branch parallel topology conventions.  Must be explicitly
    requested.  May reuse existing evaluate_parallel_topology_residuals.  No solve.

CLOSURE_ONLY
    Allowed when an explicit CombinedClosureResidualSet is provided.  Evaluates
    only the provided closures over explicit unknown values.  Does not infer
    closures from roles.  No solve.

Architecture constraints
------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop, or mpl_sim.solvers.
MUST NOT import CoolProp or any property engine.
MUST NOT import or reference SystemState, FluidState, or PropertyBackend.
MUST NOT store FluidState, SystemState, mdot values, pressure values, or
    enthalpy values.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT call PropertyBackend, CorrelationRegistry, or HeatExchangerModelRegistry.
MUST NOT implement solve(network) or NetworkGraph.solve().
MUST NOT call solve_fixed_single_loop_residuals or any solver.
MUST NOT execute production component physics.
MUST NOT infer physics from component_type.
MUST NOT infer closures from component roles.
MUST NOT dispatch physics from role values.
MUST NOT write files or depend on pandas, matplotlib, or numpy.
MUST NOT perform least-squares, root-finding, or optimization.

Exported names
--------------
ConfigurableResidualMode               — explicit residual strategy enum (4 modes)
ConfigurableResidualSelectionRequest   — frozen selection request
ConfigurableResidualCompatibilityResult — structured compatibility check result
ConfigurableResidualSelectionResult    — frozen selection (+ optional evaluation) result
select_configurable_residual_strategy  — select mode, check compatibility, optional eval
evaluate_selected_configurable_residuals — selection with evaluation required
build_configurable_residual_selection_report — plain JSON-serializable report
"""

from __future__ import annotations

import enum
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.closure_integration import (
    CombinedClosureEvaluationResult,
    CombinedClosureResidualSet,
    evaluate_combined_closure_residuals,
)
from mpl_sim.network.configurable_scenarios import ConfigurableScenarioBuildResult
from mpl_sim.network.fixed_single_loop_residuals import FixedSingleLoopResidualParameters
from mpl_sim.network.fixed_single_loop_runner import (
    FixedSingleLoopEvaluationResult,
    evaluate_fixed_single_loop_residuals,
)
from mpl_sim.network.fixed_single_loop_scenario import build_fixed_single_loop_scenario
from mpl_sim.network.parallel_topology_residuals import (
    ParallelTopologyEvaluationResult,
    ParallelTopologyResidualParameters,
    evaluate_parallel_topology_residuals,
)
from mpl_sim.network.parallel_topology_scenario import build_parallel_topology_scenario

# ---------------------------------------------------------------------------
# Conventional ID sets for compatibility checking
# ---------------------------------------------------------------------------

_SINGLE_LOOP_COMPONENT_IDS: tuple[str, ...] = (
    "accumulator",
    "pump",
    "evaporator",
    "condenser",
)
_SINGLE_LOOP_NODE_IDS: tuple[str, ...] = (
    "n_acc_out",
    "n_pump_out",
    "n_evap_out",
    "n_cond_out",
)

_TWO_BRANCH_COMPONENT_IDS: tuple[str, ...] = (
    "accumulator",
    "pump",
    "branch_a",
    "branch_b",
    "merge_a",
    "merge_b",
    "condenser",
)
_TWO_BRANCH_NODE_IDS: tuple[str, ...] = (
    "n_acc_out",
    "n_pump_out",
    "n_a_out",
    "n_b_out",
    "n_merge_out",
    "n_cond_out",
)
_TWO_BRANCH_BRANCH_IDS: tuple[str, ...] = ("branch_a", "branch_b")

# ---------------------------------------------------------------------------
# Module-level limitations constant
# ---------------------------------------------------------------------------

_LIMITATIONS: tuple[str, ...] = (
    "residual mode must be user-requested explicitly; no automatic mode selection",
    "roles are declaration metadata only; roles did not select physics here",
    "closures not inferred automatically from component roles",
    "production component execution not performed",
    "SystemState not assembled; FluidState not constructed",
    "solve(network) and NetworkGraph.solve() not implemented",
    "not property-backed, not correlation-backed, not HX-backed",
    "fixed single-loop algebraic mode: no solve; evaluation-only path used",
    "fixed two-branch parallel algebraic mode: no solve; evaluation-only path used",
    "closure-only mode: closures must be explicitly supplied; none inferred from roles",
    "compatibility requires conventional component/node IDs in declaration order",
)


def _graph_edge_signature(
    build_result: ConfigurableScenarioBuildResult,
) -> tuple[tuple[str, str, str], ...]:
    """Return deterministic (component_id, inlet_node_id, outlet_node_id) triples."""
    return tuple(
        (
            inst.instance_id.value,
            inst.inlet_node.value,
            inst.outlet_node.value,
        )
        for inst in build_result.graph.instances()
    )


def _fixed_single_loop_edge_signature() -> tuple[tuple[str, str, str], ...]:
    scenario = build_fixed_single_loop_scenario()
    return tuple(
        (
            inst.instance_id.value,
            inst.inlet_node.value,
            inst.outlet_node.value,
        )
        for inst in scenario.graph.instances()
    )


def _fixed_two_branch_edge_signature() -> tuple[tuple[str, str, str], ...]:
    scenario = build_parallel_topology_scenario()
    return tuple(
        (
            inst.instance_id.value,
            inst.inlet_node.value,
            inst.outlet_node.value,
        )
        for inst in scenario.graph.instances()
    )


# ---------------------------------------------------------------------------
# ConfigurableResidualMode
# ---------------------------------------------------------------------------


class ConfigurableResidualMode(enum.Enum):
    """Explicit residual strategy mode for configurable scenarios.

    All four modes must be user-requested.  No mode is chosen automatically
    from component roles or from component_type.  Roles are declaration
    metadata only and do not trigger physics dispatch.

    Modes
    -----
    DECLARATION_ONLY
        Declaration objects only.  No residual evaluation.
        Compatible with any valid ConfigurableScenarioBuildResult.

    FIXED_SINGLE_LOOP_ALGEBRAIC
        Fixed single-loop algebraic residual evaluation.
        Only compatible when the configurable scenario matches the
        conventional single-loop component/node IDs in declaration order.
        Uses existing evaluate_fixed_single_loop_residuals (evaluation only,
        no solve).

    FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC
        Fixed two-branch parallel algebraic residual evaluation.
        Only compatible when the configurable scenario matches the
        conventional two-branch component/node/branch IDs in declaration order.
        Uses existing evaluate_parallel_topology_residuals (no solve).

    CLOSURE_ONLY
        Closure residual evaluation only.
        Requires an explicit CombinedClosureResidualSet supplied by the caller.
        Does not infer closures from roles.  No solve.
    """

    DECLARATION_ONLY = "declaration_only"
    FIXED_SINGLE_LOOP_ALGEBRAIC = "fixed_single_loop_algebraic"
    FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC = "fixed_two_branch_parallel_algebraic"
    CLOSURE_ONLY = "closure_only"


# ---------------------------------------------------------------------------
# ConfigurableResidualSelectionRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableResidualSelectionRequest:
    """Frozen request for configurable residual strategy selection.

    Evaluation is explicit.  Mode-specific evaluation fields may be supplied
    ahead of time, but no residual evaluation is performed unless evaluate=True.
    When evaluate=True, the fields must be consistent with the requested mode.

    Evaluation fields by mode:
      DECLARATION_ONLY:
        No evaluation fields used.  All evaluation fields are ignored.
      FIXED_SINGLE_LOOP_ALGEBRAIC:
        single_loop_parameters + single_loop_unknown_values required when
        evaluate=True.
      FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC:
        two_branch_parameters + two_branch_unknown_values required when
        evaluate=True.
      CLOSURE_ONLY:
        closure_residual_set required for compatibility.
        closure_unknown_values additionally required when evaluate=True.

    Fields
    ------
    build_result              : ConfigurableScenarioBuildResult — the scenario
    mode                      : ConfigurableResidualMode — explicitly requested mode
    single_loop_parameters    : FixedSingleLoopResidualParameters | None
    single_loop_unknown_values : Mapping[str, float] | None
    two_branch_parameters     : ParallelTopologyResidualParameters | None
    two_branch_unknown_values : Mapping[str, float] | None
    closure_residual_set      : CombinedClosureResidualSet | None
    closure_unknown_values    : Mapping[str, float] | None
    evaluate                  : bool — perform evaluation only when True
    metadata                  : Mapping[str, object] | None
    """

    build_result: ConfigurableScenarioBuildResult
    mode: ConfigurableResidualMode
    single_loop_parameters: FixedSingleLoopResidualParameters | None = None
    single_loop_unknown_values: Mapping[str, float] | None = None
    two_branch_parameters: ParallelTopologyResidualParameters | None = None
    two_branch_unknown_values: Mapping[str, float] | None = None
    closure_residual_set: CombinedClosureResidualSet | None = None
    closure_unknown_values: Mapping[str, float] | None = None
    evaluate: bool = False
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.build_result, ConfigurableScenarioBuildResult):
            raise TypeError(
                "ConfigurableResidualSelectionRequest.build_result must be a "
                "ConfigurableScenarioBuildResult; "
                f"got {type(self.build_result).__name__!r}"
            )
        if not isinstance(self.mode, ConfigurableResidualMode):
            raise TypeError(
                "ConfigurableResidualSelectionRequest.mode must be a "
                "ConfigurableResidualMode; "
                f"got {type(self.mode).__name__!r}"
            )
        if self.single_loop_parameters is not None and not isinstance(
            self.single_loop_parameters, FixedSingleLoopResidualParameters
        ):
            raise TypeError(
                "ConfigurableResidualSelectionRequest.single_loop_parameters must be "
                "a FixedSingleLoopResidualParameters or None; "
                f"got {type(self.single_loop_parameters).__name__!r}"
            )
        if self.single_loop_unknown_values is not None and not isinstance(
            self.single_loop_unknown_values, Mapping
        ):
            raise TypeError(
                "ConfigurableResidualSelectionRequest.single_loop_unknown_values must "
                "be a Mapping or None; "
                f"got {type(self.single_loop_unknown_values).__name__!r}"
            )
        if self.single_loop_unknown_values is not None:
            object.__setattr__(
                self,
                "single_loop_unknown_values",
                MappingProxyType(dict(self.single_loop_unknown_values)),
            )
        if self.two_branch_parameters is not None and not isinstance(
            self.two_branch_parameters, ParallelTopologyResidualParameters
        ):
            raise TypeError(
                "ConfigurableResidualSelectionRequest.two_branch_parameters must be "
                "a ParallelTopologyResidualParameters or None; "
                f"got {type(self.two_branch_parameters).__name__!r}"
            )
        if self.two_branch_unknown_values is not None and not isinstance(
            self.two_branch_unknown_values, Mapping
        ):
            raise TypeError(
                "ConfigurableResidualSelectionRequest.two_branch_unknown_values must "
                "be a Mapping or None; "
                f"got {type(self.two_branch_unknown_values).__name__!r}"
            )
        if self.two_branch_unknown_values is not None:
            object.__setattr__(
                self,
                "two_branch_unknown_values",
                MappingProxyType(dict(self.two_branch_unknown_values)),
            )
        if self.closure_residual_set is not None and not isinstance(
            self.closure_residual_set, CombinedClosureResidualSet
        ):
            raise TypeError(
                "ConfigurableResidualSelectionRequest.closure_residual_set must be "
                "a CombinedClosureResidualSet or None; "
                f"got {type(self.closure_residual_set).__name__!r}"
            )
        if self.closure_unknown_values is not None and not isinstance(
            self.closure_unknown_values, Mapping
        ):
            raise TypeError(
                "ConfigurableResidualSelectionRequest.closure_unknown_values must "
                "be a Mapping or None; "
                f"got {type(self.closure_unknown_values).__name__!r}"
            )
        if self.closure_unknown_values is not None:
            object.__setattr__(
                self,
                "closure_unknown_values",
                MappingProxyType(dict(self.closure_unknown_values)),
            )
        if not isinstance(self.evaluate, bool):
            raise TypeError(
                "ConfigurableResidualSelectionRequest.evaluate must be bool; "
                f"got {type(self.evaluate).__name__!r}"
            )
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ConfigurableResidualSelectionRequest.metadata must be a "
                    f"Mapping or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# ConfigurableResidualCompatibilityResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableResidualCompatibilityResult:
    """Structured result of a residual strategy compatibility check.

    Produced by the compatibility-check step inside
    select_configurable_residual_strategy.

    Fields
    ------
    is_compatible : bool              — True iff the scenario is compatible
    mode          : ConfigurableResidualMode — the checked mode
    reasons       : tuple[str, ...]   — deterministic human-readable reasons
    """

    is_compatible: bool
    mode: ConfigurableResidualMode
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.is_compatible, bool):
            raise TypeError(
                "ConfigurableResidualCompatibilityResult.is_compatible must be bool; "
                f"got {type(self.is_compatible).__name__!r}"
            )
        if not isinstance(self.mode, ConfigurableResidualMode):
            raise TypeError(
                "ConfigurableResidualCompatibilityResult.mode must be a "
                f"ConfigurableResidualMode; got {type(self.mode).__name__!r}"
            )
        reasons = self.reasons
        if not isinstance(reasons, tuple):
            object.__setattr__(self, "reasons", tuple(reasons))


# ---------------------------------------------------------------------------
# ConfigurableResidualSelectionResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableResidualSelectionResult:
    """Frozen result of configurable residual strategy selection.

    Produced by select_configurable_residual_strategy or
    evaluate_selected_configurable_residuals.

    Fields
    ------
    request              : ConfigurableResidualSelectionRequest
    compatibility        : ConfigurableResidualCompatibilityResult
    selected_mode        : ConfigurableResidualMode
    evaluation_performed : bool — True if residual evaluation was attempted
    evaluation_result    : FixedSingleLoopEvaluationResult
                           | ParallelTopologyEvaluationResult
                           | CombinedClosureEvaluationResult
                           | None
    evaluation_deferred  : bool — True if evaluation was not performed
    evaluation_deferred_reason : str — reason evaluation was deferred (or "")
    no_solve             : bool — always True; explicitly no solving
    limitations          : tuple[str, ...] — explicit limitations
    metadata             : Mapping[str, object] | None
    """

    request: ConfigurableResidualSelectionRequest
    compatibility: ConfigurableResidualCompatibilityResult
    selected_mode: ConfigurableResidualMode
    evaluation_performed: bool
    evaluation_result: (
        FixedSingleLoopEvaluationResult
        | ParallelTopologyEvaluationResult
        | CombinedClosureEvaluationResult
        | None
    )
    evaluation_deferred: bool
    evaluation_deferred_reason: str
    no_solve: bool
    limitations: tuple[str, ...]
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request, ConfigurableResidualSelectionRequest):
            raise TypeError(
                "ConfigurableResidualSelectionResult.request must be a "
                "ConfigurableResidualSelectionRequest; "
                f"got {type(self.request).__name__!r}"
            )
        if not isinstance(self.compatibility, ConfigurableResidualCompatibilityResult):
            raise TypeError(
                "ConfigurableResidualSelectionResult.compatibility must be a "
                "ConfigurableResidualCompatibilityResult; "
                f"got {type(self.compatibility).__name__!r}"
            )
        if not isinstance(self.selected_mode, ConfigurableResidualMode):
            raise TypeError(
                "ConfigurableResidualSelectionResult.selected_mode must be a "
                "ConfigurableResidualMode; "
                f"got {type(self.selected_mode).__name__!r}"
            )
        if not isinstance(self.no_solve, bool):
            raise TypeError(
                "ConfigurableResidualSelectionResult.no_solve must be bool; "
                f"got {type(self.no_solve).__name__!r}"
            )
        limitations = self.limitations
        if not isinstance(limitations, tuple):
            object.__setattr__(self, "limitations", tuple(limitations))
        md = self.metadata
        if md is not None:
            if not isinstance(md, Mapping):
                raise TypeError(
                    "ConfigurableResidualSelectionResult.metadata must be a "
                    f"Mapping or None; got {type(md).__name__!r}"
                )
            object.__setattr__(self, "metadata", MappingProxyType(dict(md)))


# ---------------------------------------------------------------------------
# Internal compatibility checkers
# ---------------------------------------------------------------------------


def _check_declaration_only_compatibility(
    build_result: ConfigurableScenarioBuildResult,
) -> ConfigurableResidualCompatibilityResult:
    """Declaration-only mode is always compatible with any valid build result."""
    return ConfigurableResidualCompatibilityResult(
        is_compatible=True,
        mode=ConfigurableResidualMode.DECLARATION_ONLY,
        reasons=(
            "declaration-only mode accepts any valid ConfigurableScenarioBuildResult",
            f"scenario_id={build_result.spec.scenario_id!r}",
            f"component_count={len(build_result.spec.components)}",
            f"node_count={len(build_result.spec.nodes)}",
        ),
    )


def _check_single_loop_compatibility(
    build_result: ConfigurableScenarioBuildResult,
) -> ConfigurableResidualCompatibilityResult:
    """Check if build_result matches the fixed single-loop conventional IDs."""
    actual_comp_ids = tuple(c.value for c in build_result.component_ids)
    actual_node_ids = tuple(n.value for n in build_result.node_ids)
    actual_edges = _graph_edge_signature(build_result)
    expected_edges = _fixed_single_loop_edge_signature()
    fixed_scenario = build_fixed_single_loop_scenario()
    expected_unknown_names = fixed_scenario.assembly.unknowns.names()
    expected_residual_names = fixed_scenario.assembly.residuals.names()

    reasons: list[str] = []

    if actual_comp_ids == _SINGLE_LOOP_COMPONENT_IDS:
        reasons.append(
            f"component IDs match single-loop convention: {list(_SINGLE_LOOP_COMPONENT_IDS)!r}"
        )
    else:
        reasons.append(
            f"component IDs do not match single-loop convention; "
            f"expected {list(_SINGLE_LOOP_COMPONENT_IDS)!r}, "
            f"got {list(actual_comp_ids)!r}"
        )

    if actual_node_ids == _SINGLE_LOOP_NODE_IDS:
        reasons.append(f"node IDs match single-loop convention: {list(_SINGLE_LOOP_NODE_IDS)!r}")
    else:
        reasons.append(
            f"node IDs do not match single-loop convention; "
            f"expected {list(_SINGLE_LOOP_NODE_IDS)!r}, "
            f"got {list(actual_node_ids)!r}"
        )

    if actual_edges == expected_edges:
        reasons.append("graph edge signature matches fixed single-loop topology")
    else:
        reasons.append(
            "graph edge signature does not match fixed single-loop topology; "
            f"expected {list(expected_edges)!r}, got {list(actual_edges)!r}"
        )

    if build_result.unknown_names == expected_unknown_names:
        reasons.append("unknown names match fixed single-loop convention")
    else:
        reasons.append(
            "unknown names do not match fixed single-loop convention; "
            f"expected {list(expected_unknown_names)!r}, "
            f"got {list(build_result.unknown_names)!r}"
        )

    if build_result.residual_names == expected_residual_names:
        reasons.append("residual names match fixed single-loop convention")
    else:
        reasons.append(
            "residual names do not match fixed single-loop convention; "
            f"expected {list(expected_residual_names)!r}, "
            f"got {list(build_result.residual_names)!r}"
        )

    is_compatible = (
        actual_comp_ids == _SINGLE_LOOP_COMPONENT_IDS
        and actual_node_ids == _SINGLE_LOOP_NODE_IDS
        and actual_edges == expected_edges
        and build_result.unknown_names == expected_unknown_names
        and build_result.residual_names == expected_residual_names
    )
    return ConfigurableResidualCompatibilityResult(
        is_compatible=is_compatible,
        mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        reasons=tuple(reasons),
    )


def _check_two_branch_compatibility(
    build_result: ConfigurableScenarioBuildResult,
) -> ConfigurableResidualCompatibilityResult:
    """Check if build_result matches the fixed two-branch parallel conventional IDs."""
    actual_comp_ids = tuple(c.value for c in build_result.component_ids)
    actual_node_ids = tuple(n.value for n in build_result.node_ids)
    actual_branch_ids = build_result.branch_ids
    actual_edges = _graph_edge_signature(build_result)
    expected_edges = _fixed_two_branch_edge_signature()
    fixed_scenario = build_parallel_topology_scenario()
    expected_unknown_names = fixed_scenario.assembly.unknowns.names()
    expected_residual_names = fixed_scenario.assembly.residuals.names()

    reasons: list[str] = []

    if actual_comp_ids == _TWO_BRANCH_COMPONENT_IDS:
        reasons.append(
            f"component IDs match two-branch convention: {list(_TWO_BRANCH_COMPONENT_IDS)!r}"
        )
    else:
        reasons.append(
            f"component IDs do not match two-branch convention; "
            f"expected {list(_TWO_BRANCH_COMPONENT_IDS)!r}, "
            f"got {list(actual_comp_ids)!r}"
        )

    if actual_node_ids == _TWO_BRANCH_NODE_IDS:
        reasons.append(f"node IDs match two-branch convention: {list(_TWO_BRANCH_NODE_IDS)!r}")
    else:
        reasons.append(
            f"node IDs do not match two-branch convention; "
            f"expected {list(_TWO_BRANCH_NODE_IDS)!r}, "
            f"got {list(actual_node_ids)!r}"
        )

    if actual_branch_ids == _TWO_BRANCH_BRANCH_IDS:
        reasons.append(f"branch IDs match two-branch convention: {list(_TWO_BRANCH_BRANCH_IDS)!r}")
    else:
        reasons.append(
            f"branch IDs do not match two-branch convention; "
            f"expected {list(_TWO_BRANCH_BRANCH_IDS)!r}, "
            f"got {list(actual_branch_ids)!r}"
        )

    if actual_edges == expected_edges:
        reasons.append("graph edge signature matches fixed two-branch topology")
    else:
        reasons.append(
            "graph edge signature does not match fixed two-branch topology; "
            f"expected {list(expected_edges)!r}, got {list(actual_edges)!r}"
        )

    if build_result.unknown_names == expected_unknown_names:
        reasons.append("unknown names match fixed two-branch convention")
    else:
        reasons.append(
            "unknown names do not match fixed two-branch convention; "
            f"expected {list(expected_unknown_names)!r}, "
            f"got {list(build_result.unknown_names)!r}"
        )

    if build_result.residual_names == expected_residual_names:
        reasons.append("residual names match fixed two-branch convention")
    else:
        reasons.append(
            "residual names do not match fixed two-branch convention; "
            f"expected {list(expected_residual_names)!r}, "
            f"got {list(build_result.residual_names)!r}"
        )

    is_compatible = (
        actual_comp_ids == _TWO_BRANCH_COMPONENT_IDS
        and actual_node_ids == _TWO_BRANCH_NODE_IDS
        and actual_branch_ids == _TWO_BRANCH_BRANCH_IDS
        and actual_edges == expected_edges
        and build_result.unknown_names == expected_unknown_names
        and build_result.residual_names == expected_residual_names
    )
    return ConfigurableResidualCompatibilityResult(
        is_compatible=is_compatible,
        mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        reasons=tuple(reasons),
    )


def _check_closure_only_compatibility(
    closure_residual_set: CombinedClosureResidualSet | None,
) -> ConfigurableResidualCompatibilityResult:
    """Closure-only mode is compatible iff an explicit closure set is provided."""
    if closure_residual_set is None:
        return ConfigurableResidualCompatibilityResult(
            is_compatible=False,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            reasons=(
                "closure_residual_set is None; closure-only mode requires an explicit "
                "CombinedClosureResidualSet supplied by the caller",
                "closures are not inferred automatically from component roles",
            ),
        )
    if not isinstance(closure_residual_set, CombinedClosureResidualSet):
        return ConfigurableResidualCompatibilityResult(
            is_compatible=False,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            reasons=(
                f"closure_residual_set must be a CombinedClosureResidualSet; "
                f"got {type(closure_residual_set).__name__!r}",
            ),
        )
    h_count = closure_residual_set.hydraulic_count
    t_count = closure_residual_set.thermal_count
    return ConfigurableResidualCompatibilityResult(
        is_compatible=True,
        mode=ConfigurableResidualMode.CLOSURE_ONLY,
        reasons=(
            "explicit CombinedClosureResidualSet provided",
            f"hydraulic closure count: {h_count}",
            f"thermal closure count: {t_count}",
            "closures were not inferred from component roles",
        ),
    )


def _check_compatibility(
    request: ConfigurableResidualSelectionRequest,
) -> ConfigurableResidualCompatibilityResult:
    """Dispatch to the appropriate compatibility checker for the requested mode."""
    mode = request.mode
    build_result = request.build_result

    if mode is ConfigurableResidualMode.DECLARATION_ONLY:
        return _check_declaration_only_compatibility(build_result)
    elif mode is ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC:
        return _check_single_loop_compatibility(build_result)
    elif mode is ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC:
        return _check_two_branch_compatibility(build_result)
    elif mode is ConfigurableResidualMode.CLOSURE_ONLY:
        return _check_closure_only_compatibility(request.closure_residual_set)
    else:
        return ConfigurableResidualCompatibilityResult(
            is_compatible=False,
            mode=mode,
            reasons=(f"unknown mode {mode!r}",),
        )


# ---------------------------------------------------------------------------
# Internal evaluation helpers
# ---------------------------------------------------------------------------


def _evaluate_single_loop(
    request: ConfigurableResidualSelectionRequest,
) -> tuple[bool, FixedSingleLoopEvaluationResult | None, bool, str]:
    """Attempt single-loop evaluation; return (performed, result, deferred, reason)."""
    params = request.single_loop_parameters
    uvs = request.single_loop_unknown_values
    if params is None or uvs is None:
        missing = []
        if params is None:
            missing.append("single_loop_parameters")
        if uvs is None:
            missing.append("single_loop_unknown_values")
        reason = (
            f"evaluation deferred: {', '.join(missing)} not provided; "
            "provide FixedSingleLoopResidualParameters and unknown_values to evaluate"
        )
        return False, None, True, reason
    scenario = build_fixed_single_loop_scenario()
    result = evaluate_fixed_single_loop_residuals(scenario, params, uvs)
    return True, result, False, ""


def _evaluate_two_branch(
    request: ConfigurableResidualSelectionRequest,
) -> tuple[bool, ParallelTopologyEvaluationResult | None, bool, str]:
    """Attempt two-branch evaluation; return (performed, result, deferred, reason)."""
    params = request.two_branch_parameters
    uvs = request.two_branch_unknown_values
    if params is None or uvs is None:
        missing = []
        if params is None:
            missing.append("two_branch_parameters")
        if uvs is None:
            missing.append("two_branch_unknown_values")
        reason = (
            f"evaluation deferred: {', '.join(missing)} not provided; "
            "provide ParallelTopologyResidualParameters and unknown_values to evaluate"
        )
        return False, None, True, reason
    scenario = build_parallel_topology_scenario()
    result = evaluate_parallel_topology_residuals(scenario, params, uvs)
    return True, result, False, ""


def _evaluate_closure_only(
    request: ConfigurableResidualSelectionRequest,
) -> tuple[bool, CombinedClosureEvaluationResult | None, bool, str]:
    """Attempt closure-only evaluation; return (performed, result, deferred, reason)."""
    closure_set = request.closure_residual_set
    uvs = request.closure_unknown_values
    if closure_set is None:
        return (
            False,
            None,
            True,
            "evaluation deferred: closure_residual_set not provided",
        )
    if uvs is None:
        return (
            False,
            None,
            True,
            "evaluation deferred: closure_unknown_values not provided; "
            "provide closure_unknown_values to evaluate closure residuals",
        )
    result = evaluate_combined_closure_residuals(closure_set, uvs)
    return True, result, False, ""


# ---------------------------------------------------------------------------
# select_configurable_residual_strategy
# ---------------------------------------------------------------------------


def select_configurable_residual_strategy(
    request: ConfigurableResidualSelectionRequest,
) -> ConfigurableResidualSelectionResult:
    """Select a residual strategy for a configurable scenario and optionally evaluate.

    Performs a deterministic compatibility check for the requested mode.
    If the scenario is compatible, request.evaluate is True, and the required
    evaluation parameters are provided, performs residual evaluation using the
    appropriate existing fixed-evaluation backend.

    No evaluation occurs during pure selection: evaluation only happens when
    request.evaluate is explicitly True.

    No closures are inferred from component roles.
    No physics is dispatched from component roles or component_type.
    No solve is performed.

    Parameters
    ----------
    request : ConfigurableResidualSelectionRequest
        Frozen request with build_result, mode, and optional evaluation params.

    Returns
    -------
    ConfigurableResidualSelectionResult
        Frozen result with compatibility, selected mode, optional evaluation
        result, and limitations.  no_solve is always True.

    Raises
    ------
    TypeError
        If request is not a ConfigurableResidualSelectionRequest.
    """
    if not isinstance(request, ConfigurableResidualSelectionRequest):
        raise TypeError(
            "select_configurable_residual_strategy: request must be a "
            "ConfigurableResidualSelectionRequest; "
            f"got {type(request).__name__!r}"
        )

    compatibility = _check_compatibility(request)
    mode = request.mode

    evaluation_performed = False
    evaluation_result: (
        FixedSingleLoopEvaluationResult
        | ParallelTopologyEvaluationResult
        | CombinedClosureEvaluationResult
        | None
    ) = None
    evaluation_deferred = False
    evaluation_deferred_reason = ""

    if compatibility.is_compatible:
        if mode is ConfigurableResidualMode.DECLARATION_ONLY:
            evaluation_deferred = True
            evaluation_deferred_reason = (
                "declaration-only mode: no residual evaluation performed by design"
            )

        elif not request.evaluate:
            evaluation_deferred = True
            evaluation_deferred_reason = (
                "evaluation deferred: request.evaluate is False; selection only"
            )

        elif mode is ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC:
            (
                evaluation_performed,
                evaluation_result,
                evaluation_deferred,
                evaluation_deferred_reason,
            ) = _evaluate_single_loop(request)

        elif mode is ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC:
            (
                evaluation_performed,
                evaluation_result,
                evaluation_deferred,
                evaluation_deferred_reason,
            ) = _evaluate_two_branch(request)

        elif mode is ConfigurableResidualMode.CLOSURE_ONLY:
            (
                evaluation_performed,
                evaluation_result,
                evaluation_deferred,
                evaluation_deferred_reason,
            ) = _evaluate_closure_only(request)
    else:
        evaluation_deferred = True
        evaluation_deferred_reason = (
            f"evaluation deferred: scenario is not compatible with mode "
            f"{mode.value!r}; see compatibility.reasons"
        )

    return ConfigurableResidualSelectionResult(
        request=request,
        compatibility=compatibility,
        selected_mode=mode,
        evaluation_performed=evaluation_performed,
        evaluation_result=evaluation_result,
        evaluation_deferred=evaluation_deferred,
        evaluation_deferred_reason=evaluation_deferred_reason,
        no_solve=True,
        limitations=_LIMITATIONS,
        metadata=request.metadata,
    )


# ---------------------------------------------------------------------------
# evaluate_selected_configurable_residuals
# ---------------------------------------------------------------------------


def evaluate_selected_configurable_residuals(
    request: ConfigurableResidualSelectionRequest,
) -> ConfigurableResidualSelectionResult:
    """Select strategy and require evaluation; raise if evaluation cannot be performed.

    Thin variant of select_configurable_residual_strategy that raises
    ValueError if evaluation was not performed (compatibility failed or
    required evaluation parameters were not provided).

    Use this when evaluation is mandatory — it makes omitted evaluation
    parameters into an explicit error rather than a silent deferral.

    Parameters
    ----------
    request : ConfigurableResidualSelectionRequest
        Frozen request.  Evaluation parameters must be provided for the
        requested mode.

    Returns
    -------
    ConfigurableResidualSelectionResult
        As from select_configurable_residual_strategy, with evaluation_performed=True.

    Raises
    ------
    TypeError
        If request is not a ConfigurableResidualSelectionRequest.
    ValueError
        If the scenario is not compatible with the requested mode.
        If evaluation parameters are not provided for the requested mode.
    """
    result = select_configurable_residual_strategy(request)
    if not result.evaluation_performed:
        reason = result.evaluation_deferred_reason or "evaluation not performed"
        if not result.compatibility.is_compatible:
            raise ValueError(
                "evaluate_selected_configurable_residuals: scenario is not compatible "
                f"with mode {request.mode.value!r}; "
                f"compatibility reasons: {list(result.compatibility.reasons)!r}"
            )
        raise ValueError(f"evaluate_selected_configurable_residuals: {reason}")
    return result


# ---------------------------------------------------------------------------
# build_configurable_residual_selection_report
# ---------------------------------------------------------------------------


def build_configurable_residual_selection_report(
    result: ConfigurableResidualSelectionResult,
) -> dict[str, object]:
    """Build a plain JSON-serializable report for a ConfigurableResidualSelectionResult.

    Returns a plain dict with only JSON-serializable values (str, int, bool,
    list, dict, None).  No file writes.  No pandas.

    The report always includes:
      - no_solve: True (explicit statement that no solve was performed)
      - roles_selected_physics: False (explicit statement that roles did not
        trigger physics dispatch)
      - closures_inferred_from_roles: False (explicit statement that no
        closures were inferred automatically from roles)

    Parameters
    ----------
    result : ConfigurableResidualSelectionResult

    Returns
    -------
    dict[str, object] — JSON-serializable report

    Raises
    ------
    TypeError
        If result is not a ConfigurableResidualSelectionResult.
    """
    if not isinstance(result, ConfigurableResidualSelectionResult):
        raise TypeError(
            "build_configurable_residual_selection_report: result must be a "
            "ConfigurableResidualSelectionResult; "
            f"got {type(result).__name__!r}"
        )

    request = result.request
    build_result = request.build_result
    spec = build_result.spec

    compatibility_report: dict[str, object] = {
        "is_compatible": result.compatibility.is_compatible,
        "mode": result.compatibility.mode.value,
        "reasons": list(result.compatibility.reasons),
    }

    eval_report: dict[str, object] = {
        "performed": result.evaluation_performed,
        "deferred": result.evaluation_deferred,
        "deferred_reason": result.evaluation_deferred_reason,
    }

    if result.evaluation_result is not None:
        eval_r = result.evaluation_result
        if isinstance(eval_r, FixedSingleLoopEvaluationResult):
            eval_report["backend"] = "fixed_single_loop"
            eval_report["residual_names"] = list(eval_r.residual_names)
            eval_report["residual_values"] = dict(eval_r.residual_values)
            eval_report["max_abs_residual"] = eval_r.max_abs_residual
            eval_report["l2_residual"] = eval_r.l2_residual
        elif isinstance(eval_r, ParallelTopologyEvaluationResult):
            eval_report["backend"] = "parallel_topology"
            eval_report["residual_names"] = list(eval_r.residual_names)
            eval_report["residual_values"] = dict(eval_r.residual_values)
            eval_report["max_abs_residual"] = eval_r.max_abs_residual
            eval_report["l2_residual"] = eval_r.l2_residual
        elif isinstance(eval_r, CombinedClosureEvaluationResult):
            eval_report["backend"] = "combined_closure"
            eval_report["hydraulic_residuals"] = dict(eval_r.hydraulic_residuals)
            eval_report["thermal_residuals"] = dict(eval_r.thermal_residuals)
            eval_report["combined_residuals"] = dict(eval_r.combined_residuals)
            eval_report["max_abs_residual"] = eval_r.max_absolute_residual
            eval_report["l2_residual_norm"] = eval_r.l2_residual_norm

    report: dict[str, object] = {
        "scenario_id": spec.scenario_id,
        "selected_mode": result.selected_mode.value,
        "no_solve": True,
        "roles_selected_physics": False,
        "closures_inferred_from_roles": False,
        "compatibility": compatibility_report,
        "evaluation": eval_report,
        "component_count": len(spec.components),
        "node_count": len(spec.nodes),
        "component_ids": [comp.component_id for comp in spec.components],
        "node_ids": [node.node_id for node in spec.nodes],
        "branch_ids": list(build_result.branch_ids),
        "component_roles": {comp.component_id: comp.role.value for comp in spec.components},
        "unknown_count": build_result.assembly.unknowns.count(),
        "unknown_names": list(build_result.unknown_names),
        "residual_count": build_result.assembly.residuals.count(),
        "residual_names": list(build_result.residual_names),
        "limitations": list(result.limitations),
    }

    # Verify JSON-serializability before returning.
    json.dumps(report)
    return report
