"""Hydraulic closure sufficiency diagnostics — Block 15D-A.

Provides lightweight diagnostics for whether a set of hydraulic closure
primitives satisfies the minimum required constraint categories for a given
fixed-topology hydraulic scenario.

This diagnostic is targeted and honest.  It does NOT perform symbolic rank
analysis, DAE analysis, or full linear-algebra coverage checking.  It checks
whether each required closure category has at least one corresponding closure
of the appropriate kind in the provided HydraulicClosureResidualSet.

Supported topology: fixed two-branch parallel topology (Block 15C-A/15C-B).

Required closure categories for the fixed two-branch parallel topology
-----------------------------------------------------------------------
The Block 15C-B parallel topology has two structural degrees of freedom in
the mass-flow subspace:
  1. Total flow level — needs an ImposedMassFlowClosure or equivalent.
  2. Branch split ratio — needs an ImposedBranchSplitClosure or equivalent.

Additionally, before a full solve can proceed:
  3. Pressure reference — needs an ImposedPressureClosure to anchor the
     absolute pressure level (note: Block 15C-B parameters already include
     accumulator_pressure_reference, but as a standalone closure it would
     be an ImposedPressureClosure).
  4. Branch pressure-drop law — at least one LinearPressureDropClosure or
     QuadraticPressureDropClosure (covers the branch resistance model when
     used outside the 15C-B parameterized approach).
  5. Pressure compatibility — a PressureCompatibilityClosure to express
     equality of two explicit caller-supplied linearized path-drop expressions.

Diagnostic verdict
------------------
A diagnostic is considered sufficient if all required categories are
satisfied by at least one closure of the corresponding kind.  The verdict
is honest and conservative:
  - sufficient=True means all required categories have at least one closure.
  - sufficient=False means at least one required category is missing.
  - The diagnostic does NOT claim to verify full algebraic rank or
    guarantee solveability.

Architecture constraints
------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop,
    mpl_sim.solvers, or mpl_sim.network.solver.
MUST NOT import CoolProp or any property engine.
MUST NOT store FluidState, SystemState, mdot values, or pressure values.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT call PropertyBackend, CorrelationRegistry, or
    HeatExchangerModelRegistry.
MUST NOT implement solve(network) or NetworkGraph.solve().
MUST NOT execute production component physics.
MUST NOT perform symbolic rank analysis or DAE analysis.

Exported names
--------------
HydraulicClosureCategory       — enum of named closure categories
HydraulicClosureDiagnostic     — describes required categories for a topology
HydraulicClosureDiagnosticResult — result of a sufficiency check
evaluate_hydraulic_closure_sufficiency — function: diagnostic + closures -> result
make_two_branch_parallel_diagnostic   — factory: standard two-branch diagnostic
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from mpl_sim.network.hydraulic_closures import (
    HydraulicClosureKind,
    HydraulicClosureResidualSet,
)

# ---------------------------------------------------------------------------
# HydraulicClosureCategory
# ---------------------------------------------------------------------------


class HydraulicClosureCategory(str, Enum):
    """Named closure category for diagnostic purposes.

    Each category corresponds to a physical or structural constraint that
    must be present in a closure set before the associated topology can be
    solved.

    TOTAL_FLOW:
        At least one closure fixes or constrains the total loop mass flow.
        Satisfied by: ImposedMassFlowClosure (kind=IMPOSED_MASS_FLOW).
        Missing means: the absolute mass-flow level is undetermined.

    BRANCH_SPLIT:
        At least one closure fixes or constrains the branch flow split.
        Satisfied by: ImposedBranchSplitClosure (kind=IMPOSED_BRANCH_SPLIT).
        Missing means: the fraction of flow through each parallel branch
        is undetermined (cannot predict branch distribution).

    PRESSURE_REFERENCE:
        At least one closure anchors the absolute pressure level.
        Satisfied by: ImposedPressureClosure (kind=IMPOSED_PRESSURE).
        Missing means: the absolute pressure solution is undetermined
        (pressure equations can be shifted by an arbitrary constant).

    BRANCH_PRESSURE_DROP_LAW:
        At least one closure provides an algebraic pressure-drop model
        for a branch element.
        Satisfied by: LinearPressureDropClosure or QuadraticPressureDropClosure.
        Missing means: no algebraic branch resistance law is present.

    PRESSURE_COMPATIBILITY:
        At least one closure asserts equality of two explicit caller-supplied
        linearized path-drop expressions.
        Satisfied by: PressureCompatibilityClosure
                      (kind=PRESSURE_COMPATIBILITY).
        Missing means: this simplified algebraic compatibility category is
        not explicitly represented.
    """

    TOTAL_FLOW = "total_flow"
    BRANCH_SPLIT = "branch_split"
    PRESSURE_REFERENCE = "pressure_reference"
    BRANCH_PRESSURE_DROP_LAW = "branch_pressure_drop_law"
    PRESSURE_COMPATIBILITY = "pressure_compatibility"


# ---------------------------------------------------------------------------
# Category-to-kind mapping (module-private)
# ---------------------------------------------------------------------------

_CATEGORY_TO_KINDS: MappingProxyType[HydraulicClosureCategory, frozenset[HydraulicClosureKind]] = (
    MappingProxyType(
        {
            HydraulicClosureCategory.TOTAL_FLOW: frozenset(
                {HydraulicClosureKind.IMPOSED_MASS_FLOW}
            ),
            HydraulicClosureCategory.BRANCH_SPLIT: frozenset(
                {HydraulicClosureKind.IMPOSED_BRANCH_SPLIT}
            ),
            HydraulicClosureCategory.PRESSURE_REFERENCE: frozenset(
                {HydraulicClosureKind.IMPOSED_PRESSURE}
            ),
            HydraulicClosureCategory.BRANCH_PRESSURE_DROP_LAW: frozenset(
                {
                    HydraulicClosureKind.LINEAR_PRESSURE_DROP,
                    HydraulicClosureKind.QUADRATIC_PRESSURE_DROP,
                }
            ),
            HydraulicClosureCategory.PRESSURE_COMPATIBILITY: frozenset(
                {HydraulicClosureKind.PRESSURE_COMPATIBILITY}
            ),
        }
    )
)

_CATEGORY_MISSING_MESSAGES: MappingProxyType[HydraulicClosureCategory, str] = MappingProxyType(
    {
        HydraulicClosureCategory.TOTAL_FLOW: (
            "total flow not fixed: add an ImposedMassFlowClosure "
            "to fix the absolute mass-flow level"
        ),
        HydraulicClosureCategory.BRANCH_SPLIT: (
            "mass-flow split not determined: add an ImposedBranchSplitClosure "
            "to fix the branch flow fraction (user constraint, not predicted physics)"
        ),
        HydraulicClosureCategory.PRESSURE_REFERENCE: (
            "pressure reference missing: add an ImposedPressureClosure "
            "to anchor the absolute pressure level"
        ),
        HydraulicClosureCategory.BRANCH_PRESSURE_DROP_LAW: (
            "branch pressure-drop law missing: add a LinearPressureDropClosure "
            "or QuadraticPressureDropClosure for at least one branch element"
        ),
        HydraulicClosureCategory.PRESSURE_COMPATIBILITY: (
            "branch pressure compatibility missing: add a PressureCompatibilityClosure "
            "to equate explicit caller-supplied linearized path drops"
        ),
    }
)


# ---------------------------------------------------------------------------
# HydraulicClosureDiagnostic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HydraulicClosureDiagnostic:
    """Describes the required closure categories for a fixed-topology scenario.

    This is a declaration object that specifies which closure categories
    must be present for the associated hydraulic scenario to be considered
    adequately closed for solving.

    Fields
    ------
    required_categories : frozenset of HydraulicClosureCategory values that
                          must be satisfied
    description         : short human-readable description of the topology

    Use make_two_branch_parallel_diagnostic() to build the standard instance
    for the Block 15C-A/15C-B two-branch parallel scenario.
    """

    required_categories: frozenset[HydraulicClosureCategory]
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.required_categories, frozenset):
            raise TypeError(
                "HydraulicClosureDiagnostic.required_categories must be "
                "a frozenset; got "
                f"{type(self.required_categories).__name__!r}"
            )
        for cat in self.required_categories:
            if not isinstance(cat, HydraulicClosureCategory):
                raise TypeError(
                    f"HydraulicClosureDiagnostic.required_categories entries "
                    f"must be HydraulicClosureCategory; got {type(cat).__name__!r}"
                )
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("HydraulicClosureDiagnostic.description must be a non-blank str")


# ---------------------------------------------------------------------------
# HydraulicClosureDiagnosticResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HydraulicClosureDiagnosticResult:
    """Result of evaluating closure sufficiency.

    Produced by evaluate_hydraulic_closure_sufficiency.

    Fields
    ------
    provided_categories : frozenset of satisfied HydraulicClosureCategory values
    missing_categories  : frozenset of unsatisfied HydraulicClosureCategory values
    is_sufficient       : True iff all required categories are satisfied
    closure_names       : tuple of residual names of the provided closures
    missing_messages    : tuple of human-readable descriptions of missing categories

    Notes
    -----
    is_sufficient=True does NOT guarantee algebraic rank or solveability.
    It only means every required category has at least one matching closure.
    Full rank verification is not implemented in Block 15D-A.
    """

    provided_categories: frozenset[HydraulicClosureCategory]
    missing_categories: frozenset[HydraulicClosureCategory]
    is_sufficient: bool
    closure_names: tuple[str, ...]
    missing_messages: tuple[str, ...]


# ---------------------------------------------------------------------------
# evaluate_hydraulic_closure_sufficiency
# ---------------------------------------------------------------------------


def evaluate_hydraulic_closure_sufficiency(
    diagnostic: HydraulicClosureDiagnostic,
    closures: HydraulicClosureResidualSet,
) -> HydraulicClosureDiagnosticResult:
    """Evaluate whether a closure set satisfies all required categories.

    For each required category in the diagnostic, checks whether at least
    one closure in the set has a kind that satisfies that category.

    Parameters
    ----------
    diagnostic:
        A HydraulicClosureDiagnostic declaring the required categories.
    closures:
        A HydraulicClosureResidualSet to evaluate.

    Returns
    -------
    HydraulicClosureDiagnosticResult with provided/missing categories,
    sufficiency verdict, closure names, and human-readable missing messages.

    Notes
    -----
    This function does not evaluate residual values and does not require
    an unknown-value vector.  It only inspects closure kinds.
    """
    if not isinstance(diagnostic, HydraulicClosureDiagnostic):
        raise TypeError(
            "evaluate_hydraulic_closure_sufficiency: diagnostic must be "
            "a HydraulicClosureDiagnostic; got "
            f"{type(diagnostic).__name__!r}"
        )
    if not isinstance(closures, HydraulicClosureResidualSet):
        raise TypeError(
            "evaluate_hydraulic_closure_sufficiency: closures must be "
            "a HydraulicClosureResidualSet; got "
            f"{type(closures).__name__!r}"
        )

    provided_kinds: frozenset[HydraulicClosureKind] = frozenset(c.kind for c in closures.closures)

    provided_categories: set[HydraulicClosureCategory] = set()
    missing_categories: set[HydraulicClosureCategory] = set()
    missing_messages: list[str] = []

    for cat in sorted(diagnostic.required_categories, key=lambda c: c.value):
        satisfying_kinds = _CATEGORY_TO_KINDS[cat]
        if provided_kinds & satisfying_kinds:
            provided_categories.add(cat)
        else:
            missing_categories.add(cat)
            missing_messages.append(_CATEGORY_MISSING_MESSAGES[cat])

    is_sufficient = len(missing_categories) == 0

    return HydraulicClosureDiagnosticResult(
        provided_categories=frozenset(provided_categories),
        missing_categories=frozenset(missing_categories),
        is_sufficient=is_sufficient,
        closure_names=tuple(c.residual_name for c in closures.closures),
        missing_messages=tuple(missing_messages),
    )


# ---------------------------------------------------------------------------
# make_two_branch_parallel_diagnostic
# ---------------------------------------------------------------------------


def make_two_branch_parallel_diagnostic() -> HydraulicClosureDiagnostic:
    """Return the standard diagnostic for the fixed two-branch parallel topology.

    This diagnostic targets the Block 15C-A/15C-B fixed two-branch parallel
    scenario (accumulator -> pump -> [branch_a / branch_b] -> condenser).

    Required categories:
      - TOTAL_FLOW            : fixes the underdetermined total flow level
      - BRANCH_SPLIT          : fixes the underdetermined branch split ratio
      - PRESSURE_REFERENCE    : anchors the absolute pressure level
      - BRANCH_PRESSURE_DROP_LAW : provides an algebraic resistance model
      - PRESSURE_COMPATIBILITY   : equates explicit linearized path drops

    Note: Block 15C-B already includes parameterized pressure residuals for
    all elements.  This category-presence diagnostic does not decide which
    equations should supplement or replace those residuals, and it does not
    validate a combined equation count or algebraic rank.
    """
    return HydraulicClosureDiagnostic(
        required_categories=frozenset(
            {
                HydraulicClosureCategory.TOTAL_FLOW,
                HydraulicClosureCategory.BRANCH_SPLIT,
                HydraulicClosureCategory.PRESSURE_REFERENCE,
                HydraulicClosureCategory.BRANCH_PRESSURE_DROP_LAW,
                HydraulicClosureCategory.PRESSURE_COMPATIBILITY,
            }
        ),
        description=(
            "Fixed two-branch parallel topology (Block 15C-A/15C-B scenario): "
            "accumulator -> pump -> [branch_a / branch_b] -> condenser"
        ),
    )
