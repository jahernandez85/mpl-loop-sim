"""
mpl.fluid_properties
====================
CoolProp wrapper for the MPL simulation library, with A1_TwoPhProp table
fallback for properties unavailable in CoolProp (electrical conductivity,
relative permittivity, and improved surface tension / viscosity for some
fluids).

Priority logic (per property):
    1. CoolProp AbstractState  — primary source (EOS-based, continuous)
    2. Empirical correlations  — for organics when CoolProp lacks model
       (Letsou-Stiel for μ, Latini for k)
    3. A1_TwoPhProp CSV tables — for properties CoolProp does not expose
       at all: electrical conductivity, relative permittivity.
       Also used as consistency cross-check for surface tension.

Supported fluids (CoolProp names):
    'Acetone'    — low-GWP organic, ~56 °C boiling @ 1 atm
    'R1233ZDE'   — low-GWP HFO, ~18 °C boiling @ 1 atm
    'R1234YF'    — low-GWP HFO, ~-29 °C boiling @ 1 atm
    'Water'      — condenser secondary side
    'CO2'        — low-GWP, used in some MPL systems
    'R134a'      — legacy refrigerant, validation reference

Additional fluids available via A1_TwoPhProp tables (electrical/dielectric
properties only): AMMONIA, ETHANOL, METHANOL, PROPANE, ISOBUTANE, NHEXANE,
NHEPTANE, CYCLOPENTANE, R245FA, R152A, R22, R11, R12, NOVEC649,
ISOPENTANE, R404A, R410A, R507A, ACETONE, TOLUENE, NPENTANE, R1234ZEE,
R1224YDZ, R1336MZZZ, CARBONDIOXIDE.

Physical basis:
    Homogeneous Equilibrium Model (HEM) as per Dogan (1983) and
    Kokate & Park (2023). Two phases move at the same velocity and
    share a single temperature (saturated mixture).

    Mixture density (Eq. 4, Dogan 1983):
        1/ρ_tp = x/ρ_v + (1-x)/ρ_l

    Mixture enthalpy (Eq. 5, Dogan 1983):
        h_tp = (1-x)*h_l + x*h_v

    Void fraction (homogeneous):
        α = 1 / (1 + (1-x)/x * ρ_v/ρ_l)

References:
    [1] Dogan (1983) — homogeneous model equations
    [2] Kokate & Park (2023) — P2PL system model, CoolProp usage
    [3] VanGerner (2016) — equation of state (H, P) as state variables
    [4] A1_TwoPhProp.py — CSV-based saturation property tables
"""

from __future__ import annotations

import math
import os
import warnings
from dataclasses import dataclass, field
from math import isnan as _isnan
from typing import Optional

import numpy as np
import CoolProp.CoolProp as CP
from CoolProp.CoolProp import AbstractState


# ===========================================================================
# A1_TwoPhProp integration — CSV table loader
# ===========================================================================

_TABLE_SEARCH_DIRS = [
    os.path.dirname(__file__),           # same directory as this file
    os.path.join(os.path.dirname(__file__), "..", "data"),   # mpl_sim/data/
    os.path.join(os.path.dirname(__file__), "..", "tables"), # mpl_sim/tables/
    os.getcwd(),                          # working directory (legacy support)
]

# Fluid CSV files as listed in A1_TwoPhProp.py
_TABLE_FILES = [
    'R1233ZDE.csv', 'TOLUENE.csv', 'NPENTANE.csv', 'NHEXANE.csv',
    'CARBONDIOXIDE.csv', 'NHEPTANE.csv', 'CYCLOPENTANE.csv', 'R1234ZEE.csv',
    'R245FA.csv', 'ETHANOL.csv', 'METHANOL.csv', 'PROPANE.csv',
    'ISOBUTANE.csv', 'R152A.csv', 'R1234YF.csv', 'R22.csv', 'R11.csv',
    'R12.csv', 'AMMONIA.csv', 'WATER.csv', 'ISOPENTANE.csv', 'R134A.csv',
    'R404A.csv', 'R410A.csv', 'R507A.csv', 'ACETONE.csv', 'NOVEC649.csv',
    'R1224YDZ.csv', 'R1336MZZZ.csv',
]

