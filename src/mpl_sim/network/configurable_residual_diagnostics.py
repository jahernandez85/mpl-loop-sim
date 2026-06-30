"""Explicit residual/unknown structural diagnostics — Block 15H-A.

Provides structural bookkeeping diagnostics over an explicit
``ConfigurableAlgebraicResidualSet`` (Block 15F-A), with optional explicit
``ConfigurableScenarioBuildResult`` (Block 15E-A) and optional explicit
unknown-value mappings.  Diagnostics answer purely structural questions:

* Which unknowns are required by the residual declarations?
* Which required unknowns are missing from the scenario declaration?
* Which required unknowns are missing from supplied unknown values?
* Which supplied unknown values are extra?
* How many residuals and required unknowns exist?
* Is the system structurally square, underdetermined, or overdetermined?
* Is it ready for explicit residual evaluation?
* Is it ready for solve? (Always no, in this MVP.)

This module is structural bookkeeping only.  It is not a solver.  It does
not assemble physical residuals.  It does not infer topology or roles.

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
MUST NOT infer residuals from component roles or network topology.
MUST NOT infer blueprints or closures from component roles or network topology.
MUST NOT inspect graph edges to decide residual content.
MUST NOT compute a numerical Jacobian, rank, or any linear-algebra solve.
MUST NOT write files or depend on pandas, matplotlib, or numpy.

Exported names
--------------
ResidualDeterminationStatus              — count-based structural status enum
ConfigurableResidualStructuralDiagnostic — frozen diagnostic result
evaluate_configurable_residual_structure — diagnostic factory function
build_configurable_residual_diagnostic_report — plain JSON-serializable report
"""

from __future__ import annotations

import enum
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass

from mpl_sim.network.configurable_algebraic_residuals import (
    ConfigurableAlgebraicResidualSet,
)
from mpl_sim.network.configurable_scenarios import ConfigurableScenarioBuildResult

# ---------------------------------------------------------------------------
# Module-level limitations constant
# ---------------------------------------------------------------------------

