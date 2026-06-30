"""Explicit blueprint-to-selection workflow integration — Block 15G-B.

Provides a small orchestration layer that wires Block 15G-A explicit residual
blueprints into the Block 15F-B configurable algebraic residual selection
layer.  The workflow is explicit end to end:

    explicit scenario
    + explicit residual blueprints
    + optional explicit unknown values
    -> blueprint build result (15G-A)
    -> ConfigurableResidualSelectionRequest(mode=CONFIGURABLE_ALGEBRAIC) (15F-B)
    -> explicit selection/evaluation result
    -> JSON-serializable workflow report

This module is a workflow helper, not a new physics engine.  It only
orchestrates existing 15G-A and 15F-B pieces; it does not add new residual
kinds, does not infer blueprints or residuals from roles or topology, and
does not solve.

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
MUST NOT execute production component physics.
MUST NOT infer blueprints or residuals from component roles or network topology.
MUST NOT inspect graph edges to decide blueprint or residual content.
MUST NOT create closures automatically.
MUST NOT write files or depend on pandas, matplotlib, or numpy.

Exported names
--------------
ConfigurableResidualBlueprintWorkflowRequest  — frozen workflow request
ConfigurableResidualBlueprintWorkflowResult   — frozen workflow result
build_configurable_residual_selection_from_blueprints — orchestration helper
build_configurable_residual_blueprint_workflow_report  — plain JSON-serializable report
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

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
from mpl_sim.network.configurable_residual_selection import (
    ConfigurableResidualMode,
    ConfigurableResidualSelectionRequest,
    ConfigurableResidualSelectionResult,
    build_configurable_residual_selection_report,
    select_configurable_residual_strategy,
)
from mpl_sim.network.configurable_scenarios import ConfigurableScenarioBuildResult

# ---------------------------------------------------------------------------
# Module-level limitations constant
# ---------------------------------------------------------------------------

_LIMITATIONS: tuple[str, ...] = (
    "workflow input is user-declared: scenario build result, explicit blueprints, "
    "and optional explicit unknown values",
    "no blueprints inferred from component roles",
    "no blueprints inferred from network topology",
    "no residuals inferred from component roles",
    "no residuals inferred from network topology",
    "no closures inferred from component roles",
    "evaluation occurs only when evaluate=True and explicit unknown values are supplied",
    "incompatible blueprint translations do not produce a selection request or evaluation",
    "no solve, no root-finding, no least-squares",
    "property-free; no CoolProp, PropertyBackend, or correlation calls",
    "correlation-free; no HTC, DP, friction-factor, or flow-regime logic",
    "HX-model-free; no LMTD, NTU, UA, or two-phase computations",
    "production component execution not performed",
    "SystemState not assembled; FluidState not constructed",
    "no generic network solve; no graph-based root-finding path",
)

_BLUEPRINT_DECLARATION_TYPES = (
    MassBalanceResidualBlueprint,
    PressureDifferenceResidualBlueprint,
    ImposedPressureResidualBlueprint,
    ImposedMassFlowResidualBlueprint,
    EnthalpyFlowResidualBlueprint,
)


# ---------------------------------------------------------------------------
# ConfigurableResidualBlueprintWorkflowRequest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableResidualBlueprintWorkflowRequest:
    """Frozen request for an explicit blueprint-to-selection workflow run.

    Fields
    ------
    scenario_build_result    : ConfigurableScenarioBuildResult — explicit, required
    blueprints                : ConfigurableResidualBlueprintSet
                                 | Sequence[ConfigurableResidualBlueprintDeclaration]
                                 — explicit, required
    algebraic_unknown_values  : Mapping[str, float] | None — explicit, optional
    evaluate                  : bool — defaults to False

    No evaluation is performed during request construction.  No scenario graph
    scanning is performed to create blueprints.  No role or topology inference
    is performed.  Blueprint order is preserved.  Mappings are defensively
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
                "ConfigurableResidualBlueprintWorkflowRequest.scenario_build_result "
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
                "ConfigurableResidualBlueprintWorkflowRequest.blueprints must be a "
                "ConfigurableResidualBlueprintSet or a Sequence of "
                "ConfigurableResidualBlueprintDeclaration; "
                f"got {type(bps).__name__!r}"
            )
        if not isinstance(normalized, ConfigurableResidualBlueprintSet):
            for i, bp in enumerate(normalized):
                if not isinstance(bp, _BLUEPRINT_DECLARATION_TYPES):
                    raise TypeError(
                        "ConfigurableResidualBlueprintWorkflowRequest.blueprints["
                        f"{i}] must be a ConfigurableResidualBlueprintDeclaration; "
                        f"got {type(bp).__name__!r}"
                    )
        object.__setattr__(self, "blueprints", normalized)

        if self.algebraic_unknown_values is not None:
            if not isinstance(self.algebraic_unknown_values, Mapping):
                raise TypeError(
                    "ConfigurableResidualBlueprintWorkflowRequest."
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
                "ConfigurableResidualBlueprintWorkflowRequest.evaluate must be bool; "
                f"got {type(self.evaluate).__name__!r}"
            )


