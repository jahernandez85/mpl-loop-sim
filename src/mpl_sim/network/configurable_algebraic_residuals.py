"""Configurable algebraic residual assembly foundation — Block 15F-A.

Provides explicit user-declared algebraic residual declarations for configurable
scenarios.  Residuals are declared with explicit unknown names and evaluated
over an explicit unknown-value mapping.  No residuals are inferred from component
roles or network topology.

This module is property-free, correlation-free, and HX-model-free.  It does not
execute production components, does not assemble SystemState, does not construct
FluidState, does not call CoolProp or PropertyBackend, and does not solve.

Sign conventions
----------------
MassBalanceResidualDeclaration:
    r = sum(incoming_unknown_values) - sum(outgoing_unknown_values)
    Zero when total flow into the node equals total flow out.

PressureDifferenceResidualDeclaration:
    r = P_outlet - P_inlet + delta_p
    ``delta_p`` is positive for pressure-dropping elements (resistors),
    negative for pressure-rising elements (e.g., pumps).
    Zero when P_outlet = P_inlet - delta_p.

ImposedPressureResidualDeclaration:
    r = P_unknown - P_imposed
    Zero when the pressure unknown equals the imposed value.

ImposedMassFlowResidualDeclaration:
    r = mdot_unknown - mdot_imposed
    Zero when the mass-flow unknown equals the imposed value.

EnthalpyFlowResidualDeclaration:
    r = q - mdot * (h_out - h_in)
    Zero when the heat-rate unknown equals the enthalpy-flow product.
    No property backend; h_out, h_in, mdot are explicit unknowns.

Extra unknowns in the evaluation mapping are silently ignored.
Missing required unknowns raise ValueError.

Exported names
--------------
ConfigurableAlgebraicResidualKind          — enum of supported residual kinds
ConfigurableAlgebraicResidualDeclaration   — Union type alias for all declarations
MassBalanceResidualDeclaration             — explicit mass-balance residual
PressureDifferenceResidualDeclaration      — explicit pressure-difference residual
ImposedPressureResidualDeclaration         — explicit imposed-pressure residual
ImposedMassFlowResidualDeclaration         — explicit imposed mass-flow residual
EnthalpyFlowResidualDeclaration            — explicit enthalpy-flow energy residual
ConfigurableAlgebraicResidualSet           — ordered, duplicate-rejecting residual set
ConfigurableAlgebraicResidualEvaluationResult — frozen evaluation result
build_configurable_algebraic_residual_set  — factory with declaration-level validation
evaluate_configurable_algebraic_residuals  — evaluation over explicit unknown values
validate_algebraic_residuals_against_scenario — naming compatibility check
build_configurable_algebraic_residual_report  — plain JSON-serializable report

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
MUST NOT execute production component physics.
MUST NOT infer residuals from component roles or network topology.
MUST NOT perform least-squares, root-finding, or optimization.
MUST NOT write files or depend on pandas, matplotlib, or numpy.
"""

from __future__ import annotations

import enum
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

# ---------------------------------------------------------------------------
# Module-level limitations constant
# ---------------------------------------------------------------------------

