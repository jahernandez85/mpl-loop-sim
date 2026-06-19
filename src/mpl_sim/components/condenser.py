"""CondenserComponent — Phase 11D / Phase 11Q / Phase 11R.

Foundational condenser component: immutable, local, physics-free skeleton
with a minimal evaluate_heat_exchanger helper.

Phase 11D:
  - CondenserHXInput   : scalar inputs for evaluate_heat_exchanger
  - CondenserComponent : inlet/outlet ports, ComponentKind.CONDENSER,
                         evaluate_heat_exchanger method

Phase 11Q:
  - CondenserHXInput adds q_flux_primary and dp_primary_is_two_phase,
    forwarded explicitly to HXSolveRequest so callers can use YanCondensationHTC
    with two-phase DP closures without hidden defaults.

Phase 11R:
  - CondenserScenarioBinding : immutable frozen dataclass holding all
    scenario-specific config (everything except runtime primary_state_in and
    primary_mdot), including q_flux_primary and dp_primary_is_two_phase from
    Phase 11Q.  geom_scalars is stored as MappingProxyType to prevent mutation.
  - CondenserComponent.evaluate_scenario : scenario-bound helper that builds
    CondenserHXInput from runtime state + immutable scenario binding and
    delegates to evaluate_heat_exchanger.  Not the frozen contribute(trial, ctx)
    contract from INTERFACE_SPEC §11.1, which remains deferred.

Sign convention for Q (inherited from HXSolveResult via HXSolveRequest):
  Q < 0  — primary fluid rejects heat (standard condenser sense)

Internal state seam (V1):
  () — no internal states declared; condenser plates have no V1 wall capacitance.

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
from types import MappingProxyType

from mpl_sim.components.base import Component, ComponentId, ComponentKind
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.core.port import Port, PortId, PortRole
from mpl_sim.correlations.contract import Correlation
from mpl_sim.discretization.primitives import DiscretizationSpec
from mpl_sim.geometry.primitives import PlateGeometry
from mpl_sim.hx_models.base import (
    HeatExchangerModel,
    HXSolveRequest,
    HXSolveResult,
    PrimaryThermalMode,
    SecondaryFluidBC,
    UAComputationMode,
)

# ---------------------------------------------------------------------------
# CondenserHXInput — scalar inputs for evaluate_heat_exchanger
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CondenserHXInput:
    """Scalar inputs for CondenserComponent.evaluate_heat_exchanger.

    Fields
    ------
    primary_state_in    : inlet fluid state (P, h, identity)
    primary_mdot        : primary-side mass flow rate [kg/s]
    secondary_bc        : boundary condition on the secondary side
    model               : injected HX model strategy object
    discretization      : discretization specification for this evaluation
    geom_scalars        : flat scalar bag for correlation inputs
    htc_primary         : optional injected primary-side HTC correlation
    htc_secondary       : optional injected secondary-side HTC correlation
    dp_primary          : optional injected primary-side DP correlation
    htc_multiplier      : calibration multiplier for HTC output; default 1.0
    friction_multiplier : calibration multiplier for DP output; default 1.0
    q_flux_primary      : optional wall heat flux [W/m²] for the primary side;
                          forwarded unchanged to HXSolveRequest.q_flux_primary;
                          must be finite and > 0 if supplied; default None
    dp_primary_is_two_phase : when True the HX model builds TwoPhaseDPInput
                          for dp_primary and converts Pa/m gradient to Pa;
                          default False (single-phase DP path)
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
    q_flux_primary: float | None = None
    dp_primary_is_two_phase: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.geom_scalars, Mapping):
            object.__setattr__(self, "geom_scalars", {})
        else:
            object.__setattr__(self, "geom_scalars", dict(self.geom_scalars))


# ---------------------------------------------------------------------------
# CondenserScenarioBinding — Phase 11R
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CondenserScenarioBinding:
    """Immutable scenario config for CondenserComponent.evaluate_scenario.

    Holds everything needed to evaluate the condenser except the runtime
    primary fluid state and mass flow rate, which are supplied separately
    to CondenserComponent.evaluate_scenario at call time.

    All fields mirror CondenserHXInput minus primary_state_in and
    primary_mdot, so a caller can bind a scenario once and reuse it across
    multiple evaluate_scenario calls with different runtime states.

    Note: this is NOT the frozen contribute(trial, ctx) contract from
    INTERFACE_SPEC §11.1.  That contract remains deferred.  This helper
    provides scenario-bound evaluation without a full EvalContext.

    Fields
    ------
    secondary_bc        : boundary condition on the secondary side
    model               : injected HX model strategy object
    discretization      : discretization specification
    geom_scalars        : flat scalar bag for correlation inputs
    htc_primary         : optional primary-side HTC correlation
    htc_secondary       : optional secondary-side HTC correlation
    dp_primary          : optional primary-side DP correlation
    htc_multiplier      : calibration multiplier for HTC output; default 1.0
    friction_multiplier : calibration multiplier for DP output; default 1.0
    primary_T_in        : optional primary inlet temperature [K]
    primary_cp          : optional primary specific heat [J/kg/K]
    primary_thermal_mode : optional primary thermal capacity mode
    ua_computation_mode : optional UA computation mode
    q_flux_primary      : optional wall heat flux [W/m²] (Phase 11Q);
                          forwarded to HXSolveRequest.q_flux_primary
    dp_primary_is_two_phase : when True, HX model builds TwoPhaseDPInput
                          (Phase 11Q); default False
    """

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
    q_flux_primary: float | None = None
    dp_primary_is_two_phase: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.geom_scalars, Mapping):
            object.__setattr__(self, "geom_scalars", MappingProxyType({}))
        else:
            object.__setattr__(
                self,
                "geom_scalars",
                MappingProxyType(dict(self.geom_scalars)),
            )