# ---------------------------------------------------------------------------
# ConfigurableResidualBlueprintWorkflowResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableResidualBlueprintWorkflowResult:
    """Frozen result of an explicit blueprint-to-selection workflow run.

    Fields
    ------
    blueprint_build_result : ConfigurableResidualBlueprintBuildResult — always present
    selection_result        : ConfigurableResidualSelectionResult | None
                               — None iff the blueprint translation was not
                               compatible with the scenario build result
    selected_mode            : ConfigurableResidualMode | None
                               — None iff selection_result is None
    evaluation_performed     : bool
    deferred_or_incompatibility_reason : str — empty when evaluation was performed
    required_unknown_names   : tuple[str, ...]
    missing_unknowns         : tuple[str, ...]
    no_solve                 : bool — always True
    blueprints_inferred_from_roles    : bool — always False
    blueprints_inferred_from_topology : bool — always False
    residuals_inferred_from_roles     : bool — always False
    residuals_inferred_from_topology  : bool — always False
    closures_inferred_from_roles      : bool — always False
    production_components_executed    : bool — always False
    limitations               : tuple[str, ...]
    """

    blueprint_build_result: ConfigurableResidualBlueprintBuildResult
    selection_result: ConfigurableResidualSelectionResult | None
    selected_mode: ConfigurableResidualMode | None
    evaluation_performed: bool
    deferred_or_incompatibility_reason: str
    required_unknown_names: tuple[str, ...]
    missing_unknowns: tuple[str, ...]
    no_solve: bool
    blueprints_inferred_from_roles: bool
    blueprints_inferred_from_topology: bool
    residuals_inferred_from_roles: bool
    residuals_inferred_from_topology: bool
    closures_inferred_from_roles: bool
    production_components_executed: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.blueprint_build_result, ConfigurableResidualBlueprintBuildResult):
            raise TypeError(
                "ConfigurableResidualBlueprintWorkflowResult.blueprint_build_result "
                "must be a ConfigurableResidualBlueprintBuildResult; "
                f"got {type(self.blueprint_build_result).__name__!r}"
            )
        if self.selection_result is not None and not isinstance(
            self.selection_result, ConfigurableResidualSelectionResult
        ):
            raise TypeError(
                "ConfigurableResidualBlueprintWorkflowResult.selection_result must be "
                "a ConfigurableResidualSelectionResult or None; "
                f"got {type(self.selection_result).__name__!r}"
            )
        if self.selected_mode is not None and not isinstance(
            self.selected_mode, ConfigurableResidualMode
        ):
            raise TypeError(
                "ConfigurableResidualBlueprintWorkflowResult.selected_mode must be "
                "a ConfigurableResidualMode or None; "
                f"got {type(self.selected_mode).__name__!r}"
            )
        if self.selection_result is None and self.selected_mode is not None:
            raise ValueError(
                "ConfigurableResidualBlueprintWorkflowResult.selected_mode must be "
                "None when selection_result is None"
            )
        if not isinstance(self.no_solve, bool):
            raise TypeError("ConfigurableResidualBlueprintWorkflowResult.no_solve must be bool")
        if not self.no_solve:
            raise ValueError("ConfigurableResidualBlueprintWorkflowResult.no_solve must be True")
        for flag_name in (
            "blueprints_inferred_from_roles",
            "blueprints_inferred_from_topology",
            "residuals_inferred_from_roles",
            "residuals_inferred_from_topology",
            "closures_inferred_from_roles",
            "production_components_executed",
        ):
            val = getattr(self, flag_name)
            if not isinstance(val, bool):
                raise TypeError(
                    f"ConfigurableResidualBlueprintWorkflowResult.{flag_name} must be bool"
                )
            if val:
                raise ValueError(
                    f"ConfigurableResidualBlueprintWorkflowResult.{flag_name} must be False"
                )
        for seq_name in ("required_unknown_names", "missing_unknowns", "limitations"):
            if not isinstance(getattr(self, seq_name), tuple):
                raise TypeError(
                    f"ConfigurableResidualBlueprintWorkflowResult.{seq_name} must be a tuple"
                )
        if not isinstance(self.evaluation_performed, bool):
            raise TypeError(
                "ConfigurableResidualBlueprintWorkflowResult.evaluation_performed must be bool"
            )
        if not isinstance(self.deferred_or_incompatibility_reason, str):
            raise TypeError(
                "ConfigurableResidualBlueprintWorkflowResult."
                "deferred_or_incompatibility_reason must be a str"
            )


