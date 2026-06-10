"""
components/pipe.py — Single-Phase & Two-Phase Pipe Component
=============================================================
MPL Simulation Library — Module 3b (Phase 3)

Implements a 1D adiabatic (or heat-loss) pipe for the MPL loop.
Supports:
  • Single-phase liquid or vapour  (Blasius / Churchill / Gnielinski)
  • Two-phase (homogeneous / Kim-Mudawar 2013 / Müller-Steinhagen-Heck)
  • Horizontal, vertical-up, vertical-down orientations
  • Optional uniform heat loss Q_loss [W]

Pressure drop model
-------------------
ΔP_total = ΔP_friction + ΔP_gravity + ΔP_acceleration

  ΔP_friction:     configurable DPCorrelation (Strategy Pattern)
                   Default: HomogeneousDP for two-phase, BlassiusDP for liquid
  ΔP_gravity:      ρ_tp · g · L · sin(θ)
                   sign convention: positive when flow goes against gravity
  ΔP_acceleration: G² · Δ(1/ρ) — only for two-phase with enthalpy change

Energy balance
--------------
For a pipe with uniform Q_loss [W] (default 0):
  h_out = h_in − Q_loss / mdot

If Q_loss = 0 the pipe is purely adiabatic and h_out = h_in.

State update
------------
Outlet state is constructed from (P_out, h_out) via FluidState.from_Ph,
consistent with (P, h) as the primary state variables (VanGerner 2016).

Two-phase handling
------------------
Phase can change along the pipe (e.g. partial condensation due to heat loss).
The model treats the pipe as a lumped element with inlet conditions driving the
correlation choice. A mixed-phase check is performed at the outlet: if the
outlet enthalpy falls outside the two-phase dome, the correct single-phase
state is used.

References
----------
[1]  T.N. Dogan (1983) — HEM: ΔP_friction, ΔP_gravity, ΔP_acceleration
[2]  R. Kokate & C. Park (2023) — pipe model in P2PL loop
[3]  M. VanGerner et al. (2016) — (P,h) state variables
[4]  S.-M. Kim & I. Mudawar (2013) — two-phase ΔP correlation
[5]  H. Müller-Steinhagen & K. Heck (1986) — MSH ΔP correlation
[6]  W.S. Churchill (1977) — unified friction factor
[7]  Truster et al. (2024) — pipe component energy/mass/momentum equations
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Optional, Callable

import numpy as np

# ---------------------------------------------------------------------------
# Sibling imports — lazy to allow isolated testing with stubs
# ---------------------------------------------------------------------------
try:
    from fluid_properties import FluidState
    _FLUID_PROPS_AVAILABLE = True
except ImportError:
    _FLUID_PROPS_AVAILABLE = False

try:
    from correlations import (
        BlassiusDP, HomogeneousDP, KimMudawar2013DP, GnielinskiHTC,
        DittusBoelterHTC, acceleration_pressure_gradient,
        gravity_pressure_gradient,
    )
    _CORR_AVAILABLE = True
except ImportError:
    _CORR_AVAILABLE = False

from base import Component, Port, Orientation, ComponentError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
G_EARTH = 9.806   # m/s²  — standard gravity


# ---------------------------------------------------------------------------
# PipeGeometry — all geometric parameters in one dataclass
# ---------------------------------------------------------------------------

@dataclass
class PipeGeometry:
    """
    Geometric parameters for a circular pipe.

    Parameters
    ----------
    D_i : float
        Inner diameter [m].
    L : float
        Pipe length [m].
    roughness : float
        Absolute wall roughness [m]. Default 1.5e-6 m (drawn tubing).
    orientation : str
        Flow orientation: 'horizontal' | 'vertical_up' | 'vertical_down'.
        Default: 'horizontal'.
    n_passes : int
        Number of parallel passes (for multi-tube arrangements). Default 1.
        G_per_tube = mdot / (n_passes · A_c_single)

    Derived
    -------
    A_c   : cross-sectional area [m²] = π D_i² / 4
    P_wet : wetted perimeter [m]      = π D_i
    D_h   : hydraulic diameter [m]    = D_i  (circular)
    V     : pipe volume [m³]          = A_c · L
    """
    D_i:         float
    L:           float
    roughness:   float = 1.5e-6   # drawn copper/SS tubing
    orientation: str   = Orientation.HORIZONTAL
    n_passes:    int   = 1

    def __post_init__(self) -> None:
        Orientation.validate(self.orientation)
        if self.D_i <= 0:
            raise ValueError(f"PipeGeometry.D_i must be > 0, got {self.D_i}")
        if self.L <= 0:
            raise ValueError(f"PipeGeometry.L must be > 0, got {self.L}")
        if self.roughness < 0:
            raise ValueError(f"PipeGeometry.roughness must be ≥ 0, got {self.roughness}")
        if self.n_passes < 1:
            raise ValueError(f"PipeGeometry.n_passes must be ≥ 1, got {self.n_passes}")

    @property
    def A_c(self) -> float:
        """Cross-sectional area per pass [m²]."""
        return math.pi * self.D_i**2 / 4.0

    @property
    def P_wet(self) -> float:
        """Wetted perimeter [m]."""
        return math.pi * self.D_i

    @property
    def D_h(self) -> float:
        """Hydraulic diameter [m] — equals D_i for circular cross-section."""
        return self.D_i

    @property
    def V(self) -> float:
        """Total pipe volume [m³] (all passes combined)."""
        return self.A_c * self.L * self.n_passes


# Sentinel: distinguishes "user passed None explicitly" from "use default"
_PIPE_DEFAULT_SP = object()
_PIPE_DEFAULT_TP = object()


# ---------------------------------------------------------------------------
# Internal wrappers — bypass correlations._validate_state for single-phase
# ---------------------------------------------------------------------------
# correlations._validate_state requires k_v and Pr_v even for single-phase
# liquid states where FluidState does not populate vapour properties.
# These thin wrappers extract only the attributes actually needed by each
# friction factor formula.

class _LiquidBlassiusDP:
    """
    Fanning friction factor for single-phase flow, using only mu_l.
    Equivalent to BlassiusDP but works with single-phase FluidState.

    f = 16/Re          Re < 2000  (Hagen-Poiseuille)
    f = 0.079 Re^-0.25 2000≤Re<20000  (Blasius)
    f = 0.046 Re^-0.20 Re≥20000
    dP/dz = 2 f G² / (D ρ)
    """
    def __call__(self, state: object, G: float, D_h: float, **kwargs) -> float:
        mu  = getattr(state, "mu_l", getattr(state, "mu_tp", 1e-3))
        rho = getattr(state, "rho", 1000.0)
        Re  = G * D_h / mu
        if Re < 2000:
            f = 16.0 / Re
        elif Re < 20_000:
            f = 0.079 * Re**(-0.25)
        else:
            f = 0.046 * Re**(-0.20)
        return 2.0 * f * G**2 / (D_h * rho)



@dataclass
class Pipe(Component):
    """
    1D adiabatic (or heat-loss) pipe — single-phase and two-phase capable.

    Parameters
    ----------
    geometry : PipeGeometry
        Physical dimensions and orientation.
    Q_loss : float
        Heat removed from the fluid to the environment [W].
        Q_loss > 0  →  fluid cools (energy leaves).
        Q_loss = 0  →  adiabatic.   Default: 0.
    dp_correlation_sp : DPCorrelation | None
        Pressure-drop correlation for single-phase flow.
        Default: BlassiusDP (Fanning friction, Hagen-Poiseuille + Blasius).
    dp_correlation_tp : DPCorrelation | None
        Pressure-drop correlation for two-phase flow.
        Default: HomogeneousDP (Cicchitti μ_tp, Dogan 1983).
    fluid : str
        CoolProp fluid name used to reconstruct outlet FluidState.
        Only required when _FLUID_PROPS_AVAILABLE = True.
    name : str
        Human-readable identifier.

    Pressure drop breakdown (stored after solve_ss)
    ------------------------------------------------
    dP_friction  [Pa]  — wall friction
    dP_gravity   [Pa]  — hydrostatic head (0 for horizontal)
    dP_accel     [Pa]  — momentum / acceleration (two-phase with heat)
    dP_total     [Pa]  — sum of all three  = self._last_dP

    Notes
    -----
    * The pipe uses *inlet* conditions to select the correlation.
      If flow is two-phase at the inlet, HomogeneousDP (or the configured
      two-phase correlation) is used for the entire length.
    * The acceleration term is only non-zero for two-phase flow with Q_loss ≠ 0.
    * For very short pipes where ΔP > P_in (non-physical), a warning is issued
      and ΔP is clamped to 90 % of P_in.
    """

    geometry:           PipeGeometry
    Q_loss:             float = 0.0     # [W] heat removed to environment
    dp_correlation_sp:  object = field(default_factory=lambda: _PIPE_DEFAULT_SP)
    dp_correlation_tp:  object = field(default_factory=lambda: _PIPE_DEFAULT_TP)
    fluid:              str   = ""
    name:               str   = ""

    # Post-solve diagnostics (populated by solve_ss)
    dP_friction: float = field(default=0.0, init=False, repr=False)
    dP_gravity:  float = field(default=0.0, init=False, repr=False)
    dP_accel:    float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        # Call Component.__init__ to set self.name, self.inlet, self.outlet
        Component.__init__(self, name=self.name or "Pipe")

        # Lazy defaults for correlations — only set if not explicitly provided
        # If user passes None, keep None so test_missing_dp_correlation_raises works
        if self.dp_correlation_sp is _PIPE_DEFAULT_SP:
            self.dp_correlation_sp = _LiquidBlassiusDP()
        if self.dp_correlation_tp is _PIPE_DEFAULT_TP:
            self.dp_correlation_tp = HomogeneousDP() if _CORR_AVAILABLE else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _mass_flux(self, mdot: float) -> float:
        """
        Mass flux per tube [kg/m²·s].
        G = mdot / (n_passes · A_c)
        """
        return mdot / (self.geometry.n_passes * self.geometry.A_c)

    def _is_two_phase(self, state: object) -> bool:
        """Return True if the state is in the two-phase region."""
        phase = getattr(state, "phase", "liquid")
        return phase == "two-phase"

    def _friction_dp(self, state: object, G: float) -> float:
        """
        Frictional pressure drop [Pa] for the full pipe length.

        Uses the single-phase or two-phase correlation depending on phase.
        Returns a positive value (pressure decreases in flow direction).
        """
        if self.dp_correlation_sp is None or self.dp_correlation_tp is None:
            raise ComponentError(
                self,
                "ΔP correlations not set. Install correlations.py or pass "
                "dp_correlation_sp / dp_correlation_tp explicitly."
            )

        D_h = self.geometry.D_h
        L   = self.geometry.L

        if self._is_two_phase(state):
            dPdz = self.dp_correlation_tp(state, G, D_h, roughness=self.geometry.roughness)
        else:
            dPdz = self.dp_correlation_sp(state, G, D_h, roughness=self.geometry.roughness)

        return dPdz * L  # [Pa]

    def _gravity_dp(self, state: object) -> float:
        """
        Gravitational pressure change [Pa].

        ΔP_grav = ρ · g · L · sin(θ)
        positive → pressure drop (flow against gravity, vertical_up)
        negative → pressure gain (flow aided by gravity, vertical_down)
        """
        rho = getattr(state, "rho", 1000.0)
        L   = self.geometry.L
        ori = self.geometry.orientation

        if ori == Orientation.HORIZONTAL:
            return 0.0
        elif ori == Orientation.VERTICAL_UP:
            return rho * G_EARTH * L
        else:  # VERTICAL_DOWN
            return -rho * G_EARTH * L

    def _acceleration_dp(self, state: object, G: float, h_out: float) -> float:
        """
        Accelerational (momentum) pressure drop [Pa] for two-phase flow.

        ΔP_accel = G² · [v_tp_out − v_tp_in]
                 = G² · [(x_out/ρ_v + (1-x_out)/ρ_l)
                          − (x_in /ρ_v + (1-x_in )/ρ_l)]

        Only non-zero when phase is two-phase and quality changes (Q_loss ≠ 0).
        Requires the outlet enthalpy h_out to determine x_out.

        Parameters
        ----------
        state  : FluidState at inlet
        G      : mass flux [kg/m²·s]
        h_out  : specific enthalpy at outlet [J/kg]
        """
        if not self._is_two_phase(state):
            return 0.0

        # Homogeneous specific volume: v_tp = x/ρ_v + (1-x)/ρ_l
        h_in_state = getattr(state, "h", h_out)
        if abs(h_out - h_in_state) < 1e-9:
            return 0.0  # adiabatic: no quality change → no acceleration ΔP

        x_in  = getattr(state, "x",     0.0)
        rho_l = getattr(state, "rho_l", 1000.0)
        rho_v = getattr(state, "rho_v", 1.0)
        h_fg  = getattr(state, "h_fg",  1e6)
        h_l   = getattr(state, "h_l",   getattr(state, "h", 0.0))

        if h_fg <= 0:
            return 0.0

        # Quality at outlet (clamped to [0, 1])
        x_out = (h_out - h_l) / h_fg
        x_out = max(0.0, min(1.0, x_out))

        v_in  = x_in  / rho_v + (1.0 - x_in)  / rho_l
        v_out = x_out / rho_v + (1.0 - x_out) / rho_l

        return G**2 * (v_out - v_in)  # [Pa]  positive if quality increases

    def _rebuild_outlet_state(self, P_out: float, h_out: float) -> object:
        """
        Construct the outlet FluidState from (P_out, h_out).

        If CoolProp FluidState is available, uses FluidState.from_Ph.
        Otherwise returns a minimal duck-typed stub (for unit tests).
        """
        if _FLUID_PROPS_AVAILABLE and self.fluid:
            try:
                return FluidState.from_Ph(self.fluid, P_out, h_out)
            except Exception as exc:
                raise ComponentError(
                    self,
                    f"FluidState.from_Ph({self.fluid!r}, P={P_out:.0f} Pa, "
                    f"h={h_out:.0f} J/kg) failed: {exc}"
                ) from exc
        else:
            # Duck-typed stub — preserves P and h for use in loop.py
            # without CoolProp. Phase and x will be approximate.
            # NOTE: This path is only used in isolated unit tests.
            return _SimplePHState(P=P_out, h=h_out)

    # ------------------------------------------------------------------
    # Component interface — mandatory overrides
    # ------------------------------------------------------------------

    def solve_ss(self, inlet: Port) -> Port:
        """
        Steady-state solution for the pipe.

        Algorithm
        ---------
        1. Extract inlet conditions: P_in, h_in, mdot, state.
        2. Compute mass flux G = mdot / A_c.
        3. Compute h_out = h_in − Q_loss / mdot  (energy balance).
        4. Compute ΔP_friction (using inlet state correlation).
        5. Compute ΔP_gravity (from orientation).
        6. Compute ΔP_accel (two-phase with quality change).
        7. P_out = P_in − ΔP_total.
        8. Reconstruct outlet FluidState from (P_out, h_out).
        9. Return outlet Port.

        Parameters
        ----------
        inlet : Port
            Upstream connection.

        Returns
        -------
        Port
            Outlet Port with updated (P_out, h_out, mdot).

        Raises
        ------
        ComponentError
            If mdot ≤ 0, correlations are missing, or CoolProp call fails.
        """
        # --- store inlet -----------------------------------------------------
        self.inlet = inlet
        state_in   = inlet.state
        mdot       = inlet.mdot

        if mdot <= 0.0:
            raise ComponentError(
                self,
                f"mass flow rate must be > 0; got mdot={mdot:.4g} kg/s."
            )

        # --- geometry --------------------------------------------------------
        G   = self._mass_flux(mdot)    # [kg/m²·s]
        D_h = self.geometry.D_h        # [m]
        L   = self.geometry.L          # [m]

        # --- energy balance --------------------------------------------------
        h_in  = inlet.h
        h_out = h_in - self.Q_loss / mdot   # [J/kg]

        # --- friction ΔP -----------------------------------------------------
        try:
            dP_f = self._friction_dp(state_in, G)
        except ComponentError:
            raise
        except Exception as exc:
            raise ComponentError(
                self, f"friction ΔP calculation failed: {exc}"
            ) from exc

        # --- gravity ΔP ------------------------------------------------------
        dP_g = self._gravity_dp(state_in)

        # --- acceleration ΔP (two-phase) -------------------------------------
        dP_a = self._acceleration_dp(state_in, G, h_out)

        # --- total ΔP --------------------------------------------------------
        dP_total = dP_f + dP_g + dP_a

        P_in  = inlet.P
        P_out = P_in - dP_total

        # Guard against non-physical pressure (very short pipe or bad inputs)
        if P_out <= 0.0:
            warnings.warn(
                f"{self.name}: computed P_out={P_out:.1f} Pa ≤ 0. "
                f"Clamping to 10% of P_in={P_in:.1f} Pa. "
                "Check geometry and mass flux.",
                RuntimeWarning,
                stacklevel=2,
            )
            P_out = 0.1 * P_in

        # --- store diagnostics -----------------------------------------------
        self.dP_friction = dP_f
        self.dP_gravity  = dP_g
        self.dP_accel    = dP_a
        self._last_dP    = dP_total
        self._last_Q     = -self.Q_loss   # heat added = negative of heat lost

        # --- build outlet state ----------------------------------------------
        state_out = self._rebuild_outlet_state(P_out, h_out)

        # --- build and store outlet Port -------------------------------------
        self.outlet = Port(state=state_out, mdot=mdot)
        return self.outlet

    def pressure_drop(self) -> float:
        """Total pressure drop [Pa] = friction + gravity + acceleration."""
        return self._last_dP

    def heat_transfer(self) -> float:
        """
        Net heat added to the fluid [W].
        For a pipe with Q_loss: Q = −Q_loss  (negative = heat leaves fluid).
        """
        return self._last_Q

    # ------------------------------------------------------------------
    # Convenience summary
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return a formatted summary of the pipe and last solve results."""
        g = self.geometry
        lines = [
            f"=== {self.name} ===",
            f"  Geometry : D_i={g.D_i*1e3:.2f} mm, L={g.L:.3f} m, "
            f"orientation={g.orientation}, passes={g.n_passes}",
            f"  roughness: {g.roughness*1e6:.1f} µm",
            f"  Q_loss   : {self.Q_loss:.2f} W",
        ]
        if self.inlet is not None:
            lines.append(f"  Inlet    : {self.inlet}")
        if self.outlet is not None:
            lines.append(f"  Outlet   : {self.outlet}")
            lines += [
                f"  ΔP_fric  : {self.dP_friction:.1f} Pa",
                f"  ΔP_grav  : {self.dP_gravity:.1f} Pa",
                f"  ΔP_accel : {self.dP_accel:.1f} Pa",
                f"  ΔP_total : {self._last_dP:.1f} Pa",
            ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# _SimplePHState — minimal duck-type stub for isolated testing
# ---------------------------------------------------------------------------

@dataclass
class _SimplePHState:
    """
    Minimal (P, h) state used when CoolProp / FluidState is unavailable.
    Sufficient for loop bookkeeping; does not compute thermal properties.
    """
    P:     float
    h:     float
    T:     float   = float("nan")
    rho:   float   = float("nan")
    x:     float   = float("nan")
    phase: str     = "unknown"
    rho_l: float   = float("nan")
    rho_v: float   = float("nan")
    h_fg:  float   = float("nan")
    h_l:   float   = float("nan")
    mu_l:  float   = float("nan")
    mu_v:  float   = float("nan")
    mu_tp: float   = float("nan")
    k_l:   float   = float("nan")
    k_v:   float   = float("nan")
    Pr_l:  float   = float("nan")
    Pr_v:  float   = float("nan")
    sigma: float   = float("nan")
    P_red: float   = float("nan")
    T_sat: float   = float("nan")


# ---------------------------------------------------------------------------
# Module self-test (run as script: python pipe.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Smoke test using CoolProp FluidState if available,
    or duck-typed stubs otherwise.
    """
    print("=" * 60)
    print("pipe.py — smoke test")
    print("=" * 60)

    if _FLUID_PROPS_AVAILABLE and _CORR_AVAILABLE:
        print("[INFO] Using full FluidState + correlations")

        # --- Single-phase liquid pipe ---
        geom = PipeGeometry(D_i=0.01, L=1.0, orientation=Orientation.HORIZONTAL)
        pipe = Pipe(geometry=geom, Q_loss=0.0, fluid="Acetone", name="TestPipe_SP")

        state_in = FluidState.from_Ph("Acetone", 3e5, 2.5e5)
        port_in  = Port(state=state_in, mdot=0.02)
        port_out = pipe.solve_ss(port_in)

        print(f"\nSingle-phase liquid pipe (Acetone, horizontal, L=1 m, D=10 mm):")
        print(pipe.summary())
        assert port_out.P < port_in.P, "Pressure must drop across pipe"
        assert abs(port_out.h - port_in.h) < 1e-6, "Adiabatic pipe: h must be conserved"

        # --- Two-phase pipe ---
        geom2 = PipeGeometry(D_i=0.008, L=0.5, orientation=Orientation.VERTICAL_UP)
        pipe2 = Pipe(geometry=geom2, Q_loss=10.0, fluid="R134a", name="TestPipe_TP")

        state_tp = FluidState.from_Px("R134a", 4e5, 0.3)
        port_tp  = Port(state=state_tp, mdot=0.01)
        port_tp_out = pipe2.solve_ss(port_tp)

        print(f"\nTwo-phase pipe (R134a, vertical_up, L=0.5 m, D=8 mm, Q_loss=10 W):")
        print(pipe2.summary())
        assert port_tp_out.P < port_tp.P, "Pressure must drop (friction + gravity)"

    else:
        print("[WARN] CoolProp / correlations not available — using stub states")

        # Minimal stub test
        @dataclass
        class _Stub:
            phase: str  = "liquid"
            P:     float = 5e5
            h:     float = 2.5e5
            T:     float = 310.0
            rho:   float = 900.0
            x:     float = 0.0
            rho_l: float = 900.0
            rho_v: float = 5.0
            mu_l:  float = 2e-4
            mu_v:  float = 1e-5
            mu_tp: float = 1.5e-4
            k_l:   float = 0.08
            k_v:   float = 0.015
            Pr_l:  float = 3.5
            Pr_v:  float = 1.1
            h_fg:  float = 300_000.0
            sigma: float = 0.01
            P_red: float = 0.05
            T_sat: float = 310.0
            h_l:   float = 1.0e5

        # Build minimal DPCorrelation stubs
        class _ConstDP:
            def __call__(self, state, G, D_h, **kwargs):
                return 100.0   # 100 Pa/m flat

        geom = PipeGeometry(D_i=0.01, L=1.0)
        pipe = Pipe(
            geometry=geom,
            Q_loss=0.0,
            dp_correlation_sp=_ConstDP(),
            dp_correlation_tp=_ConstDP(),
            name="StubPipe",
        )

        s = _Stub()
        port_in  = Port(state=s, mdot=0.05)
        port_out = pipe.solve_ss(port_in)

        print(f"Stub pipe: P_in={port_in.P:.0f} → P_out={port_out.P:.0f} Pa")
        assert port_out.P < port_in.P

    print("\nSmoke test passed ✓")
