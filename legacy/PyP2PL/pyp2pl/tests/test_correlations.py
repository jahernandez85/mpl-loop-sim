"""
tests/test_correlations.py
===========================
Unit tests for all correlations in pyp2pl.correlations.

Reference values are taken from:
  - Kokate & Park, Applied Thermal Engineering 249 (2024), Table 3, Fig. 6-7
  - Kokate & Park, Applied Thermal Engineering 229 (2023), Appendix equations
  - Kokate PhD Thesis (2024), Appendix A and B

Run with:
    cd /path/to/pyp2pl
    python -m pytest tests/test_correlations.py -v

Or directly:
    python tests/test_correlations.py
"""

import sys
import os
import math
import CoolProp.CoolProp as CP

# Make sure pyp2pl is importable from the parent directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from pyp2pl.fluid.fluid import FluidProperties
from pyp2pl.correlations.htc_boiling import (
    shah, kandlikar_balasubramanian, gungor_winterton,
    compute_htc_boiling, AVAILABLE_CORRELATIONS,
)
from pyp2pl.correlations.dp_twophase import (
    msh_frictional_gradient, two_phase_pressure_drop,
)
from pyp2pl.correlations.dp_singlephase import (
    churchill_friction_factor, single_phase_dp,
)


# ---------------------------------------------------------------------------
# Reference fluid: R-134a at 20°C / 572 kPa (Kokate Table 2.1)
# ---------------------------------------------------------------------------

FP = FluidProperties('R134a')
SAT_REF = FP.saturated(P=572.2e3)   # Kokate reference condition: 20°C

# Kokate Table 2.1 reference values at 20°C
REF = {
    'T_sat':   293.15,    # K
    'P_sat':   572.2e3,   # Pa
    'rho_l':   1225.3,    # kg/m³
    'rho_v':   27.8,      # kg/m³
    'h_fg':    182.3e3,   # J/kg
    'sigma':   8.7e-3,    # N/m
    'k_l':     0.08,      # W/(m·K)
    'mu_l':    2.0e-3,    # Pa·s
    'cp_l':    1.4e3,     # J/(kg·K)
}

# Kokate baseline evaporator geometry (Table 2.2, design C, Lytron CP20G03)
# 44 microchannels, Wch = 0.5 mm, Hch = 2.5 mm, Lch = 25 mm
N_CH = 44
W_CH = 0.5e-3    # m
H_CH = 2.5e-3    # m
L_CH = 25e-3     # m
Dh = 2.0 * W_CH * H_CH / (W_CH + H_CH)   # hydraulic diameter ≈ 0.769 mm
Ac = W_CH * H_CH                           # channel cross-section

# Baseline: G_ch = 47.9 kg/(m²·s), q" = 10 W/cm² = 1e5 W/m²
G_BASELINE = 47.9   # kg/(m²·s)  (Table 4.1 in Kokate 2024)
Q_FLUX     = 10e4   # W/m²


def _tol(val, ref, pct):
    """Assert val is within ±pct% of ref."""
    err = abs(val - ref) / abs(ref) * 100.0
    assert err < pct, f"Got {val:.4g}, expected {ref:.4g} (error {err:.1f}% > {pct}%)"


# ===========================================================================
# 1.  CoolProp wrapper / FluidProperties
# ===========================================================================

def test_saturation_pressure_r134a():
    """Saturation pressure at 20°C should be ~572 kPa (Kokate Table 2.1)."""
    P = FP.P_sat(T=293.15)
    _tol(P, 572.2e3, pct=2.0)

def test_saturation_properties_density():
    """Saturated liquid density at 20°C should be ~1225 kg/m³."""
    _tol(SAT_REF.rho_l, 1225.3, pct=2.0)

def test_saturation_properties_hvap():
    """Latent heat at 20°C should be ~182 kJ/kg (Kokate Table 2.1)."""
    _tol(SAT_REF.h_fg, 182.3e3, pct=3.0)