# ---------------------------------------------------------------------------
# CondenserComponent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CondenserComponent(Component):
    """Foundational condenser component — Phase 11D.

    An immutable component representing a plate heat exchanger condenser.
    Declares one inlet port and one outlet port.

    Fields
    ------
    component_id : stable identity for this component
    geometry     : PlateGeometry — inert, immutable; no physics computed here

    Exposed interface:
        kind()                       → ComponentKind.CONDENSER
        inlet                        → Port (INLET, peer=None before assembly)
        outlet                       → Port (OUTLET, peer=None before assembly)
        ports()                      → (inlet, outlet)
        internal_state_names()       → ()  — no V1 internal states
        evaluate_heat_exchanger(...) → HXSolveResult  (primary evaluation path)
        evaluate_scenario(...)       → HXSolveResult  (scenario-bound helper; Phase 11R)

    Must NOT:
        - call CoolProp, PropertyBackend
        - reference Network or Solver
        - mutate any object
        - store or compute thermodynamic state values
        - store correlation or HX model objects on the component
    """

    component_id: ComponentId
    geometry: PlateGeometry

    # ------------------------------------------------------------------
    # Component contract — structural declarations
    # ------------------------------------------------------------------

    def kind(self) -> ComponentKind:
        """Returns ComponentKind.CONDENSER."""
        return ComponentKind.CONDENSER

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
        """No internal states declared in V1 condenser."""
        return ()

    # ------------------------------------------------------------------
    # Phase 11R: scenario-bound helper (not the frozen contribute(trial, ctx))
    # ------------------------------------------------------------------

    def evaluate_scenario(
        self,
        primary_state_in: FluidState,
        primary_mdot: float,
        scenario: CondenserScenarioBinding,
    ) -> HXSolveResult:
        """Scenario-bound helper: build CondenserHXInput from runtime state + scenario.

        Combines the runtime primary fluid state and mass flow rate with the
        pre-bound immutable scenario configuration, then delegates to
        evaluate_heat_exchanger.  No registry is accessed here; no closures
        are chosen automatically.

        This is NOT the frozen contribute(trial, ctx) -> ComponentContribution
        contract from INTERFACE_SPEC §11.1.  That path remains deferred.

        Parameters
        ----------
        primary_state_in : FluidState — runtime inlet fluid state
        primary_mdot     : float — runtime primary mass flow rate [kg/s]
        scenario         : CondenserScenarioBinding — pre-bound scenario config

        Returns
        -------
        HXSolveResult
        """
        inp = CondenserHXInput(
            primary_state_in=primary_state_in,
            primary_mdot=primary_mdot,
            secondary_bc=scenario.secondary_bc,
            model=scenario.model,
            discretization=scenario.discretization,
            geom_scalars=scenario.geom_scalars,
            htc_primary=scenario.htc_primary,
            htc_secondary=scenario.htc_secondary,
            dp_primary=scenario.dp_primary,
            htc_multiplier=scenario.htc_multiplier,
            friction_multiplier=scenario.friction_multiplier,
            primary_T_in=scenario.primary_T_in,
            primary_cp=scenario.primary_cp,
            primary_thermal_mode=scenario.primary_thermal_mode,
            ua_computation_mode=scenario.ua_computation_mode,
            q_flux_primary=scenario.q_flux_primary,
            dp_primary_is_two_phase=scenario.dp_primary_is_two_phase,
        )
        return self.evaluate_heat_exchanger(inp)

    # ------------------------------------------------------------------
    # Phase 11D: heat-exchanger evaluation helper (primary evaluation path)
    # ------------------------------------------------------------------

    def evaluate_heat_exchanger(
        self,
        inp: CondenserHXInput,
    ) -> HXSolveResult:
        """Build an HXSolveRequest and delegate to the injected HX model.

        Assembles HXSolveRequest from *inp* and this component's geometry,
        then calls inp.model.solve(req).  No registry is accessed here.

        Parameters
        ----------
        inp : CondenserHXInput

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
            q_flux_primary=inp.q_flux_primary,
            dp_primary_is_two_phase=inp.dp_primary_is_two_phase,
        )
        return inp.model.solve(req)