_LIMITATIONS: tuple[str, ...] = (
    "structural bookkeeping only; counts and names, not numerical analysis",
    "does not evaluate residual values",
    "does not solve; solve_ready is always False",
    "does not build, rank, or factor a Jacobian",
    "does not call least-squares, root-finding, minimization, or linear-algebra " "solvers",
    "does not infer residuals from component roles",
    "does not infer residuals from network topology",
    "does not infer blueprints from component roles or network topology",
    "does not infer closures from component roles",
    "does not create residual declarations or unknown values",
    "structurally square is a count diagnostic only; it does not imply "
    "numerical rank, solvability, or physical predictiveness",
    "property-free; no CoolProp, PropertyBackend, or correlation calls",
    "correlation-free; no HTC, DP, friction-factor, or flow-regime logic",
    "HX-model-free; no LMTD, NTU, UA, or two-phase computations",
    "production component execution not performed",
    "SystemState not assembled; FluidState not constructed",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_supplied_value_types(unknown_values: Mapping[str, object]) -> dict[str, float]:
    """Defensively copy and validate every supplied unknown value.

    Rejects bool, non-numeric, NaN, and infinite values for ALL supplied
    entries (not only required ones), consistent with Block 15F-A scalar
    validation expectations.  Does not check coverage against required names.
    """
    result: dict[str, float] = {}
    for name, raw in unknown_values.items():
        if not isinstance(name, str) or not name.strip():
            raise TypeError(
                "evaluate_configurable_residual_structure: unknown_values keys "
                f"must be non-empty str; got {name!r}"
            )
        if isinstance(raw, bool):
            raise TypeError(
                f"evaluate_configurable_residual_structure: unknown_values[{name!r}] "
                "must be a finite float, not bool"
            )
        if not isinstance(raw, (int, float)):
            raise TypeError(
                f"evaluate_configurable_residual_structure: unknown_values[{name!r}] "
                f"must be a finite float; got {type(raw).__name__!r}"
            )
        v = float(raw)
        if not math.isfinite(v):
            raise ValueError(
                f"evaluate_configurable_residual_structure: unknown_values[{name!r}] "
                f"must be finite; got {raw!r}"
            )
        result[name] = v
    return result


# ---------------------------------------------------------------------------
# ResidualDeterminationStatus
# ---------------------------------------------------------------------------


class ResidualDeterminationStatus(enum.Enum):
    """Count-based structural determination status.

    This is a simple count comparison between residual_count and
    required_unknown_count.  It does NOT claim numerical rank, solvability,
    or physical predictiveness.

    Values
    ------
    SQUARE          — residual_count == required_unknown_count
    UNDERDETERMINED — residual_count < required_unknown_count
    OVERDETERMINED  — residual_count > required_unknown_count
    """

    SQUARE = "square"
    UNDERDETERMINED = "underdetermined"
    OVERDETERMINED = "overdetermined"


# ---------------------------------------------------------------------------
# ConfigurableResidualStructuralDiagnostic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableResidualStructuralDiagnostic:
    """Frozen structural diagnostic result for an explicit residual set.

    Built by ``evaluate_configurable_residual_structure``.  Carries only
    names, counts, and boolean compatibility flags — no physical values, no
    solved values, no Jacobian, no rank.

    Fields
    ------
    residual_names           : tuple[str, ...]       — from the residual set
    required_unknown_names   : tuple[str, ...]       — from the residual set
    residual_count           : int
    required_unknown_count   : int
    determination_status     : ResidualDeterminationStatus
    scenario_unknown_names   : tuple[str, ...] | None — None iff scenario omitted
    missing_from_scenario    : tuple[str, ...]       — sorted, empty if not checked
    extra_scenario_unknowns  : tuple[str, ...]       — sorted, empty if not checked
    scenario_compatible      : bool | None           — None iff scenario omitted
    supplied_unknown_names   : tuple[str, ...] | None — None iff unknown_values omitted
    missing_from_values      : tuple[str, ...]       — sorted, empty if not checked
    extra_supplied_unknowns  : tuple[str, ...]       — sorted, empty if not checked
    unknown_values_complete  : bool | None           — None iff unknown_values omitted
    evaluation_ready         : bool
    solve_ready               : bool — always False
    no_solve                  : bool — always True
    residuals_inferred_from_roles     : bool — always False
    residuals_inferred_from_topology  : bool — always False
    blueprints_inferred_from_roles    : bool — always False
    blueprints_inferred_from_topology : bool — always False
    closures_inferred_from_roles      : bool — always False
    production_components_executed    : bool — always False
    limitations                : tuple[str, ...]
    """

    residual_names: tuple[str, ...]
    required_unknown_names: tuple[str, ...]
    residual_count: int
    required_unknown_count: int
    determination_status: ResidualDeterminationStatus
    scenario_unknown_names: tuple[str, ...] | None
    missing_from_scenario: tuple[str, ...]
    extra_scenario_unknowns: tuple[str, ...]
    scenario_compatible: bool | None
    supplied_unknown_names: tuple[str, ...] | None
    missing_from_values: tuple[str, ...]
    extra_supplied_unknowns: tuple[str, ...]
    unknown_values_complete: bool | None
    evaluation_ready: bool
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
        for tuple_field in ("residual_names", "required_unknown_names"):
            val = getattr(self, tuple_field)
            if not isinstance(val, tuple):
                raise TypeError(
                    f"ConfigurableResidualStructuralDiagnostic.{tuple_field} must be a tuple"
                )

        if not isinstance(self.residual_count, int) or isinstance(self.residual_count, bool):
            raise TypeError("ConfigurableResidualStructuralDiagnostic.residual_count must be int")
        if self.residual_count != len(self.residual_names):
            raise ValueError(
                "ConfigurableResidualStructuralDiagnostic.residual_count must equal "
                "len(residual_names)"
            )
        if not isinstance(self.required_unknown_count, int) or isinstance(
            self.required_unknown_count, bool
        ):
            raise TypeError(
                "ConfigurableResidualStructuralDiagnostic.required_unknown_count must be int"
            )
        if self.required_unknown_count != len(self.required_unknown_names):
            raise ValueError(
                "ConfigurableResidualStructuralDiagnostic.required_unknown_count must equal "
                "len(required_unknown_names)"
            )

        if not isinstance(self.determination_status, ResidualDeterminationStatus):
            raise TypeError(
                "ConfigurableResidualStructuralDiagnostic.determination_status must be "
                "a ResidualDeterminationStatus"
            )

        if self.scenario_unknown_names is not None and not isinstance(
            self.scenario_unknown_names, tuple
        ):
            raise TypeError(
                "ConfigurableResidualStructuralDiagnostic.scenario_unknown_names must be "
                "a tuple or None"
            )
        for tuple_field in ("missing_from_scenario", "extra_scenario_unknowns"):
            if not isinstance(getattr(self, tuple_field), tuple):
                raise TypeError(
                    f"ConfigurableResidualStructuralDiagnostic.{tuple_field} must be a tuple"
                )
        if self.scenario_compatible is not None and not isinstance(self.scenario_compatible, bool):
            raise TypeError(
                "ConfigurableResidualStructuralDiagnostic.scenario_compatible must be "
                "bool or None"
            )
        if (self.scenario_unknown_names is None) != (self.scenario_compatible is None):
            raise ValueError(
                "ConfigurableResidualStructuralDiagnostic.scenario_unknown_names and "
                "scenario_compatible must both be None or both be set"
            )

        if self.supplied_unknown_names is not None and not isinstance(
            self.supplied_unknown_names, tuple
        ):
            raise TypeError(
                "ConfigurableResidualStructuralDiagnostic.supplied_unknown_names must be "
                "a tuple or None"
            )
        for tuple_field in ("missing_from_values", "extra_supplied_unknowns"):
            if not isinstance(getattr(self, tuple_field), tuple):
                raise TypeError(
                    f"ConfigurableResidualStructuralDiagnostic.{tuple_field} must be a tuple"
                )
        if self.unknown_values_complete is not None and not isinstance(
            self.unknown_values_complete, bool
        ):
            raise TypeError(
                "ConfigurableResidualStructuralDiagnostic.unknown_values_complete must be "
                "bool or None"
            )
        if (self.supplied_unknown_names is None) != (self.unknown_values_complete is None):
            raise ValueError(
                "ConfigurableResidualStructuralDiagnostic.supplied_unknown_names and "
                "unknown_values_complete must both be None or both be set"
            )

        if not isinstance(self.evaluation_ready, bool):
            raise TypeError(
                "ConfigurableResidualStructuralDiagnostic.evaluation_ready must be bool"
            )

        if not isinstance(self.solve_ready, bool):
            raise TypeError("ConfigurableResidualStructuralDiagnostic.solve_ready must be bool")
        if self.solve_ready:
            raise ValueError("ConfigurableResidualStructuralDiagnostic.solve_ready must be False")
        if not isinstance(self.no_solve, bool):
            raise TypeError("ConfigurableResidualStructuralDiagnostic.no_solve must be bool")
        if not self.no_solve:
            raise ValueError("ConfigurableResidualStructuralDiagnostic.no_solve must be True")

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
                    f"ConfigurableResidualStructuralDiagnostic.{flag_name} must be bool"
                )
            if val:
                raise ValueError(
                    f"ConfigurableResidualStructuralDiagnostic.{flag_name} must be False"
                )

        if not isinstance(self.limitations, tuple):
            raise TypeError("ConfigurableResidualStructuralDiagnostic.limitations must be a tuple")


