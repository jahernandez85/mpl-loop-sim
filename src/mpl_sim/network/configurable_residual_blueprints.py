"""Explicit configurable residual blueprint assembly — Block 15G-A.

Provides a user-declared blueprint layer that translates scenario-level IDs
(component IDs, node IDs) into 15F-A algebraic residual declarations.

Blueprints are explicit.  No residuals are inferred from graph topology, from
component roles, or from component_type.  The user must declare every blueprint.

Each blueprint translates to exactly one 15F-A algebraic residual declaration
using deterministic naming conventions:
    mdot:<component_id>   — mass-flow unknown for a component
    P:<node_id>           — pressure unknown for a node

Exported names
--------------
ConfigurableResidualBlueprintKind         — enum of supported blueprint kinds
ConfigurableResidualBlueprintDeclaration  — Union type alias for all blueprints
MassBalanceResidualBlueprint              — explicit mass-balance blueprint
PressureDifferenceResidualBlueprint       — explicit pressure-difference blueprint
ImposedPressureResidualBlueprint          — explicit imposed-pressure blueprint
ImposedMassFlowResidualBlueprint          — explicit imposed mass-flow blueprint
EnthalpyFlowResidualBlueprint             — explicit enthalpy-flow blueprint
ConfigurableResidualBlueprintSet          — ordered, duplicate-rejecting blueprint set
ConfigurableResidualBlueprintBuildResult  — frozen build result
build_configurable_algebraic_residuals_from_blueprints — builder function
build_configurable_residual_blueprint_report            — plain JSON-serializable report

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
MUST NOT inspect graph edges to decide residual content.
MUST NOT perform least-squares, root-finding, or optimization.
MUST NOT write files or depend on pandas, matplotlib, or numpy.
"""

from __future__ import annotations

import enum
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

from mpl_sim.network.configurable_algebraic_residuals import (
    ConfigurableAlgebraicResidualSet,
    EnthalpyFlowResidualDeclaration,
    ImposedMassFlowResidualDeclaration,
    ImposedPressureResidualDeclaration,
    MassBalanceResidualDeclaration,
    PressureDifferenceResidualDeclaration,
    build_configurable_algebraic_residual_set,
)

# ---------------------------------------------------------------------------
# Module-level limitations constant
# ---------------------------------------------------------------------------