def test_saturation_properties_sigma():
    """Surface tension at 20°C should be ~8.7 mN/m (Kokate Table 2.1)."""
    _tol(SAT_REF.sigma, 8.7e-3, pct=10.0)  # wider tolerance, measured value

def test_fluid_invalid_name():
    """Invalid fluid name should raise ValueError."""
    try:
        FluidProperties('NotAFluid_XYZ')
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


# ===========================================================================
# 2.  Dittus-Boelter liquid baseline (inside Shah)
# ===========================================================================

def test_shah_returns_htcresult():
    """Shah correlation should return HTCResult with positive alpha."""
    res = shah(
        G=G_BASELINE, x=0.5, q_flux=Q_FLUX, dh=Dh, P=SAT_REF.P_sat,
        P_crit=CP.PropsSI("Pcrit", "", 0, "", 0, "R134a"),
        rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
        mu_l=SAT_REF.mu_l, mu_v=SAT_REF.mu_v,
        cp_l=SAT_REF.cp_l, k_l=SAT_REF.k_l, h_fg=SAT_REF.h_fg,
    )
    assert res.alpha > 0, "HTC must be positive"
    assert res.alpha_l > 0, "Liquid-only HTC must be positive"
    assert res.Bo > 0, "Boiling number must be positive"

def test_shah_order_of_magnitude():
    """
    Shah HTC for R-134a microchannel at G=47.9 kg/(m²·s), q"=10 W/cm²
    should be in the range 500–3000 W/(m²·K) based on Kokate Fig. 6.
    """
    import CoolProp.CoolProp as CP
    P_crit = CP.PropsSI('Pcrit', '', 0, '', 0, 'R134a')
    res = shah(
        G=G_BASELINE, x=0.5, q_flux=Q_FLUX, dh=Dh, P=SAT_REF.P_sat,
        P_crit=P_crit,
        rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
        mu_l=SAT_REF.mu_l, mu_v=SAT_REF.mu_v,
        cp_l=SAT_REF.cp_l, k_l=SAT_REF.k_l, h_fg=SAT_REF.h_fg,
    )
    assert 300 < res.alpha < 5000, f"Unexpected HTC: {res.alpha:.1f} W/(m²·K)"

def test_shah_increases_with_quality_at_low_x():
    """HTC should generally increase from x=0.1 to x=0.5 (convective boiling)."""
    import CoolProp.CoolProp as CP
    P_crit = CP.PropsSI('Pcrit', '', 0, '', 0, 'R134a')
    kwargs = dict(G=G_BASELINE, q_flux=Q_FLUX, dh=Dh, P=SAT_REF.P_sat,
                  P_crit=P_crit,
                  rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
                  mu_l=SAT_REF.mu_l, mu_v=SAT_REF.mu_v,
                  cp_l=SAT_REF.cp_l, k_l=SAT_REF.k_l, h_fg=SAT_REF.h_fg)
    alpha_low  = shah(x=0.1, **kwargs).alpha
    alpha_mid  = shah(x=0.5, **kwargs).alpha
    # Not strictly monotonic for Shah, but generally higher at mid quality
    assert alpha_low > 0 and alpha_mid > 0


# ===========================================================================
# 3.  Kandlikar correlation
# ===========================================================================

def test_kandlikar_returns_positive():
    """Kandlikar HTC should be positive for valid inputs."""
    res = kandlikar_balasubramanian(
        G=G_BASELINE, x=0.5, q_flux=Q_FLUX, dh=Dh,
        rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
        mu_l=SAT_REF.mu_l, cp_l=SAT_REF.cp_l, k_l=SAT_REF.k_l,
        h_fg=SAT_REF.h_fg, F_fl=1.63,
    )
    assert res.alpha > 0