# ---------------------------------------------------------------------------
# evaluate_configurable_residual_structure
# ---------------------------------------------------------------------------


def evaluate_configurable_residual_structure(
    residual_set: ConfigurableAlgebraicResidualSet,
    *,
    scenario_build_result: ConfigurableScenarioBuildResult | None = None,
    unknown_values: Mapping[str, float] | None = None,
) -> ConfigurableResidualStructuralDiagnostic:
    """Evaluate purely structural diagnostics for an explicit residual set.

    Required unknown names are read directly from
    ``residual_set.required_unknown_names`` (the existing Block 15F-A
    approved API).  No scenario graph topology is inspected.  No roles are
    inspected.  No residual values are evaluated.  No solve is performed.

    Parameters
    ----------
    residual_set           : ConfigurableAlgebraicResidualSet — explicit, required
    scenario_build_result  : ConfigurableScenarioBuildResult | None — optional
    unknown_values          : Mapping[str, float] | None — optional

    Returns
    -------
    ConfigurableResidualStructuralDiagnostic — frozen, immutable

    Raises
    ------
    TypeError
        If residual_set is not a ConfigurableAlgebraicResidualSet.
        If scenario_build_result is not a ConfigurableScenarioBuildResult or None.
        If unknown_values is not a Mapping or None.
        If any supplied unknown value is bool or non-numeric.
    ValueError
        If any supplied unknown value is NaN or infinite.
    """
    if not isinstance(residual_set, ConfigurableAlgebraicResidualSet):
        raise TypeError(
            "evaluate_configurable_residual_structure: residual_set must be a "
            "ConfigurableAlgebraicResidualSet; "
            f"got {type(residual_set).__name__!r}"
        )
    if scenario_build_result is not None and not isinstance(
        scenario_build_result, ConfigurableScenarioBuildResult
    ):
        raise TypeError(
            "evaluate_configurable_residual_structure: scenario_build_result must be "
            "a ConfigurableScenarioBuildResult or None; "
            f"got {type(scenario_build_result).__name__!r}"
        )
    if unknown_values is not None and not isinstance(unknown_values, Mapping):
        raise TypeError(
            "evaluate_configurable_residual_structure: unknown_values must be a "
            f"Mapping or None; got {type(unknown_values).__name__!r}"
        )

    residual_names = residual_set.residual_names
    required_unknown_names = residual_set.required_unknown_names
    residual_count = len(residual_names)
    required_unknown_count = len(required_unknown_names)
    required_set = set(required_unknown_names)

    if residual_count == required_unknown_count:
        determination_status = ResidualDeterminationStatus.SQUARE
    elif residual_count < required_unknown_count:
        determination_status = ResidualDeterminationStatus.UNDERDETERMINED
    else:
        determination_status = ResidualDeterminationStatus.OVERDETERMINED

    # Scenario compatibility diagnostics.
    scenario_unknown_names: tuple[str, ...] | None
    missing_from_scenario: tuple[str, ...]
    extra_scenario_unknowns: tuple[str, ...]
    scenario_compatible: bool | None
    if scenario_build_result is not None:
        scenario_unknown_names = tuple(scenario_build_result.unknown_names)
        scenario_set = set(scenario_unknown_names)
        missing_from_scenario = tuple(sorted(required_set - scenario_set))
        extra_scenario_unknowns = tuple(sorted(scenario_set - required_set))
        scenario_compatible = len(missing_from_scenario) == 0
    else:
        scenario_unknown_names = None
        missing_from_scenario = ()
        extra_scenario_unknowns = ()
        scenario_compatible = None

    # Unknown value completeness diagnostics.
    supplied_unknown_names: tuple[str, ...] | None
    missing_from_values: tuple[str, ...]
    extra_supplied_unknowns: tuple[str, ...]
    unknown_values_complete: bool | None
    if unknown_values is not None:
        validated = _validate_supplied_value_types(unknown_values)
        supplied_set = set(validated.keys())
        supplied_unknown_names = tuple(sorted(supplied_set))
        missing_from_values = tuple(sorted(required_set - supplied_set))
        extra_supplied_unknowns = tuple(sorted(supplied_set - required_set))
        unknown_values_complete = len(missing_from_values) == 0
    else:
        supplied_unknown_names = None
        missing_from_values = ()
        extra_supplied_unknowns = ()
        unknown_values_complete = None

    # Evaluation readiness.
    if unknown_values_complete is None:
        evaluation_ready = False
    elif scenario_compatible is not None:
        evaluation_ready = bool(scenario_compatible) and bool(unknown_values_complete)
    else:
        evaluation_ready = bool(unknown_values_complete)

    return ConfigurableResidualStructuralDiagnostic(
        residual_names=residual_names,
        required_unknown_names=required_unknown_names,
        residual_count=residual_count,
        required_unknown_count=required_unknown_count,
        determination_status=determination_status,
        scenario_unknown_names=scenario_unknown_names,
        missing_from_scenario=missing_from_scenario,
        extra_scenario_unknowns=extra_scenario_unknowns,
        scenario_compatible=scenario_compatible,
        supplied_unknown_names=supplied_unknown_names,
        missing_from_values=missing_from_values,
        extra_supplied_unknowns=extra_supplied_unknowns,
        unknown_values_complete=unknown_values_complete,
        evaluation_ready=evaluation_ready,
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
# build_configurable_residual_diagnostic_report
# ---------------------------------------------------------------------------


def build_configurable_residual_diagnostic_report(
    diagnostic: ConfigurableResidualStructuralDiagnostic,
) -> dict[str, object]:
    """Build a plain JSON-serializable report for a structural diagnostic.

    Returns a plain dict with only JSON-serializable values.  No file
    writes.  No pandas.  No physical state values.  No solved values.

    Parameters
    ----------
    diagnostic : ConfigurableResidualStructuralDiagnostic

    Returns
    -------
    dict[str, object] — JSON-serializable report

    Raises
    ------
    TypeError
        If diagnostic is not a ConfigurableResidualStructuralDiagnostic.
    """
    if not isinstance(diagnostic, ConfigurableResidualStructuralDiagnostic):
        raise TypeError(
            "build_configurable_residual_diagnostic_report: diagnostic must be a "
            "ConfigurableResidualStructuralDiagnostic; "
            f"got {type(diagnostic).__name__!r}"
        )

    report: dict[str, object] = {
        "status": "configurable_residual_structural_diagnostic",
        "residual_names": list(diagnostic.residual_names),
        "required_unknown_names": list(diagnostic.required_unknown_names),
        "residual_count": diagnostic.residual_count,
        "required_unknown_count": diagnostic.required_unknown_count,
        "determination_status": diagnostic.determination_status.value,
        "scenario_compatibility": {
            "checked": diagnostic.scenario_unknown_names is not None,
            "scenario_unknown_names": (
                list(diagnostic.scenario_unknown_names)
                if diagnostic.scenario_unknown_names is not None
                else None
            ),
            "missing_from_scenario": list(diagnostic.missing_from_scenario),
            "extra_scenario_unknowns": list(diagnostic.extra_scenario_unknowns),
            "scenario_compatible": diagnostic.scenario_compatible,
        },
        "unknown_value_completeness": {
            "checked": diagnostic.supplied_unknown_names is not None,
            "supplied_unknown_names": (
                list(diagnostic.supplied_unknown_names)
                if diagnostic.supplied_unknown_names is not None
                else None
            ),
            "missing_from_values": list(diagnostic.missing_from_values),
            "extra_supplied_unknowns": list(diagnostic.extra_supplied_unknowns),
            "unknown_values_complete": diagnostic.unknown_values_complete,
        },
        "evaluation_ready": diagnostic.evaluation_ready,
        "solve_ready": diagnostic.solve_ready,
        "no_solve": diagnostic.no_solve,
        "residuals_inferred_from_roles": diagnostic.residuals_inferred_from_roles,
        "residuals_inferred_from_topology": diagnostic.residuals_inferred_from_topology,
        "blueprints_inferred_from_roles": diagnostic.blueprints_inferred_from_roles,
        "blueprints_inferred_from_topology": diagnostic.blueprints_inferred_from_topology,
        "closures_inferred_from_roles": diagnostic.closures_inferred_from_roles,
        "production_components_executed": diagnostic.production_components_executed,
        "limitations": list(diagnostic.limitations),
    }

    # Verify JSON-serializability before returning.
    json.dumps(report)
    return report
