"""
components/evaporator.py — Microchannel Evaporator Component
=============================================================
MPL Simulation Library — Module 3c (Phase 3)

Models a microchannel evaporator heated by electronics at a specified
heat flux (or total power). Implements a zone-based, nodal steady-state
model:

  Zone 1 — Subcooled liquid  (if h_in < h_liq_sat)
  Zone 2 — Two-phase boiling (core of the evaporator)
  Zone 3 — Superheated vapour (if x_out would exceed 1.0)

The model resolves the axial enthalpy profile along N_nodes control
volumes and computes:
  • Outlet FluidState (P_out, h_out)
  • Total pressure drop ΔP  [Pa]  (friction + acceleration)
  • Average wall temperature T_wall [K]
  • Axial HTC profile α(z)  [W/m²·K]
  • Exit vapour quality x_out  [-]
  • Boiling curve point (q_flux vs. ΔT_wall)

Physical model
--------------
Each control volume i of length dz = L_ch / N_nodes obeys:

  Energy:    mdot · (h_{i+1} − h_i) = q_flux · N_ch · P_wet · dz
  Pressure:  P_{i+1} = P_i − (dP_fric_i + dP_acc_i)
  Wall temp: T_wall_i = T_fluid_i + q_flux / α_i

where:
  P_wet = 2·(W_ch + H_ch)          wetted perimeter per channel [m]
  A_c   = W_ch · H_ch              cross-sectional area per channel [m²]
  D_h   = 4·A_c / P_wet            hydraulic diameter [m]
  G     = mdot / (N_ch · A_c)      mass flux [kg/m²·s]

HTC correlations (Strategy Pattern)
------------------------------------
  Subcooled    → DittusBoelterHTC  (n=0.4, heating)
  Two-phase    → ShahBoilingHTC    (default) or KimMudawar2012HTC
  Superheated  → DittusBoelterHTC  (n=0.4, vapour)

Pressure drop correlations (Strategy Pattern)
---------------------------------------------
  Single-phase → BlassiusDP
  Two-phase    → MullerSteinhagenHeckDP  (default, used by Kokate 2023)
                 or HomogeneousDP / KimMudawar2013DP

Acceleration pressure drop (two-phase only):
  dP_acc = G² · d(1/ρ_tp)/dz · dz      [HEM, Dogan 1983]

Design limits / warnings
------------------------
  • x_out > x_out_max  → DryoutWarning
  • x_out_max default 0.80  (annular-to-mist transition, Kokate 2023 Fig. 8)
  • Negative ΔP per node (non-physical) → PhysicsWarning

Usage example
-------------
    from fluid_properties import FluidState
    from correlations import ShahBoilingHTC, MullerSteinhagenHeckDP
    from evaporator import Evaporator, EvaporatorGeometry

    geom = EvaporatorGeometry(
        N_ch   = 33,
        L_ch   = 0.0508,   # 2 inches
        W_ch   = 0.5e-3,
        H_ch   = 0.5e-3,
    )
    evap = Evaporator(
        geom         = geom,
        Q_evap       = 200.0,    # [W]
        htc_corr     = ShahBoilingHTC(),
        dp_corr      = MullerSteinhagenHeckDP(),
        N_nodes      = 50,
        x_out_max    = 0.80,
        name         = "Evap_Main",
    )
    inlet = Port(state=state_in, mdot=0.01)
    outlet = evap.solve_ss(inlet)
    print(evap.summary())

References
----------
[1]  M. Shah, "Chart correlation for saturated boiling heat transfer,"
     ASHRAE Trans. 88 (1982).  [Shah boiling — primary HTC]
[2]  R. Kokate, C. Park, "Pumped two-phase loop …,"
     Appl. Therm. Eng. 229 (2023) 120630.  [Nodal model, MSH ΔP, Shah HTC]
[3]  R. Kokate, PhD Thesis, 2024.  [Appendix A — Shah eqs.; Appendix B — ΔP]
[4]  T.N. Dogan (1983).  [HEM acceleration ΔP: G²·d(1/ρ)]
[5]  M. VanGerner et al. (2016).  [(P,h) as state variables]
[6]  H. Müller-Steinhagen & K. Heck (1986).  [MSH two-phase ΔP]
[7]  S.-M. Kim & I. Mudawar (2012).  [Universal HTC mini/micro-channel]
[8]  Middelhuis et al. (2024).  [Evaporator energy balance, thermal mass]
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, field
from typing import Optional, List

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
        ShahBoilingHTC,
        DittusBoelterHTC,
        BlassiusDP,
        MullerSteinhagenHeckDP,
        HomogeneousDP,
        acceleration_pressure_gradient,
    )
    _CORR_AVAILABLE = True
except ImportError:
    _CORR_AVAILABLE = False

try:
    from base import Component, Port
    _BASE_AVAILABLE = True
except ImportError:
    _BASE_AVAILABLE = False
    # Minimal stubs for isolated testing
    from abc import ABC, abstractmethod

    class Component(ABC):  # type: ignore[no-redef]
        def __init__(self, name: str = ""):
            self.name = name or self.__class__.__name__
            self.inlet: Optional[object] = None
            self.outlet: Optional[object] = None
            self._last_dP: float = 0.0
            self._last_Q: float = 0.0

        @abstractmethod
        def solve_ss(self, inlet): ...

        @abstractmethod
        def pressure_drop(self) -> float: ...

        @abstractmethod
        def heat_transfer(self) -> float: ...

    @dataclass
    class Port:  # type: ignore[no-redef]
        state: object
        mdot: float = 0.0


# ---------------------------------------------------------------------------
# Custom warnings
# ---------------------------------------------------------------------------

class DryoutWarning(UserWarning):
    """Fired when predicted exit quality exceeds x_out_max."""


class PhysicsWarning(UserWarning):
    """Fired when a non-physical intermediate result is detected."""


# ---------------------------------------------------------------------------
# EvaporatorGeometry — immutable geometry descriptor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvaporatorGeometry:
    """
    Geometric parameters for a rectangular microchannel evaporator.

    Parameters
    ----------
    N_ch : int
        Number of parallel microchannels.
    L_ch : float
        Channel length [m].
    W_ch : float
        Channel width [m].
    H_ch : float
        Channel height (depth) [m].
    t_wall : float
        Wall / fin thickness [m]. Used for fin efficiency if needed (default 0.2 mm).
    material : str
        Wall material label — informational only (default "aluminium").

    Derived properties
    ------------------
    A_c    : float  — cross-sectional area per channel  [m²]
    P_wet  : float  — wetted perimeter per channel      [m]
    D_h    : float  — hydraulic diameter                [m]
    A_heat : float  — total heated area (all channels)  [m²]
    """

    N_ch:     int
    L_ch:     float
    W_ch:     float
    H_ch:     float
    t_wall:   float = 200e-6   # 0.2 mm default fin thickness
    material: str   = "aluminium"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def __post_init__(self):
        if self.N_ch < 1:
            raise ValueError(f"N_ch must be >= 1, got {self.N_ch}")
        for attr in ("L_ch", "W_ch", "H_ch", "t_wall"):
            v = getattr(self, attr)
            if v <= 0:
                raise ValueError(f"{attr} must be > 0, got {v}")

    # ------------------------------------------------------------------
    # Derived geometry (computed on demand, frozen dataclass so cached OK)
    # ------------------------------------------------------------------
    @property
    def A_c(self) -> float:
        """Cross-sectional area per channel [m²]."""
        return self.W_ch * self.H_ch

    @property
    def P_wet(self) -> float:
        """Wetted perimeter per channel [m]."""
        return 2.0 * (self.W_ch + self.H_ch)

    @property
    def D_h(self) -> float:
        """Hydraulic diameter [m]."""
        return 4.0 * self.A_c / self.P_wet

    @property
    def A_heat(self) -> float:
        """Total heated surface area (all channels, both walls, bottom) [m²]."""
        # Heated perimeter = W_ch + 2·H_ch (bottom + two sides, no fin top)
        P_heat = self.W_ch + 2.0 * self.H_ch
        return self.N_ch * P_heat * self.L_ch

    @property
    def A_c_total(self) -> float:
        """Total cross-sectional flow area (all channels) [m²]."""
        return self.N_ch * self.A_c

    def __repr__(self) -> str:
        return (
            f"EvaporatorGeometry(N_ch={self.N_ch}, "
            f"L_ch={self.L_ch*1e3:.1f} mm, "
            f"W_ch={self.W_ch*1e6:.0f} µm, "
            f"H_ch={self.H_ch*1e6:.0f} µm, "
            f"D_h={self.D_h*1e6:.0f} µm)"
        )


# ---------------------------------------------------------------------------
# EvaporatorResult — output data container
# ---------------------------------------------------------------------------

@dataclass
class EvaporatorResult:
    """
    Detailed results from a single solve_ss() call.

    Attributes
    ----------
    z           : ndarray [m]      — axial positions (N_nodes+1 points)
    P_profile   : ndarray [Pa]     — pressure along channel
    h_profile   : ndarray [J/kg]   — enthalpy along channel
    T_fluid     : ndarray [K]      — fluid temperature along channel
    T_wall      : ndarray [K]      — wall temperature along channel
    alpha       : ndarray [W/m²K]  — local HTC along channel
    x_profile   : ndarray [-]      — local vapour quality (-1 = subcooled)
    dP_fric     : float [Pa]       — total friction pressure drop
    dP_acc      : float [Pa]       — total acceleration pressure drop
    dP_total    : float [Pa]       — total pressure drop
    Q_actual    : float [W]        — heat actually transferred to fluid
    x_out       : float [-]        — outlet vapour quality
    T_wall_avg  : float [K]        — area-averaged wall temperature
    alpha_avg   : float [W/m²K]   — area-averaged HTC
    dryout_flag : bool             — True if x_out > x_out_max
    """

    z:           np.ndarray
    P_profile:   np.ndarray
    h_profile:   np.ndarray
    T_fluid:     np.ndarray
    T_wall:      np.ndarray
    alpha:       np.ndarray
    x_profile:   np.ndarray
    dP_fric:     float
    dP_acc:      float
    dP_total:    float
    Q_actual:    float
    x_out:       float
    T_wall_avg:  float
    alpha_avg:   float
    dryout_flag: bool = False


# ---------------------------------------------------------------------------
# Evaporator — main component class
# ---------------------------------------------------------------------------

class Evaporator(Component):
    """
    Steady-state microchannel evaporator with zone-based nodal model.

    Parameters
    ----------
    geom : EvaporatorGeometry
        Channel geometry descriptor.
    Q_evap : float
        Total heat input from electronics [W].
    htc_corr : callable, optional
        Two-phase HTC correlation (Strategy). Default: ShahBoilingHTC().
    dp_corr : callable, optional
        Two-phase ΔP correlation (Strategy). Default: MullerSteinhagenHeckDP().
    N_nodes : int
        Number of axial control volumes (default 50).
    x_out_max : float
        Maximum allowed exit vapour quality before DryoutWarning (default 0.80).
    name : str
        Component identifier string.

    Notes
    -----
    The nodal loop marches from inlet to outlet:
      1. Compute local q_flux from Q_evap uniformly distributed.
      2. Update enthalpy: h_{i+1} = h_i + q_flux·P_heat·dz / mdot_ch
      3. Update state via FluidState.from_Ph(P_i, h_{i+1})
      4. Compute local α from appropriate HTC correlation.
      5. Compute T_wall = T_fluid + q_flux / α.
      6. Compute dP_fric and dP_acc; update P_{i+1}.

    The model uses (P, h) as primary state variables following VanGerner (2016),
    which avoids discontinuities at phase boundaries.
    """

    def __init__(
        self,
        geom:      EvaporatorGeometry,
        Q_evap:    float,
        htc_corr=  None,
        dp_corr=   None,
        N_nodes:   int   = 50,
        x_out_max: float = 0.80,
        name:      str   = "Evaporator",
    ):
        super().__init__(name=name)

        if not isinstance(geom, EvaporatorGeometry):
            raise TypeError("geom must be an EvaporatorGeometry instance.")
        if Q_evap < 0:
            raise ValueError(f"Q_evap must be >= 0 [W], got {Q_evap}")
        if N_nodes < 2:
            raise ValueError(f"N_nodes must be >= 2, got {N_nodes}")
        if not (0 < x_out_max <= 1.0):
            raise ValueError(f"x_out_max must be in (0, 1], got {x_out_max}")

        self.geom      = geom
        self.Q_evap    = Q_evap
        self.N_nodes   = N_nodes
        self.x_out_max = x_out_max

        # ---- Correlation defaults ----------------------------------------
        if _CORR_AVAILABLE:
            self.htc_corr = htc_corr if htc_corr is not None else ShahBoilingHTC()
            self.dp_corr  = dp_corr  if dp_corr  is not None else MullerSteinhagenHeckDP()
            self._htc_sp  = DittusBoelterHTC(heating=True)    # single-phase (heating)
            self._dp_sp   = BlassiusDP()                    # single-phase
        else:
            self.htc_corr = htc_corr
            self.dp_corr  = dp_corr
            self._htc_sp  = None
            self._dp_sp   = None

        # ---- Cached result -----------------------------------------------
        self._result: Optional[EvaporatorResult] = None

    # ------------------------------------------------------------------
    # Derived geometry shortcuts
    # ------------------------------------------------------------------

    @property
    def q_flux(self) -> float:
        """Heat flux on heated surface [W/m²]."""
        return self.Q_evap / self.geom.A_heat

    @property
    def q_flux_ch(self) -> float:
        """Heat flux per unit channel length per channel [W/m]."""
        dz = self.geom.L_ch / self.N_nodes
        P_heat_ch = self.geom.W_ch + 2.0 * self.geom.H_ch   # per channel
        return self.q_flux * P_heat_ch                        # [W/m]

    # ------------------------------------------------------------------
    # Abstract interface implementation
    # ------------------------------------------------------------------

    def solve_ss(self, inlet: Port) -> Port:  # type: ignore[override]
        """
        Steady-state solution: compute outlet Port from inlet Port.

        Parameters
        ----------
        inlet : Port
            Inlet thermodynamic state + mass flow rate.

        Returns
        -------
        outlet : Port
            Outlet state at (P_out, h_out).

        Raises
        ------
        TypeError
            If inlet.state is not a FluidState-compatible object.
        ValueError
            If mdot <= 0 or fluid state is missing required attributes.

        Side effects
        ------------
        Sets self.inlet, self.outlet, self._last_dP, self._last_Q,
        and self._result (full axial profile).
        """
        self.inlet = inlet
        state_in   = inlet.state
        mdot       = inlet.mdot

        if mdot <= 0:
            raise ValueError(f"[{self.name}] mdot must be > 0, got {mdot} kg/s")

        # Mass flux per channel
        G    = mdot / self.geom.A_c_total       # [kg/m²·s]
        D_h  = self.geom.D_h                    # [m]
        dz   = self.geom.L_ch / self.N_nodes    # [m]

        # Heat added per node per channel [W]
        P_heat_ch = self.geom.W_ch + 2.0 * self.geom.H_ch
        dQ_node   = self.q_flux * P_heat_ch * dz  # [W] per node per channel
        # Enthalpy rise per node per channel
        dh_node   = dQ_node / (mdot / self.geom.N_ch)   # [J/kg]

        # --- Initialise axial arrays (N_nodes + 1 node points) -----------
        N  = self.N_nodes
        z_arr      = np.linspace(0.0, self.geom.L_ch, N + 1)
        P_arr      = np.empty(N + 1)
        h_arr      = np.empty(N + 1)
        T_fl_arr   = np.empty(N + 1)
        T_wall_arr = np.empty(N + 1)
        alpha_arr  = np.empty(N + 1)
        x_arr      = np.empty(N + 1)

        # --- Inlet node (i = 0) ------------------------------------------
        P_arr[0] = state_in.P
        h_arr[0] = state_in.h
        T_fl_arr[0]   = state_in.T
        x_arr[0]      = state_in.x

        # Initial HTC & wall temperature at inlet
        alpha_arr[0]  = self._local_htc(state_in, G, D_h, self.q_flux)
        T_wall_arr[0] = state_in.T + self.q_flux / max(alpha_arr[0], 1.0)

        dP_fric_total = 0.0
        dP_acc_total  = 0.0

        # --- Nodal march: i → i+1 ----------------------------------------
        state_i = state_in
        for i in range(N):
            # 1. Update enthalpy (uniform heat flux → linear h profile)
            h_next = h_arr[i] + dh_node

            # 2. Compute ΔP friction
            dP_fric_i = self._local_dp_fric(state_i, G, D_h) * dz  # [Pa]

            # 3. Acceleration ΔP (two-phase only, HEM)
            dP_acc_i = self._local_dp_acc(state_i, G, D_h, dh_node)  # [Pa]

            # 4. Update pressure
            P_next = P_arr[i] - dP_fric_i - dP_acc_i

            if P_next <= 0:
                warnings.warn(
                    f"[{self.name}] Non-physical P_next={P_next:.1f} Pa at node {i+1}. "
                    "Check operating conditions.",
                    PhysicsWarning,
                    stacklevel=2,
                )
                P_next = max(P_next, 100.0)   # floor to avoid CoolProp crash

            # 5. Compute next state via (P, h)
            state_next = FluidState.from_Ph(state_in.fluid, P_next, h_next)

            # 6. Local HTC and wall temperature at outlet face of node
            alpha_i1 = self._local_htc(state_next, G, D_h, self.q_flux)
            T_wall_i1 = state_next.T + self.q_flux / max(alpha_i1, 1.0)

            # 7. Store
            P_arr[i + 1]      = P_next
            h_arr[i + 1]      = h_next
            T_fl_arr[i + 1]   = state_next.T
            T_wall_arr[i + 1] = T_wall_i1
            alpha_arr[i + 1]  = alpha_i1
            x_arr[i + 1]      = state_next.x

            dP_fric_total += dP_fric_i
            dP_acc_total  += dP_acc_i

            state_i = state_next

        # --- Outlet state ---------------------------------------------------
        state_out = state_i
        x_out     = float(state_out.x)
        dP_total  = dP_fric_total + dP_acc_total

        # Dryout check
        dryout_flag = x_out > self.x_out_max
        if dryout_flag:
            warnings.warn(
                f"[{self.name}] Exit quality x_out={x_out:.3f} exceeds "
                f"x_out_max={self.x_out_max:.2f}. Possible dryout.",
                DryoutWarning,
                stacklevel=2,
            )

        # --- Build result ---------------------------------------------------
        self._result = EvaporatorResult(
            z           = z_arr,
            P_profile   = P_arr,
            h_profile   = h_arr,
            T_fluid     = T_fl_arr,
            T_wall      = T_wall_arr,
            alpha       = alpha_arr,
            x_profile   = x_arr,
            dP_fric     = dP_fric_total,
            dP_acc      = dP_acc_total,
            dP_total    = dP_total,
            Q_actual    = self.Q_evap,
            x_out       = x_out,
            T_wall_avg  = float(np.mean(T_wall_arr)),
            alpha_avg   = float(np.mean(alpha_arr)),
            dryout_flag = dryout_flag,
        )

        # --- Cache scalars for Component interface -------------------------
        self._last_dP = dP_total
        self._last_Q  = self.Q_evap

        # --- Build outlet Port --------------------------------------------
        outlet = Port(state=state_out, mdot=mdot)
        self.outlet = outlet
        return outlet

    def pressure_drop(self) -> float:
        """
        Total evaporator pressure drop [Pa] from the last solve_ss() call.

        Returns
        -------
        float
            ΔP [Pa] (positive = pressure decreases in flow direction).

        Raises
        ------
        RuntimeError
            If solve_ss() has not been called yet.
        """
        if self._result is None:
            raise RuntimeError(
                f"[{self.name}] Call solve_ss() before querying pressure_drop()."
            )
        return self._result.dP_total

    def heat_transfer(self) -> float:
        """
        Total heat transferred to the fluid [W] from the last solve_ss() call.

        Returns
        -------
        float
            Q_evap [W].

        Raises
        ------
        RuntimeError
            If solve_ss() has not been called yet.
        """
        if self._result is None:
            raise RuntimeError(
                f"[{self.name}] Call solve_ss() before querying heat_transfer()."
            )
        return self._result.Q_actual

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def result(self) -> EvaporatorResult:
        """Full axial profile from the last solve_ss() call."""
        if self._result is None:
            raise RuntimeError(
                f"[{self.name}] Call solve_ss() first to obtain results."
            )
        return self._result

    @property
    def T_wall_avg(self) -> float:
        """Area-averaged wall temperature [K] from last solve."""
        return self.result.T_wall_avg

    @property
    def x_out(self) -> float:
        """Exit vapour quality [-] from last solve."""
        return self.result.x_out

    @property
    def alpha_avg(self) -> float:
        """Area-averaged HTC [W/m²·K] from last solve."""
        return self.result.alpha_avg

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return a formatted summary string of the last solve result."""
        if self._result is None:
            return f"Evaporator '{self.name}' — not yet solved."
        r = self._result
        g = self.geom
        lines = [
            f"{'='*60}",
            f" Evaporator: {self.name}",
            f"{'='*60}",
            f"  Geometry   : {g.N_ch} ch × {g.L_ch*1e3:.1f} mm  "
            f"({g.W_ch*1e6:.0f}×{g.H_ch*1e6:.0f} µm)  D_h={g.D_h*1e6:.0f} µm",
            f"  Q_evap     : {self.Q_evap:.1f} W",
            f"  q_flux     : {self.q_flux/1e4:.2f} W/cm²",
            f"  N_nodes    : {self.N_nodes}",
            f"  ─── Results ────────────────────────────────────────",
            f"  x_out      : {r.x_out:.4f}  {'⚠ DRYOUT' if r.dryout_flag else '✓ OK'}",
            f"  ΔP_fric    : {r.dP_fric:.1f} Pa",
            f"  ΔP_acc     : {r.dP_acc:.1f} Pa",
            f"  ΔP_total   : {r.dP_total:.1f} Pa",
            f"  T_wall_avg : {r.T_wall_avg - 273.15:.2f} °C",
            f"  α_avg      : {r.alpha_avg:.1f} W/m²·K",
            f"{'='*60}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _local_htc(self, state, G: float, D_h: float, q_flux: float) -> float:
        """
        Select and call appropriate HTC correlation based on fluid phase.

        Returns α [W/m²·K]. Falls back to 500 W/m²·K with a warning
        if correlations are unavailable (testing stubs scenario).
        """
        if not _CORR_AVAILABLE or self.htc_corr is None:
            return 500.0   # stub fallback

        phase = getattr(state, "phase", "two_phase")

        if phase in ("liquid", "subcooled_liquid"):
            # Single-phase liquid: Dittus-Boelter (heating, n=0.4)
            try:
                return self._htc_sp(state, G, D_h, q_flux)
            except Exception:
                return 1000.0

        elif phase in ("gas", "superheated_gas", "vapour", "vapor"):
            # Single-phase vapour: Dittus-Boelter
            try:
                return self._htc_sp(state, G, D_h, q_flux)
            except Exception:
                return 500.0

        else:
            # Two-phase: use configured htc_corr (Shah boiling default)
            try:
                return self.htc_corr(state, G, D_h, q_flux)
            except Exception:
                # Graceful fallback: Dittus-Boelter on liquid props
                try:
                    return self._htc_sp(state, G, D_h, q_flux)
                except Exception:
                    return 2000.0

    def _local_dp_fric(self, state, G: float, D_h: float) -> float:
        """
        Friction pressure gradient [Pa/m] at local conditions.
        """
        if not _CORR_AVAILABLE or self.dp_corr is None:
            return 0.0

        phase = getattr(state, "phase", "two_phase")

        if phase in ("liquid", "subcooled_liquid",
                     "gas", "superheated_gas", "vapour", "vapor"):
            try:
                return self._dp_sp(state, G, D_h)
            except Exception:
                return 0.0
        else:
            try:
                return self.dp_corr(state, G, D_h)
            except Exception:
                return 0.0

    def _local_dp_acc(self, state, G: float, D_h: float, dh: float) -> float:
        """
        Acceleration pressure drop [Pa] for a single node (HEM basis).

        ΔP_acc = G² · Δ(1/ρ_tp)
        Δ(1/ρ_tp) ≈ (∂(1/ρ)/∂h)|_P · dh   [computed from CoolProp state]

        For single-phase flow this term is negligible but non-zero.
        For two-phase flow it captures the void-fraction acceleration.
        """
        if not _CORR_AVAILABLE:
            return 0.0

        try:
            return acceleration_pressure_gradient(state, G, dh)
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        solved = "solved" if self._result is not None else "not solved"
        return (
            f"Evaporator(name={self.name!r}, "
            f"Q_evap={self.Q_evap:.1f} W, "
            f"N_ch={self.geom.N_ch}, "
            f"L_ch={self.geom.L_ch*1e3:.1f} mm, "
            f"D_h={self.geom.D_h*1e6:.0f} µm, "
            f"N_nodes={self.N_nodes}, "
            f"status={solved})"
        )