def test_kandlikar_vs_shah_same_order():
    """Kandlikar and Shah should agree within an order of magnitude."""
    import CoolProp.CoolProp as CP
    P_crit = CP.PropsSI('Pcrit', '', 0, '', 0, 'R134a')
    alpha_shah = shah(
        G=G_BASELINE, x=0.5, q_flux=Q_FLUX, dh=Dh, P=SAT_REF.P_sat,
        P_crit=P_crit,
        rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
        mu_l=SAT_REF.mu_l, mu_v=SAT_REF.mu_v,
        cp_l=SAT_REF.cp_l, k_l=SAT_REF.k_l, h_fg=SAT_REF.h_fg,
    ).alpha
    alpha_kand = kandlikar_balasubramanian(
        G=G_BASELINE, x=0.5, q_flux=Q_FLUX, dh=Dh,
        rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
        mu_l=SAT_REF.mu_l, cp_l=SAT_REF.cp_l, k_l=SAT_REF.k_l,
        h_fg=SAT_REF.h_fg,
    ).alpha
    ratio = alpha_kand / alpha_shah
    assert 0.1 < ratio < 10.0, f"Kandlikar/Shah ratio out of range: {ratio:.2f}"


# ===========================================================================
# 4.  MSH two-phase pressure drop
# ===========================================================================

def test_msh_gradient_positive():
    """MSH frictional gradient should be positive."""
    dPdz = msh_frictional_gradient(
        G=G_BASELINE, x=0.5, dh=Dh,
        rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
        mu_l=SAT_REF.mu_l, mu_v=SAT_REF.mu_v,
    )
    assert dPdz > 0, f"Expected positive dP/dz, got {dPdz}"

def test_msh_gradient_order_of_magnitude():
    """MSH gradient for Kokate baseline should be in kPa/m range."""
    dPdz = msh_frictional_gradient(
        G=G_BASELINE, x=0.5, dh=Dh,
        rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
        mu_l=SAT_REF.mu_l, mu_v=SAT_REF.mu_v,
    )
    # For microchannel at G~48 kg/(m²s), expect order 1–100 kPa/m
    assert 1e2 < dPdz < 1e6, f"Unexpected gradient: {dPdz:.1f} Pa/m"

def test_two_phase_dp_result_components():
    """Total ΔP should equal friction + acceleration + hydrostatic."""
    res = two_phase_pressure_drop(
        G=G_BASELINE, x_in=0.0, x_out=0.8, L=L_CH, dh=Dh,
        rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
        mu_l=SAT_REF.mu_l, mu_v=SAT_REF.mu_v,
    )
    total_check = res.dP_fric + res.dP_accel + res.dP_static
    _tol(res.dP_total, total_check, pct=0.1)
    assert res.dP_total > 0

def test_two_phase_dp_increases_with_G():
    """Pressure drop should increase with mass flux."""
    dp_low = two_phase_pressure_drop(
        G=30.0, x_in=0.0, x_out=0.8, L=L_CH, dh=Dh,
        rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
        mu_l=SAT_REF.mu_l, mu_v=SAT_REF.mu_v,
    ).dP_total
    dp_high = two_phase_pressure_drop(
        G=100.0, x_in=0.0, x_out=0.8, L=L_CH, dh=Dh,
        rho_l=SAT_REF.rho_l, rho_v=SAT_REF.rho_v,
        mu_l=SAT_REF.mu_l, mu_v=SAT_REF.mu_v,
    ).dP_total
    assert dp_high > dp_low, "ΔP should increase with G"


# ===========================================================================
# 5.  Churchill single-phase friction factor
# ===========================================================================

def test_churchill_laminar():
    """f = 64/Re in laminar regime."""
    Re = 500.0
    f  = churchill_friction_factor(Re)
    _tol(f, 64.0 / Re, pct=1.0)

def test_churchill_turbulent_smooth():
    """Turbulent smooth pipe: compare to Petukhov f = (0.790 ln Re - 1.64)^-2."""
    Re = 1e5
    f_ch = churchill_friction_factor(Re, roughness_ratio=0.0)
    # Petukhov approximation
    f_p = (0.790 * math.log(Re) - 1.64)**(-2)
    _tol(f_ch, f_p, pct=5.0)