# Properties provided exclusively by the tables (not available in CoolProp)
_TABLE_ONLY_PROPS = {
    'EleConduc_liq', 'EleConduc_vap',
    'RelPermittivity_liq', 'RelPermittivity_vap',
}

# Properties provided by tables as supplement / cross-check
_TABLE_SUPPLEMENT_PROPS = {
    'Surface_tension',
    'ThConduc_liq', 'ThConduc_vap',
    'ViscosityDyn_liq', 'ViscosityDyn_vap',
}


def _find_csv(filename: str) -> Optional[str]:
    """Search known directories for a CSV table file."""
    for d in _TABLE_SEARCH_DIRS:
        path = os.path.join(d, filename)
        if os.path.isfile(path):
            return path
    return None


class _TableDB:
    """
    Lazy-loading database of saturation property tables from CSV files.
    Mirrors the loading logic of A1_TwoPhProp.py but with auto-discovery.
    """
    def __init__(self):
        self._data: dict[str, dict[str, np.ndarray]] = {}
        self._loaded  = False
        self._missing: set[str] = set()   # files not found — suppress repeated warnings

    def _ensure_loaded(self):
        if self._loaded:
            return
        import pandas as pd
        for fname in _TABLE_FILES:
            path = _find_csv(fname)
            if path is None:
                fluid_key = os.path.splitext(fname)[0]
                if fluid_key not in self._missing:
                    self._missing.add(fluid_key)
                continue
            try:
                df = pd.read_csv(path)
                fluid_key = os.path.splitext(os.path.basename(path))[0]
                self._data[fluid_key] = {col: df[col].values for col in df.columns}
            except Exception as exc:
                warnings.warn(f"A1_TwoPhProp: could not load {path}: {exc}", stacklevel=2)
        self._loaded = True

    def available(self, table_key: str) -> bool:
        self._ensure_loaded()
        return table_key in self._data

    def get_prop_at_T(self, table_key: str, T_sat_K: float,
                      quality_X: float, col_liq: str, col_vap: str) -> Optional[float]:
        """
        Interpolate a two-phase property at saturation temperature T_sat_K
        and quality quality_X.  Returns None if data unavailable.
        """
        self._ensure_loaded()
        data = self._data.get(table_key)
        if data is None:
            return None
        if col_liq not in data:
            return None

        temperatures = data['Temperature_sat']
        vals_liq = data[col_liq]
        vals_vap = data.get(col_vap, vals_liq)   # some props share liq/vap column

        idx = np.argsort(temperatures)
        T_arr  = temperatures[idx]
        vl_arr = vals_liq[idx]
        vv_arr = vals_vap[idx]

        if T_sat_K < T_arr.min() or T_sat_K > T_arr.max():
            return None   # out of range — do not extrapolate

        vl = float(np.interp(T_sat_K, T_arr, vl_arr))
        vv = float(np.interp(T_sat_K, T_arr, vv_arr))
        return vl + quality_X * (vv - vl)

    def get_scalar_at_T(self, table_key: str, T_sat_K: float, col: str) -> Optional[float]:
        """Interpolate a scalar (non-phase-split) property at T_sat_K."""
        return self.get_prop_at_T(table_key, T_sat_K, 0.0, col, col)


# Module-level singleton
_tables = _TableDB()