_LIMITATIONS: tuple[str, ...] = (
    "blueprints are user-declared; none are inferred from roles or topology",
    "no residuals inferred from component roles",
    "no residuals inferred from graph topology",
    "no closures inferred from roles",
    "no graph-edge inspection to decide residual content",
    "translation is identifier-level only; no physics evaluated",
    "evaluation-only after translation; no solve, no root-finding, no least-squares",
    "property-free; no CoolProp, PropertyBackend, or correlation calls",
    "correlation-free; no HTC, DP, friction-factor, or flow-regime logic",
    "HX-model-free; no LMTD, NTU, UA, or two-phase computations",
    "production component execution not performed",
    "SystemState not assembled; FluidState not constructed",
    "no generic network solve; no graph-based root-finding path",
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


# ---------------------------------------------------------------------------
# ConfigurableResidualBlueprintKind
# ---------------------------------------------------------------------------


class ConfigurableResidualBlueprintKind(enum.Enum):
    """Enum of supported configurable residual blueprint kinds.

    All kinds are explicitly user-declared.  None are inferred from component
    roles, network topology, or component_type.  Each blueprint kind maps
    to exactly one 15F-A algebraic residual declaration type.

    Kinds
    -----
    MASS_BALANCE
        Maps to MassBalanceResidualDeclaration.
        Translates incoming/outgoing component IDs to mdot:<id> unknowns.

    PRESSURE_DIFFERENCE
        Maps to PressureDifferenceResidualDeclaration.
        Translates inlet/outlet node IDs to P:<id> unknowns.

    IMPOSED_PRESSURE
        Maps to ImposedPressureResidualDeclaration.
        Translates a node ID to a P:<id> unknown.

    IMPOSED_MASS_FLOW
        Maps to ImposedMassFlowResidualDeclaration.
        Translates a component ID to a mdot:<id> unknown.

    ENTHALPY_FLOW
        Maps to EnthalpyFlowResidualDeclaration.
        Translates a mass-flow component ID to a mdot:<id> unknown;
        heat-rate, h_in, and h_out unknowns are supplied explicitly.
    """

    MASS_BALANCE = "mass_balance"
    PRESSURE_DIFFERENCE = "pressure_difference"
    IMPOSED_PRESSURE = "imposed_pressure"
    IMPOSED_MASS_FLOW = "imposed_mass_flow"
    ENTHALPY_FLOW = "enthalpy_flow"


# ---------------------------------------------------------------------------
# MassBalanceResidualBlueprint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MassBalanceResidualBlueprint:
    """Explicit mass-balance residual blueprint.

    Translates incoming/outgoing component IDs into mdot:<id> unknown names,
    then creates a MassBalanceResidualDeclaration.

    Translation
    -----------
        incoming_unknowns = tuple(f"mdot:{cid}" for cid in incoming_component_ids)
        outgoing_unknowns = tuple(f"mdot:{cid}" for cid in outgoing_component_ids)
        → MassBalanceResidualDeclaration(residual_name, incoming_unknowns, outgoing_unknowns)

    Fields
    ------
    residual_name          : str                — non-empty unique residual name
    incoming_component_ids : tuple[str, ...]    — component IDs with flow into node
    outgoing_component_ids : tuple[str, ...]    — component IDs with flow out of node
    anchor_node_id         : str | None         — optional metadata label; NOT used
                                                  for topology inference or discovery

    At least one of incoming_component_ids or outgoing_component_ids must be non-empty.
    Component IDs are explicit non-empty strings.
    No graph-edge inspection is performed.
    No role inference is performed.
    anchor_node_id (if provided) is a metadata label only; it does not trigger
    discovery of connected components.
    """

    residual_name: str
    incoming_component_ids: tuple[str, ...]
    outgoing_component_ids: tuple[str, ...]
    anchor_node_id: str | None = None

    kind: ConfigurableResidualBlueprintKind = ConfigurableResidualBlueprintKind.MASS_BALANCE

    def __post_init__(self) -> None:
        _require_nonempty_str(self.residual_name, "MassBalanceResidualBlueprint.residual_name")
        if self.kind is not ConfigurableResidualBlueprintKind.MASS_BALANCE:
            raise ValueError(
                "MassBalanceResidualBlueprint.kind must be MASS_BALANCE; " f"got {self.kind!r}"
            )
        incoming = self.incoming_component_ids
        if not isinstance(incoming, tuple):
            object.__setattr__(self, "incoming_component_ids", tuple(incoming))
            incoming = self.incoming_component_ids
        outgoing = self.outgoing_component_ids
        if not isinstance(outgoing, tuple):
            object.__setattr__(self, "outgoing_component_ids", tuple(outgoing))
            outgoing = self.outgoing_component_ids
        if not incoming and not outgoing:
            raise ValueError(
                "MassBalanceResidualBlueprint: at least one of "
                "incoming_component_ids or outgoing_component_ids must be non-empty"
            )
        for i, cid in enumerate(incoming):
            _require_nonempty_str(cid, f"MassBalanceResidualBlueprint.incoming_component_ids[{i}]")
        for i, cid in enumerate(outgoing):
            _require_nonempty_str(cid, f"MassBalanceResidualBlueprint.outgoing_component_ids[{i}]")
        if self.anchor_node_id is not None:
            _require_nonempty_str(
                self.anchor_node_id, "MassBalanceResidualBlueprint.anchor_node_id"
            )

    def _to_algebraic_declaration(self) -> MassBalanceResidualDeclaration:
        """Translate blueprint to a MassBalanceResidualDeclaration.

        incoming_unknowns = tuple(f"mdot:{cid}" for cid in incoming_component_ids)
        outgoing_unknowns = tuple(f"mdot:{cid}" for cid in outgoing_component_ids)
        No graph inspection.  No role lookup.
        """
        incoming = tuple(f"mdot:{cid}" for cid in self.incoming_component_ids)
        outgoing = tuple(f"mdot:{cid}" for cid in self.outgoing_component_ids)
        return MassBalanceResidualDeclaration(
            residual_name=self.residual_name,
            incoming_unknown_names=incoming,
            outgoing_unknown_names=outgoing,
        )


# ---------------------------------------------------------------------------
# PressureDifferenceResidualBlueprint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PressureDifferenceResidualBlueprint:
    """Explicit pressure-difference residual blueprint.

    Translates inlet and outlet node IDs into P:<id> unknown names, then
    creates a PressureDifferenceResidualDeclaration.

    Translation
    -----------
        P_in  = f"P:{inlet_node_id}"
        P_out = f"P:{outlet_node_id}"
        r = P_out - P_in + delta_p
        → PressureDifferenceResidualDeclaration(residual_name, P_in, P_out, delta_p)

    delta_p is positive for pressure-dropping elements (resistors) and negative
    for pressure-rising elements (e.g., pumps).

    Fields
    ------
    residual_name  : str   — non-empty unique residual name
    inlet_node_id  : str   — inlet node ID (translates to P:<id>)
    outlet_node_id : str   — outlet node ID (translates to P:<id>)
    delta_p        : float — finite scalar pressure difference; no pressure-drop
                             model, no friction law, no density or viscosity

    No graph-edge inspection is performed to choose inlet/outlet.
    """

    residual_name: str
    inlet_node_id: str
    outlet_node_id: str
    delta_p: float

    kind: ConfigurableResidualBlueprintKind = ConfigurableResidualBlueprintKind.PRESSURE_DIFFERENCE

    def __post_init__(self) -> None:
        _require_nonempty_str(
            self.residual_name, "PressureDifferenceResidualBlueprint.residual_name"
        )
        if self.kind is not ConfigurableResidualBlueprintKind.PRESSURE_DIFFERENCE:
            raise ValueError(
                "PressureDifferenceResidualBlueprint.kind must be "
                f"PRESSURE_DIFFERENCE; got {self.kind!r}"
            )
        _require_nonempty_str(
            self.inlet_node_id, "PressureDifferenceResidualBlueprint.inlet_node_id"
        )
        _require_nonempty_str(
            self.outlet_node_id, "PressureDifferenceResidualBlueprint.outlet_node_id"
        )
        _require_finite_scalar(self.delta_p, "PressureDifferenceResidualBlueprint.delta_p")
        object.__setattr__(self, "delta_p", float(self.delta_p))

    def _to_algebraic_declaration(self) -> PressureDifferenceResidualDeclaration:
        """Translate blueprint to a PressureDifferenceResidualDeclaration.

        P_in = f"P:{inlet_node_id}", P_out = f"P:{outlet_node_id}".
        No graph inspection.  No role lookup.
        """
        return PressureDifferenceResidualDeclaration(
            residual_name=self.residual_name,
            inlet_pressure_unknown=f"P:{self.inlet_node_id}",
            outlet_pressure_unknown=f"P:{self.outlet_node_id}",
            delta_p=self.delta_p,
        )


# ---------------------------------------------------------------------------
# ImposedPressureResidualBlueprint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImposedPressureResidualBlueprint:
    """Explicit imposed-pressure residual blueprint.

    Translates a node ID into a P:<id> unknown name, then creates an
    ImposedPressureResidualDeclaration.

    Translation
    -----------
        pressure_unknown = f"P:{node_id}"
        r = P_unknown - pressure
        → ImposedPressureResidualDeclaration(residual_name, pressure_unknown, pressure)

    Fields
    ------
    residual_name : str   — non-empty unique residual name
    node_id       : str   — node ID (translates to P:<id>)
    pressure      : float — finite scalar imposed pressure; no state construction,
                            no property backend
    """

    residual_name: str
    node_id: str
    pressure: float

    kind: ConfigurableResidualBlueprintKind = ConfigurableResidualBlueprintKind.IMPOSED_PRESSURE

    def __post_init__(self) -> None:
        _require_nonempty_str(self.residual_name, "ImposedPressureResidualBlueprint.residual_name")
        if self.kind is not ConfigurableResidualBlueprintKind.IMPOSED_PRESSURE:
            raise ValueError(
                "ImposedPressureResidualBlueprint.kind must be "
                f"IMPOSED_PRESSURE; got {self.kind!r}"
            )
        _require_nonempty_str(self.node_id, "ImposedPressureResidualBlueprint.node_id")
        _require_finite_scalar(self.pressure, "ImposedPressureResidualBlueprint.pressure")
        object.__setattr__(self, "pressure", float(self.pressure))

    def _to_algebraic_declaration(self) -> ImposedPressureResidualDeclaration:
        """Translate blueprint to an ImposedPressureResidualDeclaration.

        pressure_unknown = f"P:{node_id}".
        No state construction.  No property backend.
        """
        return ImposedPressureResidualDeclaration(
            residual_name=self.residual_name,
            pressure_unknown=f"P:{self.node_id}",
            imposed_value=self.pressure,
        )


# ---------------------------------------------------------------------------
# ImposedMassFlowResidualBlueprint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImposedMassFlowResidualBlueprint:
    """Explicit imposed mass-flow residual blueprint.

    Translates a component ID into a mdot:<id> unknown name, then creates an
    ImposedMassFlowResidualDeclaration.

    Translation
    -----------
        mass_flow_unknown = f"mdot:{component_id}"
        r = mdot_unknown - mass_flow
        → ImposedMassFlowResidualDeclaration(residual_name, mass_flow_unknown, mass_flow)

    Fields
    ------
    residual_name : str   — non-empty unique residual name
    component_id  : str   — component ID (translates to mdot:<id>)
    mass_flow     : float — finite scalar imposed mass flow; no pump model or
                            flow prediction
    """

    residual_name: str
    component_id: str
    mass_flow: float

    kind: ConfigurableResidualBlueprintKind = ConfigurableResidualBlueprintKind.IMPOSED_MASS_FLOW

    def __post_init__(self) -> None:
        _require_nonempty_str(self.residual_name, "ImposedMassFlowResidualBlueprint.residual_name")
        if self.kind is not ConfigurableResidualBlueprintKind.IMPOSED_MASS_FLOW:
            raise ValueError(
                "ImposedMassFlowResidualBlueprint.kind must be "
                f"IMPOSED_MASS_FLOW; got {self.kind!r}"
            )
        _require_nonempty_str(self.component_id, "ImposedMassFlowResidualBlueprint.component_id")
        _require_finite_scalar(self.mass_flow, "ImposedMassFlowResidualBlueprint.mass_flow")
        object.__setattr__(self, "mass_flow", float(self.mass_flow))

    def _to_algebraic_declaration(self) -> ImposedMassFlowResidualDeclaration:
        """Translate blueprint to an ImposedMassFlowResidualDeclaration.

        mass_flow_unknown = f"mdot:{component_id}".
        No pump model.  No flow prediction.
        """
        return ImposedMassFlowResidualDeclaration(
            residual_name=self.residual_name,
            mass_flow_unknown=f"mdot:{self.component_id}",
            imposed_value=self.mass_flow,
        )


# ---------------------------------------------------------------------------
# EnthalpyFlowResidualBlueprint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnthalpyFlowResidualBlueprint:
    """Explicit enthalpy-flow residual blueprint.

    Translates a mass-flow component ID into a mdot:<id> unknown name, then
    creates an EnthalpyFlowResidualDeclaration.  Heat-rate, h_in, and h_out
    unknowns are supplied explicitly by the caller.

    Translation
    -----------
        mdot_unknown = f"mdot:{mass_flow_component_id}"
        r = q - mdot * (h_out - h_in)
        → EnthalpyFlowResidualDeclaration(
               residual_name, heat_rate_unknown, mdot_unknown,
               h_in_unknown, h_out_unknown)

    Fields
    ------
    residual_name          : str — non-empty unique residual name
    heat_rate_unknown      : str — explicit heat-rate unknown name
    mass_flow_component_id : str — component ID (translates to mdot:<id>)
    h_in_unknown           : str — explicit inlet enthalpy unknown name
    h_out_unknown          : str — explicit outlet enthalpy unknown name

    Scalar algebra only.  No FluidState.  No property backend.  No phase,
    quality, saturation, or enthalpy-temperature conversion.
    """

    residual_name: str
    heat_rate_unknown: str
    mass_flow_component_id: str
    h_in_unknown: str
    h_out_unknown: str

    kind: ConfigurableResidualBlueprintKind = ConfigurableResidualBlueprintKind.ENTHALPY_FLOW

    def __post_init__(self) -> None:
        _require_nonempty_str(self.residual_name, "EnthalpyFlowResidualBlueprint.residual_name")
        if self.kind is not ConfigurableResidualBlueprintKind.ENTHALPY_FLOW:
            raise ValueError(
                "EnthalpyFlowResidualBlueprint.kind must be " f"ENTHALPY_FLOW; got {self.kind!r}"
            )
        for field_name, val in (
            ("heat_rate_unknown", self.heat_rate_unknown),
            ("mass_flow_component_id", self.mass_flow_component_id),
            ("h_in_unknown", self.h_in_unknown),
            ("h_out_unknown", self.h_out_unknown),
        ):
            _require_nonempty_str(val, f"EnthalpyFlowResidualBlueprint.{field_name}")

    def _to_algebraic_declaration(self) -> EnthalpyFlowResidualDeclaration:
        """Translate blueprint to an EnthalpyFlowResidualDeclaration.

        mdot_unknown = f"mdot:{mass_flow_component_id}".
        No property backend.  Scalar algebra only.
        """
        return EnthalpyFlowResidualDeclaration(
            residual_name=self.residual_name,
            q_unknown=self.heat_rate_unknown,
            mdot_unknown=f"mdot:{self.mass_flow_component_id}",
            h_in_unknown=self.h_in_unknown,
            h_out_unknown=self.h_out_unknown,
        )


# ---------------------------------------------------------------------------
# ConfigurableResidualBlueprintDeclaration — Union type alias
# ---------------------------------------------------------------------------

ConfigurableResidualBlueprintDeclaration = (
    MassBalanceResidualBlueprint
    | PressureDifferenceResidualBlueprint
    | ImposedPressureResidualBlueprint
    | ImposedMassFlowResidualBlueprint
    | EnthalpyFlowResidualBlueprint
)

_BLUEPRINT_TYPES = (
    MassBalanceResidualBlueprint,
    PressureDifferenceResidualBlueprint,
    ImposedPressureResidualBlueprint,
    ImposedMassFlowResidualBlueprint,
    EnthalpyFlowResidualBlueprint,
)


# ---------------------------------------------------------------------------
# ConfigurableResidualBlueprintSet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableResidualBlueprintSet:
    """Ordered, duplicate-name-rejecting collection of configurable residual blueprints.

    Validates that the blueprint sequence is non-empty, that all elements are
    valid blueprint types, and that residual names are unique.

    Fields
    ------
    blueprints     : tuple[ConfigurableResidualBlueprintDeclaration, ...]
    residual_names : tuple[str, ...] — ordered names extracted from blueprints
    blueprint_count: int             — number of blueprints
    """

    blueprints: tuple[ConfigurableResidualBlueprintDeclaration, ...]
    residual_names: tuple[str, ...]
    blueprint_count: int

    def __post_init__(self) -> None:
        bps = self.blueprints
        if not isinstance(bps, tuple):
            raise TypeError(
                "ConfigurableResidualBlueprintSet.blueprints must be a tuple; "
                f"got {type(bps).__name__!r}"
            )
        if not bps:
            raise ValueError("ConfigurableResidualBlueprintSet.blueprints must not be empty")
        for i, bp in enumerate(bps):
            if not isinstance(bp, _BLUEPRINT_TYPES):
                raise TypeError(
                    f"ConfigurableResidualBlueprintSet.blueprints[{i}] must be a "
                    "ConfigurableResidualBlueprintDeclaration; "
                    f"got {type(bp).__name__!r}"
                )
        # Validate residual name uniqueness.
        seen: dict[str, int] = {}
        for i, bp in enumerate(bps):
            name = bp.residual_name
            if name in seen:
                raise ValueError(
                    "ConfigurableResidualBlueprintSet: duplicate residual_name "
                    f"{name!r} at blueprint indices {seen[name]} and {i}"
                )
            seen[name] = i
        # Validate residual_names and blueprint_count consistency.
        if not isinstance(self.residual_names, tuple):
            raise TypeError("ConfigurableResidualBlueprintSet.residual_names must be a tuple")
        if not isinstance(self.blueprint_count, int):
            raise TypeError("ConfigurableResidualBlueprintSet.blueprint_count must be an int")


def build_configurable_residual_blueprint_set(
    blueprints: (
        tuple[ConfigurableResidualBlueprintDeclaration, ...]
        | list[ConfigurableResidualBlueprintDeclaration]
    ),
) -> ConfigurableResidualBlueprintSet:
    """Build a validated ConfigurableResidualBlueprintSet from a sequence of blueprints.

    Validates:
    - Each element is a valid ConfigurableResidualBlueprintDeclaration type.
    - Residual names are unique (no duplicates).
    - At least one blueprint is provided.

    No translation or evaluation is performed during construction.

    Parameters
    ----------
    blueprints : sequence of ConfigurableResidualBlueprintDeclaration

    Returns
    -------
    ConfigurableResidualBlueprintSet — frozen, validated

    Raises
    ------
    TypeError
        If blueprints is not a sequence or any element is not a blueprint type.
    ValueError
        If blueprints is empty or contains duplicate residual names.
    """
    if not isinstance(blueprints, (tuple, list)):
        raise TypeError(
            "build_configurable_residual_blueprint_set: blueprints must be a "
            f"tuple or list; got {type(blueprints).__name__!r}"
        )
    bp_tuple: tuple[ConfigurableResidualBlueprintDeclaration, ...] = tuple(blueprints)
    if not bp_tuple:
        raise ValueError("build_configurable_residual_blueprint_set: blueprints must not be empty")
    for i, bp in enumerate(bp_tuple):
        if not isinstance(bp, _BLUEPRINT_TYPES):
            raise TypeError(
                f"build_configurable_residual_blueprint_set: blueprints[{i}] must be "
                "a ConfigurableResidualBlueprintDeclaration; "
                f"got {type(bp).__name__!r}"
            )
    seen: dict[str, int] = {}
    for i, bp in enumerate(bp_tuple):
        name = bp.residual_name
        if name in seen:
            raise ValueError(
                "build_configurable_residual_blueprint_set: duplicate residual_name "
                f"{name!r} at blueprint indices {seen[name]} and {i}"
            )
        seen[name] = i
    residual_names = tuple(bp.residual_name for bp in bp_tuple)
    return ConfigurableResidualBlueprintSet(
        blueprints=bp_tuple,
        residual_names=residual_names,
        blueprint_count=len(bp_tuple),
    )


# ---------------------------------------------------------------------------
# ConfigurableResidualBlueprintBuildResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigurableResidualBlueprintBuildResult:
    """Frozen result of translating blueprints into 15F-A algebraic residual declarations.

    Fields
    ------
    blueprint_count               : int                          — number of blueprints
    blueprint_names               : tuple[str, ...]              — ordered residual names
    blueprint_kinds               : tuple[str, ...]              — kind enum values
    algebraic_residual_set        : ConfigurableAlgebraicResidualSet — translated set
    required_unknown_names        : tuple[str, ...]              — deduplicated, order-preserving
    scenario_compatibility_checked: bool                         — True if scenario provided
    scenario_is_compatible        : bool                         — False if not checked
    missing_unknowns              : tuple[str, ...]              — names not in scenario
    no_solve                      : bool                         — always True
    residuals_inferred_from_roles : bool                         — always False
    residuals_inferred_from_topology: bool                       — always False
    closures_inferred_from_roles  : bool                         — always False
    production_components_executed: bool                         — always False
    limitations                   : tuple[str, ...]
    """

    blueprint_count: int
    blueprint_names: tuple[str, ...]
    blueprint_kinds: tuple[str, ...]
    algebraic_residual_set: ConfigurableAlgebraicResidualSet
    required_unknown_names: tuple[str, ...]
    scenario_compatibility_checked: bool
    scenario_is_compatible: bool
    missing_unknowns: tuple[str, ...]
    no_solve: bool
    residuals_inferred_from_roles: bool
    residuals_inferred_from_topology: bool
    closures_inferred_from_roles: bool
    production_components_executed: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.algebraic_residual_set, ConfigurableAlgebraicResidualSet):
            raise TypeError(
                "ConfigurableResidualBlueprintBuildResult.algebraic_residual_set "
                "must be a ConfigurableAlgebraicResidualSet; "
                f"got {type(self.algebraic_residual_set).__name__!r}"
            )
        if not isinstance(self.no_solve, bool):
            raise TypeError("ConfigurableResidualBlueprintBuildResult.no_solve must be bool")
        if not self.no_solve:
            raise ValueError("ConfigurableResidualBlueprintBuildResult.no_solve must be True")
        for flag_name in (
            "residuals_inferred_from_roles",
            "residuals_inferred_from_topology",
            "closures_inferred_from_roles",
            "production_components_executed",
        ):
            val = getattr(self, flag_name)
            if not isinstance(val, bool):
                raise TypeError(
                    f"ConfigurableResidualBlueprintBuildResult.{flag_name} must be bool"
                )
            if val:
                raise ValueError(
                    f"ConfigurableResidualBlueprintBuildResult.{flag_name} must be False"
                )
        for seq_name in (
            "blueprint_names",
            "blueprint_kinds",
            "required_unknown_names",
            "missing_unknowns",
            "limitations",
        ):
            if not isinstance(getattr(self, seq_name), tuple):
                raise TypeError(
                    f"ConfigurableResidualBlueprintBuildResult.{seq_name} must be a tuple"
                )
        if not isinstance(self.blueprint_count, int):
            raise TypeError(
                "ConfigurableResidualBlueprintBuildResult.blueprint_count must be an int"
            )
        if not isinstance(self.scenario_compatibility_checked, bool):
            raise TypeError(
                "ConfigurableResidualBlueprintBuildResult.scenario_compatibility_checked "
                "must be bool"
            )
        if not isinstance(self.scenario_is_compatible, bool):
            raise TypeError(
                "ConfigurableResidualBlueprintBuildResult.scenario_is_compatible must be bool"
            )


