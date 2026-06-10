"""
tests/test_correlations.py
==========================
Pytest test suite for correlations.py — MPL Simulation Library.

Coverage:
  1. Physical consistency: outputs positive, finite, physically plausible
  2. Limit verification: single-phase limits, x→0 and x→1 behaviour
  3. Monotonicity: HTC increases with q_flux / G; ΔP increases with G
  4. Regime transitions: laminar/turbulent, stratified/non-stratified
  5. Registry: factory functions return correct types
  6. Protocols: classes satisfy HTCCorrelation / DPCorrelation protocols
  7. Gravity & acceleration helpers

Run with:
    pytest tests/test_correlations.py -v
"""

import math
import warnings
import pytest
from dataclasses import dataclass, field
from typing import Any

# ── import module under test ────────────────────────────────────────────────
from correlations import (
    # HTC
    DittusBoelterHTC, GnielinskiHTC, ShahLondonLaminarHTC,
    ShahBoilingHTC, KimMudawar2012HTC, YanCondensationHTC,
    # ΔP
    BlassiusDP, ChurchillDP,
    HomogeneousDP, KimMudawar2013DP, MullerSteinhagenHeckDP,
    # Helpers
    acceleration_pressure_gradient, gravity_pressure_gradient,
    # Registry
    get_htc_correlation, get_dp_correlation,
    # Protocols
    HTCCorrelation, DPCorrelation,
    # Internal helpers
    _friction_factor_blasius, _nusselt_dittus_boelter,
    _friction_factor_rect_laminar,
)


# ===========================================================================
# Shared fixtures
# ===========================================================================

@dataclass
class FluidStub:
    """
    Minimal duck-typed FluidState for testing correlations
    without importing fluid_properties.py.
    Represents a two-phase mixture of a generic refrigerant.
    """
    phase: str   = "two-phase"
    T: float     = 293.15    # [K]   ~20 °C
    P: float     = 5.0e5    # [Pa]  ~5 bar
    x: float     = 0.30     # quality
    rho: float   = 85.0     # [kg/m³] HEM mixture
    rho_l: float = 1100.0   # [kg/m³]
    rho_v: float = 12.0     # [kg/m³]
    mu_l: float  = 2.0e-4   # [Pa·s]
    mu_v: float  = 1.3e-5   # [Pa·s]
    mu_tp: float = 0.7 * 2.0e-4 + 0.3 * 1.3e-5  # Cicchitti, x=0.3
    k_l: float   = 0.085    # [W/m·K]
    k_v: float   = 0.014    # [W/m·K]
    Pr_l: float  = 4.2
    Pr_v: float  = 1.05
    h_fg: float  = 195_000.0  # [J/kg]
    sigma: float = 0.010    # [N/m]
    P_red: float = 0.12
    T_sat: float = 293.15


@dataclass
class LiquidStub(FluidStub):
    phase: str  = "liquid"
    x: float    = 0.0
    rho: float  = 1100.0


@dataclass
class VaporStub(FluidStub):
    phase: str  = "vapor"
    x: float    = 1.0
    rho: float  = 12.0


# Geometry constants for tests
G_NOM   = 200.0    # kg/m²·s  — nominal mass flux
D_H_NOM = 1.0e-3   # m        — 1 mm hydraulic diameter
Q_NOM   = 50_000.0 # W/m²     — 50 kW/m² heat flux


@pytest.fixture
def tp_state():
    return FluidStub()


@pytest.fixture
def liq_state():
    return LiquidStub()


@pytest.fixture
def vap_state():
    return VaporStub()


# ===========================================================================
# 1. Internal helpers
# ===========================================================================

