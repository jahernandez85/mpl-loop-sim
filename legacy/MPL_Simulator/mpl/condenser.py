"""
components/condenser.py — Plate Heat Exchanger Condenser (SS Model)
====================================================================
MPL Simulation Library — Module 5 (Phase 5)

Models a brazed plate heat exchanger (PHX) used as the condenser in a
Mechanically Pumped Loop (MPL). The refrigerant (hot side) condenses
against liquid water (cold side) in a counter-flow, single-pass
configuration.

Three-zone nodal model
----------------------
The condenser is discretised into N_nodes axial control volumes.
Each node is classified into one of three zones based on local refrigerant
quality and temperature:

  Zone 1 — Desuperheating  : superheated vapour → saturated vapour  (x ≥ 1)
  Zone 2 — Condensation    : two-phase condensation  (0 < x < 1)
  Zone 3 — Subcooling      : sub-saturated liquid  (x ≤ 0)

Counter-flow water-side energy balance
---------------------------------------
Water flows counter to the refrigerant. At each node the water inlet
temperature is determined from a global enthalpy balance (ε-NTU per node).
For the full counter-flow geometry, water temperature increases from outlet
to inlet of the refrigerant side.

  Q_node  = mdot_ref · (h_ref_in_node − h_ref_out_node)
  T_w_in_node, T_w_out_node ← ε-NTU  [counter-flow]

ε-NTU method per node
---------------------
For two-phase condensation (C_r → 0):
  ε = 1 − exp(−NTU)
  NTU = α_ref · A_node / C_water_node   (water side controls)

For single-phase (desuperheating / subcooling):
  C_r = C_min / C_max
  ε   = (1 − exp[−NTU(1 − C_r)]) / (1 − C_r · exp[−NTU(1 − C_r)])
  NTU = UA_node / C_min
  UA_node = 1 / (1/α_ref·A_node + t_plate/k_plate·A_node + 1/α_w·A_node)

HTC correlations
----------------
  Refrigerant, condensation  → YanCondensationHTC  (Yan et al. 1999)
  Refrigerant, single-phase  → DittusBoelterHTC    (cooling, n = 0.3)
  Water side (always SP)     → DittusBoelterHTC    (heating, n = 0.4)

Pressure drop
-------------
  Refrigerant, two-phase     → YanCondensationDP   (Yan et al. 1999)
  Refrigerant, single-phase  → BlassiusDP
  Acceleration ΔP (two-phase): ΔP_acc = G²·Δ(1/ρ_tp)  [HEM, Dogan 1983]
  Port pressure drop          → optional, set dp_port_ref [Pa]

Water side (informational only — not part of refrigerant loop ΔP):
  Water ΔP is computed and stored but does NOT feed back into the
  refrigerant pressure iteration.

Geometry descriptor (CondenserGeometry)
----------------------------------------
  N_ch     : int    — number of refrigerant channels (per pass)
  L_p      : float  — plate / channel length [m]
  D_h      : float  — hydraulic diameter of plate channel [m]
  W_p      : float  — effective plate width [m]
  t_plate  : float  — plate thickness [m]
  k_plate  : float  — plate thermal conductivity [W/m·K]
  N_ch_w   : int    — number of water-side channels
  D_h_w    : float  — water-side hydraulic diameter [m]

Derived per channel:
  A_c_ref  = D_h² · π / 4   (circular equivalent; override with W_p·H_ch if rect)
  A_eff    = N_ch · L_p · W_p    total effective heat transfer area [m²]

Usage example
-------------
    from fluid_properties import FluidState
    from condenser import Condenser, CondenserGeometry

    geom = CondenserGeometry(
        N_ch    = 29,
        L_p     = 0.25,
        D_h     = 5.3e-3,
        W_p     = 0.076,
        t_plate = 6e-4,
        k_plate = 15.0,   # SS
        N_ch_w  = 30,
        D_h_w   = 5.3e-3,
    )
    cond = Condenser(
        geom         = geom,
        T_w_in       = 283.15,   # 10 °C inlet water
        mdot_w       = 0.10,     # kg/s
        N_nodes      = 40,
        name         = "Cond_Main",
    )
    outlet = cond.solve_ss(inlet_port)
    print(cond.summary())

References
----------
[1]  Y.-Y. Yan, H.-C. Lio, T.-F. Lin, "Condensation heat transfer and pressure
     drop of refrigerant R-134a in a plate heat exchanger,"
     Int. J. Heat Mass Transfer 42 (1999) 993-1006.  [Yan condensation]
[2]  R. Kokate, C. Park, "Pumped two-phase loop …,"
     Appl. Therm. Eng. 229 (2023) 120630.  [Condenser model & validation]
[3]  R. Kokate, PhD Thesis, 2024, §2.2 / Appendix A–B.  [Yan eqs., ΔP detail]
[4]  T.N. Dogan (1983).  [HEM acceleration ΔP: G²·d(1/ρ)]
[5]  F. Dittus, L. Boelter (1930).  [Single-phase HTC]
[6]  W. Wang et al., Appl. Sci. 13 (2023) 7472.  [Plate condenser model]
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
        YanCondensationHTC,
        DittusBoelterHTC,
        BlassiusDP,
        MullerSteinhagenHeckDP,
        HomogeneousDP,
        acceleration_pressure_gradient,
    )
    _CORR_AVAILABLE = True
    _YAN_HTC = YanCondensationHTC()
    _DB_HTC_COOLING = DittusBoelterHTC(heating=False)  # single-phase cooling (ref side)
    _DB_HTC_HEATING = DittusBoelterHTC(heating=True)   # water side
    _BLASIUS_DP = BlassiusDP()
    _HOMOGENEOUS_DP = HomogeneousDP()
except ImportError:
    _CORR_AVAILABLE = False
    _YAN_HTC = None
    _DB_HTC_COOLING = None
    _DB_HTC_HEATING = None
    _BLASIUS_DP = None
    _HOMOGENEOUS_DP = None

try:
    from base import Component, Port
    _BASE_AVAILABLE = True
except ImportError:
    _BASE_AVAILABLE = False
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

class CondenserWarning(UserWarning):
    """Fired when a non-physical or out-of-range condition is detected."""


class IncompleteCoolingWarning(CondenserWarning):
    """Fired when refrigerant exits condenser with quality > 0 (partial cond.)."""


# ---------------------------------------------------------------------------
# Water properties (pure-water approximations, T in K)
# ---------------------------------------------------------------------------
# Liquid water at ~10–30 °C.  CoolProp not used here to keep condenser
# self-contained and fast; relative error < 1 % in 0–40 °C range.

_WATER_CP   = 4182.0    # J/kg·K  (specific heat, ~20 °C)
_WATER_RHO  = 998.0     # kg/m³
_WATER_MU   = 1.002e-3  # Pa·s    (dynamic viscosity, ~20 °C)
_WATER_K    = 0.598     # W/m·K
_WATER_PR   = 7.01      # Prandtl number


def _water_nusselt_dittus_boelter(Re_w: float, Pr_w: float = _WATER_PR) -> float:
    """Nu = 0.023 Re^0.8 Pr^0.4 (Dittus-Boelter, heating)."""
    return 0.023 * Re_w**0.8 * Pr_w**0.4


def _water_htc(mdot_w_ch: float, D_h_w: float) -> float:
    """
    Water-side single-phase HTC [W/m²·K].

    Parameters
    ----------
    mdot_w_ch : float  — mass flow rate per water channel [kg/s]
    D_h_w     : float  — hydraulic diameter of water channel [m]
    """
    A_c_w = math.pi * (D_h_w / 2)**2   # circular equivalent
    G_w   = mdot_w_ch / A_c_w
    Re_w  = G_w * D_h_w / _WATER_MU
    Nu_w  = _water_nusselt_dittus_boelter(Re_w)
    return Nu_w * _WATER_K / D_h_w


# ---------------------------------------------------------------------------
# CondenserGeometry — immutable geometry descriptor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CondenserGeometry:
    """
    Geometric parameters for a brazed plate heat exchanger condenser.

    Parameters
    ----------
    N_ch    : int    — number of refrigerant flow channels (per pass)
    L_p     : float  — effective plate length (port-to-port distance) [m]
    D_h     : float  — hydraulic diameter of refrigerant channel [m]
    W_p     : float  — effective plate width [m]
    t_plate : float  — plate thickness [m]  (default 0.6 mm, SS)
    k_plate : float  — plate thermal conductivity [W/m·K] (default 15 W/m·K, SS)
    N_ch_w  : int    — number of water-side channels (default = N_ch + 1)
    D_h_w   : float  — hydraulic diameter of water channel [m] (default = D_h)
    N_passes: int    — number of refrigerant passes (default 1)

    Derived properties
    ------------------
    A_c_ref  : cross-sectional area per refrigerant channel [m²]  (circular equiv.)
    A_node   : heat transfer area per node per channel [m²]
    A_eff    : total effective heat transfer area (all N_ch channels) [m²]
    """

    N_ch:    int
    L_p:     float
    D_h:     float
    W_p:     float
    t_plate: float = 6e-4    # 0.6 mm
    k_plate: float = 15.0    # SS
    N_ch_w:  int   = 0       # 0 → set to N_ch + 1 in __post_init__
    D_h_w:   float = 0.0     # 0 → same as D_h
    N_passes: int  = 1

    def __post_init__(self):
        if self.N_ch < 1:
            raise ValueError(f"N_ch must be ≥ 1, got {self.N_ch}")
        for attr in ("L_p", "D_h", "W_p", "t_plate", "k_plate"):
            v = getattr(self, attr)
            if v <= 0:
                raise ValueError(f"{attr} must be > 0, got {v}")
        # N_ch_w and D_h_w allow post-init override via object.__setattr__
        # because frozen=True; use object.__setattr__ for mutable fields.
        if self.N_ch_w == 0:
            object.__setattr__(self, "N_ch_w", self.N_ch + 1)
        if self.D_h_w == 0.0:
            object.__setattr__(self, "D_h_w", self.D_h)

    @property
    def A_c_ref(self) -> float:
        """Cross-sectional area per refrigerant channel [m²] (circular equiv.)."""
        return math.pi * (self.D_h / 2)**2

    @property
    def A_eff(self) -> float:
        """Total effective heat transfer area [m²] (all channels)."""
        return self.N_ch * self.L_p * self.W_p

    def A_node(self, N_nodes: int) -> float:
        """Heat transfer area per node per channel [m²]."""
        return (self.L_p / N_nodes) * self.W_p


# ---------------------------------------------------------------------------
# CondenserResult — output data container
# ---------------------------------------------------------------------------

@dataclass
class CondenserResult:
    """
    Full output from a single solve_ss() call.

    Attributes
    ----------
    z           : ndarray [m]     — axial coordinate (0 = ref inlet)
    P_ref       : ndarray [Pa]    — refrigerant pressure profile
    h_ref       : ndarray [J/kg]  — refrigerant enthalpy profile
    x_ref       : ndarray [-]     — refrigerant quality profile
    T_ref       : ndarray [K]     — refrigerant temperature profile
    T_water     : ndarray [K]     — water temperature profile (counter-flow)
    alpha_ref   : ndarray [W/m²K] — refrigerant-side HTC profile
    alpha_water : ndarray [W/m²K] — water-side HTC profile
    zone        : list[str]       — zone label per node ('desuperheat'/'cond'/'subcool')
    dP_fric     : float [Pa]      — total frictional pressure drop (ref side)
    dP_acc      : float [Pa]      — total acceleration pressure drop (ref side)
    dP_total    : float [Pa]      — total refrigerant pressure drop
    Q_total     : float [W]       — total heat rejected to water
    x_out       : float [-]       — outlet refrigerant quality
    T_ref_out   : float [K]       — outlet refrigerant temperature
    T_water_out : float [K]       — water outlet temperature
    alpha_avg   : float [W/m²K]  — area-averaged refrigerant HTC
    incomplete_condensation : bool — True if x_out > 0 (not fully condensed)
    """

    z:           np.ndarray
    P_ref:       np.ndarray
    h_ref:       np.ndarray
    x_ref:       np.ndarray
    T_ref:       np.ndarray
    T_water:     np.ndarray
    alpha_ref:   np.ndarray
    alpha_water: np.ndarray
    zone:        List[str]
    dP_fric:     float
    dP_acc:      float
    dP_total:    float
    Q_total:     float
    x_out:       float
    T_ref_out:   float
    T_water_out: float
    alpha_avg:   float
    incomplete_condensation: bool


# ---------------------------------------------------------------------------
# Condenser — main component class
# ---------------------------------------------------------------------------

class Condenser(Component):
    """
    Steady-state model of a plate heat exchanger condenser.

    The refrigerant enters (possibly superheated) and exits as subcooled
    liquid. The cooling water enters at *T_w_in* counter-currently.

    Parameters
    ----------
    geom          : CondenserGeometry
    T_w_in        : float  — water inlet temperature [K]
    mdot_w        : float  — total water-side mass flow rate [kg/s]
    N_nodes       : int    — number of axial control volumes (default 40)
    dp_corr_2ph   : callable | None
        Two-phase pressure drop correlation (default: HomogeneousDP).
        Must follow DPCorrelation protocol: f(state, G, D_h) → Pa/m.
    dp_port_ref   : float  — refrigerant port pressure drop [Pa] (default 0)
    name          : str
    """

    def __init__(
        self,
        geom:         CondenserGeometry,
        T_w_in:       float,
        mdot_w:       float,
        N_nodes:      int   = 40,
        dp_corr_2ph:  object = None,
        dp_port_ref:  float  = 0.0,
        name:         str    = "Condenser",
    ):
        super().__init__(name=name)

        if not isinstance(geom, CondenserGeometry):
            raise TypeError("geom must be a CondenserGeometry instance.")
        if T_w_in <= 0:
            raise ValueError(f"T_w_in must be > 0 K, got {T_w_in}")
        if mdot_w <= 0:
            raise ValueError(f"mdot_w must be > 0 kg/s, got {mdot_w}")
        if N_nodes < 4:
            raise ValueError(f"N_nodes must be ≥ 4, got {N_nodes}")

        self.geom        = geom
        self.T_w_in      = T_w_in
        self.mdot_w      = mdot_w
        self.N_nodes     = N_nodes
        self.dp_port_ref = dp_port_ref
        self.name        = name

        # Two-phase ΔP correlation: default to HomogeneousDP
        if dp_corr_2ph is not None:
            self._dp_2ph = dp_corr_2ph
        elif _CORR_AVAILABLE:
            self._dp_2ph = _HOMOGENEOUS_DP
        else:
            self._dp_2ph = None

        self._result: Optional[CondenserResult] = None

    # ------------------------------------------------------------------
    # Component interface
    # ------------------------------------------------------------------

    def solve_ss(self, inlet) -> "Port":
        """
        Solve steady-state condenser given inlet Port.

        Parameters
        ----------
        inlet : Port
            Must carry a FluidState (refrigerant, hot side) and mdot [kg/s].

        Returns
        -------
        Port
            Outlet Port with updated FluidState and same mdot.

        Raises
        ------
        ValueError
            If inlet state is invalid (e.g. missing attributes).
        RuntimeError
            If fluid_properties module is not available.
        """
        # --- Unpack inlet ---------------------------------------------------
        state_in = inlet.state
        mdot     = float(inlet.mdot)

        if mdot <= 0:
            raise ValueError(f"[{self.name}] mdot must be > 0, got {mdot}")

        geom = self.geom
        N    = self.N_nodes

        # Mass flux per channel [kg/m²·s]
        G = mdot / (geom.N_ch * geom.A_c_ref)

        # Water: split evenly across water channels
        mdot_w_ch = self.mdot_w / geom.N_ch_w   # per water channel [kg/s]
        C_water   = self.mdot_w * _WATER_CP       # total water heat capacity rate [W/K]

        # α_water (constant along condenser — water stays single-phase)
        alpha_w = _water_htc(mdot_w_ch, geom.D_h_w)

        # Node length and area
        dz      = geom.L_p / N
        A_node  = geom.A_node(N)    # per channel, one node

        # ----------------------------------------------------------------
        # Initialise arrays  (index 0 = refrigerant INLET)
        # ----------------------------------------------------------------
        z_arr     = np.linspace(0.0, geom.L_p, N + 1)
        P_arr     = np.zeros(N + 1)
        h_arr     = np.zeros(N + 1)
        x_arr     = np.zeros(N + 1)
        T_arr     = np.zeros(N + 1)

        alpha_ref_arr = np.zeros(N)
        alpha_w_arr   = np.full(N, alpha_w)
        zone_arr      = [""] * N
        Q_node_arr    = np.zeros(N)
        dP_fric_arr   = np.zeros(N)
        dP_acc_arr    = np.zeros(N)

        # Water temperature array — counter-flow.
        # T_w_arr[i] = water temperature at the left boundary of node i
        # T_w_arr[N] = water temperature at refrigerant outlet (= T_w_in)
        T_w_arr = np.zeros(N + 1)
        T_w_arr[N] = self.T_w_in   # water enters at refrigerant outlet

        # Set inlet state
        P_arr[0] = state_in.P
        h_arr[0] = state_in.h

        # Build state at inlet
        state_node = _make_state(state_in, P_arr[0], h_arr[0])
        x_arr[0]   = getattr(state_node, "x", 0.0)
        T_arr[0]   = state_node.T

        # ----------------------------------------------------------------
        # Forward pass: march from refrigerant inlet (i=0) to outlet (i=N)
        # At each node we: (a) find α_ref, (b) solve ε-NTU → Q_node,
        # (c) update h_ref, P_ref, T_ref.
        # Water temperature is updated backward (counter-flow coupling).
        # ----------------------------------------------------------------
        # We solve this with a two-pass approach:
        #   Pass 1: march forward assuming T_w = T_w_in at every node
        #           (first estimate of Q_node and h distribution)
        #   Pass 2: recalculate T_w backward from Q_node distribution
        #           and re-solve (single corrector iteration is sufficient
        #           for typical condenser operating points).
        # This is a simple and robust approach for counter-flow NTU.

        for _pass in range(2):
            P_arr[0] = state_in.P
            h_arr[0] = state_in.h
            state_node = _make_state(state_in, P_arr[0], h_arr[0])

            for i in range(N):
                P_i = P_arr[i]
                h_i = h_arr[i]
                state_i = _make_state(state_in, P_i, h_i)

                # Local quality and zone
                # CoolProp returns nan for x in single-phase regions;
                # use phase string as primary discriminator.
                phase_i = getattr(state_i, "phase", "two_phase")
                x_raw   = getattr(state_i, "x", 0.5)
                try:
                    x_i = float(x_raw)
                except (TypeError, ValueError):
                    x_i = float("nan")
                if math.isnan(x_i):
                    x_i = 2.0 if phase_i in ("vapor", "gas") else -1.0

                T_ref_i = float(state_i.T)

                if phase_i in ("vapor", "gas") or x_i > 1.0:
                    zone = "desuperheat"
                elif phase_i in ("liquid",) or x_i < 0.0:
                    zone = "subcooling"
                else:
                    zone = "condensation"

                # ── Refrigerant-side HTC ────────────────────────────────
                alpha_ref_i = self._local_alpha_ref(state_i, G, geom.D_h, zone)
                alpha_ref_arr[i] = alpha_ref_i
                zone_arr[i]      = zone

                # ── Water temperature at node inlet (counter-flow) ──────
                # On pass 1, T_w_arr is initialised to T_w_in.
                # On pass 2, it is corrected from the backward sweep.
                T_w_i = T_w_arr[i]   # water at refrigerant-inlet side of node

                # ── UA and ε-NTU for this node ──────────────────────────
                # UA: overall heat transfer coefficient × area (per channel)
                UA_i = _ua_node(
                    alpha_ref_i, alpha_w, A_node,
                    geom.t_plate, geom.k_plate
                )

                Q_node_i = _entu_node(
                    UA_i, mdot, C_water,
                    T_ref_i, T_w_i,
                    zone, geom.N_ch, _WATER_CP
                )
                Q_node_arr[i] = Q_node_i

                # ── Refrigerant enthalpy update ─────────────────────────
                # Q_node_i is heat rejected by refrigerant, h decreases
                dh   = -Q_node_i / mdot
                h_new = h_i + dh

                # ── Pressure drop (frictional + acceleration) ───────────
                dP_f  = self._local_dp_fric(state_i, G, geom.D_h, zone) * dz
                dP_a  = self._local_dp_acc(state_i, G, dh)
                dP_fric_arr[i] = dP_f
                dP_acc_arr[i]  = dP_a

                P_new = P_i - dP_f - dP_a   # pressure drops along flow

                P_arr[i + 1] = max(P_new, 1e3)   # floor at 1 kPa
                h_arr[i + 1] = h_new

                state_next = _make_state(state_in, P_arr[i + 1], h_arr[i + 1])
                x_raw_next = getattr(state_next, "x", 0.0)
                try:
                    x_next = float(x_raw_next)
                    if math.isnan(x_next):
                        ph_next = getattr(state_next, "phase", "two_phase")
                        x_next = 2.0 if ph_next in ("vapor", "gas") else -1.0
                except (TypeError, ValueError):
                    x_next = 0.5
                x_arr[i + 1] = x_next
                T_arr[i + 1] = float(state_next.T)

            # ── Backward sweep: update water temperatures ───────────────
            # T_w_arr[N] = T_w_in  (water enters at refrigerant exit side)
            # Energy balance per node: Q_node_i = mdot_w·Cp·ΔT_w
            T_w_arr[N] = self.T_w_in
            for i in range(N - 1, -1, -1):
                T_w_arr[i] = T_w_arr[i + 1] + Q_node_arr[i] / C_water

        # ----------------------------------------------------------------
        # Aggregate results
        # ----------------------------------------------------------------
        dP_fric_total = float(np.sum(dP_fric_arr)) + self.dp_port_ref
        dP_acc_total  = float(np.sum(dP_acc_arr))
        dP_total      = dP_fric_total + dP_acc_total
        Q_total       = float(np.sum(Q_node_arr))

        state_out = _make_state(state_in, P_arr[N], h_arr[N])
        x_out_raw = float(x_arr[N])
        x_out     = x_out_raw if not math.isnan(x_out_raw) else -1.0
        T_ref_out = float(T_arr[N])
        T_w_out   = float(T_w_arr[0])   # water exits at refrigerant inlet side

        incomplete = (x_out > 0.0)
        if incomplete:
            warnings.warn(
                f"[{self.name}] Refrigerant exits condenser with x_out={x_out:.3f} > 0. "
                "Condensation is incomplete — increase condenser area or water flow.",
                IncompleteCoolingWarning,
                stacklevel=2,
            )

        self._result = CondenserResult(
            z           = z_arr,
            P_ref       = P_arr,
            h_ref       = h_arr,
            x_ref       = x_arr,
            T_ref       = T_arr,
            T_water     = T_w_arr,
            alpha_ref   = alpha_ref_arr,
            alpha_water = alpha_w_arr,
            zone        = zone_arr,
            dP_fric     = dP_fric_total,
            dP_acc      = dP_acc_total,
            dP_total    = dP_total,
            Q_total     = Q_total,
            x_out       = x_out,
            T_ref_out   = T_ref_out,
            T_water_out = T_w_out,
            alpha_avg   = float(np.mean(alpha_ref_arr)),
            incomplete_condensation = incomplete,
        )

        self._last_dP = dP_total
        self._last_Q  = Q_total

        outlet = Port(state=state_out, mdot=mdot)
        self.outlet = outlet
        return outlet

    def pressure_drop(self) -> float:
        """Total refrigerant pressure drop [Pa] from last solve_ss()."""
        if self._result is None:
            raise RuntimeError(
                f"[{self.name}] Call solve_ss() before querying pressure_drop()."
            )
        return self._result.dP_total

    def heat_transfer(self) -> float:
        """Total heat rejected by refrigerant [W] from last solve_ss()."""
        if self._result is None:
            raise RuntimeError(
                f"[{self.name}] Call solve_ss() before querying heat_transfer()."
            )
        return self._result.Q_total

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def result(self) -> CondenserResult:
        if self._result is None:
            raise RuntimeError(f"[{self.name}] Call solve_ss() first.")
        return self._result

    @property
    def x_out(self) -> float:
        return self.result.x_out

    @property
    def T_ref_out(self) -> float:
        return self.result.T_ref_out

    @property
    def T_water_out(self) -> float:
        return self.result.T_water_out

    @property
    def alpha_avg(self) -> float:
        return self.result.alpha_avg

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return a formatted summary of the last solve_ss() call."""
        if self._result is None:
            return f"Condenser '{self.name}' — not yet solved."
        r  = self._result
        g  = self.geom
        zones_count = {z: r.zone.count(z) for z in ("desuperheat", "condensation", "subcooling")}
        lines = [
            f"{'='*62}",
            f" Condenser: {self.name}",
            f"{'='*62}",
            f"  Geometry   : {g.N_ch} ref-ch × {g.L_p*1e2:.1f} cm  "
            f"Dh={g.D_h*1e3:.1f} mm  W={g.W_p*1e2:.1f} cm",
            f"  Plate      : t={g.t_plate*1e3:.1f} mm  k={g.k_plate:.1f} W/m·K  "
            f"A_eff={g.A_eff:.4f} m²",
            f"  Water in   : T={self.T_w_in - 273.15:.1f} °C  "
            f"ṁ={self.mdot_w*1e3:.1f} g/s",
            f"  ─── Zone distribution ({'nodes':>6}) ──────────────────────",
            f"  Desuperheat : {zones_count['desuperheat']:>4} nodes",
            f"  Condensation: {zones_count['condensation']:>4} nodes",
            f"  Subcooling  : {zones_count['subcooling']:>4} nodes",
            f"  ─── Results ────────────────────────────────────────────",
            f"  x_out      : {r.x_out:.4f}  "
            f"{'⚠ INCOMPLETE COND.' if r.incomplete_condensation else '✓ fully condensed'}",
            f"  T_ref_out  : {r.T_ref_out - 273.15:.2f} °C",
            f"  T_water_out: {r.T_water_out - 273.15:.2f} °C",
            f"  Q_total    : {r.Q_total:.1f} W",
            f"  ΔP_fric    : {r.dP_fric:.1f} Pa",
            f"  ΔP_acc     : {r.dP_acc:.1f} Pa",
            f"  ΔP_total   : {r.dP_total:.1f} Pa",
            f"  α_ref_avg  : {r.alpha_avg:.1f} W/m²·K",
            f"  α_water    : {r.alpha_water[0]:.1f} W/m²·K",
            f"{'='*62}",
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _local_alpha_ref(
        self,
        state:  object,
        G:      float,
        D_h:    float,
        zone:   str,
    ) -> float:
        """
        Refrigerant-side HTC [W/m²·K].

        Zone dispatch:
          condensation → YanCondensationHTC
          desuperheat  → DittusBoelterHTC (vapour, cooling n=0.3)
          subcooling   → DittusBoelterHTC (liquid, cooling n=0.3)
        """
        if not _CORR_AVAILABLE:
            return 3000.0   # stub fallback

        try:
            if zone == "condensation":
                return _yan_htc_safe(state, G, D_h)
            else:
                # Single-phase: Dittus-Boelter (cooling, n=0.3)
                return _db_htc_safe(state, G, D_h, heating=False)
        except Exception as exc:
            warnings.warn(
                f"[{self.name}] HTC correlation failed ({exc}); using 2000 W/m²K fallback.",
                CondenserWarning,
                stacklevel=3,
            )
            return 2000.0

    def _local_dp_fric(
        self,
        state: object,
        G:     float,
        D_h:   float,
        zone:  str,
    ) -> float:
        """Friction pressure gradient [Pa/m] at local conditions."""
        if not _CORR_AVAILABLE:
            return 0.0

        try:
            if zone == "condensation":
                return _yan_dp_safe(state, G, D_h)
            else:
                return _blasius_dp_safe(state, G, D_h)
        except Exception:
            return 0.0

    @staticmethod
    def _local_dp_acc(state: object, G: float, dh: float) -> float:
        """
        Acceleration pressure drop [Pa] for a single node (HEM).

        ΔP_acc = G² · Δ(v_tp) = G² · (v_g - v_l) · Δx
        where Δx = dh / h_fg   [Dogan 1983, homogeneous model]

        Negative dh (condensation) → quality drops → ΔP_acc < 0 (pressure recovery).
        For single-phase nodes (h_fg = 0 or phase liquid) this term is negligible.
        """
        try:
            phase = getattr(state, "phase", "two_phase")
            if phase in ("liquid", "vapor", "gas"):
                return 0.0
            h_fg = float(getattr(state, "h_fg", 0.0))
            if h_fg <= 0:
                return 0.0
            v_l = 1.0 / float(state.rho_l)
            v_g = 1.0 / float(state.rho_v)
            dx  = dh / h_fg
            return G**2 * (v_g - v_l) * dx
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        solved = "solved" if self._result is not None else "not solved"
        return (
            f"Condenser(name={self.name!r}, "
            f"N_ch={self.geom.N_ch}, "
            f"L_p={self.geom.L_p*1e2:.1f} cm, "
            f"D_h={self.geom.D_h*1e3:.1f} mm, "
            f"T_w_in={self.T_w_in - 273.15:.1f} °C, "
            f"mdot_w={self.mdot_w*1e3:.1f} g/s, "
            f"N_nodes={self.N_nodes}, "
            f"status={solved})"
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Safe HTC / ΔP wrappers — bypass _validate_state for attributes that
# FluidState does not expose (k_v, Pr_v), computing directly from primitives.
# ---------------------------------------------------------------------------

def _yan_htc_safe(state: object, G: float, D_h: float) -> float:
    """
    Yan (1999) condensation HTC without calling _validate_state.

    α = 4.118 · Re_eq^0.4 · Pr_l^(1/3) · k_l / D_h
    G_eq = G · [1 - x + x · (ρ_l/ρ_v)^0.5]
    Re_eq = G_eq · D_h / μ_l
    """
    x     = float(getattr(state, "x", 0.5))
    if math.isnan(x) or x < 0.001:
        x = 0.001
    if x > 0.999:
        x = 0.999
    rho_l = float(state.rho_l)
    rho_v = float(state.rho_v)
    mu_l  = float(state.mu_l)
    k_l   = float(state.k_l)
    Pr_l  = float(state.Pr_l)

    G_eq  = G * (1.0 - x + x * (rho_l / rho_v) ** 0.5)
    Re_eq = G_eq * D_h / mu_l
    return 4.118 * Re_eq ** 0.4 * Pr_l ** (1.0 / 3.0) * k_l / D_h


def _db_htc_safe(state: object, G: float, D_h: float, heating: bool = False) -> float:
    """
    Dittus-Boelter HTC without calling _validate_state.

    Nu = 0.023 · Re^0.8 · Pr^n    n=0.4 heating, n=0.3 cooling
    Uses liquid props for liquid/two-phase, vapour props for gas zone.
    """
    phase = getattr(state, "phase", "liquid")
    n = 0.4 if heating else 0.3

    if phase in ("vapor", "gas"):
        # Use saturation vapour props (CoolProp provides mu_v, k_l as fallback)
        mu  = float(getattr(state, "mu_v", state.mu_l))
        k   = float(getattr(state, "k_l", 0.02))   # fallback to liq k
        Pr  = float(getattr(state, "Pr_l", 1.0))
        rho = float(getattr(state, "rho_v", state.rho))
    else:
        mu  = float(state.mu_l)
        k   = float(state.k_l)
        Pr  = float(state.Pr_l)
        rho = float(getattr(state, "rho_l", state.rho))

    Re = G * D_h / mu
    Nu = 0.023 * Re ** 0.8 * Pr ** n
    return Nu * k / D_h


def _yan_dp_safe(state: object, G: float, D_h: float) -> float:
    """
    Yan (1999) two-phase friction pressure gradient [Pa/m].

    f_tp = 0.061 / Re_eq^0.25   (Yan 1999 plate HX correlation)
    dP/dz = 2 · f_tp · G_eq² / (D_h · ρ_l)

    Reference: Yan et al. 1999, Eq. (14–15); Kokate 2023 Appendix B.
    """
    x     = float(getattr(state, "x", 0.5))
    if math.isnan(x) or x < 0.001:
        x = 0.001
    if x > 0.999:
        x = 0.999
    rho_l = float(state.rho_l)
    rho_v = float(state.rho_v)
    mu_l  = float(state.mu_l)

    G_eq  = G * (1.0 - x + x * (rho_l / rho_v) ** 0.5)
    Re_eq = G_eq * D_h / mu_l
    f_tp  = 0.061 / Re_eq ** 0.25
    return 2.0 * f_tp * G_eq ** 2 / (D_h * rho_l)


def _blasius_dp_safe(state: object, G: float, D_h: float) -> float:
    """
    Blasius / Hagen-Poiseuille single-phase friction gradient [Pa/m].
    Uses liquid properties (appropriate for subcooling / liquid zones).
    """
    phase = getattr(state, "phase", "liquid")
    if phase in ("vapor", "gas"):
        mu  = float(getattr(state, "mu_v", state.mu_l))
        rho = float(getattr(state, "rho_v", state.rho))
    else:
        mu  = float(state.mu_l)
        rho = float(getattr(state, "rho_l", state.rho))

    Re = G * D_h / mu
    if Re < 2000:
        f = 16.0 / Re
    elif Re < 20000:
        f = 0.079 * Re ** (-0.25)
    else:
        f = 0.046 * Re ** (-0.20)
    return 2.0 * f * G ** 2 / (D_h * rho)


def _make_state(ref_state: object, P: float, h: float) -> object:
    """
    Construct a new FluidState at (P, h) using the same fluid as ref_state.

    Falls back gracefully if FluidState is not importable (test stubs).
    """
    if _FLUID_PROPS_AVAILABLE:
        try:
            from fluid_properties import FluidState as FS
            fluid = getattr(ref_state, "fluid", "R134a")
            return FS.from_Ph(fluid, P, h)
        except Exception:
            pass

    # Stub path: return a simple namespace mimicking FluidState
    import types
    s = types.SimpleNamespace()
    s.P    = P
    s.h    = h
    s.T    = getattr(ref_state, "T", 300.0)
    s.x    = getattr(ref_state, "x", 0.5)
    s.rho  = getattr(ref_state, "rho", 1000.0)
    s.phase = getattr(ref_state, "phase", "two_phase")
    # copy saturation props from reference (adequate for stubs)
    for attr in ("rho_l", "rho_v", "mu_l", "mu_v", "mu_tp",
                 "k_l", "k_v", "Pr_l", "Pr_v", "h_fg", "sigma",
                 "P_red", "T_sat", "h_l", "h_v"):
        setattr(s, attr, getattr(ref_state, attr, 1.0))
    return s


def _ua_node(
    alpha_ref: float,
    alpha_w:   float,
    A_node:    float,
    t_plate:   float,
    k_plate:   float,
) -> float:
    """
    Overall UA [W/K] for a single node (one refrigerant channel).

    1/UA = 1/(α_ref·A) + t/(k·A) + 1/(α_w·A)
    """
    A = A_node
    if A <= 0 or alpha_ref <= 0 or alpha_w <= 0:
        return 0.0
    return 1.0 / (1.0 / (alpha_ref * A)
                  + t_plate / (k_plate * A)
                  + 1.0 / (alpha_w * A))


def _entu_node(
    UA:       float,
    mdot_ref: float,
    C_water:  float,
    T_ref:    float,
    T_water:  float,
    zone:     str,
    N_ch:     int,
    cp_water: float = _WATER_CP,
) -> float:
    """
    Heat rejected by refrigerant in one node [W].

    Uses the ε-NTU counter-flow formulation:
      Two-phase condensation  (C_r → 0):  ε = 1 − exp(−NTU)
      Single-phase            (C_r > 0):  ε = ε_counter_flow(NTU, C_r)

    Q_node = ε · C_min · (T_ref − T_water)

    Parameters are per-channel values except C_water (total loop).
    mdot_ref is the *total* refrigerant mass flow rate; per-channel
    enthalpy update uses mdot_ref directly (channels are identical in
    parallel, so Q_total = Q_per_channel × N_ch, handled in outer loop).
    """
    if UA <= 0 or T_ref <= T_water:
        return 0.0

    # Per-channel water capacity rate (heat capacity rate per channel)
    C_w_ch = C_water / N_ch        # [W/K] water per channel

    if zone == "condensation":
        # Condensing side: C_ref → ∞ (isothermal), so C_r = C_w / C_ref → 0
        NTU = UA / C_w_ch
        eps = 1.0 - math.exp(-NTU)
        C_min = C_w_ch
    else:
        # Single-phase: finite C_ref per channel
        # cp_ref estimated from enthalpy step — use a nominal cp for ref liquid
        # We derive C_ref from mdot and specific heat implied by FluidState.
        # For simplicity use C_ref = mdot_ref * 1500 (R134a liquid ~1450 J/kgK)
        # A better approach would pass FluidState cp, but this is consistent
        # with how Kokate 2023 handles single-phase zones (ε-NTU with Kumar).
        cp_ref_est = 1450.0    # J/kg·K  (R134a liquid; conservative)
        C_ref_ch   = (mdot_ref / N_ch) * cp_ref_est
        C_min = min(C_ref_ch, C_w_ch)
        C_max = max(C_ref_ch, C_w_ch)
        C_r   = C_min / C_max if C_max > 0 else 0.0
        NTU   = UA / C_min
        # Counter-flow ε-NTU
        if abs(1.0 - C_r) < 1e-6:
            eps = NTU / (1.0 + NTU)
        else:
            arg = NTU * (1.0 - C_r)
            eps = (1.0 - math.exp(-arg)) / (1.0 - C_r * math.exp(-arg))

    Q_ch = eps * C_min * (T_ref - T_water)    # heat per channel [W]
    return Q_ch * N_ch                          # total heat [W]


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("condenser.py — smoke test  (Kokate 2023 geometry, R134a)")
    print("=" * 62)

    try:
        from fluid_properties import FluidState
        from base import Port

        # ── Geometry: flat-plate condenser from Kokate 2023 Table 3 ──
        geom = CondenserGeometry(
            N_ch    = 29,       # refrigerant channels
            L_p     = 0.25,     # port-to-port 25 cm
            D_h     = 5.3e-3,   # hydraulic diameter 5.3 mm
            W_p     = 0.076,    # plate width 7.6 cm
            t_plate = 6e-4,     # 0.6 mm SS plate
            k_plate = 15.0,     # W/m·K (stainless steel)
            N_ch_w  = 30,
            D_h_w   = 5.3e-3,
        )

        # ── Test 1: two-phase inlet (x=0.8), typical MPL condensing point ──
        print("\nTest 1: two-phase inlet  x_in=0.8")
        s_tp = FluidState.from_Px("R134a", 700e3, 0.8)
        cond1 = Condenser(geom=geom, T_w_in=283.15, mdot_w=0.5,
                          N_nodes=50, name="Cond_TwoPhase")
        out1 = cond1.solve_ss(Port(state=s_tp, mdot=7.6e-3))
        print(f"  Inlet : T={s_tp.T-273.15:.2f}°C  x={s_tp.x:.2f}  "
              f"h={s_tp.h:.1f} J/kg  phase={s_tp.phase}")
        print(f"  Outlet: T={out1.state.T-273.15:.2f}°C  "
              f"x={out1.state.x:.4f}  h={out1.state.h:.1f} J/kg")
        print(f"  Q={cond1.result.Q_total:.1f} W  "
              f"ΔP={cond1.result.dP_total:.1f} Pa  "
              f"α_avg={cond1.result.alpha_avg:.0f} W/m²K")

        # ── Test 2: superheated inlet (5K superheat) → should fully condense ──
        print("\nTest 2: superheated inlet (5K superheat)")
        T_sat = FluidState.from_Px("R134a", 700e3, 1.0).T
        s_sh  = FluidState.from_PT("R134a", 700e3, T_sat + 5)
        cond2 = Condenser(geom=geom, T_w_in=283.15, mdot_w=0.5,
                          N_nodes=50, name="Cond_Superheated")
        out2  = cond2.solve_ss(Port(state=s_sh, mdot=7.6e-3))
        print(f"  Inlet : T={s_sh.T-273.15:.2f}°C  phase={s_sh.phase}  h={s_sh.h:.1f} J/kg")
        r2 = cond2.result
        print(f"  Zones : desuperheat={r2.zone.count('desuperheat')}  "
              f"condensation={r2.zone.count('condensation')}  "
              f"subcooling={r2.zone.count('subcooling')} nodes")
        print(f"  Outlet: T={out2.state.T-273.15:.2f}°C  "
              f"x={out2.state.x:.4f}  h={out2.state.h:.1f} J/kg")
        print(f"  Q={r2.Q_total:.1f} W  ΔP={r2.dP_total:.1f} Pa  "
              f"T_water_out={r2.T_water_out-273.15:.2f}°C")
        assert not r2.incomplete_condensation, "Should be fully condensed"

        # ── Test 3: repr and summary ──────────────────────────────────
        print("\nTest 3: repr")
        print(f"  {cond2!r}")

        # ── Test 4: geometry validation ───────────────────────────────
        print("\nTest 4: CondenserGeometry derived properties")
        print(f"  A_eff   = {geom.A_eff:.4f} m²")
        print(f"  A_c_ref = {geom.A_c_ref*1e6:.2f} mm²")
        print(f"  A_node  = {geom.A_node(50)*1e4:.2f} cm²  (per ch, 50 nodes)")

        # ── Test 5: Error path — mdot=0 ──────────────────────────────
        print("\nTest 5: error handling")
        try:
            cond2.solve_ss(Port(state=s_sh, mdot=0.0))
            assert False, "Should have raised"
        except ValueError as e:
            print(f"  ValueError raised correctly: {e}")

        print("\n✓  All smoke tests passed.")

    except ImportError as e:
        print(f"  Modules not available ({e}). Running geometry-only test.")
        geom = CondenserGeometry(
            N_ch=29, L_p=0.25, D_h=5.3e-3, W_p=0.076,
            t_plate=6e-4, k_plate=15.0,
        )
        print(f"  A_eff   = {geom.A_eff:.4f} m²")
        print(f"  A_c_ref = {geom.A_c_ref*1e6:.2f} mm²")
        print(f"  N_ch_w  = {geom.N_ch_w}")
        print("✓  CondenserGeometry smoke test passed.")