# ---------------------------------------------------------------------------
# build_configurable_residual_selection_from_blueprints
# ---------------------------------------------------------------------------


def build_configurable_residual_selection_from_blueprints(
    request: ConfigurableResidualBlueprintWorkflowRequest,
) -> ConfigurableResidualBlueprintWorkflowResult:
    """Build a 15G-A blueprint result and, if compatible, a 15F-B selection result.

    Steps
    -----
    1. Translate request.blueprints into a ConfigurableResidualBlueprintBuildResult
       using build_configurable_algebraic_residuals_from_blueprints, validating
       scenario compatibility against request.scenario_build_result.
    2. If the blueprint translation is not compatible with the scenario, no
       selection request is created, and no evaluation is performed.
    3. If compatible, a ConfigurableResidualSelectionRequest is created with
       mode=CONFIGURABLE_ALGEBRAIC and passed to select_configurable_residual_strategy.
       Evaluation only occurs when request.evaluate is True and the 15F-B
       selection path evaluates (which itself requires explicit unknown values).

    No residuals are inferred from roles or topology.  No closures are created
    automatically.  No solve is performed.

    Parameters
    ----------
    request : ConfigurableResidualBlueprintWorkflowRequest

    Returns
    -------
    ConfigurableResidualBlueprintWorkflowResult — frozen, immutable

    Raises
    ------
    TypeError
        If request is not a ConfigurableResidualBlueprintWorkflowRequest.
    ValueError
        If request.blueprints is empty or contains duplicate residual names
        (raised by the underlying 15G-A builder).
    """
    if not isinstance(request, ConfigurableResidualBlueprintWorkflowRequest):
        raise TypeError(
            "build_configurable_residual_selection_from_blueprints: request must be "
            "a ConfigurableResidualBlueprintWorkflowRequest; "
            f"got {type(request).__name__!r}"
        )

    blueprint_result = build_configurable_algebraic_residuals_from_blueprints(
        request.blueprints,
        scenario_build_result=request.scenario_build_result,
    )

    required_unknown_names = blueprint_result.required_unknown_names
    missing_unknowns = blueprint_result.missing_unknowns

    if not blueprint_result.scenario_is_compatible:
        reason = (
            "blueprint-translated unknowns are not fully compatible with the "
            f"scenario build result; missing_unknowns={list(missing_unknowns)!r}; "
            "no selection request was created and no evaluation was performed"
        )
        return ConfigurableResidualBlueprintWorkflowResult(
            blueprint_build_result=blueprint_result,
            selection_result=None,
            selected_mode=None,
            evaluation_performed=False,
            deferred_or_incompatibility_reason=reason,
            required_unknown_names=required_unknown_names,
            missing_unknowns=missing_unknowns,
            no_solve=True,
            blueprints_inferred_from_roles=False,
            blueprints_inferred_from_topology=False,
            residuals_inferred_from_roles=False,
            residuals_inferred_from_topology=False,
            closures_inferred_from_roles=False,
            production_components_executed=False,
            limitations=_LIMITATIONS,
        )

    selection_request = ConfigurableResidualSelectionRequest(
        build_result=request.scenario_build_result,
        mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
        algebraic_residual_set=blueprint_result.algebraic_residual_set,
        algebraic_unknown_values=request.algebraic_unknown_values,
        evaluate=request.evaluate,
    )
    selection_result = select_configurable_residual_strategy(selection_request)

    deferred_reason = (
        selection_result.evaluation_deferred_reason if selection_result.evaluation_deferred else ""
    )

    return ConfigurableResidualBlueprintWorkflowResult(
        blueprint_build_result=blueprint_result,
        selection_result=selection_result,
        selected_mode=selection_result.selected_mode,
        evaluation_performed=selection_result.evaluation_performed,
        deferred_or_incompatibility_reason=deferred_reason,
        required_unknown_names=required_unknown_names,
        missing_unknowns=missing_unknowns,
        no_solve=True,
        blueprints_inferred_from_roles=False,
        blueprints_inferred_from_topology=False,
        residuals_inferred_from_roles=False,
        residuals_inferred_from_topology=False,
        closures_inferred_from_roles=False,
        production_components_executed=False,
        limitations=_LIMITATIONS,
    )


