"""Tests for Phase 2B — CoolPropBackend.

Acceptance criteria (TEST_PLAN_V1 §5.2–§5.6, INTERFACE_SPEC §3.3, [F6], [F13]):

- CoolPropBackend is a concrete PropertyBackend.
- provides() returns True for VECTOR_QUERIES, SATURATION_PROPERTIES, SURFACE_TENSION.
- provides() returns False for DERIVATIVES, ELECTRICAL_CONDUCTIVITY, RELATIVE_PERMITTIVITY.
- valid_range() returns finite P and h bounds for a known PureFluid.
- valid_range() returns all-None bounds for Mixture and CustomFluid.
- query() returns physically reasonable values for T, RHO, MU, K, CP, PHASE.
- query() returns UNAVAILABLE for X when queried at a single-phase state.
- query() returns quality in [0, 1] for X at a two-phase state.
- query() returns consistent H_F, H_G, H_FG at saturation.
- query() returns T_SAT and SIGMA at saturation.
- query() returns OUT_OF_RANGE (with NaN) for physically impossible (P, h).
- query() returns UNAVAILABLE for Mixture / CustomFluid identities.
- query() returns UNAVAILABLE for SIGMA_E and EPS_R.
- query_derivative() always returns UNAVAILABLE.
- Vector query (length > 1) produces per-element results identical to scalar queries.
- CoolProp is the only module that loads CoolProp (import-boundary guard).
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

from mpl_sim.core.fluid_identity import CustomFluid, Mixture, PureFluid
from mpl_sim.properties import CoolPropBackend
from mpl_sim.properties.backend import (
    BackendCapability,
    PhaseLabel,
    PropertyName,
    QueryStatus,
    ValidRange,
)

# ---------------------------------------------------------------------------
# Test fixtures and shared state
# ---------------------------------------------------------------------------

_R134A = PureFluid("R134a")

# Subcooled liquid: P=8 bar, h well below h_f at 8 bar
_P_LIQ = np.array([8.0e5])
_H_LIQ = np.array([200_000.0])  # ~273 K subcooled

# Superheated vapor: P=8 bar, h well above h_g at 8 bar
_P_VAP = np.array([8.0e5])
_H_VAP = np.array([450_000.0])  # ~338 K superheated

# Two-phase: P=6 bar, h at ~50% quality
# h_f(6 bar) ≈ 229682, h_g(6 bar) ≈ 410571 → midpoint ≈ 320127
_P_2PH = np.array([6.0e5])
_H_2PH = np.array([320_127.0])

# Saturation pressure for saturation-property queries
_P_SAT = np.array([6.0e5])  # 6 bar

# Physically impossible: near-vacuum pressure with very low enthalpy
_P_OOR = np.array([500.0])  # below triple-point pressure of R134a
_H_OOR = np.array([1_000.0])


@pytest.fixture(scope="module")
def backend() -> CoolPropBackend:
    return CoolPropBackend()


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


class TestInstantiation:
    def test_can_instantiate(self):
        b = CoolPropBackend()
        assert b is not None

    def test_is_property_backend(self):
        from mpl_sim.properties.backend import PropertyBackend

        assert isinstance(CoolPropBackend(), PropertyBackend)


# ---------------------------------------------------------------------------
# provides() — capability flags
# ---------------------------------------------------------------------------


class TestProvides:
    def test_vector_queries(self, backend: CoolPropBackend):
        assert backend.provides(BackendCapability.VECTOR_QUERIES) is True

    def test_saturation_properties(self, backend: CoolPropBackend):
        assert backend.provides(BackendCapability.SATURATION_PROPERTIES) is True

    def test_surface_tension(self, backend: CoolPropBackend):
        assert backend.provides(BackendCapability.SURFACE_TENSION) is True

    def test_derivatives_not_supported(self, backend: CoolPropBackend):
        assert backend.provides(BackendCapability.DERIVATIVES) is False

    def test_electrical_conductivity_not_supported(self, backend: CoolPropBackend):
        assert backend.provides(BackendCapability.ELECTRICAL_CONDUCTIVITY) is False

    def test_relative_permittivity_not_supported(self, backend: CoolPropBackend):
        assert backend.provides(BackendCapability.RELATIVE_PERMITTIVITY) is False


# ---------------------------------------------------------------------------
# valid_range()
# ---------------------------------------------------------------------------


class TestValidRange:
    def test_returns_valid_range_object(self, backend: CoolPropBackend):
        vr = backend.valid_range(_R134A)
        assert isinstance(vr, ValidRange)

    def test_r134a_bounds_are_finite(self, backend: CoolPropBackend):
        vr = backend.valid_range(_R134A)
        assert vr.P_min is not None and np.isfinite(vr.P_min)
        assert vr.P_max is not None and np.isfinite(vr.P_max)
        assert vr.h_min is not None and np.isfinite(vr.h_min)
        assert vr.h_max is not None and np.isfinite(vr.h_max)

    def test_r134a_p_range_is_ordered(self, backend: CoolPropBackend):
        vr = backend.valid_range(_R134A)
        assert vr.P_min < vr.P_max  # type: ignore[operator]

    def test_r134a_h_range_is_ordered(self, backend: CoolPropBackend):
        vr = backend.valid_range(_R134A)
        assert vr.h_min < vr.h_max  # type: ignore[operator]

    def test_r134a_p_min_near_triple_point(self, backend: CoolPropBackend):
        vr = backend.valid_range(_R134A)
        assert vr.P_min == pytest.approx(389.56, rel=1e-3)  # type: ignore[operator]

    def test_mixture_returns_all_none(self, backend: CoolPropBackend):
        m = Mixture((("R134a", 0.5), ("R32", 0.5)))
        vr = backend.valid_range(m)
        assert vr.P_min is None
        assert vr.P_max is None
        assert vr.h_min is None
        assert vr.h_max is None

    def test_custom_fluid_returns_all_none(self, backend: CoolPropBackend):
        vr = backend.valid_range(CustomFluid("my_fluid"))
        assert vr.P_min is None


# ---------------------------------------------------------------------------
# query() — temperature
# ---------------------------------------------------------------------------


class TestQueryTemperature:
    def test_liquid_temperature_is_reasonable(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.T, _P_LIQ, _H_LIQ, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == pytest.approx(273.06, rel=1e-3)

    def test_vapor_temperature_is_reasonable(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.T, _P_VAP, _H_VAP, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == pytest.approx(338.16, rel=1e-3)

    def test_two_phase_temperature_equals_t_sat(self, backend: CoolPropBackend):
        result_t = backend.query(PropertyName.T, _P_2PH, _H_2PH, _R134A)
        result_ts = backend.query(PropertyName.T_SAT, _P_SAT, _H_2PH, _R134A)
        assert result_t.status[0] == QueryStatus.OK
        assert result_ts.status[0] == QueryStatus.OK
        assert result_t.values[0] == pytest.approx(result_ts.values[0], rel=1e-6)


# ---------------------------------------------------------------------------
# query() — density
# ---------------------------------------------------------------------------


class TestQueryDensity:
    def test_liquid_density_is_high(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.RHO, _P_LIQ, _H_LIQ, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == pytest.approx(1297.05, rel=1e-3)

    def test_vapor_density_is_low(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.RHO, _P_VAP, _H_VAP, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] < 100.0  # kg/m³, vapor is much less dense


# ---------------------------------------------------------------------------
# query() — transport properties
# ---------------------------------------------------------------------------


class TestQueryTransport:
    def test_viscosity_liquid(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.MU, _P_LIQ, _H_LIQ, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == pytest.approx(2.687e-4, rel=1e-2)

    def test_thermal_conductivity_liquid(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.K, _P_LIQ, _H_LIQ, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == pytest.approx(0.09237, rel=1e-2)

    def test_cp_liquid(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.CP, _P_LIQ, _H_LIQ, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == pytest.approx(1338.0, rel=1e-2)


# ---------------------------------------------------------------------------
# query() — phase label
# ---------------------------------------------------------------------------


class TestQueryPhase:
    def test_liquid_phase_label(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.PHASE, _P_LIQ, _H_LIQ, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == float(PhaseLabel.LIQUID.value)

    def test_vapor_phase_label(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.PHASE, _P_VAP, _H_VAP, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == float(PhaseLabel.VAPOR.value)

    def test_two_phase_label(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.PHASE, _P_2PH, _H_2PH, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == float(PhaseLabel.TWO_PHASE.value)


# ---------------------------------------------------------------------------
# query() — vapour quality (X)
# ---------------------------------------------------------------------------


class TestQueryQuality:
    def test_two_phase_quality_near_half(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.X, _P_2PH, _H_2PH, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == pytest.approx(0.5, abs=0.01)

    def test_liquid_quality_is_unavailable(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.X, _P_LIQ, _H_LIQ, _R134A)
        assert result.status[0] == QueryStatus.UNAVAILABLE
        assert np.isnan(result.values[0])

    def test_vapor_quality_is_unavailable(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.X, _P_VAP, _H_VAP, _R134A)
        assert result.status[0] == QueryStatus.UNAVAILABLE
        assert np.isnan(result.values[0])


# ---------------------------------------------------------------------------
# query() — saturation properties (H_F, H_G, H_FG, T_SAT, SIGMA)
# ---------------------------------------------------------------------------


class TestQuerySaturation:
    def test_h_f_is_finite(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.H_F, _P_SAT, _H_2PH, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == pytest.approx(229_682.0, rel=1e-3)

    def test_h_g_is_finite(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.H_G, _P_SAT, _H_2PH, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == pytest.approx(410_571.0, rel=1e-3)

    def test_h_fg_equals_h_g_minus_h_f(self, backend: CoolPropBackend):
        r_f = backend.query(PropertyName.H_F, _P_SAT, _H_2PH, _R134A)
        r_g = backend.query(PropertyName.H_G, _P_SAT, _H_2PH, _R134A)
        r_fg = backend.query(PropertyName.H_FG, _P_SAT, _H_2PH, _R134A)
        assert r_fg.status[0] == QueryStatus.OK
        expected = r_g.values[0] - r_f.values[0]
        assert r_fg.values[0] == pytest.approx(expected, rel=1e-6)

    def test_t_sat_is_reasonable(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.T_SAT, _P_SAT, _H_2PH, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] == pytest.approx(294.72, rel=1e-3)

    def test_sigma_is_positive(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.SIGMA, _P_SAT, _H_2PH, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.values[0] > 0.0
        assert result.values[0] == pytest.approx(8.483e-3, rel=1e-2)

    def test_saturation_props_ignore_h(self, backend: CoolPropBackend):
        """Saturation properties depend only on P, not on h."""
        h_alt = np.array([999_999.0])  # nonsensical h
        result_orig = backend.query(PropertyName.H_F, _P_SAT, _H_2PH, _R134A)
        result_alt = backend.query(PropertyName.H_F, _P_SAT, h_alt, _R134A)
        assert result_orig.values[0] == pytest.approx(result_alt.values[0], rel=1e-9)


# ---------------------------------------------------------------------------
# query() — out-of-range and unsupported cases
# ---------------------------------------------------------------------------


class TestQueryEdgeCases:
    def test_out_of_range_returns_nan_and_oor_status(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.T, _P_OOR, _H_OOR, _R134A)
        assert result.status[0] == QueryStatus.OUT_OF_RANGE
        assert np.isnan(result.values[0])

    def test_out_of_range_has_warning(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.T, _P_OOR, _H_OOR, _R134A)
        assert result.warning is not None

    def test_mixture_returns_unavailable(self, backend: CoolPropBackend):
        m = Mixture((("R134a", 0.5), ("R32", 0.5)))
        result = backend.query(PropertyName.T, _P_LIQ, _H_LIQ, m)
        assert all(s == QueryStatus.UNAVAILABLE for s in result.status)
        assert all(np.isnan(result.values))

    def test_custom_fluid_returns_unavailable(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.T, _P_LIQ, _H_LIQ, CustomFluid("x"))
        assert all(s == QueryStatus.UNAVAILABLE for s in result.status)

    def test_sigma_e_returns_unavailable(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.SIGMA_E, _P_LIQ, _H_LIQ, _R134A)
        assert all(s == QueryStatus.UNAVAILABLE for s in result.status)
        assert all(np.isnan(result.values))

    def test_eps_r_returns_unavailable(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.EPS_R, _P_LIQ, _H_LIQ, _R134A)
        assert all(s == QueryStatus.UNAVAILABLE for s in result.status)


# ---------------------------------------------------------------------------
# query_derivative() — always UNAVAILABLE
# ---------------------------------------------------------------------------


class TestQueryDerivative:
    def test_drho_dp_h_is_unavailable(self, backend: CoolPropBackend):
        result = backend.query_derivative(PropertyName.DRHO_DP_H, _P_LIQ, _H_LIQ, _R134A)
        assert all(s == QueryStatus.UNAVAILABLE for s in result.status)
        assert all(np.isnan(result.values))

    def test_drho_dh_p_is_unavailable(self, backend: CoolPropBackend):
        result = backend.query_derivative(PropertyName.DRHO_DH_P, _P_LIQ, _H_LIQ, _R134A)
        assert all(s == QueryStatus.UNAVAILABLE for s in result.status)

    def test_derivative_has_warning(self, backend: CoolPropBackend):
        result = backend.query_derivative(PropertyName.DRHO_DP_H, _P_LIQ, _H_LIQ, _R134A)
        assert result.warning is not None


# ---------------------------------------------------------------------------
# Vector-first contract — scalar vs vector consistency
# ---------------------------------------------------------------------------


class TestVectorContract:
    _P_VEC = np.array([8.0e5, 6.0e5, 8.0e5])
    _H_VEC = np.array([200_000.0, 320_127.0, 450_000.0])

    def test_vector_result_has_correct_length(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.T, self._P_VEC, self._H_VEC, _R134A)
        assert len(result.values) == 3
        assert len(result.status) == 3

    def test_scalar_and_vector_agree_per_element(self, backend: CoolPropBackend):
        vec = backend.query(PropertyName.T, self._P_VEC, self._H_VEC, _R134A)
        for i in range(len(self._P_VEC)):
            scalar = backend.query(
                PropertyName.T,
                np.array([self._P_VEC[i]]),
                np.array([self._H_VEC[i]]),
                _R134A,
            )
            assert scalar.values[0] == pytest.approx(vec.values[i], rel=1e-9)

    def test_mixed_phase_vector(self, backend: CoolPropBackend):
        result = backend.query(PropertyName.PHASE, self._P_VEC, self._H_VEC, _R134A)
        assert result.values[0] == float(PhaseLabel.LIQUID.value)
        assert result.values[1] == float(PhaseLabel.TWO_PHASE.value)
        assert result.values[2] == float(PhaseLabel.VAPOR.value)

    def test_vector_with_oor_point(self, backend: CoolPropBackend):
        P_mix = np.array([8.0e5, 500.0])
        H_mix = np.array([200_000.0, 1_000.0])
        result = backend.query(PropertyName.T, P_mix, H_mix, _R134A)
        assert result.status[0] == QueryStatus.OK
        assert result.status[1] == QueryStatus.OUT_OF_RANGE
        assert not np.isnan(result.values[0])
        assert np.isnan(result.values[1])


# ---------------------------------------------------------------------------
# Import boundary guard — CoolProp must not be accessible outside properties/
# ---------------------------------------------------------------------------


class TestImportBoundary:
    def test_coolprop_not_importable_from_core(self):
        """core/ must not transitively expose CoolProp."""
        import mpl_sim.core as core_mod

        assert not hasattr(core_mod, "CoolProp")

    def test_coolprop_module_is_in_sys_modules_after_backend_use(self):
        """Using CoolPropBackend loads CoolProp (confirms it is actually used)."""
        assert "CoolProp" in sys.modules or "CoolProp.CoolProp" in sys.modules
