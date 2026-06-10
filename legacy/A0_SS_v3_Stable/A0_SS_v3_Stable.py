# %%
# ============================================================================
# STEADY-STATE MODEL — v3.0
# A0_SS_v3_stable.py
# ============================================================================
"""
Steady-state two-phase loop simulator (v3.0).

Features:
  • Generic (Fujii,2004) geometry
  • Per-region inclination angles (theta1, theta2, theta3, theta4) [deg].
Notes:
  - Uses CoolProp for EOS; A1_TwoPhProp as fallback.
Last updated: 26 Sep 2025
"""
# ============================================================================
# 0) PREREQUISITES
# ============================================================================

# IMPORT REQUIRED LIBRARIES
import math  # Math library
import numpy as np  # for array manipulations and numerical operations
import CoolProp.CoolProp as Cp  # for thermodynamic property calculations
import matplotlib.pyplot as plt  # for visualization and plotting
import A1_TwoPhProp as twophprop  # to import properties
import time  # to measure time


# GLOBAL CONSTANTS AND SIMULATION PARAMETERS
g = 9.81  # [m/s^2] Gravitational acceleration
start_time = time.time()   # Time record start

# ============================================================================
# 1) GOVERNING EQUATIONS
# ============================================================================


def governing_mass(G_i_1, Ac_i, Ac_i_1):
    # G_i=G_i_1
    PastMassFlux = G_i_1*(Ac_i_1/Ac_i)
    CurrentMassFlux = PastMassFlux
    G_i = CurrentMassFlux
    return G_i


def governing_momentum(P_i_1, rho_i, R_r, f_i, G_i, dz_r, rho_i_1, theta_deg_r, Ac_i, Pw_i):
    PastPressure = P_i_1
    HidrostaticLoss = rho_i * g * (dz_r * sin_deg(theta_deg_r))
    ResistanceCoeff = R_r
    d_i = (4*Ac_i)/(Pw_i)
    WallFriction = (2 * f_i * (G_i**2)) / (d_i * rho_i) * dz_r
    FrictionLoss = ResistanceCoeff * WallFriction
    AccelerationLoss = (G_i**2) * ((1 / rho_i) - (1 / rho_i_1))
    CurrentPressure = PastPressure - HidrostaticLoss - FrictionLoss - AccelerationLoss
    P_i = CurrentPressure
    return P_i


def governing_energy(h_i_1, dQdz_i, dz_r, G_i, Ac_i):
    # h_i=h_i_1+(dQ_dz*dz_i)/G_i*Ac_i
    PastEnthalpy = h_i_1
    EnergyTransferred = dQdz_i*dz_r
    MassFlow = G_i*Ac_i
    EnthalpyDelta = EnergyTransferred/MassFlow
    CurrentEnthalpy = PastEnthalpy+EnthalpyDelta
    h_i = CurrentEnthalpy
    return h_i

# ============================================================================
# 2) CONSTITUTIVE EQUATIONS (closures: friction, HTC, void/slip, wall T, etc.)
# ============================================================================


def actual_quality(h_i, h_l, h_v):
    x_i = (h_i-h_l)/(h_v-h_l)
    if x_i >= 0 and x_i <= 1:
        x_i = x_i
    elif x_i > 1:
        x_i = 1
    else:
        x_i = 0

    return x_i


def void_fraction(x_i, rho_l, rho_v):
    psi_i = (x_i/rho_v)/((x_i/rho_v)+((1-x_i)/rho_l))
    return psi_i


def rho_mixture(x_i, rho_l, rho_v):
    rho_i = (rho_v)/(x_i+((1-x_i)*(rho_v/rho_l)))
    return rho_i


def homogeneous_velocity(G_i, rho_i):
    u_i = G_i/rho_i
    return u_i


def f_term_singlephase(rho, u_i, mu, Ac_i, Pw_i):
    d_i = (4*Ac_i)/(Pw_i)
    f_term_i = 0.079*(((rho*u_i*d_i)/(mu))**(-0.25))
    return f_term_i


def friction_factor(psi_i, rho_l, rho_v, rho_i, f_l, f_v):
    f_i = ((1-psi_i)*(rho_l/rho_i)*(f_l))+((psi_i)*(rho_v/rho_i)*(f_v))
    return f_i


def alpha_boiling(i):
    """
    Return total HTC for flow boiling at cell i (convective + nucleate).
    - Reads local state from global arrays (G_vec, x_vec, P_vec, T_vec).
    - Uses EOS_liq_properties / EOS_vap_properties for fluid properties.
    - Uses CoolProp only for Psat(T) and Tcrit (no helper provided).
    - Does not write any global array; returns alpha_total [W/m^2/K].
    """
    # --- Local state from global arrays ---
    G = G_vec[i]
    x = float(np.clip(x_vec[i], 0.0, 1.0))
    P = P_vec[i]
    T = T_vec[i]

    # --- Saturated liquid/vapor properties at local P (via EOS helpers) ---
    h_l, _, rho_l, mu_l, k_l, cp_l, sigma = EOS_liq_properties(T, P, fluid)
    h_v, _, rho_v, mu_v, k_v, cp_v = EOS_vap_properties(T, P, fluid)

    # Defensive clamps (avoid zero/NaN in transport/thermo)
    k_l = max(k_l if np.isfinite(k_l) else 0.0,  1e-9)
    mu_l = max(mu_l if np.isfinite(mu_l) else 0.0, 1e-12)
    cp_l = max(cp_l if np.isfinite(cp_l) else 0.0, 1e-6)
    sigma = max(sigma if np.isfinite(sigma) else 0.0, 1e-9)

    # Latent heat (fallback to CoolProp if needed; last resort avoids zero)
    if (h_l is None) or (h_v is None) or (not np.isfinite(h_l)) or (not np.isfinite(h_v)):
        try:
            h_l = Cp.PropsSI('H', 'P', P, 'Q', 0, fluid)
            h_v = Cp.PropsSI('H', 'P', P, 'Q', 1, fluid)
        except Exception:
            h_l, h_v = 0.0, 1.0
    h_lv = max(h_v - h_l, 1e-6)

    # --- Homogeneous mixture density and velocity ---
    rho_m = rho_mixture(x, rho_l, rho_v)
    u = homogeneous_velocity(G, rho_m)

    # --- Convective HTC (liquid and vapor at mixture velocity, Dittus–Boelter) ---
    Re_l = rho_l * u * d / max(mu_l, 1e-12)
    Pr_l = (cp_l * mu_l) / k_l
    alpha_l = 0.023 * (Re_l ** 0.8) * (Pr_l ** 0.4) * k_l / d

    mu_v_ = max(mu_v if np.isfinite(mu_v) else 0.0, 1e-12)
    k_v_ = max(k_v if np.isfinite(k_v) else 0.0, 1e-9)
    cp_v_ = max(cp_v if np.isfinite(cp_v) else 0.0, 1e-6)
    Re_v = rho_v * u * d / mu_v_
    Pr_v = (cp_v_ * mu_v_) / k_v_
    alpha_v = 0.023 * (Re_v ** 0.8) * (Pr_v ** 0.4) * k_v_ / d

    psi = void_fraction(x, rho_l, rho_v)
    alpha_conv = (1.0 - psi) * alpha_l + psi * alpha_v

    # --- Microconvective shape factor (user form) ---
    S = 1.0 if x <= 0.3 else (60.0 / 49.0) * (x - 1.0) ** 2 + 0.4

    # --- Local saturation temperature and ΔT bounds (stay away from Tcrit) ---
    try:
        Tsat = Cp.PropsSI('T', 'P', P, 'Q', 0, fluid)
    except Exception:
        Tsat = T
    try:
        Tcrit = Cp.PropsSI('Tcrit', fluid)
    except Exception:
        Tcrit = Tsat + 1e3
    dT_cap = max(5.0, 0.30 * (Tcrit - Tsat))
    dT_lo, dT_hi = 0.0, dT_cap

    # --- Segment wall area and segment heat (read dQ_dz, dz from current loop scope) ---
    As = math.pi * d * dz      # wall area of cell i
    Qseg = dQ_dz * dz            # heat added to the segment (can be +/-)

    # --- Nucleate boiling HTC as a function of wall superheat ΔT ---
    def alpha_b_of_dT(dT_local: float) -> float:
        dT_local = max(float(dT_local), 0.0)
        Tw = Tsat + min(dT_local, dT_cap)
        try:
            Psat_Tw = Cp.PropsSI('P', 'T', Tw, 'Q', 0, fluid)
        except Exception:
            return np.nan
        dP = max(Psat_Tw - P, 0.0)
        num = (k_l ** 0.79) * (cp_l ** 0.45) * (rho_l ** 0.49) * (g ** 0.25)
        den = (sigma ** 0.25) * (mu_l ** 0.29) * \
            (h_lv ** 0.24) * max(rho_v, 1e-9)
        return 0.00122 * (num / max(den, 1e-30)) * (dT_local ** 0.24) * (dP ** 0.75) * S

    # --- Damped fixed-point iteration for ΔT (no wall temperature stored here) ---
    dT = min(10.0, dT_cap)  # initial guess [K]
    lam = 0.30               # damping factor
    for _ in range(60):
        ab = alpha_b_of_dT(dT)
        if not np.isfinite(ab):
            break
        alpha_tot = alpha_conv + ab
        if alpha_tot <= 0.0:
            break
        dT_model = Qseg / (alpha_tot * As)          # energy balance closure
        dT_new = (1.0 - lam) * dT + lam * dT_model
        dT_new = min(max(dT_new, dT_lo), dT_hi)   # keep within safe bounds
        if abs(dT_new - dT) <= 1e-1:                # 0.1 K tolerance
            dT = dT_new
            break
        dT = dT_new

    ab_final = alpha_b_of_dT(dT)
    if (not np.isfinite(ab_final)) or (ab_final < 0.0):
        ab_final = 0.0

    alpha_total = alpha_conv + ab_final
    return float(max(alpha_total, 1.0))  # numerical floor