# ---------------------------------------------------------------------------
# build_configurable_residual_blueprint_workflow_report
# ---------------------------------------------------------------------------


def build_configurable_residual_blueprint_workflow_report(
    result: ConfigurableResidualBlueprintWorkflowResult,
) -> dict[str, object]:
    """Build a plain JSON-serializable report for a workflow result.

    Composes the 15G-A blueprint build report with the 15F-B selection report
    (when a selection result was created).  Returns a plain dict with only
    JSON-serializable values (str, int, float, bool, list, dict, None).  No
    file writes.  No pandas.

    Parameters
    ----------
    result : ConfigurableResidualBlueprintWorkflowResult

    Returns
    -------
    dict[str, object] — JSON-serializable report

    Raises
    ------
    TypeError
        If result is not a ConfigurableResidualBlueprintWorkflowResult.
    """
    if not isinstance(result, ConfigurableResidualBlueprintWorkflowResult):
        raise TypeError(
            "build_configurable_residual_blueprint_workflow_report: result must be "
            "a ConfigurableResidualBlueprintWorkflowResult; "
            f"got {type(result).__name__!r}"
        )

    blueprint_report = build_configurable_residual_blueprint_report(result.blueprint_build_result)
    selection_report: dict[str, object] | None = None
    if result.selection_result is not None:
        selection_report = build_configurable_residual_selection_report(result.selection_result)

    report: dict[str, object] = {
        "status": "configurable_residual_blueprint_workflow",
        "blueprint_report": blueprint_report,
        "selection_report": selection_report,
        "selected_mode": (result.selected_mode.value if result.selected_mode is not None else None),
        "required_unknown_names": list(result.required_unknown_names),
        "missing_unknowns": list(result.missing_unknowns),
        "evaluation_performed": result.evaluation_performed,
        "deferred_or_incompatibility_reason": result.deferred_or_incompatibility_reason,
        "no_solve": True,
        "blueprints_inferred_from_roles": False,
        "blueprints_inferred_from_topology": False,
        "residuals_inferred_from_roles": False,
        "residuals_inferred_from_topology": False,
        "closures_inferred_from_roles": False,
        "production_components_executed": False,
        "limitations": list(result.limitations),
    }

    # Verify JSON-serializability before returning.
    json.dumps(report)
    return report