_LIMITATIONS: tuple[str, ...] = (
    "residuals are user-declared; none are inferred from roles or topology",
    "evaluation-only; no solve, no root-finding, no least-squares",
    "property-free; no CoolProp, PropertyBackend, or correlation calls",
    "correlation-free; no HTC, DP, friction-factor, or flow-regime logic",
    "HX-model-free; no LMTD, NTU, UA, or two-phase computations",
    "production component execution not performed",
    "SystemState not assembled; FluidState not constructed",
    "solve(network) and NetworkGraph.solve() not implemented",
    "not role-based; roles did not select or generate any residual here",
    "no automatic closure inference from roles or topology",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_nonempty_str(value: object, field: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a str; got {type(value).__name__!r}")
    if not value.strip():
        raise ValueError(f"{field} must be non-empty; got {value!r}")


def _require_finite_scalar(value: object, field: str) -> None:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be a finite float, not bool")
    if not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be a finite float; got {type(value).__name__!r}")
    if not math.isfinite(float(value)):
        raise ValueError(f"{field} must be finite; got {value!r}")


def _validate_unknown_values(
    unknown_values: Mapping[str, object],
    required_names: tuple[str, ...],
    context: str,
) -> dict[str, float]:
    """Extract and validate required unknown values from the mapping.

    Extra unknowns are silently ignored.
    Missing, bool, non-numeric, NaN, or infinite values raise ValueError/TypeError.
    """
    result: dict[str, float] = {}
    for name in required_names:
        if name not in unknown_values:
            raise ValueError(
                f"{context}: required unknown {name!r} not found in unknown_values; "
                f"available keys: {sorted(unknown_values)!r}"
            )
        raw = unknown_values[name]
        if isinstance(raw, bool):
            raise TypeError(f"{context}: unknown {name!r} must be a finite float, not bool")
        if not isinstance(raw, (int, float)):
            raise TypeError(
                f"{context}: unknown {name!r} must be a finite float; "
                f"got {type(raw).__name__!r}"
            )
        v = float(raw)
        if not math.isfinite(v):
            raise ValueError(f"{context}: unknown {name!r} must be finite; got {raw!r}")
        result[name] = v
    return result


# ---------------------------------------------------------------------------
# ConfigurableAlgebraicResidualKind
# ---------------------------------------------------------------------------


class ConfigurableAlgebraicResidualKind(enum.Enum):
    """Enum of supported configurable algebraic residual kinds.

    All kinds are explicitly user-declared.  None are inferred from component
    roles, network topology, or component_type.

    Kinds
    -----
    MASS_BALANCE
        r = sum(incoming_unknowns) - sum(outgoing_unknowns).

    PRESSURE_DIFFERENCE
        r = P_outlet - P_inlet + delta_p.
        Positive delta_p = pressure drop (resistor); negative = rise (pump).

    IMPOSED_PRESSURE
        r = P_unknown - P_imposed.

    IMPOSED_MASS_FLOW
        r = mdot_unknown - mdot_imposed.

    ENTHALPY_FLOW
        r = q - mdot * (h_out - h_in).
        No property backend; all terms are explicit unknowns.
    """

    MASS_BALANCE = "mass_balance"
    PRESSURE_DIFFERENCE = "pressure_difference"
    IMPOSED_PRESSURE = "imposed_pressure"
    IMPOSED_MASS_FLOW = "imposed_mass_flow"
    ENTHALPY_FLOW = "enthalpy_flow"


# ---------------------------------------------------------------------------
# MassBalanceResidualDeclaration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MassBalanceResidualDeclaration:
    """Explicit algebraic mass-balance residual declaration.

    Sign convention:
        r = sum(incoming_unknown_values) - sum(outgoing_unknown_values)

    Zero when total flow into the junction equals total flow out.
    Positive when incoming exceeds outgoing; negative when outgoing exceeds
    incoming.

    Fields
    ------
    residual_name         : str              — non-empty unique residual name
    incoming_unknown_names : tuple[str, ...] — mass-flow unknowns entering node
    outgoing_unknown_names : tuple[str, ...] — mass-flow unknowns leaving node

    At least one of incoming_unknown_names or outgoing_unknown_names must be
    non-empty.  All unknown names must be non-empty strings.

    No graph topology inference is performed; unknown names must be explicitly
    supplied by the caller.
    """

    residual_name: str
    incoming_unknown_names: tuple[str, ...]
    outgoing_unknown_names: tuple[str, ...]

    kind: ConfigurableAlgebraicResidualKind = ConfigurableAlgebraicResidualKind.MASS_BALANCE

    def __post_init__(self) -> None:
        _require_nonempty_str(self.residual_name, "MassBalanceResidualDeclaration.residual_name")
        if self.kind is not ConfigurableAlgebraicResidualKind.MASS_BALANCE:
            raise ValueError(
                "MassBalanceResidualDeclaration.kind must be MASS_BALANCE; " f"got {self.kind!r}"
            )
        incoming = self.incoming_unknown_names
        if not isinstance(incoming, tuple):
            object.__setattr__(self, "incoming_unknown_names", tuple(incoming))
            incoming = self.incoming_unknown_names
        outgoing = self.outgoing_unknown_names
        if not isinstance(outgoing, tuple):
            object.__setattr__(self, "outgoing_unknown_names", tuple(outgoing))
            outgoing = self.outgoing_unknown_names
        if not incoming and not outgoing:
            raise ValueError(
                "MassBalanceResidualDeclaration: at least one of "
                "incoming_unknown_names or outgoing_unknown_names must be non-empty"
            )
        for i, name in enumerate(incoming):
            _require_nonempty_str(
                name, f"MassBalanceResidualDeclaration.incoming_unknown_names[{i}]"
            )
        for i, name in enumerate(outgoing):
            _require_nonempty_str(
                name, f"MassBalanceResidualDeclaration.outgoing_unknown_names[{i}]"
            )

    @property
    def required_unknown_names(self) -> tuple[str, ...]:
        """All unknown names required for evaluation (preserves declaration order)."""
        seen: dict[str, None] = {}
        for n in self.incoming_unknown_names:
            seen[n] = None
        for n in self.outgoing_unknown_names:
            seen[n] = None
        return tuple(seen)

    def evaluate(self, unknown_values: Mapping[str, float]) -> float:
        """Evaluate the mass-balance residual over the provided unknown values.

        r = sum(incoming) - sum(outgoing)

        Missing, bool, NaN, or infinite values raise ValueError/TypeError.
        Extra unknowns are silently ignored.
        """
        vals = _validate_unknown_values(
            unknown_values,
            self.required_unknown_names,
            f"MassBalanceResidualDeclaration({self.residual_name!r})",
        )
        total = sum(vals[n] for n in self.incoming_unknown_names) - sum(
            vals[n] for n in self.outgoing_unknown_names
        )
        return float(total)


# ---------------------------------------------------------------------------
# PressureDifferenceResidualDeclaration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PressureDifferenceResidualDeclaration:
    """Explicit algebraic pressure-difference residual declaration.

    Sign convention:
        r = P_outlet - P_inlet + delta_p

    ``delta_p`` is positive for pressure-dropping elements (pipes, valves,
    heat exchangers acting as resistors) and negative for pressure-rising
    elements (e.g., pumps).  Zero when P_outlet = P_inlet - delta_p.

    No pressure-drop model, no friction law, no valve law, no density or
    viscosity.  ``delta_p`` is an explicit finite scalar supplied by the caller.

    Fields
    ------
    residual_name          : str   — non-empty unique residual name
    inlet_pressure_unknown : str   — inlet pressure unknown name
    outlet_pressure_unknown: str   — outlet pressure unknown name
    delta_p                : float — finite scalar pressure difference
                                     (positive = drop; negative = rise)

    kind : ConfigurableAlgebraicResidualKind — always PRESSURE_DIFFERENCE
    """

    residual_name: str
    inlet_pressure_unknown: str
    outlet_pressure_unknown: str
    delta_p: float

    kind: ConfigurableAlgebraicResidualKind = ConfigurableAlgebraicResidualKind.PRESSURE_DIFFERENCE

    def __post_init__(self) -> None:
        _require_nonempty_str(
            self.residual_name, "PressureDifferenceResidualDeclaration.residual_name"
        )
        if self.kind is not ConfigurableAlgebraicResidualKind.PRESSURE_DIFFERENCE:
            raise ValueError(
                "PressureDifferenceResidualDeclaration.kind must be "
                f"PRESSURE_DIFFERENCE; got {self.kind!r}"
            )
        _require_nonempty_str(
            self.inlet_pressure_unknown,
            "PressureDifferenceResidualDeclaration.inlet_pressure_unknown",
        )
        _require_nonempty_str(
            self.outlet_pressure_unknown,
            "PressureDifferenceResidualDeclaration.outlet_pressure_unknown",
        )
        _require_finite_scalar(self.delta_p, "PressureDifferenceResidualDeclaration.delta_p")
        object.__setattr__(self, "delta_p", float(self.delta_p))

    @property
    def required_unknown_names(self) -> tuple[str, ...]:
        """Both pressure unknowns required for evaluation."""
        seen: dict[str, None] = {}
        seen[self.inlet_pressure_unknown] = None
        seen[self.outlet_pressure_unknown] = None
        return tuple(seen)

    def evaluate(self, unknown_values: Mapping[str, float]) -> float:
        """Evaluate: r = P_outlet - P_inlet + delta_p."""
        vals = _validate_unknown_values(
            unknown_values,
            self.required_unknown_names,
            f"PressureDifferenceResidualDeclaration({self.residual_name!r})",
        )
        return vals[self.outlet_pressure_unknown] - vals[self.inlet_pressure_unknown] + self.delta_p


# ---------------------------------------------------------------------------
# ImposedPressureResidualDeclaration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImposedPressureResidualDeclaration:
    """Explicit imposed-pressure residual declaration.

    Sign convention:
        r = P_unknown - P_imposed

    Zero when the pressure unknown equals the imposed scalar.  No property or
    state construction; P_imposed is a finite scalar supplied by the caller.

    Fields
    ------
    residual_name    : str   — non-empty unique residual name
    pressure_unknown : str   — pressure unknown name
    imposed_value    : float — finite scalar imposed pressure

    kind : ConfigurableAlgebraicResidualKind — always IMPOSED_PRESSURE
    """

    residual_name: str
    pressure_unknown: str
    imposed_value: float

    kind: ConfigurableAlgebraicResidualKind = ConfigurableAlgebraicResidualKind.IMPOSED_PRESSURE

    def __post_init__(self) -> None:
        _require_nonempty_str(
            self.residual_name, "ImposedPressureResidualDeclaration.residual_name"
        )
        if self.kind is not ConfigurableAlgebraicResidualKind.IMPOSED_PRESSURE:
            raise ValueError(
                "ImposedPressureResidualDeclaration.kind must be IMPOSED_PRESSURE; "
                f"got {self.kind!r}"
            )
        _require_nonempty_str(
            self.pressure_unknown, "ImposedPressureResidualDeclaration.pressure_unknown"
        )
        _require_finite_scalar(
            self.imposed_value, "ImposedPressureResidualDeclaration.imposed_value"
        )
        object.__setattr__(self, "imposed_value", float(self.imposed_value))

    @property
    def required_unknown_names(self) -> tuple[str, ...]:
        return (self.pressure_unknown,)

    def evaluate(self, unknown_values: Mapping[str, float]) -> float:
        """Evaluate: r = P_unknown - P_imposed."""
        vals = _validate_unknown_values(
            unknown_values,
            self.required_unknown_names,
            f"ImposedPressureResidualDeclaration({self.residual_name!r})",
        )
        return vals[self.pressure_unknown] - self.imposed_value


# ---------------------------------------------------------------------------
# ImposedMassFlowResidualDeclaration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImposedMassFlowResidualDeclaration:
    """Explicit imposed mass-flow residual declaration.

    Sign convention:
        r = mdot_unknown - mdot_imposed

    Zero when the mass-flow unknown equals the imposed scalar.  No pump model or
    flow prediction; mdot_imposed is a finite scalar supplied by the caller.

    Fields
    ------
    residual_name      : str   — non-empty unique residual name
    mass_flow_unknown  : str   — mass-flow unknown name
    imposed_value      : float — finite scalar imposed mass flow

    kind : ConfigurableAlgebraicResidualKind — always IMPOSED_MASS_FLOW
    """

    residual_name: str
    mass_flow_unknown: str
    imposed_value: float

    kind: ConfigurableAlgebraicResidualKind = ConfigurableAlgebraicResidualKind.IMPOSED_MASS_FLOW

    def __post_init__(self) -> None:
        _require_nonempty_str(
            self.residual_name, "ImposedMassFlowResidualDeclaration.residual_name"
        )
        if self.kind is not ConfigurableAlgebraicResidualKind.IMPOSED_MASS_FLOW:
            raise ValueError(
                "ImposedMassFlowResidualDeclaration.kind must be IMPOSED_MASS_FLOW; "
                f"got {self.kind!r}"
            )
        _require_nonempty_str(
            self.mass_flow_unknown, "ImposedMassFlowResidualDeclaration.mass_flow_unknown"
        )
        _require_finite_scalar(
            self.imposed_value, "ImposedMassFlowResidualDeclaration.imposed_value"
        )
        object.__setattr__(self, "imposed_value", float(self.imposed_value))

    @property
    def required_unknown_names(self) -> tuple[str, ...]:
        return (self.mass_flow_unknown,)

    def evaluate(self, unknown_values: Mapping[str, float]) -> float:
        """Evaluate: r = mdot_unknown - mdot_imposed."""
        vals = _validate_unknown_values(
            unknown_values,
            self.required_unknown_names,
            f"ImposedMassFlowResidualDeclaration({self.residual_name!r})",
        )
        return vals[self.mass_flow_unknown] - self.imposed_value


# ---------------------------------------------------------------------------
# EnthalpyFlowResidualDeclaration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnthalpyFlowResidualDeclaration:
    """Explicit enthalpy-flow energy-balance residual declaration.

    Sign convention:
        r = q - mdot * (h_out - h_in)

    Zero when the declared heat-rate unknown equals the enthalpy-flow product.
    No property backend; no phase/quality/saturation logic; no FluidState;
    no enthalpy-temperature conversion.  All terms are explicit unknowns.

    Fields
    ------
    residual_name : str — non-empty unique residual name
    q_unknown     : str — heat-rate unknown name
    mdot_unknown  : str — mass-flow unknown name
    h_in_unknown  : str — inlet specific enthalpy unknown name
    h_out_unknown : str — outlet specific enthalpy unknown name

    kind : ConfigurableAlgebraicResidualKind — always ENTHALPY_FLOW
    """

    residual_name: str
    q_unknown: str
    mdot_unknown: str
    h_in_unknown: str
    h_out_unknown: str

    kind: ConfigurableAlgebraicResidualKind = ConfigurableAlgebraicResidualKind.ENTHALPY_FLOW

    def __post_init__(self) -> None:
        _require_nonempty_str(self.residual_name, "EnthalpyFlowResidualDeclaration.residual_name")
        if self.kind is not ConfigurableAlgebraicResidualKind.ENTHALPY_FLOW:
            raise ValueError(
                "EnthalpyFlowResidualDeclaration.kind must be ENTHALPY_FLOW; " f"got {self.kind!r}"
            )
        for field_name, val in (
            ("q_unknown", self.q_unknown),
            ("mdot_unknown", self.mdot_unknown),
            ("h_in_unknown", self.h_in_unknown),
            ("h_out_unknown", self.h_out_unknown),
        ):
            _require_nonempty_str(val, f"EnthalpyFlowResidualDeclaration.{field_name}")

    @property
    def required_unknown_names(self) -> tuple[str, ...]:
        """All four unknowns, deduplicated while preserving declaration order."""
        seen: dict[str, None] = {}
        for n in (self.q_unknown, self.mdot_unknown, self.h_in_unknown, self.h_out_unknown):
            seen[n] = None
        return tuple(seen)

    def evaluate(self, unknown_values: Mapping[str, float]) -> float:
        """Evaluate: r = q - mdot * (h_out - h_in)."""
        vals = _validate_unknown_values(
            unknown_values,
            self.required_unknown_names,
            f"EnthalpyFlowResidualDeclaration({self.residual_name!r})",
        )
        return vals[self.q_unknown] - vals[self.mdot_unknown] * (
            vals[self.h_out_unknown] - vals[self.h_in_unknown]
        )


# ---------------------------------------------------------------------------
# ConfigurableAlgebraicResidualDeclaration — Union type alias
# ---------------------------------------------------------------------------

ConfigurableAlgebraicResidualDeclaration = (
    MassBalanceResidualDeclaration
    | PressureDifferenceResidualDeclaration
    | ImposedPressureResidualDeclaration
    | ImposedMassFlowResidualDeclaration
    | EnthalpyFlowResidualDeclaration
)

_DECLARATION_TYPES = (
    MassBalanceResidualDeclaration,
    PressureDifferenceResidualDeclaration,
    ImposedPressureResidualDeclaration,
    ImposedMassFlowResidualDeclaration,
    EnthalpyFlowResidualDeclaration,
)

# ---------------------------------------------------------------------------
# ConfigurableAlgebraicResidualSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableAlgebraicResidualSet:
    """Ordered, duplicate-name-rejecting collection of algebraic residual declarations.

    Built by ``build_configurable_algebraic_residual_set``.  Frozen/read-only.
    Contains no production component dependencies, no SystemState, no FluidState.

    Fields
    ------
    declarations         : tuple[ConfigurableAlgebraicResidualDeclaration, ...]
    residual_names       : tuple[str, ...] — ordered names from declarations
    required_unknown_names : tuple[str, ...] — deduplicated, declaration-order unique names
    limitations          : tuple[str, ...] — explicit limitation statements
    """

    declarations: tuple[ConfigurableAlgebraicResidualDeclaration, ...]
    residual_names: tuple[str, ...]
    required_unknown_names: tuple[str, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        decls = self.declarations
        if not isinstance(decls, tuple):
            raise TypeError(
                "ConfigurableAlgebraicResidualSet.declarations must be a tuple; "
                f"got {type(decls).__name__!r}"
            )
        for i, d in enumerate(decls):
            if not isinstance(d, _DECLARATION_TYPES):
                raise TypeError(
                    f"ConfigurableAlgebraicResidualSet.declarations[{i}] must be a "
                    "ConfigurableAlgebraicResidualDeclaration; "
                    f"got {type(d).__name__!r}"
                )
        if not isinstance(self.residual_names, tuple):
            raise TypeError("ConfigurableAlgebraicResidualSet.residual_names must be a tuple")
        if not isinstance(self.required_unknown_names, tuple):
            raise TypeError(
                "ConfigurableAlgebraicResidualSet.required_unknown_names must be a tuple"
            )
        if not isinstance(self.limitations, tuple):
            raise TypeError("ConfigurableAlgebraicResidualSet.limitations must be a tuple")

    @property
    def count(self) -> int:
        return len(self.declarations)


# ---------------------------------------------------------------------------
# ConfigurableAlgebraicResidualEvaluationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableAlgebraicResidualEvaluationResult:
    """Frozen result of evaluating a ConfigurableAlgebraicResidualSet.

    Fields
    ------
    residual_names      : tuple[str, ...]         — ordered from set
    residual_values     : Mapping[str, float]      — read-only residual map
    max_abs_residual    : float                    — max(|r|) over all residuals
    l2_norm             : float                    — sqrt(sum(r^2))
    unknown_names_used  : tuple[str, ...]          — required unknowns extracted
    no_solve            : bool                     — always True
    limitations         : tuple[str, ...]          — from the residual set
    """

    residual_names: tuple[str, ...]
    residual_values: Mapping[str, float]
    max_abs_residual: float
    l2_norm: float
    unknown_names_used: tuple[str, ...]
    no_solve: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.residual_names, tuple):
            raise TypeError(
                "ConfigurableAlgebraicResidualEvaluationResult.residual_names " "must be a tuple"
            )
        rv = self.residual_values
        if not isinstance(rv, Mapping):
            raise TypeError(
                "ConfigurableAlgebraicResidualEvaluationResult.residual_values " "must be a Mapping"
            )
        if not isinstance(rv, MappingProxyType):
            object.__setattr__(self, "residual_values", MappingProxyType(dict(rv)))
        if not isinstance(self.no_solve, bool):
            raise TypeError("ConfigurableAlgebraicResidualEvaluationResult.no_solve must be bool")
        if not self.no_solve:
            raise ValueError("ConfigurableAlgebraicResidualEvaluationResult.no_solve must be True")
        if not isinstance(self.unknown_names_used, tuple):
            raise TypeError(
                "ConfigurableAlgebraicResidualEvaluationResult.unknown_names_used "
                "must be a tuple"
            )
        if not isinstance(self.limitations, tuple):
            raise TypeError(
                "ConfigurableAlgebraicResidualEvaluationResult.limitations must be a tuple"
            )


# ---------------------------------------------------------------------------
# build_configurable_algebraic_residual_set
# ---------------------------------------------------------------------------


def build_configurable_algebraic_residual_set(
    declarations: (
        tuple[ConfigurableAlgebraicResidualDeclaration, ...]
        | list[ConfigurableAlgebraicResidualDeclaration]
    ),
) -> ConfigurableAlgebraicResidualSet:
    """Build a validated ConfigurableAlgebraicResidualSet from a sequence of declarations.

    Validates:
    - Each declaration is a known ConfigurableAlgebraicResidualDeclaration type.
    - Residual names are unique (no duplicates).
    - At least one declaration is provided.

    No evaluation is performed during construction.

    Parameters
    ----------
    declarations : sequence of ConfigurableAlgebraicResidualDeclaration

    Returns
    -------
    ConfigurableAlgebraicResidualSet — frozen, validated

    Raises
    ------
    TypeError
        If declarations is not a sequence or any element is not a declaration type.
    ValueError
        If declarations is empty or contains duplicate residual names.
    """
    if not isinstance(declarations, (tuple, list)):
        raise TypeError(
            "build_configurable_algebraic_residual_set: declarations must be a "
            f"tuple or list; got {type(declarations).__name__!r}"
        )
    decl_tuple: tuple[ConfigurableAlgebraicResidualDeclaration, ...] = tuple(declarations)
    if not decl_tuple:
        raise ValueError(
            "build_configurable_algebraic_residual_set: declarations must not be empty"
        )
    for i, d in enumerate(decl_tuple):
        if not isinstance(d, _DECLARATION_TYPES):
            raise TypeError(
                f"build_configurable_algebraic_residual_set: declarations[{i}] must be "
                "a ConfigurableAlgebraicResidualDeclaration; "
                f"got {type(d).__name__!r}"
            )

    # Validate residual name uniqueness.
    seen_names: dict[str, int] = {}
    for i, d in enumerate(decl_tuple):
        name = d.residual_name
        if name in seen_names:
            raise ValueError(
                "build_configurable_algebraic_residual_set: duplicate residual name "
                f"{name!r} at declaration indices {seen_names[name]} and {i}"
            )
        seen_names[name] = i

    # Build ordered residual names.
    residual_names: tuple[str, ...] = tuple(d.residual_name for d in decl_tuple)

    # Build deduplicated required unknown names (preserve declaration order).
    seen_unknowns: dict[str, None] = {}
    for d in decl_tuple:
        for n in d.required_unknown_names:
            seen_unknowns[n] = None
    required_unknown_names: tuple[str, ...] = tuple(seen_unknowns)

    return ConfigurableAlgebraicResidualSet(
        declarations=decl_tuple,
        residual_names=residual_names,
        required_unknown_names=required_unknown_names,
        limitations=_LIMITATIONS,
    )


# ---------------------------------------------------------------------------
# evaluate_configurable_algebraic_residuals
# ---------------------------------------------------------------------------


def evaluate_configurable_algebraic_residuals(
    residual_set: ConfigurableAlgebraicResidualSet,
    unknown_values: Mapping[str, float],
) -> ConfigurableAlgebraicResidualEvaluationResult:
    """Evaluate all algebraic residuals in the set over explicit unknown values.

    Each residual is evaluated independently over the provided unknown-value
    mapping.  Extra unknowns are silently ignored.  Missing, bool, non-numeric,
    NaN, or infinite values raise ValueError or TypeError.

    No solve is performed.  No root-finding.  No least-squares.

    Parameters
    ----------
    residual_set   : ConfigurableAlgebraicResidualSet — validated set
    unknown_values : Mapping[str, float]              — explicit values

    Returns
    -------
    ConfigurableAlgebraicResidualEvaluationResult — frozen result

    Raises
    ------
    TypeError
        If residual_set is not a ConfigurableAlgebraicResidualSet.
        If unknown_values is not a Mapping.
        If any required unknown value is bool or non-numeric.
    ValueError
        If any required unknown is missing, NaN, or infinite.
    """
    if not isinstance(residual_set, ConfigurableAlgebraicResidualSet):
        raise TypeError(
            "evaluate_configurable_algebraic_residuals: residual_set must be a "
            "ConfigurableAlgebraicResidualSet; "
            f"got {type(residual_set).__name__!r}"
        )
    if not isinstance(unknown_values, Mapping):
        raise TypeError(
            "evaluate_configurable_algebraic_residuals: unknown_values must be a "
            f"Mapping; got {type(unknown_values).__name__!r}"
        )

    # Validate all required unknowns up front (fail early, consistent error context).
    all_vals = _validate_unknown_values(
        unknown_values,
        residual_set.required_unknown_names,
        "evaluate_configurable_algebraic_residuals",
    )

    # Evaluate each residual; use all_vals for efficiency.
    residual_values: dict[str, float] = {}
    for decl in residual_set.declarations:
        residual_values[decl.residual_name] = decl.evaluate(all_vals)

    # Compute norms.
    values_list = [residual_values[n] for n in residual_set.residual_names]
    max_abs = max(abs(v) for v in values_list) if values_list else 0.0
    l2 = math.sqrt(sum(v * v for v in values_list))

    return ConfigurableAlgebraicResidualEvaluationResult(
        residual_names=residual_set.residual_names,
        residual_values=MappingProxyType(residual_values),
        max_abs_residual=max_abs,
        l2_norm=l2,
        unknown_names_used=residual_set.required_unknown_names,
        no_solve=True,
        limitations=residual_set.limitations,
    )


# ---------------------------------------------------------------------------
# validate_algebraic_residuals_against_scenario
# ---------------------------------------------------------------------------


def validate_algebraic_residuals_against_scenario(
    residual_set: ConfigurableAlgebraicResidualSet,
    build_result: object,
) -> dict[str, object]:
    """Check naming compatibility of a residual set against a scenario build result.

    Verifies that all declared unknown names in the residual set exist in the
    scenario build result's unknown_names tuple.  No residuals are inferred
    from the scenario graph or component roles.  No evaluation is performed.

    Parameters
    ----------
    residual_set : ConfigurableAlgebraicResidualSet
    build_result : ConfigurableScenarioBuildResult
        (imported lazily to avoid circular imports; checked by duck-typing)

    Returns
    -------
    dict[str, object] — plain JSON-serializable compatibility report:
        is_compatible : bool
        missing_unknowns : list[str] — names declared but not in scenario
        declared_unknowns : list[str] — all unknowns declared in residual set
        scenario_unknowns : list[str] — all unknowns in the scenario
        residual_names : list[str] — declared residual names
        reasons : list[str] — human-readable compatibility notes
        no_residuals_inferred_from_roles : bool — always True
        no_residuals_inferred_from_topology : bool — always True

    Raises
    ------
    TypeError
        If residual_set is not a ConfigurableAlgebraicResidualSet.
        If build_result does not have an unknown_names attribute.
    """
    if not isinstance(residual_set, ConfigurableAlgebraicResidualSet):
        raise TypeError(
            "validate_algebraic_residuals_against_scenario: residual_set must be a "
            "ConfigurableAlgebraicResidualSet; "
            f"got {type(residual_set).__name__!r}"
        )
    if not hasattr(build_result, "unknown_names"):
        raise TypeError(
            "validate_algebraic_residuals_against_scenario: build_result must have "
            "an 'unknown_names' attribute (expected ConfigurableScenarioBuildResult)"
        )

    scenario_unknowns: tuple[str, ...] = build_result.unknown_names
    if not isinstance(scenario_unknowns, tuple):
        raise TypeError(
            "validate_algebraic_residuals_against_scenario: "
            "build_result.unknown_names must be a tuple"
        )
    for i, name in enumerate(scenario_unknowns):
        _require_nonempty_str(
            name,
            "validate_algebraic_residuals_against_scenario." f"build_result.unknown_names[{i}]",
        )
    scenario_unknown_set = set(scenario_unknowns)
    declared_unknowns = list(residual_set.required_unknown_names)
    missing = [n for n in declared_unknowns if n not in scenario_unknown_set]

    reasons: list[str] = []
    if missing:
        reasons.append(f"declared unknown names not in scenario: {sorted(missing)!r}")
    else:
        reasons.append("all declared unknown names are present in the scenario build result")
    reasons.append(f"residual count: {residual_set.count}")
    reasons.append(
        "residuals were not inferred from scenario roles or topology; "
        "all declarations are user-supplied"
    )

    is_compatible = len(missing) == 0

    report: dict[str, object] = {
        "is_compatible": is_compatible,
        "missing_unknowns": sorted(missing),
        "declared_unknowns": declared_unknowns,
        "scenario_unknowns": list(scenario_unknowns),
        "residual_names": list(residual_set.residual_names),
        "reasons": reasons,
        "no_residuals_inferred_from_roles": True,
        "no_residuals_inferred_from_topology": True,
    }
    # Verify JSON-serializability before returning.
    json.dumps(report)
    return report


# ---------------------------------------------------------------------------
# build_configurable_algebraic_residual_report
# ---------------------------------------------------------------------------


def build_configurable_algebraic_residual_report(
    evaluation_result: ConfigurableAlgebraicResidualEvaluationResult,
    *,
    scenario_compatibility: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a plain JSON-serializable report for a residual evaluation result.

    Returns a plain dict with only JSON-serializable values.  No file writes.
    No pandas.  No physical state values.

    Always includes:
        status: "algebraic_residual_evaluation"
        no_solve: True
        no_properties: True
        no_correlations: True
        no_hx_models: True
        no_production_components: True
        no_role_based_physics: True
        no_automatic_residual_inference: True
        no_topology_based_residual_inference: True
        no_automatic_closure_inference: True

    Parameters
    ----------
    evaluation_result    : ConfigurableAlgebraicResidualEvaluationResult
    scenario_compatibility : dict | None — optional scenario compatibility report

    Returns
    -------
    dict[str, object] — JSON-serializable report

    Raises
    ------
    TypeError
        If evaluation_result is not a ConfigurableAlgebraicResidualEvaluationResult.
    """
    if not isinstance(evaluation_result, ConfigurableAlgebraicResidualEvaluationResult):
        raise TypeError(
            "build_configurable_algebraic_residual_report: evaluation_result must be "
            "a ConfigurableAlgebraicResidualEvaluationResult; "
            f"got {type(evaluation_result).__name__!r}"
        )
    if scenario_compatibility is not None and not isinstance(scenario_compatibility, dict):
        raise TypeError(
            "build_configurable_algebraic_residual_report: scenario_compatibility "
            "must be a dict or None; "
            f"got {type(scenario_compatibility).__name__!r}"
        )

    report: dict[str, object] = {
        "status": "algebraic_residual_evaluation",
        "no_solve": True,
        "no_properties": True,
        "no_correlations": True,
        "no_hx_models": True,
        "no_production_components": True,
        "no_role_based_physics": True,
        "no_automatic_residual_inference": True,
        "no_topology_based_residual_inference": True,
        "no_automatic_closure_inference": True,
        "residual_count": len(evaluation_result.residual_names),
        "residual_names": list(evaluation_result.residual_names),
        "residual_values": dict(evaluation_result.residual_values),
        "max_abs_residual": evaluation_result.max_abs_residual,
        "l2_norm": evaluation_result.l2_norm,
        "unknown_names_used": list(evaluation_result.unknown_names_used),
        "limitations": list(evaluation_result.limitations),
    }
    if scenario_compatibility is not None:
        report["scenario_compatibility"] = scenario_compatibility

    # Verify JSON-serializability before returning.
    json.dumps(report)
    return report