def alpha_condensation(i, selected_correlation):
    # 1 - Chen style modified for condensation
    # 2 - Shah 197 (modified in 2022)
    if selected_correlation == 1:
        """
        Chen condensation HTC inside smooth tubes (compact, self-contained).
        ---------------------------------------
        - Baseline single-phase (liquid-side) convection: h_lo
          * Turbulent: Gnielinski with Blasius (Darcy) f for smooth tubes:
              f_D = 0.3164 * Re^(-0.25)
              Nu_Gnielinski = (f_D/8) * (Re - 1000) * Pr / [1 + 12.7 * (f_D/8)^(1/2) * (Pr^(2/3) - 1)]
          * Laminar fallback: Nu = 3.66 (fully-developed, constant wall T)
          * Safety fallback: Dittus–Boelter Nu = 0.023 * Re^0.8 * Pr^0.4
        - Chen-style factors (as provided by the user):
            E = 0.00122 * ((G^2 * D) / (rho_l * sigma))^0.5          (enhancement)
            S = 1 / (1 + 2.53e-6 * G^1.17 * x^1.17 / (rho_l^0.5 * sigma^0.25))  (suppression)
          Final HTC:
            h_tp = h_lo * (S + E)
        """
        # --- Update to local indexed values ---
        G = G_vec[i]
        x = x_vec[i]
        P = P_vec[i]
        T = T_vec[i]
        # --- Saturated liquid/vapor properties at local pressure ---
        h_l, _, rho_l, mu_l, k_l, cp_l, sigma = EOS_liq_properties(T, P, fluid)
        _,   _, rho_v, mu_v, k_v, cp_v = EOS_vap_properties(T, P, fluid)
        # --- Defensive checks and clamps ---
        x = float(np.clip(x, 0.0, 1.0))
        k_l = max(k_l,  1e-9)
        mu_l = max(mu_l, 1e-12)
        cp_l = max(cp_l, 1e-6)
        sigma = max(sigma, 1e-9)
        # --- Liquid-side Reynolds & Prandtl numbers ---
        Re_lo = G * d / mu_l
        Pr_l = (cp_l * mu_l) / k_l
        # --- Baseline convective HTC (liquid side) ---
        if Re_lo < 2300.0:
            # Laminar, fully-developed, constant wall T (simple fallback)
            Nu_lo = 3.66
        else:
            # Gnielinski with Blasius (Darcy) friction factor for smooth tubes
            f_D = 0.3164 * (Re_lo ** -0.25)
            denom = 1.0 + 12.7 * ((f_D / 8.0) ** 0.5) * \
                ((Pr_l ** (2.0/3.0)) - 1.0)
            Nu_lo = (f_D / 8.0) * (Re_lo - 1000.0) * Pr_l / max(denom, 1e-12)
            # Safety: if Gnielinski misbehaves, fallback to Dittus–Boelter
            if (not np.isfinite(Nu_lo)) or (Nu_lo <= 0.0):
                Nu_lo = 0.023 * (Re_lo ** 0.8) * (Pr_l ** 0.4)
        h_lo = Nu_lo * k_l / d  # [W/m^2/K]
        # --- Chen Correlation (user-supplied forms) ---
        # Enhancement factor E (dimensionless)
        E = 0.00122 * (((G**2) * d) / (rho_l * sigma)) ** 0.5
        # Suppression factor S (dimensionless)
        S = 1.0 / (1.0 + 2.53e-6 * (G ** 1.17) * (x ** 1.17) /
                   ((rho_l ** 0.5) * (sigma ** 0.25)))
        # --- Final two-phase HTC ---
        h_tp = h_lo * (S + E)

    # ----------------------- Shah correlation -------------------------------
    elif selected_correlation == 2:
        """
        Shah (2021) condensation HTC at cell i (tube flow).
        - Reads local G, x, P, T from global arrays.
        - Uses EOS_liq_properties for saturated liquid properties at P.
        - Returns total two-phase HTC [W/m^2/K]; no side effects.
        Model:
          1) Single-phase liquid baseline (turbulent DB / laminar 3.66):
               Re_lo = G*D/mu_l,  Pr_l = cp_l*mu_l/k_l
               h_lo  = (0.023*Re_lo^0.8*Pr_l^0.4)*(k_l/D)   [if Re_lo>=2300]
                       else (Nu=3.66)*(k_l/D)
          2) Shah enhancement:
               Fr_lo = G^2 / (rho_l^2 * g * D)
               E     = 1 + 3.8 * x^0.76 * (1-x)^0.04 / Fr_lo^0.38
          3) h_tp = h_lo * E
        """
        # --- Local state from global arrays ---
        G = G_vec[i]
        x = float(np.clip(x_vec[i], 0.0, 1.0))
        P = P_vec[i]
        T = T_vec[i]
        # --- Saturated liquid properties at P (EOS helper only) ---
        _h_l, _s_l, rho_l, mu_l, k_l, cp_l, _sigma = EOS_liq_properties(
            T, P, fluid)
        # Defensive clamps
        rho_l = max(rho_l if np.isfinite(rho_l) else 0.0, 1e-6)
        mu_l = max(mu_l if np.isfinite(mu_l) else 0.0, 1e-12)
        k_l = max(k_l if np.isfinite(k_l) else 0.0, 1e-9)
        cp_l = max(cp_l if np.isfinite(cp_l) else 0.0, 1e-6)
        # --- Baseline single-phase liquid HTC (DB / laminar fallback) ---
        Re_lo = (G * d) / mu_l
        Pr_l = (cp_l * mu_l) / k_l
        if Re_lo >= 2300.0:
            Nu_lo = 0.023 * (Re_lo ** 0.8) * (Pr_l ** 0.4)
        else:
            Nu_lo = 3.66  # fully-developed laminar, constant wall T
        h_lo = (Nu_lo * k_l) / d
        # --- Froude number and Shah enhancement ---
        Fr_lo = (G * G) / (rho_l * rho_l * g * d)
        Fr_lo = max(Fr_lo, 1e-12)  # avoid division by zero
        E = 1.0 + 3.8 * (x ** 0.76) * ((1.0 - x) ** 0.04) / (Fr_lo ** 0.38)
        # --- Final HTC Shah ---
        h_tp = h_lo * E
    # # ----------------------- Other correlation -------------------------------
    # elif selected_correlation == 3:
        # h_tp = 1
    # ------ Numerical floor for calculated htp -------
    if (not np.isfinite(h_tp)) or (h_tp <= 0.0):
        h_tp = max(h_lo, 1.0)

    return float(h_tp)

