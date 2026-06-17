"""EvaporatorComponent — Phase 11C.

Foundational evaporator component: immutable, local, physics-free skeleton
with a minimal evaluate_heat_exchanger helper.

Phase 11C:
  - EvaporatorHXInput   : scalar inputs for evaluate_heat_exchanger
  - EvaporatorHXResult  : result of evaluate_heat_exchanger (aliases HXSolveResult)
  - EvaporatorComponent : inlet/outlet ports, ComponentKind.EVAPORATOR,
                          evaluate_heat_exchanger method

Sign convention for Q (inherited from HXSolveResult via HXSolveRequest):
  Q > 0  — primary fluid gains enthalpy (standard evaporator sense)

Internal state seam (V1):
  ("T_wall",) — wall temperature named and frozen; no dynamic equation computed.

Hard constraints respected:
  - No CoolProp.
  - No PropertyBackend.
  - No network / solver.
  - No mutation of any object.
  - No derived thermodynamic state stored on component or ports.
  - Correlation objects injected at call time, not stored on component.
  - HX model object injected at call time, not stored on component.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from mpl_sim.components.base import Component, ComponentId, ComponentKind
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.core.port import Port, PortId, PortRole
from mpl_sim.correlations.contract import Correlation
from mpl_sim.discretization.primitives import DiscretizationSpec
from mpl_sim.geometry.primitives import MicrochannelGeometry
from mpl_sim.hx_models.base import (
    HeatExchangerModel,
    HXSolveRequest,
    HXSolveResult,
    PrimaryThermalMode,
    SecondaryFluidBC,
    UAComputationMode,
)

# ---------------------------------------------------------------------------
# EvaporatorHXInput — scalar inputs for evaluate_heat_exchanger
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaporatorHXInput:
    """Scalar inputs for EvaporatorComponent.evaluate_heat_exchanger.

    Fields
    ------
    primary_state_in    : inlet fluid state (P, h, identity)
    primary_mdot        : primary-side mass flow rate [kg/s]
    secondary_bc        : boundary condition on the secondary side (heat load)
    model               : injected HX model strategy object
    discretization      : discretization specification for this evaluation
    geom_scalars        : flat scalar bag for correlation inputs
                          (e.g. "G", "D_h", "roughness", "L_cell", "rho", "mu")
    htc_primary         : optional injected primary-side HTC correlation
    htc_secondary       : optional injected secondary-side HTC correlation
    dp_primary          : optional injected primary-side DP correlation
    htc_multiplier      : calibration multiplier for HTC output; default 1.0
    friction_multiplier : calibration multiplier for DP output; default 1.0
    """

    primary_state_in: FluidState
    primary_mdot: float
    secondary_bc: SecondaryFluidBC
    model: HeatExchangerModel
    discretization: DiscretizationSpec
    geom_scalars: Mapping[str, float] = ()  # type: ignore[assignment]
    htc_primary: Correlation | None = None
    htc_secondary: Correlation | None = None
    dp_primary: Correlation | None = None
    htc_multiplier: float = 1.0
    friction_multiplier: float = 1.0
    primary_T_in: float | None = None
    primary_cp: float | None = None
    primary_thermal_mode: PrimaryThermalMode | None = None
    ua_computation_mode: UAComputationMode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.geom_scalars, Mapping):
            object.__setattr__(self, "geom_scalars", {})
        else:
            object.__setattr__(self, "geom_scalars", dict(self.geom_scalars))


# ---------------------------------------------------------------------------
# EvaporatorComponent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaporatorComponent(Component):
    """Foundational evaporator component — Phase 11C.

    An immutable component representing a microchannel evaporator.
    Declares one inlet port and one outlet port.

    Fields
    ------
    component_id : stable identity for this component
    geometry     : MicrochannelGeometry — inert, immutable; no physics computed here

    Exposed interface:
        kind()                       → ComponentKind.EVAPORATOR
        inlet                        → Port (INLET, peer=None before assembly)
        outlet                       → Port (OUTLET, peer=None before assembly)
        ports()                      → (inlet, outlet)
        internal_state_names()       → ("T_wall",)  — wall temperature named, frozen V1
        evaluate_heat_exchanger(...) → HXSolveResult

    Must NOT:
        - call CoolProp, PropertyBackend
        - reference Network or Solver
        - mutate any object
        - store or compute thermodynamic state values
        - store correlation or HX model objects on the component
    """

    component_id: ComponentId
    geometry: MicrochannelGeometry

    # ------------------------------------------------------------------
    # Component contract — structural declarations
    # ------------------------------------------------------------------

    def kind(self) -> ComponentKind:
        """Returns ComponentKind.EVAPORATOR."""
        return ComponentKind.EVAPORATOR

    @property
    def inlet(self) -> Port:
        """Declared inlet port (peer=None before Network assembly)."""
        return Port(
            id=PortId(component_id=self.component_id.name, port_name="in"),
            owner=self.component_id.name,
            role=PortRole.INLET,
            peer=None,
        )

    @property
    def outlet(self) -> Port:
        """Declared outlet port (peer=None before Network assembly)."""
        return Port(
            id=PortId(component_id=self.component_id.name, port_name="out"),
            owner=self.component_id.name,
            role=PortRole.OUTLET,
            peer=None,
        )

    def ports(self) -> tuple[Port, ...]:
        """Returns (inlet, outlet) — exactly two ports in V1."""
        return (self.inlet, self.outlet)

    def internal_state_names(self) -> tuple[str, ...]:
        """Named internal state: T_wall (wall temperature, frozen seam V1).

        No dynamic equation is computed; no derivative is assembled.
        """
        return ("T_wall",)

    # ------------------------------------------------------------------
    # Phase 11C: heat-exchanger evaluation helper
    # ------------------------------------------------------------------

    def evaluate_heat_exchanger(
        self,
        inp: EvaporatorHXInput,
    ) -> HXSolveResult:
        """Build an HXSolveRequest and delegate to the injected HX model.

        Assembles HXSolveRequest from *inp* and this component's geometry,
        then calls inp.model.solve(req).  No registry is accessed here.

        Parameters
        ----------
        inp : EvaporatorHXInput

        Returns
        -------
        HXSolveResult
        """
        req = HXSolveRequest(
            primary_state_in=inp.primary_state_in,
            primary_mdot=inp.primary_mdot,
            secondary_bc=inp.secondary_bc,
            geometry=self.geometry,
            discretization=inp.discretization,
            geom_scalars=inp.geom_scalars,
            htc_primary=inp.htc_primary,
            htc_secondary=inp.htc_secondary,
            dp_primary=inp.dp_primary,
            htc_multiplier=inp.htc_multiplier,
            friction_multiplier=inp.friction_multiplier,
            primary_T_in=inp.primary_T_in,
            primary_cp=inp.primary_cp,
            primary_thermal_mode=inp.primary_thermal_mode,
            ua_computation_mode=inp.ua_computation_mode,
        )
        return inp.model.solve(req)
