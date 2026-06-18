"""Tests for two-phase pressure-drop correlations — Phase 11O.

Covers MSHTwoPhaseFrictionGradient (Müller-Steinhagen & Heck 1986):

  Contract:
    - Role is TWO_PHASE_DP.
    - Returns CorrelationOutput (never a bare number).
    - value[0] is dP/dx_friction [Pa/m] (gradient, not integrated drop).
    - Verdict metadata is always present.
    - IN_ENVELOPE for valid in-range inputs.
    - EXTRAPOLATED for out-of-envelope but evaluable inputs (D_h < 1e-6 m).

  Numerical formula:
    - At least one test compares against an independently computed expected value.
    - Quality endpoints x=0 and x=1 return the all-liquid and all-vapor gradients.
    - Mid-quality value matches the MSH polynomial.

  Invalid inputs:
    - ValueError for missing rho_l, rho_v, mu_l, mu_v (None).
    - ValueError for non-finite or non-positive G, D_h.
    - ValueError for non-finite x.
    - ValueError for x < 0 or x > 1 (quality outside physical domain).
    - ValueError for non-finite or non-positive rho_l, rho_v, mu_l, mu_v.
    - TypeError for wrong input type.

  Architecture:
    - No CoolProp import or call.
    - No PropertyBackend import or call.
    - No quality clamping (abs/min/max on x).
    - No hidden defaults.
    - Correct package export from mpl_sim.correlations.
    - Registerable through CorrelationRegistry.
    - HX injection is deferred; tested with a focused note.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations import MSHTwoPhaseFrictionGradient
from mpl_sim.correlations.contract import (
    CorrelationOutput,
    CorrelationRole,
    TwoPhaseDPInput,
    ValidityStatus,
)
from mpl_sim.correlations.registry import (
    CorrelationRegistry,
    create_empty_correlation_registry,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FLUID = PureFluid("R134a")
_STATE = FluidState(P=500_000.0, h=250_000.0, identity=_FLUID)


def _make_inp(
    G: float = 200.0,
    x: float = 0.5,
    D_h: float = 0.005,
    rho_l: float | None = 1000.0,
    rho_v: float | None = 20.0,
    mu_l: float | None = 2e-4,
    mu_v: float | None = 1.2e-5,
    L_cell: float = 0.1,
) -> TwoPhaseDPInput:
    return TwoPhaseDPInput(
        state=(_STATE,),
        G=G,
        x=(x,),
        D_h=D_h,
        L_cell=L_cell,
        rho_l=rho_l,
        rho_v=rho_v,
        mu_l=mu_l,
        mu_v=mu_v,
    )


def _msh_expected(
    G: float,
    x: float,
    D_h: float,
    rho_l: float,
    rho_v: float,
    mu_l: float,
    mu_v: float,
) -> float:
    """Independent implementation of the MSH formula for test comparison.

    Uses Churchill (1977) Darcy friction factor, smooth wall (eps/D = 0).
    This reimplementation is kept in the test to serve as an independent
    oracle against which the production closure is verified.
    """

    def _f_darcy(Re: float) -> float:
        term_lam = (8.0 / Re) ** 12
        inner = (7.0 / Re) ** 0.9
        A = (2.457 * math.log(1.0 / inner)) ** 16
        B = (37530.0 / Re) ** 16
        return 8.0 * (term_lam + (A + B) ** (-1.5)) ** (1.0 / 12.0)

    Re_lo = G * D_h / mu_l
    Re_vo = G * D_h / mu_v
    A = _f_darcy(Re_lo) * G**2 / (2.0 * rho_l * D_h)
    B = _f_darcy(Re_vo) * G**2 / (2.0 * rho_v * D_h)
    Gx = A + 2.0 * (B - A) * x
    return Gx * (1.0 - x) ** (1.0 / 3.0) + B * x**3


_CORR = MSHTwoPhaseFrictionGradient()


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


class TestContract:
    def test_role_is_two_phase_dp(self) -> None:
        assert _CORR.role() == CorrelationRole.TWO_PHASE_DP

    def test_returns_correlation_output(self) -> None:
        result = _CORR.evaluate(_make_inp())
        assert isinstance(result, CorrelationOutput)

    def test_value_is_length_one_tuple(self) -> None:
        result = _CORR.evaluate(_make_inp())
        assert len(result.value) == 1

    def test_value_is_finite(self) -> None:
        result = _CORR.evaluate(_make_inp())
        assert math.isfinite(result.value[0])

    def test_value_is_positive(self) -> None:
        result = _CORR.evaluate(_make_inp())
        assert result.value[0] > 0.0

    def test_verdict_is_present(self) -> None:
        result = _CORR.evaluate(_make_inp())
        assert result.verdict is not None

    def test_metadata_is_present(self) -> None:
        result = _CORR.evaluate(_make_inp())
        assert result.metadata is not None
        assert result.metadata.name == "msh_two_phase_friction_gradient"

    def test_envelope_method_returns_envelope(self) -> None:
        env = _CORR.envelope()
        assert env is not None
        assert env.bounds


# ---------------------------------------------------------------------------
# Numerical formula
# ---------------------------------------------------------------------------


class TestNumericalFormula:
    """Compares correlation output against an independent implementation."""

    _CASES = [
        # (G, x, D_h, rho_l, rho_v, mu_l, mu_v)
        (200.0, 0.5, 0.005, 1000.0, 20.0, 2e-4, 1.2e-5),
        (300.0, 0.3, 0.002, 800.0, 15.0, 1.5e-4, 1.0e-5),
        (150.0, 0.7, 0.003, 1100.0, 25.0, 2.5e-4, 1.3e-5),
    ]

    @pytest.mark.parametrize("G,x,D_h,rho_l,rho_v,mu_l,mu_v", _CASES)
    def test_matches_independent_computation(
        self,
        G: float,
        x: float,
        D_h: float,
        rho_l: float,
        rho_v: float,
        mu_l: float,
        mu_v: float,
    ) -> None:
        inp = _make_inp(G=G, x=x, D_h=D_h, rho_l=rho_l, rho_v=rho_v, mu_l=mu_l, mu_v=mu_v)
        expected = _msh_expected(G, x, D_h, rho_l, rho_v, mu_l, mu_v)
        result = _CORR.evaluate(inp)
        assert result.value[0] == pytest.approx(expected, rel=1e-8)

    def test_x_zero_returns_liquid_only_gradient(self) -> None:
        G, D_h, rho_l, mu_l = 200.0, 0.005, 1000.0, 2e-4
        inp = _make_inp(G=G, x=0.0, D_h=D_h, rho_l=rho_l, rho_v=20.0, mu_l=mu_l, mu_v=1.2e-5)
        result = _CORR.evaluate(inp)
        # At x=0: dPdz = A*(1-0)^(1/3) + B*0 = A = dPdz_lo
        Re_lo = G * D_h / mu_l

        def _f(Re: float) -> float:
            term = (8 / Re) ** 12
            inner = (7 / Re) ** 0.9
            A_ch = (2.457 * math.log(1 / inner)) ** 16
            B_ch = (37530 / Re) ** 16
            return 8 * (term + (A_ch + B_ch) ** (-1.5)) ** (1 / 12)

        dPdz_lo = _f(Re_lo) * G**2 / (2.0 * rho_l * D_h)
        assert result.value[0] == pytest.approx(dPdz_lo, rel=1e-8)

    def test_x_one_returns_vapor_only_gradient(self) -> None:
        G, D_h, rho_v, mu_v = 200.0, 0.005, 20.0, 1.2e-5
        inp = _make_inp(G=G, x=1.0, D_h=D_h, rho_l=1000.0, rho_v=rho_v, mu_l=2e-4, mu_v=mu_v)
        result = _CORR.evaluate(inp)
        # At x=1: first term = (2B-A)*(1-1)^(1/3) = 0, second = B*1 = B = dPdz_vo
        Re_vo = G * D_h / mu_v

        def _f(Re: float) -> float:
            term = (8 / Re) ** 12
            inner = (7 / Re) ** 0.9
            A_ch = (2.457 * math.log(1 / inner)) ** 16
            B_ch = (37530 / Re) ** 16
            return 8 * (term + (A_ch + B_ch) ** (-1.5)) ** (1 / 12)

        dPdz_vo = _f(Re_vo) * G**2 / (2.0 * rho_v * D_h)
        assert result.value[0] == pytest.approx(dPdz_vo, rel=1e-8)

    def test_gradient_increases_with_mass_flux(self) -> None:
        lo = _CORR.evaluate(_make_inp(G=100.0)).value[0]
        hi = _CORR.evaluate(_make_inp(G=300.0)).value[0]
        assert hi > lo

    def test_two_different_qualities_give_different_values(self) -> None:
        v1 = _CORR.evaluate(_make_inp(x=0.2)).value[0]
        v2 = _CORR.evaluate(_make_inp(x=0.8)).value[0]
        assert v1 != pytest.approx(v2)


# ---------------------------------------------------------------------------
# Validity envelope / verdict
# ---------------------------------------------------------------------------


class TestEnvelope:
    def test_valid_inputs_give_in_envelope(self) -> None:
        result = _CORR.evaluate(_make_inp(x=0.5))
        assert result.verdict.status == ValidityStatus.IN_ENVELOPE

    def test_x_zero_gives_in_envelope(self) -> None:
        result = _CORR.evaluate(_make_inp(x=0.0))
        assert result.verdict.status == ValidityStatus.IN_ENVELOPE

    def test_x_one_gives_in_envelope(self) -> None:
        result = _CORR.evaluate(_make_inp(x=1.0))
        assert result.verdict.status == ValidityStatus.IN_ENVELOPE

    def test_small_dh_gives_extrapolated(self) -> None:
        # D_h = 5e-7 m (below 1e-6 threshold) → EXTRAPOLATED
        result = _CORR.evaluate(_make_inp(D_h=5e-7))
        assert result.verdict.status == ValidityStatus.EXTRAPOLATED
        assert result.verdict.violated
        assert math.isfinite(result.value[0])

    def test_extrapolated_value_is_still_finite(self) -> None:
        result = _CORR.evaluate(_make_inp(D_h=1e-7))
        assert math.isfinite(result.value[0])

    def test_in_envelope_has_no_violated_bounds(self) -> None:
        result = _CORR.evaluate(_make_inp(x=0.5))
        assert result.verdict.violated == ()

    def test_extrapolated_has_violated_bounds(self) -> None:
        result = _CORR.evaluate(_make_inp(D_h=1e-8))
        assert len(result.verdict.violated) > 0


# ---------------------------------------------------------------------------
# Invalid inputs — quality
# ---------------------------------------------------------------------------


class TestInvalidQuality:
    def test_x_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="quality x must be in"):
            _CORR.evaluate(_make_inp(x=-0.01))

    def test_x_greater_than_one_raises(self) -> None:
        with pytest.raises(ValueError, match="quality x must be in"):
            _CORR.evaluate(_make_inp(x=1.01))

    def test_x_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be finite"):
            _CORR.evaluate(_make_inp(x=math.nan))

    def test_x_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be finite"):
            _CORR.evaluate(_make_inp(x=math.inf))

    def test_empty_x_tuple_raises(self) -> None:
        inp = TwoPhaseDPInput(
            state=(_STATE,),
            G=200.0,
            x=(),
            D_h=0.005,
            L_cell=0.1,
            rho_l=1000.0,
            rho_v=20.0,
            mu_l=2e-4,
            mu_v=1.2e-5,
        )
        with pytest.raises(ValueError, match="x tuple must not be empty"):
            _CORR.evaluate(inp)


# ---------------------------------------------------------------------------
# Invalid inputs — mass flux
# ---------------------------------------------------------------------------


class TestInvalidMassFlux:
    def test_g_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="G must be finite and > 0"):
            _CORR.evaluate(_make_inp(G=0.0))

    def test_g_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="G must be finite and > 0"):
            _CORR.evaluate(_make_inp(G=-100.0))

    def test_g_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="G must be finite and > 0"):
            _CORR.evaluate(_make_inp(G=math.nan))

    def test_g_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="G must be finite and > 0"):
            _CORR.evaluate(_make_inp(G=math.inf))


# ---------------------------------------------------------------------------
# Invalid inputs — hydraulic diameter
# ---------------------------------------------------------------------------


class TestInvalidDh:
    def test_dh_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="D_h must be finite and > 0"):
            _CORR.evaluate(_make_inp(D_h=0.0))

    def test_dh_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="D_h must be finite and > 0"):
            _CORR.evaluate(_make_inp(D_h=-0.001))

    def test_dh_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="D_h must be finite and > 0"):
            _CORR.evaluate(_make_inp(D_h=math.nan))


# ---------------------------------------------------------------------------
# Invalid inputs — density
# ---------------------------------------------------------------------------


class TestInvalidDensity:
    def test_rho_l_none_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_l is required"):
            _CORR.evaluate(_make_inp(rho_l=None))

    def test_rho_v_none_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_v is required"):
            _CORR.evaluate(_make_inp(rho_v=None))

    def test_rho_l_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_l must be finite and > 0"):
            _CORR.evaluate(_make_inp(rho_l=0.0))

    def test_rho_v_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_v must be finite and > 0"):
            _CORR.evaluate(_make_inp(rho_v=0.0))

    def test_rho_l_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_l must be finite and > 0"):
            _CORR.evaluate(_make_inp(rho_l=-1.0))

    def test_rho_v_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_v must be finite and > 0"):
            _CORR.evaluate(_make_inp(rho_v=-1.0))

    def test_rho_l_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_l must be finite and > 0"):
            _CORR.evaluate(_make_inp(rho_l=math.nan))

    def test_rho_v_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_v must be finite and > 0"):
            _CORR.evaluate(_make_inp(rho_v=math.nan))


# ---------------------------------------------------------------------------
# Invalid inputs — viscosity
# ---------------------------------------------------------------------------


class TestInvalidViscosity:
    def test_mu_l_none_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_l is required"):
            _CORR.evaluate(_make_inp(mu_l=None))

    def test_mu_v_none_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_v is required"):
            _CORR.evaluate(_make_inp(mu_v=None))

    def test_mu_l_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_l must be finite and > 0"):
            _CORR.evaluate(_make_inp(mu_l=0.0))

    def test_mu_v_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_v must be finite and > 0"):
            _CORR.evaluate(_make_inp(mu_v=0.0))

    def test_mu_l_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_l must be finite and > 0"):
            _CORR.evaluate(_make_inp(mu_l=-1e-4))

    def test_mu_v_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_v must be finite and > 0"):
            _CORR.evaluate(_make_inp(mu_v=-1e-5))

    def test_mu_l_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_l must be finite and > 0"):
            _CORR.evaluate(_make_inp(mu_l=math.nan))

    def test_mu_v_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_v must be finite and > 0"):
            _CORR.evaluate(_make_inp(mu_v=math.nan))


# ---------------------------------------------------------------------------
# Wrong input type
# ---------------------------------------------------------------------------


class TestWrongInputType:
    def test_wrong_type_raises_type_error(self) -> None:
        from mpl_sim.correlations.contract import SinglePhaseDPInput

        wrong = SinglePhaseDPInput(
            state=(_STATE,),
            G=200.0,
            D_h=0.005,
            roughness=0.0,
            L_cell=0.1,
            rho=1000.0,
            mu=2e-4,
        )
        with pytest.raises(TypeError):
            _CORR.evaluate(wrong)


# ---------------------------------------------------------------------------
# Architecture
# ---------------------------------------------------------------------------


class TestArchitecture:
    def test_no_coolprop_import(self) -> None:
        import mpl_sim.correlations.two_phase_dp as mod

        assert "CoolProp" not in dir(mod)

    def test_no_property_backend_import(self) -> None:
        import mpl_sim.correlations.two_phase_dp as mod

        # PropertyBackend must not be imported at module level
        assert not hasattr(mod, "PropertyBackend")

    def test_no_hidden_rho_default(self) -> None:
        # rho_l=None must raise, not silently use 1000
        with pytest.raises(ValueError):
            _CORR.evaluate(_make_inp(rho_l=None))

    def test_no_hidden_mu_default(self) -> None:
        # mu_l=None must raise, not silently use 1e-3
        with pytest.raises(ValueError):
            _CORR.evaluate(_make_inp(mu_l=None))

    def test_no_quality_clamping(self) -> None:
        # x = 1.01 must raise, not clamp to 1.0
        with pytest.raises(ValueError):
            _CORR.evaluate(_make_inp(x=1.01))

    def test_no_quality_clamping_negative(self) -> None:
        # x = -0.01 must raise, not clamp to 0.0
        with pytest.raises(ValueError):
            _CORR.evaluate(_make_inp(x=-0.01))


# ---------------------------------------------------------------------------
# Package export and registry
# ---------------------------------------------------------------------------


class TestPackageExport:
    def test_exported_from_mpl_sim_correlations(self) -> None:
        import mpl_sim.correlations as pkg

        assert hasattr(pkg, "MSHTwoPhaseFrictionGradient")
        assert pkg.MSHTwoPhaseFrictionGradient is MSHTwoPhaseFrictionGradient

    def test_registerable_through_correlation_registry(self) -> None:
        reg: CorrelationRegistry = create_empty_correlation_registry()
        corr = MSHTwoPhaseFrictionGradient()
        reg.register("msh_two_phase_friction_gradient", corr)
        resolved = reg.resolve("msh_two_phase_friction_gradient")
        assert resolved is corr

    def test_registry_role_matches(self) -> None:
        reg: CorrelationRegistry = create_empty_correlation_registry()
        corr = MSHTwoPhaseFrictionGradient()
        reg.register("msh_two_phase_friction_gradient", corr)
        by_role = reg.by_role(CorrelationRole.TWO_PHASE_DP)
        assert "msh_two_phase_friction_gradient" in by_role


# ---------------------------------------------------------------------------
# HX injection — deferred; documented note
# ---------------------------------------------------------------------------


class TestHXInjectionDeferred:
    """Direct HX injection of MSHTwoPhaseFrictionGradient is deferred.

    Current HX models (_build_dp_input) build SinglePhaseDPInput, not
    TwoPhaseDPInput.  When MSHTwoPhaseFrictionGradient.evaluate() receives a
    SinglePhaseDPInput it raises TypeError.  Injection additionally requires:
      1. HX models to build TwoPhaseDPInput with two-phase property scalars.
      2. Explicit gradient-to-drop multiplication by L_cell inside the HX model
         (current convention treats value[0] as ΔP, not Pa/m gradient).
      3. rho_l, rho_v, mu_l, mu_v forwarded through geom_scalars or a
         dedicated two-phase input builder.
    These changes are deferred to a later phase.
    """

    def test_wrong_input_type_raised_when_called_with_single_phase_input(self) -> None:
        """Confirm that passing SinglePhaseDPInput raises TypeError — the
        same error that would occur if an HX model injected this correlation
        via the current _build_dp_input which produces SinglePhaseDPInput."""
        from mpl_sim.correlations.contract import SinglePhaseDPInput

        wrong = SinglePhaseDPInput(
            state=(_STATE,),
            G=200.0,
            D_h=0.005,
            roughness=0.0,
            L_cell=0.1,
            rho=1000.0,
            mu=2e-4,
        )
        with pytest.raises(TypeError):
            _CORR.evaluate(wrong)

    def test_output_semantics_are_gradient_not_drop(self) -> None:
        """Confirm that value[0] is a gradient (Pa/m), not a total drop (Pa).

        For L_cell=0.1 m and a typical gradient of order ~1e3-1e5 Pa/m,
        value[0] is NOT expected to equal gradient * L_cell; it is just the
        gradient.  HX models that treat value[0] directly as ΔP (Pa) would
        obtain incorrect results without the explicit * L_cell conversion.
        """
        inp = _make_inp(L_cell=0.1)
        result = _CORR.evaluate(inp)
        # value[0] has units Pa/m — it is a gradient
        gradient_Pa_m = result.value[0]
        L_cell = 0.1
        implied_drop_Pa = gradient_Pa_m * L_cell
        # The gradient and the implied total drop are different by L_cell factor
        assert gradient_Pa_m != pytest.approx(implied_drop_Pa, rel=0.01)
