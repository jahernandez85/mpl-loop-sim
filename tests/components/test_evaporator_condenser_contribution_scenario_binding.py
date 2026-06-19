"""Phase 11R: Evaporator/Condenser contribution-path scenario binding tests.

Verifies that the Phase 11Q scenario fields (q_flux_primary,
dp_primary_is_two_phase) are accessible and functional through the scenario-bound
helper evaluate_scenario(), not only through direct evaluate_heat_exchanger()
calls.

NOTE: evaluate_scenario() is NOT the frozen contribute(trial, ctx) ->
ComponentContribution contract from INTERFACE_SPEC §11.1.  That contract
remains deferred.  Phase 11R adds:
  - Immutable EvaporatorScenarioBinding / CondenserScenarioBinding value objects
    (geom_scalars stored as MappingProxyType).
  - EvaporatorComponent.evaluate_scenario / CondenserComponent.evaluate_scenario :
    thin adapters that build *HXInput from runtime state + immutable scenario
    and delegate to evaluate_heat_exchanger().

Required coverage (13 items):

  1.  Existing main evaluation path behavior remains unchanged by default.
  2.  Evaporator evaluate_scenario can carry q_flux_primary.
  3.  Evaporator evaluate_scenario can carry dp_primary_is_two_phase=True.
  4.  Evaporator evaluate_scenario reaches the same HX result semantics as
      direct evaluate_heat_exchanger().
  5.  Condenser evaluate_scenario can carry dp_primary_is_two_phase=True.
  6.  Condenser evaluate_scenario reaches the same HX result semantics as
      direct evaluate_heat_exchanger().
  7.  Missing q-flux for explicit Shah scenario through evaluate_scenario fails
      clearly.
  8.  Missing two-phase DP scalar through evaluate_scenario fails clearly.
  9.  No component-side registry resolution.
  10. No component-side property lookup.
  11. No automatic closure selection.
  12. No hidden scalar defaults.
  13. Existing Phase 11Q tests pass unchanged (run by pytest automatically).

Additional immutability coverage (Finding 2):
  - Direct field assignment on frozen binding raises FrozenInstanceError.
  - Mutation through binding.geom_scalars[...] raises TypeError.
  - Mutating the original dict after binding construction has no effect.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId
from mpl_sim.components.condenser import (
    CondenserComponent,
    CondenserHXInput,
    CondenserScenarioBinding,
)
from mpl_sim.components.evaporator import (
    EvaporatorComponent,
    EvaporatorHXInput,
    EvaporatorScenarioBinding,
)
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


def _rec_evap_scenario(rec: _RecordingModel, **kwargs) -> EvaporatorScenarioBinding:  # type: ignore[no-untyped-def]
    return EvaporatorScenarioBinding(
        secondary_bc=FixedHeatRate(Q=500.0),
        model=rec,
        discretization=_DISC,
        **kwargs,
    )


def _rec_cond_scenario(rec: _RecordingModel, **kwargs) -> CondenserScenarioBinding:  # type: ignore[no-untyped-def]
    return CondenserScenarioBinding(
        secondary_bc=FixedHeatRate(Q=-500.0),
        model=rec,
        discretization=_DISC,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Common two-phase geom_scalars (matches Phase 11Q scenario plumbing test values)
# ---------------------------------------------------------------------------

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
# Immutability tests (Finding 2 correction)
# ---------------------------------------------------------------------------


class TestScenarioBindingImmutability:
    """Scenario bindings must be deeply immutable.

    geom_scalars is stored as MappingProxyType; the frozen dataclass prevents
    field reassignment.
    """

    def test_evaporator_binding_is_frozen(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        with pytest.raises((AttributeError, TypeError)):
            scenario.q_flux_primary = 1000.0  # type: ignore[misc]

    def test_condenser_binding_is_frozen(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        with pytest.raises((AttributeError, TypeError)):
            scenario.q_flux_primary = 1000.0  # type: ignore[misc]

    def test_evaporator_geom_scalars_is_read_only(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars={"G": 300.0},
        )
        with pytest.raises(TypeError):
            scenario.geom_scalars["G"] = 999.0  # type: ignore[index]

    def test_condenser_geom_scalars_is_read_only(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars={"G": 250.0},
        )
        with pytest.raises(TypeError):
            scenario.geom_scalars["G"] = 999.0  # type: ignore[index]

    def test_evaporator_original_dict_mutation_does_not_affect_binding(self) -> None:
        original = {"G": 300.0, "x": 0.3}
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=original,
        )
        original["G"] = 999.0
        original["new_key"] = 42.0
        assert scenario.geom_scalars["G"] == pytest.approx(300.0)
        assert "new_key" not in scenario.geom_scalars

    def test_condenser_original_dict_mutation_does_not_affect_binding(self) -> None:
        original = {"G": 250.0, "x": 0.4}
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=original,
        )
        original["G"] = 888.0
        original["extra"] = 55.0
        assert scenario.geom_scalars["G"] == pytest.approx(250.0)
        assert "extra" not in scenario.geom_scalars

    def test_evaporator_geom_scalars_new_key_raises(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars={"G": 300.0},
        )
        with pytest.raises(TypeError):
            scenario.geom_scalars["new"] = 1.0  # type: ignore[index]

    def test_condenser_geom_scalars_new_key_raises(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars={"G": 250.0},
        )
        with pytest.raises(TypeError):
            scenario.geom_scalars["new"] = 1.0  # type: ignore[index]


# ---------------------------------------------------------------------------
# 1 — Default behavior of evaluate_scenario() is unchanged
# ---------------------------------------------------------------------------


class TestEvaluateScenarioDefaultBehavior:
    """Item 1: evaluate_scenario() uses the same defaults as evaluate_heat_exchanger()."""

    def test_evaporator_evaluate_scenario_q_flux_primary_default_none(self) -> None:
        rec = _RecordingModel()
        _evap().evaluate_scenario(_STATE_IN, 0.05, _rec_evap_scenario(rec))
        assert rec.last_req is not None
        assert rec.last_req.q_flux_primary is None

    def test_evaporator_evaluate_scenario_dp_primary_is_two_phase_default_false(
        self,
    ) -> None:
        rec = _RecordingModel()
        _evap().evaluate_scenario(_STATE_IN, 0.05, _rec_evap_scenario(rec))
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is False

    def test_condenser_evaluate_scenario_q_flux_primary_default_none(self) -> None:
        rec = _RecordingModel()
        _cond().evaluate_scenario(_STATE_IN, 0.05, _rec_cond_scenario(rec))
        assert rec.last_req is not None
        assert rec.last_req.q_flux_primary is None

    def test_condenser_evaluate_scenario_dp_primary_is_two_phase_default_false(
        self,
    ) -> None:
        rec = _RecordingModel()
        _cond().evaluate_scenario(_STATE_IN, 0.05, _rec_cond_scenario(rec))
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is False

    def test_evaporator_evaluate_scenario_energy_balance_unchanged(self) -> None:
        Q, mdot = 2000.0, 0.05
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=Q),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        result = _evap().evaluate_scenario(_STATE_IN, mdot, scenario)
        expected_h = _STATE_IN.h + Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)

    def test_condenser_evaluate_scenario_energy_balance_unchanged(self) -> None:
        Q, mdot = -3000.0, 0.05
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=Q),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        result = _cond().evaluate_scenario(_STATE_IN, mdot, scenario)
        expected_h = _STATE_IN.h + Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)

    def test_evaporator_scenario_binding_defaults(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert scenario.q_flux_primary is None
        assert scenario.dp_primary_is_two_phase is False
        assert scenario.htc_primary is None
        assert scenario.dp_primary is None

    def test_condenser_scenario_binding_defaults(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert scenario.q_flux_primary is None
        assert scenario.dp_primary_is_two_phase is False
        assert scenario.htc_primary is None
        assert scenario.dp_primary is None


# ---------------------------------------------------------------------------
# 2 — Evaporator evaluate_scenario can carry q_flux_primary
# ---------------------------------------------------------------------------


class TestEvaporatorEvaluateScenarioQFlux:
    """Item 2: q_flux_primary from EvaporatorScenarioBinding reaches HXSolveRequest."""

    def test_q_flux_primary_forwarded_to_request(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec, q_flux_primary=8000.0)
        _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert math.isclose(rec.last_req.q_flux_primary, 8000.0)

    def test_q_flux_primary_none_forwarded(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec, q_flux_primary=None)
        _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.q_flux_primary is None

    def test_q_flux_primary_value_preserved_exactly(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec, q_flux_primary=12345.678)
        _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.q_flux_primary == pytest.approx(12345.678)


# ---------------------------------------------------------------------------
# 3 — Evaporator evaluate_scenario can carry dp_primary_is_two_phase=True
# ---------------------------------------------------------------------------


class TestEvaporatorEvaluateScenarioTwoPhaseDP:
    """Item 3: dp_primary_is_two_phase from EvaporatorScenarioBinding reaches request."""

    def test_dp_primary_is_two_phase_true_forwarded(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec, dp_primary_is_two_phase=True)
        _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is True

    def test_dp_primary_is_two_phase_false_forwarded(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec, dp_primary_is_two_phase=False)
        _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is False

    def test_geom_scalars_forwarded_unchanged(self) -> None:
        rec = _RecordingModel()
        geom_scalars = {"G": 123.0, "x": 0.25, "custom": 9.5}
        scenario = _rec_evap_scenario(rec, geom_scalars=geom_scalars)
        _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.geom_scalars == geom_scalars


# ---------------------------------------------------------------------------
# 4 — Evaporator evaluate_scenario reaches same HX result semantics
# ---------------------------------------------------------------------------


class TestEvaporatorEvaluateScenarioSameSemantics:
    """Item 4: evaluate_scenario() and evaluate_heat_exchanger() produce identical results."""

    def test_shah_scenario_same_result_as_evaluate_heat_exchanger(self) -> None:
        mdot = 0.05
        shah_scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
            q_flux_primary=5000.0,
        )
        result_scenario = _evap().evaluate_scenario(_STATE_IN, mdot, shah_scenario)

        direct_inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
            q_flux_primary=5000.0,
        )
        result_direct = _evap().evaluate_heat_exchanger(direct_inp)

        assert math.isclose(result_scenario.Q, result_direct.Q, rel_tol=1e-12)
        assert math.isclose(
            result_scenario.primary_state_out.h,
            result_direct.primary_state_out.h,
            rel_tol=1e-12,
        )

    def test_shah_with_two_phase_dp_same_result(self) -> None:
        mdot = 0.05
        shah_scenario = EvaporatorScenarioBinding(
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
        result_scenario = _evap().evaluate_scenario(_STATE_IN, mdot, shah_scenario)

        direct_inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
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
        result_direct = _evap().evaluate_heat_exchanger(direct_inp)

        assert math.isclose(result_scenario.Q, result_direct.Q, rel_tol=1e-12)
        assert math.isclose(result_scenario.dP_primary, result_direct.dP_primary, rel_tol=1e-12)

    def test_evaluate_scenario_result_q_positive_for_evaporator(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
            q_flux_primary=5000.0,
        )
        result = _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert result.Q > 0.0

    def test_evaluate_scenario_result_has_verdicts(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
            q_flux_primary=5000.0,
        )
        result = _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert len(result.verdicts) >= 1

    def test_evaluate_scenario_enthalpy_balance_satisfied(self) -> None:
        mdot = 0.05
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
            q_flux_primary=5000.0,
        )
        result = _evap().evaluate_scenario(_STATE_IN, mdot, scenario)
        expected_h = _STATE_IN.h + result.Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# 5 — Condenser evaluate_scenario can carry dp_primary_is_two_phase=True
# ---------------------------------------------------------------------------


class TestCondenserEvaluateScenarioTwoPhaseDP:
    """Item 5: dp_primary_is_two_phase from CondenserScenarioBinding reaches request."""

    def test_dp_primary_is_two_phase_true_forwarded(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_cond_scenario(rec, dp_primary_is_two_phase=True)
        _cond().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is True

    def test_dp_primary_is_two_phase_false_forwarded(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_cond_scenario(rec, dp_primary_is_two_phase=False)
        _cond().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is False

    def test_geom_scalars_forwarded_unchanged(self) -> None:
        rec = _RecordingModel()
        geom_scalars = {"G": 234.0, "x": 0.75, "custom": 4.5}
        scenario = _rec_cond_scenario(rec, geom_scalars=geom_scalars)
        _cond().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.geom_scalars == geom_scalars

    def test_yan_two_phase_dp_through_evaluate_scenario_runs(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            dp_primary=MSHTwoPhaseFrictionGradient(),
            primary_T_in=320.0,
            dp_primary_is_two_phase=True,
        )
        result = _cond().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert isinstance(result, HXSolveResult)
        assert result.dP_primary >= 0.0


# ---------------------------------------------------------------------------
# 6 — Condenser evaluate_scenario reaches same HX result semantics
# ---------------------------------------------------------------------------


class TestCondenserEvaluateScenarioSameSemantics:
    """Item 6: evaluate_scenario() and evaluate_heat_exchanger() produce identical results."""

    def test_yan_scenario_same_result_as_evaluate_heat_exchanger(self) -> None:
        mdot = 0.05
        yan_scenario = CondenserScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            primary_T_in=320.0,
        )
        result_scenario = _cond().evaluate_scenario(_STATE_IN, mdot, yan_scenario)

        direct_inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            primary_T_in=320.0,
        )
        result_direct = _cond().evaluate_heat_exchanger(direct_inp)

        assert math.isclose(result_scenario.Q, result_direct.Q, rel_tol=1e-12)
        assert math.isclose(
            result_scenario.primary_state_out.h,
            result_direct.primary_state_out.h,
            rel_tol=1e-12,
        )

    def test_yan_with_two_phase_dp_same_result(self) -> None:
        mdot = 0.05
        yan_scenario = CondenserScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            dp_primary=MSHTwoPhaseFrictionGradient(),
            primary_T_in=320.0,
            dp_primary_is_two_phase=True,
        )
        result_scenario = _cond().evaluate_scenario(_STATE_IN, mdot, yan_scenario)

        direct_inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            dp_primary=MSHTwoPhaseFrictionGradient(),
            primary_T_in=320.0,
            dp_primary_is_two_phase=True,
        )
        result_direct = _cond().evaluate_heat_exchanger(direct_inp)

        assert math.isclose(result_scenario.Q, result_direct.Q, rel_tol=1e-12)
        assert math.isclose(result_scenario.dP_primary, result_direct.dP_primary, rel_tol=1e-12)

    def test_evaluate_scenario_result_q_negative_for_condenser(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            primary_T_in=320.0,
        )
        result = _cond().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert result.Q < 0.0

    def test_condenser_evaluate_scenario_enthalpy_balance_satisfied(self) -> None:
        mdot = 0.05
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            primary_T_in=320.0,
        )
        result = _cond().evaluate_scenario(_STATE_IN, mdot, scenario)
        expected_h = _STATE_IN.h + result.Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)

    def test_yan_does_not_require_q_flux_primary_through_evaluate_scenario(
        self,
    ) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_YAN_GEOM_SCALARS,
            htc_primary=YanCondensationHTC(),
            primary_T_in=320.0,
            # q_flux_primary intentionally absent — Yan must not need it
        )
        result = _cond().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert isinstance(result, HXSolveResult)


# ---------------------------------------------------------------------------
# 7 — Missing q-flux for Shah scenario through evaluate_scenario fails clearly
# ---------------------------------------------------------------------------


class TestMissingQFluxThroughEvaluateScenario:
    """Item 7: missing q_flux_primary for Shah raises through evaluate_scenario()."""

    def test_shah_without_q_flux_raises_via_evaluate_scenario(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
            # q_flux_primary intentionally absent — default is None
        )
        with pytest.raises(ValueError):
            _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)

    def test_shah_without_q_flux_error_mentions_q_flux_via_evaluate_scenario(
        self,
    ) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=290.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars=_SHAH_GEOM_SCALARS,
            htc_primary=ShahBoilingHTC(),
            primary_T_in=280.0,
        )
        with pytest.raises(ValueError, match="q_flux"):
            _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)

    def test_zero_q_flux_rejected_via_evaluate_scenario(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec, q_flux_primary=0.0)
        with pytest.raises(ValueError):
            _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)

    def test_negative_q_flux_rejected_via_evaluate_scenario(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec, q_flux_primary=-500.0)
        with pytest.raises(ValueError):
            _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)


# ---------------------------------------------------------------------------
# 8 — Missing two-phase DP scalar through evaluate_scenario fails clearly
# ---------------------------------------------------------------------------


class TestMissingTwoPhaseScalarThroughEvaluateScenario:
    """Item 8: missing property scalar for two-phase DP raises through evaluate_scenario()."""

    def _base_scenario_missing(self, missing_key: str) -> EvaporatorScenarioBinding:
        gs = dict(_SHAH_GEOM_SCALARS)
        del gs[missing_key]
        return EvaporatorScenarioBinding(
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

    def test_missing_rho_l_raises_via_evaluate_scenario(self) -> None:
        with pytest.raises(ValueError, match="rho_l"):
            _evap().evaluate_scenario(_STATE_IN, 0.05, self._base_scenario_missing("rho_l"))

    def test_missing_rho_v_raises_via_evaluate_scenario(self) -> None:
        with pytest.raises(ValueError, match="rho_v"):
            _evap().evaluate_scenario(_STATE_IN, 0.05, self._base_scenario_missing("rho_v"))

    def test_missing_mu_l_raises_via_evaluate_scenario(self) -> None:
        with pytest.raises(ValueError, match="mu_l"):
            _evap().evaluate_scenario(_STATE_IN, 0.05, self._base_scenario_missing("mu_l"))

    def test_missing_mu_v_raises_via_evaluate_scenario(self) -> None:
        with pytest.raises(ValueError, match="mu_v"):
            _evap().evaluate_scenario(_STATE_IN, 0.05, self._base_scenario_missing("mu_v"))

    def test_missing_l_cell_raises_via_evaluate_scenario(self) -> None:
        with pytest.raises(ValueError, match="L_cell"):
            _evap().evaluate_scenario(_STATE_IN, 0.05, self._base_scenario_missing("L_cell"))

    def test_condenser_missing_mu_v_raises_via_evaluate_scenario(self) -> None:
        geom_scalars = dict(_YAN_GEOM_SCALARS)
        del geom_scalars["mu_v"]
        scenario = CondenserScenarioBinding(
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
            _cond().evaluate_scenario(_STATE_IN, 0.05, scenario)


# ---------------------------------------------------------------------------
# 9 — No CorrelationRegistry in components
# ---------------------------------------------------------------------------


def _import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        return [ln.strip() for ln in f if ln.strip().startswith(("import ", "from "))]


class TestNoCorrelationRegistryViaEvaluateScenario:
    """Item 9: component modules do not import or reference CorrelationRegistry."""

    def test_evaporator_module_no_correlation_registry(self) -> None:
        import mpl_sim.components.evaporator as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "CorrelationRegistry" not in ln

    def test_condenser_module_no_correlation_registry(self) -> None:
        import mpl_sim.components.condenser as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "CorrelationRegistry" not in ln

    def test_evaluate_scenario_calls_no_registry_at_runtime(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec)
        _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.call_count == 1


# ---------------------------------------------------------------------------
# 10 — No property lookup in components
# ---------------------------------------------------------------------------


class TestNoPropertyLookupViaEvaluateScenario:
    """Item 10: component modules do not import CoolProp or PropertyBackend."""

    def test_evaporator_no_coolprop(self) -> None:
        import mpl_sim.components.evaporator as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "coolprop" not in ln.lower()

    def test_evaporator_no_property_backend(self) -> None:
        import mpl_sim.components.evaporator as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "properties" not in ln

    def test_condenser_no_coolprop(self) -> None:
        import mpl_sim.components.condenser as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "coolprop" not in ln.lower()

    def test_condenser_no_property_backend(self) -> None:
        import mpl_sim.components.condenser as m

        assert m.__file__ is not None
        lines = _import_lines(m.__file__)
        for ln in lines:
            assert "properties" not in ln


# ---------------------------------------------------------------------------
# 11 — No automatic closure selection
# ---------------------------------------------------------------------------


class TestNoAutomaticClosureSelection:
    """Item 11: components make no autonomous closure decisions via evaluate_scenario()."""

    def test_evaporator_evaluate_scenario_no_closures_runs(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        result = _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert isinstance(result, HXSolveResult)

    def test_condenser_evaluate_scenario_no_closures_runs(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        result = _cond().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert isinstance(result, HXSolveResult)

    def test_evaporator_evaluate_scenario_does_not_choose_shah(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec)
        _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.htc_primary is None

    def test_condenser_evaluate_scenario_does_not_choose_yan(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_cond_scenario(rec)
        _cond().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.htc_primary is None

    def test_evaporator_evaluate_scenario_does_not_choose_msh(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec)
        _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary is None

    def test_two_phase_dp_requires_explicit_flag_via_evaluate_scenario(self) -> None:
        rec = _RecordingModel()
        scenario = _rec_evap_scenario(rec, dp_primary=MSHTwoPhaseFrictionGradient())
        _evap().evaluate_scenario(_STATE_IN, 0.05, scenario)
        assert rec.last_req is not None
        assert rec.last_req.dp_primary_is_two_phase is False


# ---------------------------------------------------------------------------
# 12 — No hidden scalar defaults
# ---------------------------------------------------------------------------


class TestNoHiddenScalarDefaults:
    """Item 12: scenario binding has no hidden defaults for scalars or closures."""

    def test_evaporator_scenario_binding_q_flux_default_none(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert scenario.q_flux_primary is None

    def test_evaporator_scenario_binding_dp_two_phase_default_false(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert scenario.dp_primary_is_two_phase is False

    def test_condenser_scenario_binding_q_flux_default_none(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert scenario.q_flux_primary is None

    def test_condenser_scenario_binding_dp_two_phase_default_false(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert scenario.dp_primary_is_two_phase is False

    def test_evaporator_scenario_binding_htc_multiplier_default(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert scenario.htc_multiplier == 1.0

    def test_evaporator_scenario_binding_friction_multiplier_default(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert scenario.friction_multiplier == 1.0

    def test_condenser_scenario_binding_htc_multiplier_default(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert scenario.htc_multiplier == 1.0

    def test_condenser_scenario_binding_friction_multiplier_default(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert scenario.friction_multiplier == 1.0

    def test_evaporator_scenario_binding_geom_scalars_default_empty(self) -> None:
        scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert len(scenario.geom_scalars) == 0

    def test_condenser_scenario_binding_geom_scalars_default_empty(self) -> None:
        scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        assert len(scenario.geom_scalars) == 0


# ---------------------------------------------------------------------------
# Package export verification
# ---------------------------------------------------------------------------


class TestPackageExports:
    """Verify EvaporatorScenarioBinding and CondenserScenarioBinding are exported."""

    def test_evaporator_scenario_binding_importable_from_components(self) -> None:
        from mpl_sim.components import EvaporatorScenarioBinding as ESB

        assert ESB is EvaporatorScenarioBinding

    def test_condenser_scenario_binding_importable_from_components(self) -> None:
        from mpl_sim.components import CondenserScenarioBinding as CSB

        assert CSB is CondenserScenarioBinding

    def test_evaporator_scenario_binding_in_all(self) -> None:
        import mpl_sim.components as pkg

        assert "EvaporatorScenarioBinding" in pkg.__all__

    def test_condenser_scenario_binding_in_all(self) -> None:
        import mpl_sim.components as pkg

        assert "CondenserScenarioBinding" in pkg.__all__


# ---------------------------------------------------------------------------
# Contract boundary: evaluate_scenario is not the frozen contribute(trial, ctx)
# ---------------------------------------------------------------------------


class TestEvaluateScenarioIsNotContributeContract:
    """Document that evaluate_scenario is a helper, not the INTERFACE_SPEC contract.

    INTERFACE_SPEC §11.1 requires: contribute(trial, ctx) -> ComponentContribution
    Phase 11R does NOT implement that frozen contract; it adds a simpler helper
    that takes explicit runtime scalars and an immutable scenario binding.
    """

    def test_evaporator_has_no_contribute_method(self) -> None:
        evap = _evap()
        assert not hasattr(evap, "contribute"), (
            "EvaporatorComponent.contribute() must not exist in Phase 11R "
            "because it would violate the frozen contribute(trial, ctx) contract. "
            "Use evaluate_scenario() instead."
        )

    def test_condenser_has_no_contribute_method(self) -> None:
        cond = _cond()
        assert not hasattr(cond, "contribute"), (
            "CondenserComponent.contribute() must not exist in Phase 11R "
            "because it would violate the frozen contribute(trial, ctx) contract. "
            "Use evaluate_scenario() instead."
        )

    def test_evaporator_has_evaluate_scenario_method(self) -> None:
        assert hasattr(_evap(), "evaluate_scenario")

    def test_condenser_has_evaluate_scenario_method(self) -> None:
        assert hasattr(_cond(), "evaluate_scenario")