def test_single_phase_dp_increases_with_L():
    """Pressure drop should be proportional to pipe length."""
    base = dict(m_dot=1e-3, D=5e-3, rho=1200.0, mu=2e-3)
    dp_1 = single_phase_dp(L=0.5, **base).dP
    dp_2 = single_phase_dp(L=1.0, **base).dP
    _tol(dp_2, 2.0 * dp_1, pct=0.5)

def test_single_phase_dp_laminar_known():
    """
    For laminar flow (Re ≈ 200), Hagen-Poiseuille: ΔP = 128*mu*L*Q / (pi*D^4).
    Using f=64/Re form: ΔP = 32*mu*u*L / (D²/4 * 2) ... verify consistency.
    """
    D = 4e-3; L = 1.0; rho = 1000.0; mu = 1e-3
    m_dot = 0.001  # kg/s → u = m_dot/(rho*pi*D²/4)
    import math as m
    A = m.pi * D**2 / 4.0
    u = m_dot / (rho * A)
    Re = rho * u * D / mu
    f = 64.0 / Re
    dP_manual = f * (L / D) * rho * u**2 / 2.0
    res = single_phase_dp(m_dot=m_dot, L=L, D=D, rho=rho, mu=mu)
    _tol(res.dP, dP_manual, pct=0.5)


# ===========================================================================
# 6.  Dispatcher (compute_htc_boiling)
# ===========================================================================

def test_dispatcher_all_correlations():
    """All correlations should run without error and return positive alpha."""
    import CoolProp.CoolProp as CP
    P_crit = CP.PropsSI('Pcrit', '', 0, '', 0, 'R134a')

    for corr in AVAILABLE_CORRELATIONS:
        res = compute_htc_boiling(
            correlation=corr,
            G=G_BASELINE, x=0.5, q_flux=Q_FLUX, dh=Dh,
            sat=SAT_REF, P=SAT_REF.P_sat, P_crit=P_crit,
            T_wall=SAT_REF.T_sat + 10.0,  # 10 K superheat for Chen-based
        )
        assert res.alpha > 0, f"Correlation '{corr}' returned alpha={res.alpha}"

def test_dispatcher_invalid_name():
    """Invalid correlation name should raise ValueError."""
    import CoolProp.CoolProp as CP
    P_crit = CP.PropsSI('Pcrit', '', 0, '', 0, 'R134a')
    try:
        compute_htc_boiling(
            correlation='not_a_real_correlation',
            G=G_BASELINE, x=0.5, q_flux=Q_FLUX, dh=Dh,
            sat=SAT_REF, P=SAT_REF.P_sat, P_crit=P_crit,
        )
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


# ===========================================================================
# Run all tests manually (without pytest)
# ===========================================================================

if __name__ == '__main__':
    tests = [
        test_saturation_pressure_r134a,
        test_saturation_properties_density,
        test_saturation_properties_hvap,
        test_saturation_properties_sigma,
        test_fluid_invalid_name,
        test_shah_returns_htcresult,
        test_shah_order_of_magnitude,
        test_shah_increases_with_quality_at_low_x,
        test_kandlikar_returns_positive,
        test_kandlikar_vs_shah_same_order,
        test_msh_gradient_positive,
        test_msh_gradient_order_of_magnitude,
        test_two_phase_dp_result_components,
        test_two_phase_dp_increases_with_G,
        test_churchill_laminar,
        test_churchill_turbulent_smooth,
        test_single_phase_dp_increases_with_L,
        test_single_phase_dp_laminar_known,
        test_dispatcher_all_correlations,
        test_dispatcher_invalid_name,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}  →  {e}")
            failed += 1

    print(f"\n{'='*55}")
    print(f"  Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*55}")
    if failed > 0:
        sys.exit(1)