# ============================================================================
# 3) EQUATION-OF-STATE (EOS) & THERMOPHYSICAL PROPERTIES
# ============================================================================


def EOS_liq_properties(T, P, fluid):  # 7 output properties
    try:
        h_l = Cp.PropsSI('H', 'P', P, 'Q', 0, fluid)  # Enthalpy [J/kg]
    except Exception:
        try:
            h_l = twophprop.get_Enthalpy(fluid, T, 0)
        except Exception as e:
            print(
                f"Warning: Could not retrieve enthalpy for {fluid} at T={T}K, P={P}Pa: {e}")
            h_l = None

    try:
        s_l = Cp.PropsSI('S', 'P', P, 'Q', 0, fluid)  # Entropy [J/kg.K]
    except Exception:
        try:
            s_l = twophprop.get_Entropy(fluid, T, 0)
        except Exception as e:
            print(
                f"Warning: Could not retrieve entropy for {fluid} at T={T}K, P={P}Pa: {e}")
            s_l = None

    try:
        rho_l = Cp.PropsSI('D', 'P', P, 'Q', 0, fluid)  # Density [kg/m^3]
    except Exception:
        try:
            rho_l = twophprop.get_Density(fluid, T, 0)
        except Exception as e:
            print(
                f"Warning: Could not retrieve density for {fluid} at T={T}K, P={P}Pa: {e}")
            rho_l = None

    try:
        mu_l = Cp.PropsSI('V', 'P', P, 'Q', 0, fluid)  # Viscosity [Pa·s]
    except Exception:
        try:
            mu_l = twophprop.get_ViscosityDynamic(fluid, T, 0)
        except Exception as e:
            print(
                f"Warning: Could not retrieve viscosity for {fluid} at T={T}K, P={P}Pa: {e}")
            mu_l = None

    try:
        # Thermal conductivity [W/m·K]
        k_l = Cp.PropsSI('L', 'P', P, 'Q', 0, fluid)
    except Exception:
        try:
            k_l = twophprop.get_ThermalConductivity(fluid, T, 0)
        except Exception as e:
            print(
                f"Warning: Could not retrieve thermal conductivity for {fluid} at T={T}K, P={P}Pa: {e}")
            k_l = None

    try:
        cp_l = Cp.PropsSI('C', 'P', P, 'Q', 0, fluid)  # Specific heat [J/kg·K]
    except Exception:
        try:
            cp_l = twophprop.get_SpecificHeat(fluid, T, 0)
        except Exception as e:
            print(
                f"Warning: Could not retrieve specific heat for {fluid} at T={T}K, P={P}Pa: {e}")
            cp_l = None

    try:
        sigma = Cp.PropsSI('I', 'P', P, 'Q', 0, fluid)  # Surface tension [N/m]
    except Exception:
        try:
            sigma = Cp.PropsSI('I', 'T', T, 'Q', 0, fluid)
        except Exception:
            try:
                sigma = twophprop.get_SurfaceTension(fluid, T)
            except Exception as e:
                print(
                    f"Warning: Could not retrieve surface tension for {fluid} at T={T}K, P={P}Pa: {e}")
                sigma = None

    return h_l, s_l, rho_l, mu_l, k_l, cp_l, sigma


def EOS_vap_properties(T, P, fluid):  # 6 output properties
    try:
        h_v = Cp.PropsSI('H', 'P', P, 'Q', 1, fluid)  # Enthalpy [J/kg]
    except Exception:
        try:
            h_v = twophprop.get_Enthalpy(fluid, T, 1)
        except Exception as e:
            print(
                f"Warning: Could not retrieve enthalpy for {fluid} at T={T}K, P={P}Pa: {e}")
            h_v = None

    try:
        s_v = Cp.PropsSI('S', 'P', P, 'Q', 1, fluid)  # Entropy [J/kg.K]
    except Exception:
        try:
            s_v = twophprop.get_Entropy(fluid, T, 1)
        except Exception as e:
            print(
                f"Warning: Could not retrieve entropy for {fluid} at T={T}K, P={P}Pa: {e}")
            s_v = None

    try:
        rho_v = Cp.PropsSI('D', 'P', P, 'Q', 1, fluid)  # Density [kg/m^3]
    except Exception:
        try:
            rho_v = twophprop.get_Density(fluid, T, 1)
        except Exception as e:
            print(
                f"Warning: Could not retrieve density for {fluid} at T={T}K, P={P}Pa: {e}")
            rho_v = None

    try:
        mu_v = Cp.PropsSI('V', 'P', P, 'Q', 1, fluid)  # Viscosity [Pa·s]
    except Exception:
        try:
            mu_v = twophprop.get_ViscosityDynamic(fluid, T, 1)
        except Exception as e:
            print(
                f"Warning: Could not retrieve viscosity for {fluid} at T={T}K, P={P}Pa: {e}")
            mu_v = None

    try:
        # Thermal conductivity [W/m·K]
        k_v = Cp.PropsSI('L', 'P', P, 'Q', 1, fluid)
    except Exception:
        try:
            k_v = twophprop.get_ThermalConductivity(fluid, T, 1)
        except Exception as e:
            print(
                f"Warning: Could not retrieve thermal conductivity for {fluid} at T={T}K, P={P}Pa: {e}")
            k_v = None

    try:
        cp_v = Cp.PropsSI('C', 'P', P, 'Q', 1, fluid)  # Specific heat [J/kg·K]
    except Exception:
        try:
            cp_v = twophprop.get_SpecificHeat(fluid, T, 1)
        except Exception as e:
            print(
                f"Warning: Could not retrieve specific heat for {fluid} at T={T}K, P={P}Pa: {e}")
            cp_v = None

    return h_v, s_v, rho_v, mu_v, k_v, cp_v