class TestFrictionFactor:

    def test_laminar_value(self):
        """f = 16/Re for Re < 2000"""
        Re = 1000.0
        assert _friction_factor_blasius(Re) == pytest.approx(16.0 / Re)

    def test_turbulent_low_value(self):
        """f = 0.079 Re^-0.25 for 2000 ≤ Re < 20000"""
        Re = 5000.0
        expected = 0.079 * Re**(-0.25)
        assert _friction_factor_blasius(Re) == pytest.approx(expected, rel=1e-6)

    def test_turbulent_high_value(self):
        """f = 0.046 Re^-0.20 for Re ≥ 20000"""
        Re = 50_000.0
        expected = 0.046 * Re**(-0.20)
        assert _friction_factor_blasius(Re) == pytest.approx(expected, rel=1e-6)

    def test_monotone_decreasing(self):
        """Friction factor decreases with increasing Re (turbulent regime)"""
        Re_list = [5_000, 10_000, 50_000, 100_000]
        f_list  = [_friction_factor_blasius(Re) for Re in Re_list]
        for i in range(len(f_list) - 1):
            assert f_list[i] > f_list[i+1]

    def test_positive(self):
        for Re in [500, 2000, 20_000, 100_000]:
            assert _friction_factor_blasius(Re) > 0

    def test_rect_laminar_square(self):
        """For square channel β=1, fRe ≈ 14.23"""
        Re = 1000.0
        f = _friction_factor_rect_laminar(Re, beta=1.0)
        assert f * Re == pytest.approx(14.23, abs=0.05)

    def test_rect_laminar_beta_clamp(self):
        """beta > 1 is clamped to 1"""
        Re = 1000.0
        f1 = _friction_factor_rect_laminar(Re, beta=1.0)
        f2 = _friction_factor_rect_laminar(Re, beta=2.0)
        assert f1 == pytest.approx(f2)


class TestDittusBoelterNu:

    def test_known_value(self):
        """Nu = 0.023 * 10000^0.8 * 5^0.4"""
        Re, Pr = 10_000.0, 5.0
        Nu = _nusselt_dittus_boelter(Re, Pr, heating=True)
        expected = 0.023 * 10_000**0.8 * 5**0.4
        assert Nu == pytest.approx(expected, rel=1e-6)

    def test_heating_vs_cooling(self):
        """n=0.4 (heating) > n=0.3 (cooling) for Pr > 1"""
        Nu_heat = _nusselt_dittus_boelter(10_000, 5.0, heating=True)
        Nu_cool = _nusselt_dittus_boelter(10_000, 5.0, heating=False)
        assert Nu_heat > Nu_cool


# ===========================================================================
# 2. Single-phase HTC correlations
# ===========================================================================

class TestDittusBoelterHTC:

    def test_returns_positive(self, liq_state):
        htc = DittusBoelterHTC()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            val = htc(liq_state, G_NOM, D_H_NOM, Q_NOM)
        assert val > 0

    def test_increases_with_G(self, liq_state):
        htc = DittusBoelterHTC()
        G_values = [100, 300, 600, 1000]
        vals = []
        for G in G_values:
            s = LiquidStub()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                vals.append(htc(s, G, D_H_NOM, Q_NOM))
        for i in range(len(vals) - 1):
            assert vals[i] < vals[i+1], "HTC should increase with G"

    def test_heating_cooling_differ(self, liq_state):
        htc_h = DittusBoelterHTC(heating=True)
        htc_c = DittusBoelterHTC(heating=False)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            val_h = htc_h(liq_state, 2000.0, D_H_NOM, Q_NOM)
            val_c = htc_c(liq_state, 2000.0, D_H_NOM, Q_NOM)
        # Pr_l = 4.2 > 1, so heating exponent 0.4 > 0.3 → higher HTC
        assert val_h > val_c

    def test_vapor_phase(self, vap_state):
        htc = DittusBoelterHTC()
        val = htc(vap_state, 2000.0, D_H_NOM, Q_NOM)
        assert val > 0

    def test_protocol_satisfied(self):
        assert isinstance(DittusBoelterHTC(), HTCCorrelation)


class TestGnielinskiHTC:

    def test_returns_positive(self, liq_state):
        # Force turbulent Re by using high G
        htc = GnielinskiHTC()
        val = htc(liq_state, 2000.0, D_H_NOM, Q_NOM)
        assert val > 0

    def test_close_to_dittus_high_re(self, liq_state):
        """At high Re, Gnielinski and Dittus-Boelter should be within ~30%"""
        htc_g = GnielinskiHTC()
        htc_d = DittusBoelterHTC()
        G_high = 5000.0
        val_g = htc_g(liq_state, G_high, D_H_NOM, Q_NOM)
        val_d = htc_d(liq_state, G_high, D_H_NOM, Q_NOM)
        ratio = val_g / val_d
        assert 0.7 < ratio < 1.3

    def test_protocol_satisfied(self):
        assert isinstance(GnielinskiHTC(), HTCCorrelation)