def _coolprop_to_table_key(coolprop_name: str) -> str:
    """
    Map CoolProp canonical name → CSV file stem used in A1_TwoPhProp.
    E.g. 'R134a' → 'R134A', 'CO2' → 'CARBONDIOXIDE', 'Acetone' → 'ACETONE'
    """
    _mapping = {
        "Acetone":   "ACETONE",
        "R1233ZDE":  "R1233ZDE",
        "R1234YF":   "R1234YF",
        "Water":     "WATER",
        "CO2":       "CARBONDIOXIDE",
        "R134a":     "R134A",
        "Ammonia":   "AMMONIA",
        "R245fa":    "R245FA",
        "R1234ze(E)": "R1234ZEE",
        "R1224yd(Z)": "R1224YDZ",
        "R1336mzz(Z)": "R1336MZZZ",
        "Propane":   "PROPANE",
        "IsoButane": "ISOBUTANE",
        "Ethanol":   "ETHANOL",
        "Methanol":  "METHANOL",
        "R152A":     "R152A",
        "R22":       "R22",
        "R11":       "R11",
        "R12":       "R12",
        "n-Pentane": "NPENTANE",
        "n-Hexane":  "NHEXANE",
        "n-Heptane": "NHEPTANE",
        "CycloPentane": "CYCLOPENTANE",
        "Toluene":   "TOLUENE",
        "IsoPentane": "ISOPENTANE",
    }
    return _mapping.get(coolprop_name, coolprop_name.upper().replace("-", ""))


# ===========================================================================
# Transport property fallback correlations (unchanged from original)
# ===========================================================================

def _viscosity_liquid_Letsou_Stiel(T: float, T_crit: float, P_crit: float,
                                    M: float, omega: float) -> float:
    """
    Letsou-Stiel correlation for saturated liquid viscosity [Pa·s].
    Reid, Prausnitz & Poling (1987), Chapter 9.

    Valid for: organic compounds, 0.76 < T_r < 0.98
    Accuracy: ~10% typical
    """
    T_r = T / T_crit
    xi  = T_crit**(1/6) / (M**0.5 * (P_crit / 1e5)**(2/3))   # P in bar
    eta_0 = (1.5174 - 2.135 * T_r + 0.75 * T_r**2) * 1e-5
    eta_1 = (4.2552 - 7.674 * T_r + 3.4 * T_r**2) * 1e-5
    return (eta_0 + omega * eta_1) / xi


def _conductivity_liquid_Latini(T: float, T_crit: float, T_b: float,
                                 M: float) -> float:
    """
    Latini correlation for saturated liquid thermal conductivity [W/m·K].
    Reid, Prausnitz & Poling (1987), Chapter 10.
    Accuracy: ~10-15%
    """
    A_star = 0.0655
    alpha  = 1.14
    beta   = 0.50
    gamma  = 0.167
    T_r    = T / T_crit
    k = (A_star * T_b**alpha) / (M**beta * T_crit**gamma) * (1 - T_r)**(0.38) / T_r**(1/6)
    return max(k, 0.01)


_FLUID_CONSTANTS: dict[str, dict] = {
    "Acetone": {
        "M":     58.08,
        "omega": 0.307,
        "T_b":   329.22,
    },
    "R1233ZDE": {
        "M":     130.50,
        "omega": 0.355,
        "T_b":   291.47,
    },
    "R1234YF": {
        "M":     114.04,
        "omega": 0.276,
        "T_b":   243.65,
    },
}


# ===========================================================================
# Supported fluid registry
# ===========================================================================

SUPPORTED_FLUIDS: dict[str, str] = {
    "acetone":      "Acetone",
    "r1233zde":     "R1233ZDE",
    "r1234yf":      "R1234YF",
    "water":        "Water",
    "co2":          "CO2",
    "r134a":        "R134a",
    "ammonia":      "Ammonia",
    "r245fa":       "R245fa",
    "propane":      "Propane",
    "isobutane":    "IsoButane",
    "ethanol":      "Ethanol",
    "methanol":     "Methanol",
    "r152a":        "R152A",
    "r22":          "R22",
    "r11":          "R11",
    "r12":          "R12",
    "npentane":     "n-Pentane",
    "nhexane":      "n-Hexane",
    "nheptane":     "n-Heptane",
    "cyclopentane": "CycloPentane",
    "toluene":      "Toluene",
    "isopentane":   "IsoPentane",
}