# ============================================================================
# 4) REGION FUNCTIONS
# ============================================================================
def function_conservation(dQdz_i, dz_r, i, R_r, theta_deg_r, G_i_1, Ac_i, Ac_i_1, Pw_i):
    # Ac = np.pi * (d**2) / 4  # [m2]
    # governing_mass(G_i_1, Ac_i, Ac_i_1):
    # governing_momentum(P_i_1, rho_i, R_r, f_i, G_i, dz_r, rho_i_1, theta_deg_r, Ac_i):
    # governing_energy(h_i_1, dQdz_i, dz_r, G_i, Ac_i):

    G_vec[i] = governing_mass(G_i_1, Ac_i, Ac_i_1)
    h_vec[i] = governing_energy(h_vec[i-1], dQdz_i, dz_r, G_vec[i], Ac_i)

    # Provisional step
    T_prov1 = Cp.PropsSI('T', 'H', h_vec[i], 'P', P_vec[i-1], fluid)
    h_l_prov1, _, rho_l_prov1, mu_l_prov1, _, _, _ = EOS_liq_properties(
        T_prov1, P_vec[i-1], fluid)
    h_v_prov1, _, rho_v_prov1, mu_v_prov1, _, _ = EOS_vap_properties(
        T_prov1, P_vec[i-1], fluid)
    x_prov1 = actual_quality(h_vec[i], h_l_prov1, h_v_prov1)
    psi_prov1 = void_fraction(x_prov1, rho_l_prov1, rho_v_prov1)
    rho_m_prov1 = rho_mixture(x_prov1, rho_l_prov1, rho_v_prov1)
    u_prov1 = homogeneous_velocity(G_vec[i], rho_m_prov1)
    f_l_prov1 = f_term_singlephase(
        rho_l_prov1, u_prov1, mu_l_prov1, Ac_i, Pw_i)
    f_v_prov1 = f_term_singlephase(
        rho_v_prov1, u_prov1, mu_v_prov1, Ac_i, Pw_i)
    f_i_prov1 = friction_factor(
        psi_prov1, rho_l_prov1, rho_v_prov1, rho_m_prov1, f_l_prov1, f_v_prov1)
    P_prov = governing_momentum(
        P_vec[i-1], rho_m_prov1, R_r, f_i_prov1, G_vec[i], dz_r, rho_vec[i-1], theta_deg_r, Ac_i, Pw_i)

    # Refresh step
    T_prov2 = Cp.PropsSI('T', 'H', h_vec[i], 'P', P_prov, fluid)
    h_l_prov2, _, rho_l_prov2, mu_l_prov2, _, _, _ = EOS_liq_properties(
        T_prov2, P_prov, fluid)
    h_v_prov2, _, rho_v_prov2, mu_v_prov2, _, _ = EOS_vap_properties(
        T_prov2, P_prov, fluid)
    x_prov2 = actual_quality(h_vec[i], h_l_prov2, h_v_prov2)
    psi_prov2 = void_fraction(x_prov2, rho_l_prov2, rho_v_prov2)
    rho_m_prov2 = rho_mixture(x_prov2, rho_l_prov2, rho_v_prov2)
    u_prov2 = homogeneous_velocity(G_vec[i], rho_m_prov2)
    f_l_prov2 = f_term_singlephase(
        rho_l_prov2, u_prov2, mu_l_prov2, Ac_i, Pw_i)
    f_v_prov2 = f_term_singlephase(
        rho_v_prov2, u_prov2, mu_v_prov2, Ac_i, Pw_i)
    f_i_prov2 = friction_factor(
        psi_prov2, rho_l_prov2, rho_v_prov2, rho_m_prov2, f_l_prov2, f_v_prov2)

    # Final value
    P_vec[i] = governing_momentum(
        P_vec[i-1], rho_m_prov2, R_r, f_i_prov2, G_vec[i], dz_r, rho_vec[i-1], theta_deg_r, Ac_i, Pw_i)
    T_vec[i] = Cp.PropsSI('T', 'H', h_vec[i], 'P', P_vec[i], fluid)
    h_l, _, rho_l, _, _, _, _ = EOS_liq_properties(T_vec[i], P_vec[i], fluid)
    h_v, _, rho_v, _, _, _ = EOS_vap_properties(T_vec[i], P_vec[i], fluid)
    x_vec[i] = actual_quality(h_vec[i], h_l, h_v)
    psi_vec[i] = void_fraction(x_vec[i], rho_l, rho_v)
    rho_vec[i] = rho_mixture(x_vec[i], rho_l, rho_v)
    u_vec[i] = homogeneous_velocity(G_vec[i], rho_vec[i])

    return h_vec[i], P_vec[i], T_vec[i], x_vec[i], psi_vec[i], rho_vec[i], u_vec[i], h_l


def wall_temperature(T_i, dQdz_r, dz_r, alpha_i, As_i):
    FluidTemperature = T_i
    EnergyTransferred = dQdz_r*dz_r
    ThermalConductance = alpha_i*As_i
    WallTemperature = FluidTemperature+(EnergyTransferred/ThermalConductance)
    T_w_i = WallTemperature
    return T_w_i

# ============================================================================
# 5) AUXILIAR/NUMERIC FUNCTIONS
# ============================================================================
def measure_region_dP(r: int) -> float:
    """Read ΔP for region r using current arrays after running region r."""
    if r == 0:
        i_start = N0+1; i_end = N1
        Pin = P_vec[N0]
    elif r == 1:
        i_start = N1+1; i_end = N2
        Pin = P_vec[N1]
    elif r == 2:
        i_start = N2+1; i_end = N3
        Pin = P_vec[N2]
    elif r == 3:
        i_start = N3+1; i_end = N4
        Pin = P_vec[N3]
    else:
        raise ValueError("bad region index")
    return float(Pin - P_vec[i_end])  # sign as per your convention

def solve_R_for_region(
    r: int,
    dP_target: float,
    tol: float = 50.0,
    R_lo: float = 0.0,
    R_hi_init: float = 4.0,     # small starting hi, we’ll expand as needed
    R_cap: float = 1e3,         # hard safety cap for R*
    max_expand: int = 12,       # expansions (doublings) allowed
    min_growth: float = 5.0,    # [Pa] – treat ΔP growth < this as “no progress”
    stall_hits: int = 3,        # consecutive “no progress” hits => saturation
    max_iter: int = 50
) -> float:
    """
    Robustly find R* so that ΔP_region(R*) ≈ dP_target.
    Adds feasibility checks, adaptive bracket expansion, and saturation detection.
    """

    def eval_dp(Rtrial: float) -> float:
        R_vec[r] = Rtrial
        region_runners[r]()              # run just this region with current R*
        return measure_region_dP(r)

    # 0) Base evaluations
    dP_lo = eval_dp(R_lo)

    # Quick success
    if abs(dP_lo - dP_target) <= tol:
        return R_lo

    # 1) Find a reasonable high bound (start small)
    R_hi = R_hi_init
    dP_hi = eval_dp(R_hi)

    # If slope is tiny already, try a bigger step to estimate sensitivity
    if dP_hi <= dP_lo + min_growth:
        R_hi = max(2.0 * R_hi, 1.0)
        dP_hi = eval_dp(R_hi)

    # Optional: slope-based initial guess to speed things up
    if dP_hi > dP_lo + 1e-6:
        slope = (dP_hi - dP_lo) / (R_hi - R_lo)
        R_guess = R_lo + (dP_target - dP_lo) / slope
        if R_guess > R_lo and R_guess < R_cap:
            # try a targeted guess and keep the best side for bracketing
            dP_guess = eval_dp(R_guess)
            # choose (lo, hi) around the target
            if (dP_lo - dP_target) * (dP_guess - dP_target) <= 0:
                R_hi, dP_hi = R_guess, dP_guess
            elif (dP_guess - dP_target) * (dP_hi - dP_target) <= 0:
                R_lo, dP_lo = R_guess, dP_guess

    # 2) Adaptive expansion to bracket the target
    stalls = 0
    expands = 0
    while (dP_lo - dP_target) * (dP_hi - dP_target) > 0:
        if dP_target > dP_hi:
            # need higher ΔP -> increase R_hi
            R_next = min(2.0 * R_hi, R_cap)
            if R_next == R_hi:
                # hit cap
                raise RuntimeError(
                    f"[R{r+1}] Unreachable target: ΔP_target={dP_target:.1f} Pa, "
                    f"ΔP(0)={dP_lo:.1f} Pa, ΔP(R_cap={R_cap})={dP_hi:.1f} Pa."
                )
            dP_next = eval_dp(R_next)

            # Saturation detection
            if dP_next <= dP_hi + min_growth:
                stalls += 1
                if stalls >= stall_hits:
                    raise RuntimeError(
                        f"[R{r+1}] ΔP saturates with R*: cannot reach target "
                        f"(ΔP ≈ {dP_next:.1f} Pa at R*={R_next:.2f})."
                    )
            else:
                stalls = 0

            R_hi, dP_hi = R_next, dP_next

        else:
            # target is below dP_lo (rare if R_lo=0). Reduce R_hi toward R_lo.
            R_hi = 0.5 * (R_lo + R_hi)
            dP_hi = eval_dp(R_hi)

        expands += 1
        if expands > max_expand:
            raise RuntimeError(
                f"[R{r+1}] Could not bracket target after {max_expand} expansions. "
                f"ΔP(0)={dP_lo:.1f} Pa, ΔP({R_hi:.2f})={dP_hi:.1f} Pa, target={dP_target:.1f} Pa."
            )

    # 3) Bisection within bracket
    for _ in range(max_iter):
        R_mid = 0.5 * (R_lo + R_hi)
        dP_mid = eval_dp(R_mid)
        err = dP_mid - dP_target
        if abs(err) <= tol:
            return R_mid
        if (dP_lo - dP_target) * (err) <= 0:
            R_hi, dP_hi = R_mid, dP_mid
        else:
            R_lo, dP_lo = R_mid, dP_mid

    # Fall-back return (should be within tolerance or very close)
    return 0.5 * (R_lo + R_hi)