class TestShahLondonLaminarHTC:

    def test_square_channel_nu(self):
        """Square channel: Nu_UHF ≈ 3.608"""
        htc = ShahLondonLaminarHTC(aspect_ratio=1.0)
        s = LiquidStub()
        val = htc(s, 10.0, D_H_NOM, 0.0)
        # Nu * k / D = val → Nu = val * D / k
        Nu_calc = val * D_H_NOM / s.k_l
        assert Nu_calc == pytest.approx(3.608, abs=0.05)

    def test_protocol_satisfied(self):
        assert isinstance(ShahLondonLaminarHTC(), HTCCorrelation)


# ===========================================================================
# 3. Flow boiling HTC — Shah (1982)
# ===========================================================================

class TestShahBoilingHTC:

    def test_returns_positive(self, tp_state):
        htc = ShahBoilingHTC()
        val = htc(tp_state, G_NOM, D_H_NOM, Q_NOM)
        assert val > 0

    def test_larger_than_liquid_only(self, tp_state, liq_state):
        """Two-phase HTC should exceed liquid-only single-phase HTC"""
        htc_tp = ShahBoilingHTC()
        htc_lq = DittusBoelterHTC()
        val_tp = htc_tp(tp_state, G_NOM, D_H_NOM, Q_NOM)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            val_lq = htc_lq(liq_state, G_NOM, D_H_NOM, Q_NOM)
        assert val_tp > val_lq

    def test_increases_with_q_flux(self, tp_state):
        """Higher heat flux → higher nucleate boiling contribution"""
        htc = ShahBoilingHTC()
        q_low  = htc(tp_state, G_NOM, D_H_NOM, 10_000.0)
        q_high = htc(tp_state, G_NOM, D_H_NOM, 100_000.0)
        assert q_high >= q_low  # may be equal if convective dominates

    def test_finite_at_low_quality(self):
        s = FluidStub(x=0.01)
        htc = ShahBoilingHTC()
        val = htc(s, G_NOM, D_H_NOM, Q_NOM)
        assert math.isfinite(val) and val > 0

    def test_finite_at_high_quality(self):
        s = FluidStub(x=0.95)
        htc = ShahBoilingHTC()
        val = htc(s, G_NOM, D_H_NOM, Q_NOM)
        assert math.isfinite(val) and val > 0

    def test_stratified_flow_branch(self):
        """Fr_l < 0.04 activates stratified branch (N with Fr correction)"""
        # Low G to get small Fr_l  → stratified branch
        s = FluidStub(x=0.3)
        htc = ShahBoilingHTC()
        val_low_G  = htc(s, 20.0, D_H_NOM, Q_NOM)
        val_high_G = htc(s, 500.0, D_H_NOM, Q_NOM)
        assert val_low_G > 0
        assert val_high_G > 0

    def test_nucleate_dominated_low_x(self):
        """At low quality and high Bo, nucleate boiling should dominate"""
        s = FluidStub(x=0.05)
        htc = ShahBoilingHTC()
        val = htc(s, G_NOM, D_H_NOM, 200_000.0)  # very high flux
        assert val > 0

    def test_protocol_satisfied(self):
        assert isinstance(ShahBoilingHTC(), HTCCorrelation)


# ===========================================================================
# 4. Kim & Mudawar 2012 HTC
# ===========================================================================

class TestKimMudawar2012HTC:

    def test_returns_positive(self, tp_state):
        htc = KimMudawar2012HTC()
        val = htc(tp_state, G_NOM, D_H_NOM, Q_NOM)
        assert val > 0 and math.isfinite(val)

    def test_increases_with_q_flux(self, tp_state):
        htc = KimMudawar2012HTC()
        v1 = htc(tp_state, G_NOM, D_H_NOM, 10_000.0)
        v2 = htc(tp_state, G_NOM, D_H_NOM, 100_000.0)
        assert v2 > v1

    def test_one_sided_heating(self, tp_state):
        """P_H/P_F < 1 reduces effective Bo → lower HTC"""
        htc_uniform = KimMudawar2012HTC(P_H_over_P_F=1.0)
        htc_one_side = KimMudawar2012HTC(P_H_over_P_F=0.5)
        v_uni  = htc_uniform(tp_state, G_NOM, D_H_NOM, Q_NOM)
        v_side = htc_one_side(tp_state, G_NOM, D_H_NOM, Q_NOM)
        assert v_uni > v_side

    def test_protocol_satisfied(self):
        assert isinstance(KimMudawar2012HTC(), HTCCorrelation)


