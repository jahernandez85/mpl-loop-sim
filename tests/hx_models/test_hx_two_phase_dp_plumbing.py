"""Tests for Phase 11P two-phase DP HX builder and gradient-to-drop plumbing.

Coverage:
 1. Existing single-phase DP paths remain unchanged (dp_primary_is_two_phase=False).
 2. Two-phase DP path builds TwoPhaseDPInput (not SinglePhaseDPInput).
 3. Required property_scalars are forwarded exactly.
 4. Missing rho_l / rho_v / mu_l / mu_v fails clearly.
 5. Invalid property scalar (zero, negative, NaN, inf) fails clearly.
 6. Gradient Pa/m is converted to pressure drop Pa using explicit L_cell.
 7. friction_multiplier multiplies the pressure drop after conversion.
 8. No hidden L_cell default (missing L_cell fails clearly).
 9. No hidden density/viscosity defaults (missing rho_l fails).
10. Segmented model applies per-cell conversion using the cell length.
11. EpsilonNTU / LMTD / Segmented all support the two-phase path.
12. HX models do not resolve CorrelationRegistry (import boundary).
13. No CoolProp / PropertyBackend access (import boundary).
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import (
    ClosureMetadata,
    CorrelationOutput,
    EnvelopeRef,
    SinglePhaseDPInput,
    SourceRef,
    TwoPhaseDPInput,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.correlations.single_phase_dp import ChurchillFrictionGradient
from mpl_sim.correlations.two_phase_dp import MSHTwoPhaseFrictionGradient
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import (
    AmbientCoupling,
    FixedHeatRate,
    FixedWallTemp,
    HXSolveRequest,
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel
from mpl_sim.hx_models.lmtd import LMTDModel
from mpl_sim.hx_models.segmented import SegmentedMarchModel

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=1_000_000.0, h=250_000.0, identity=_IDENTITY)

_LUMPED = DiscretizationSpec(mode=DiscretizationMode.LUMPED)
_UNIFORM_3 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=3)

# Shared valid geom_scalars for two-phase DP tests.
_TWO_PHASE_GEOM = {
    "G": 200.0,
    "x": 0.4,
    "D_h": 1e-3,
    "L_cell": 0.5,
    "rho_l": 1000.0,
    "rho_v": 10.0,
    "mu_l": 1e-3,
    "mu_v": 1e-5,
}

# Shared valid geom_scalars for single-phase DP tests.
_SINGLE_PHASE_GEOM = {
    "G": 200.0,
    "D_h": 1e-3,
    "L_cell": 0.5,
    "rho": 1000.0,
    "mu": 1e-3,
    "x": 0.0,
}


def _make_verdict(status: ValidityStatus = ValidityStatus.IN_ENVELOPE) -> ValidityVerdict:
    return ValidityVerdict(
        status=status,
        envelope=EnvelopeRef(correlation_name="stub", correlation_version="0"),
        violated=(),
    )


def _make_metadata() -> ClosureMetadata:
    return ClosureMetadata(
        name="stub",
        version="0",
        source=SourceRef(citation="test"),
    )


def _make_output(value: float) -> CorrelationOutput:
    return CorrelationOutput(
        value=(value,),
        verdict=_make_verdict(),
        metadata=_make_metadata(),
    )


class _RecordingDP:
    """DP stub that records the type and content of each evaluate() call."""

    def __init__(self, return_value: float = 500.0) -> None:
        self._return_value = return_value
        self.calls: list[Any] = []

    def evaluate(self, inp: Any) -> CorrelationOutput:
        self.calls.append(inp)
        return _make_output(self._return_value)


class _ConstDP:
    """DP stub that always returns a fixed value (no recording)."""

    def __init__(self, return_value: float = 500.0) -> None:
        self._return_value = return_value

    def evaluate(self, inp: Any) -> CorrelationOutput:
        return _make_output(self._return_value)


class _ConstHTC:
    """HTC stub that always returns a fixed value."""

    def __init__(self, return_value: float = 500.0) -> None:
        self._return_value = return_value

    def evaluate(self, inp: Any) -> CorrelationOutput:
        return _make_output(self._return_value)


# ---------------------------------------------------------------------------
# Request builders
# ---------------------------------------------------------------------------


def _fixed_heat_rate_request(
    geom_scalars: dict,
    dp_primary: Any = None,
    dp_primary_is_two_phase: bool = False,
    friction_multiplier: float = 1.0,
    htc_primary: Any = None,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=FixedHeatRate(Q=1000.0),
        geometry=object(),
        discretization=_LUMPED,
        geom_scalars=geom_scalars,
        dp_primary=dp_primary,
        dp_primary_is_two_phase=dp_primary_is_two_phase,
        friction_multiplier=friction_multiplier,
        htc_primary=htc_primary,
    )


def _fixed_wall_temp_request(
    geom_scalars: dict,
    dp_primary: Any = None,
    dp_primary_is_two_phase: bool = False,
    friction_multiplier: float = 1.0,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=FixedWallTemp(T_wall=350.0),
        geometry=object(),
        discretization=_LUMPED,
        geom_scalars={**geom_scalars, "A_ht": 0.1},
        dp_primary=dp_primary,
        dp_primary_is_two_phase=dp_primary_is_two_phase,
        friction_multiplier=friction_multiplier,
        htc_primary=_ConstHTC(500.0),
        primary_T_in=300.0,
    )


def _segmented_fixed_heat_rate_request(
    geom_scalars: dict,
    dp_primary: Any = None,
    dp_primary_is_two_phase: bool = False,
    friction_multiplier: float = 1.0,
    n_cells: int = 3,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=FixedHeatRate(Q=3000.0),
        geometry=object(),
        discretization=DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n_cells),
        geom_scalars=geom_scalars,
        dp_primary=dp_primary,
        dp_primary_is_two_phase=dp_primary_is_two_phase,
        friction_multiplier=friction_multiplier,
    )


# ---------------------------------------------------------------------------
# 1. Single-phase DP path unchanged
# ---------------------------------------------------------------------------


class TestSinglePhasePathUnchanged:
    """Existing single-phase DP behaviour is unaffected by the new flag."""

    def test_epsilon_ntu_single_phase_dp_path_unchanged(self) -> None:
        dp = _RecordingDP(return_value=250.0)
        req = _fixed_heat_rate_request(
            geom_scalars=_SINGLE_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=False,
        )
        result = EpsilonNTUModel().solve(req)
        assert len(dp.calls) == 1
        assert isinstance(dp.calls[0], SinglePhaseDPInput)
        assert result.raw_dP_primary == pytest.approx(250.0)
        assert result.dP_primary == pytest.approx(250.0)

    def test_lmtd_single_phase_dp_path_unchanged(self) -> None:
        dp = _RecordingDP(return_value=250.0)
        req = _fixed_wall_temp_request(
            geom_scalars=_SINGLE_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=False,
        )
        result = LMTDModel().solve(req)
        assert len(dp.calls) == 1
        assert isinstance(dp.calls[0], SinglePhaseDPInput)
        assert result.raw_dP_primary == pytest.approx(250.0)

    def test_segmented_single_phase_dp_path_unchanged(self) -> None:
        dp = _RecordingDP(return_value=100.0)
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=_SINGLE_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=False,
            n_cells=3,
        )
        result = SegmentedMarchModel().solve(req)
        assert all(isinstance(c, SinglePhaseDPInput) for c in dp.calls)
        # 3 cells × 100.0 each = 300.0 total
        assert result.raw_dP_primary == pytest.approx(300.0)

    def test_default_is_single_phase(self) -> None:
        req = _fixed_heat_rate_request(geom_scalars=_SINGLE_PHASE_GEOM)
        assert req.dp_primary_is_two_phase is False


# ---------------------------------------------------------------------------
# 2. Two-phase DP path builds TwoPhaseDPInput
# ---------------------------------------------------------------------------


class TestTwoPhaseDPInputBuilt:
    """When dp_primary_is_two_phase=True the builder creates TwoPhaseDPInput."""

    def test_epsilon_ntu_builds_two_phase_dp_input(self) -> None:
        dp = _RecordingDP(return_value=1000.0)
        req = _fixed_heat_rate_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        EpsilonNTUModel().solve(req)
        assert len(dp.calls) == 1
        assert isinstance(dp.calls[0], TwoPhaseDPInput)

    def test_lmtd_builds_two_phase_dp_input(self) -> None:
        dp = _RecordingDP(return_value=1000.0)
        req = _fixed_wall_temp_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        LMTDModel().solve(req)
        assert len(dp.calls) == 1
        assert isinstance(dp.calls[0], TwoPhaseDPInput)

    def test_segmented_builds_two_phase_dp_input_per_cell(self) -> None:
        dp = _RecordingDP(return_value=1000.0)
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            n_cells=3,
        )
        SegmentedMarchModel().solve(req)
        assert len(dp.calls) == 3
        assert all(isinstance(c, TwoPhaseDPInput) for c in dp.calls)


# ---------------------------------------------------------------------------
# 3. Required property_scalars forwarded exactly
# ---------------------------------------------------------------------------


class TestPropertyScalarsForwarded:
    """property_scalars in the built TwoPhaseDPInput match geom_scalars exactly."""

    def _check_property_scalars(self, inp: TwoPhaseDPInput) -> None:
        ps = inp.property_scalars
        assert ps["rho_l"] == pytest.approx(1000.0)
        assert ps["rho_v"] == pytest.approx(10.0)
        assert ps["mu_l"] == pytest.approx(1e-3)
        assert ps["mu_v"] == pytest.approx(1e-5)

    def test_epsilon_ntu_property_scalars_forwarded(self) -> None:
        dp = _RecordingDP(return_value=1000.0)
        req = _fixed_heat_rate_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        EpsilonNTUModel().solve(req)
        self._check_property_scalars(dp.calls[0])

    def test_lmtd_property_scalars_forwarded(self) -> None:
        dp = _RecordingDP(return_value=1000.0)
        req = _fixed_wall_temp_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        LMTDModel().solve(req)
        self._check_property_scalars(dp.calls[0])

    def test_segmented_property_scalars_forwarded_per_cell(self) -> None:
        dp = _RecordingDP(return_value=1000.0)
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            n_cells=2,
        )
        SegmentedMarchModel().solve(req)
        for call in dp.calls:
            self._check_property_scalars(call)

    def test_extra_geom_scalars_do_not_appear_in_property_scalars(self) -> None:
        dp = _RecordingDP(return_value=1000.0)
        extra = {**_TWO_PHASE_GEOM, "A_ht": 0.5, "roughness": 0.001}
        req = _fixed_heat_rate_request(
            geom_scalars=extra,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        EpsilonNTUModel().solve(req)
        ps = dp.calls[0].property_scalars
        assert "A_ht" not in ps
        assert "roughness" not in ps
        assert set(ps.keys()) == {"rho_l", "rho_v", "mu_l", "mu_v"}


# ---------------------------------------------------------------------------
# 4 & 9. Missing property scalar fails clearly
# ---------------------------------------------------------------------------


class TestMissingPropertyScalars:
    """Missing rho_l / rho_v / mu_l / mu_v raises ValueError."""

    @pytest.mark.parametrize(
        "missing_key",
        ["G", "x", "D_h", "L_cell", "rho_l", "rho_v", "mu_l", "mu_v"],
    )
    def test_every_required_scalar_missing_fails_clearly(self, missing_key: str) -> None:
        gs = {k: v for k, v in _TWO_PHASE_GEOM.items() if k != missing_key}
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=_ConstDP(),
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match=missing_key):
            EpsilonNTUModel().solve(req)

    @pytest.mark.parametrize("missing_key", ["rho_l", "rho_v", "mu_l", "mu_v"])
    def test_epsilon_ntu_missing_scalar_raises(self, missing_key: str) -> None:
        gs = {k: v for k, v in _TWO_PHASE_GEOM.items() if k != missing_key}
        dp = _ConstDP()
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match=missing_key):
            EpsilonNTUModel().solve(req)

    @pytest.mark.parametrize("missing_key", ["rho_l", "rho_v", "mu_l", "mu_v"])
    def test_lmtd_missing_scalar_raises(self, missing_key: str) -> None:
        gs = {k: v for k, v in _TWO_PHASE_GEOM.items() if k != missing_key}
        dp = _ConstDP()
        req = _fixed_wall_temp_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match=missing_key):
            LMTDModel().solve(req)

    @pytest.mark.parametrize("missing_key", ["rho_l", "rho_v", "mu_l", "mu_v"])
    def test_segmented_missing_scalar_raises(self, missing_key: str) -> None:
        gs = {k: v for k, v in _TWO_PHASE_GEOM.items() if k != missing_key}
        dp = _ConstDP()
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            n_cells=2,
        )
        with pytest.raises(ValueError, match=missing_key):
            SegmentedMarchModel().solve(req)


# ---------------------------------------------------------------------------
# 5. Invalid property scalar fails clearly
# ---------------------------------------------------------------------------


class TestInvalidPropertyScalars:
    """Zero, negative, NaN, or inf property scalar raises ValueError."""

    @pytest.mark.parametrize("bad_value", [0.0, -1.0, float("nan"), float("inf")])
    def test_zero_rho_l_raises(self, bad_value: float) -> None:
        gs = {**_TWO_PHASE_GEOM, "rho_l": bad_value}
        dp = _ConstDP()
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError):
            EpsilonNTUModel().solve(req)

    @pytest.mark.parametrize("bad_value", [0.0, -1.0, float("nan"), float("inf")])
    def test_zero_mu_v_raises(self, bad_value: float) -> None:
        gs = {**_TWO_PHASE_GEOM, "mu_v": bad_value}
        dp = _ConstDP()
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError):
            EpsilonNTUModel().solve(req)

    @pytest.mark.parametrize(
        ("key", "bad_value"),
        [
            (key, bad_value)
            for key in ("G", "D_h", "L_cell", "rho_l", "rho_v", "mu_l", "mu_v")
            for bad_value in (0.0, -1.0, float("nan"), float("inf"))
        ],
    )
    def test_every_positive_scalar_rejects_invalid_values(self, key: str, bad_value: float) -> None:
        gs = {**_TWO_PHASE_GEOM, key: bad_value}
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=_ConstDP(),
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match=key):
            EpsilonNTUModel().solve(req)

    @pytest.mark.parametrize("bad_value", [-1.0, 1.1, float("nan"), float("inf")])
    def test_quality_rejects_invalid_values(self, bad_value: float) -> None:
        gs = {**_TWO_PHASE_GEOM, "x": bad_value}
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=_ConstDP(),
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match="x"):
            EpsilonNTUModel().solve(req)


# ---------------------------------------------------------------------------
# 6. Gradient Pa/m × L_cell = pressure drop Pa
# ---------------------------------------------------------------------------


class TestGradientToDropConversion:
    """value[0] [Pa/m] is multiplied by L_cell [m] to produce Pa drop."""

    def test_epsilon_ntu_gradient_times_l_cell(self) -> None:
        gradient_pa_m = 2000.0
        L_cell = 0.5
        dp = _ConstDP(return_value=gradient_pa_m)
        gs = {**_TWO_PHASE_GEOM, "L_cell": L_cell}
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        result = EpsilonNTUModel().solve(req)
        assert result.raw_dP_primary == pytest.approx(gradient_pa_m * L_cell)
        assert result.dP_primary == pytest.approx(gradient_pa_m * L_cell)

    def test_lmtd_gradient_times_l_cell(self) -> None:
        gradient_pa_m = 3000.0
        L_cell = 0.25
        dp = _ConstDP(return_value=gradient_pa_m)
        gs = {**_TWO_PHASE_GEOM, "L_cell": L_cell}
        req = _fixed_wall_temp_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        result = LMTDModel().solve(req)
        assert result.raw_dP_primary == pytest.approx(gradient_pa_m * L_cell)

    def test_segmented_gradient_times_l_cell_per_cell(self) -> None:
        gradient_pa_m = 1000.0
        L_cell = 0.3
        n_cells = 4
        dp = _ConstDP(return_value=gradient_pa_m)
        gs = {**_TWO_PHASE_GEOM, "L_cell": L_cell}
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            n_cells=n_cells,
        )
        result = SegmentedMarchModel().solve(req)
        expected_total = gradient_pa_m * L_cell * n_cells
        assert result.raw_dP_primary == pytest.approx(expected_total)
        assert result.dP_primary == pytest.approx(expected_total)

    def test_gradient_differs_from_raw_value(self) -> None:
        gradient_pa_m = 4000.0
        L_cell = 0.5
        dp = _ConstDP(return_value=gradient_pa_m)
        gs = {**_TWO_PHASE_GEOM, "L_cell": L_cell}
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        result = EpsilonNTUModel().solve(req)
        assert result.raw_dP_primary != pytest.approx(gradient_pa_m)
        assert result.raw_dP_primary == pytest.approx(gradient_pa_m * L_cell)

    def test_l_cell_forwarded_to_tw_phase_dp_input(self) -> None:
        L_cell = 0.7
        dp = _RecordingDP(return_value=1000.0)
        gs = {**_TWO_PHASE_GEOM, "L_cell": L_cell}
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        EpsilonNTUModel().solve(req)
        assert dp.calls[0].L_cell == pytest.approx(L_cell)


# ---------------------------------------------------------------------------
# 7. friction_multiplier applies to pressure drop after conversion
# ---------------------------------------------------------------------------


class TestFrictionMultiplierAfterConversion:
    """friction_multiplier scales the Pa drop (after gradient*L_cell)."""

    def test_epsilon_ntu_friction_multiplier_after_conversion(self) -> None:
        gradient_pa_m = 2000.0
        L_cell = 0.5
        mult = 3.0
        dp = _ConstDP(return_value=gradient_pa_m)
        gs = {**_TWO_PHASE_GEOM, "L_cell": L_cell}
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            friction_multiplier=mult,
        )
        result = EpsilonNTUModel().solve(req)
        raw_expected = gradient_pa_m * L_cell
        assert result.raw_dP_primary == pytest.approx(raw_expected)
        assert result.dP_primary == pytest.approx(raw_expected * mult)

    def test_segmented_friction_multiplier_after_conversion(self) -> None:
        gradient_pa_m = 1000.0
        L_cell = 0.4
        mult = 2.0
        n_cells = 3
        dp = _ConstDP(return_value=gradient_pa_m)
        gs = {**_TWO_PHASE_GEOM, "L_cell": L_cell}
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            friction_multiplier=mult,
            n_cells=n_cells,
        )
        result = SegmentedMarchModel().solve(req)
        raw_expected = gradient_pa_m * L_cell * n_cells
        assert result.raw_dP_primary == pytest.approx(raw_expected)
        assert result.dP_primary == pytest.approx(raw_expected * mult)

    def test_multiplier_one_does_not_change_drop(self) -> None:
        gradient_pa_m = 5000.0
        L_cell = 0.2
        dp = _ConstDP(return_value=gradient_pa_m)
        gs = {**_TWO_PHASE_GEOM, "L_cell": L_cell}
        req_1x = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            friction_multiplier=1.0,
        )
        req_2x = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            friction_multiplier=2.0,
        )
        r1 = EpsilonNTUModel().solve(req_1x)
        r2 = EpsilonNTUModel().solve(req_2x)
        assert r2.dP_primary == pytest.approx(r1.dP_primary * 2.0)
        assert r2.raw_dP_primary == pytest.approx(r1.raw_dP_primary)


# ---------------------------------------------------------------------------
# 8. No hidden L_cell default
# ---------------------------------------------------------------------------


class TestNoHiddenLCellDefault:
    """Missing L_cell raises when dp_primary_is_two_phase=True."""

    def test_epsilon_ntu_missing_l_cell_raises(self) -> None:
        gs = {k: v for k, v in _TWO_PHASE_GEOM.items() if k != "L_cell"}
        dp = _ConstDP()
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match="L_cell"):
            EpsilonNTUModel().solve(req)

    def test_lmtd_missing_l_cell_raises(self) -> None:
        gs = {k: v for k, v in _TWO_PHASE_GEOM.items() if k != "L_cell"}
        dp = _ConstDP()
        req = _fixed_wall_temp_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match="L_cell"):
            LMTDModel().solve(req)

    def test_segmented_missing_l_cell_raises(self) -> None:
        gs = {k: v for k, v in _TWO_PHASE_GEOM.items() if k != "L_cell"}
        dp = _ConstDP()
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            n_cells=2,
        )
        with pytest.raises(ValueError, match="L_cell"):
            SegmentedMarchModel().solve(req)

    def test_zero_l_cell_raises(self) -> None:
        gs = {**_TWO_PHASE_GEOM, "L_cell": 0.0}
        dp = _ConstDP()
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match="L_cell"):
            EpsilonNTUModel().solve(req)


# ---------------------------------------------------------------------------
# 10. Segmented per-cell DP conversion
# ---------------------------------------------------------------------------


class TestSegmentedPerCellConversion:
    """Each cell gets its own TwoPhaseDPInput; raw drop is gradient*L_cell per cell."""

    def test_raw_dp_is_sum_of_per_cell_conversions(self) -> None:
        gradient_pa_m = 2000.0
        L_cell = 0.3
        n_cells = 5
        dp = _ConstDP(return_value=gradient_pa_m)
        gs = {**_TWO_PHASE_GEOM, "L_cell": L_cell}
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            n_cells=n_cells,
        )
        result = SegmentedMarchModel().solve(req)
        expected = gradient_pa_m * L_cell * n_cells
        assert result.raw_dP_primary == pytest.approx(expected)

    def test_zone_profile_cell_dp_matches_per_cell_conversion(self) -> None:
        gradient_pa_m = 3000.0
        L_cell = 0.2
        n_cells = 2
        dp = _ConstDP(return_value=gradient_pa_m)
        gs = {**_TWO_PHASE_GEOM, "L_cell": L_cell}
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            n_cells=n_cells,
        )
        result = SegmentedMarchModel().solve(req)
        expected_cell_drop = gradient_pa_m * L_cell
        for record in result.zone_profile.cells:  # type: ignore[union-attr]
            assert record.raw_dP_cell == pytest.approx(expected_cell_drop)

    def test_n_cells_dp_calls_equals_n_cells(self) -> None:
        dp = _RecordingDP(return_value=1000.0)
        for n in (1, 2, 5):
            dp.calls.clear()
            req = _segmented_fixed_heat_rate_request(
                geom_scalars=_TWO_PHASE_GEOM,
                dp_primary=dp,
                dp_primary_is_two_phase=True,
                n_cells=n,
            )
            SegmentedMarchModel().solve(req)
            assert len(dp.calls) == n


# ---------------------------------------------------------------------------
# 11. All three models support the two-phase path
# ---------------------------------------------------------------------------


class TestAllModelsSupported:
    """EpsilonNTU, LMTD, and Segmented all complete a two-phase DP solve."""

    def test_epsilon_ntu_two_phase_dp_completes(self) -> None:
        dp = _ConstDP(return_value=1500.0)
        req = _fixed_heat_rate_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        result = EpsilonNTUModel().solve(req)
        assert math.isfinite(result.dP_primary)
        assert result.dP_primary > 0.0

    def test_lmtd_two_phase_dp_completes(self) -> None:
        dp = _ConstDP(return_value=1500.0)
        req = _fixed_wall_temp_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        result = LMTDModel().solve(req)
        assert math.isfinite(result.dP_primary)
        assert result.dP_primary > 0.0

    def test_segmented_two_phase_dp_completes(self) -> None:
        dp = _ConstDP(return_value=1500.0)
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            n_cells=3,
        )
        result = SegmentedMarchModel().solve(req)
        assert math.isfinite(result.dP_primary)
        assert result.dP_primary > 0.0

    def test_two_phase_dp_absent_gives_zero_drop(self) -> None:
        req = _fixed_heat_rate_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=None,
            dp_primary_is_two_phase=True,
        )
        result = EpsilonNTUModel().solve(req)
        assert result.dP_primary == pytest.approx(0.0)
        assert result.raw_dP_primary == pytest.approx(0.0)

    def test_ambient_coupling_path_epsilon_ntu(self) -> None:
        dp = _ConstDP(return_value=2000.0)
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=AmbientCoupling(T_ambient=280.0, UA_ambient=10.0),
            geometry=object(),
            discretization=_LUMPED,
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            primary_T_in=300.0,
        )
        result = EpsilonNTUModel().solve(req)
        expected_drop = 2000.0 * _TWO_PHASE_GEOM["L_cell"]
        assert result.raw_dP_primary == pytest.approx(expected_drop)

    @pytest.mark.parametrize(
        "secondary_bc",
        [
            FixedHeatRate(Q=1000.0),
            FixedWallTemp(T_wall=350.0),
            AmbientCoupling(T_ambient=280.0, UA_ambient=10.0),
            SinkInletTempAndFlow(T_in=280.0, mdot_secondary=0.1, cp_secondary=4200.0),
        ],
    )
    def test_epsilon_ntu_all_four_bc_paths(self, secondary_bc: object) -> None:
        dp = _RecordingDP(return_value=2000.0)
        kwargs: dict[str, Any] = {}
        geom = dict(_TWO_PHASE_GEOM)
        if isinstance(secondary_bc, FixedWallTemp):
            geom["A_ht"] = 0.1
            kwargs.update(htc_primary=_ConstHTC(), primary_T_in=300.0)
        elif isinstance(secondary_bc, AmbientCoupling):
            kwargs["primary_T_in"] = 300.0
        elif isinstance(secondary_bc, SinkInletTempAndFlow):
            geom["A_ht"] = 0.1
            kwargs.update(
                htc_primary=_ConstHTC(),
                primary_T_in=300.0,
                primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
                ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
            )
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=secondary_bc,  # type: ignore[arg-type]
            geometry=object(),
            discretization=_LUMPED,
            geom_scalars=geom,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            **kwargs,
        )
        result = EpsilonNTUModel().solve(req)
        assert isinstance(dp.calls[0], TwoPhaseDPInput)
        assert result.raw_dP_primary == pytest.approx(1000.0)

    @pytest.mark.parametrize(
        "secondary_bc",
        [
            FixedWallTemp(T_wall=350.0),
            AmbientCoupling(T_ambient=280.0, UA_ambient=10.0),
        ],
    )
    def test_lmtd_both_supported_bc_paths(self, secondary_bc: object) -> None:
        dp = _RecordingDP(return_value=2000.0)
        geom = dict(_TWO_PHASE_GEOM)
        kwargs: dict[str, Any] = {"primary_T_in": 300.0}
        if isinstance(secondary_bc, FixedWallTemp):
            geom["A_ht"] = 0.1
            kwargs["htc_primary"] = _ConstHTC()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=secondary_bc,  # type: ignore[arg-type]
            geometry=object(),
            discretization=_LUMPED,
            geom_scalars=geom,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            **kwargs,
        )
        result = LMTDModel().solve(req)
        assert isinstance(dp.calls[0], TwoPhaseDPInput)
        assert result.raw_dP_primary == pytest.approx(1000.0)

    @pytest.mark.parametrize(
        "secondary_bc",
        [
            FixedHeatRate(Q=3000.0),
            FixedWallTemp(T_wall=350.0),
            AmbientCoupling(T_ambient=330.0, UA_ambient=10.0),
            SinkInletTempAndFlow(T_in=330.0, mdot_secondary=0.1, cp_secondary=4200.0),
        ],
    )
    def test_segmented_all_four_bc_paths(self, secondary_bc: object) -> None:
        dp = _RecordingDP(return_value=1000.0)
        geom = dict(_TWO_PHASE_GEOM)
        kwargs: dict[str, Any] = {}
        if isinstance(secondary_bc, FixedWallTemp):
            geom["A_ht"] = 0.1
            kwargs.update(
                htc_primary=_ConstHTC(),
                primary_T_in=300.0,
                primary_cp=2000.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            )
        elif isinstance(secondary_bc, AmbientCoupling):
            kwargs.update(
                primary_T_in=300.0,
                primary_cp=2000.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            )
        elif isinstance(secondary_bc, SinkInletTempAndFlow):
            geom["A_ht"] = 0.1
            kwargs.update(
                htc_primary=_ConstHTC(),
                htc_secondary=_ConstHTC(),
                primary_T_in=300.0,
                primary_cp=2000.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
            )
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=secondary_bc,  # type: ignore[arg-type]
            geometry=object(),
            discretization=DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=3),
            geom_scalars=geom,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
            **kwargs,
        )
        result = SegmentedMarchModel().solve(req)
        assert len(dp.calls) == 3
        assert all(isinstance(call, TwoPhaseDPInput) for call in dp.calls)
        assert result.raw_dP_primary == pytest.approx(1500.0)


# ---------------------------------------------------------------------------
# 12. HX models do not resolve CorrelationRegistry
# ---------------------------------------------------------------------------


class TestNoRegistryResolution:
    """HX model modules must not import CorrelationRegistry."""

    def test_epsilon_ntu_no_registry_import(self) -> None:
        import mpl_sim.hx_models.epsilon_ntu as module

        assert not hasattr(module, "CorrelationRegistry")

    def test_lmtd_no_registry_import(self) -> None:
        import mpl_sim.hx_models.lmtd as module

        assert not hasattr(module, "CorrelationRegistry")

    def test_segmented_no_registry_import(self) -> None:
        import mpl_sim.hx_models.segmented as module

        assert not hasattr(module, "CorrelationRegistry")

    def test_base_no_registry_import(self) -> None:
        import mpl_sim.hx_models.base as module

        assert not hasattr(module, "CorrelationRegistry")


# ---------------------------------------------------------------------------
# 13. No CoolProp / PropertyBackend access
# ---------------------------------------------------------------------------


class TestNoCoolPropOrPropertyBackend:
    """HX model modules must not import CoolProp or PropertyBackend."""

    @pytest.mark.parametrize(
        "mod_name",
        [
            "mpl_sim.hx_models.base",
            "mpl_sim.hx_models.epsilon_ntu",
            "mpl_sim.hx_models.lmtd",
            "mpl_sim.hx_models.segmented",
        ],
    )
    def test_no_coolprop(self, mod_name: str) -> None:
        import importlib

        mod = importlib.import_module(mod_name)
        assert not hasattr(mod, "CoolProp")
        assert "CoolProp" not in (getattr(mod, "__file__", "") or "")

    @pytest.mark.parametrize(
        "mod_name",
        [
            "mpl_sim.hx_models.base",
            "mpl_sim.hx_models.epsilon_ntu",
            "mpl_sim.hx_models.lmtd",
            "mpl_sim.hx_models.segmented",
        ],
    )
    def test_no_property_backend(self, mod_name: str) -> None:
        import importlib

        mod = importlib.import_module(mod_name)
        assert not hasattr(mod, "PropertyBackend")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Boundary and edge-case coverage."""

    def test_quality_zero_accepted(self) -> None:
        gs = {**_TWO_PHASE_GEOM, "x": 0.0}
        dp = _ConstDP(return_value=1000.0)
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        result = EpsilonNTUModel().solve(req)
        assert math.isfinite(result.dP_primary)

    def test_quality_one_accepted(self) -> None:
        gs = {**_TWO_PHASE_GEOM, "x": 1.0}
        dp = _ConstDP(return_value=1000.0)
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        result = EpsilonNTUModel().solve(req)
        assert math.isfinite(result.dP_primary)

    def test_quality_out_of_range_raises(self) -> None:
        gs = {**_TWO_PHASE_GEOM, "x": 1.5}
        dp = _ConstDP(return_value=1000.0)
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match="x"):
            EpsilonNTUModel().solve(req)

    def test_dp_primary_none_with_flag_true_gives_zero(self) -> None:
        req = _segmented_fixed_heat_rate_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=None,
            dp_primary_is_two_phase=True,
            n_cells=3,
        )
        result = SegmentedMarchModel().solve(req)
        assert result.raw_dP_primary == pytest.approx(0.0)
        assert result.dP_primary == pytest.approx(0.0)

    def test_two_phase_dp_verdict_in_result(self) -> None:
        dp = _ConstDP(return_value=1000.0)
        req = _fixed_heat_rate_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        result = EpsilonNTUModel().solve(req)
        assert len(result.verdicts) == 1
        assert isinstance(result.verdicts[0], CorrelationOutput)

    def test_g_zero_raises_for_two_phase(self) -> None:
        gs = {**_TWO_PHASE_GEOM, "G": 0.0}
        dp = _ConstDP()
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match="G"):
            EpsilonNTUModel().solve(req)

    def test_d_h_zero_raises_for_two_phase(self) -> None:
        gs = {**_TWO_PHASE_GEOM, "D_h": 0.0}
        dp = _ConstDP()
        req = _fixed_heat_rate_request(
            geom_scalars=gs,
            dp_primary=dp,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match="D_h"):
            EpsilonNTUModel().solve(req)

    def test_two_phase_correlation_with_single_phase_mode_fails_clearly(self) -> None:
        geom = {**_TWO_PHASE_GEOM, "rho": 1000.0, "mu": 1e-3}
        req = _fixed_heat_rate_request(
            geom_scalars=geom,
            dp_primary=MSHTwoPhaseFrictionGradient(),
            dp_primary_is_two_phase=False,
        )
        with pytest.raises(TypeError, match="TwoPhaseDPInput"):
            EpsilonNTUModel().solve(req)

    def test_single_phase_correlation_with_two_phase_mode_fails_clearly(self) -> None:
        req = _fixed_heat_rate_request(
            geom_scalars=_TWO_PHASE_GEOM,
            dp_primary=ChurchillFrictionGradient(),
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(TypeError, match="SinglePhaseDPInput"):
            EpsilonNTUModel().solve(req)
