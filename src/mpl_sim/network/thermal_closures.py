"""Thermal closure primitives — Block 15D-B.

Provides explicit algebraic closure equations for thermal (energy-side) networks.
All closures are pure algebraic: no property lookups, no CoolProp, no correlations,
no HX models, no SystemState, no FluidState, no production component execution,
no saturation/phase/quality logic, no enthalpy-temperature conversion.

Imposed enthalpy and temperature-like closures are user-imposed scalar constraints,
not thermodynamic property calculations.  Sensible heat and enthalpy-flow closures
are explicit algebraic relations with caller-supplied values.  Effectiveness and
recuperator closures, where implemented, do not represent real HX models.

Closures can supply missing constraint equations for a later, explicitly assembled
thermal solve.  This module only declares and evaluates those equations; it does
not assemble or solve a combined network system.

Closure equations and sign conventions
---------------------------------------

FixedHeatRateClosure:
    r = q_unknown - q_fixed
    Zero iff the named heat-rate unknown equals q_fixed.
    Sign: positive q_fixed means heat added to the stream.

ImposedEnthalpyClosure:
    r = h_unknown - h_imposed
    Zero iff the named enthalpy unknown equals h_imposed.
    h_imposed is a user-supplied scalar (J/kg); not a property calculation.

ImposedTemperatureLikeClosure:
    r = theta_unknown - theta_imposed
    Zero iff the named scalar unknown equals theta_imposed.
    This is a symbolic scalar closure only.  theta_imposed is a user-supplied
    scalar, NOT a thermodynamic temperature computed from properties.
    No CoolProp, no enthalpy-temperature conversion.

SensibleHeatRateClosure:
    r = q - mdot * cp * (theta_out - theta_in)
    Zero iff the heat rate equals mdot * cp * delta_theta.
    cp is an explicit, positive, caller-supplied scalar (J/(kg·K)).
    No property lookup; no automatic cp calculation; no CoolProp.
    Sign: positive (theta_out - theta_in) and positive mdot yield positive q.

EnthalpyFlowHeatRateClosure:
    r = q - mdot * (h_out - h_in)
    Zero iff the heat rate equals the enthalpy-flow difference.
    No phase logic; no property backend.
    Sign: positive (h_out - h_in) and positive mdot yield positive q.

EffectivenessHeatRateClosure:
    r = q - effectiveness * q_max
    Zero iff the heat rate equals effectiveness times the maximum heat rate.
    effectiveness is a structural parameter satisfying 0 <= effectiveness <= 1.
    q and q_max are unknowns supplied by the caller.
    This is NOT a real HX effectiveness-NTU model; it is a purely algebraic
    constraint with a user-supplied effectiveness scalar.

RecuperatorEnergyBalanceClosure:
    r = q_hot + q_cold
    Zero iff the signed hot-side and cold-side heat rates sum to zero.
    Sign convention: q_hot < 0 (heat given up by hot stream), q_cold > 0
    (heat received by cold stream).  At energy balance: q_hot + q_cold = 0.
    No heat-transfer coefficient, area, UA, LMTD, NTU, or property call.

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
MUST NOT implement saturation, quality, phase, or refrigerant thermodynamics.
MUST NOT implement LMTD, NTU, UA, HTC correlations, or real HX model logic.
MUST NOT write files or depend on pandas, matplotlib, or numpy.

Exported names
--------------
ThermalClosureKind             — enum of closure types
ThermalClosureDeclaration      — Union type alias for all closure objects
FixedHeatRateClosure           — frozen: fix a heat-rate unknown to a value
ImposedEnthalpyClosure         — frozen: fix an enthalpy unknown to a value
ImposedTemperatureLikeClosure  — frozen: fix a scalar thermal unknown to a value
SensibleHeatRateClosure        — frozen: q = mdot * cp * (theta_out - theta_in)
EnthalpyFlowHeatRateClosure    — frozen: q = mdot * (h_out - h_in)
EffectivenessHeatRateClosure   — frozen: q = effectiveness * q_max
RecuperatorEnergyBalanceClosure — frozen: q_hot + q_cold = 0
ThermalClosureResidualSet      — ordered, duplicate-rejecting closure set
build_thermal_closure_residuals — factory: closures -> ThermalClosureResidualSet
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
            f"{field} must be a real numeric (int or float); got {type(value).__name__!r}"
        )
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite; got {value!r}")
    return float(value)


def _require_positive_finite_float(value: object, field: str) -> float:
    v = _require_finite_float(value, field)
    if v <= 0.0:
        raise ValueError(f"{field} must be positive; got {v!r}")
    return v


def _require_effectiveness(value: object, field: str) -> float:
    v = _require_finite_float(value, field)
    if not (0.0 <= v <= 1.0):
        raise ValueError(f"{field} must satisfy 0 <= effectiveness <= 1; got {v!r}")
    return v


def _require_unknown(unknowns: Mapping[str, float], name: str, closure_type: str) -> float:
    if name not in unknowns:
        raise KeyError(f"{closure_type}: unknown '{name}' not found in unknowns mapping")
    v = unknowns[name]
    if isinstance(v, bool):
        raise TypeError(f"{closure_type}: unknown '{name}' must not be bool")
    if not isinstance(v, (int, float)):
        raise TypeError(
            f"{closure_type}: unknown '{name}' must be numeric; got {type(v).__name__!r}"
        )
    if not math.isfinite(v):
        raise ValueError(f"{closure_type}: unknown '{name}' must be finite; got {v!r}")
    return float(v)


# ---------------------------------------------------------------------------
# ThermalClosureKind
# ---------------------------------------------------------------------------


class ThermalClosureKind(str, Enum):
    """Identifies the type of a thermal closure equation.

    Used by diagnostics to determine which constraint categories are satisfied.
    """

    FIXED_HEAT_RATE = "fixed_heat_rate"
    IMPOSED_ENTHALPY = "imposed_enthalpy"
    IMPOSED_TEMPERATURE_LIKE = "imposed_temperature_like"
    SENSIBLE_HEAT_RATE = "sensible_heat_rate"
    ENTHALPY_FLOW_HEAT_RATE = "enthalpy_flow_heat_rate"
    EFFECTIVENESS_HEAT_RATE = "effectiveness_heat_rate"
    RECUPERATOR_ENERGY_BALANCE = "recuperator_energy_balance"


# ---------------------------------------------------------------------------
# FixedHeatRateClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixedHeatRateClosure:
    """Fix one heat-rate unknown to an explicitly imposed value.

    Residual equation:
        r = q_unknown - q_fixed

    Zero iff the named heat-rate unknown equals q_fixed.

    Use cases:
      - Electrical heater with known power.
      - Imposed heat input or heat rejection.
      - Test fixture heat source.

    Sign convention:
      - Positive q_fixed means heat added to the fluid stream.
      - q_fixed may be negative (heat rejection from stream).
      - Sign is the caller's responsibility; no automatic sign inference.

    Validation:
      - unknown_name must be a non-blank str.
      - residual_name must be a non-blank str.
      - q_fixed must be a finite real scalar (not bool, not NaN, not inf).
      - No property calls; q_fixed is an explicit algebraic parameter.
      - No production component execution.
    """

    unknown_name: str
    q_fixed: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unknown_name",
            _require_non_empty_str(self.unknown_name, "FixedHeatRateClosure.unknown_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(self.residual_name, "FixedHeatRateClosure.residual_name"),
        )
        object.__setattr__(
            self,
            "q_fixed",
            _require_finite_float(self.q_fixed, "FixedHeatRateClosure.q_fixed"),
        )

    @property
    def kind(self) -> ThermalClosureKind:
        return ThermalClosureKind.FIXED_HEAT_RATE

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        v = _require_unknown(unknowns, self.unknown_name, "FixedHeatRateClosure")
        return v - self.q_fixed


# ---------------------------------------------------------------------------
# ImposedEnthalpyClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImposedEnthalpyClosure:
    """Fix one enthalpy unknown to a user-imposed scalar value.

    Residual equation:
        r = h_unknown - h_imposed

    Zero iff the named enthalpy unknown equals h_imposed.

    This is a user-imposed scalar constraint, NOT a thermodynamic property
    calculation.  h_imposed is an explicit algebraic parameter supplied by
    the caller.  No FluidState, no property lookup, no saturation logic,
    no phase logic, no CoolProp.

    Use cases:
      - Boundary enthalpy (inlet or outlet).
      - Imposed target outlet enthalpy.
      - Algebraic test closure.

    Validation:
      - unknown_name must be a non-blank str.
      - residual_name must be a non-blank str.
      - h_imposed must be a finite real scalar (not bool, not NaN, not inf).
    """

    unknown_name: str
    h_imposed: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unknown_name",
            _require_non_empty_str(self.unknown_name, "ImposedEnthalpyClosure.unknown_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(self.residual_name, "ImposedEnthalpyClosure.residual_name"),
        )
        object.__setattr__(
            self,
            "h_imposed",
            _require_finite_float(self.h_imposed, "ImposedEnthalpyClosure.h_imposed"),
        )

    @property
    def kind(self) -> ThermalClosureKind:
        return ThermalClosureKind.IMPOSED_ENTHALPY

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        v = _require_unknown(unknowns, self.unknown_name, "ImposedEnthalpyClosure")
        return v - self.h_imposed


# ---------------------------------------------------------------------------
# ImposedTemperatureLikeClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImposedTemperatureLikeClosure:
    """Fix one symbolic thermal scalar unknown to a user-imposed value.

    Residual equation:
        r = theta_unknown - theta_imposed

    Zero iff the named scalar unknown equals theta_imposed.

    IMPORTANT: This is a symbolic scalar closure only.  theta_imposed is a
    user-supplied scalar, NOT a thermodynamic temperature computed from fluid
    properties.  No CoolProp, no enthalpy-temperature conversion, no property
    lookup, no FluidState, no SystemState.

    Use cases:
      - Impose a reference temperature-like scalar for algebraic testing.
      - Close one DOF in a symbolic thermal scenario.
      - Impose a boundary condition scalar (caller's responsibility to ensure
        physical consistency outside this module).

    Validation:
      - unknown_name must be a non-blank str.
      - residual_name must be a non-blank str.
      - theta_imposed must be a finite real scalar (not bool, not NaN, not inf).
    """

    unknown_name: str
    theta_imposed: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unknown_name",
            _require_non_empty_str(self.unknown_name, "ImposedTemperatureLikeClosure.unknown_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(
                self.residual_name, "ImposedTemperatureLikeClosure.residual_name"
            ),
        )
        object.__setattr__(
            self,
            "theta_imposed",
            _require_finite_float(
                self.theta_imposed, "ImposedTemperatureLikeClosure.theta_imposed"
            ),
        )

    @property
    def kind(self) -> ThermalClosureKind:
        return ThermalClosureKind.IMPOSED_TEMPERATURE_LIKE

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        v = _require_unknown(unknowns, self.unknown_name, "ImposedTemperatureLikeClosure")
        return v - self.theta_imposed


# ---------------------------------------------------------------------------
# SensibleHeatRateClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SensibleHeatRateClosure:
    """Algebraic sensible heat-rate relation.

    Residual equation:
        r = q - mdot * cp * (theta_out - theta_in)

    Zero iff the heat rate equals mdot * cp * (theta_out - theta_in).

    This is a purely algebraic explicit relation.  cp is an explicit,
    caller-supplied, positive scalar.  No property lookup, no automatic cp
    calculation, no CoolProp, no FluidState.

    Sign convention:
      - Positive (theta_out - theta_in) and positive mdot yield positive q
        (heat added to the stream).
      - Negative (theta_out - theta_in) yields negative q (heat removed).
      - Sign of q and mdot are the caller's responsibility.

    Use cases:
      - Explicit algebraic model for single-phase sensible heat exchange.
      - Symbolic thermal scenario with user-supplied cp.
      - Algebraic preheater or cooler closure.

    Validation:
      - q_name, mdot_name, theta_in_name, theta_out_name, residual_name:
        all must be non-blank str.
      - cp must be a finite, positive real scalar (>0); not bool, not NaN,
        not inf, not zero.
      - No property calls; cp is an explicit algebraic parameter.
    """

    q_name: str
    mdot_name: str
    theta_in_name: str
    theta_out_name: str
    cp: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "q_name",
            _require_non_empty_str(self.q_name, "SensibleHeatRateClosure.q_name"),
        )
        object.__setattr__(
            self,
            "mdot_name",
            _require_non_empty_str(self.mdot_name, "SensibleHeatRateClosure.mdot_name"),
        )
        object.__setattr__(
            self,
            "theta_in_name",
            _require_non_empty_str(self.theta_in_name, "SensibleHeatRateClosure.theta_in_name"),
        )
        object.__setattr__(
            self,
            "theta_out_name",
            _require_non_empty_str(self.theta_out_name, "SensibleHeatRateClosure.theta_out_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(self.residual_name, "SensibleHeatRateClosure.residual_name"),
        )
        object.__setattr__(
            self,
            "cp",
            _require_positive_finite_float(self.cp, "SensibleHeatRateClosure.cp"),
        )

    @property
    def kind(self) -> ThermalClosureKind:
        return ThermalClosureKind.SENSIBLE_HEAT_RATE

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        q = _require_unknown(unknowns, self.q_name, "SensibleHeatRateClosure")
        mdot = _require_unknown(unknowns, self.mdot_name, "SensibleHeatRateClosure")
        theta_in = _require_unknown(unknowns, self.theta_in_name, "SensibleHeatRateClosure")
        theta_out = _require_unknown(unknowns, self.theta_out_name, "SensibleHeatRateClosure")
        return q - mdot * self.cp * (theta_out - theta_in)


# ---------------------------------------------------------------------------
# EnthalpyFlowHeatRateClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnthalpyFlowHeatRateClosure:
    """Algebraic enthalpy-flow heat-rate relation.

    Residual equation:
        r = q - mdot * (h_out - h_in)

    Zero iff the heat rate equals the enthalpy-flow difference.

    This is a purely algebraic explicit relation.  No phase logic, no property
    backend, no saturation, no quality, no CoolProp, no FluidState.
    h_in and h_out are explicit scalar unknowns supplied by the caller.

    Sign convention:
      - Positive (h_out - h_in) and positive mdot yield positive q
        (enthalpy gained by the stream).
      - Negative (h_out - h_in) yields negative q (enthalpy given up).

    Use cases:
      - Preheater/evaporator/condenser algebraic closure (refrigerant side).
      - Future evaporator/condenser/preheater algebra.
      - Explicit algebraic enthalpy-balance closure.

    Validation:
      - q_name, mdot_name, h_in_name, h_out_name, residual_name:
        all must be non-blank str.
      - All required unknowns must be present and finite at evaluation.
      - No property calls.
    """

    q_name: str
    mdot_name: str
    h_in_name: str
    h_out_name: str
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "q_name",
            _require_non_empty_str(self.q_name, "EnthalpyFlowHeatRateClosure.q_name"),
        )
        object.__setattr__(
            self,
            "mdot_name",
            _require_non_empty_str(self.mdot_name, "EnthalpyFlowHeatRateClosure.mdot_name"),
        )
        object.__setattr__(
            self,
            "h_in_name",
            _require_non_empty_str(self.h_in_name, "EnthalpyFlowHeatRateClosure.h_in_name"),
        )
        object.__setattr__(
            self,
            "h_out_name",
            _require_non_empty_str(self.h_out_name, "EnthalpyFlowHeatRateClosure.h_out_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(self.residual_name, "EnthalpyFlowHeatRateClosure.residual_name"),
        )

    @property
    def kind(self) -> ThermalClosureKind:
        return ThermalClosureKind.ENTHALPY_FLOW_HEAT_RATE

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        q = _require_unknown(unknowns, self.q_name, "EnthalpyFlowHeatRateClosure")
        mdot = _require_unknown(unknowns, self.mdot_name, "EnthalpyFlowHeatRateClosure")
        h_in = _require_unknown(unknowns, self.h_in_name, "EnthalpyFlowHeatRateClosure")
        h_out = _require_unknown(unknowns, self.h_out_name, "EnthalpyFlowHeatRateClosure")
        return q - mdot * (h_out - h_in)


# ---------------------------------------------------------------------------
# EffectivenessHeatRateClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EffectivenessHeatRateClosure:
    """Simplified algebraic heat-exchanger effectiveness closure.

    Residual equation:
        r = q - effectiveness * q_max

    Zero iff the heat rate equals effectiveness times the maximum heat rate.

    IMPORTANT: This is NOT a real HX effectiveness-NTU model.  It is a purely
    algebraic constraint with a user-supplied effectiveness scalar.  No UA,
    no LMTD, no NTU calculation, no HTC correlation, no property lookup,
    no HX model import.  q and q_max are caller-supplied unknowns.

    effectiveness is a structural parameter between 0 and 1 (inclusive).
    Its physical interpretation is the caller's responsibility.

    Sign convention:
      - Positive effectiveness and positive q_max yield positive q.
      - If q_max is negative (e.g., heat rejection), q will also be negative.

    Use cases:
      - Algebraic effectiveness-limited heat transfer in test scenarios.
      - Closure for a user-defined maximum heat transfer capacity.
      - Simplified HX design-point constraint.

    Validation:
      - q_name, q_max_name, residual_name must be non-blank str.
      - effectiveness must satisfy 0 <= effectiveness <= 1.
      - effectiveness must be a finite real scalar (not bool, not NaN, not inf).
    """

    q_name: str
    q_max_name: str
    effectiveness: float
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "q_name",
            _require_non_empty_str(self.q_name, "EffectivenessHeatRateClosure.q_name"),
        )
        object.__setattr__(
            self,
            "q_max_name",
            _require_non_empty_str(self.q_max_name, "EffectivenessHeatRateClosure.q_max_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(
                self.residual_name, "EffectivenessHeatRateClosure.residual_name"
            ),
        )
        object.__setattr__(
            self,
            "effectiveness",
            _require_effectiveness(
                self.effectiveness, "EffectivenessHeatRateClosure.effectiveness"
            ),
        )

    @property
    def kind(self) -> ThermalClosureKind:
        return ThermalClosureKind.EFFECTIVENESS_HEAT_RATE

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        q = _require_unknown(unknowns, self.q_name, "EffectivenessHeatRateClosure")
        q_max = _require_unknown(unknowns, self.q_max_name, "EffectivenessHeatRateClosure")
        return q - self.effectiveness * q_max


# ---------------------------------------------------------------------------
# RecuperatorEnergyBalanceClosure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecuperatorEnergyBalanceClosure:
    """Simple algebraic recuperator energy-balance closure.

    Residual equation:
        r = q_hot + q_cold

    Zero iff the signed hot-side and cold-side heat rates sum to zero.

    This closure only enforces energy consistency between two thermal streams.
    It does NOT predict heat transfer magnitude.  No heat-transfer coefficient,
    no area, no UA, no LMTD, no NTU, no properties, no HX model call.

    Sign convention:
      - q_hot < 0: heat given up by the hot side (energy leaving hot stream).
      - q_cold > 0: heat received by the cold side (energy entering cold stream).
      - At energy balance: q_hot + q_cold = 0.
      - The caller is responsible for assigning signs consistently.

    Use cases:
      - Algebraic energy-balance constraint between two recuperator streams.
      - Simplified internal heat exchange consistency check.
      - Combined with per-stream EnthalpyFlowHeatRateClosure for full closure.

    Validation:
      - q_hot_name, q_cold_name, residual_name must be non-blank str.
      - All required unknowns must be present and finite at evaluation.
      - No property calls; no production component execution.
    """

    q_hot_name: str
    q_cold_name: str
    residual_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "q_hot_name",
            _require_non_empty_str(self.q_hot_name, "RecuperatorEnergyBalanceClosure.q_hot_name"),
        )
        object.__setattr__(
            self,
            "q_cold_name",
            _require_non_empty_str(self.q_cold_name, "RecuperatorEnergyBalanceClosure.q_cold_name"),
        )
        object.__setattr__(
            self,
            "residual_name",
            _require_non_empty_str(
                self.residual_name, "RecuperatorEnergyBalanceClosure.residual_name"
            ),
        )

    @property
    def kind(self) -> ThermalClosureKind:
        return ThermalClosureKind.RECUPERATOR_ENERGY_BALANCE

    def evaluate(self, unknowns: Mapping[str, float]) -> float:
        """Return residual value given the current unknown vector."""
        q_hot = _require_unknown(unknowns, self.q_hot_name, "RecuperatorEnergyBalanceClosure")
        q_cold = _require_unknown(unknowns, self.q_cold_name, "RecuperatorEnergyBalanceClosure")
        return q_hot + q_cold


# ---------------------------------------------------------------------------
# ThermalClosureDeclaration union type alias
# ---------------------------------------------------------------------------

ThermalClosureDeclaration = (
    FixedHeatRateClosure
    | ImposedEnthalpyClosure
    | ImposedTemperatureLikeClosure
    | SensibleHeatRateClosure
    | EnthalpyFlowHeatRateClosure
    | EffectivenessHeatRateClosure
    | RecuperatorEnergyBalanceClosure
)
"""Union of all concrete thermal closure types.

