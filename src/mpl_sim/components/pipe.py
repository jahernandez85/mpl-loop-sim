"""Pipe component — Phase 6C: gravity pressure contribution added.

Defines the Pipe component: an immutable value object that holds a
PipeGeometry and DiscretizationSpec, declares inlet and outlet ports, and
exposes evaluate_single_phase_friction (Phase 6B) and evaluate_gravity_pressure
(Phase 6C).

Phase 6B adds:
- PipeSinglePhaseFrictionInput: scalar input value object for friction eval
- PipeFrictionResult: result value object (gradient, total ΔP, verdict, metadata)
- Pipe.evaluate_single_phase_friction: calls a SINGLE_PHASE_DP correlation

Phase 6C adds:
- PipeGravityInput: scalar input value object (rho, g)
- PipeGravityResult: result value object (delta_p_gravity, rho, g, delta_z)
- Pipe.evaluate_gravity_pressure: pure arithmetic; reads delta_z from geometry

Sign convention (Phase 6C):
  delta_p_gravity = rho * g * delta_z
  positive delta_z → outlet is higher than inlet → positive delta_p_gravity
  (pressure required/lost lifting the fluid upward)

Hard constraints respected in Phase 6C:
- No acceleration.
- No heat transfer.
- No energy balance.
- No phase change / two-phase.
- No network / solvers.
- No CoolProp.
- No PropertyBackend.
- No CalibrationRegistry.
- Pipe, geometry, discretization, and inputs are never mutated.
- evaluate_gravity_pressure does not call any correlation.

Calibration deferred note:
  A scalar friction-gradient multiplier (CalibrationModifier.MULTIPLIER on
  FRICTION_GRADIENT) is structurally possible via calibration.primitives, but
  wiring it into evaluate_single_phase_friction is deferred to a dedicated
  calibration-integration sub-phase to keep this patch narrow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from mpl_sim.components.base import Component, ComponentId, ComponentKind
from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.core.port import Port, PortId, PortRole
from mpl_sim.correlations.contract import (
    ClosureMetadata,
    Correlation,
    CorrelationRole,
    SinglePhaseDPInput,
    ValidityVerdict,
)
from mpl_sim.discretization.primitives import DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry

# ---------------------------------------------------------------------------
# Placeholder FluidState
# ---------------------------------------------------------------------------
# SinglePhaseDPInput requires a state tuple, but every SINGLE_PHASE_DP closure
# in the current framework derives friction entirely from G, D_h, roughness,
# rho, and mu.  The state field is a seam for future closures that need
# additional thermodynamic context.  We supply one structural placeholder so
# the contract is satisfied without calling PropertyBackend.
_PLACEHOLDER_FLUID_STATE = FluidState(P=0.0, h=0.0, identity=PureFluid("_unspecified"))


# ---------------------------------------------------------------------------
# PipeSinglePhaseFrictionInput
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipeSinglePhaseFrictionInput:
    """Input for Pipe.evaluate_single_phase_friction.

    All fields are physical scalars; no FluidState is stored.

    Sign convention: G may be positive or negative; friction uses |G| and
    always returns a non-negative pressure gradient (friction opposes flow
    regardless of direction).

    Fields:
        G   : mass flux [kg/m²s]  — finite; zero allowed (returns zero friction)
        rho : fluid density [kg/m³]  — must be > 0
        mu  : dynamic viscosity [Pa·s] — must be > 0
    """

    G: float
    rho: float
    mu: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.G):
            raise ValueError(f"PipeSinglePhaseFrictionInput.G must be finite; got {self.G!r}")
        if not (math.isfinite(self.rho) and self.rho > 0.0):
            raise ValueError(f"PipeSinglePhaseFrictionInput.rho must be > 0; got {self.rho!r}")
        if not (math.isfinite(self.mu) and self.mu > 0.0):
            raise ValueError(f"PipeSinglePhaseFrictionInput.mu must be > 0; got {self.mu!r}")


# ---------------------------------------------------------------------------
# PipeFrictionResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipeFrictionResult:
    """Result of Pipe.evaluate_single_phase_friction.

    Friction only — no gravity, acceleration, or heat transfer.

    Fields:
        dp_dx_friction   : friction pressure gradient [Pa/m] (non-negative)
        delta_p_friction : total friction pressure loss [Pa]
                           = dp_dx_friction × pipe.geometry.L  (non-negative)
        verdict          : per-call validity verdict from the correlation
        metadata         : correlation provenance (name, version, source)
    """

    dp_dx_friction: float
    delta_p_friction: float
    verdict: ValidityVerdict
    metadata: ClosureMetadata


# ---------------------------------------------------------------------------
# PipeGravityInput
# ---------------------------------------------------------------------------

_STANDARD_GRAVITY: float = 9.80665  # m/s²


@dataclass(frozen=True)
class PipeGravityInput:
    """Input for Pipe.evaluate_gravity_pressure.

    Fields:
        rho : fluid density [kg/m³]  — must be > 0
        g   : gravitational acceleration [m/s²]  — must be > 0;
              defaults to standard gravity (9.80665 m/s²)

    delta_z is not a field here — it is read directly from the Pipe's
    geometry.trajectory so that this object carries only fluid properties
    and the gravitational constant.
    """

    rho: float
    g: float = _STANDARD_GRAVITY

    def __post_init__(self) -> None:
        if not (math.isfinite(self.rho) and self.rho > 0.0):
            raise ValueError(f"PipeGravityInput.rho must be > 0; got {self.rho!r}")
        if not (math.isfinite(self.g) and self.g > 0.0):
            raise ValueError(f"PipeGravityInput.g must be > 0; got {self.g!r}")


# ---------------------------------------------------------------------------
# PipeGravityResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipeGravityResult:
    """Result of Pipe.evaluate_gravity_pressure.

    Gravity only — no friction, acceleration, or heat transfer.

    Sign convention:
        delta_p_gravity = rho * g * delta_z
        positive delta_z  → outlet is higher than inlet
        positive delta_p_gravity → pressure required/lost lifting fluid upward

    Fields:
        delta_p_gravity : gravity pressure contribution [Pa]
        rho             : density used [kg/m³]
        g               : gravitational acceleration used [m/s²]
        delta_z         : elevation change (outlet − inlet) [m] from geometry
    """

    delta_p_gravity: float
    rho: float
    g: float
    delta_z: float


# ---------------------------------------------------------------------------
# Pipe
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pipe(Component):
    """Pipe component.

    An immutable component describing a single-passage pipe.  Stores geometry
    and discretization declarations, exposes two ports (inlet and outlet), and
    from Phase 6B exposes evaluate_single_phase_friction.

    Fields:
        component_id  : stable identity for this component
        geometry      : PipeGeometry — stored by reference; never mutated
        discretization: DiscretizationSpec — stored by reference; never mutated

    Exposed interface:
        kind()                       → ComponentKind.PIPE
        inlet                        → Port (peer=None before assembly)
        outlet                       → Port (peer=None before assembly)
        ports()                      → (inlet, outlet) — exactly two in V1
        internal_state_names()       → () — deferred to future phase
        evaluate_single_phase_friction(...) → PipeFrictionResult  (Phase 6B)
        evaluate_gravity_pressure(...)      → PipeGravityResult   (Phase 6C)

    Must NOT compute:
        acceleration term, heat transfer, phase, quality, HTC, Nu.

    Must NOT call:
        PropertyBackend, CalibrationRegistry, CoolProp.

    Must NOT contain:
        pressure, enthalpy, mdot, fluid state values, residuals, solver data,
        mesh nodes, or cell state beyond the DiscretizationSpec.
    """

    component_id: ComponentId
    geometry: PipeGeometry
    discretization: DiscretizationSpec

    # ------------------------------------------------------------------
    # Component contract — structural declarations
    # ------------------------------------------------------------------

    def kind(self) -> ComponentKind:
        """Returns ComponentKind.PIPE."""
        return ComponentKind.PIPE

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
        """Named internal states — empty; per-segment states deferred."""
        return ()

    # ------------------------------------------------------------------
    # Phase 6B: single-phase friction kernel
    # ------------------------------------------------------------------

    def evaluate_single_phase_friction(
        self,
        inp: PipeSinglePhaseFrictionInput,
        correlation: Correlation,
    ) -> PipeFrictionResult:
        """Evaluate single-phase friction pressure drop for this pipe.

        Computes:
            dp_dx_friction  = correlation output [Pa/m]  (non-negative)
            delta_p_friction = dp_dx_friction × geometry.L  [Pa]

        Friction only — gravity, acceleration, and heat transfer are not
        included.  Neither the Pipe, its geometry, nor the inputs are mutated.

        Parameters
        ----------
        inp         : PipeSinglePhaseFrictionInput — scalar fluid properties
        correlation : a Correlation whose role() is SINGLE_PHASE_DP

        Returns
        -------
        PipeFrictionResult

        Raises
        ------
        TypeError
            If *correlation* is not a Correlation instance.
        ValueError
            If *correlation*.role() is not CorrelationRole.SINGLE_PHASE_DP.
        """
        if not isinstance(correlation, Correlation):
            raise TypeError(
                f"correlation must be a Correlation instance; got {type(correlation)!r}"
            )
        if correlation.role() is not CorrelationRole.SINGLE_PHASE_DP:
            raise ValueError(
                f"correlation role must be SINGLE_PHASE_DP; got {correlation.role()!r}"
            )

        # Build the correlation input.
        # state is required by the contract but unused by any current
        # SINGLE_PHASE_DP closure; rho and mu carry the friction-relevant
        # fluid properties.  _PLACEHOLDER_FLUID_STATE satisfies the contract
        # without calling PropertyBackend.
        corr_inp = SinglePhaseDPInput(
            state=(_PLACEHOLDER_FLUID_STATE,),
            G=inp.G,
            D_h=self.geometry.D_h,
            roughness=self.geometry.roughness,
            L_cell=self.geometry.L,
            rho=inp.rho,
            mu=inp.mu,
        )

        output = correlation.evaluate(corr_inp)
        dp_dx = output.value[0]

        return PipeFrictionResult(
            dp_dx_friction=dp_dx,
            delta_p_friction=dp_dx * self.geometry.L,
            verdict=output.verdict,
            metadata=output.metadata,
        )

    # ------------------------------------------------------------------
    # Phase 6C: gravity pressure contribution
    # ------------------------------------------------------------------

    def evaluate_gravity_pressure(
        self,
        inp: PipeGravityInput,
    ) -> PipeGravityResult:
        """Evaluate the gravity pressure contribution for this pipe.

        Computes:
            delta_p_gravity = rho * g * delta_z

        where delta_z is read from self.geometry.trajectory.delta_z.

        Sign convention:
            positive delta_z  → outlet is higher than inlet
            positive delta_p_gravity → pressure required/lost lifting fluid upward
            zero delta_z → horizontal pipe → zero gravity contribution
            negative delta_z → outlet lower → negative delta_p_gravity (pressure recovered)

        No correlation is called.  No PropertyBackend is called.  Neither
        the Pipe, its geometry, nor inp are mutated.

        Parameters
        ----------
        inp : PipeGravityInput — density and gravitational acceleration

        Returns
        -------
        PipeGravityResult
        """
        delta_z = self.geometry.trajectory.delta_z
        delta_p_gravity = inp.rho * inp.g * delta_z
        return PipeGravityResult(
            delta_p_gravity=delta_p_gravity,
            rho=inp.rho,
            g=inp.g,
            delta_z=delta_z,
        )