def calibrate_R_stars(targets: dict, tol: float = 50.0, fixed_R: dict | None = None):
    """
    Calibrate R* for regions according to 'targets' dictionary.

    targets = {region_index: ΔP_target or None}
      None  -> free run (R* = 1.0)
      float -> calibrate to match ΔP_target

    fixed_R = {region_index: R_star}
      Force a given R* and skip calibration for those regions.
    """
    if fixed_R is None:
        fixed_R = {}

    n_regions = len(region_runners)

    # --- Step 1: Initialize R* values --------------------------------------
    for r in range(n_regions):
        if r in fixed_R:
            R_vec[r] = float(fixed_R[r])    # fixed region
        elif targets.get(r, None) is None:
            R_vec[r] = 1.0                  # free run
        else:
            R_vec[r] = float(R_vec[r])      # will calibrate later

    # --- Step 2: Sequential calibration ------------------------------------
    for r in range(n_regions):
        # Run upstream regions first
        if r > 0:
            for ru in range(r):
                region_runners[ru]()

        dP_target = targets.get(r, None)

        # Decide what to do for this region
        if r in fixed_R:
            status = "Forced"
            R_star = float(fixed_R[r])
        elif dP_target is not None:
            R_star = solve_R_for_region(r, dP_target, tol=tol)
            R_vec[r] = R_star
            status = "Calibrated"
        else:
            R_star = 1.0
            R_vec[r] = R_star
            status = "Free run"

        # Execute region with its final R*
        region_runners[r]()
        dP_measured = measure_region_dP(r)

        # --- Printing section (clear and correct) -------------------------
        if status == "Calibrated":
            print(f"[R{r+1}] {status} (R* = {R_star:.4f}, "
                  f"ΔP_target = {dP_target:.1f} Pa, ΔP = {dP_measured:.1f} Pa)")
        elif status == "Forced":
            print(f"[R{r+1}] {status} (R* = {R_star:.4f}, ΔP = {dP_measured:.1f} Pa)")
        else:  # Free run
            print(f"[R{r+1}] {status} (R* = {R_star:.4f}, no ΔP target, ΔP = {dP_measured:.1f} Pa)")

            

def sin_deg(theta_deg_r: float) -> float:
    """Sine of an angle in degrees (used for hydrostatic head)."""
    return math.sin(math.radians(float(theta_deg_r)))


def plot_profile(
    x, y,
    fixed_nodes, fixed_labels,
    cond_nodes=None, cond_labels=None,
    ref_points=None, ref_label=None,
    line_style=None,
    fixed_style=None,
    cond_styles=None,
    ref_style=None,
    annotate_offset=(5, 5),
    fontsize=10,                   # NEW: font size for labels and legend
    legend=True,                   # NEW: whether to show legend
    legend_loc="best",             # NEW: legend location
    ylim=None,                     # NEW: y-axis limit (tuple: (ymin, ymax))
    xlabel='', ylabel='', title='',
    dpi=200, show=True,
):
    """
    General-purpose profile plotter with nodes, conditional markers, and reference data.
    You provide x, y already in the desired units (Pa->bar, K->°C, etc.).
    """

    x = np.asarray(x)
    y = np.asarray(y)
    n = len(y)

    # Defaults
    line_style = {} if line_style is None else dict(line_style)
    fixed_style = {
        'marker': 's', 'color': 'silver'} if fixed_style is None else dict(fixed_style)
    ref_style = {'marker': 'o',
                 'color': 'orange'} if ref_style is None else dict(ref_style)

    plt.figure(dpi=dpi, figsize=(8, 3))
    plt.plot(x, y, **line_style, label="SS model")

    # --- Fixed nodes ---
    fx = []
    fy = []
    for idx in fixed_nodes:
        if isinstance(idx, (int, np.integer)) and 0 <= idx < n:
            fx.append(idx)
            fy.append(y[idx])
    if fx:
        plt.scatter(fx, fy, **fixed_style, label="Nodes")
        for idx, lab in zip(fx, fixed_labels):
            plt.annotate(lab, (idx, y[idx]),
                         textcoords="offset points", xytext=annotate_offset,
                         ha='center', fontsize=fontsize)

    # --- Conditional nodes (optional) ---
    if cond_nodes:
        cond_nodes = list(cond_nodes)
        cond_labels = list(cond_labels) if cond_labels is not None else [
            f"N{c}" for c in cond_nodes]
        cond_styles = cond_styles or [{}] * len(cond_nodes)

        valid_pairs = []
        for c in cond_nodes:
            if c is None or c == 0:
                continue
            if isinstance(c, (int, np.integer)) and 0 <= c < n:
                valid_pairs.append(c)

        for j, c in enumerate(valid_pairs):
            style_j = cond_styles[min(j, len(cond_styles)-1)]
            plt.scatter([c], [y[c]], **style_j, label=cond_labels[j])
            plt.annotate(cond_labels[j], (c, y[c]),
                         textcoords="offset points", xytext=annotate_offset,
                         ha='center', fontsize=fontsize)

    # --- Reference points (optional) ---
    if ref_points is not None:
        x_ref, y_ref = ref_points
        plt.scatter(x_ref, y_ref, **ref_style, label=ref_label or "Reference")

    # Labels & formatting
    plt.xlabel(xlabel, fontsize=fontsize)
    plt.ylabel(ylabel, fontsize=fontsize)
    if title:
        plt.title(title, fontsize=fontsize+2)
    if ylim is not None:
        plt.ylim(*ylim)
    if legend:
        plt.legend(loc=legend_loc, fontsize=fontsize-1)
    plt.grid(True)

    if show:
        plt.show()


def h_piecewise(nac, xk, hk):
    # xk, hk are lists, e.g., xk=[0, 0.6, 1], hk=[15000, 10000, 5000]
    return np.interp(nac, xk, hk)


def smooth(h, w=7):      # simple moving average, odd window
    w = max(1, int(w))
    w += 1 - w % 2
    k = np.ones(w)/w
    return np.convolve(h, k, mode='same')


# ============================================================================
# 6) GEOMETRY AND MESH
# ============================================================================
d = 8 * 1e-3  # [m] Inner diameter (mm)

# Per-region inclination [deg] (positive = upward component with your dz sign)
theta1 = 0
theta2 = 0
theta3 = 0
theta4 = 0
n_regions = 4

