"""
components/accumulator.py — Accumulator (Pressure Regulator) Model
===================================================================
MPL Simulation Library — Module 6b (Phase 6)

The accumulator is the pressure-regulating element of the MPL.  It acts as a
compressible buffer that absorbs or releases liquid to maintain a target system
pressure (and therefore saturation temperature).

Physical background
-------------------
In a two-phase loop the saturation pressure P_sat sets the evaporation
temperature T_sat = T_sat(P_sat).  Controlling P_sat therefore controls the
junction temperature of the electronics being cooled.

Two accumulator types are implemented  (VanGerner 2016, Truster 2024):

  HCA — Heat Controlled Accumulator
    * Contains a liquid/vapour mixture in thermodynamic equilibrium.
    * A heater (Pheat) boils liquid → raises pressure.
    * A cooling mantle (Pcool) condenses vapour → lowers pressure.
    * At SS the saturation state is set by the HCA temperature T_set.
    * Pressure: P_sys = P_sat(T_set)  (CoolProp saturation look-up)

  PCA — Pressure Controlled Accumulator
    * Contains only subcooled liquid; separated from an inert-gas (N2)
      bellows by a flexible membrane.
    * The N2 pressure P_gas is mechanically controlled (servo, manual).
    * At SS: P_sys ≈ P_gas_set  (liquid incompressible → P transmitted).
    * Liquid inventory: V_liquid changes as system fluid expands/contracts.
    * Gas: polytropic compression  P * V^n = const  (n ≈ 1.4 adiabatic,
      n = 1.0 isothermal; default 1.0 for slow SS operation).

Steady-state role in the loop
-------------------------------
The accumulator does NOT appear in the pressure-drop chain.  It is a
*boundary condition* that sets P_sys.  The loop solver (loop.py) uses:

    P_sys = accumulator.set_pressure()     → system saturation pressure [Pa]

The accumulator can also be placed in the liquid line (between condenser and
pump) to absorb liquid-volume changes.  In that position it does NOT affect
the enthalpy or mass flow through the main loop path.

Liquid inventory balance
------------------------
At SS the loop is closed:  m_total = m_loop + m_accu = const.
The accumulator liquid mass m_accu is implicitly determined by the loop
solver.  The Accumulator classes expose:

    liquid_mass(V_accu, P, x_accu) → float    [kg]
    volume_at_pressure(P_target)   → float    [m³]  (PCA only)

References
----------
[1] M. VanGerner et al., "1D dynamic model for CO2 two-phase loop,"
    ICES (2016).  [HCA + PCA models; fundamental]
[2] N. Truster et al., "PCA and MPC in MPL," Energies 17 (2024) 6347.
    [PCA with flexible bladder, R134a; control]
[3] J. Lee et al., "Accumulator effects on MPL instabilities,"
    Int. J. Heat Mass Transfer 198 (2022) 123394.
    [accumulator position vs PDO/PCI; Lee Eq. 12 gas-law]
[4] R. Kokate, PhD Thesis, 2024.  [stability interaction with accumulator]
[5] Middelhuis et al., "Review MPL experiments," (2024).
    [passive membrane accumulator; N2 + CO2; Eq. 11–12]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from fluid_properties import FluidState, resolve_fluid_name

# ---------------------------------------------------------------------------
# Shared helper: CoolProp saturation look-up
# ---------------------------------------------------------------------------

def _sat_pressure_from_T(fluid: str, T: float) -> float:
    """
    Return saturation pressure [Pa] at temperature T [K].

    Uses CoolProp directly via PropsSI.
    """
    import CoolProp.CoolProp as CP
    f = resolve_fluid_name(fluid)
    return float(CP.PropsSI("P", "T", T, "Q", 0, f))


def _sat_T_from_P(fluid: str, P: float) -> float:
    """Return saturation temperature [K] at pressure P [Pa]."""
    sat = FluidState.from_Px(fluid=fluid, P=P, x=0.0)
    return sat.T


def _liquid_density(fluid: str, P: float) -> float:
    """Return saturated liquid density [kg/m³] at pressure P."""
    sat = FluidState.from_Px(fluid=fluid, P=P, x=0.0)
    return sat.rho


# ---------------------------------------------------------------------------
# HCA — Heat Controlled Accumulator
# ---------------------------------------------------------------------------

@dataclass
class AccumulatorHCA:
    """
    Heat Controlled Accumulator (HCA).

    The HCA contains a liquid/vapour mixture in thermal equilibrium.
    Its temperature T_set sets the system saturation pressure:

        P_sys = P_sat(T_set)

    A heater (P_heat) and cooling mantle (P_cool) adjust T_set via
    active control (not modelled at SS; at SS T_set is prescribed).

    Parameters
    ----------
    fluid : str
        CoolProp fluid identifier (e.g. "Acetone").
    T_set : float
        Accumulator setpoint temperature [K].
        At SS this equals the system saturation temperature.
    V_total : float
        Total internal volume of the accumulator vessel [m³].
    x_accu : float
        Vapour quality inside the accumulator [-].
        Typically 0.2–0.5 at operating conditions.
        Does not affect pressure (HCA is isobaric at T_set).
    name : str
        Component label.

    Key outputs (after calling set_pressure / liquid_mass)
    -------------------------------------------------------
    P_sys         → system saturation pressure [Pa]
    T_sat         → saturation temperature [K]  (= T_set at SS)
    m_liquid      → liquid mass stored in accumulator [kg]
    m_vapour      → vapour mass stored [kg]

    Physics (VanGerner 2016, Section F)
    ------------------------------------
    The HCA controls pressure via phase change:
      - Heater submerged in liquid vaporises liquid → raises P (and T).
      - Cooling mantle at top condenses vapour → lowers P (and T).

    At SS:
        P_sys = P_sat(T_set)         [CoolProp look-up]
        ρ_l   = ρ_sat_liquid(P_sys)
        ρ_v   = ρ_sat_vapour(P_sys)
        m_l   = ρ_l * V_liquid
        m_v   = ρ_v * V_vapour
        V_liquid + V_vapour = V_total
        x_accu = m_v / (m_l + m_v)  → solve for V_liquid
    """

    fluid:    str
    T_set:    float
    V_total:  float
    x_accu:   float  = 0.3
    name:     str    = field(default="AccumulatorHCA")

    # ------------------------------------------------------------------ #
    #  Validation                                                          #
    # ------------------------------------------------------------------ #

    def __post_init__(self) -> None:
        if self.T_set <= 0:
            raise ValueError(f"T_set must be > 0 K; got {self.T_set}")
        if self.V_total <= 0:
            raise ValueError(f"V_total must be > 0 m³; got {self.V_total}")
        if not (0.0 <= self.x_accu <= 1.0):
            raise ValueError(f"x_accu must be in [0, 1]; got {self.x_accu}")

    # ------------------------------------------------------------------ #
    #  Primary interface                                                   #
    # ------------------------------------------------------------------ #

    def set_pressure(self) -> float:
        """
        Return the system saturation pressure [Pa] set by this HCA.

        This is the *boundary condition* imposed on the loop:
            P_sys = P_sat(T_set)

        Returns
        -------
        float
            System pressure [Pa].
        """
        return _sat_pressure_from_T(self.fluid, self.T_set)

    @property
    def P_sys(self) -> float:
        """System saturation pressure [Pa] (alias for set_pressure)."""
        return self.set_pressure()

    @property
    def T_sat(self) -> float:
        """System saturation temperature [K]  (= T_set at SS)."""
        return self.T_set

    # ------------------------------------------------------------------ #
    #  Liquid / vapour inventory                                           #
    # ------------------------------------------------------------------ #

    def fluid_inventory(self) -> dict:
        """
        Compute liquid and vapour masses inside the HCA at steady state.

        Returns
        -------
        dict with keys:
            P_sys      [Pa]
            T_sat      [K]
            rho_l      [kg/m³]
            rho_v      [kg/m³]
            V_liquid   [m³]
            V_vapour   [m³]
            m_liquid   [kg]
            m_vapour   [kg]
            m_total    [kg]
            x_accu     [-]
        """
        P = self.set_pressure()
        state_l = FluidState.from_Px(fluid=self.fluid, P=P, x=0.0)
        state_v = FluidState.from_Px(fluid=self.fluid, P=P, x=1.0)
        rho_l = state_l.rho
        rho_v = state_v.rho

        # Solve: x_accu = m_v / (m_l + m_v)
        # with V_l + V_v = V_total, m_l = rho_l*V_l, m_v = rho_v*V_v
        # → V_v = x_accu * rho_l * V_total / (rho_v + x_accu*(rho_l - rho_v))
        x = self.x_accu
        V_v = x * rho_l * self.V_total / (rho_v + x * (rho_l - rho_v))
        V_l = self.V_total - V_v
        m_l = rho_l * V_l
        m_v = rho_v * V_v

        return {
            "P_sys":    P,
            "T_sat":    self.T_sat,
            "rho_l":    rho_l,
            "rho_v":    rho_v,
            "V_liquid": V_l,
            "V_vapour": V_v,
            "m_liquid": m_l,
            "m_vapour": m_v,
            "m_total":  m_l + m_v,
            "x_accu":   x,
        }

    def liquid_mass(self) -> float:
        """Return liquid mass stored in HCA [kg]."""
        return self.fluid_inventory()["m_liquid"]

    # ------------------------------------------------------------------ #
    #  Setpoint adjustment                                                 #
    # ------------------------------------------------------------------ #

    def adjust_setpoint(self, T_new: float) -> None:
        """
        Update the HCA temperature setpoint.

        Parameters
        ----------
        T_new : float
            New target temperature [K].
        """
        if T_new <= 0:
            raise ValueError(f"T_new must be > 0 K; got {T_new}")
        self.T_set = T_new

    # ------------------------------------------------------------------ #
    #  Sensitivity                                                         #
    # ------------------------------------------------------------------ #

    def dP_dT(self) -> float:
        """
        Approximate dP_sat/dT at the current setpoint [Pa/K].

        Useful for control: how much does system pressure change per
        1 K change in HCA temperature?  Uses Clausius-Clapeyron.

        Returns
        -------
        float
            dP_sat/dT [Pa/K] — always positive for normal fluids.
        """
        dT = 0.1  # K perturbation
        P1 = _sat_pressure_from_T(self.fluid, self.T_set - dT / 2)
        P2 = _sat_pressure_from_T(self.fluid, self.T_set + dT / 2)
        return (P2 - P1) / dT

    def __repr__(self) -> str:
        P = self.set_pressure()
        return (
            f"AccumulatorHCA(fluid={self.fluid!r}, "
            f"T_set={self.T_set - 273.15:.1f} °C, "
            f"P_sys={P / 1e5:.3f} bar, "
            f"V_total={self.V_total * 1e6:.1f} cm³, "
            f"x_accu={self.x_accu:.2f})"
        )


# ---------------------------------------------------------------------------
# PCA — Pressure Controlled Accumulator
# ---------------------------------------------------------------------------

@dataclass
class AccumulatorPCA:
    """
    Pressure Controlled Accumulator (PCA) with inert-gas bladder.

    Contains subcooled liquid refrigerant separated from pressurised inert
    gas (typically N₂) by a flexible membrane or bladder.  The gas pressure
    P_gas is mechanically controlled and is transmitted directly to the liquid.

    System pressure:
        P_sys = P_gas_set     (liquid in accumulator is incompressible at SS)

    As loop fluid volume changes, the liquid volume in the accumulator
    changes and the gas is isothermally (or polytropically) compressed:

        P_gas * V_gas^n = P_prefill * V_prefill^n = const

    Parameters
    ----------
    fluid : str
        CoolProp fluid identifier.
    P_gas_set : float
        Target nitrogen-side pressure [Pa].
        At SS this equals the system pressure.
    V_total : float
        Total accumulator vessel volume [m³]  (liquid + gas).
    V_prefill : float
        Initial gas volume at prefill pressure [m³].
        Typically V_total (empty accumulator before liquid charging).
    P_prefill : float
        Prefill nitrogen pressure [Pa]  (before liquid enters the loop).
    n_polytropic : float
        Polytropic index [-].
        n = 1.0 → isothermal  (slow processes, default)
        n = 1.4 → adiabatic   (fast transients)
    name : str
        Component label.

    Physical model (Lee 2022, Middelhuis 2024, Eq. 11–12)
    -------------------------------------------------------
    At any operating state:
        P_gas * V_gas^n = P_prefill * V_prefill^n
        V_liquid = V_total - V_gas
        m_liquid = rho_l(P_sys) * V_liquid

    The SS model is queried as:
        P_sys = P_gas_set
        V_gas at operating point:
            V_gas = V_prefill * (P_prefill / P_gas_set)^(1/n)
        V_liquid = V_total - V_gas

    References: Truster (2024) §2, Lee (2022) Eqs. 11-12,
                Middelhuis (2024) Eqs. 11-12.
    """

    fluid:         str
    P_gas_set:     float
    V_total:       float
    V_prefill:     float
    P_prefill:     float
    n_polytropic:  float = 1.0
    name:          str   = field(default="AccumulatorPCA")

    def __post_init__(self) -> None:
        if self.P_gas_set <= 0:
            raise ValueError(f"P_gas_set must be > 0 Pa; got {self.P_gas_set}")
        if self.V_total <= 0:
            raise ValueError(f"V_total must be > 0 m³; got {self.V_total}")
        if self.V_prefill > self.V_total:
            raise ValueError(
                f"V_prefill ({self.V_prefill*1e6:.1f} cm³) > "
                f"V_total ({self.V_total*1e6:.1f} cm³)."
            )
        if self.P_prefill <= 0:
            raise ValueError(f"P_prefill must be > 0 Pa; got {self.P_prefill}")
        if self.n_polytropic <= 0:
            raise ValueError(f"n_polytropic must be > 0; got {self.n_polytropic}")

    # ------------------------------------------------------------------ #
    #  Primary interface                                                   #
    # ------------------------------------------------------------------ #

    def set_pressure(self) -> float:
        """
        Return the system pressure [Pa] imposed by this PCA.

        P_sys = P_gas_set  (gas pressure is mechanically prescribed).

        Returns
        -------
        float
            System pressure [Pa].
        """
        return self.P_gas_set

    @property
    def P_sys(self) -> float:
        """System pressure [Pa]."""
        return self.P_gas_set

    # ------------------------------------------------------------------ #
    #  Gas volume & liquid inventory                                       #
    # ------------------------------------------------------------------ #

    def gas_volume(self, P: Optional[float] = None) -> float:
        """
        Compute nitrogen gas volume [m³] at operating pressure P.

        Uses polytropic relation:
            V_gas = V_prefill * (P_prefill / P)^(1/n)

        Parameters
        ----------
        P : float, optional
            Operating gas pressure [Pa].  Defaults to P_gas_set.

        Returns
        -------
        float
            Gas volume [m³].
        """
        P = P or self.P_gas_set
        V_gas = self.V_prefill * (self.P_prefill / P) ** (1.0 / self.n_polytropic)
        if V_gas > self.V_total:
            raise ValueError(
                f"Gas volume {V_gas*1e6:.1f} cm³ exceeds vessel total "
                f"{self.V_total*1e6:.1f} cm³ at P = {P/1e5:.3f} bar. "
                "Accumulator is fully extended (no liquid inside)."
            )
        return V_gas

    def liquid_volume(self, P: Optional[float] = None) -> float:
        """Return liquid volume [m³] inside the PCA at pressure P."""
        return self.V_total - self.gas_volume(P)

    def fluid_inventory(self, P: Optional[float] = None) -> dict:
        """
        Compute liquid mass and volume inside the PCA.

        Parameters
        ----------
        P : float, optional
            Operating system pressure [Pa].  Defaults to P_gas_set.

        Returns
        -------
        dict with keys:
            P_sys      [Pa]
            V_gas      [m³]
            V_liquid   [m³]
            rho_l      [kg/m³]
            m_liquid   [kg]
        """
        P = P or self.P_gas_set
        V_gas = self.gas_volume(P)
        V_liq = self.V_total - V_gas
        # Liquid in PCA is subcooled (sat liquid approximation for density)
        rho_l = _liquid_density(self.fluid, P)
        m_liq = rho_l * V_liq
        return {
            "P_sys":    P,
            "V_gas":    V_gas,
            "V_liquid": V_liq,
            "rho_l":    rho_l,
            "m_liquid": m_liq,
        }

    def liquid_mass(self, P: Optional[float] = None) -> float:
        """Return liquid mass stored in PCA [kg]."""
        return self.fluid_inventory(P)["m_liquid"]

    # ------------------------------------------------------------------ #
    #  Pressure modulation                                                 #
    # ------------------------------------------------------------------ #

    def volume_at_pressure(self, P_target: float) -> float:
        """
        Return total liquid volume [m³] stored at a target pressure.

        Useful for loop-level mass balance: how much fluid must be in the
        loop if the accumulator is at P_target?

        Parameters
        ----------
        P_target : float
            Target system pressure [Pa].

        Returns
        -------
        float
            Liquid volume inside accumulator [m³].
        """
        return self.liquid_volume(P_target)

    def adjust_setpoint(self, P_new: float) -> None:
        """
        Update the gas-side pressure setpoint.

        Parameters
        ----------
        P_new : float
            New N₂ pressure [Pa].
        """
        if P_new <= 0:
            raise ValueError(f"P_new must be > 0 Pa; got {P_new}")
        self.P_gas_set = P_new

    # ------------------------------------------------------------------ #
    #  Sensitivity / compressibility                                       #
    # ------------------------------------------------------------------ #

    def effective_compressibility(self) -> float:
        """
        Effective compressibility of the PCA [m³/Pa].

        C_eff = dV_liquid / dP  (negative: liquid volume decreases as P rises)

        Derived from polytropic gas law:
            V_gas = V_prefill * (P_prefill / P)^(1/n)
            dV_gas/dP = -(1/n) * V_prefill * P_prefill^(1/n) * P^(-1/n - 1)
            dV_liquid/dP = -dV_gas/dP

        Returns
        -------
        float
            |C_eff| [m³/Pa] — always positive (liquid volume decreases with P).
        """
        P = self.P_gas_set
        n = self.n_polytropic
        dV_gas_dP = (
            -(1.0 / n)
            * self.V_prefill
            * (self.P_prefill ** (1.0 / n))
            * P ** (-1.0 / n - 1.0)
        )
        # dV_liquid / dP = -dV_gas / dP  → positive when P increases
        return abs(dV_gas_dP)

    def __repr__(self) -> str:
        V_gas = self.gas_volume()
        V_liq = self.liquid_volume()
        return (
            f"AccumulatorPCA(fluid={self.fluid!r}, "
            f"P_gas={self.P_gas_set/1e5:.3f} bar, "
            f"V_gas={V_gas*1e6:.1f} cm³, "
            f"V_liquid={V_liq*1e6:.1f} cm³, "
            f"V_total={self.V_total*1e6:.1f} cm³, "
            f"n={self.n_polytropic:.2f})"
        )