# ---------------------------------------------------------------------------
# build_configurable_algebraic_residuals_from_blueprints
# ---------------------------------------------------------------------------


def build_configurable_algebraic_residuals_from_blueprints(
    blueprints: (
        ConfigurableResidualBlueprintSet | Sequence[ConfigurableResidualBlueprintDeclaration]
    ),
    *,
    scenario_build_result: object | None = None,
) -> ConfigurableResidualBlueprintBuildResult:
    """Build a ConfigurableResidualBlueprintBuildResult from explicit blueprints.

    Translates each blueprint into a 15F-A algebraic residual declaration, then
    assembles a ConfigurableAlgebraicResidualSet.

    Blueprint order is preserved.  Duplicate residual names are rejected.
    Empty blueprint sequences are rejected.

    No residuals are inferred from graph topology.
    No residuals are inferred from component roles.
    No closures are inferred from roles.
    No production components are executed.
    No solve is performed.

    Parameters
    ----------
    blueprints : ConfigurableResidualBlueprintSet or Sequence of blueprint types
        Explicit user-declared residual blueprints.
    scenario_build_result : ConfigurableScenarioBuildResult | None
        Optional.  If provided, the translated unknown names are validated against
        scenario_build_result.unknown_names.  Missing unknowns are reported
        deterministically in the build result.  If omitted, scenario compatibility
        is marked as not checked.

    Returns
    -------
    ConfigurableResidualBlueprintBuildResult — frozen, immutable

    Raises
    ------
    TypeError
        If blueprints is not a ConfigurableResidualBlueprintSet or Sequence.
        If any element is not a valid blueprint type.
        If scenario_build_result is provided but lacks an unknown_names attribute.
    ValueError
        If blueprints is empty.
        If blueprints contains duplicate residual names.
    """
    # Normalize blueprints to an ordered sequence of blueprint objects.
    if isinstance(blueprints, ConfigurableResidualBlueprintSet):
        bp_sequence: tuple[ConfigurableResidualBlueprintDeclaration, ...] = blueprints.blueprints
    elif isinstance(blueprints, (list, tuple)):
        bp_sequence = tuple(blueprints)
    elif hasattr(blueprints, "__iter__"):
        bp_sequence = tuple(blueprints)
    else:
        raise TypeError(
            "build_configurable_algebraic_residuals_from_blueprints: blueprints "
            "must be a ConfigurableResidualBlueprintSet or Sequence; "
            f"got {type(blueprints).__name__!r}"
        )

    if not bp_sequence:
        raise ValueError(
            "build_configurable_algebraic_residuals_from_blueprints: blueprints "
            "must not be empty"
        )

    for i, bp in enumerate(bp_sequence):
        if not isinstance(bp, _BLUEPRINT_TYPES):
            raise TypeError(
                "build_configurable_algebraic_residuals_from_blueprints: "
                f"blueprints[{i}] must be a ConfigurableResidualBlueprintDeclaration; "
                f"got {type(bp).__name__!r}"
            )

    # Reject duplicate residual names.
    seen_names: dict[str, int] = {}
    for i, bp in enumerate(bp_sequence):
        name = bp.residual_name
        if name in seen_names:
            raise ValueError(
                "build_configurable_algebraic_residuals_from_blueprints: "
                f"duplicate residual_name {name!r} at blueprint indices "
                f"{seen_names[name]} and {i}"
            )
        seen_names[name] = i

    # Translate each blueprint to a 15F-A algebraic residual declaration.
    declarations = [bp._to_algebraic_declaration() for bp in bp_sequence]

    # Build the algebraic residual set (preserves order, deduplicates unknowns).
    algebraic_residual_set = build_configurable_algebraic_residual_set(declarations)

    blueprint_names = tuple(bp.residual_name for bp in bp_sequence)
    blueprint_kinds = tuple(bp.kind.value for bp in bp_sequence)
    required_unknown_names = algebraic_residual_set.required_unknown_names

    # Scenario compatibility validation.
    scenario_compatibility_checked = False
    scenario_is_compatible = False
    missing_unknowns: tuple[str, ...] = ()

    if scenario_build_result is not None:
        if not hasattr(scenario_build_result, "unknown_names"):
            raise TypeError(
                "build_configurable_algebraic_residuals_from_blueprints: "
                "scenario_build_result must have an 'unknown_names' attribute "
                "(expected ConfigurableScenarioBuildResult)"
            )
        scenario_unknown_set = set(scenario_build_result.unknown_names)
        missing_list = [name for name in required_unknown_names if name not in scenario_unknown_set]
        missing_unknowns = tuple(sorted(missing_list))
        scenario_compatibility_checked = True
        scenario_is_compatible = len(missing_unknowns) == 0

    return ConfigurableResidualBlueprintBuildResult(
        blueprint_count=len(bp_sequence),
        blueprint_names=blueprint_names,
        blueprint_kinds=blueprint_kinds,
        algebraic_residual_set=algebraic_residual_set,
        required_unknown_names=required_unknown_names,
        scenario_compatibility_checked=scenario_compatibility_checked,
        scenario_is_compatible=scenario_is_compatible,
        missing_unknowns=missing_unknowns,
        no_solve=True,
        residuals_inferred_from_roles=False,
        residuals_inferred_from_topology=False,
        closures_inferred_from_roles=False,
        production_components_executed=False,
        limitations=_LIMITATIONS,
    )


