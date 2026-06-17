"""Tests for EpsilonNTUModel — Phase 11B/11D.

Verifies:
  - EpsilonNTUModel returns HXSolveResult for FixedHeatRate BC
  - FixedHeatRate changes outlet enthalpy by Q / mdot
  - primary_state_out is a new FluidState, not stored on a Port
  - Q sign convention is explicit: positive Q → h_out > h_in
  - dP_primary is derived from dp_primary correlation (not stored)
  - Injected htc_primary and dp_primary are called through their contract
  - Correlation verdicts are propagated into HXSolveResult.verdicts
  - Calibration (friction_multiplier) scales DP output, not the balance
  - Calibration (htc_multiplier) is threaded but does not alter Q
  - EpsilonNTUModel does not resolve a registry internally
  - EpsilonNTUModel does not import Network, Solver, or CoolProp
  - SinkInletTempAndFlow without primary_T_in raises ValueError at construction
  - Missing required geom_scalars keys raise ValueError with clear messages

Note: FixedWallTemp and AmbientCoupling are now supported — see
test_epsilon_ntu_fixed_wall_temp.py and test_epsilon_ntu_ambient_coupling.py.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import (
    AnyFluid,
    Bound,
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationInput,
    CorrelationOutput,
    CorrelationRole,
    EnvelopeRef,
    SourceRef,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import (
    FixedHeatRate,
    HeatExchangerModelKind,
    HXSolveRequest,
    HXSolveResult,
    SinkInletTempAndFlow,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

# ---------------------------------------------------------------------------
# Fake correlations — accept any input, return canned output
# ---------------------------------------------------------------------------

_MINIMAL_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test"),
)

_FAKE_HTC_VALUE = 150.0  # W/m²K
_FAKE_DP_VALUE = 800.0  # Pa


class _FakeHTCCorrelation(Correlation):
    """Always returns htc = 150 W/m²K; ignores input values."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(_FAKE_HTC_VALUE,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef(correlation_name="fake_htc", correlation_version="0"),
                violated=(),
            ),
            metadata=ClosureMetadata(
                name="fake_htc",
                version="0",
                source=SourceRef(citation="test"),
            ),
        )


