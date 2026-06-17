"""Input-hardening tests for EpsilonNTUModel — Phase 11C.

Verifies that EpsilonNTUModel raises clear ValueError for:
  - Non-positive G, D_h in _build_htc_input
  - x outside [0, 1] in _build_htc_input
  - Non-positive G, D_h, L_cell in _build_dp_input
  - Non-finite G, D_h, L_cell, x (already caught by _require_scalar; documented here)
  - HTC output nan, inf, 0, or negative when used in UA computation (sink-inlet path)
  - DP output nan or inf (both FixedHeatRate and SinkInletTempAndFlow paths)

DP sign contract (documented):
  dP_primary > 0 means pressure decreases (P_out = P_in - dP_primary).
  Negative DP (pressure gain) is physically allowed and must NOT raise.
  Only non-finite DP raises ValueError.

Smooth-wall convention:
  roughness = 0.0 is the explicit smooth-pipe default when the key is absent.
  Omitting roughness from geom_scalars must succeed.

Architectural constraints respected:
  - No CoolProp, no PropertyBackend, no Network, no Solver.
  - All HTC/DP correlations are local fakes.
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
    HXSolveRequest,
    HXSolveResult,
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=1e6, h=250e3, identity=_IDENTITY)
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

_MINIMAL_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test"),
)

# Valid base geom scalars covering all paths
_VALID_GEOM = {
    "A_ht": 1.0,
    "G": 100.0,
    "D_h": 0.002,
    "x": 0.5,
    "L_cell": 0.1,
    "rho": 1200.0,
    "mu": 2e-4,
}


# ---------------------------------------------------------------------------
# Configurable fake correlations
# ---------------------------------------------------------------------------


class _HTCCorr(Correlation):
    """Returns a configurable scalar value for the HTC output."""

    def __init__(self, value: float = 1000.0) -> None:
        self._value = value

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(self._value,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef("htc_fake", "0"),
                violated=(),
            ),
            metadata=ClosureMetadata("htc_fake", "0", SourceRef("test")),
        )


class _DPCorr(Correlation):
    """Returns a configurable scalar value for the DP output."""

    def __init__(self, value: float = 500.0) -> None:
        self._value = value

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(self._value,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef("dp_fake", "0"),
                violated=(),
            ),
            metadata=ClosureMetadata("dp_fake", "0", SourceRef("test")),
        )


# ---------------------------------------------------------------------------
# Request builders
# ---------------------------------------------------------------------------


def _fixed_heat_req(
    geom: dict | None = None,
    htc_primary: Correlation | None = None,
    dp_primary: Correlation | None = None,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.05,
        secondary_bc=FixedHeatRate(Q=1000.0),
        geometry=object(),
        discretization=_DISC,
        geom_scalars=geom if geom is not None else _VALID_GEOM,
        htc_primary=htc_primary,
        dp_primary=dp_primary,
    )


def _sink_req(
    geom: dict | None = None,
    htc_primary: Correlation | None = None,
    htc_secondary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    ua_mode: UAComputationMode = UAComputationMode.PRIMARY_ONLY,
    htc_value: float = 1000.0,
) -> HXSolveRequest:
    """Build a SinkInletTempAndFlow request with valid mandatory fields."""
    if htc_primary is None:
        htc_primary = _HTCCorr(htc_value)
    if ua_mode is UAComputationMode.TWO_SIDED and htc_secondary is None:
        htc_secondary = _HTCCorr(htc_value)
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.05,
        secondary_bc=SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.5, cp_secondary=4000.0),
        geometry=object(),
        discretization=_DISC,
        geom_scalars=geom if geom is not None else _VALID_GEOM,
        htc_primary=htc_primary,
        htc_secondary=htc_secondary,
        dp_primary=dp_primary,
        primary_T_in=350.0,
        primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
        ua_computation_mode=ua_mode,
    )


# ---------------------------------------------------------------------------
# Geom scalar hardening — _build_htc_input (G, D_h, x)
# ---------------------------------------------------------------------------


class TestHTCGeomHardening:
    """EpsilonNTUModel._build_htc_input rejects non-positive or out-of-range scalars."""

    # --- G ---

    def test_zero_G_in_htc_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "G": 0.0}
        with pytest.raises(ValueError, match="'G'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))

    def test_negative_G_in_htc_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "G": -100.0}
        with pytest.raises(ValueError, match="'G'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))

    def test_nan_G_in_htc_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "G": float("nan")}
        with pytest.raises(ValueError, match="'G'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))

    def test_inf_G_in_htc_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "G": float("inf")}
        with pytest.raises(ValueError, match="'G'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))

    # --- D_h ---

    def test_zero_D_h_in_htc_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "D_h": 0.0}
        with pytest.raises(ValueError, match="'D_h'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))

    def test_negative_D_h_in_htc_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "D_h": -0.002}
        with pytest.raises(ValueError, match="'D_h'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))

    def test_nan_D_h_in_htc_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "D_h": float("nan")}
        with pytest.raises(ValueError, match="'D_h'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))

    # --- x (vapor quality) ---

    def test_x_below_zero_raises(self) -> None:
        geom = {**_VALID_GEOM, "x": -0.1}
        with pytest.raises(ValueError, match="'x'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))

    def test_x_above_one_raises(self) -> None:
        geom = {**_VALID_GEOM, "x": 1.1}
        with pytest.raises(ValueError, match="'x'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))

    def test_nan_x_raises(self) -> None:
        geom = {**_VALID_GEOM, "x": float("nan")}
        with pytest.raises(ValueError, match="'x'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))

    def test_x_at_zero_is_valid(self) -> None:
        geom = {**_VALID_GEOM, "x": 0.0}
        result = EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))
        assert isinstance(result, HXSolveResult)

    def test_x_at_one_is_valid(self) -> None:
        geom = {**_VALID_GEOM, "x": 1.0}
        result = EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, htc_primary=_HTCCorr()))
        assert isinstance(result, HXSolveResult)


# ---------------------------------------------------------------------------
# Geom scalar hardening — _build_dp_input (G, D_h, L_cell, rho, mu)
# ---------------------------------------------------------------------------


class TestDPGeomHardening:
    """EpsilonNTUModel._build_dp_input rejects non-positive scalars."""

    # --- G ---

    def test_zero_G_in_dp_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "G": 0.0}
        with pytest.raises(ValueError, match="'G'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))

    def test_negative_G_in_dp_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "G": -50.0}
        with pytest.raises(ValueError, match="'G'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))

    def test_nan_G_in_dp_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "G": float("nan")}
        with pytest.raises(ValueError, match="'G'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))

    # --- D_h ---

    def test_zero_D_h_in_dp_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "D_h": 0.0}
        with pytest.raises(ValueError, match="'D_h'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))

    def test_negative_D_h_in_dp_path_raises(self) -> None:
        geom = {**_VALID_GEOM, "D_h": -0.001}
        with pytest.raises(ValueError, match="'D_h'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))

    # --- L_cell ---

    def test_zero_L_cell_raises(self) -> None:
        geom = {**_VALID_GEOM, "L_cell": 0.0}
        with pytest.raises(ValueError, match="'L_cell'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))

    def test_negative_L_cell_raises(self) -> None:
        geom = {**_VALID_GEOM, "L_cell": -0.1}
        with pytest.raises(ValueError, match="'L_cell'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))

    def test_nan_L_cell_raises(self) -> None:
        geom = {**_VALID_GEOM, "L_cell": float("nan")}
        with pytest.raises(ValueError, match="'L_cell'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))

    # --- rho and mu (pre-existing checks, documented here) ---

    def test_zero_rho_raises(self) -> None:
        geom = {**_VALID_GEOM, "rho": 0.0}
        with pytest.raises(ValueError, match="'rho'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))

    def test_zero_mu_raises(self) -> None:
        geom = {**_VALID_GEOM, "mu": 0.0}
        with pytest.raises(ValueError, match="'mu'"):
            EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))

    # --- roughness=0.0 smooth-wall convention ---

    def test_roughness_absent_defaults_to_smooth_wall(self) -> None:
        geom = {k: v for k, v in _VALID_GEOM.items() if k != "roughness"}
        result = EpsilonNTUModel().solve(_fixed_heat_req(geom=geom, dp_primary=_DPCorr()))
        assert isinstance(result, HXSolveResult)


# ---------------------------------------------------------------------------
# HTC output validation — values returned by correlation used for UA
# ---------------------------------------------------------------------------


class TestHTCOutputValidation:
    """HTC output must be finite and > 0 when used for UA in sink-inlet path.

    The FixedHeatRate path calls HTC only for verdict tracking (not UA), so
    invalid HTC outputs in that path are NOT validated here.
    """

    # --- PRIMARY_ONLY path ---

    def test_primary_htc_nan_raises_primary_only(self) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(_sink_req(htc_primary=_HTCCorr(float("nan"))))

    def test_primary_htc_inf_raises_primary_only(self) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(_sink_req(htc_primary=_HTCCorr(float("inf"))))

    def test_primary_htc_zero_raises_primary_only(self) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(_sink_req(htc_primary=_HTCCorr(0.0)))

    def test_primary_htc_negative_raises_primary_only(self) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(_sink_req(htc_primary=_HTCCorr(-500.0)))

    # --- TWO_SIDED path — primary HTC invalid ---

    def test_primary_htc_nan_raises_two_sided(self) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(
                _sink_req(
                    ua_mode=UAComputationMode.TWO_SIDED,
                    htc_primary=_HTCCorr(float("nan")),
                    htc_secondary=_HTCCorr(1000.0),
                )
            )

    def test_primary_htc_zero_raises_two_sided(self) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(
                _sink_req(
                    ua_mode=UAComputationMode.TWO_SIDED,
                    htc_primary=_HTCCorr(0.0),
                    htc_secondary=_HTCCorr(1000.0),
                )
            )

    # --- TWO_SIDED path — secondary HTC invalid ---

    def test_secondary_htc_nan_raises_two_sided(self) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(
                _sink_req(
                    ua_mode=UAComputationMode.TWO_SIDED,
                    htc_primary=_HTCCorr(1000.0),
                    htc_secondary=_HTCCorr(float("nan")),
                )
            )

    def test_secondary_htc_zero_raises_two_sided(self) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(
                _sink_req(
                    ua_mode=UAComputationMode.TWO_SIDED,
                    htc_primary=_HTCCorr(1000.0),
                    htc_secondary=_HTCCorr(0.0),
                )
            )

    def test_secondary_htc_negative_raises_two_sided(self) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(
                _sink_req(
                    ua_mode=UAComputationMode.TWO_SIDED,
                    htc_primary=_HTCCorr(1000.0),
                    htc_secondary=_HTCCorr(-200.0),
                )
            )

    def test_secondary_htc_inf_raises_two_sided(self) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(
                _sink_req(
                    ua_mode=UAComputationMode.TWO_SIDED,
                    htc_primary=_HTCCorr(1000.0),
                    htc_secondary=_HTCCorr(float("inf")),
                )
            )

    # --- Valid HTC output still works ---

    def test_valid_positive_htc_succeeds_primary_only(self) -> None:
        result = EpsilonNTUModel().solve(_sink_req(htc_primary=_HTCCorr(1000.0)))
        assert isinstance(result, HXSolveResult)

    def test_valid_positive_htc_succeeds_two_sided(self) -> None:
        result = EpsilonNTUModel().solve(
            _sink_req(
                ua_mode=UAComputationMode.TWO_SIDED,
                htc_primary=_HTCCorr(2000.0),
                htc_secondary=_HTCCorr(1500.0),
            )
        )
        assert isinstance(result, HXSolveResult)


# ---------------------------------------------------------------------------
# DP output validation — finite required; sign is allowed
# ---------------------------------------------------------------------------


class TestDPOutputValidation:
    """DP output must be finite.

    Sign contract: negative dP means pressure gain (P_out = P_in - dP_primary).
    Negative values are physically valid and must NOT raise.
    """

    # --- Non-finite DP raises (FixedHeatRate path) ---

    def test_dp_nan_raises_fixed_heat_rate(self) -> None:
        with pytest.raises(ValueError, match="DP"):
            EpsilonNTUModel().solve(_fixed_heat_req(dp_primary=_DPCorr(float("nan"))))

    def test_dp_pos_inf_raises_fixed_heat_rate(self) -> None:
        with pytest.raises(ValueError, match="DP"):
            EpsilonNTUModel().solve(_fixed_heat_req(dp_primary=_DPCorr(float("inf"))))

    def test_dp_neg_inf_raises_fixed_heat_rate(self) -> None:
        with pytest.raises(ValueError, match="DP"):
            EpsilonNTUModel().solve(_fixed_heat_req(dp_primary=_DPCorr(float("-inf"))))

    # --- Non-finite DP raises (SinkInletTempAndFlow path) ---

    def test_dp_nan_raises_sink_inlet(self) -> None:
        with pytest.raises(ValueError, match="DP"):
            EpsilonNTUModel().solve(_sink_req(dp_primary=_DPCorr(float("nan"))))

    def test_dp_pos_inf_raises_sink_inlet(self) -> None:
        with pytest.raises(ValueError, match="DP"):
            EpsilonNTUModel().solve(_sink_req(dp_primary=_DPCorr(float("inf"))))

    def test_dp_neg_inf_raises_sink_inlet(self) -> None:
        with pytest.raises(ValueError, match="DP"):
            EpsilonNTUModel().solve(_sink_req(dp_primary=_DPCorr(float("-inf"))))

    # --- Negative DP is allowed (pressure gain) ---

    def test_negative_dp_is_valid_fixed_heat_rate(self) -> None:
        result = EpsilonNTUModel().solve(_fixed_heat_req(dp_primary=_DPCorr(-300.0)))
        assert isinstance(result, HXSolveResult)
        assert math.isclose(result.dP_primary, -300.0, rel_tol=1e-12)

    def test_negative_dp_is_valid_sink_inlet(self) -> None:
        result = EpsilonNTUModel().solve(_sink_req(dp_primary=_DPCorr(-200.0)))
        assert isinstance(result, HXSolveResult)
        assert math.isclose(result.dP_primary, -200.0, rel_tol=1e-12)

    def test_zero_dp_is_valid(self) -> None:
        result = EpsilonNTUModel().solve(_fixed_heat_req(dp_primary=_DPCorr(0.0)))
        assert isinstance(result, HXSolveResult)
        assert result.dP_primary == 0.0