# ---------------------------------------------------------------------------
# build_configurable_residual_blueprint_report
# ---------------------------------------------------------------------------


def build_configurable_residual_blueprint_report(
    build_result: ConfigurableResidualBlueprintBuildResult,
) -> dict[str, object]:
    """Build a plain JSON-serializable report for a blueprint build result.

    Returns a plain dict with only JSON-serializable values (str, int, bool,
    list, dict, None).  No file writes.  No pandas.

    Always includes:
        status: "configurable_residual_blueprint_build"
        no_solve: True
        residuals_inferred_from_roles: False
        residuals_inferred_from_topology: False
        closures_inferred_from_roles: False
        production_components_executed: False

    Parameters
    ----------
    build_result : ConfigurableResidualBlueprintBuildResult

    Returns
    -------
    dict[str, object] — JSON-serializable report

    Raises
    ------
    TypeError
        If build_result is not a ConfigurableResidualBlueprintBuildResult.
    """
    if not isinstance(build_result, ConfigurableResidualBlueprintBuildResult):
        raise TypeError(
            "build_configurable_residual_blueprint_report: build_result must be a "
            "ConfigurableResidualBlueprintBuildResult; "
            f"got {type(build_result).__name__!r}"
        )

    rs = build_result.algebraic_residual_set
    scenario_compat: dict[str, object] = {
        "checked": build_result.scenario_compatibility_checked,
        "is_compatible": (
            build_result.scenario_is_compatible
            if build_result.scenario_compatibility_checked
            else None
        ),
        "missing_unknowns": list(build_result.missing_unknowns),
    }

    report: dict[str, object] = {
        "status": "configurable_residual_blueprint_build",
        "no_solve": True,
        "residuals_inferred_from_roles": False,
        "residuals_inferred_from_topology": False,
        "closures_inferred_from_roles": False,
        "production_components_executed": False,
        "blueprint_count": build_result.blueprint_count,
        "blueprint_names": list(build_result.blueprint_names),
        "blueprint_kinds": list(build_result.blueprint_kinds),
        "residual_names_generated": list(rs.residual_names),
        "required_unknown_names": list(build_result.required_unknown_names),
        "scenario_compatibility": scenario_compat,
        "limitations": list(build_result.limitations),
    }

    # Verify JSON-serializability before returning.
    json.dumps(report)
    return report