class _FakeDPCorrelation(Correlation):
    """Always returns dp = 800 Pa; ignores input values."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(_FAKE_DP_VALUE,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef(correlation_name="fake_dp", correlation_version="0"),
                violated=(),
            ),
            metadata=ClosureMetadata(
                name="fake_dp",
                version="0",
                source=SourceRef(citation="test"),
            ),
        )


class _CallRecordingCorrelation(Correlation):
    """Records calls; returns a canned value."""

    def __init__(self, role_: CorrelationRole, return_value: float) -> None:
        self._role = role_
        self._return_value = return_value
        self.call_count = 0
        self.last_input: CorrelationInput | None = None

    def role(self) -> CorrelationRole:
        return self._role

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        self.call_count += 1
        self.last_input = inp
        return CorrelationOutput(
            value=(self._return_value,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef(correlation_name="recording", correlation_version="0"),
                violated=(),
            ),
            metadata=ClosureMetadata(
                name="recording",
                version="0",
                source=SourceRef(citation="test"),
            ),
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=1e6, h=250e3, identity=_IDENTITY)
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)


def _make_request(
    Q: float = 1000.0,
    mdot: float = 0.05,
    htc_primary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
    geom_scalars: dict | None = None,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=mdot,
        secondary_bc=FixedHeatRate(Q=Q),
        geometry=object(),
        discretization=_DISC,
        geom_scalars=geom_scalars
        or {
            "rho": 1200.0,
            "mu": 2e-4,
            "D_h": 0.002,
            "G": 100.0,
            "L_cell": 0.1,
            "x": 0.5,
        },
        htc_primary=htc_primary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
    )


# ---------------------------------------------------------------------------
# Basic EpsilonNTU behaviour
# ---------------------------------------------------------------------------


class TestEpsilonNTUKind:
    def test_kind_is_epsilon_ntu(self) -> None:
        model = EpsilonNTUModel()
        assert model.kind() is HeatExchangerModelKind.EPSILON_NTU


class TestEpsilonNTUReturnsResult:
    def test_solve_returns_hx_solve_result(self) -> None:
        model = EpsilonNTUModel()
        req = _make_request()
        result = model.solve(req)
        assert isinstance(result, HXSolveResult)

    def test_result_has_primary_state_out(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request())
        assert isinstance(result.primary_state_out, FluidState)

    def test_result_primary_state_out_is_new_object(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request())
        assert result.primary_state_out is not _STATE_IN


# ---------------------------------------------------------------------------
# FixedHeatRate energy balance
# ---------------------------------------------------------------------------


class TestFixedHeatRateBalance:
    def test_positive_q_increases_enthalpy(self) -> None:
        model = EpsilonNTUModel()
        Q, mdot = 1000.0, 0.05
        result = model.solve(_make_request(Q=Q, mdot=mdot))
        expected_h_out = _STATE_IN.h + Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h_out, rel_tol=1e-12)

    def test_negative_q_decreases_enthalpy(self) -> None:
        model = EpsilonNTUModel()
        Q, mdot = -2000.0, 0.1
        result = model.solve(_make_request(Q=Q, mdot=mdot))
        expected_h_out = _STATE_IN.h + Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h_out, rel_tol=1e-12)

    def test_zero_q_preserves_enthalpy(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request(Q=0.0))
        assert math.isclose(result.primary_state_out.h, _STATE_IN.h, rel_tol=1e-12)

    def test_q_stored_in_result(self) -> None:
        model = EpsilonNTUModel()
        Q = 1500.0
        result = model.solve(_make_request(Q=Q))
        assert result.Q == Q

    def test_identity_preserved(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request())
        assert result.primary_state_out.identity is _STATE_IN.identity

    def test_h_out_equals_h_in_plus_q_over_mdot(self) -> None:
        model = EpsilonNTUModel()
        for Q in (-5000.0, 0.0, 500.0, 10000.0):
            mdot = 0.08
            result = model.solve(_make_request(Q=Q, mdot=mdot))
            expected = _STATE_IN.h + Q / mdot
            assert math.isclose(
                result.primary_state_out.h, expected, rel_tol=1e-12
            ), f"Q={Q}: h_out={result.primary_state_out.h}, expected={expected}"


# ---------------------------------------------------------------------------
# Pressure drop (no correlations → zero)
# ---------------------------------------------------------------------------


class TestFixedHeatRateNoDPCorrelation:
    def test_no_dp_gives_zero_dp(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request(dp_primary=None))
        assert result.dP_primary == 0.0

    def test_no_dp_p_out_equals_p_in(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request(dp_primary=None))
        assert math.isclose(result.primary_state_out.P, _STATE_IN.P, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# DP correlation called and used
# ---------------------------------------------------------------------------


class TestDPCorrelationCalled:
    def test_dp_correlation_called(self) -> None:
        rec = _CallRecordingCorrelation(CorrelationRole.SINGLE_PHASE_DP, _FAKE_DP_VALUE)
        model = EpsilonNTUModel()
        model.solve(_make_request(dp_primary=rec))
        assert rec.call_count == 1

    def test_dp_output_used_for_dp_primary(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request(dp_primary=_FakeDPCorrelation()))
        assert math.isclose(result.dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_dp_decreases_outlet_pressure(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request(dp_primary=_FakeDPCorrelation()))
        assert math.isclose(
            result.primary_state_out.P,
            _STATE_IN.P - _FAKE_DP_VALUE,
            rel_tol=1e-12,
        )

    def test_dp_verdict_propagated(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request(dp_primary=_FakeDPCorrelation()))
        assert len(result.verdicts) == 1
        assert result.verdicts[0].metadata.name == "fake_dp"

    def test_dp_raw_stored(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request(dp_primary=_FakeDPCorrelation()))
        assert math.isclose(result.raw_dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# HTC correlation called
# ---------------------------------------------------------------------------


class TestHTCCorrelationCalled:
    def test_htc_correlation_called(self) -> None:
        rec = _CallRecordingCorrelation(CorrelationRole.HTC, _FAKE_HTC_VALUE)
        model = EpsilonNTUModel()
        model.solve(_make_request(htc_primary=rec))
        assert rec.call_count == 1

    def test_htc_verdict_propagated(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(_make_request(htc_primary=_FakeHTCCorrelation()))
        assert any(v.metadata.name == "fake_htc" for v in result.verdicts)

    def test_both_correlations_produce_two_verdicts(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(
            _make_request(htc_primary=_FakeHTCCorrelation(), dp_primary=_FakeDPCorrelation())
        )
        assert len(result.verdicts) == 2

    def test_htc_does_not_change_q(self) -> None:
        model = EpsilonNTUModel()
        Q = 750.0
        result = model.solve(_make_request(Q=Q, htc_primary=_FakeHTCCorrelation()))
        assert result.Q == Q

    def test_htc_does_not_change_h_out(self) -> None:
        model = EpsilonNTUModel()
        Q, mdot = 750.0, 0.05
        result = model.solve(_make_request(Q=Q, mdot=mdot, htc_primary=_FakeHTCCorrelation()))
        expected = _STATE_IN.h + Q / mdot
        assert math.isclose(result.primary_state_out.h, expected, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Calibration — friction_multiplier scales DP only
# ---------------------------------------------------------------------------


class TestCalibrationFrictionMultiplier:
    def test_multiplier_scales_dp(self) -> None:
        model = EpsilonNTUModel()
        m = 2.0
        result = model.solve(_make_request(dp_primary=_FakeDPCorrelation(), friction_multiplier=m))
        assert math.isclose(result.dP_primary, m * _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_zero_multiplier_suppresses_dp(self) -> None:
        model = EpsilonNTUModel()
        result = model.solve(
            _make_request(dp_primary=_FakeDPCorrelation(), friction_multiplier=0.0)
        )
        assert result.dP_primary == 0.0

    def test_multiplier_does_not_affect_q(self) -> None:
        model = EpsilonNTUModel()
        Q = 500.0
        r1 = model.solve(
            _make_request(Q=Q, dp_primary=_FakeDPCorrelation(), friction_multiplier=1.0)
        )
        r2 = model.solve(
            _make_request(Q=Q, dp_primary=_FakeDPCorrelation(), friction_multiplier=3.0)
        )
        assert r1.Q == r2.Q == Q

    def test_multiplier_does_not_affect_enthalpy_balance(self) -> None:
        model = EpsilonNTUModel()
        Q, mdot = 500.0, 0.05
        expected_h = _STATE_IN.h + Q / mdot
        for m in (0.5, 1.0, 2.0):
            result = model.solve(
                _make_request(
                    Q=Q, mdot=mdot, dp_primary=_FakeDPCorrelation(), friction_multiplier=m
                )
            )
            assert math.isclose(
                result.primary_state_out.h, expected_h, rel_tol=1e-12
            ), f"friction_multiplier={m} altered enthalpy balance"

    def test_raw_dp_is_pre_calibration(self) -> None:
        model = EpsilonNTUModel()
        m = 3.0
        result = model.solve(_make_request(dp_primary=_FakeDPCorrelation(), friction_multiplier=m))
        assert math.isclose(result.raw_dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)
        assert math.isclose(result.dP_primary, m * _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_friction_multiplier_stored_in_result(self) -> None:
        model = EpsilonNTUModel()
        m = 1.5
        result = model.solve(_make_request(friction_multiplier=m))
        assert math.isclose(result.friction_multiplier, m, rel_tol=1e-12)


class TestCalibrationHTCMultiplier:
    def test_htc_multiplier_stored_in_result(self) -> None:
        model = EpsilonNTUModel()
        m = 0.9
        result = model.solve(_make_request(htc_primary=_FakeHTCCorrelation(), htc_multiplier=m))
        assert math.isclose(result.htc_multiplier, m, rel_tol=1e-12)

    def test_htc_multiplier_does_not_change_q(self) -> None:
        model = EpsilonNTUModel()
        Q = 300.0
        for m in (0.5, 1.0, 2.0):
            result = model.solve(
                _make_request(Q=Q, htc_primary=_FakeHTCCorrelation(), htc_multiplier=m)
            )
            assert result.Q == Q, f"htc_multiplier={m} changed Q"


# ---------------------------------------------------------------------------
# BC error handling
# ---------------------------------------------------------------------------


class TestUnsupportedBCs:
    def test_sink_inlet_without_primary_t_in_raises_value_error(self) -> None:
        """SinkInletTempAndFlow with missing primary_T_in raises ValueError at construction."""
        bc = SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.1, cp_secondary=4000.0)
        with pytest.raises(ValueError, match="primary_T_in"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=bc,
                geometry=object(),
                discretization=_DISC,
                primary_T_in=None,
            )


# ---------------------------------------------------------------------------
# Missing required geom_scalars keys raise ValueError
# ---------------------------------------------------------------------------


class TestMissingGeomScalars:
    def _htc_req(self, geom_scalars: dict) -> HXSolveRequest:
        return HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=1000.0),
            geometry=object(),
            discretization=_DISC,
            geom_scalars=geom_scalars,
            htc_primary=_FakeHTCCorrelation(),
        )

    def _dp_req(self, geom_scalars: dict) -> HXSolveRequest:
        return HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=1000.0),
            geometry=object(),
            discretization=_DISC,
            geom_scalars=geom_scalars,
            dp_primary=_FakeDPCorrelation(),
        )

    def test_htc_missing_G_raises(self) -> None:
        with pytest.raises(ValueError, match="'G'"):
            EpsilonNTUModel().solve(self._htc_req({"x": 0.5, "D_h": 0.002}))

    def test_htc_missing_x_raises(self) -> None:
        with pytest.raises(ValueError, match="'x'"):
            EpsilonNTUModel().solve(self._htc_req({"G": 100.0, "D_h": 0.002}))

    def test_htc_missing_D_h_raises(self) -> None:
        with pytest.raises(ValueError, match="'D_h'"):
            EpsilonNTUModel().solve(self._htc_req({"G": 100.0, "x": 0.5}))

    def test_dp_missing_G_raises(self) -> None:
        with pytest.raises(ValueError, match="'G'"):
            EpsilonNTUModel().solve(
                self._dp_req({"D_h": 0.002, "L_cell": 0.1, "rho": 1200.0, "mu": 2e-4})
            )

    def test_dp_missing_D_h_raises(self) -> None:
        with pytest.raises(ValueError, match="'D_h'"):
            EpsilonNTUModel().solve(
                self._dp_req({"G": 100.0, "L_cell": 0.1, "rho": 1200.0, "mu": 2e-4})
            )

    def test_dp_missing_L_cell_raises(self) -> None:
        with pytest.raises(ValueError, match="'L_cell'"):
            EpsilonNTUModel().solve(
                self._dp_req({"G": 100.0, "D_h": 0.002, "rho": 1200.0, "mu": 2e-4})
            )

    def test_dp_missing_rho_raises(self) -> None:
        with pytest.raises(ValueError, match="'rho'"):
            EpsilonNTUModel().solve(
                self._dp_req({"G": 100.0, "D_h": 0.002, "L_cell": 0.1, "mu": 2e-4})
            )

    def test_dp_missing_mu_raises(self) -> None:
        with pytest.raises(ValueError, match="'mu'"):
            EpsilonNTUModel().solve(
                self._dp_req({"G": 100.0, "D_h": 0.002, "L_cell": 0.1, "rho": 1200.0})
            )

    def test_dp_roughness_optional(self) -> None:
        req = self._dp_req({"G": 100.0, "D_h": 0.002, "L_cell": 0.1, "rho": 1200.0, "mu": 2e-4})
        result = EpsilonNTUModel().solve(req)
        assert isinstance(result, HXSolveResult)


# ---------------------------------------------------------------------------
# Import boundary
# ---------------------------------------------------------------------------


def _import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        return [ln.strip() for ln in f if ln.strip().startswith(("import ", "from "))]


class TestEpsilonNTUImportBoundary:
    def _imports(self) -> list[str]:
        import mpl_sim.hx_models.epsilon_ntu as m

        assert m.__file__ is not None
        return _import_lines(m.__file__)

    def test_does_not_import_network(self) -> None:
        for ln in self._imports():
            assert "network" not in ln

    def test_does_not_import_solvers(self) -> None:
        for ln in self._imports():
            assert "solvers" not in ln

    def test_does_not_import_coolprop(self) -> None:
        for ln in self._imports():
            assert "coolprop" not in ln.lower()

    def test_does_not_import_registry(self) -> None:
        for ln in self._imports():
            assert "registry" not in ln.lower()

    def test_does_not_import_components(self) -> None:
        for ln in self._imports():
            assert "components" not in ln

    def test_does_not_import_properties(self) -> None:
        for ln in self._imports():
            assert "properties" not in ln