# .............Length definition
LR1 = (1000) * 1e-3  # [m] Length of Region 1 (mm)
LR2 = (100) * 1e-3  # [m] Length of Heater {Region 2 + Region 3} (mm)
LR3 = (500) * 1e-3  # [m] Length of Region 4 (mm)
LR4 = (5000) * 1e-3  # [m] Length of Region 5 (mm)
# .............Block definition
b0 = 1  # [-] Initial block
b1 = (100)  # [-] (1) Segment block of Region 1
b2 = (500)  # [-] Number of delta blocks in Heater (Region 2 + Region 3)
b3 = (100)  # [-] (1) Segment block of Region 4
b4 = (100)  # [-] (1) Component block of Region 5
n_cells = b0+b1+b2+b3+b4  # Number of computational cells

b2_ipg = 0.1  # Percentage of region length for the inlet section
b2_opg = 0.1  # Percentage of region length for the outlet section

Ac1 = ((np.pi*(d**2))/4)  # [m2] from de pipe
# [m2] from coupon (mm2) {Micro:61.44 / Baseline: 84.479 / Macro:103.68}
Ac2 = 84.479 * 1e-6
Pw1 = (np.pi*d)  # [m] from de pipe
# [m] from coupon (mm) {Micro:243.2 / Baseline: 193.6 / Macro:141.6}
Pw2 = 193.6 * 1e-3

# ============================================================================
# 7) BOUNDARY / INITIAL CONDITIONS
# ============================================================================
fluid = 'R123'
# .............State variables
T0 = 10 + 273.15  # [K] Inlet temperature (°C)
# P0 = 5.683 * 1e5  # [Pa] Loop inlet pressure (bar) 1.78L
P0 = 2.28 * 1e5  # [Pa] Loop inlet pressure (bar) 1.78L
# .............Operational values
# Quantitative flow definition:
# # By volumetric flow:
# vol_flow = 0.35*(1/(1000*60))  # [m^3/s] Volumetric flow (l/min)
# _, _, rho_l, _, _, _, _ = EOS_liq_properties(T0, P0, fluid) # [kg/m^3] Density of liquid
# m_dot = rho_l*vol_flow  # [kg/s] Mass flow rate
# A_pipe = np.pi*(d**2)/4  # pipe area [m2]
# G0 = m_dot / A_pipe  # [kg/s] Mass flow rate
# # By mass flow:
# m_dot = 27.5 * 1e-3  # [kg/s] Mass flow rate (g/s)
# A_pipe = np.pi*(d**2)/4  # pipe area [m2]
# G0 = m_dot / A_pipe  # [kg/s] Mass flow rate
# # By mass flux:
G0 = 264.4  # [kg/m^2.s] Mass flux

# MPL2030 50 W/cm2 -> transferred heat requirement 1140 [W]

# .............Heat transfer rate per region
W1 = 0  # [W] Heat transfer rate
alpha2 = 5500  # [W/m^2.K] Heat transfer coefficient
a2xp = [0, 0.2, 0.4, 0.6, 0.8, 1]
a2yp = [900, 8500, 4500, 3500, 2200, 500]
W3 = 0  # [W] Heat transfer rate
W4 = -1150  # [W] Heat transfer rate


# ============================================================================
# 8) NUMERICS (REGION-WISE)
# ============================================================================
# .............Definition of vectors
G_vec = np.zeros(n_cells)
h_vec = np.zeros(n_cells)
rho_vec = np.zeros(n_cells)
x_vec = np.zeros(n_cells)
psi_vec = np.zeros(n_cells)
T_vec = np.zeros(n_cells)
P_vec = np.zeros(n_cells)
u_vec = np.zeros(n_cells)
alpha_vec = np.zeros(n_cells)
T_wall_vec = (60+273.15) * np.ones(n_cells)

Ac_vec = ((np.pi*(d**2))/4)*np.ones(n_cells)
Pw_vec = (np.pi*d)*np.ones(n_cells)
dQdz_vec = np.zeros(n_cells)

R_vec = np.ones(n_regions)
dz_vec = np.ones(n_regions)
theta_vec = np.zeros(n_regions)

# .............Initialisation values
G_vec[0] = G0
T_vec[0] = T0
P_vec[0] = P0
h_vec[0] = Cp.PropsSI('H', 'T', T_vec[0], 'P', P_vec[0], fluid)
rho_vec[0] = Cp.PropsSI('D', 'T', T_vec[0], 'P', P_vec[0], fluid)
u_vec[0] = homogeneous_velocity(G_vec[0], rho_vec[0])
T_wall_vec[0] = T_vec[0]

# .............Computational node indexing
# Fixed nodes
N0 = (b0)-1
N1 = (b0+b1)-1
N2 = (b0+b1+b2)-1
N3 = (b0+b1+b2+b3)-1
N4 = (b0+b1+b2+b3+b4)-1

#############################################################
############################################################

# .............(((((((())))))))
# .............(((((( N0 ))))))
# .............(((((((())))))))


# ..................................................................................
def run_region1():
    # <<<<<<<<  Inlet of Region 1 <<<<<<<<
    r = 1-1  # region number
    for i in range(N0+1, N1+1):
        dQdz_vec[i] = W1/LR1  # [W/m] Heat transfer rate per unit length
        dz_vec[r] = LR1/b1  # [m] Delta length (region dependent)
        h_vec[i], P_vec[i], T_vec[i], x_vec[i], psi_vec[i], rho_vec[i], u_vec[i], _ = \
            function_conservation(
                dQdz_vec[i], dz_vec[r], i, R_vec[r], theta_vec[r], G_vec[i-1], Ac_vec[i], Ac_vec[i-1], Pw_vec[i])
    # .............(((((((())))))))
    # .............(((((( N1 ))))))
    # .............(((((((())))))))


def run_region2():
    # <<<<<<<<  Inlet of Region 2 <<<<<<<<
    r = 2-1  # region number
    
    b2_in = math.ceil(b2*b2_ipg)  # Element where the inlet section ends
    b2_out = math.ceil(b2*(1-b2_opg))  # Element where the outlet section begins
    inAc = np.linspace(Ac1, Ac2, b2_in)
    outAc = np.linspace(Ac2, Ac1, b2-b2_out)
    inPw = np.linspace(Pw1, Pw2, b2_in)
    outPw = np.linspace(Pw2, Pw1, b2-b2_out)
    SumdQdz = 0
    
    nac = np.linspace(0, 1, b2)  # Normalized axial coordinate from 0 to 1
    alpha2 = h_piecewise(nac, a2xp, a2yp)
    alpha2 = smooth(alpha2, 7)
    
    for i in range(N1+1, N2+1):
        j = i-(N1+1)
        k = i-(N1+1+b2_out)
        dz_vec[r] = LR2/b2  # [m] Delta length (region dependent)
        if i < N1+1+b2_in:  # In the inlet section
            Ac_vec[i] = inAc[j]
            Pw_vec[i] = inPw[j]
        elif i > N1+1+b2_out:  # In the outlet section
            Ac_vec[i] = outAc[k]
            Pw_vec[i] = outPw[k]
        else:  # In the middle section
            Ac_vec[i] = Ac2
            Pw_vec[i] = Pw2
    
        alpha_vec[i] = alpha2[j]
        # [W/m] Heat transfer rate per unit length
        dQdz_vec[i] = alpha_vec[i] * Pw_vec[i] * (T_wall_vec[i]-T_vec[i-1])
    
        SumdQdz = (dQdz_vec[i]*dz_vec[r])+SumdQdz
    
        h_vec[i], P_vec[i], T_vec[i], x_vec[i], psi_vec[i], rho_vec[i], u_vec[i], h_l = \
            function_conservation(
                dQdz_vec[i], dz_vec[r], i, R_vec[r], theta_vec[r], G_vec[i-1], Ac_vec[i], Ac_vec[i-1], Pw_vec[i])
    
    # print('SumdQdz:', SumdQdz, '[W]', 'Target=1140 [W]')
    # <<<<<<<<  Outlet of Region 2 <<<<<<<<