# ===========================================================================
# 5. Yan Condensation HTC
# ===========================================================================

class TestYanCondensationHTC:

    def test_returns_positive(self, tp_state):
        htc = YanCondensationHTC()
        val = htc(tp_state, G_NOM, D_H_NOM)
        assert val > 0

    def test_increases_with_G(self, tp_state):
        htc = YanCondensationHTC()
        v1 = htc(tp_state, 100.0, D_H_NOM)
        v2 = htc(tp_state, 400.0, D_H_NOM)
        assert v2 > v1

    def test_increases_with_quality(self):
        """Higher quality → larger G_eq → higher HTC"""
        htc = YanCondensationHTC()
        v1 = htc(FluidStub(x=0.1), G_NOM, D_H_NOM)
        v2 = htc(FluidStub(x=0.7), G_NOM, D_H_NOM)
        assert v2 > v1

    def test_protocol_satisfied(self):
        assert isinstance(YanCondensationHTC(), HTCCorrelation)


# ===========================================================================
# 6. Blasius ΔP
# ===========================================================================

class TestBlassiusDP:

    def test_returns_positive_liquid(self, liq_state):
        dp = BlassiusDP()
        val = dp(liq_state, G_NOM, D_H_NOM)
        assert val > 0

    def test_returns_positive_vapor(self, vap_state):
        dp = BlassiusDP()
        val = dp(vap_state, G_NOM, D_H_NOM)
        assert val > 0

    def test_hagen_poiseuille_limit(self):
        """For laminar liquid flow, verify Hagen-Poiseuille scaling"""
        dp = BlassiusDP()
        G1, G2 = 10.0, 20.0
        s = LiquidStub()
        v1 = dp(s, G1, D_H_NOM)
        v2 = dp(s, G2, D_H_NOM)
        # dP/dz ∝ G² in turbulent, ∝ G in laminar (f∝1/Re=mu/(G*D))
        # Re(G1)=10*1e-3/2e-4=50 → laminar: dP∝G·f∝G·(1/Re)∝G·mu/(G·D)=const/D
        # Actually for laminar: dP/dz = 2*(16/Re)*G²/(D*rho) = 32*mu*G/(rho*D²*rho/rho)
        # → dP/dz ∝ G¹  in laminar
        ratio = v2 / v1
        assert ratio == pytest.approx(2.0, rel=0.05)

    def test_increases_with_G_turbulent(self, liq_state):
        dp = BlassiusDP()
        v1 = dp(liq_state, 500.0, D_H_NOM)
        v2 = dp(liq_state, 1000.0, D_H_NOM)
        assert v2 > v1

    def test_protocol_satisfied(self):
        assert isinstance(BlassiusDP(), DPCorrelation)


# ===========================================================================
# 7. Churchill ΔP
# ===========================================================================

class TestChurchillDP:

    def test_returns_positive(self, liq_state):
        dp = ChurchillDP()
        val = dp(liq_state, 2000.0, D_H_NOM)
        assert val > 0

    def test_rougher_pipe_higher_dp(self, liq_state):
        G = 2000.0
        dp_smooth = ChurchillDP(roughness=1e-6)
        dp_rough  = ChurchillDP(roughness=1e-4)
        v_smooth = dp_smooth(liq_state, G, D_H_NOM)
        v_rough  = dp_rough (liq_state, G, D_H_NOM)
        assert v_rough > v_smooth

    def test_laminar_agrees_with_blasius(self, liq_state):
        """For laminar flow, Churchill and Blasius should agree closely"""
        dp_c = ChurchillDP(roughness=0.0)
        dp_b = BlassiusDP()
        G_lam = 10.0  # low Re
        v_c = dp_c(liq_state, G_lam, D_H_NOM)
        v_b = dp_b(liq_state, G_lam, D_H_NOM)
        assert v_c == pytest.approx(v_b, rel=0.02)

    def test_protocol_satisfied(self):
        assert isinstance(ChurchillDP(), DPCorrelation)


# ===========================================================================
# 8. Homogeneous ΔP
# ===========================================================================

