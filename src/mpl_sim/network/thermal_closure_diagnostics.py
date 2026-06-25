"""Thermal closure sufficiency diagnostics — Block 15D-B.

Provides lightweight diagnostics for whether a set of thermal closure
primitives satisfies the minimum required constraint categories for a given
thermal scenario.

This diagnostic is targeted and honest.  It does NOT perform symbolic rank
analysis, DAE analysis, or full linear-algebra coverage checking.  It checks
whether each required closure category has at least one corresponding closure
of the appropriate kind in the provided ThermalClosureResidualSet.

Supported diagnostics
----------------------
Two targeted helper diagnostics are provided:

  make_basic_thermal_loop_diagnostic():
    For a simple heater or preheater-like element.
    Required categories: HEAT_RATE and ENTHALPY_FLOW_RELATION.
    A HEAT_RATE closure (e.g., FixedHeatRateClosure) fixes or constrains the
    heat input.  An ENTHALPY_FLOW_RELATION (e.g., EnthalpyFlowHeatRateClosure)
    relates the heat rate to the enthalpy change across the element.

  make_recuperator_thermal_diagnostic():
    For a recuperator with two interacting thermal streams.
    Required categories: RECUPERATOR_ENERGY_BALANCE and ENTHALPY_FLOW_RELATION.
    A RECUPERATOR_ENERGY_BALANCE closure enforces that q_hot + q_cold = 0.
    At least one ENTHALPY_FLOW_RELATION closure (per stream or shared) relates
    the heat rates to enthalpy changes.

Diagnostic verdict
------------------
A diagnostic is considered sufficient if all required categories are
satisfied by at least one closure of the corresponding kind.  The verdict
is honest and conservative:
  - is_sufficient=True means all required categories have at least one closure.
  - is_sufficient=False means at least one required category is missing.
  - The diagnostic does NOT claim to verify full algebraic rank or
    guarantee solveability.

Architecture constraints
------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop,
    mpl_sim.solvers, or mpl_sim.network.solver.
MUST NOT import CoolProp or any property engine.
MUST NOT store FluidState, SystemState, or any physical state values.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT call PropertyBackend, CorrelationRegistry, or
    HeatExchangerModelRegistry.
MUST NOT implement solve(network) or NetworkGraph.solve().
MUST NOT execute production component physics.
MUST NOT perform symbolic rank analysis or DAE analysis.

Exported names
--------------
ThermalClosureCategory              — enum of named closure categories
ThermalClosureDiagnostic            — describes required categories for a scenario
ThermalClosureDiagnosticResult      — result of a sufficiency check
evaluate_thermal_closure_sufficiency — function: diagnostic + closures -> result
make_basic_thermal_loop_diagnostic  — factory: heater/preheater diagnostic
make_recuperator_thermal_diagnostic — factory: recuperator diagnostic
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from mpl_sim.network.thermal_closures import (
    ThermalClosureKind,
    ThermalClosureResidualSet,
)

# ---------------------------------------------------------------------------
# ThermalClosureCategory
# ---------------------------------------------------------------------------


class ThermalClosureCategory(str, Enum):
    """Named closure category for thermal diagnostic purposes.

    Each category corresponds to a physical or structural constraint that
    must be present in a thermal closure set before the associated scenario
    can be considered adequately closed.

    HEAT_RATE:
        At least one closure fixes or constrains an explicit heat-rate unknown.
        Satisfied by: FixedHeatRateClosure (kind=FIXED_HEAT_RATE).
        Missing means: the absolute heat input/rejection level is undetermined.

    ENTHALPY_REFERENCE:
        At least one closure imposes an explicit enthalpy boundary condition.
        Satisfied by: ImposedEnthalpyClosure (kind=IMPOSED_ENTHALPY).
        Missing means: no enthalpy boundary is anchored algebraically.

    TEMPERATURE_LIKE_REFERENCE:
        At least one closure imposes an explicit temperature-like scalar.
        Satisfied by: ImposedTemperatureLikeClosure (kind=IMPOSED_TEMPERATURE_LIKE).
        Missing means: no temperature-like boundary is anchored algebraically.

    SENSIBLE_HEAT_RELATION:
        At least one closure provides a sensible heat-rate algebraic relation.
        Satisfied by: SensibleHeatRateClosure (kind=SENSIBLE_HEAT_RATE).
        Missing means: no q = mdot * cp * delta_theta relation is present.

    ENTHALPY_FLOW_RELATION:
        At least one closure provides an enthalpy-flow heat-rate relation.
        Satisfied by: EnthalpyFlowHeatRateClosure (kind=ENTHALPY_FLOW_HEAT_RATE).
        Missing means: no q = mdot * (h_out - h_in) relation is present.

    EFFECTIVENESS_RELATION:
        At least one closure provides an effectiveness-based algebraic relation.
        Satisfied by: EffectivenessHeatRateClosure (kind=EFFECTIVENESS_HEAT_RATE).
        Missing means: no q = effectiveness * q_max relation is present.

    RECUPERATOR_ENERGY_BALANCE:
        At least one closure enforces recuperator energy balance.
        Satisfied by: RecuperatorEnergyBalanceClosure
                      (kind=RECUPERATOR_ENERGY_BALANCE).
        Missing means: no q_hot + q_cold = 0 energy balance is present.
    """

    HEAT_RATE = "heat_rate"
    ENTHALPY_REFERENCE = "enthalpy_reference"
    TEMPERATURE_LIKE_REFERENCE = "temperature_like_reference"
    SENSIBLE_HEAT_RELATION = "sensible_heat_relation"
    ENTHALPY_FLOW_RELATION = "enthalpy_flow_relation"
    EFFECTIVENESS_RELATION = "effectiveness_relation"
    RECUPERATOR_ENERGY_BALANCE = "recuperator_energy_balance"


# ---------------------------------------------------------------------------
# Category-to-kind mapping (module-private)
# ---------------------------------------------------------------------------

_CATEGORY_TO_KINDS: MappingProxyType[ThermalClosureCategory, frozenset[ThermalClosureKind]] = (
    MappingProxyType(
        {
            ThermalClosureCategory.HEAT_RATE: frozenset({ThermalClosureKind.FIXED_HEAT_RATE}),
            ThermalClosureCategory.ENTHALPY_REFERENCE: frozenset(
                {ThermalClosureKind.IMPOSED_ENTHALPY}
            ),
            ThermalClosureCategory.TEMPERATURE_LIKE_REFERENCE: frozenset(
                {ThermalClosureKind.IMPOSED_TEMPERATURE_LIKE}
            ),
            ThermalClosureCategory.SENSIBLE_HEAT_RELATION: frozenset(
                {ThermalClosureKind.SENSIBLE_HEAT_RATE}
            ),
            ThermalClosureCategory.ENTHALPY_FLOW_RELATION: frozenset(
                {ThermalClosureKind.ENTHALPY_FLOW_HEAT_RATE}
            ),
            ThermalClosureCategory.EFFECTIVENESS_RELATION: frozenset(
                {ThermalClosureKind.EFFECTIVENESS_HEAT_RATE}
            ),
            ThermalClosureCategory.RECUPERATOR_ENERGY_BALANCE: frozenset(
                {ThermalClosureKind.RECUPERATOR_ENERGY_BALANCE}
            ),
        }
    )
)

_CATEGORY_MISSING_MESSAGES: MappingProxyType[ThermalClosureCategory, str] = MappingProxyType(
    {
        ThermalClosureCategory.HEAT_RATE: (
            "heat-rate closure missing: add a FixedHeatRateClosure "
            "to fix the absolute heat input or rejection level"
        ),
        ThermalClosureCategory.ENTHALPY_REFERENCE: (
            "enthalpy reference missing: add an ImposedEnthalpyClosure "
            "to anchor an enthalpy boundary condition "
            "(user-supplied scalar, not a property calculation)"
        ),
        ThermalClosureCategory.TEMPERATURE_LIKE_REFERENCE: (
            "temperature-like reference missing: add an ImposedTemperatureLikeClosure "
            "to anchor a scalar thermal boundary condition "
            "(user-supplied scalar, not a property-backed temperature)"
        ),
        ThermalClosureCategory.SENSIBLE_HEAT_RELATION: (
            "sensible heat relation missing: add a SensibleHeatRateClosure "
            "to provide q = mdot * cp * (theta_out - theta_in) with explicit cp"
        ),
        ThermalClosureCategory.ENTHALPY_FLOW_RELATION: (
            "enthalpy-flow relation missing: add an EnthalpyFlowHeatRateClosure "
            "to provide q = mdot * (h_out - h_in) for at least one stream"
        ),
        ThermalClosureCategory.EFFECTIVENESS_RELATION: (
            "effectiveness relation missing: add an EffectivenessHeatRateClosure "
            "to provide q = effectiveness * q_max "
            "(algebraic only; not a real HX effectiveness-NTU model)"
        ),
        ThermalClosureCategory.RECUPERATOR_ENERGY_BALANCE: (
            "recuperator energy balance missing: add a RecuperatorEnergyBalanceClosure "
            "to enforce q_hot + q_cold = 0 between the two thermal streams"
        ),
    }
)


# ---------------------------------------------------------------------------
# ThermalClosureDiagnostic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThermalClosureDiagnostic:
    """Describes the required closure categories for a thermal scenario.

    This is a declaration object that specifies which closure categories
    must be present for the associated thermal scenario to be considered
    adequately closed for solving.

    Fields
    ------
    required_categories : frozenset of ThermalClosureCategory values that
                          must be satisfied
    description         : short human-readable description of the scenario

    Use make_basic_thermal_loop_diagnostic() for the heater/preheater pattern.
    Use make_recuperator_thermal_diagnostic() for the recuperator pattern.
    """

    required_categories: frozenset[ThermalClosureCategory]
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.required_categories, frozenset):
            raise TypeError(
                "ThermalClosureDiagnostic.required_categories must be "
                "a frozenset; got "
                f"{type(self.required_categories).__name__!r}"
            )
        for cat in self.required_categories:
            if not isinstance(cat, ThermalClosureCategory):
                raise TypeError(
                    f"ThermalClosureDiagnostic.required_categories entries "
                    f"must be ThermalClosureCategory; got {type(cat).__name__!r}"
                )
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("ThermalClosureDiagnostic.description must be a non-blank str")


# ---------------------------------------------------------------------------
# ThermalClosureDiagnosticResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThermalClosureDiagnosticResult:
    """Result of evaluating thermal closure sufficiency.

    Produced by evaluate_thermal_closure_sufficiency.

    Fields
    ------
    provided_categories : frozenset of satisfied ThermalClosureCategory values
    missing_categories  : frozenset of unsatisfied ThermalClosureCategory values
    is_sufficient       : True iff all required categories are satisfied
    closure_names       : tuple of residual names of the provided closures
    missing_messages    : tuple of human-readable descriptions of missing categories

    Notes
    -----
    is_sufficient=True does NOT guarantee algebraic rank or solveability.
    It only means every required category has at least one matching closure.
    Full rank verification is not implemented in Block 15D-B.
    Diagnostics are category-based only; no residual evaluation is performed.
    """

    provided_categories: frozenset[ThermalClosureCategory]
    missing_categories: frozenset[ThermalClosureCategory]
    is_sufficient: bool
    closure_names: tuple[str, ...]
    missing_messages: tuple[str, ...]


# ---------------------------------------------------------------------------
# evaluate_thermal_closure_sufficiency
# ---------------------------------------------------------------------------


def evaluate_thermal_closure_sufficiency(
    diagnostic: ThermalClosureDiagnostic,
    closures: ThermalClosureResidualSet,
) -> ThermalClosureDiagnosticResult:
    """Evaluate whether a thermal closure set satisfies all required categories.

    For each required category in the diagnostic, checks whether at least
    one closure in the set has a kind that satisfies that category.

    Parameters
    ----------
    diagnostic:
        A ThermalClosureDiagnostic declaring the required categories.
    closures:
        A ThermalClosureResidualSet to evaluate.

    Returns
    -------
    ThermalClosureDiagnosticResult with provided/missing categories,
    sufficiency verdict, closure names, and human-readable missing messages.

    Notes
    -----
    This function does not evaluate residual values and does not require
    an unknown-value vector.  It only inspects closure kinds.
    """
    if not isinstance(diagnostic, ThermalClosureDiagnostic):
        raise TypeError(
            "evaluate_thermal_closure_sufficiency: diagnostic must be "
            "a ThermalClosureDiagnostic; got "
            f"{type(diagnostic).__name__!r}"
        )
    if not isinstance(closures, ThermalClosureResidualSet):
        raise TypeError(
            "evaluate_thermal_closure_sufficiency: closures must be "
            "a ThermalClosureResidualSet; got "
            f"{type(closures).__name__!r}"
        )

    provided_kinds: frozenset[ThermalClosureKind] = frozenset(c.kind for c in closures.closures)

    provided_categories: set[ThermalClosureCategory] = set()
    missing_categories: set[ThermalClosureCategory] = set()
    missing_messages: list[str] = []

    for cat in sorted(diagnostic.required_categories, key=lambda c: c.value):
        satisfying_kinds = _CATEGORY_TO_KINDS[cat]
        if provided_kinds & satisfying_kinds:
            provided_categories.add(cat)
        else:
            missing_categories.add(cat)
            missing_messages.append(_CATEGORY_MISSING_MESSAGES[cat])

    is_sufficient = len(missing_categories) == 0

    return ThermalClosureDiagnosticResult(
        provided_categories=frozenset(provided_categories),
        missing_categories=frozenset(missing_categories),
        is_sufficient=is_sufficient,
        closure_names=tuple(c.residual_name for c in closures.closures),
        missing_messages=tuple(missing_messages),
    )


# ---------------------------------------------------------------------------
# make_basic_thermal_loop_diagnostic
# ---------------------------------------------------------------------------


def make_basic_thermal_loop_diagnostic() -> ThermalClosureDiagnostic:
    """Return a diagnostic for a basic heater or preheater-like element.

    This diagnostic targets a simple single-stream thermal element such as an
    electrical heater, a preheater with imposed duty, or a heat-source boundary:

      - A HEAT_RATE closure (e.g., FixedHeatRateClosure) is required to fix
        the absolute heat input or rejection level.
      - An ENTHALPY_FLOW_RELATION closure (e.g., EnthalpyFlowHeatRateClosure)
        is required to relate the heat rate to the enthalpy change.

    Together these two closures algebraically close the single-stream thermal
    balance: q is fixed by the HEAT_RATE closure and linked to the enthalpy
    change by the ENTHALPY_FLOW_RELATION closure.

    Note: This diagnostic does NOT guarantee full algebraic rank or
    solveability.  It checks only that at least one closure of each required
    kind is present.  A SENSIBLE_HEAT_RELATION could substitute for the
    enthalpy-flow relation in sensible-only scenarios, but this helper
    targets the enthalpy-flow pattern.
    """
    return ThermalClosureDiagnostic(
        required_categories=frozenset(
            {
                ThermalClosureCategory.HEAT_RATE,
                ThermalClosureCategory.ENTHALPY_FLOW_RELATION,
            }
        ),
        description=(
            "Basic thermal loop element (heater/preheater/heat-source boundary): "
            "requires a fixed heat-rate closure and an enthalpy-flow relation closure"
        ),
    )


# ---------------------------------------------------------------------------
# make_recuperator_thermal_diagnostic
# ---------------------------------------------------------------------------


def make_recuperator_thermal_diagnostic() -> ThermalClosureDiagnostic:
    """Return a diagnostic for a recuperator with two interacting thermal streams.

    This diagnostic targets a recuperator-like element where heat is exchanged
    between a hot stream and a cold stream:

      - A RECUPERATOR_ENERGY_BALANCE closure (RecuperatorEnergyBalanceClosure)
        is required to enforce that q_hot + q_cold = 0 (energy consistency
        between the two streams; does NOT predict heat-transfer magnitude).
      - An ENTHALPY_FLOW_RELATION closure (EnthalpyFlowHeatRateClosure)
        is required for at least one stream, to relate q to enthalpy change.

    A fully closed recuperator scenario would typically have two
    EnthalpyFlowHeatRateClosure instances (one per stream), but this
    diagnostic only checks that the category is present at least once.

    Note: This diagnostic does NOT guarantee full algebraic rank or
    solveability.  It does not check that both streams have independent
    closures or that the combined system is square.  No UA, LMTD, NTU,
    HTC, or property-backed logic is required or validated.
    """
    return ThermalClosureDiagnostic(
        required_categories=frozenset(
            {
                ThermalClosureCategory.RECUPERATOR_ENERGY_BALANCE,
                ThermalClosureCategory.ENTHALPY_FLOW_RELATION,
            }
        ),
        description=(
            "Recuperator thermal element (two-stream internal heat exchange): "
            "requires a recuperator energy balance and an enthalpy-flow relation"
        ),
    )
