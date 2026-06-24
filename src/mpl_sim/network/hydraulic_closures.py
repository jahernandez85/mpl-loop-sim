"""Hydraulic closure primitives — Block 15D-A.

Provides explicit algebraic closure equations for hydraulic networks.
All closures are pure algebraic: no property lookups, no CoolProp, no
correlations, no HX models, no SystemState, no FluidState, no production
component execution.

Closures can supply missing constraint equations for a later, explicitly
assembled hydraulic solve.  This module only declares and evaluates those
equations; it does not assemble or solve a combined network system.

Closure equations and sign conventions
---------------------------------------

ImposedMassFlowClosure:
    r = mdot_unknown - imposed_value
    Zero iff the named mass-flow unknown equals imposed_value.

ImposedBranchSplitClosure:
    r = mdot_branch - split_fraction * mdot_total
    Zero iff the named branch flow is the stated fraction of the total flow.
    split_fraction must satisfy 0 < split_fraction < 1 (strict, exclusive).

ImposedPressureClosure:
    r = P_unknown - imposed_value
    Zero iff the named pressure unknown equals imposed_value.

LinearPressureDropClosure:
    r = P_in - P_out - resistance * mdot
    Zero iff inlet pressure exceeds outlet pressure by resistance * mdot.
    resistance must be non-negative.

QuadraticPressureDropClosure:
    r = P_in - P_out - coefficient * mdot * |mdot|
    Zero iff inlet pressure exceeds outlet pressure by coefficient * mdot^2.
    coefficient must be non-negative.  Sign of mdot is preserved in the
    quadratic term so the closure is consistent for reverse flow.

PressureCompatibilityClosure:
    r = resistance_a * mdot_a - resistance_b * mdot_b
    Zero iff two caller-supplied linearized path-drop expressions are equal.
    This is a simplified algebraic compatibility closure, not a general
    parallel-manifold pressure equation.
    Both resistance values must be non-negative.

Architecture constraints
------------------------
MUST NOT import mpl_sim.components, mpl_sim.properties, mpl_sim.correlations,
    mpl_sim.calibration, mpl_sim.hx_models, mpl_sim.closed_loop,
    mpl_sim.solvers, or mpl_sim.network.solver.
MUST NOT import CoolProp or any property engine.
MUST NOT store FluidState, SystemState, mdot values, pressure values, or
    enthalpy values in structural objects.
MUST NOT call contribute(...) or define a method named contribute.
MUST NOT call PropertyBackend, CorrelationRegistry, or
    HeatExchangerModelRegistry.
MUST NOT implement solve(network) or NetworkGraph.solve().
MUST NOT execute production component physics.
MUST NOT infer physics from component_type.
MUST NOT write files or depend on pandas, matplotlib, or numpy.
MUST NOT implement Darcy-Weisbach, Friedel, Gnielinski, Shah, or any
    fluid-property-dependent model.

Exported names
--------------
HydraulicClosureKind             — enum of closure types
HydraulicClosureDeclaration      — Union type alias for all closure objects
ImposedMassFlowClosure           — frozen: fix a mass-flow unknown to a value
ImposedBranchSplitClosure        — frozen: fix branch flow as fraction of total
ImposedPressureClosure           — frozen: fix a pressure unknown to a value
LinearPressureDropClosure        — frozen: linear P_in - P_out = R * mdot
QuadraticPressureDropClosure     — frozen: quadratic P_in - P_out = C * mdot|mdot|
PressureCompatibilityClosure     — frozen: equal path drops for two branches
HydraulicClosureResidualSet      — ordered, duplicate-rejecting closure set
build_hydraulic_closure_residuals — factory: closures -> HydraulicClosureResidualSet
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

# ---------------------------------------------------------------------------
# Validation helpers (module-private)
# ---------------------------------------------------------------------------


def _require_non_empty_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a str; got {type(value).__name__!r}")
    if not value.strip():
        raise ValueError(f"{field} must not be blank")
    return value


def _require_finite_float(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field} must not be bool")
    if not isinstance(value, (int, float)):
        raise TypeError(
            f"{field} must be a real numeric (int or float); " f"got {type(value).__name__!r}"
        )
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite; got {value!r}")
    return float(value)


def _require_non_negative_finite_float(value: object, field: str) -> float:
    v = _require_finite_float(value, field)
    if v < 0.0:
        raise ValueError(f"{field} must be non-negative; got {v!r}")
    return v


def _require_unknown(unknowns: Mapping[str, float], name: str, closure_type: str) -> float:
    if name not in unknowns:
        raise KeyError(f"{closure_type}: unknown '{name}' not found in unknowns mapping")
    v = unknowns[name]
    if isinstance(v, bool):
        raise TypeError(f"{closure_type}: unknown '{name}' must not be bool")
    if not isinstance(v, (int, float)):
        raise TypeError(
            f"{closure_type}: unknown '{name}' must be numeric; " f"got {type(v).__name__!r}"
        )
    if not math.isfinite(v):
        raise ValueError(f"{closure_type}: unknown '{name}' must be finite; got {v!r}")
    return float(v)


# ---------------------------------------------------------------------------
# HydraulicClosureKind
# ---------------------------------------------------------------------------


class HydraulicClosureKind(str, Enum):
    """Identifies the type of a hydraulic closure equation.

    Used by diagnostics to determine which constraint categories are satisfied.
    """

    IMPOSED_MASS_FLOW = "imposed_mass_flow"
    IMPOSED_BRANCH_SPLIT = "imposed_branch_split"
    IMPOSED_PRESSURE = "imposed_pressure"
    LINEAR_PRESSURE_DROP = "linear_pressure_drop"
    QUADRATIC_PRESSURE_DROP = "quadratic_pressure_drop"
    PRESSURE_COMPATIBILITY = "pressure_compatibility"


# ---------------------------------------------------------------------------
# ImposedMassFlowClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImposedMassFlowClosure:
    """Fix one mass-flow unknown to an explicitly imposed value.

    Residual equation:
        r = mdot_unknown - imposed_value

    Zero iff the named mass-flow unknown equals imposed_value.

    Use cases:
      - Fix total loop mass flow.
      - Fix a branch mass flow.
      - Provide a gauge (underdetermined system DOF removal).

    Validation:
      - unknown_name must be a non-blank str.
      - residual_name must be a non-blank str.
      - imposed_value must be a finite real scalar (not bool, not NaN, not inf).
      - Sign: imposed_value may be negative (caller's responsibility).
    """

    unknown_name: str
    imposed_value: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unknown_name",
            _require_non_empty_str(self.unknown_name, "ImposedMassFlowClosure.unknown_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(self.residual_name, "ImposedMassFlowClosure.residual_name"),
        )
        object.__setattr__(
            self,
            "imposed_value",
            _require_finite_float(self.imposed_value, "ImposedMassFlowClosure.imposed_value"),
        )

    @property
    def kind(self) -> HydraulicClosureKind:
        return HydraulicClosureKind.IMPOSED_MASS_FLOW

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        v = _require_unknown(unknowns, self.unknown_name, "ImposedMassFlowClosure")
        return v - self.imposed_value


# ---------------------------------------------------------------------------
# ImposedBranchSplitClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImposedBranchSplitClosure:
    """Fix one branch flow to an explicit fraction of a total flow unknown.

    Residual equation:
        r = mdot_branch - split_fraction * mdot_total

    Zero iff the branch flow is exactly split_fraction of the total flow.

    This is a user-imposed constraint, NOT predicted physics.  The caller
    must explicitly supply the split fraction; this module does not compute
    or infer a physical flow distribution.

    Use cases:
      - Force a known branch split for testing.
      - Apply an external operating constraint.
      - Close one DOF in an underdetermined two-branch system.

    Validation:
      - total_flow_name and branch_flow_name must be non-blank str.
      - residual_name must be a non-blank str.
      - split_fraction must be a finite real scalar, 0 < split_fraction < 1
        (strict; endpoint fractions 0 and 1 are rejected as degenerate).
    """

    total_flow_name: str
    branch_flow_name: str
    split_fraction: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "total_flow_name",
            _require_non_empty_str(
                self.total_flow_name, "ImposedBranchSplitClosure.total_flow_name"
            ),
        )
        object.__setattr__(
            self,
            "branch_flow_name",
            _require_non_empty_str(
                self.branch_flow_name, "ImposedBranchSplitClosure.branch_flow_name"
            ),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(self.residual_name, "ImposedBranchSplitClosure.residual_name"),
        )
        f = _require_finite_float(self.split_fraction, "ImposedBranchSplitClosure.split_fraction")
        if not (0.0 < f < 1.0):
            raise ValueError(
                f"ImposedBranchSplitClosure.split_fraction must satisfy "
                f"0 < split_fraction < 1 (strict); got {f!r}"
            )
        object.__setattr__(self, "split_fraction", f)

    @property
    def kind(self) -> HydraulicClosureKind:
        return HydraulicClosureKind.IMPOSED_BRANCH_SPLIT

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        mdot_branch = _require_unknown(unknowns, self.branch_flow_name, "ImposedBranchSplitClosure")
        mdot_total = _require_unknown(unknowns, self.total_flow_name, "ImposedBranchSplitClosure")
        return mdot_branch - self.split_fraction * mdot_total


# ---------------------------------------------------------------------------
# ImposedPressureClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImposedPressureClosure:
    """Fix one pressure unknown to an explicitly imposed value.

    Residual equation:
        r = P_unknown - imposed_value

    Zero iff the named pressure unknown equals imposed_value.

    Use cases:
      - Set an accumulator or reservoir reference pressure.
      - Provide a boundary condition pressure.

    Validation:
      - unknown_name must be a non-blank str.
      - residual_name must be a non-blank str.
      - imposed_value must be a finite real scalar (not bool, not NaN, not inf).
      - No property calls; imposed_value is an explicit algebraic parameter.
    """

    unknown_name: str
    imposed_value: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unknown_name",
            _require_non_empty_str(self.unknown_name, "ImposedPressureClosure.unknown_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(self.residual_name, "ImposedPressureClosure.residual_name"),
        )
        object.__setattr__(
            self,
            "imposed_value",
            _require_finite_float(self.imposed_value, "ImposedPressureClosure.imposed_value"),
        )

    @property
    def kind(self) -> HydraulicClosureKind:
        return HydraulicClosureKind.IMPOSED_PRESSURE

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        v = _require_unknown(unknowns, self.unknown_name, "ImposedPressureClosure")
        return v - self.imposed_value


# ---------------------------------------------------------------------------
# LinearPressureDropClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinearPressureDropClosure:
    """Linear algebraic pressure-drop closure.

    Residual equation:
        r = P_in - P_out - resistance * mdot

    Zero iff inlet pressure exceeds outlet pressure by resistance * mdot.

    This is a purely algebraic linear resistance model.  It is NOT
    Darcy-Weisbach, not friction-factor-based, and does not call any
    fluid property or correlation.  The resistance coefficient is an
    explicit algebraic parameter.

    Sign convention:
      - Positive mdot flows from P_in to P_out.
      - resistance >= 0 by construction; negative resistance is rejected.
      - At solution: P_in - P_out = resistance * mdot.

    Validation:
      - p_in_name, p_out_name, mdot_name, residual_name must be non-blank str.
      - resistance must be a finite, non-negative real scalar.
    """

    p_in_name: str
    p_out_name: str
    mdot_name: str
    resistance: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "p_in_name",
            _require_non_empty_str(self.p_in_name, "LinearPressureDropClosure.p_in_name"),
        )
        object.__setattr__(
            self,
            "p_out_name",
            _require_non_empty_str(self.p_out_name, "LinearPressureDropClosure.p_out_name"),
        )
        object.__setattr__(
            self,
            "mdot_name",
            _require_non_empty_str(self.mdot_name, "LinearPressureDropClosure.mdot_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(self.residual_name, "LinearPressureDropClosure.residual_name"),
        )
        object.__setattr__(
            self,
            "resistance",
            _require_non_negative_finite_float(
                self.resistance, "LinearPressureDropClosure.resistance"
            ),
        )

    @property
    def kind(self) -> HydraulicClosureKind:
        return HydraulicClosureKind.LINEAR_PRESSURE_DROP

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        p_in = _require_unknown(unknowns, self.p_in_name, "LinearPressureDropClosure")
        p_out = _require_unknown(unknowns, self.p_out_name, "LinearPressureDropClosure")
        mdot = _require_unknown(unknowns, self.mdot_name, "LinearPressureDropClosure")
        return p_in - p_out - self.resistance * mdot


# ---------------------------------------------------------------------------
# QuadraticPressureDropClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuadraticPressureDropClosure:
    """Quadratic algebraic pressure-drop closure.

    Residual equation:
        r = P_in - P_out - coefficient * mdot * abs(mdot)

    Zero iff inlet pressure exceeds outlet pressure by coefficient * mdot^2
    (using the sign-preserving form so reverse flow is consistent).

    This is a purely algebraic quadratic resistance model.  It is NOT
    correlation-backed, not property-backed.  The coefficient is an
    explicit algebraic parameter.

    Sign convention:
      - coefficient >= 0 by construction.
      - mdot * abs(mdot) is sign-preserving: positive for forward flow,
        negative for reverse flow.
      - At solution: P_in - P_out = coefficient * mdot * |mdot|.

    Validation:
      - p_in_name, p_out_name, mdot_name, residual_name must be non-blank str.
      - coefficient must be a finite, non-negative real scalar.
    """

    p_in_name: str
    p_out_name: str
    mdot_name: str
    coefficient: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "p_in_name",
            _require_non_empty_str(self.p_in_name, "QuadraticPressureDropClosure.p_in_name"),
        )
        object.__setattr__(
            self,
            "p_out_name",
            _require_non_empty_str(self.p_out_name, "QuadraticPressureDropClosure.p_out_name"),
        )
        object.__setattr__(
            self,
            "mdot_name",
            _require_non_empty_str(self.mdot_name, "QuadraticPressureDropClosure.mdot_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(
                self.residual_name, "QuadraticPressureDropClosure.residual_name"
            ),
        )
        object.__setattr__(
            self,
            "coefficient",
            _require_non_negative_finite_float(
                self.coefficient, "QuadraticPressureDropClosure.coefficient"
            ),
        )

    @property
    def kind(self) -> HydraulicClosureKind:
        return HydraulicClosureKind.QUADRATIC_PRESSURE_DROP

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        p_in = _require_unknown(unknowns, self.p_in_name, "QuadraticPressureDropClosure")
        p_out = _require_unknown(unknowns, self.p_out_name, "QuadraticPressureDropClosure")
        mdot = _require_unknown(unknowns, self.mdot_name, "QuadraticPressureDropClosure")
        return p_in - p_out - self.coefficient * mdot * abs(mdot)


# ---------------------------------------------------------------------------
# PressureCompatibilityClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PressureCompatibilityClosure:
    """Simplified linearized compatibility for two parallel branch paths.

    Asserts that the total pressure drop along path A equals the total
    pressure drop along path B, using explicit effective resistance
    coefficients (Pa/(kg/s)):

        r = resistance_a * mdot_a - resistance_b * mdot_b

    Zero iff the two explicit linearized path-drop expressions are equal.
    This is not a general pressure-compatibility equation and does not inspect
    branch topology or hidden branch laws.

    Use case:
      For a two-branch parallel architecture where both branches connect the
      same split node to the same merge node, this closure can represent equal
      path drops only when the caller intentionally models both complete paths
      with compatible linearized resistance expressions.

      resistance_a and resistance_b are caller-supplied linear coefficients.
      Their units and physical interpretation are the caller's responsibility.
      This module does not compute, infer, or validate them against components,
      properties, correlations, or topology.

    Sign convention:
      - Both resistances must be non-negative.
      - mdot_a and mdot_b are positive for flow in the forward direction.
      - At solution: resistance_a * mdot_a == resistance_b * mdot_b.

    Validation:
      - mdot_a_name, mdot_b_name, residual_name must be non-blank str.
      - resistance_a and resistance_b must be finite non-negative real scalars.
    """

    mdot_a_name: str
    mdot_b_name: str
    resistance_a: float
    resistance_b: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mdot_a_name",
            _require_non_empty_str(self.mdot_a_name, "PressureCompatibilityClosure.mdot_a_name"),
        )
        object.__setattr__(
            self,
            "mdot_b_name",
            _require_non_empty_str(self.mdot_b_name, "PressureCompatibilityClosure.mdot_b_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(
                self.residual_name, "PressureCompatibilityClosure.residual_name"
            ),
        )
        object.__setattr__(
            self,
            "resistance_a",
            _require_non_negative_finite_float(
                self.resistance_a, "PressureCompatibilityClosure.resistance_a"
            ),
        )
        object.__setattr__(
            self,
            "resistance_b",
            _require_non_negative_finite_float(
                self.resistance_b, "PressureCompatibilityClosure.resistance_b"
            ),
        )

    @property
    def kind(self) -> HydraulicClosureKind:
        return HydraulicClosureKind.PRESSURE_COMPATIBILITY

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        mdot_a = _require_unknown(unknowns, self.mdot_a_name, "PressureCompatibilityClosure")
        mdot_b = _require_unknown(unknowns, self.mdot_b_name, "PressureCompatibilityClosure")
        return self.resistance_a * mdot_a - self.resistance_b * mdot_b


# ---------------------------------------------------------------------------
# HydraulicClosureDeclaration union type alias
# ---------------------------------------------------------------------------

HydraulicClosureDeclaration = (
    ImposedMassFlowClosure
    | ImposedBranchSplitClosure
    | ImposedPressureClosure
    | LinearPressureDropClosure
    | QuadraticPressureDropClosure
    | PressureCompatibilityClosure
)
"""Union of all concrete hydraulic closure types.

Use this alias as the type annotation for collections of mixed closures.
"""


# ---------------------------------------------------------------------------
# HydraulicClosureResidualSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HydraulicClosureResidualSet:
    """Ordered, duplicate-name-rejecting collection of hydraulic closures.

    Produced by build_hydraulic_closure_residuals.  Provides:
      - an ordered tuple of closure objects;
      - residual name lookup (unique names enforced at build time);
      - evaluate_all: evaluates all closure residuals at a given unknown vector;
      - optional caller metadata (defensively copied).

    All residual names are unique within this set.

    Fields
    ------
    closures   : tuple of HydraulicClosureDeclaration objects (ordered)
    metadata   : optional caller metadata; defensively copied at build time

    Properties
    ----------
    residual_names : tuple[str, ...] — ordered residual names

    Methods
    -------
    evaluate_all(unknowns) -> MappingProxyType[str, float]
        Evaluate all closures at the given unknown vector and return a
        read-only mapping of residual_name -> float.  All required unknowns
        must be present and finite.  Extra unknowns are silently ignored.
    """

    closures: tuple[HydraulicClosureDeclaration, ...]
    metadata: MappingProxyType[str, object] | None

    @property
    def residual_names(self) -> tuple[str, ...]:
        return tuple(c.residual_name for c in self.closures)

    def evaluate_all(self, unknowns: Mapping[str, float]) -> MappingProxyType[str, float]:
        """Evaluate all closures and return a read-only residual map."""
        result: dict[str, float] = {}
        for closure in self.closures:
            value = closure.evaluate(unknowns)
            if not math.isfinite(value):
                raise ValueError(
                    f"HydraulicClosureResidualSet: closure '{closure.residual_name}' "
                    f"returned non-finite residual {value!r}"
                )
            result[closure.residual_name] = value
        return MappingProxyType(result)


# ---------------------------------------------------------------------------
# build_hydraulic_closure_residuals
# ---------------------------------------------------------------------------


def build_hydraulic_closure_residuals(
    closures: Iterable[HydraulicClosureDeclaration],
    *,
    metadata: Mapping[str, object] | None = None,
) -> HydraulicClosureResidualSet:
    """Build a validated HydraulicClosureResidualSet from an iterable of closures.

    Parameters
    ----------
    closures:
        An iterable of HydraulicClosureDeclaration objects.  Must be
        non-empty.  Duplicate residual names are rejected.
    metadata:
        Optional caller-supplied metadata.  Defensively copied as
        MappingProxyType.  Keys must be str.

    Returns
    -------
    HydraulicClosureResidualSet

    Raises
    ------
    TypeError  — if any closure is not a recognized HydraulicClosureDeclaration
    ValueError — if the closure list is empty or duplicate residual names exist
    """
    _valid_types = (
        ImposedMassFlowClosure,
        ImposedBranchSplitClosure,
        ImposedPressureClosure,
        LinearPressureDropClosure,
        QuadraticPressureDropClosure,
        PressureCompatibilityClosure,
    )
    collected: list[HydraulicClosureDeclaration] = []
    seen_names: set[str] = set()
    for i, c in enumerate(closures):
        if not isinstance(c, _valid_types):
            raise TypeError(
                f"build_hydraulic_closure_residuals: item at index {i} is not a "
                f"recognized HydraulicClosureDeclaration; got {type(c).__name__!r}"
            )
        if c.residual_name in seen_names:
            raise ValueError(
                f"build_hydraulic_closure_residuals: duplicate residual name "
                f"'{c.residual_name}' at index {i}"
            )
        seen_names.add(c.residual_name)
        collected.append(c)

    if not collected:
        raise ValueError("build_hydraulic_closure_residuals: closures must not be empty")

    meta_proxy: MappingProxyType[str, object] | None = None
    if metadata is not None:
        meta_proxy = MappingProxyType(dict(metadata))

    return HydraulicClosureResidualSet(
        closures=tuple(collected),
        metadata=meta_proxy,
    )