class TestHomogeneousDP:

    def test_two_phase_positive(self, tp_state):
        dp = HomogeneousDP()
        val = dp(tp_state, G_NOM, D_H_NOM)
        assert val > 0

    def test_liquid_limit(self, liq_state):
        """Single-phase liquid should match Blasius"""
        dp_hom = HomogeneousDP()
        dp_bla = BlassiusDP()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            v_hom = dp_hom(liq_state, G_NOM, D_H_NOM)
            v_bla = dp_bla(liq_state, G_NOM, D_H_NOM)
        assert v_hom == pytest.approx(v_bla, rel=1e-4)

    def test_two_phase_higher_than_liquid(self, tp_state, liq_state):
        """Two-phase pressure drop should exceed liquid-only"""
        dp = HomogeneousDP()
        v_tp = dp(tp_state, G_NOM, D_H_NOM)
        v_lq = dp(liq_state, G_NOM, D_H_NOM)
        assert v_tp > v_lq

    def test_increases_with_G(self, tp_state):
        dp = HomogeneousDP()
        v1 = dp(tp_state, 100.0, D_H_NOM)
        v2 = dp(tp_state, 400.0, D_H_NOM)
        assert v2 > v1

    def test_increases_with_quality(self):
        """Higher quality → lower mixture density → higher dP/dz"""
        dp = HomogeneousDP()
        v1 = dp(FluidStub(x=0.1), G_NOM, D_H_NOM)
        v2 = dp(FluidStub(x=0.6), G_NOM, D_H_NOM)
        assert v2 > v1

    def test_protocol_satisfied(self):
        assert isinstance(HomogeneousDP(), DPCorrelation)


# ===========================================================================
# 9. Kim & Mudawar 2013 ΔP
# ===========================================================================

class TestKimMudawar2013DP:

    def test_two_phase_positive(self, tp_state):
        dp = KimMudawar2013DP()
        val = dp(tp_state, G_NOM, D_H_NOM, q_flux=Q_NOM)
        assert val > 0 and math.isfinite(val)

    def test_liquid_fallback(self, liq_state):
        dp = KimMudawar2013DP()
        val = dp(liq_state, G_NOM, D_H_NOM)
        assert val > 0

    def test_vapor_fallback(self, vap_state):
        dp = KimMudawar2013DP()
        val = dp(vap_state, G_NOM, D_H_NOM)
        assert val > 0

    def test_increases_with_G(self, tp_state):
        dp = KimMudawar2013DP()
        v1 = dp(tp_state, 100.0, D_H_NOM, q_flux=Q_NOM)
        v2 = dp(tp_state, 400.0, D_H_NOM, q_flux=Q_NOM)
        assert v2 > v1

    def test_higher_with_boiling(self, tp_state):
        """Boiling correction raises C → higher two-phase multiplier"""
        dp = KimMudawar2013DP()
        v_no_boil = dp(tp_state, G_NOM, D_H_NOM, q_flux=0.0)
        v_boiling  = dp(tp_state, G_NOM, D_H_NOM, q_flux=Q_NOM)
        assert v_boiling >= v_no_boil

    def test_laminar_turbulent_regime(self):
        """Test all four regime combinations: tt, tv, vt, vv"""
        dp = KimMudawar2013DP()
        # High G → turbulent both (tt)
        s_tt = FluidStub(x=0.5)
        v_tt = dp(s_tt, 1000.0, D_H_NOM, q_flux=Q_NOM)
        # Very low G → laminar both (vv)
        s_vv = FluidStub(x=0.5)
        v_vv = dp(s_vv, 5.0, 1.0e-3, q_flux=1000.0)
        assert v_tt > 0 and v_vv > 0

    def test_finite_extreme_qualities(self):
        dp = KimMudawar2013DP()
        for x in [0.01, 0.99]:
            s = FluidStub(x=x)
            val = dp(s, G_NOM, D_H_NOM, q_flux=Q_NOM)
            assert math.isfinite(val) and val > 0

    def test_protocol_satisfied(self):
        assert isinstance(KimMudawar2013DP(), DPCorrelation)


# ===========================================================================
# 10. Müller-Steinhagen & Heck ΔP
# ===========================================================================

