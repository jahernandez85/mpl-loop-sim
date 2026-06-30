"""Structural diagnostics workflow integration — Block 15H-B.

Provides a small orchestration layer that composes the Block 15G-A explicit
residual blueprint translation, the Block 15H-A structural diagnostics, and
the optional Block 15G-B blueprint-to-selection workflow:

    explicit scenario build result
    + explicit residual blueprints
    + optional explicit unknown values
    -> 15G-A blueprint build result
    -> 15H-A structural diagnostic
    -> optional 15G-B / 15F-B CONFIGURABLE_ALGEBRAIC selection/evaluation workflow
    -> unified JSON-serializable diagnostic workflow report

Structural diagnostics are used as a conservative gate before any optional
evaluation: evaluation is only attempted through the existing 15G-B workflow
helper when the blueprint translation is scenario-compatible, the caller
explicitly requested evaluation, and the 15H-A structural diagnostic reports
``evaluation_ready=True``.  Otherwise selection/evaluation is deferred with a
deterministic reason.

This module is a workflow/orchestration helper, not a new physics engine and
not a solver.  It does not assemble physical residuals, does not infer
topology or roles, and does not evaluate residuals directly — evaluation, when
attempted, is always delegated to the existing Block 15G-B workflow helper.

Architecture constraints enforced here
---------------------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop, or mpl_sim.solvers.
MUST NOT import CoolProp or any property engine.
MUST NOT store FluidState, SystemState, mdot values, pressure values, or
    enthalpy values.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT call PropertyBackend, CorrelationRegistry, or HeatExchangerModelRegistry.
MUST NOT implement solve(network) or NetworkGraph.solve().
MUST NOT call solve_fixed_single_loop_residuals, solve_network_residual_problem,
    or any solver.
MUST NOT call evaluate_configurable_algebraic_residuals or
    evaluate_selected_configurable_residuals directly; evaluation is delegated
    to build_configurable_residual_selection_from_blueprints (Block 15G-B).
MUST NOT build a Jacobian, compute rank, or call a pseudo-inverse.
MUST NOT execute production component physics.
MUST NOT infer residuals or blueprints from component roles or network topology.
MUST NOT infer closures from component roles.
MUST NOT inspect graph edges to decide residual or blueprint content.
MUST NOT write files or depend on pandas, matplotlib, or numpy.

Exported names
--------------
ConfigurableResidualDiagnosticWorkflowRequest  — frozen workflow request
ConfigurableResidualDiagnosticWorkflowResult   — frozen workflow result
build_configurable_residual_diagnostic_workflow — orchestration helper
build_configurable_residual_diagnostic_workflow_report — plain JSON-serializable report
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.network.configurable_residual_blueprint_workflows import (
    ConfigurableResidualBlueprintWorkflowRequest,
    ConfigurableResidualBlueprintWorkflowResult,
    build_configurable_residual_blueprint_workflow_report,
    build_configurable_residual_selection_from_blueprints,
)
from mpl_sim.network.configurable_residual_blueprints import (
    ConfigurableResidualBlueprintBuildResult,
    ConfigurableResidualBlueprintDeclaration,
    ConfigurableResidualBlueprintSet,
    EnthalpyFlowResidualBlueprint,
    ImposedMassFlowResidualBlueprint,
    ImposedPressureResidualBlueprint,
    MassBalanceResidualBlueprint,
    PressureDifferenceResidualBlueprint,
    build_configurable_algebraic_residuals_from_blueprints,
    build_configurable_residual_blueprint_report,
)
from mpl_sim.network.configurable_residual_diagnostics import (
    ConfigurableResidualStructuralDiagnostic,
    ResidualDeterminationStatus,
    build_configurable_residual_diagnostic_report,
    evaluate_configurable_residual_structure,
)
from mpl_sim.network.configurable_residual_selection import ConfigurableResidualMode
from mpl_sim.network.configurable_scenarios import ConfigurableScenarioBuildResult

# ---------------------------------------------------------------------------
# Module-level limitations constant
# ---------------------------------------------------------------------------

_LIMITATIONS: tuple[str, ...] = (
    "diagnostic-aware workflow integration layer; not a new physics engine",
    "composes explicit 15G-A blueprint translation, 15H-A structural "
    "diagnostics, and optional 15G-B selection/evaluation",
    "evaluation is attempted only when request.evaluate is True, the "
    "blueprint translation is scenario-compatible, and the structural "
    "diagnostic reports evaluation_ready=True",
    "otherwise selection/evaluation is deferred with a deterministic reason",
    "does not evaluate residuals directly in this module",
    "does not call evaluate_configurable_algebraic_residuals or "
    "evaluate_selected_configurable_residuals directly; evaluation is "
    "delegated to the existing 15G-B workflow helper",
    "does not build a Jacobian, compute rank, or call a pseudo-inverse",
    "does not call least-squares, root-finding, minimization, or " "linear-algebra solvers",
    "does not infer residuals from component roles",
    "does not infer residuals from network topology",
    "does not infer blueprints from component roles or network topology",
    "does not infer closures from component roles",
    "structurally square is a count diagnostic only; it does not imply "
    "numerical rank, solvability, or physical predictiveness",
    "no_solve is always True; solve_ready is always False",
    "property-free; no CoolProp, PropertyBackend, or correlation calls",
    "correlation-free; no HTC, DP, friction-factor, or flow-regime logic",
    "HX-model-free; no LMTD, NTU, UA, or two-phase computations",
    "production component execution not performed",
    "SystemState not assembled; FluidState not constructed",
)

_BLUEPRINT_DECLARATION_TYPES = (
    MassBalanceResidualBlueprint,
    PressureDifferenceResidualBlueprint,
    ImposedPressureResidualBlueprint,
    ImposedMassFlowResidualBlueprint,
    EnthalpyFlowResidualBlueprint,
)


# ---------------------------------------------------------------------------
# ConfigurableResidualDiagnosticWorkflowRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableResidualDiagnosticWorkflowRequest:
    """Frozen request for an explicit diagnostic-aware workflow run.

    Fields
    ------
    scenario_build_result    : ConfigurableScenarioBuildResult — explicit, required
    blueprints                : ConfigurableResidualBlueprintSet
                                 | Sequence[ConfigurableResidualBlueprintDeclaration]
                                 — explicit, required
    algebraic_unknown_values  : Mapping[str, float] | None — explicit, optional
    evaluate                  : bool — defaults to False

    No build, diagnostic, evaluation, or solve step is performed during
    request construction.  No scenario graph topology or component role is
    inspected.  Blueprint order is preserved.  Mappings are defensively
    copied.
    """

    scenario_build_result: ConfigurableScenarioBuildResult
    blueprints: (
        ConfigurableResidualBlueprintSet | Sequence[ConfigurableResidualBlueprintDeclaration]
    )
    algebraic_unknown_values: Mapping[str, float] | None = None
    evaluate: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_build_result, ConfigurableScenarioBuildResult):
            raise TypeError(
                "ConfigurableResidualDiagnosticWorkflowRequest.scenario_build_result "
                "must be a ConfigurableScenarioBuildResult; "
                f"got {type(self.scenario_build_result).__name__!r}"
            )

        bps = self.blueprints
        normalized: (
            ConfigurableResidualBlueprintSet | tuple[ConfigurableResidualBlueprintDeclaration, ...]
        )
        if isinstance(bps, ConfigurableResidualBlueprintSet):
            normalized = bps
        elif isinstance(bps, (tuple, list)):
            normalized = tuple(bps)
        elif hasattr(bps, "__iter__") and not isinstance(bps, (str, bytes)):
            normalized = tuple(bps)
        else:
            raise TypeError(
                "ConfigurableResidualDiagnosticWorkflowRequest.blueprints must be a "
                "ConfigurableResidualBlueprintSet or a Sequence of "
                "ConfigurableResidualBlueprintDeclaration; "
                f"got {type(bps).__name__!r}"
            )
        if not isinstance(normalized, ConfigurableResidualBlueprintSet):
            for i, bp in enumerate(normalized):
                if not isinstance(bp, _BLUEPRINT_DECLARATION_TYPES):
                    raise TypeError(
                        "ConfigurableResidualDiagnosticWorkflowRequest.blueprints["
                        f"{i}] must be a ConfigurableResidualBlueprintDeclaration; "
                        f"got {type(bp).__name__!r}"
                    )
        object.__setattr__(self, "blueprints", normalized)

        if self.algebraic_unknown_values is not None:
            if not isinstance(self.algebraic_unknown_values, Mapping):
                raise TypeError(
                    "ConfigurableResidualDiagnosticWorkflowRequest."
                    "algebraic_unknown_values must be a Mapping or None; "
                    f"got {type(self.algebraic_unknown_values).__name__!r}"
                )
            object.__setattr__(
                self,
                "algebraic_unknown_values",
                MappingProxyType(dict(self.algebraic_unknown_values)),
            )

        if not isinstance(self.evaluate, bool):
            raise TypeError(
                "ConfigurableResidualDiagnosticWorkflowRequest.evaluate must be bool; "
                f"got {type(self.evaluate).__name__!r}"
            )


# ---------------------------------------------------------------------------
# ConfigurableResidualDiagnosticWorkflowResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableResidualDiagnosticWorkflowResult:
    """Frozen result of an explicit diagnostic-aware workflow run.

    Fields
    ------
    blueprint_build_result    : ConfigurableResidualBlueprintBuildResult — always present
    structural_diagnostic      : ConfigurableResidualStructuralDiagnostic | None
                                  — None iff the blueprint translation was not
                                  compatible with the scenario build result
    selection_workflow_result  : ConfigurableResidualBlueprintWorkflowResult | None
                                  — None unless the 15G-B workflow was invoked
    selection_requested        : bool — blueprint compatible and evaluate=True
    selection_performed        : bool — the 15G-B workflow was invoked and
                                  produced a selection result
    evaluation_requested       : bool — request.evaluate, unconditionally
    evaluation_ready           : bool — diagnostic.evaluation_ready, or False
                                  when no diagnostic was produced
    evaluation_performed       : bool
    deferred_reason             : str — empty when evaluation was performed
    selected_mode               : ConfigurableResidualMode | None
                                  — None unless selection_performed is True
    required_unknown_names      : tuple[str, ...]
    missing_from_scenario       : tuple[str, ...]
    missing_from_values         : tuple[str, ...]
    determination_status        : ResidualDeterminationStatus | None
                                  — None iff no diagnostic was produced
    solve_ready                 : bool — always False
    no_solve                    : bool — always True
    residuals_inferred_from_roles     : bool — always False
    residuals_inferred_from_topology  : bool — always False
    blueprints_inferred_from_roles    : bool — always False
    blueprints_inferred_from_topology : bool — always False
    closures_inferred_from_roles      : bool — always False
    production_components_executed    : bool — always False
    limitations                 : tuple[str, ...]
    """

    blueprint_build_result: ConfigurableResidualBlueprintBuildResult
    structural_diagnostic: ConfigurableResidualStructuralDiagnostic | None
    selection_workflow_result: ConfigurableResidualBlueprintWorkflowResult | None
    selection_requested: bool
    selection_performed: bool
    evaluation_requested: bool
    evaluation_ready: bool
    evaluation_performed: bool
    deferred_reason: str
    selected_mode: ConfigurableResidualMode | None
    required_unknown_names: tuple[str, ...]
    missing_from_scenario: tuple[str, ...]
    missing_from_values: tuple[str, ...]
    determination_status: ResidualDeterminationStatus | None
    solve_ready: bool
    no_solve: bool
    residuals_inferred_from_roles: bool
    residuals_inferred_from_topology: bool
    blueprints_inferred_from_roles: bool
    blueprints_inferred_from_topology: bool
    closures_inferred_from_roles: bool
    production_components_executed: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.blueprint_build_result, ConfigurableResidualBlueprintBuildResult):
            raise TypeError(
                "ConfigurableResidualDiagnosticWorkflowResult.blueprint_build_result "
                "must be a ConfigurableResidualBlueprintBuildResult; "
                f"got {type(self.blueprint_build_result).__name__!r}"
            )
        if self.structural_diagnostic is not None and not isinstance(
            self.structural_diagnostic, ConfigurableResidualStructuralDiagnostic
        ):
            raise TypeError(
                "ConfigurableResidualDiagnosticWorkflowResult.structural_diagnostic "
                "must be a ConfigurableResidualStructuralDiagnostic or None; "
                f"got {type(self.structural_diagnostic).__name__!r}"
            )
        if self.selection_workflow_result is not None and not isinstance(
            self.selection_workflow_result, ConfigurableResidualBlueprintWorkflowResult
        ):
            raise TypeError(
                "ConfigurableResidualDiagnosticWorkflowResult.selection_workflow_result "
                "must be a ConfigurableResidualBlueprintWorkflowResult or None; "
                f"got {type(self.selection_workflow_result).__name__!r}"
            )
        if self.selected_mode is not None and not isinstance(
            self.selected_mode, ConfigurableResidualMode
        ):
            raise TypeError(
                "ConfigurableResidualDiagnosticWorkflowResult.selected_mode must be "
                "a ConfigurableResidualMode or None; "
                f"got {type(self.selected_mode).__name__!r}"
            )
        if not self.selection_performed and self.selected_mode is not None:
            raise ValueError(
                "ConfigurableResidualDiagnosticWorkflowResult.selected_mode must be "
                "None when selection_performed is False"
            )
        if self.determination_status is not None and not isinstance(
            self.determination_status, ResidualDeterminationStatus
        ):
            raise TypeError(
                "ConfigurableResidualDiagnosticWorkflowResult.determination_status must "
                "be a ResidualDeterminationStatus or None; "
                f"got {type(self.determination_status).__name__!r}"
            )
        if (self.structural_diagnostic is None) != (self.determination_status is None):
            raise ValueError(
                "ConfigurableResidualDiagnosticWorkflowResult.structural_diagnostic and "
                "determination_status must both be None or both be set"
            )
        if not isinstance(self.solve_ready, bool):
            raise TypeError("ConfigurableResidualDiagnosticWorkflowResult.solve_ready must be bool")
        if self.solve_ready:
            raise ValueError(
                "ConfigurableResidualDiagnosticWorkflowResult.solve_ready must be False"
            )
        if not isinstance(self.no_solve, bool):
            raise TypeError("ConfigurableResidualDiagnosticWorkflowResult.no_solve must be bool")
        if not self.no_solve:
            raise ValueError("ConfigurableResidualDiagnosticWorkflowResult.no_solve must be True")
        for flag_name in (
            "residuals_inferred_from_roles",
            "residuals_inferred_from_topology",
            "blueprints_inferred_from_roles",
            "blueprints_inferred_from_topology",
            "closures_inferred_from_roles",
            "production_components_executed",
        ):
            val = getattr(self, flag_name)
            if not isinstance(val, bool):
                raise TypeError(
                    f"ConfigurableResidualDiagnosticWorkflowResult.{flag_name} must be bool"
                )
            if val:
                raise ValueError(
                    f"ConfigurableResidualDiagnosticWorkflowResult.{flag_name} must be False"
                )
        for bool_name in (
            "selection_requested",
            "selection_performed",
            "evaluation_requested",
            "evaluation_ready",
            "evaluation_performed",
        ):
            if not isinstance(getattr(self, bool_name), bool):
                raise TypeError(
                    f"ConfigurableResidualDiagnosticWorkflowResult.{bool_name} must be bool"
                )
        for seq_name in (
            "required_unknown_names",
            "missing_from_scenario",
            "missing_from_values",
            "limitations",
        ):
            if not isinstance(getattr(self, seq_name), tuple):
                raise TypeError(
                    f"ConfigurableResidualDiagnosticWorkflowResult.{seq_name} must be a tuple"
                )
        if not isinstance(self.deferred_reason, str):
            raise TypeError(
                "ConfigurableResidualDiagnosticWorkflowResult.deferred_reason must be a str"
            )


# ---------------------------------------------------------------------------
# build_configurable_residual_diagnostic_workflow
# ---------------------------------------------------------------------------


def build_configurable_residual_diagnostic_workflow(
    request: ConfigurableResidualDiagnosticWorkflowRequest,
) -> ConfigurableResidualDiagnosticWorkflowResult:
    """Build a 15G-A blueprint result, run 15H-A diagnostics, and optionally evaluate.

    Steps
    -----
    1. Translate request.blueprints into a ConfigurableResidualBlueprintBuildResult
       using build_configurable_algebraic_residuals_from_blueprints, validating
       scenario compatibility against request.scenario_build_result.
    2. If the blueprint translation is not compatible with the scenario, no
       structural diagnostic and no selection workflow result are created.
    3. If compatible, run evaluate_configurable_residual_structure on the
       translated algebraic residual set, the same scenario build result, and
       the optional explicit unknown values.
    4. If request.evaluate is False, return diagnostics only.
    5. If request.evaluate is True and the structural diagnostic reports
       evaluation_ready=True, delegate to the existing 15G-B workflow helper
       (build_configurable_residual_selection_from_blueprints) for
       selection/evaluation.
    6. If request.evaluate is True but evaluation_ready is False, defer
       selection/evaluation with a deterministic reason; the 15G-B workflow
       helper is not invoked.

    No residuals are evaluated directly in this function.  No Jacobian, rank,
    or solve is computed.  No residuals are inferred from roles or topology.

    Parameters
    ----------
    request : ConfigurableResidualDiagnosticWorkflowRequest

    Returns
    -------
    ConfigurableResidualDiagnosticWorkflowResult — frozen, immutable

    Raises
    ------
    TypeError
        If request is not a ConfigurableResidualDiagnosticWorkflowRequest.
    ValueError
        If request.blueprints is empty or contains duplicate residual names
        (raised by the underlying 15G-A builder).
    """
    if not isinstance(request, ConfigurableResidualDiagnosticWorkflowRequest):
        raise TypeError(
            "build_configurable_residual_diagnostic_workflow: request must be "
            "a ConfigurableResidualDiagnosticWorkflowRequest; "
            f"got {type(request).__name__!r}"
        )

    blueprint_result = build_configurable_algebraic_residuals_from_blueprints(
        request.blueprints,
        scenario_build_result=request.scenario_build_result,
    )

    required_unknown_names = blueprint_result.required_unknown_names

    if not blueprint_result.scenario_is_compatible:
        reason = (
            "blueprint-translated unknowns are not fully compatible with the "
            f"scenario build result; missing_unknowns="
            f"{list(blueprint_result.missing_unknowns)!r}; structural diagnostics "
            "and selection/evaluation were not attempted"
        )
        return ConfigurableResidualDiagnosticWorkflowResult(
            blueprint_build_result=blueprint_result,
            structural_diagnostic=None,
            selection_workflow_result=None,
            selection_requested=False,
            selection_performed=False,
            evaluation_requested=bool(request.evaluate),
            evaluation_ready=False,
            evaluation_performed=False,
            deferred_reason=reason,
            selected_mode=None,
            required_unknown_names=required_unknown_names,
            missing_from_scenario=blueprint_result.missing_unknowns,
            missing_from_values=(),
            determination_status=None,
            solve_ready=False,
            no_solve=True,
            residuals_inferred_from_roles=False,
            residuals_inferred_from_topology=False,
            blueprints_inferred_from_roles=False,
            blueprints_inferred_from_topology=False,
            closures_inferred_from_roles=False,
            production_components_executed=False,
            limitations=_LIMITATIONS,
        )

    diagnostic = evaluate_configurable_residual_structure(
        blueprint_result.algebraic_residual_set,
        scenario_build_result=request.scenario_build_result,
        unknown_values=request.algebraic_unknown_values,
    )

    selection_requested = bool(request.evaluate)
    selection_workflow_result: ConfigurableResidualBlueprintWorkflowResult | None = None
    selection_performed = False
    evaluation_performed = False
    selected_mode: ConfigurableResidualMode | None = None

    if not request.evaluate:
        deferred_reason = (
            "evaluation not requested: request.evaluate is False; " "structural diagnostics only"
        )
    elif not diagnostic.evaluation_ready:
        if diagnostic.unknown_values_complete is None:
            value_reason = "explicit unknown values were not supplied"
        else:
            value_reason = f"missing_from_values={list(diagnostic.missing_from_values)!r}"
        deferred_reason = (
            "evaluation deferred: structural diagnostic reports "
            "evaluation_ready=False; "
            f"missing_from_scenario={list(diagnostic.missing_from_scenario)!r}; "
            f"{value_reason}; "
            "the 15G-B selection/evaluation workflow was not invoked"
        )
    else:
        workflow_request = ConfigurableResidualBlueprintWorkflowRequest(
            scenario_build_result=request.scenario_build_result,
            blueprints=request.blueprints,
            algebraic_unknown_values=request.algebraic_unknown_values,
            evaluate=True,
        )
        selection_workflow_result = build_configurable_residual_selection_from_blueprints(
            workflow_request
        )
        selection_performed = selection_workflow_result.selection_result is not None
        evaluation_performed = selection_workflow_result.evaluation_performed
        selected_mode = selection_workflow_result.selected_mode if selection_performed else None
        deferred_reason = (
            ""
            if evaluation_performed
            else selection_workflow_result.deferred_or_incompatibility_reason
        )

    return ConfigurableResidualDiagnosticWorkflowResult(
        blueprint_build_result=blueprint_result,
        structural_diagnostic=diagnostic,
        selection_workflow_result=selection_workflow_result,
        selection_requested=selection_requested,
        selection_performed=selection_performed,
        evaluation_requested=bool(request.evaluate),
        evaluation_ready=diagnostic.evaluation_ready,
        evaluation_performed=evaluation_performed,
        deferred_reason=deferred_reason,
        selected_mode=selected_mode,
        required_unknown_names=diagnostic.required_unknown_names,
        missing_from_scenario=diagnostic.missing_from_scenario,
        missing_from_values=diagnostic.missing_from_values,
        determination_status=diagnostic.determination_status,
        solve_ready=False,
        no_solve=True,
        residuals_inferred_from_roles=False,
        residuals_inferred_from_topology=False,
        blueprints_inferred_from_roles=False,
        blueprints_inferred_from_topology=False,
        closures_inferred_from_roles=False,
        production_components_executed=False,
        limitations=_LIMITATIONS,
    )


# ---------------------------------------------------------------------------
# build_configurable_residual_diagnostic_workflow_report
# ---------------------------------------------------------------------------


def build_configurable_residual_diagnostic_workflow_report(
    result: ConfigurableResidualDiagnosticWorkflowResult,
) -> dict[str, object]:
    """Build a plain JSON-serializable report for a diagnostic workflow result.

    Composes the 15G-A blueprint build report, the 15H-A structural
    diagnostic report (when available), and the 15G-B selection workflow
    report (when a selection workflow was invoked).  Returns a plain dict
    with only JSON-serializable values (str, int, float, bool, list, dict,
    None).  No file writes.  No pandas.

    Parameters
    ----------
    result : ConfigurableResidualDiagnosticWorkflowResult

    Returns
    -------
    dict[str, object] — JSON-serializable report

    Raises
    ------
    TypeError
        If result is not a ConfigurableResidualDiagnosticWorkflowResult.
    """
    if not isinstance(result, ConfigurableResidualDiagnosticWorkflowResult):
        raise TypeError(
            "build_configurable_residual_diagnostic_workflow_report: result must be "
            "a ConfigurableResidualDiagnosticWorkflowResult; "
            f"got {type(result).__name__!r}"
        )

    blueprint_report = build_configurable_residual_blueprint_report(result.blueprint_build_result)

    diagnostic_report: dict[str, object] | None = None
    if result.structural_diagnostic is not None:
        diagnostic_report = build_configurable_residual_diagnostic_report(
            result.structural_diagnostic
        )

    selection_report: dict[str, object] | None = None
    if result.selection_workflow_result is not None:
        selection_report = build_configurable_residual_blueprint_workflow_report(
            result.selection_workflow_result
        )

    report: dict[str, object] = {
        "status": "configurable_residual_diagnostic_workflow",
        "blueprint_report": blueprint_report,
        "diagnostic_report": diagnostic_report,
        "selection_report": selection_report,
        "selection_requested": result.selection_requested,
        "selection_performed": result.selection_performed,
        "evaluation_requested": result.evaluation_requested,
        "evaluation_ready": result.evaluation_ready,
        "evaluation_performed": result.evaluation_performed,
        "deferred_reason": result.deferred_reason,
        "selected_mode": (result.selected_mode.value if result.selected_mode is not None else None),
        "required_unknown_names": list(result.required_unknown_names),
        "missing_from_scenario": list(result.missing_from_scenario),
        "missing_from_values": list(result.missing_from_values),
        "determination_status": (
            result.determination_status.value if result.determination_status is not None else None
        ),
        "solve_ready": False,
        "no_solve": True,
        "residuals_inferred_from_roles": False,
        "residuals_inferred_from_topology": False,
        "blueprints_inferred_from_roles": False,
        "blueprints_inferred_from_topology": False,
        "closures_inferred_from_roles": False,
        "production_components_executed": False,
        "limitations": list(result.limitations),
    }

    # Verify JSON-serializability before returning.
    json.dumps(report)
    return report
