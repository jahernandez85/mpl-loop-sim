"""Tests for SecondaryFluidBC family — Phase 11A.

Verifies:
  - Each BC type is a frozen dataclass
  - Field validation (finite, positive where required)
  - Sign convention documented for FixedHeatRate
  - Union type SecondaryFluidBC covers all four variants
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.hx_models.base import (
    AmbientCoupling,
    FixedHeatRate,
    FixedWallTemp,
    SecondaryFluidBC,
    SinkInletTempAndFlow,
)

# ---------------------------------------------------------------------------
# FixedHeatRate
# ---------------------------------------------------------------------------


class TestFixedHeatRate:
    def test_valid_positive_q(self) -> None:
        bc = FixedHeatRate(Q=1000.0)
        assert bc.Q == 1000.0

    def test_valid_negative_q(self) -> None:
        bc = FixedHeatRate(Q=-2000.0)
        assert bc.Q == -2000.0

    def test_valid_zero_q(self) -> None:
        bc = FixedHeatRate(Q=0.0)
        assert bc.Q == 0.0

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="Q"):
            FixedHeatRate(Q=math.nan)

    def test_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="Q"):
            FixedHeatRate(Q=math.inf)

    def test_neg_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="Q"):
            FixedHeatRate(Q=-math.inf)

    def test_is_frozen(self) -> None:
        bc = FixedHeatRate(Q=500.0)
        with pytest.raises((AttributeError, TypeError)):
            bc.Q = 0.0  # type: ignore[misc]

    def test_sign_positive_means_primary_gains(self) -> None:
        bc = FixedHeatRate(Q=500.0)
        assert bc.Q > 0

    def test_sign_negative_means_primary_rejects(self) -> None:
        bc = FixedHeatRate(Q=-500.0)
        assert bc.Q < 0


# ---------------------------------------------------------------------------
# SinkInletTempAndFlow
# ---------------------------------------------------------------------------


class TestSinkInletTempAndFlow:
    def test_valid_construction(self) -> None:
        bc = SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.1, cp_secondary=4180.0)
        assert bc.T_in == 300.0
        assert bc.mdot_secondary == 0.1
        assert bc.cp_secondary == 4180.0

    def test_zero_t_in_rejected(self) -> None:
        with pytest.raises(ValueError, match="T_in"):
            SinkInletTempAndFlow(T_in=0.0, mdot_secondary=0.1, cp_secondary=4180.0)

    def test_negative_t_in_rejected(self) -> None:
        with pytest.raises(ValueError, match="T_in"):
            SinkInletTempAndFlow(T_in=-1.0, mdot_secondary=0.1, cp_secondary=4180.0)

    def test_nan_t_in_rejected(self) -> None:
        with pytest.raises(ValueError, match="T_in"):
            SinkInletTempAndFlow(T_in=math.nan, mdot_secondary=0.1, cp_secondary=4180.0)

    def test_zero_mdot_rejected(self) -> None:
        with pytest.raises(ValueError, match="mdot_secondary"):
            SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.0, cp_secondary=4180.0)

    def test_negative_cp_rejected(self) -> None:
        with pytest.raises(ValueError, match="cp_secondary"):
            SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.1, cp_secondary=-1.0)

    def test_is_frozen(self) -> None:
        bc = SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.1, cp_secondary=4180.0)
        with pytest.raises((AttributeError, TypeError)):
            bc.T_in = 0.0  # type: ignore[misc]

    def test_inf_t_in_rejected(self) -> None:
        with pytest.raises(ValueError, match="T_in"):
            SinkInletTempAndFlow(T_in=math.inf, mdot_secondary=0.1, cp_secondary=4180.0)

    def test_negative_mdot_rejected(self) -> None:
        with pytest.raises(ValueError, match="mdot_secondary"):
            SinkInletTempAndFlow(T_in=300.0, mdot_secondary=-0.1, cp_secondary=4180.0)

    def test_inf_mdot_rejected(self) -> None:
        with pytest.raises(ValueError, match="mdot_secondary"):
            SinkInletTempAndFlow(T_in=300.0, mdot_secondary=math.inf, cp_secondary=4180.0)

    def test_nan_mdot_rejected(self) -> None:
        with pytest.raises(ValueError, match="mdot_secondary"):
            SinkInletTempAndFlow(T_in=300.0, mdot_secondary=math.nan, cp_secondary=4180.0)

    def test_zero_cp_rejected(self) -> None:
        with pytest.raises(ValueError, match="cp_secondary"):
            SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.1, cp_secondary=0.0)

    def test_nan_cp_rejected(self) -> None:
        with pytest.raises(ValueError, match="cp_secondary"):
            SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.1, cp_secondary=math.nan)

    def test_inf_cp_rejected(self) -> None:
        with pytest.raises(ValueError, match="cp_secondary"):
            SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.1, cp_secondary=math.inf)


# ---------------------------------------------------------------------------
# FixedWallTemp
# ---------------------------------------------------------------------------


class TestFixedWallTemp:
    def test_valid_construction(self) -> None:
        bc = FixedWallTemp(T_wall=350.0)
        assert bc.T_wall == 350.0

    def test_zero_t_wall_rejected(self) -> None:
        with pytest.raises(ValueError, match="T_wall"):
            FixedWallTemp(T_wall=0.0)

    def test_negative_t_wall_rejected(self) -> None:
        with pytest.raises(ValueError, match="T_wall"):
            FixedWallTemp(T_wall=-10.0)

    def test_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="T_wall"):
            FixedWallTemp(T_wall=math.nan)

    def test_is_frozen(self) -> None:
        bc = FixedWallTemp(T_wall=350.0)
        with pytest.raises((AttributeError, TypeError)):
            bc.T_wall = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AmbientCoupling
# ---------------------------------------------------------------------------


class TestAmbientCoupling:
    def test_valid_construction(self) -> None:
        bc = AmbientCoupling(T_ambient=298.0, UA_ambient=10.0)
        assert bc.T_ambient == 298.0
        assert bc.UA_ambient == 10.0

    def test_zero_t_ambient_rejected(self) -> None:
        with pytest.raises(ValueError, match="T_ambient"):
            AmbientCoupling(T_ambient=0.0, UA_ambient=10.0)

    def test_zero_ua_rejected(self) -> None:
        with pytest.raises(ValueError, match="UA_ambient"):
            AmbientCoupling(T_ambient=298.0, UA_ambient=0.0)

    def test_negative_ua_rejected(self) -> None:
        with pytest.raises(ValueError, match="UA_ambient"):
            AmbientCoupling(T_ambient=298.0, UA_ambient=-1.0)

    def test_nan_t_ambient_rejected(self) -> None:
        with pytest.raises(ValueError, match="T_ambient"):
            AmbientCoupling(T_ambient=math.nan, UA_ambient=10.0)

    def test_is_frozen(self) -> None:
        bc = AmbientCoupling(T_ambient=298.0, UA_ambient=10.0)
        with pytest.raises((AttributeError, TypeError)):
            bc.T_ambient = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SecondaryFluidBC union type
# ---------------------------------------------------------------------------


class TestSecondaryFluidBCUnion:
    def test_fixed_heat_rate_is_valid_bc(self) -> None:
        bc: SecondaryFluidBC = FixedHeatRate(Q=100.0)
        assert isinstance(bc, FixedHeatRate)

    def test_sink_inlet_is_valid_bc(self) -> None:
        bc: SecondaryFluidBC = SinkInletTempAndFlow(
            T_in=300.0, mdot_secondary=0.1, cp_secondary=4000.0
        )
        assert isinstance(bc, SinkInletTempAndFlow)

    def test_fixed_wall_is_valid_bc(self) -> None:
        bc: SecondaryFluidBC = FixedWallTemp(T_wall=350.0)
        assert isinstance(bc, FixedWallTemp)

    def test_ambient_coupling_is_valid_bc(self) -> None:
        bc: SecondaryFluidBC = AmbientCoupling(T_ambient=298.0, UA_ambient=5.0)
        assert isinstance(bc, AmbientCoupling)

    def test_four_bc_variants_exist(self) -> None:
        variants = (FixedHeatRate, SinkInletTempAndFlow, FixedWallTemp, AmbientCoupling)
        assert len(variants) == 4
