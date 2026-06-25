"""Closure integration and sufficiency diagnostics — Block 15D-C.

Combines hydraulic (Block 15D-A) and thermal (Block 15D-B) closure residual
sets into a unified combined closure layer.  Provides combined residual
evaluation, combined category-presence diagnostics, and plain report
generation.

This module is evaluation/reporting only.  It does NOT solve the combined
system.  Category sufficiency does NOT imply equation rank, DAE solvability,
or physical predictiveness.

Ordering
--------
Residual ordering within the combined set is deterministic:
  hydraulic residuals first (in their original declared order),
  thermal residuals second (in their original declared order).
This ordering is preserved across all evaluation, diagnostic, and report
functions.

Partial-domain sets
-------------------
A hydraulic-only CombinedClosureResidualSet (thermal=None) is allowed.
A thermal-only CombinedClosureResidualSet (hydraulic=None) is allowed.
An empty set (both None) is rejected by build_combined_closure_residuals.

Extra unknowns
--------------
Extra unknowns beyond what the closures require are silently ignored by
evaluate_all.  Only unknowns referenced by a closure equation are validated;
extra unknowns with bad values (NaN, inf, bool) are not seen and not rejected.
This matches the behavior of the underlying domain residual sets.

Known limitation
----------------
This module provides category-presence diagnostics only.  is_sufficient=True
means all required categories have at least one matching closure; it does NOT
mean the combined system has correct algebraic rank, is uniquely solvable, or
represents physically predictive equations.  Symbolic rank analysis and DAE
solvability verification are not performed and are not claimed.

Architecture constraints
------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop,
    mpl_sim.solvers, or mpl_sim.network.solver.
MUST NOT import CoolProp or any property engine.
MUST NOT store FluidState, SystemState, mdot values, pressure values,
    enthalpy values, or temperature values in structural objects.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT call PropertyBackend, CorrelationRegistry, or
    HeatExchangerModelRegistry.
MUST NOT implement solve(network) or NetworkGraph.solve().
MUST NOT execute production component physics.
MUST NOT infer physics from component_type.
MUST NOT write files or depend on pandas, matplotlib, or numpy.
MUST NOT perform least-squares, root-finding, or optimization.

Exported names
--------------
ClosureDomain                        — enum: "hydraulic" / "thermal"
CombinedClosureResidualSet           — combined residual set (wraps H + T)
CombinedClosureEvaluationResult      — result of combined residual evaluation
CombinedClosureDiagnosticResult      — result of combined sufficiency check
build_combined_closure_residuals     — factory: H + T sets -> combined set
evaluate_combined_closure_residuals  — evaluates all closure residuals
evaluate_combined_closure_sufficiency — combined category-presence check
build_combined_closure_report        — plain serializable dict report
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from mpl_sim.network.hydraulic_closure_diagnostics import (
    HydraulicClosureDiagnostic,
    HydraulicClosureDiagnosticResult,
    evaluate_hydraulic_closure_sufficiency,
)
from mpl_sim.network.hydraulic_closures import HydraulicClosureResidualSet
from mpl_sim.network.thermal_closure_diagnostics import (
    ThermalClosureDiagnostic,
    ThermalClosureDiagnosticResult,
    evaluate_thermal_closure_sufficiency,
)
from mpl_sim.network.thermal_closures import ThermalClosureResidualSet

# ---------------------------------------------------------------------------
# ClosureDomain
# ---------------------------------------------------------------------------


class ClosureDomain(str, Enum):
    """Identifies which physical domain a closure or residual belongs to.

    Used to label residual values and diagnostic results by domain.
    """

    HYDRAULIC = "hydraulic"
    THERMAL = "thermal"


# ---------------------------------------------------------------------------
# CombinedClosureResidualSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CombinedClosureResidualSet:
    """Combined hydraulic + thermal closure residual set.

    Wraps an optional hydraulic and an optional thermal closure residual set.
    At least one must be non-None; build_combined_closure_residuals enforces
    this.

    Residual ordering is deterministic:
      hydraulic residuals first (in their original declared order),
      thermal residuals second (in their original declared order).

    All residual names are unique across both domains; duplicate residual
    names across hydraulic and thermal domains are rejected at build time
    by build_combined_closure_residuals.

    Build using build_combined_closure_residuals.

    Fields
    ------
    hydraulic : HydraulicClosureResidualSet or None
    thermal   : ThermalClosureResidualSet or None

    Properties
    ----------
    residual_names : tuple[str, ...] — ordered residual names (hydraulic first)
    hydraulic_count : int — number of hydraulic residuals (0 if no hydraulic)
    thermal_count   : int — number of thermal residuals (0 if no thermal)

    Methods
    -------
    evaluate_all(unknowns) -> MappingProxyType[str, float]
        Evaluate all closures at the given unknown vector and return a
        read-only mapping of residual_name -> float.  Hydraulic residuals
        are evaluated first, thermal second.  All required unknowns must be
        present, finite, and non-bool.  Extra unknowns are silently ignored.
    """

    hydraulic: HydraulicClosureResidualSet | None
    thermal: ThermalClosureResidualSet | None

    def __post_init__(self) -> None:
        if self.hydraulic is None and self.thermal is None:
            raise ValueError(
                "CombinedClosureResidualSet: at least one of hydraulic or "
                "thermal must be provided; both are None"
            )
        if self.hydraulic is not None and not isinstance(
            self.hydraulic, HydraulicClosureResidualSet
        ):
            raise TypeError(
                "CombinedClosureResidualSet: hydraulic must be a "
                f"HydraulicClosureResidualSet or None; got "
                f"{type(self.hydraulic).__name__!r}"
            )
        if self.thermal is not None and not isinstance(self.thermal, ThermalClosureResidualSet):
            raise TypeError(
                "CombinedClosureResidualSet: thermal must be a "
                f"ThermalClosureResidualSet or None; got "
                f"{type(self.thermal).__name__!r}"
            )

        if self.hydraulic is not None and self.thermal is not None:
            conflicts = set(self.hydraulic.residual_names) & set(self.thermal.residual_names)
            if conflicts:
                raise ValueError(
                    "CombinedClosureResidualSet: duplicate residual names "
                    f"across hydraulic and thermal domains: {sorted(conflicts)!r}"
                )

    @property
    def residual_names(self) -> tuple[str, ...]:
        names: list[str] = []
        if self.hydraulic is not None:
            names.extend(self.hydraulic.residual_names)
        if self.thermal is not None:
            names.extend(self.thermal.residual_names)
        return tuple(names)

    @property
    def hydraulic_count(self) -> int:
        return len(self.hydraulic.closures) if self.hydraulic is not None else 0

    @property
    def thermal_count(self) -> int:
        return len(self.thermal.closures) if self.thermal is not None else 0

    def evaluate_all(self, unknowns: Mapping[str, float]) -> MappingProxyType[str, float]:
        """Evaluate all closures and return a read-only combined residual map.

        Hydraulic residuals are evaluated first, thermal residuals second.
        All required unknowns must be present, finite, and non-bool.
        Extra unknowns beyond what the closures require are silently ignored.
        """
        result: dict[str, float] = {}
        if self.hydraulic is not None:
            result.update(self.hydraulic.evaluate_all(unknowns))
        if self.thermal is not None:
            result.update(self.thermal.evaluate_all(unknowns))
        return MappingProxyType(result)


# ---------------------------------------------------------------------------
# CombinedClosureEvaluationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CombinedClosureEvaluationResult:
    """Result of evaluating a CombinedClosureResidualSet.

    Produced by evaluate_combined_closure_residuals.

    This result is evaluation-only; no solve is claimed.

    Fields
    ------
    hydraulic_residuals : MappingProxyType[str, float]
        Read-only map of hydraulic residual_name -> value.
        Empty if no hydraulic closures were provided.
    thermal_residuals   : MappingProxyType[str, float]
        Read-only map of thermal residual_name -> value.
        Empty if no thermal closures were provided.
    combined_residuals  : MappingProxyType[str, float]
        Read-only combined map (hydraulic first, thermal second).
    max_absolute_residual : float
        Maximum absolute value among all combined residuals.
        0.0 if no residuals are present.
    l2_residual_norm    : float
        Euclidean (L2) norm of all combined residual values.
    hydraulic_count     : int — number of hydraulic residuals
    thermal_count       : int — number of thermal residuals
    metadata            : MappingProxyType[str, object] or None
        Optional caller metadata; defensively copied at build time.
    """

    hydraulic_residuals: MappingProxyType[str, float]
    thermal_residuals: MappingProxyType[str, float]
    combined_residuals: MappingProxyType[str, float]
    max_absolute_residual: float
    l2_residual_norm: float
    hydraulic_count: int
    thermal_count: int
    metadata: MappingProxyType[str, object] | None


# ---------------------------------------------------------------------------
# CombinedClosureDiagnosticResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CombinedClosureDiagnosticResult:
    """Result of evaluating combined closure category-presence sufficiency.

    Produced by evaluate_combined_closure_sufficiency.

    This is a category-presence diagnostic only.  See limitations_note for
    what this result does and does not assert.

    Fields
    ------
    hydraulic_result : HydraulicClosureDiagnosticResult or None
        Hydraulic domain diagnostic result, or None if no hydraulic
        diagnostic was supplied or no hydraulic closures were present.
    thermal_result   : ThermalClosureDiagnosticResult or None
        Thermal domain diagnostic result, or None if no thermal diagnostic
        was supplied or no thermal closures were present.
    is_sufficient    : bool
        True iff every included domain's diagnostic is satisfied (all
        required categories have at least one matching closure).
        Domains without a diagnostic are not checked and do not fail.
        If no diagnostic is supplied for any domain, is_sufficient=True.
    limitations_note : str
        States that this is category-presence sufficiency only; does not
        guarantee algebraic rank, DAE solvability, or physical predictiveness.
    """

    hydraulic_result: HydraulicClosureDiagnosticResult | None
    thermal_result: ThermalClosureDiagnosticResult | None
    is_sufficient: bool
    limitations_note: str


# ---------------------------------------------------------------------------
# build_combined_closure_residuals
# ---------------------------------------------------------------------------


def build_combined_closure_residuals(
    *,
    hydraulic: HydraulicClosureResidualSet | None = None,
    thermal: ThermalClosureResidualSet | None = None,
) -> CombinedClosureResidualSet:
    """Build a CombinedClosureResidualSet from optional hydraulic and thermal sets.

    At least one of hydraulic or thermal must be provided.

    Residual names must be unique across both sets.  Duplicate residual
    names across the hydraulic and thermal domains are rejected.

    Parameters
    ----------
    hydraulic:
        Optional HydraulicClosureResidualSet.  If None, the hydraulic domain
        is absent from the combined set.  A hydraulic-only combined set is
        allowed.
    thermal:
        Optional ThermalClosureResidualSet.  If None, the thermal domain is
        absent from the combined set.  A thermal-only combined set is allowed.

    Returns
    -------
    CombinedClosureResidualSet

    Raises
    ------
    TypeError  — if hydraulic or thermal are the wrong types
    ValueError — if both are None, or if residual names conflict across domains
    """
    return CombinedClosureResidualSet(hydraulic=hydraulic, thermal=thermal)


# ---------------------------------------------------------------------------
# evaluate_combined_closure_residuals
# ---------------------------------------------------------------------------


def evaluate_combined_closure_residuals(
    combined: CombinedClosureResidualSet,
    unknowns: Mapping[str, float],
    *,
    metadata: Mapping[str, object] | None = None,
) -> CombinedClosureEvaluationResult:
    """Evaluate all closure residuals in the combined set.

    Hydraulic residuals are evaluated first, thermal residuals second.
    All required unknowns must be present, finite, and non-bool.
    Extra unknowns are silently ignored.

    Parameters
    ----------
    combined:
        A CombinedClosureResidualSet to evaluate.
    unknowns:
        Mapping of unknown name to float value.  All unknowns required by the
        closure equations must be present.  Extra unknowns are ignored.
    metadata:
        Optional caller metadata.  Defensively copied as MappingProxyType.

    Returns
    -------
    CombinedClosureEvaluationResult (frozen, with read-only residual maps)

    Raises
    ------
    TypeError  — if combined is not a CombinedClosureResidualSet
    KeyError   — if a required unknown is missing from unknowns
    TypeError  — if a required unknown value is bool or non-numeric
    ValueError — if a required unknown value is NaN or infinite
    """
    if not isinstance(combined, CombinedClosureResidualSet):
        raise TypeError(
            "evaluate_combined_closure_residuals: combined must be a "
            f"CombinedClosureResidualSet; got {type(combined).__name__!r}"
        )

    h_residuals: dict[str, float] = {}
    if combined.hydraulic is not None:
        h_residuals.update(combined.hydraulic.evaluate_all(unknowns))

    t_residuals: dict[str, float] = {}
    if combined.thermal is not None:
        t_residuals.update(combined.thermal.evaluate_all(unknowns))

    combined_dict: dict[str, float] = {}
    combined_dict.update(h_residuals)
    combined_dict.update(t_residuals)

    all_values = list(combined_dict.values())
    if all_values:
        max_abs = max(abs(v) for v in all_values)
        l2_norm = math.sqrt(sum(v * v for v in all_values))
    else:
        max_abs = 0.0
        l2_norm = 0.0

    meta_proxy: MappingProxyType[str, object] | None = None
    if metadata is not None:
        meta_proxy = MappingProxyType(dict(metadata))

    return CombinedClosureEvaluationResult(
        hydraulic_residuals=MappingProxyType(h_residuals),
        thermal_residuals=MappingProxyType(t_residuals),
        combined_residuals=MappingProxyType(combined_dict),
        max_absolute_residual=max_abs,
        l2_residual_norm=l2_norm,
        hydraulic_count=combined.hydraulic_count,
        thermal_count=combined.thermal_count,
        metadata=meta_proxy,
    )


# ---------------------------------------------------------------------------
# evaluate_combined_closure_sufficiency
# ---------------------------------------------------------------------------

_LIMITATIONS_NOTE: str = (
    "Category-presence sufficiency only.  is_sufficient=True means all "
    "required closure categories have at least one matching closure; it does "
    "NOT guarantee algebraic rank, DAE solvability, or physical predictiveness. "
    "No symbolic rank analysis is performed.  This diagnostic is not "
    "property-backed, not correlation-backed, and not HX-model-backed.  No "
    "production component execution is performed."
)


def evaluate_combined_closure_sufficiency(
    combined: CombinedClosureResidualSet,
    *,
    hydraulic_diagnostic: HydraulicClosureDiagnostic | None = None,
    thermal_diagnostic: ThermalClosureDiagnostic | None = None,
) -> CombinedClosureDiagnosticResult:
    """Evaluate combined category-presence sufficiency for all included domains.

    For each domain present in the combined set AND for which a diagnostic
    is supplied, evaluates whether the required closure categories are
    satisfied.  Returns a combined result with per-domain diagnostic results
    and an overall sufficiency verdict.

    If hydraulic_diagnostic is None, the hydraulic domain is not checked
    (hydraulic_result=None in the returned result).  If thermal_diagnostic
    is None, the thermal domain is not checked.  Domains without a diagnostic
    do not contribute to a failing verdict.

    Parameters
    ----------
    combined:
        A CombinedClosureResidualSet.
    hydraulic_diagnostic:
        Optional HydraulicClosureDiagnostic.  If None, the hydraulic domain
        is skipped.
    thermal_diagnostic:
        Optional ThermalClosureDiagnostic.  If None, the thermal domain is
        skipped.

    Returns
    -------
    CombinedClosureDiagnosticResult with per-domain results, overall
    is_sufficient verdict, and a limitations_note.

    Notes
    -----
    is_sufficient=True does NOT guarantee algebraic rank, DAE solvability,
    or physical predictiveness; see limitations_note in the returned result.
    """
    if not isinstance(combined, CombinedClosureResidualSet):
        raise TypeError(
            "evaluate_combined_closure_sufficiency: combined must be a "
            f"CombinedClosureResidualSet; got {type(combined).__name__!r}"
        )

    h_result: HydraulicClosureDiagnosticResult | None = None
    if hydraulic_diagnostic is not None and combined.hydraulic is not None:
        h_result = evaluate_hydraulic_closure_sufficiency(hydraulic_diagnostic, combined.hydraulic)

    t_result: ThermalClosureDiagnosticResult | None = None
    if thermal_diagnostic is not None and combined.thermal is not None:
        t_result = evaluate_thermal_closure_sufficiency(thermal_diagnostic, combined.thermal)

    is_sufficient = True
    if h_result is not None and not h_result.is_sufficient:
        is_sufficient = False
    if t_result is not None and not t_result.is_sufficient:
        is_sufficient = False

    return CombinedClosureDiagnosticResult(
        hydraulic_result=h_result,
        thermal_result=t_result,
        is_sufficient=is_sufficient,
        limitations_note=_LIMITATIONS_NOTE,
    )


# ---------------------------------------------------------------------------
# build_combined_closure_report
# ---------------------------------------------------------------------------


def build_combined_closure_report(
    evaluation: CombinedClosureEvaluationResult,
    diagnostic: CombinedClosureDiagnosticResult | None = None,
) -> dict[str, object]:
    """Build a plain serializable report from combined evaluation and diagnostic results.

    The returned dict contains only JSON-serializable values (str, int, float,
    bool, list, dict, None).  No file writing, no pandas, no plotting.

    The report always includes a limitations section stating:
      - evaluation only; no solve claimed
      - category sufficiency only; no symbolic rank analysis
      - not property-backed; no CoolProp or PropertyBackend
      - not correlation-backed; no CorrelationRegistry
      - not HX-model-backed; no HX model calls
      - no production component execution
      - no SystemState assembly; no FluidState construction
      - no generic solve(network) or NetworkGraph.solve()

    Parameters
    ----------
    evaluation:
        A CombinedClosureEvaluationResult.
    diagnostic:
        Optional CombinedClosureDiagnosticResult.  If None, the diagnostic
        section is absent from the report.

    Returns
    -------
    dict[str, object] — plain JSON-serializable dictionary.
    No files are written.  No pandas import is required.

    Raises
    ------
    TypeError — if evaluation is not a CombinedClosureEvaluationResult
    TypeError — if diagnostic is provided but is not a CombinedClosureDiagnosticResult
    """
    if not isinstance(evaluation, CombinedClosureEvaluationResult):
        raise TypeError(
            "build_combined_closure_report: evaluation must be a "
            f"CombinedClosureEvaluationResult; got {type(evaluation).__name__!r}"
        )

    report: dict[str, object] = {
        "block": "15D-C",
        "status": "evaluation_only",
        "no_solve": True,
        "residuals": {
            ClosureDomain.HYDRAULIC.value: dict(evaluation.hydraulic_residuals),
            ClosureDomain.THERMAL.value: dict(evaluation.thermal_residuals),
            "combined": dict(evaluation.combined_residuals),
        },
        "norms": {
            "max_absolute": evaluation.max_absolute_residual,
            "l2": evaluation.l2_residual_norm,
        },
        "domain_counts": {
            ClosureDomain.HYDRAULIC.value: evaluation.hydraulic_count,
            ClosureDomain.THERMAL.value: evaluation.thermal_count,
            "total": evaluation.hydraulic_count + evaluation.thermal_count,
        },
        "limitations": [
            "evaluation only; no solve is performed or claimed",
            "category-presence sufficiency only; not symbolic rank analysis",
            "not property-backed; no CoolProp or PropertyBackend",
            "not correlation-backed; no CorrelationRegistry",
            "not HX-model-backed; no HX model calls",
            "no production component execution",
            "no SystemState assembly; no FluidState construction",
            "no generic solve(network) or NetworkGraph.solve()",
        ],
    }

    if diagnostic is not None:
        if not isinstance(diagnostic, CombinedClosureDiagnosticResult):
            raise TypeError(
                "build_combined_closure_report: diagnostic must be a "
                f"CombinedClosureDiagnosticResult or None; got "
                f"{type(diagnostic).__name__!r}"
            )
        diag_section: dict[str, object] = {
            "is_sufficient": diagnostic.is_sufficient,
            "limitations_note": diagnostic.limitations_note,
        }
        if diagnostic.hydraulic_result is not None:
            h = diagnostic.hydraulic_result
            diag_section[ClosureDomain.HYDRAULIC.value] = {
                "is_sufficient": h.is_sufficient,
                "provided_categories": sorted(cat.value for cat in h.provided_categories),
                "missing_categories": sorted(cat.value for cat in h.missing_categories),
                "missing_messages": list(h.missing_messages),
                "closure_names": list(h.closure_names),
            }
        if diagnostic.thermal_result is not None:
            t = diagnostic.thermal_result
            diag_section[ClosureDomain.THERMAL.value] = {
                "is_sufficient": t.is_sufficient,
                "provided_categories": sorted(cat.value for cat in t.provided_categories),
                "missing_categories": sorted(cat.value for cat in t.missing_categories),
                "missing_messages": list(t.missing_messages),
                "closure_names": list(t.closure_names),
            }
        report["diagnostic"] = diag_section

    return report