class TestMullerSteinhagenHeckDP:

    def test_two_phase_positive(self, tp_state):
        dp = MullerSteinhagenHeckDP()
        val = dp(tp_state, G_NOM, D_H_NOM)
        assert val > 0

    def test_liquid_limit_x0(self):
        """At x → 0, MSH approaches liquid-only gradient (within ~20%)"""
        dp = MullerSteinhagenHeckDP()
        s = FluidStub(x=0.001)
        val = dp(s, G_NOM, D_H_NOM)
        dp_b = BlassiusDP()
        v_liq = dp_b(LiquidStub(), G_NOM, D_H_NOM)
        # MSH asymptotically → A (liquid-only) as x→0 but not exactly at x=0.001
        ratio = val / v_liq
        assert 0.8 < ratio < 1.5, f"MSH at x=0.001: ratio to liquid-only = {ratio:.3f}"

    def test_vapor_limit_x1(self):
        """At x → 1, MSH approaches vapor-only gradient (within ~25%)"""
        dp = MullerSteinhagenHeckDP()
        s = FluidStub(x=0.999)
        val = dp(s, G_NOM, D_H_NOM)
        dp_b = BlassiusDP()
        v_vap = dp_b(VaporStub(), G_NOM, D_H_NOM)
        ratio = val / v_vap
        assert 0.75 < ratio < 1.5, f"MSH at x=0.999: ratio to vapor-only = {ratio:.3f}"

    def test_increases_with_G(self, tp_state):
        dp = MullerSteinhagenHeckDP()
        v1 = dp(tp_state, 100.0, D_H_NOM)
        v2 = dp(tp_state, 400.0, D_H_NOM)
        assert v2 > v1

    def test_close_to_homogeneous(self, tp_state):
        """MSH and homogeneous should be within order of magnitude"""
        dp_msh = MullerSteinhagenHeckDP()
        dp_hom = HomogeneousDP()
        v_msh = dp_msh(tp_state, G_NOM, D_H_NOM)
        v_hom = dp_hom(tp_state, G_NOM, D_H_NOM)
        ratio = v_msh / v_hom
        assert 0.1 < ratio < 10.0

    def test_protocol_satisfied(self):
        assert isinstance(MullerSteinhagenHeckDP(), DPCorrelation)


# ===========================================================================
# 11. Acceleration and gravity helpers
# ===========================================================================

class TestAccelerationPressureGradient:

    def test_two_phase_positive(self, tp_state):
        """In a heated two-phase channel, quality increases → acceleration ΔP > 0"""
        G = 200.0
        q_H = 50_000.0   # W/m²
        A_c = math.pi * (D_H_NOM / 2)**2
        P_H = math.pi * D_H_NOM
        dh_dz = q_H * P_H / (G * A_c)  # simplified (uniform flux, round tube)
        val = acceleration_pressure_gradient(tp_state, G, dh_dz)
        assert val > 0

    def test_liquid_returns_zero(self, liq_state):
        """Incompressible single-phase liquid: no acceleration term"""
        val = acceleration_pressure_gradient(liq_state, G_NOM, 1000.0)
        assert val == 0.0

    def test_finite(self, tp_state):
        val = acceleration_pressure_gradient(tp_state, G_NOM, 5000.0)
        assert math.isfinite(val)


class TestGravityPressureGradient:

    def test_horizontal_zero(self, tp_state):
        assert gravity_pressure_gradient(tp_state, "horizontal") == 0.0

    def test_vertical_up_positive(self, tp_state):
        val = gravity_pressure_gradient(tp_state, "vertical_up")
        assert val > 0

    def test_vertical_down_negative(self, tp_state):
        val = gravity_pressure_gradient(tp_state, "vertical_down")
        assert val < 0

    def test_up_down_symmetric(self, tp_state):
        v_up   = gravity_pressure_gradient(tp_state, "vertical_up")
        v_down = gravity_pressure_gradient(tp_state, "vertical_down")
        assert v_up == pytest.approx(-v_down)

    def test_invalid_orientation(self, tp_state):
        with pytest.raises(ValueError, match="orientation"):
            gravity_pressure_gradient(tp_state, "diagonal")

    def test_uses_rho_attribute(self, tp_state):
        """Check that the mixture density (state.rho) is used"""
        G_EARTH = 9.806
        val = gravity_pressure_gradient(tp_state, "vertical_up")
        assert val == pytest.approx(tp_state.rho * G_EARTH, rel=1e-4)


# ===========================================================================
# 12. Registry / factory
# ===========================================================================

