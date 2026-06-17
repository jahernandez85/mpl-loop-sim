"""Tests for EpsilonNTUModel — SinkInletTempAndFlow path (Phase 11B).

Sign convention under test:
    Q = epsilon * C_min * (T_secondary_in - T_primary_in)

    Q > 0  primary absorbs heat (evaporator: T_secondary_in > T_primary_in)
    Q < 0  primary rejects heat (condenser: T_primary_in  > T_secondary_in)
    h_out  = h_in + Q / primary_mdot
    P_out  = P_in - dP_primary

Explicit mode requirements:
    SinkInletTempAndFlow requires:
      - primary_T_in (precomputed scalar)
      - primary_thermal_mode (FINITE_CAPACITY or CONSTANT_TEMPERATURE)
      - ua_computation_mode  (PRIMARY_ONLY or TWO_SIDED)
    No None-inference of phase change.
    No implicit single-sided UA fallback when secondary HTC is absent.

Verifies:
  1.  SinkInletTempAndFlow validates finite T_in, positive mdot, positive cp.
  2.  EpsilonNTUModel handles SinkInletTempAndFlow when all fields are present.
  3.  Missing primary_T_in raises ValueError.
  4.  Missing primary_thermal_mode raises ValueError.
  5.  Missing ua_computation_mode raises ValueError.
  6.  Missing A_ht raises ValueError.
  7.  FINITE_CAPACITY without primary_cp raises ValueError at construction.
  8.  TWO_SIDED without htc_secondary raises ValueError at construction.
  9.  PRIMARY_ONLY without htc_primary raises ValueError at construction.
  10. No default cp, no default T, no default area.
  11. Q sign convention — both condenser and evaporator directions tested.
  12. h_out follows Q / mdot balance.
  13. dP_primary comes from injected dp_primary correlation.
  14. HTC calibration (htc_multiplier) affects UA and Q.
  15. Friction calibration (friction_multiplier) affects dP only, not energy balance.
  16. Correlation verdicts are propagated.
  17. hx_models/ does not import Network, Solver, PropertyBackend, or CoolProp.
  18. FluidState remains pure; identity is preserved.
  19. CONSTANT_TEMPERATURE (Cr=0) formula is correct numerically.
  20. FINITE_CAPACITY (Cr>0) counterflow formula is correct numerically.
  21. TWO_SIDED UA uses series resistance formula.
  22. PRIMARY_ONLY UA uses primary HTC only.
  23. HTC multiplier scales UA and Q in both modes.
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
    HXSolveRequest,
    HXSolveResult,
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=2e6, h=420e3, identity=_IDENTITY)
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

_MINIMAL_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test"),
)

_T_PRIMARY_HOT = 350.0  # K  condenser scenario: primary hotter than secondary
_T_PRIMARY_COLD = 280.0  # K  evaporator scenario: primary colder than secondary
_T_SECONDARY = 300.0  # K

_HTC_VALUE = 1000.0  # W/m²K
_DP_VALUE = 500.0  # Pa
_A_HT = 1.0  # m²
_MDOT_SECONDARY = 0.5  # kg/s
_CP_SECONDARY = 4000.0  # J/kg/K


# ---------------------------------------------------------------------------
# Dummy correlations
# ---------------------------------------------------------------------------


class _FakeHTCCorrelation(Correlation):
    def __init__(self, value: float = _HTC_VALUE, name: str = "fake_htc") -> None:
        self._value = value
        self._name = name

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(self._value,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef(correlation_name=self._name, correlation_version="0"),
                violated=(),
            ),
            metadata=ClosureMetadata(
                name=self._name,
                version="0",
                source=SourceRef(citation="test"),
            ),
        )


class _FakeDPCorrelation(Correlation):
    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(_DP_VALUE,),
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


# ---------------------------------------------------------------------------
# Request builder helpers
# ---------------------------------------------------------------------------

_BASE_GEOM = {
    "A_ht": _A_HT,
    "G": 100.0,
    "D_h": 0.002,
    "x": 0.5,
    "rho": 1200.0,
    "mu": 2e-4,
    "L_cell": 0.1,
}

# Default HTC for PRIMARY_ONLY tests — module-level to avoid mutable-default issues
_DEFAULT_HTC_P = _FakeHTCCorrelation()


def _make_sink_req(
    *,
    T_primary_in: float = _T_PRIMARY_HOT,
    primary_thermal_mode: PrimaryThermalMode = PrimaryThermalMode.CONSTANT_TEMPERATURE,
    primary_cp: float | None = None,
    T_secondary: float = _T_SECONDARY,
    mdot_secondary: float = _MDOT_SECONDARY,
    cp_secondary: float = _CP_SECONDARY,
    ua_computation_mode: UAComputationMode = UAComputationMode.PRIMARY_ONLY,
    htc_primary: Correlation = _DEFAULT_HTC_P,
    htc_secondary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
    geom_scalars: dict | None = None,
    primary_mdot: float = 0.05,
) -> HXSolveRequest:
    bc = SinkInletTempAndFlow(
        T_in=T_secondary,
        mdot_secondary=mdot_secondary,
        cp_secondary=cp_secondary,
    )
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=primary_mdot,
        secondary_bc=bc,
        geometry=object(),
        discretization=_DISC,
        geom_scalars=geom_scalars if geom_scalars is not None else _BASE_GEOM,
        htc_primary=htc_primary,
        htc_secondary=htc_secondary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
        primary_T_in=T_primary_in,
        primary_cp=primary_cp,
        primary_thermal_mode=primary_thermal_mode,
        ua_computation_mode=ua_computation_mode,
    )


# ---------------------------------------------------------------------------
# 3–9. Validation — missing required fields raise clear errors
# ---------------------------------------------------------------------------


class TestMissingPrimaryTIn:
    def test_missing_primary_t_in_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="primary_T_in"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
                primary_T_in=None,
            )

    def test_error_message_names_sink_bc(self) -> None:
        with pytest.raises(ValueError, match="SinkInletTempAndFlow"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
            )


class TestMissingPrimaryThermalMode:
    def test_missing_primary_thermal_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="primary_thermal_mode"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
                htc_primary=_DEFAULT_HTC_P,
                primary_T_in=_T_PRIMARY_HOT,
                primary_thermal_mode=None,
                ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
            )


class TestMissingUAComputationMode:
    def test_missing_ua_computation_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="ua_computation_mode"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
                htc_primary=_DEFAULT_HTC_P,
                primary_T_in=_T_PRIMARY_HOT,
                primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
                ua_computation_mode=None,
            )


class TestMissingAHt:
    def test_missing_a_ht_raises_value_error(self) -> None:
        geom = {k: v for k, v in _BASE_GEOM.items() if k != "A_ht"}
        with pytest.raises(ValueError, match="'A_ht'"):
            EpsilonNTUModel().solve(_make_sink_req(geom_scalars=geom))

    def test_zero_a_ht_raises_value_error(self) -> None:
        geom = {**_BASE_GEOM, "A_ht": 0.0}
        with pytest.raises(ValueError, match="A_ht"):
            EpsilonNTUModel().solve(_make_sink_req(geom_scalars=geom))

    def test_negative_a_ht_raises_value_error(self) -> None:
        geom = {**_BASE_GEOM, "A_ht": -1.0}
        with pytest.raises(ValueError, match="A_ht"):
            EpsilonNTUModel().solve(_make_sink_req(geom_scalars=geom))


# ---------------------------------------------------------------------------
# 7. FINITE_CAPACITY without primary_cp — caught at HXSolveRequest construction
# ---------------------------------------------------------------------------


class TestFiniteCapacityRequiresCp:
    def test_finite_capacity_without_cp_raises_at_construction(self) -> None:
        with pytest.raises(ValueError, match="primary_cp"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
                htc_primary=_DEFAULT_HTC_P,
                primary_T_in=_T_PRIMARY_HOT,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
                primary_cp=None,  # missing — must raise
            )

    def test_finite_capacity_with_cp_succeeds(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                primary_cp=2000.0,
            )
        )
        assert isinstance(result, HXSolveResult)


# ---------------------------------------------------------------------------
# 7b. CONSTANT_TEMPERATURE with primary_cp — caught at HXSolveRequest construction
# ---------------------------------------------------------------------------


class TestConstantTemperatureRejectsCp:
    def test_constant_temperature_with_cp_raises_at_construction(self) -> None:
        with pytest.raises(ValueError, match="primary_cp"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
                htc_primary=_DEFAULT_HTC_P,
                primary_T_in=_T_PRIMARY_HOT,
                primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
                ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
                primary_cp=2000.0,  # must be None for CONSTANT_TEMPERATURE
            )


# ---------------------------------------------------------------------------
# 8. TWO_SIDED without htc_secondary — caught at HXSolveRequest construction
# ---------------------------------------------------------------------------


class TestTwoSidedRequiresBothHTCs:
    def test_two_sided_without_htc_secondary_raises_at_construction(self) -> None:
        with pytest.raises(ValueError, match="htc_secondary"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
                htc_primary=_DEFAULT_HTC_P,
                htc_secondary=None,  # missing — must raise
                primary_T_in=_T_PRIMARY_HOT,
                primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
            )

    def test_two_sided_without_htc_primary_raises_at_construction(self) -> None:
        with pytest.raises(ValueError, match="htc_primary"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
                htc_primary=None,  # missing — must raise
                htc_secondary=_FakeHTCCorrelation(name="htc_s"),
                primary_T_in=_T_PRIMARY_HOT,
                primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
            )


# ---------------------------------------------------------------------------
# 9. PRIMARY_ONLY without htc_primary — caught at HXSolveRequest construction
# ---------------------------------------------------------------------------


class TestPrimaryOnlyRequiresPrimaryHTC:
    def test_primary_only_without_htc_primary_raises_at_construction(self) -> None:
        with pytest.raises(ValueError, match="htc_primary"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
                htc_primary=None,  # missing — must raise
                primary_T_in=_T_PRIMARY_HOT,
                primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
                ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
            )


# ---------------------------------------------------------------------------
# 2. Solve succeeds when all fields are present
# ---------------------------------------------------------------------------


class TestSolveSucceeds:
    def test_returns_hx_solve_result(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req())
        assert isinstance(result, HXSolveResult)

    def test_primary_state_out_is_fluid_state(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req())
        assert isinstance(result.primary_state_out, FluidState)

    def test_primary_state_out_is_new_object(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req())
        assert result.primary_state_out is not _STATE_IN


# ---------------------------------------------------------------------------
# 11. Sign convention — condenser and evaporator directions
# ---------------------------------------------------------------------------


class TestSignConvention:
    def test_condenser_q_is_negative(self) -> None:
        """Hot primary (350 K) over cool secondary (300 K): primary rejects heat."""
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                T_primary_in=_T_PRIMARY_HOT,
                T_secondary=_T_SECONDARY,
            )
        )
        assert result.Q < 0.0, f"Expected Q < 0 for condenser; got {result.Q}"

    def test_evaporator_q_is_positive(self) -> None:
        """Cold primary (280 K) under warm secondary (300 K): primary absorbs heat."""
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                T_primary_in=_T_PRIMARY_COLD,
                T_secondary=_T_SECONDARY,
            )
        )
        assert result.Q > 0.0, f"Expected Q > 0 for evaporator; got {result.Q}"

    def test_equal_temps_gives_zero_q(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                T_primary_in=_T_SECONDARY,
                T_secondary=_T_SECONDARY,
            )
        )
        assert math.isclose(result.Q, 0.0, abs_tol=1e-9)

    def test_q_stored_in_result(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req())
        assert math.isfinite(result.Q)


# ---------------------------------------------------------------------------
# 12. Energy balance: h_out = h_in + Q / mdot
# ---------------------------------------------------------------------------


class TestEnergyBalance:
    def test_h_out_balance_condenser(self) -> None:
        mdot = 0.05
        result = EpsilonNTUModel().solve(
            _make_sink_req(T_primary_in=_T_PRIMARY_HOT, primary_mdot=mdot)
        )
        expected = _STATE_IN.h + result.Q / mdot
        assert math.isclose(result.primary_state_out.h, expected, rel_tol=1e-12)

    def test_h_out_balance_evaporator(self) -> None:
        mdot = 0.08
        result = EpsilonNTUModel().solve(
            _make_sink_req(T_primary_in=_T_PRIMARY_COLD, primary_mdot=mdot)
        )
        expected = _STATE_IN.h + result.Q / mdot
        assert math.isclose(result.primary_state_out.h, expected, rel_tol=1e-12)

    def test_identity_preserved(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req())
        assert result.primary_state_out.identity is _IDENTITY


# ---------------------------------------------------------------------------
# 19. CONSTANT_TEMPERATURE numerics (Cr = 0, PRIMARY_ONLY)
# ---------------------------------------------------------------------------


class TestConstantTemperatureNumerics:
    """CONSTANT_TEMPERATURE + PRIMARY_ONLY: ε = 1 - exp(-NTU), UA = h_p * A."""

    def _expected_q(
        self,
        htc: float,
        A: float,
        mdot_s: float,
        cp_s: float,
        T_primary: float,
        T_secondary: float,
    ) -> float:
        C_s = mdot_s * cp_s
        UA = htc * A
        NTU = UA / C_s
        epsilon = 1.0 - math.exp(-NTU)
        return epsilon * C_s * (T_secondary - T_primary)

    def test_condenser_q_matches_formula(self) -> None:
        htc = _HTC_VALUE
        expected = self._expected_q(
            htc, _A_HT, _MDOT_SECONDARY, _CP_SECONDARY, _T_PRIMARY_HOT, _T_SECONDARY
        )
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                T_primary_in=_T_PRIMARY_HOT,
                htc_primary=_FakeHTCCorrelation(htc),
            )
        )
        assert math.isclose(result.Q, expected, rel_tol=1e-9)

    def test_evaporator_q_matches_formula(self) -> None:
        htc = _HTC_VALUE
        expected = self._expected_q(
            htc, _A_HT, _MDOT_SECONDARY, _CP_SECONDARY, _T_PRIMARY_COLD, _T_SECONDARY
        )
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                T_primary_in=_T_PRIMARY_COLD,
                htc_primary=_FakeHTCCorrelation(htc),
            )
        )
        assert math.isclose(result.Q, expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 20. FINITE_CAPACITY numerics (Cr > 0, PRIMARY_ONLY, counterflow)
# ---------------------------------------------------------------------------


class TestFiniteCapacityNumerics:
    def _expected_q_counterflow(
        self,
        htc: float,
        A: float,
        mdot_p: float,
        cp_p: float,
        mdot_s: float,
        cp_s: float,
        T_p: float,
        T_s: float,
    ) -> float:
        C_p = mdot_p * cp_p
        C_s = mdot_s * cp_s
        C_min = min(C_p, C_s)
        C_max = max(C_p, C_s)
        Cr = C_min / C_max
        UA = htc * A
        NTU = UA / C_min
        exp_term = math.exp(-NTU * (1.0 - Cr))
        epsilon = (1.0 - exp_term) / (1.0 - Cr * exp_term)
        return epsilon * C_min * (T_s - T_p)

    def test_finite_capacity_q_matches_counterflow(self) -> None:
        htc = _HTC_VALUE
        mdot_p = 0.05
        cp_p = 2000.0

        result = EpsilonNTUModel().solve(
            _make_sink_req(
                T_primary_in=_T_PRIMARY_HOT,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                primary_cp=cp_p,
                htc_primary=_FakeHTCCorrelation(htc),
                primary_mdot=mdot_p,
            )
        )
        expected = self._expected_q_counterflow(
            htc, _A_HT, mdot_p, cp_p, _MDOT_SECONDARY, _CP_SECONDARY, _T_PRIMARY_HOT, _T_SECONDARY
        )
        assert math.isclose(result.Q, expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21. TWO_SIDED UA — series resistance formula
# ---------------------------------------------------------------------------


class TestTwoSidedUA:
    def test_two_sided_q_matches_series_resistance_formula(self) -> None:
        h_p = 2000.0
        h_s = 1000.0
        A = _A_HT
        expected_UA = 1.0 / (1.0 / (h_p * A) + 1.0 / (h_s * A))
        C_s = _MDOT_SECONDARY * _CP_SECONDARY
        NTU = expected_UA / C_s
        expected_epsilon = 1.0 - math.exp(-NTU)
        expected_Q = expected_epsilon * C_s * (_T_SECONDARY - _T_PRIMARY_HOT)

        result = EpsilonNTUModel().solve(
            _make_sink_req(
                T_primary_in=_T_PRIMARY_HOT,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                htc_primary=_FakeHTCCorrelation(h_p, "htc_p"),
                htc_secondary=_FakeHTCCorrelation(h_s, "htc_s"),
            )
        )
        assert math.isclose(result.Q, expected_Q, rel_tol=1e-9)

    def test_two_sided_both_verdicts_propagated(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                htc_primary=_FakeHTCCorrelation(name="htc_p"),
                htc_secondary=_FakeHTCCorrelation(name="htc_s"),
            )
        )
        names = {v.metadata.name for v in result.verdicts}
        assert "htc_p" in names
        assert "htc_s" in names


# ---------------------------------------------------------------------------
# 22. PRIMARY_ONLY UA — uses primary HTC only
# ---------------------------------------------------------------------------


class TestPrimaryOnlyUA:
    def test_primary_only_q_matches_primary_only_ua(self) -> None:
        h_p = _HTC_VALUE
        A = _A_HT
        C_s = _MDOT_SECONDARY * _CP_SECONDARY
        UA = h_p * A
        NTU = UA / C_s
        expected_epsilon = 1.0 - math.exp(-NTU)
        expected_Q = expected_epsilon * C_s * (_T_SECONDARY - _T_PRIMARY_HOT)

        result = EpsilonNTUModel().solve(
            _make_sink_req(
                T_primary_in=_T_PRIMARY_HOT,
                ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
                htc_primary=_FakeHTCCorrelation(h_p),
            )
        )
        assert math.isclose(result.Q, expected_Q, rel_tol=1e-9)

    def test_primary_only_differs_from_two_sided(self) -> None:
        """PRIMARY_ONLY and TWO_SIDED give different Q when secondary HTC is finite."""
        h_p = _HTC_VALUE
        h_s = 500.0

        r_po = EpsilonNTUModel().solve(
            _make_sink_req(
                ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
                htc_primary=_FakeHTCCorrelation(h_p),
            )
        )
        r_ts = EpsilonNTUModel().solve(
            _make_sink_req(
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                htc_primary=_FakeHTCCorrelation(h_p),
                htc_secondary=_FakeHTCCorrelation(h_s),
            )
        )
        assert abs(r_po.Q) > abs(r_ts.Q)  # PRIMARY_ONLY overestimates UA


# ---------------------------------------------------------------------------
# 13. DP path
# ---------------------------------------------------------------------------


class TestDPPath:
    def test_dp_from_injected_correlation(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req(dp_primary=_FakeDPCorrelation()))
        assert math.isclose(result.dP_primary, _DP_VALUE, rel_tol=1e-12)

    def test_no_dp_gives_zero_dp(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req(dp_primary=None))
        assert result.dP_primary == 0.0

    def test_p_out_decreases_by_dp(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req(dp_primary=_FakeDPCorrelation()))
        assert math.isclose(result.primary_state_out.P, _STATE_IN.P - _DP_VALUE, rel_tol=1e-12)

    def test_dp_verdict_propagated(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req(dp_primary=_FakeDPCorrelation()))
        assert any(v.metadata.name == "fake_dp" for v in result.verdicts)

    def test_raw_dp_stored(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req(dp_primary=_FakeDPCorrelation()))
        assert math.isclose(result.raw_dP_primary, _DP_VALUE, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# 14. HTC calibration (htc_multiplier) scales UA and Q
# ---------------------------------------------------------------------------


class TestHTCCalibration:
    def test_htc_multiplier_larger_gives_larger_q_magnitude(self) -> None:
        r1 = EpsilonNTUModel().solve(
            _make_sink_req(T_primary_in=_T_PRIMARY_HOT, htc_multiplier=1.0)
        )
        r2 = EpsilonNTUModel().solve(
            _make_sink_req(T_primary_in=_T_PRIMARY_HOT, htc_multiplier=2.0)
        )
        assert abs(r2.Q) > abs(r1.Q)

    def test_htc_multiplier_zero_gives_zero_q(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req(htc_multiplier=0.0))
        assert math.isclose(result.Q, 0.0, abs_tol=1e-12)

    def test_htc_multiplier_stored_in_result(self) -> None:
        m = 1.5
        result = EpsilonNTUModel().solve(_make_sink_req(htc_multiplier=m))
        assert math.isclose(result.htc_multiplier, m, rel_tol=1e-12)

    def test_htc_multiplier_scales_ua_and_q_numerically(self) -> None:
        htc = _HTC_VALUE
        A = _A_HT
        C_s = _MDOT_SECONDARY * _CP_SECONDARY
        T_p = _T_PRIMARY_HOT
        T_s = _T_SECONDARY
        for m in (0.5, 1.0, 2.0):
            UA = m * htc * A
            NTU = UA / C_s
            epsilon = 1.0 - math.exp(-NTU)
            expected_Q = epsilon * C_s * (T_s - T_p)
            result = EpsilonNTUModel().solve(
                _make_sink_req(
                    T_primary_in=T_p,
                    htc_primary=_FakeHTCCorrelation(htc),
                    htc_multiplier=m,
                )
            )
            assert math.isclose(
                result.Q, expected_Q, rel_tol=1e-9
            ), f"htc_multiplier={m}: got Q={result.Q}, expected={expected_Q}"

    def test_htc_multiplier_scales_two_sided_ua(self) -> None:
        h_p, h_s = 2000.0, 1000.0
        A = _A_HT
        m = 2.0
        expected_UA = 1.0 / (1.0 / (m * h_p * A) + 1.0 / (m * h_s * A))
        C_s = _MDOT_SECONDARY * _CP_SECONDARY
        NTU = expected_UA / C_s
        expected_Q = (1.0 - math.exp(-NTU)) * C_s * (_T_SECONDARY - _T_PRIMARY_HOT)

        result = EpsilonNTUModel().solve(
            _make_sink_req(
                T_primary_in=_T_PRIMARY_HOT,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                htc_primary=_FakeHTCCorrelation(h_p),
                htc_secondary=_FakeHTCCorrelation(h_s),
                htc_multiplier=m,
            )
        )
        assert math.isclose(result.Q, expected_Q, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 15. Friction calibration does not affect energy balance
# ---------------------------------------------------------------------------


class TestFrictionCalibration:
    def test_friction_multiplier_scales_dp(self) -> None:
        m = 3.0
        result = EpsilonNTUModel().solve(
            _make_sink_req(dp_primary=_FakeDPCorrelation(), friction_multiplier=m)
        )
        assert math.isclose(result.dP_primary, m * _DP_VALUE, rel_tol=1e-12)

    def test_friction_multiplier_does_not_change_q(self) -> None:
        r1 = EpsilonNTUModel().solve(
            _make_sink_req(dp_primary=_FakeDPCorrelation(), friction_multiplier=1.0)
        )
        r2 = EpsilonNTUModel().solve(
            _make_sink_req(dp_primary=_FakeDPCorrelation(), friction_multiplier=3.0)
        )
        assert math.isclose(r1.Q, r2.Q, rel_tol=1e-12)

    def test_friction_multiplier_does_not_change_h_out(self) -> None:
        mdot = 0.05
        r1 = EpsilonNTUModel().solve(
            _make_sink_req(
                dp_primary=_FakeDPCorrelation(), friction_multiplier=1.0, primary_mdot=mdot
            )
        )
        r2 = EpsilonNTUModel().solve(
            _make_sink_req(
                dp_primary=_FakeDPCorrelation(), friction_multiplier=5.0, primary_mdot=mdot
            )
        )
        assert math.isclose(r1.primary_state_out.h, r2.primary_state_out.h, rel_tol=1e-12)

    def test_friction_multiplier_stored_in_result(self) -> None:
        m = 2.5
        result = EpsilonNTUModel().solve(_make_sink_req(friction_multiplier=m))
        assert math.isclose(result.friction_multiplier, m, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# 16. Verdict propagation
# ---------------------------------------------------------------------------


class TestVerdictPropagation:
    def test_htc_verdict_propagated(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_sink_req(htc_primary=_FakeHTCCorrelation(name="test_htc"))
        )
        assert any(v.metadata.name == "test_htc" for v in result.verdicts)

    def test_dp_verdict_propagated(self) -> None:
        result = EpsilonNTUModel().solve(_make_sink_req(dp_primary=_FakeDPCorrelation()))
        assert any(v.metadata.name == "fake_dp" for v in result.verdicts)

    def test_primary_only_with_dp_two_verdicts(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
                htc_primary=_FakeHTCCorrelation(),
                dp_primary=_FakeDPCorrelation(),
            )
        )
        assert len(result.verdicts) == 2

    def test_two_sided_no_dp_two_verdicts(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                htc_primary=_FakeHTCCorrelation(name="htc_p"),
                htc_secondary=_FakeHTCCorrelation(name="htc_s"),
            )
        )
        assert len(result.verdicts) == 2

    def test_two_sided_with_dp_three_verdicts(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                htc_primary=_FakeHTCCorrelation(name="htc_p"),
                htc_secondary=_FakeHTCCorrelation(name="htc_s"),
                dp_primary=_FakeDPCorrelation(),
            )
        )
        assert len(result.verdicts) == 3


# ---------------------------------------------------------------------------
# 10. No hidden defaults
# ---------------------------------------------------------------------------


class TestNoHiddenDefaults:
    def test_no_default_cp_for_secondary(self) -> None:
        """cp_secondary is always explicit; the model never substitutes 4180."""
        cp_custom = 3000.0
        result = EpsilonNTUModel().solve(
            _make_sink_req(
                T_primary_in=_T_PRIMARY_HOT,
                cp_secondary=cp_custom,
                htc_primary=_FakeHTCCorrelation(),
            )
        )
        C_s = _MDOT_SECONDARY * cp_custom
        NTU = (_HTC_VALUE * _A_HT) / C_s
        expected_Q = (1.0 - math.exp(-NTU)) * C_s * (_T_SECONDARY - _T_PRIMARY_HOT)
        assert math.isclose(result.Q, expected_Q, rel_tol=1e-9)

    def test_no_default_area(self) -> None:
        """Omitting A_ht must raise ValueError, never substitute a default."""
        geom = {k: v for k, v in _BASE_GEOM.items() if k != "A_ht"}
        with pytest.raises(ValueError, match="'A_ht'"):
            EpsilonNTUModel().solve(_make_sink_req(geom_scalars=geom))

    def test_no_default_primary_t_in(self) -> None:
        """primary_T_in=None must raise ValueError at construction, never substitute a default T."""
        with pytest.raises(ValueError):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
            )

    def test_no_implicit_phase_change_from_missing_cp(self) -> None:
        """primary_thermal_mode=None must raise at construction, not infer phase change."""
        with pytest.raises(ValueError, match="primary_thermal_mode"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
                htc_primary=_DEFAULT_HTC_P,
                primary_T_in=_T_PRIMARY_HOT,
                ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
                primary_thermal_mode=None,
            )

    def test_no_implicit_single_sided_ua_from_missing_secondary_htc(self) -> None:
        """ua_computation_mode=None must raise at construction, not fall back silently."""
        with pytest.raises(ValueError, match="ua_computation_mode"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.05,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY, mdot_secondary=0.5, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_DISC,
                geom_scalars=_BASE_GEOM,
                htc_primary=_DEFAULT_HTC_P,
                primary_T_in=_T_PRIMARY_HOT,
                primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
                ua_computation_mode=None,
            )


# ---------------------------------------------------------------------------
# 17. Import boundary — hx_models must not import forbidden modules
# ---------------------------------------------------------------------------


def _import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        return [ln.strip() for ln in f if ln.strip().startswith(("import ", "from "))]


class TestImportBoundary:
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

    def test_does_not_import_properties(self) -> None:
        for ln in self._imports():
            assert "properties" not in ln

    def test_does_not_import_components(self) -> None:
        for ln in self._imports():
            assert "components" not in ln