# .............(((((((())))))))
# .............(((((( N2 ))))))
# .............(((((((())))))))

def run_region3():
    # <<<<<<<<  Inlet of Region 3 <<<<<<<<
    # DP adjustment term (L:0.357 / M:0.284 / H:0.24)
    # ..................................................................................
    r = 3-1
    for i in range(N2+1, N3+1):
        dQdz_vec[i] = W3/LR3  # [W/m] Heat transfer rate per unit length
        dz_vec[r] = LR3/b3  # [m] Delta length (region dependent)
        h_vec[i], P_vec[i], T_vec[i], x_vec[i], psi_vec[i], rho_vec[i], u_vec[i], _ = \
            function_conservation(
                dQdz_vec[i], dz_vec[r], i, R_vec[r], theta_vec[r], G_vec[i-1], Ac_vec[i], Ac_vec[i-1], Pw_vec[i])
    
    # <<<<<<<<  Outlet of Region 3 <<<<<<<<


# .............(((((((())))))))
# .............(((((( N3 ))))))
# .............(((((((())))))))

def run_region4():
    # <<<<<<<<  Inlet of Region 4 <<<<<<<<
    # DP adjustment term (L:0.157 / M:0.0989 / L:0.0739)
    # .........................................................
    r = 4-1
    for i in range(N3+1, N4+1):
        dQdz_vec[i] = W4/LR4  # [W/m] Heat transfer rate per unit length
        dz_vec[r] = LR4/b4  # [m] Delta length (region dependent)
        h_vec[i], P_vec[i], T_vec[i], x_vec[i], psi_vec[i], rho_vec[i], u_vec[i], h_l = \
            function_conservation(
                dQdz_vec[i], dz_vec[r], i, R_vec[r], theta_vec[r], G_vec[i-1], Ac_vec[i], Ac_vec[i-1], Pw_vec[i])
    
    # <<<<<<<<  Outlet of Region 4 <<<<<<<<


# .............(((((((())))))))
# .............(((((( N4 ))))))
# .............(((((((())))))))

# ................................................................................
# ........ RUNNING THE SIMULATION WITH CALIBRATED R* .............................
# ................................................................................

# Define region execution functions (each contains the marching logic of that region)
region_runners = {
    0: run_region1,
    1: run_region2,
    2: run_region3,
    3: run_region4,
}

# Define target pressure drops per region [Pa]
# If a region target is None → it will be run freely with R* = 1.0 (no calibration)
targets = {
    0: 0.2e5,        # Target pressure drops Region 1 [Pa]
    1: 0.2e5,        # Target pressure drops Region 2 [Pa]
    2: None,        # Target pressure drops Region 3 [Pa]
    3: 0.2e5         # Target pressure drops Region 4 [Pa]
}

fixed_R = {  }  # lock by Region if known e.g., 1: 116.0156, if not leave it empty

# Calibrate and run regions sequentially within tolerance 5 [Pa].
# → Each region runs in order, ensuring correct inlet conditions.
# → Regions with numeric targets are calibrated to match the desired ΔP.
# → Regions with None targets are run once with R* = 1.0, or fixed if provided.
calibrate_R_stars(targets, tol=5.0, fixed_R=fixed_R)

# Final clean full pass over all regions (in correct order)
# → Ensures the global profiles (T, P, x, etc.) correspond to the calibrated R* values.
for r in range(len(region_runners)):
    region_runners[r]()


        
# ============================================================================
# 9) PRINTOUTS AND PLOTS
# ============================================================================

N_vec_cells = np.arange(n_cells)

yP = P_vec / 1e5
plot_profile(
    x=N_vec_cells, y=yP,
    fixed_nodes=[N0, N1, N2, N3, N4],
    fixed_labels=["N0", "N1", "N2", "N3", "N4"],
    # ref_points=None,
    # ref_points=([N1, N2, N3, N4], [2.279, 2.174, 1.934, 1.86]),  # Fujii_High
    # ref_points=([N1, N3, N4, N6], [1.976, 1.842, 1.558, 1.459]), # Fujii_Medium
    # ref_points=([N1, N3, N4, N6], [1.683, 1.525, 1.168, 1.011]),  # Fujii_Low
    # ref_label="Fujii et al. (2004)",
    line_style={'color': 'blue'},
    cond_styles=[{'marker': 's', 'color': 'red'},
                 {'marker': 's', 'color': 'blue'}],
    xlabel="Discretised cells [-]",
    ylabel="Pressure [bar]",
    ylim=None,
    # ylim=(0, 3),
    fontsize=12,
    legend=None,
    legend_loc="upper right"
)

yP = T_vec - 273.15
plot_profile(
    x=N_vec_cells, y=yP,
    fixed_nodes=[N0, N1, N2, N3, N4],
    fixed_labels=["N0", "N1", "N2", "N3", "N4"],
    # ref_points=([N1, N2, N3, N4], [9.574, 50.567,46.595, 7.021]),  # Fujii_High
    # ref_points=([N1, N3, N4, N6], [9.574, 45.035, 39.645, 5.744]), # Fujii_Medium
    # ref_points=([N1, N3, N4, N6], [9.574, 39.361, 31.276, 8.156]),  # Fujii_Low
    cond_styles=[{'marker': 's', 'color': 'red'},
                 {'marker': 's', 'color': 'blue'}],
    xlabel="Discretised cells [-]",
    ylabel="Temperature [°C]",
    ylim=(0, 70),
    # ylim=None,
    fontsize=12,
    legend=None,
    legend_loc="upper right"
)

yP = x_vec
plot_profile(
    x=N_vec_cells, y=yP,
    fixed_nodes=[N0, N1, N2, N3, N4],
    fixed_labels=["N0", "N1", "N2", "N3", "N4"],
    # ref_points=([N1, N2], [-0.0128, 0.6021]),  # Fujii_High
    # ref_points=([N2, N3], [0.001, 0.616]), # Fujii_Medium
    # ref_points=([N2, N3], [0.058, 0.644]),  # Fujii_Low
    # ref_label="Fujii et al. (2004)",
    line_style={'color': 'green'},
    cond_styles=[{'marker': 's', 'color': 'red'},
                 {'marker': 's', 'color': 'blue'}],
    xlabel="Discretised cells [-]",
    ylabel="Vapour quality [-]",
    ylim=(-0.05, 1),
    # ylim=None,
    fontsize=12,
    legend=None,
    legend_loc="upper right"
)

yP = Ac_vec*1e4
plot_profile(
    x=N_vec_cells, y=yP,
    fixed_nodes=[N0, N1, N2, N3, N4],
    fixed_labels=["N0", "N1", "N2", "N3", "N4"],
    # ref_points=([N1, N2], [-0.0128, 0.6021]), # Fujii_High
    # ref_points=([N2, N3], [0.001, 0.616]), # Fujii_Medium
    # ref_points=([N2, N3], [0.058, 0.644]),  # Fujii_Low
    # ref_label="Fujii et al. (2004)",
    line_style={'color': 'cyan'},
    # cond_styles=[{'marker': 's', 'color': 'red'},
    #              {'marker': 's', 'color': 'blue'}],
    xlabel="Discretised cells [-]",
    ylabel="Cross-sectional area [cm2]",
    ylim=(0, None),
    # ylim=None,
    fontsize=12,
    legend=None,
    legend_loc="upper right"
)

