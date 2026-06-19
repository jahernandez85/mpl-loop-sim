"""Phase 11Q: Evaporator/Condenser scenario plumbing foundation tests.

Verifies:
  1.  Existing component behavior unchanged by default (no new required fields).
  2.  EvaporatorHXInput.q_flux_primary forwarded to HXSolveRequest.
  3.  EvaporatorHXInput.dp_primary_is_two_phase forwarded to HXSolveRequest.
  4.  CondenserHXInput.q_flux_primary forwarded to HXSolveRequest.
  5.  CondenserHXInput.dp_primary_is_two_phase forwarded to HXSolveRequest.
  6.  Evaporator can use ShahBoilingHTC when q_flux_primary is supplied.
  7.  Evaporator with ShahBoilingHTC fails clearly when q_flux_primary is absent.
  8.  Evaporator with two-phase DP fails clearly when required scalar is missing.
  9.  Condenser can use YanCondensationHTC when supplied explicitly.
  10. Condenser can use two-phase DP mode and property scalars.
  11. No component resolves CorrelationRegistry.
  12. No CoolProp / PropertyBackend in components.
  13. No hidden defaults — q_flux_primary and dp_primary_is_two_phase are explicit.

Architecture constraints asserted:
  - No registry resolution inside components.
  - No CoolProp or PropertyBackend in component source.
  - Caller-supplied closures are injected explicitly; components do not choose them.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId
from mpl_sim.components.condenser import CondenserComponent, CondenserHXInput
from mpl_sim.components.evaporator import EvaporatorComponent, EvaporatorHXInput
from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations import (
    MSHTwoPhaseFrictionGradient,
    ShahBoilingHTC,
    YanCondensationHTC,
)
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import (
    FinGeometry,
    MicrochannelGeometry,
    PlateGeometry,
    PortDimensions,
)
from mpl_sim.hx_models.base import (
    FixedHeatRate,
    FixedWallTemp,
    HeatExchangerModel,
    HeatExchangerModelKind,
    HXSolveRequest,
    HXSolveResult,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=500_000.0, h=250_000.0, identity=_IDENTITY)
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

_FIN = FinGeometry(fin_pitch=500.0, fin_height=0.008, fin_thickness=0.0001)
_MICROCHANNEL_GEOM = MicrochannelGeometry(
    N_channels=40,
    D_h_channel=0.001,
    fin_geometry=_FIN,
    A_heated=0.05,
    wall_mass=0.15,
    wall_material="aluminium",
)
_PLATE_GEOM = PlateGeometry(
    N_plates=20,
    chevron_angle=60.0,
    plate_spacing=0.002,
    port_dims=PortDimensions(diameter=0.01),
    A_per_plate=0.02,
)

_EVAP_ID = ComponentId("evap1")
_COND_ID = ComponentId("cond1")


def _evap() -> EvaporatorComponent:
    return EvaporatorComponent(component_id=_EVAP_ID, geometry=_MICROCHANNEL_GEOM)


def _cond() -> CondenserComponent:
    return CondenserComponent(component_id=_COND_ID, geometry=_PLATE_GEOM)


# ---------------------------------------------------------------------------
# Minimal recording HX model — captures HXSolveRequest without running physics
# ---------------------------------------------------------------------------


class _RecordingModel(HeatExchangerModel):
    """Records the last HXSolveRequest; returns a trivial fixed-heat-rate result."""

    def __init__(self) -> None:
        self.call_count = 0
        self.last_req: HXSolveRequest | None = None

    def kind(self) -> HeatExchangerModelKind:
        return HeatExchangerModelKind.EPSILON_NTU

    def solve(self, req: HXSolveRequest) -> HXSolveResult:
        self.call_count += 1
        self.last_req = req
        bc = req.secondary_bc
        assert isinstance(bc, FixedHeatRate)
        h_out = req.primary_state_in.h + bc.Q / req.primary_mdot
        state_out = FluidState(
            P=req.primary_state_in.P,
            h=h_out,
            identity=req.primary_state_in.identity,
        )
        return HXSolveResult(
            primary_state_out=state_out,
            Q=bc.Q,
            dP_primary=0.0,
            verdicts=(),
        )


def _rec_evap_inp(rec: _RecordingModel, **kwargs) -> EvaporatorHXInput:  # type: ignore[no-untyped-def]
    return EvaporatorHXInput(
        primary_state_in=_STATE_IN,
        primary_mdot=0.05,
        secondary_bc=FixedHeatRate(Q=500.0),
        model=rec,
        discretization=_DISC,
        **kwargs,
    )


def _rec_cond_inp(rec: _RecordingModel, **kwargs) -> CondenserHXInput:  # type: ignore[no-untyped-def]
    return CondenserHXInput(
        primary_state_in=_STATE_IN,
        primary_mdot=0.05,
        secondary_bc=FixedHeatRate(Q=-500.0),
        model=rec,
        discretization=_DISC,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1 — Default behavior unchanged
# ---------------------------------------------------------------------------


class TestDefaultBehaviorUnchanged:
    """Items 1, 11, 13: existing behavior is preserved; no new required fields."""

    def test_evaporator_default_q_flux_primary_is_none(self) -> None:
        rec = _RecordingModel()
        _evap().evaluate_heat_exchanger(_rec_evap_inp(rec))
        assert rec.last_req is not None
        assert rec.last_req.q_flux_primary is None

    def test_evaporator_default_dp_primary_is_two_phase_is_false(self) -> None:
        rec = _RecordingModel()
        _evap().evaluate_heat_exchanger(_rec_evap_inp(rec))
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is False

    def test_condenser_default_q_flux_primary_is_none(self) -> None:
        rec = _RecordingModel()
        _cond().evaluate_heat_exchanger(_rec_cond_inp(rec))
        assert rec.last_req is not None
        assert rec.last_req.q_flux_primary is None

    def test_condenser_default_dp_primary_is_two_phase_is_false(self) -> None:
        rec = _RecordingModel()
        _cond().evaluate_heat_exchanger(_rec_cond_inp(rec))
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is False

    def test_evaporator_energy_balance_unchanged(self) -> None:
        Q, mdot = 2000.0, 0.05
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
            secondary_bc=FixedHeatRate(Q=Q),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        result = _evap().evaluate_heat_exchanger(inp)
        expected_h = _STATE_IN.h + Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)

    def test_condenser_energy_balance_unchanged(self) -> None:
        Q, mdot = -3000.0, 0.05
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
            secondary_bc=FixedHeatRate(Q=Q),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        result = _cond().evaluate_heat_exchanger(inp)
        expected_h = _STATE_IN.h + Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# 2–3 — Evaporator forwards q_flux_primary and dp_primary_is_two_phase
# ---------------------------------------------------------------------------


class TestEvaporatorForwardsNewFields:
    """Items 2, 3: new fields reach HXSolveRequest exactly as supplied."""

    def test_forwards_geom_scalars_unchanged(self) -> None:
        rec = _RecordingModel()
        geom_scalars = {"G": 123.0, "x": 0.25, "custom": 9.5}
        inp = _rec_evap_inp(rec, geom_scalars=geom_scalars)
        _evap().evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.geom_scalars == geom_scalars

    def test_forwards_q_flux_primary(self) -> None:
        rec = _RecordingModel()
        inp = _rec_evap_inp(rec, q_flux_primary=8000.0)
        _evap().evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert math.isclose(rec.last_req.q_flux_primary, 8000.0)

    def test_forwards_dp_primary_is_two_phase_true(self) -> None:
        rec = _RecordingModel()
        inp = _rec_evap_inp(rec, dp_primary_is_two_phase=True)
        _evap().evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is True

    def test_forwards_dp_primary_is_two_phase_false(self) -> None:
        rec = _RecordingModel()
        inp = _rec_evap_inp(rec, dp_primary_is_two_phase=False)
        _evap().evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is False

    def test_q_flux_primary_none_reaches_request(self) -> None:
        rec = _RecordingModel()
        inp = _rec_evap_inp(rec, q_flux_primary=None)
        _evap().evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.q_flux_primary is None


# ---------------------------------------------------------------------------
# 4–5 — Condenser forwards q_flux_primary and dp_primary_is_two_phase
# ---------------------------------------------------------------------------


class TestCondenserForwardsNewFields:
    """Items 4, 5: new fields reach HXSolveRequest exactly as supplied."""

    def test_forwards_geom_scalars_unchanged(self) -> None:
        rec = _RecordingModel()
        geom_scalars = {"G": 234.0, "x": 0.75, "custom": 4.5}
        inp = _rec_cond_inp(rec, geom_scalars=geom_scalars)
        _cond().evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.geom_scalars == geom_scalars

    def test_forwards_q_flux_primary(self) -> None:
        rec = _RecordingModel()
        inp = _rec_cond_inp(rec, q_flux_primary=6000.0)
        _cond().evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert math.isclose(rec.last_req.q_flux_primary, 6000.0)

    def test_forwards_dp_primary_is_two_phase_true(self) -> None:
        rec = _RecordingModel()
        inp = _rec_cond_inp(rec, dp_primary_is_two_phase=True)
        _cond().evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is True

    def test_forwards_dp_primary_is_two_phase_false(self) -> None:
        rec = _RecordingModel()
        inp = _rec_cond_inp(rec, dp_primary_is_two_phase=False)
        _cond().evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is False

    def test_q_flux_primary_none_reaches_request(self) -> None:
        rec = _RecordingModel()
        inp = _rec_cond_inp(rec, q_flux_primary=None)
        _cond().evaluate_heat_exchanger(inp)
        assert rec.last_req is not None
        assert rec.last_req.q_flux_primary is None


# ---------------------------------------------------------------------------
# Common geom_scalars for two-phase scenarios
# ---------------------------------------------------------------------------

# Scalars needed by ShahBoilingHTC via EpsilonNTUModel FixedWallTemp:
#   HX builder uses: G, x, D_h from geom_scalars
#   Shah uses from geom_scalars: rho_l, rho_v, mu_l, k_l, Pr_l, h_fg
#   Two-phase DP builder additionally uses: L_cell, rho_l, rho_v, mu_l, mu_v
_SHAH_GEOM_SCALARS = {
    "G": 300.0,
    "x": 0.3,
    "D_h": 0.001,
    "A_ht": 0.05,
    "rho_l": 1200.0,
    "rho_v": 50.0,
    "mu_l": 2e-4,
    "k_l": 0.08,
    "Pr_l": 3.5,
    "h_fg": 200_000.0,
    "mu_v": 1.5e-5,
    "L_cell": 0.1,
}

# Scalars needed by YanCondensationHTC via EpsilonNTUModel FixedWallTemp:
#   HX builder uses: G, x, D_h from geom_scalars
#   Yan uses from geom_scalars: rho_l, rho_v, mu_l, k_l, Pr_l
#   Two-phase DP builder additionally uses: L_cell, mu_v
_YAN_GEOM_SCALARS = {
    "G": 250.0,
    "x": 0.4,
    "D_h": 0.001,
    "A_ht": 0.05,
    "rho_l": 1200.0,
    "rho_v": 40.0,
    "mu_l": 2e-4,
    "k_l": 0.08,
    "Pr_l": 3.5,
    "mu_v": 1.2e-5,
    "L_cell": 0.1,
}


# ---------------------------------------------------------------------------
# 6 — Evaporator can use ShahBoilingHTC when q_flux_primary is supplied
# ---------------------------------------------------------------------------


class TestEvaporatorShahBoiling:
    """Item 6: ShahBoilingHTC injectable through Evaporator when q_flux given."""

    def test_shah_htc_runs_without_error(self) -> None:
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
            q_flux_primary=5000.0,
        )
        result = _evap().evaluate_heat_exchanger(inp)
        assert isinstance(result, HXSolveResult)

    def test_shah_htc_energy_balance(self) -> None:
        mdot = 0.05
        T_wall, T_in = 290.0, 280.0
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
            secondary_bc=FixedWallTemp(T_wall=T_wall),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=T_in,
            q_flux_primary=5000.0,
        )
        result = _evap().evaluate_heat_exchanger(inp)
        # Q > 0 (T_wall > T_primary) and h_out = h_in + Q/mdot
        assert result.Q > 0.0
        expected_h = _STATE_IN.h + result.Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)

    def test_shah_htc_produces_valid_verdict(self) -> None:
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
            q_flux_primary=5000.0,
        )
        result = _evap().evaluate_heat_exchanger(inp)
        assert len(result.verdicts) >= 1

    def test_shah_htc_with_two_phase_dp(self) -> None:
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            dp_primary=MSHTwoPhaseFrictionGradient(),
            primary_T_in=280.0,
            q_flux_primary=5000.0,
            dp_primary_is_two_phase=True,
        )
        result = _evap().evaluate_heat_exchanger(inp)
        assert isinstance(result, HXSolveResult)
        # Two-phase DP produces positive pressure drop
        assert result.dP_primary >= 0.0


# ---------------------------------------------------------------------------
# 7 — Missing q_flux_primary for Shah fails clearly
# ---------------------------------------------------------------------------


class TestMissingQFluxForShah:
    """Item 7: Shah raises clearly when q_flux_primary not supplied."""

    def test_shah_without_q_flux_raises(self) -> None:
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
            # q_flux_primary intentionally absent — default is None
        )
        with pytest.raises(ValueError):
            _evap().evaluate_heat_exchanger(inp)

    def test_shah_without_q_flux_error_is_informative(self) -> None:
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
        )
        with pytest.raises(ValueError, match="q_flux"):
            _evap().evaluate_heat_exchanger(inp)

    def test_q_flux_primary_validation_zero_rejected_at_hx_request(self) -> None:
        rec = _RecordingModel()
        inp = _rec_evap_inp(rec, q_flux_primary=0.0)
        with pytest.raises(ValueError):
            _evap().evaluate_heat_exchanger(inp)

    def test_q_flux_primary_validation_negative_rejected_at_hx_request(self) -> None:
        rec = _RecordingModel()
        inp = _rec_evap_inp(rec, q_flux_primary=-100.0)
        with pytest.raises(ValueError):
            _evap().evaluate_heat_exchanger(inp)


# ---------------------------------------------------------------------------
# 8 — Missing two-phase DP property scalar fails clearly
# ---------------------------------------------------------------------------


class TestMissingTwoPhaseScalar:
    """Item 8: missing property scalar for two-phase DP raises a clear error."""

    def _base_inp_missing(self, missing_key: str) -> EvaporatorHXInput:
        gs = dict(_SHAH_GEOM_SCALARS)
        del gs[missing_key]
        return EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=gs,
            htc_primary=ShahBoilingHTC(),
            dp_primary=MSHTwoPhaseFrictionGradient(),
            primary_T_in=280.0,
            q_flux_primary=5000.0,
            dp_primary_is_two_phase=True,
        )

    def test_missing_rho_l_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_l"):
            _evap().evaluate_heat_exchanger(self._base_inp_missing("rho_l"))

    def test_missing_rho_v_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_v"):
            _evap().evaluate_heat_exchanger(self._base_inp_missing("rho_v"))

    def test_missing_mu_l_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_l"):
            _evap().evaluate_heat_exchanger(self._base_inp_missing("mu_l"))

    def test_missing_mu_v_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_v"):
            _evap().evaluate_heat_exchanger(self._base_inp_missing("mu_v"))

    def test_missing_l_cell_raises(self) -> None:
        with pytest.raises(ValueError, match="L_cell"):
            _evap().evaluate_heat_exchanger(self._base_inp_missing("L_cell"))


# ---------------------------------------------------------------------------
# 9–10 — Condenser can use YanCondensationHTC and two-phase DP
# ---------------------------------------------------------------------------


class TestCondenserYanCondensation:
    """Items 9, 10: YanCondensationHTC and two-phase DP injectable through Condenser."""

    def test_yan_htc_runs_without_error(self) -> None:
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            primary_T_in=320.0,
        )
        result = _cond().evaluate_heat_exchanger(inp)
        assert isinstance(result, HXSolveResult)

    def test_yan_htc_energy_balance(self) -> None:
        mdot = 0.05
        T_wall, T_in = 300.0, 320.0
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
            secondary_bc=FixedWallTemp(T_wall=T_wall),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            primary_T_in=T_in,
        )
        result = _cond().evaluate_heat_exchanger(inp)
        # Q < 0 (T_wall < T_primary) — condenser sense
        assert result.Q < 0.0
        expected_h = _STATE_IN.h + result.Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)

    def test_yan_does_not_need_q_flux_primary(self) -> None:
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            primary_T_in=320.0,
            # q_flux_primary=None (default) — Yan must not need it
        )
        result = _cond().evaluate_heat_exchanger(inp)
        assert isinstance(result, HXSolveResult)

    def test_yan_with_two_phase_dp(self) -> None:
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            dp_primary=MSHTwoPhaseFrictionGradient(),
            primary_T_in=320.0,
            dp_primary_is_two_phase=True,
        )
        result = _cond().evaluate_heat_exchanger(inp)
        assert isinstance(result, HXSolveResult)
        assert result.dP_primary >= 0.0

    def test_condenser_two_phase_dp_produces_verdict(self) -> None:
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            dp_primary=MSHTwoPhaseFrictionGradient(),
            primary_T_in=320.0,
            dp_primary_is_two_phase=True,
        )
        result = _cond().evaluate_heat_exchanger(inp)
        # HTC verdict + DP verdict
        assert len(result.verdicts) == 2

    def test_condenser_missing_two_phase_dp_scalar_fails_clearly(self) -> None:
        geom_scalars = dict(_YAN_GEOM_SCALARS)
        del geom_scalars["mu_v"]
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=geom_scalars,
            htc_primary=YanCondensationHTC(),
            dp_primary=MSHTwoPhaseFrictionGradient(),
            primary_T_in=320.0,
            dp_primary_is_two_phase=True,
        )
        with pytest.raises(ValueError, match="mu_v"):
            _cond().evaluate_heat_exchanger(inp)


# ---------------------------------------------------------------------------
# 11 — No CorrelationRegistry in components
# ---------------------------------------------------------------------------


def _import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        return [ln.strip() for ln in f if ln.strip().startswith(("import ", "from "))]


class TestNoCorrelationRegistry:
    """Item 11: component modules do not import or reference CorrelationRegistry."""

    def test_evaporator_does_not_import_correlation_registry(self) -> None:
        import mpl_sim.components.evaporator as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "CorrelationRegistry" not in ln

    def test_condenser_does_not_import_correlation_registry(self) -> None:
        import mpl_sim.components.condenser as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "CorrelationRegistry" not in ln


# ---------------------------------------------------------------------------
# 12 — No CoolProp / PropertyBackend in components
# ---------------------------------------------------------------------------


class TestNoCoolPropPropertyBackend:
    """Item 12: component modules do not import CoolProp or PropertyBackend."""

    def test_evaporator_does_not_import_coolprop(self) -> None:
        import mpl_sim.components.evaporator as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "coolprop" not in ln.lower()

    def test_evaporator_does_not_import_property_backend(self) -> None:
        import mpl_sim.components.evaporator as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "properties" not in ln

    def test_condenser_does_not_import_coolprop(self) -> None:
        import mpl_sim.components.condenser as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "coolprop" not in ln.lower()

    def test_condenser_does_not_import_property_backend(self) -> None:
        import mpl_sim.components.condenser as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "properties" not in ln


# ---------------------------------------------------------------------------
# 13 — No hidden defaults — no automatic closure selection
# ---------------------------------------------------------------------------


class TestNoHiddenDefaults:
    """Items 11, 12, 13: components make no autonomous closure decisions."""

    def test_evaporator_with_no_closures_runs(self) -> None:
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        result = _evap().evaluate_heat_exchanger(inp)
        assert isinstance(result, HXSolveResult)

    def test_condenser_with_no_closures_runs(self) -> None:
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        result = _cond().evaluate_heat_exchanger(inp)
        assert isinstance(result, HXSolveResult)

    def test_dp_primary_is_two_phase_default_is_false(self) -> None:
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert inp.dp_primary_is_two_phase is False

    def test_q_flux_primary_default_is_none(self) -> None:
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert inp.q_flux_primary is None

    def test_condenser_dp_primary_is_two_phase_default_is_false(self) -> None:
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert inp.dp_primary_is_two_phase is False

    def test_condenser_q_flux_primary_default_is_none(self) -> None:
        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert inp.q_flux_primary is None

    def test_component_does_not_choose_shah_automatically(self) -> None:
        rec = _RecordingModel()
        _evap().evaluate_heat_exchanger(_rec_evap_inp(rec))
        assert rec.last_req is not None
        assert rec.last_req.htc_primary is None

    def test_component_does_not_choose_yan_automatically(self) -> None:
        rec = _RecordingModel()
        _cond().evaluate_heat_exchanger(_rec_cond_inp(rec))
        assert rec.last_req is not None
        assert rec.last_req.htc_primary is None

    def test_component_does_not_choose_msh_automatically(self) -> None:
        rec = _RecordingModel()
        _evap().evaluate_heat_exchanger(_rec_evap_inp(rec))
        assert rec.last_req is not None
        assert rec.last_req.dp_primary is None

    def test_two_phase_dp_mode_requires_explicit_flag(self) -> None:
        rec = _RecordingModel()
        _evap().evaluate_heat_exchanger(
            _rec_evap_inp(rec, dp_primary=MSHTwoPhaseFrictionGradient())
        )
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is False