Use this alias as the type annotation for collections of mixed closures.
"""


# ---------------------------------------------------------------------------
# ThermalClosureResidualSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThermalClosureResidualSet:
    """Ordered, duplicate-name-rejecting collection of thermal closures.

    Produced by build_thermal_closure_residuals.  Provides:
      - an ordered tuple of closure objects;
      - residual name lookup (unique names enforced at build time);
      - evaluate_all: evaluates all closure residuals at a given unknown vector;
      - optional caller metadata (defensively copied).

    All residual names are unique within this set.

    Fields
    ------
    closures   : tuple of ThermalClosureDeclaration objects (ordered)
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

    closures: tuple[ThermalClosureDeclaration, ...]
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
                    f"ThermalClosureResidualSet: closure '{closure.residual_name}' "
                    f"returned non-finite residual {value!r}"
                )
            result[closure.residual_name] = value
        return MappingProxyType(result)


# ---------------------------------------------------------------------------
# build_thermal_closure_residuals
# ---------------------------------------------------------------------------


def build_thermal_closure_residuals(
    closures: Iterable[ThermalClosureDeclaration],
    *,
    metadata: Mapping[str, object] | None = None,
) -> ThermalClosureResidualSet:
    """Build a validated ThermalClosureResidualSet from an iterable of closures.

    Parameters
    ----------
    closures:
        An iterable of ThermalClosureDeclaration objects.  Must be non-empty.
        Duplicate residual names are rejected.
    metadata:
        Optional caller-supplied metadata.  Defensively copied as
        MappingProxyType.  Metadata contents are not interpreted by this module.

    Returns
    -------
    ThermalClosureResidualSet

    Raises
    ------
    TypeError  — if any closure is not a recognized ThermalClosureDeclaration
    ValueError — if the closure list is empty or duplicate residual names exist
    """
    _valid_types = (
        FixedHeatRateClosure,
        ImposedEnthalpyClosure,
        ImposedTemperatureLikeClosure,
        SensibleHeatRateClosure,
        EnthalpyFlowHeatRateClosure,
        EffectivenessHeatRateClosure,
        RecuperatorEnergyBalanceClosure,
    )
    collected: list[ThermalClosureDeclaration] = []
    seen_names: set[str] = set()
    for i, c in enumerate(closures):
        if not isinstance(c, _valid_types):
            raise TypeError(
                f"build_thermal_closure_residuals: item at index {i} is not a "
                f"recognized ThermalClosureDeclaration; got {type(c).__name__!r}"
            )
        if c.residual_name in seen_names:
            raise ValueError(
                f"build_thermal_closure_residuals: duplicate residual name "
                f"'{c.residual_name}' at index {i}"
            )
        seen_names.add(c.residual_name)
        collected.append(c)

    if not collected:
        raise ValueError("build_thermal_closure_residuals: closures must not be empty")

    meta_proxy: MappingProxyType[str, object] | None = None
    if metadata is not None:
        meta_proxy = MappingProxyType(dict(metadata))

    return ThermalClosureResidualSet(
        closures=tuple(collected),
        metadata=meta_proxy,
    )