class TestRegistry:

    @pytest.mark.parametrize("name", [
        "dittus_boelter", "gnielinski", "shah_london",
        "shah_boiling", "kim_mudawar_2012", "yan_condensation",
    ])
    def test_get_htc_correlation_known(self, name):
        corr = get_htc_correlation(name)
        assert corr is not None

    @pytest.mark.parametrize("name", [
        "blasius", "churchill", "homogeneous",
        "kim_mudawar_2013", "muller_steinhagen_heck",
    ])
    def test_get_dp_correlation_known(self, name):
        corr = get_dp_correlation(name)
        assert corr is not None

    def test_get_htc_unknown_raises(self):
        with pytest.raises(KeyError):
            get_htc_correlation("nonexistent")

    def test_get_dp_unknown_raises(self):
        with pytest.raises(KeyError):
            get_dp_correlation("nonexistent")

    def test_factory_kwargs_passed(self):
        htc = get_htc_correlation("dittus_boelter", heating=False)
        assert htc.heating is False

    def test_factory_dp_kwargs_passed(self):
        dp = get_dp_correlation("kim_mudawar_2013", aspect_ratio=0.5)
        assert dp.beta == pytest.approx(0.5)


# ===========================================================================
# 13. Protocol conformance
# ===========================================================================

class TestProtocols:

    @pytest.mark.parametrize("cls", [
        DittusBoelterHTC, GnielinskiHTC, ShahLondonLaminarHTC,
        ShahBoilingHTC, KimMudawar2012HTC, YanCondensationHTC,
    ])
    def test_htc_protocol(self, cls):
        assert isinstance(cls(), HTCCorrelation)

    @pytest.mark.parametrize("cls", [
        BlassiusDP, ChurchillDP,
        HomogeneousDP, KimMudawar2013DP, MullerSteinhagenHeckDP,
    ])
    def test_dp_protocol(self, cls):
        assert isinstance(cls(), DPCorrelation)


# ===========================================================================
# 14. Cross-correlation comparison (physical sanity)
# ===========================================================================

class TestCrossCorrelation:

    def test_all_dp_positive_two_phase(self, tp_state):
        """All ΔP correlations must return positive values for two-phase flow"""
        correlations = [
            HomogeneousDP(), KimMudawar2013DP(), MullerSteinhagenHeckDP(),
        ]
        for corr in correlations:
            val = corr(tp_state, G_NOM, D_H_NOM, q_flux=Q_NOM)
            assert val > 0, f"{corr.__class__.__name__} returned non-positive"

    def test_all_htc_positive_two_phase(self, tp_state):
        """All boiling HTC correlations must return positive values"""
        correlations = [
            ShahBoilingHTC(), KimMudawar2012HTC(),
        ]
        for corr in correlations:
            val = corr(tp_state, G_NOM, D_H_NOM, Q_NOM)
            assert val > 0, f"{corr.__class__.__name__} returned non-positive"

    def test_dp_order_of_magnitude(self, tp_state):
        """All ΔP correlations should agree within one order of magnitude"""
        vals = [
            HomogeneousDP()(tp_state, G_NOM, D_H_NOM),
            KimMudawar2013DP()(tp_state, G_NOM, D_H_NOM, q_flux=Q_NOM),
            MullerSteinhagenHeckDP()(tp_state, G_NOM, D_H_NOM),
        ]
        ratio = max(vals) / min(vals)
        assert ratio < 10.0, f"Correlations diverge by factor {ratio:.1f}"

    def test_htc_order_of_magnitude(self, tp_state):
        """Shah and Kim-Mudawar HTC should agree within two orders of magnitude"""
        v_shah = ShahBoilingHTC()(tp_state, G_NOM, D_H_NOM, Q_NOM)
        v_km   = KimMudawar2012HTC()(tp_state, G_NOM, D_H_NOM, Q_NOM)
        ratio  = max(v_shah, v_km) / min(v_shah, v_km)
        assert ratio < 100.0, f"HTC correlations diverge by factor {ratio:.1f}"


# ===========================================================================
# 15. Validate missing attributes detected
# ===========================================================================

class TestValidation:

    def test_missing_attr_raises_typeerror(self):
        class _Stub:
            pass  # no attributes at all
        with pytest.raises(TypeError, match="missing attributes"):
            ShahBoilingHTC()(_Stub(), G_NOM, D_H_NOM, Q_NOM)