def resolve_fluid_name(name: str) -> str:
    """Return the CoolProp-canonical name for a fluid identifier."""
    key = name.lower().replace("-", "").replace("_", "")
    if key in SUPPORTED_FLUIDS:
        return SUPPORTED_FLUIDS[key]
    CP.PropsSI("Tcrit", name)   # raises if unknown to CoolProp
    return name


# ===========================================================================
# Phase identifiers
# ===========================================================================

class Phase:
    LIQUID    = "liquid"
    TWO_PHASE = "two_phase"
    VAPOR     = "vapor"


# ===========================================================================
# FluidState — central data structure
# ===========================================================================

@dataclass
class FluidState:
    """
    Complete thermodynamic + transport + electrical state of the working
    fluid at one cross-section of the MPL loop.

    State variables (two independent variables suffice to define state):
        P  [Pa]      — absolute pressure
        h  [J/kg]    — specific enthalpy  (primary state variable, per VanGerner 2016)

    Property source priority (per property):
        1. CoolProp AbstractState (EOS-based, continuous)
        2. Empirical correlations  (Letsou-Stiel μ, Latini k — for organics)
        3. A1_TwoPhProp CSV tables (electrical conductivity, permittivity,
           and as fallback for σ, μ, k when neither CoolProp nor empirical
           correlations are available)

    Extended properties vs. original FluidState
    --------------------------------------------
    New fields added (all NaN when unavailable):
        elec_cond_l  — saturated liquid electrical conductivity [S/m]
        elec_cond_v  — saturated vapour electrical conductivity [S/m]
        eps_r_l      — saturated liquid relative permittivity [-]
        eps_r_v      — saturated vapour relative permittivity [-]
        elec_cond_tp — mixture electrical conductivity (quality-weighted) [S/m]
        eps_r_tp     — mixture relative permittivity (quality-weighted) [-]

    Usage
    -----
    >>> fs = FluidState.from_Ph("Acetone", P=300e3, h=250e3)
    >>> print(fs.T_C, "°C", "x =", fs.x)
    >>> print(fs.elec_cond_l)   # NaN if tables not found
    >>> print(fs.eps_r_l)
    """

    # ---- Fluid identity ----
    fluid: str

    # ---- Primary state variables ----
    P: float
    h: float

    # ---- Derived: thermodynamic ----
    T:      float = field(init=False)
    rho:    float = field(init=False)
    phase:  str   = field(init=False)
    x:      float = field(init=False)

    # ---- Derived: saturation ----
    T_sat:  float = field(init=False)
    h_l:    float = field(init=False)
    h_v:    float = field(init=False)
    rho_l:  float = field(init=False)
    rho_v:  float = field(init=False)
    h_fg:   float = field(init=False)

    # ---- Derived: transport ----
    mu:     float = field(init=False)
    mu_l:   float = field(init=False)
    mu_v:   float = field(init=False)
    mu_tp:  float = field(init=False)
    k:      float = field(init=False)
    k_l:    float = field(init=False)
    Pr:     float = field(init=False)
    Pr_l:   float = field(init=False)
    sigma:  float = field(init=False)
    cp:     float = field(init=False)
    cp_l:   float = field(init=False)

    # ---- Derived: void fraction ----
    alpha:  float = field(init=False)

    # ---- Derived: critical / reduced ----
    P_crit: float = field(init=False)
    T_crit: float = field(init=False)
    P_red:  float = field(init=False)

    # ---- NEW: electrical / dielectric (from A1_TwoPhProp tables) ----
    elec_cond_l:  float = field(init=False)   # liquid electrical conductivity [S/m]
    elec_cond_v:  float = field(init=False)   # vapour electrical conductivity [S/m]
    elec_cond_tp: float = field(init=False)   # mixture (quality-weighted) [S/m]
    eps_r_l:      float = field(init=False)   # liquid relative permittivity [-]
    eps_r_v:      float = field(init=False)   # vapour relative permittivity [-]
    eps_r_tp:     float = field(init=False)   # mixture (quality-weighted) [-]

    # ---- Property source tracking ----
    _prop_sources: dict = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self):
        self._compute()

    # ------------------------------------------------------------------
    # Internal: transport property retrieval with fallback chain
    # ------------------------------------------------------------------

    def _get_transport_sat(self, AS_liq: AbstractState, AS_vap: AbstractState):
        """
        Retrieve sat. liquid/vapour viscosity and conductivity.
        Fallback chain: CoolProp → empirical correlation → A1_TwoPhProp table.
        """
        f     = self.fluid
        T     = self.T_sat
        const = _FLUID_CONSTANTS.get(f, {})
        tk    = _coolprop_to_table_key(f)

        # ---- Liquid viscosity ----
        try:
            self.mu_l = AS_liq.viscosity()
            self._prop_sources['mu_l'] = 'CoolProp'
        except Exception:
            mu_l_table = _tables.get_prop_at_T(tk, T, 0.0,
                                                'ViscosityDyn_liq', 'ViscosityDyn_liq')
            if mu_l_table is not None and mu_l_table > 0:
                self.mu_l = mu_l_table
                self._prop_sources['mu_l'] = 'A1_table'
                warnings.warn(
                    f"{f}: liquid viscosity from A1_TwoPhProp tables", stacklevel=4)
            elif const:
                self.mu_l = _viscosity_liquid_Letsou_Stiel(
                    T, self.T_crit, self.P_crit, const["M"], const["omega"])
                self._prop_sources['mu_l'] = 'Letsou-Stiel'
                warnings.warn(
                    f"{f}: viscosity unavailable in CoolProp, "
                    f"using Letsou-Stiel correlation (~10% accuracy)", stacklevel=4)
            else:
                self.mu_l = float("nan")
                self._prop_sources['mu_l'] = 'unavailable'

        # ---- Vapour viscosity ----
        try:
            self.mu_v = AS_vap.viscosity()
            self._prop_sources['mu_v'] = 'CoolProp'
        except Exception:
            mu_v_table = _tables.get_prop_at_T(tk, T, 1.0,
                                                'ViscosityDyn_liq', 'ViscosityDyn_vap')
            if mu_v_table is not None and mu_v_table > 0:
                self.mu_v = mu_v_table
                self._prop_sources['mu_v'] = 'A1_table'
            else:
                # Engineering estimate: μ_v ≈ μ_l * 0.025 for organics near T_sat
                self.mu_v = self.mu_l * 0.025 if not _isnan(self.mu_l) else float("nan")
                self._prop_sources['mu_v'] = 'ratio-estimate'

        # ---- Liquid thermal conductivity ----
        try:
            self.k_l = AS_liq.conductivity()
            self._prop_sources['k_l'] = 'CoolProp'
        except Exception:
            k_l_table = _tables.get_prop_at_T(tk, T, 0.0,
                                               'ThConduc_liq', 'ThConduc_liq')
            if k_l_table is not None and k_l_table > 0:
                self.k_l = k_l_table
                self._prop_sources['k_l'] = 'A1_table'
                warnings.warn(
                    f"{f}: liquid conductivity from A1_TwoPhProp tables", stacklevel=4)
            elif const:
                self.k_l = _conductivity_liquid_Latini(
                    T, self.T_crit, const["T_b"], const["M"])
                self._prop_sources['k_l'] = 'Latini'
                warnings.warn(
                    f"{f}: thermal conductivity unavailable in CoolProp, "
                    f"using Latini correlation (~15% accuracy)", stacklevel=4)
            else:
                self.k_l = float("nan")
                self._prop_sources['k_l'] = 'unavailable'

    def _get_electrical_props(self, T_sat_K: float, x: float):
        """
        Retrieve electrical conductivity and relative permittivity from
        A1_TwoPhProp tables.  These properties are NOT available in CoolProp.
        Always NaN if tables not found or fluid not in table.
        """
        tk = _coolprop_to_table_key(self.fluid)

        # --- Electrical conductivity ---
        elec_l = _tables.get_prop_at_T(tk, T_sat_K, 0.0,
                                        'EleConduc_liq', 'EleConduc_liq')
        elec_v = _tables.get_prop_at_T(tk, T_sat_K, 1.0,
                                        'EleConduc_liq', 'EleConduc_vap')
        self.elec_cond_l = elec_l if elec_l is not None else float("nan")
        self.elec_cond_v = elec_v if elec_v is not None else float("nan")

        if not (_isnan(self.elec_cond_l) or _isnan(self.elec_cond_v)):
            self.elec_cond_tp = (self.elec_cond_l
                                 + x * (self.elec_cond_v - self.elec_cond_l))
            self._prop_sources['elec_cond'] = 'A1_table'
        else:
            self.elec_cond_tp = float("nan")
            self._prop_sources['elec_cond'] = 'unavailable'

        # --- Relative permittivity ---
        eps_l = _tables.get_prop_at_T(tk, T_sat_K, 0.0,
                                       'RelPermittivity_liq', 'RelPermittivity_liq')
        eps_v = _tables.get_prop_at_T(tk, T_sat_K, 1.0,
                                       'RelPermittivity_liq', 'RelPermittivity_vap')
        self.eps_r_l = eps_l if eps_l is not None else float("nan")
        self.eps_r_v = eps_v if eps_v is not None else float("nan")

        if not (_isnan(self.eps_r_l) or _isnan(self.eps_r_v)):
            self.eps_r_tp = self.eps_r_l + x * (self.eps_r_v - self.eps_r_l)
            self._prop_sources['eps_r'] = 'A1_table'
        else:
            self.eps_r_tp = float("nan")
            self._prop_sources['eps_r'] = 'unavailable'

    # ------------------------------------------------------------------
    # Internal: main computation
    # ------------------------------------------------------------------

    def _compute(self):
        """Populate all derived fields from (fluid, P, h)."""
        f = self.fluid
        P = self.P
        h = self.h

        self._prop_sources = {}

        # --- Critical properties ---
        self.P_crit = CP.PropsSI("Pcrit", f)
        self.T_crit = CP.PropsSI("Tcrit", f)
        self.P_red  = P / self.P_crit

        # --- Saturation properties via AbstractState ---
        AS_l = AbstractState("HEOS", f)
        AS_v = AbstractState("HEOS", f)
        AS_l.update(CP.PQ_INPUTS, P, 0.0)
        AS_v.update(CP.PQ_INPUTS, P, 1.0)

        self.T_sat = AS_l.T()
        self.h_l   = AS_l.hmass()
        self.h_v   = AS_v.hmass()
        self.rho_l = AS_l.rhomass()
        self.rho_v = AS_v.rhomass()
        self.h_fg  = self.h_v - self.h_l
        self.cp_l  = AS_l.cpmass()

        # --- Surface tension ---
        try:
            self.sigma = AS_l.surface_tension()
            self._prop_sources['sigma'] = 'CoolProp'
        except Exception:
            # Attempt table first
            tk = _coolprop_to_table_key(f)
            sigma_table = _tables.get_scalar_at_T(tk, self.T_sat, 'Surface_tension')
            if sigma_table is not None and sigma_table > 0:
                self.sigma = sigma_table
                self._prop_sources['sigma'] = 'A1_table'
            else:
                # Brock-Bird fallback
                T_r = self.T_sat / self.T_crit
                self.sigma = max(0.0132 * (1 - T_r)**1.222, 1e-4)
                self._prop_sources['sigma'] = 'Brock-Bird'

        # --- Transport properties ---
        self._get_transport_sat(AS_l, AS_v)

        # Prandtl (liquid)
        if self.mu_l > 0 and self.k_l > 0:
            self.Pr_l = self.mu_l * self.cp_l / self.k_l
        else:
            self.Pr_l = float("nan")

        # --- Phase determination ---
        if h <= self.h_l:
            # Subcooled liquid
            self.phase = Phase.LIQUID
            self.x     = float("nan")
            self.alpha = float("nan")
            AS_ph = AbstractState("HEOS", f)
            AS_ph.update(CP.HmassP_INPUTS, h, P)
            self.T   = AS_ph.T()
            self.rho = AS_ph.rhomass()
            self.cp  = AS_ph.cpmass()
            self.mu  = self.mu_l
            self.k   = self.k_l
            self.Pr  = self.Pr_l
            self.mu_tp = self.mu
            x_eff = 0.0   # for electrical props interpolation

        elif h >= self.h_v:
            # Superheated vapour
            self.phase = Phase.VAPOR
            self.x     = float("nan")
            self.alpha = float("nan")
            AS_ph = AbstractState("HEOS", f)
            AS_ph.update(CP.HmassP_INPUTS, h, P)
            self.T   = AS_ph.T()
            self.rho = AS_ph.rhomass()
            self.cp  = AS_ph.cpmass()
            self.mu  = self.mu_v
            self.k   = self.k_l * 0.04   # rough vapour conductivity estimate
            self.Pr  = self.mu * self.cp / self.k if self.k > 0 else float("nan")
            self.mu_tp = self.mu
            x_eff = 1.0

        else:
            # Two-phase saturated mixture (HEM)
            self.phase = Phase.TWO_PHASE
            self.x     = (h - self.h_l) / self.h_fg

            # HEM density (Dogan 1983, Eq. 4): 1/ρ_tp = x/ρ_v + (1-x)/ρ_l
            self.rho   = 1.0 / (self.x / self.rho_v + (1 - self.x) / self.rho_l)

            # Void fraction (homogeneous): α = 1 / (1 + (1-x)/x * ρ_v/ρ_l)
            self.alpha = 1.0 / (1.0 + (1 - self.x) / self.x * self.rho_v / self.rho_l)

            self.T   = self.T_sat
            self.mu  = self.mu_l
            self.k   = self.k_l
            self.cp  = self.cp_l
            self.Pr  = self.Pr_l

            # Cicchitti two-phase viscosity (Kim 2013 / Gholamreza 2016, Eq. 52)
            self.mu_tp = self.x * self.mu_v + (1 - self.x) * self.mu_l
            x_eff = self.x

        # --- Electrical / dielectric properties (table-only) ---
        self._get_electrical_props(self.T_sat, x_eff)

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_Ph(cls, fluid: str, P: float, h: float) -> "FluidState":
        """Create state from pressure [Pa] and enthalpy [J/kg]."""
        return cls(fluid=resolve_fluid_name(fluid), P=P, h=h)

    @classmethod
    def from_PT(cls, fluid: str, P: float, T: float) -> "FluidState":
        """Create state from pressure [Pa] and temperature [K] (single-phase only)."""
        f = resolve_fluid_name(fluid)
        h = CP.PropsSI("H", "P", P, "T", T, f)
        return cls(fluid=f, P=P, h=h)

    @classmethod
    def from_Px(cls, fluid: str, P: float, x: float) -> "FluidState":
        """Create state from pressure [Pa] and vapour quality [-]."""
        if not (0.0 <= x <= 1.0):
            raise ValueError(f"Quality x={x} out of [0, 1]")
        f = resolve_fluid_name(fluid)
        h = CP.PropsSI("H", "P", P, "Q", x, f)
        return cls(fluid=f, P=P, h=h)

    @classmethod
    def from_Tsat(cls, fluid: str, T_sat_C: float, x: float = 0.0) -> "FluidState":
        """Create state from saturation temperature [°C] and quality."""
        f = resolve_fluid_name(fluid)
        T = T_sat_C + 273.15
        P = CP.PropsSI("P", "T", T, "Q", 0, f)
        return cls.from_Px(f, P, x)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def T_C(self) -> float:
        """Temperature in Celsius."""
        return self.T - 273.15

    @property
    def T_sat_C(self) -> float:
        """Saturation temperature in Celsius."""
        return self.T_sat - 273.15

    @property
    def is_two_phase(self) -> bool:
        return self.phase == Phase.TWO_PHASE

    @property
    def is_liquid(self) -> bool:
        return self.phase == Phase.LIQUID

    @property
    def is_vapor(self) -> bool:
        return self.phase == Phase.VAPOR

    def subcooling(self) -> float:
        """ΔT_sub = T_sat - T [K]. Positive if subcooled liquid."""
        return self.T_sat - self.T

    def superheating(self) -> float:
        """ΔT_sup = T - T_sat [K]. Positive if superheated vapour."""
        return self.T - self.T_sat

    # ------------------------------------------------------------------
    # Downstream state helpers
    # ------------------------------------------------------------------

    def with_enthalpy(self, h_new: float) -> "FluidState":
        """Return new state at same pressure with updated enthalpy."""
        return FluidState(fluid=self.fluid, P=self.P, h=h_new)

    def with_pressure(self, P_new: float) -> "FluidState":
        """Return new state at same enthalpy with updated pressure."""
        return FluidState(fluid=self.fluid, P=P_new, h=self.h)

    # ------------------------------------------------------------------
    # Electrical property helpers (table access)
    # ------------------------------------------------------------------

    def has_electrical_props(self) -> bool:
        """True if electrical conductivity data are available from tables."""
        return not _isnan(self.elec_cond_l)

    def has_dielectric_props(self) -> bool:
        """True if relative permittivity data are available from tables."""
        return not _isnan(self.eps_r_l)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def summary(self) -> str:
        lines = [
            f"FluidState({self.fluid})",
            f"  Phase      : {self.phase}",
            f"  P          : {self.P/1e3:.2f} kPa",
            f"  T          : {self.T_C:.2f} °C",
            f"  h          : {self.h/1e3:.2f} kJ/kg",
            f"  ρ          : {self.rho:.3f} kg/m³",
        ]
        if self.is_two_phase:
            lines += [
                f"  x (quality): {self.x:.4f}",
                f"  α (void fr): {self.alpha:.4f}",
                f"  T_sat      : {self.T_sat_C:.2f} °C",
                f"  h_fg       : {self.h_fg/1e3:.2f} kJ/kg",
                f"  μ_tp (Cic) : {self.mu_tp*1e6:.2f} μPa·s",
            ]
        else:
            subcool = self.subcooling()
            superheat = self.superheating()
            if subcool > 0:
                lines.append(f"  ΔT_sub     : {subcool:.2f} K")
            elif superheat > 0:
                lines.append(f"  ΔT_sup     : {superheat:.2f} K")
            lines += [
                f"  μ          : {self.mu*1e6:.2f} μPa·s",
                f"  k          : {self.k:.4f} W/m·K",
                f"  Pr         : {self.Pr:.3f}",
            ]

        # Electrical / dielectric (only if available)
        if self.has_electrical_props():
            lines.append(f"  σ_e (liq)  : {self.elec_cond_l:.3e} S/m  [A1_table]")
        if self.has_dielectric_props():
            lines.append(f"  ε_r (liq)  : {self.eps_r_l:.4f}  [A1_table]")

        lines.append(f"  P_red      : {self.P_red:.4f}")

        # Source diagnostics (compact)
        if self._prop_sources:
            non_cp = {k: v for k, v in self._prop_sources.items() if v != 'CoolProp'}
            if non_cp:
                lines.append(f"  [fallbacks]: {non_cp}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"FluidState({self.fluid}, P={self.P/1e3:.1f} kPa, "
                f"T={self.T_C:.1f}°C, phase={self.phase})")