yP = Pw_vec*1e2
plot_profile(
    x=N_vec_cells, y=yP,
    fixed_nodes=[N0, N1, N2, N3, N4],
    fixed_labels=["N0", "N1", "N2", "N3", "N4"],
    # ref_points=([N1, N2], [-0.0128, 0.6021]), # Fujii_High
    # ref_points=([N2, N3], [0.001, 0.616]), # Fujii_Medium
    # ref_points=([N2, N3], [0.058, 0.644]),  # Fujii_Low
    # ref_label="Fujii et al. (2004)",
    line_style={'color': 'orange'},
    # cond_styles=[{'marker': 's', 'color': 'red'},
    #              {'marker': 's', 'color': 'blue'}],
    xlabel="Discretised cells [-]",
    ylabel="Wetted perimeter [cm]",
    ylim=(0, None),
    # ylim=None,
    fontsize=12,
    legend=None,
    legend_loc="upper right"
)

yP = dQdz_vec
plot_profile(
    x=N_vec_cells, y=yP,
    fixed_nodes=[N0, N1, N2, N3, N4],
    fixed_labels=["N0", "N1", "N2", "N3", "N4"],
    # ref_points=([N1, N2], [-0.0128, 0.6021]), # Fujii_High
    # ref_points=([N2, N3], [0.001, 0.616]), # Fujii_Medium
    # ref_points=([N2, N3], [0.058, 0.644]),  # Fujii_Low
    # ref_label="Fujii et al. (2004)",
    line_style={'color': 'magenta'},
    # cond_styles=[{'marker': 's', 'color': 'red'},
    #              {'marker': 's', 'color': 'blue'}],
    xlabel="Discretised cells [-]",
    ylabel="Heat load profile [W/m]",
    # ylim=(-0.05, 0.7),
    ylim=None,
    fontsize=12,
    legend=None,
    legend_loc="upper right"
)

yP = G_vec
plot_profile(
    x=N_vec_cells, y=yP,
    fixed_nodes=[N0, N1, N2, N3, N4],
    fixed_labels=["N0", "N1", "N2", "N3", "N4"],
    # ref_points=([N1, N2], [-0.0128, 0.6021]), # Fujii_High
    # ref_points=([N2, N3], [0.001, 0.616]), # Fujii_Medium
    # ref_points=([N2, N3], [0.058, 0.644]),  # Fujii_Low
    # ref_label="Fujii et al. (2004)",
    line_style={'color': 'black'},
    # cond_styles=[{'marker': 's', 'color': 'red'},
    #              {'marker': 's', 'color': 'blue'}],
    xlabel="Discretised cells [-]",
    ylabel="Mass flux [kg/m2.s]",
    # ylim=(-0.05, 0.7),
    ylim=None,
    fontsize=12,
    legend=None,
    legend_loc="upper right"
)

yP = alpha_vec
plot_profile(
    x=N_vec_cells, y=yP,
    fixed_nodes=[N0, N1, N2, N3, N4],
    fixed_labels=["N0", "N1", "N2", "N3", "N4"],
    # ref_points=([N1, N2], [-0.0128, 0.6021]), # Fujii_High
    # ref_points=([N2, N3], [0.001, 0.616]), # Fujii_Medium
    # ref_points=([N2, N3], [0.058, 0.644]),  # Fujii_Low
    # ref_label="Fujii et al. (2004)",
    line_style={'color': 'red'},
    # cond_styles=[{'marker': 's', 'color': 'red'},
    #              {'marker': 's', 'color': 'blue'}],
    xlabel="Discretised cells [-]",
    ylabel="HTC [W/m2.K]",
    # ylim=(-0.05, 0.7),
    ylim=None,
    fontsize=12,
    legend=None,
    legend_loc="upper right"
)


# yP = T_wall_vec-273.15
# plot_profile(
#     x=N_vec_cells, y=yP,
#     fixed_nodes=[N0, N1, N3, N4, N6],
#     fixed_labels=["N0", "N1", "N3", "N4", "N6"],
#     cond_nodes=[N2, N5],
#     cond_labels=["L->V", "V->L"],
#     ref_points=([N2, N3], [53.262, 54.113]),
#     ref_label="Fujii et al. (2004)",
#     line_style={'color': 'green'},
#     cond_styles=[{'marker': 's', 'color': 'red'},
#                  {'marker': 's', 'color': 'blue'}],
#     xlabel="Discretised cells [-]",
#     ylabel="Wall temperature [°C]",
#     ylim=None,
#     fontsize=12,
#     legend=True,
#     legend_loc="upper right"
# )

# yP = alpha_vec
# plot_profile(
#     x=N_vec_cells, y=yP,
#     fixed_nodes=[N0, N1, N3, N4, N6],
#     fixed_labels=["N0", "N1", "N3", "N4", "N6"],
#     cond_nodes=[N2, N5],
#     cond_labels=["L->V", "V->L"],
#     ref_points=None,
#     ref_label="Fujii et al. (2004)",
#     line_style={'color': 'green'},
#     cond_styles=[{'marker': 's', 'color': 'red'},
#                  {'marker': 's', 'color': 'blue'}],
#     xlabel="Discretised cells [-]",
#     ylabel="HTC [W/m2.K]",
#     ylim=None,
#     fontsize=12,
#     legend=True,
#     legend_loc="upper right"
# )


print('- - - - - -')
print('Success!!!')
print('- - - - - -')

# Time record end
end_time = time.time()
elapsed_time = end_time - start_time

print(f"Computation time: {elapsed_time:.4f} seconds")

# ---------------------------------------
# --------------- ANNEXES ---------------
# ---------------------------------------

# ///////////////////////////////////////////////////////////
# Fujii et al. (2004)
# ...............................................
# High
# P [2.279, 2.174, 1.934, 1.86, 1.859] FujiiNodes:<<1,9,10,11,12>> DP{0.1049,0.24,0.0739}
# T [9.574, 26.879, 44.326, 51.134, 50.851,50.851, 50.709, 50.709, 50.567, 46.595, 7.021] <<1,2,3,4,5,6,7,8,9,10,11>>
# x [-0.1224, -0.0128, 0.0967, 0.1921, 0.3017, 0.3972, 0.5067, 0.6021] <<2,3,4,5,6,7,8,9>>
# T_wall [61.35, 61.35, 59.93, 61.35, 61.49, 61.35, 63.48] <<2,3,4,5,6,7,8>>
# ...............................................
# ...............................................
# Medium
# P [1.976,1.842,1.558,1.459,1.458] FujiiNodes:<<1,9,10,11,12>> DP{0.1339,0.284,0.0989}
# T [9.574,28.014,46.028,46.595,46.453,46.453,46.312,46.312,45.035,39.645,5.744] <<1,2,3,4,5,6,7,8,9,10,11>>
# x [-0.094,0.001,0.096,0.206,0.315,0.411,0.520,0.616] <<2,3,4,5,6,7,8,9>>
# T_wall [57.092,58.226,55.531,56.666,56.950,56.808,58.794] <<2,3,4,5,6,7,8>>
# ...............................................
# ...............................................
# Low
# P [1.683,1.525,1.168,1.011,1.010] FujiiNodes:<<1,9,10,11,12>> DP{0.158,0.357,0.157}
# T [9.574,28.297,42.056,41.914,41.914,41.773,41.631,41.631,39.361,31.276,8.156] <<1,2,3,4,5,6,7,8,9,10,11>>
# x [-0.037,0.058,0.167,0.277,0.344,0.439,0.549,0.644] <<2,3,4,5,6,7,8,9>>
# T_wall [53.262,53.262,51.134,52.553,52.836,52.269,54.113] <<2,3,4,5,6,7,8>>
# ...............................................
# ///////////////////////////////////////////////////////////

# %%
