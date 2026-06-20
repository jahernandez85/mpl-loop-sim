"""Phase 12A: minimal loop assembly acceptance tests.

Verifies all 12 required coverage items:

 1. Minimal loop runs end-to-end.
 2. Evaporator outlet feeds condenser inlet.
 3. Heat signs are correct (Q_evap > 0, Q_cond < 0).
 4. Primary enthalpy changes are consistent with Q / mdot.
 5. Pressure drops accumulate exactly.
 6. Net loop imbalance is reported, not hidden.
 7. Explicit closures are required/injected.
 8. Missing required inputs fail clearly.
 9. No property lookup or registry resolution.
10. Public example imports work (smoke test).
11. Existing Phase 11 HX tests remain passing (suite-level gate).
12. The example can be executed as a smoke test.

Architecture constraints:
  - No CoolProp, no PropertyBackend, no Network, no Solver.
  - All correlations are local fakes with explicit deterministic outputs.
  - FluidState carries only (P, h, identity); no property derivation occurs.
  - evaluate_minimal_evaporator_condenser_loop is imported from examples package.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from examples.minimal_evaporator_condenser_loop import (
    MinimalLoopResult,
    evaluate_minimal_evaporator_condenser_loop,
)

from mpl_sim.components import (
    ComponentId,
    CondenserComponent,
    CondenserScenarioBinding,
    EvaporatorComponent,
    EvaporatorScenarioBinding,
)
from mpl_sim.core import FluidState, PureFluid
from mpl_sim.correlations import (
    AnyFluid,
    Bound,
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationInput,
    CorrelationOutput,
    CorrelationRole,
    EnvelopeRef,
    SinglePhaseDPInput,
    SourceRef,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.discretization import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry import (
    FinGeometry,
    MicrochannelGeometry,
    PlateGeometry,
    PortDimensions,
)
from mpl_sim.hx_models import EpsilonNTUModel, FixedHeatRate, HXSolveResult

# ---------------------------------------------------------------------------
# Module-level constants (deterministic; no hidden defaults)
# ---------------------------------------------------------------------------

_FLUID = PureFluid(name="TestFluid_NoCoolProp")
_MODEL = EpsilonNTUModel()
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

# Explicit inlet state.
_P0 = 800_000.0  # [Pa]
_H0 = 250_000.0  # [J/kg]
_MDOT = 0.05  # [kg/s]
_INLET = FluidState(P=_P0, h=_H0, identity=_FLUID)

# Prescribed heat rates — explicit, no inference.
_Q_EVAP = 1000.0  # [W]  Q > 0: primary gains heat
_Q_COND = -800.0  # [W]  Q < 0: primary rejects heat

# Expected enthalpy values (exact arithmetic for deterministic closures).
_H_AFTER_EVAP = _H0 + _Q_EVAP / _MDOT  # 270_000.0 J/kg
_H_AFTER_COND = _H_AFTER_EVAP + _Q_COND / _MDOT  # 254_000.0 J/kg
_NET_DH = _H_AFTER_COND - _H0  # 4_000.0 J/kg
_NET_Q = _Q_EVAP + _Q_COND  # 200.0 W

# ---------------------------------------------------------------------------
# Minimal validity-envelope helper (shared across fake correlations)
# ---------------------------------------------------------------------------

_MIN_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test-only"),
)


def _dp_output(value_pa: float) -> CorrelationOutput:
    """Build a constant fake single-phase DP output [Pa] with IN_ENVELOPE verdict."""
    return CorrelationOutput(
        value=(value_pa,),
        verdict=ValidityVerdict(
            status=ValidityStatus.IN_ENVELOPE,
            envelope=EnvelopeRef(correlation_name="fake_dp", correlation_version="0"),
            violated=(),
        ),
        metadata=ClosureMetadata(
            name="fake_dp",
            version="0",
            source=SourceRef(citation="test-only"),
        ),
    )


# ---------------------------------------------------------------------------
# Fake correlations (stateless, deterministic, no property lookup)
# ---------------------------------------------------------------------------


class _ConstDP(Correlation):
    """Constant single-phase DP correlation returning a fixed Pa value."""

    def __init__(self, dp_pa: float = 500.0) -> None:
        self._dp_pa = dp_pa

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MIN_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        assert isinstance(inp, SinglePhaseDPInput)
        return _dp_output(self._dp_pa)


class _RecordingCondenser:
    """Test-only wrapper that records the exact runtime inlet state."""

    def __init__(self, delegate: CondenserComponent) -> None:
        self._delegate = delegate
        self.primary_state_in: FluidState | None = None

    def evaluate_scenario(
        self,
        primary_state_in: FluidState,
        primary_mdot: float,
        scenario: CondenserScenarioBinding,
    ) -> HXSolveResult:
        self.primary_state_in = primary_state_in
        return self._delegate.evaluate_scenario(primary_state_in, primary_mdot, scenario)


# ---------------------------------------------------------------------------
# Shared geometry fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def evap_geom() -> MicrochannelGeometry:
    return MicrochannelGeometry(
        N_channels=10,
        D_h_channel=0.001,
        fin_geometry=FinGeometry(
            fin_pitch=500.0,
            fin_height=0.010,
            fin_thickness=0.0002,
        ),
        A_heated=0.05,
        wall_mass=0.10,
        wall_material="aluminium",
    )


@pytest.fixture(scope="module")
def cond_geom() -> PlateGeometry:
    return PlateGeometry(
        N_plates=10,
        chevron_angle=45.0,
        plate_spacing=0.002,
        port_dims=PortDimensions(diameter=0.015),
        A_per_plate=0.05,
    )


@pytest.fixture(scope="module")
def evap_component(evap_geom: MicrochannelGeometry) -> EvaporatorComponent:
    return EvaporatorComponent(
        component_id=ComponentId(name="evap"),
        geometry=evap_geom,
    )


@pytest.fixture(scope="module")
def cond_component(cond_geom: PlateGeometry) -> CondenserComponent:
    return CondenserComponent(
        component_id=ComponentId(name="cond"),
        geometry=cond_geom,
    )


@pytest.fixture(scope="module")
def evap_scenario_no_dp() -> EvaporatorScenarioBinding:
    """Evaporator with FixedHeatRate BC and no DP or HTC closures."""
    return EvaporatorScenarioBinding(
        secondary_bc=FixedHeatRate(Q=_Q_EVAP),
        model=_MODEL,
        discretization=_DISC,
    )


@pytest.fixture(scope="module")
def cond_scenario_no_dp() -> CondenserScenarioBinding:
    """Condenser with FixedHeatRate BC and no DP or HTC closures."""
    return CondenserScenarioBinding(
        secondary_bc=FixedHeatRate(Q=_Q_COND),
        model=_MODEL,
        discretization=_DISC,
    )


# ---------------------------------------------------------------------------
# Helper: run the loop with the no-DP scenarios
# ---------------------------------------------------------------------------


def _run_basic_loop(
    evap_component: EvaporatorComponent,
    evap_scenario: EvaporatorScenarioBinding,
    cond_component: CondenserComponent,
    cond_scenario: CondenserScenarioBinding,
) -> MinimalLoopResult:
    return evaluate_minimal_evaporator_condenser_loop(
        inlet_state=_INLET,
        primary_mdot=_MDOT,
        evap_component=evap_component,
        evap_scenario=evap_scenario,
        cond_component=cond_component,
        cond_scenario=cond_scenario,
    )


# ===========================================================================
# Requirement 1: Minimal loop runs end-to-end.
# ===========================================================================


class TestMinimalLoopEndToEnd:
    def test_returns_minimal_loop_result(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert isinstance(result, MinimalLoopResult)

    def test_result_carries_both_hx_results(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.evap_result is not None
        assert result.cond_result is not None


# ===========================================================================
# Requirement 2: Evaporator outlet feeds condenser inlet.
# ===========================================================================


class TestEvaporatorOutletFeedsCondenserInlet:
    def test_cond_inlet_equals_evap_outlet(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        recording_condenser = _RecordingCondenser(cond_component)
        result = evaluate_minimal_evaporator_condenser_loop(
            inlet_state=_INLET,
            primary_mdot=_MDOT,
            evap_component=evap_component,
            evap_scenario=evap_scenario_no_dp,
            cond_component=recording_condenser,  # type: ignore[arg-type]
            cond_scenario=cond_scenario_no_dp,
        )
        evap_outlet = result.evap_result.primary_state_out
        assert recording_condenser.primary_state_in is evap_outlet

    def test_enthalpy_chain_is_sequential(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        # Chain: h_initial → h_after_evap → h_after_cond.
        assert result.h_initial == pytest.approx(_H0)
        assert result.h_after_evap == pytest.approx(_H_AFTER_EVAP)
        assert result.h_after_cond == pytest.approx(_H_AFTER_COND)


# ===========================================================================
# Requirement 3: Heat signs are correct.
# ===========================================================================


class TestHeatSigns:
    def test_q_evap_is_positive(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.Q_evap > 0, f"Q_evap must be > 0 for evaporator; got {result.Q_evap}"

    def test_q_cond_is_negative(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.Q_cond < 0, f"Q_cond must be < 0 for condenser; got {result.Q_cond}"

    def test_h_after_evap_greater_than_h_initial(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.h_after_evap > result.h_initial

    def test_h_after_cond_less_than_h_after_evap(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.h_after_cond < result.h_after_evap


# ===========================================================================
# Requirement 4: Primary enthalpy changes are consistent with Q / mdot.
# ===========================================================================


class TestEnthalpyConsistency:
    def test_evap_enthalpy_rise_equals_q_over_mdot(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        expected_dh_evap = _Q_EVAP / _MDOT  # 20_000 J/kg
        actual_dh_evap = result.h_after_evap - result.h_initial
        assert actual_dh_evap == pytest.approx(expected_dh_evap)

    def test_cond_enthalpy_drop_equals_q_over_mdot(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        expected_dh_cond = _Q_COND / _MDOT  # -16_000 J/kg
        actual_dh_cond = result.h_after_cond - result.h_after_evap
        assert actual_dh_cond == pytest.approx(expected_dh_cond)

    def test_exact_enthalpy_values(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.h_initial == pytest.approx(_H0)
        assert result.h_after_evap == pytest.approx(_H_AFTER_EVAP)
        assert result.h_after_cond == pytest.approx(_H_AFTER_COND)


# ===========================================================================
# Requirement 5: Pressure drops accumulate exactly.
# ===========================================================================


class TestPressureDropAccumulation:
    def test_no_dp_when_no_closure_injected(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.dP_evap == pytest.approx(0.0)
        assert result.dP_cond == pytest.approx(0.0)
        assert result.dP_total == pytest.approx(0.0)

    def test_dp_accumulates_when_closure_injected(
        self,
        evap_component: EvaporatorComponent,
        cond_component: CondenserComponent,
    ) -> None:
        dp_evap_pa = 300.0
        dp_cond_pa = 200.0

        evap_scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_EVAP),
            model=_MODEL,
            discretization=_DISC,
            dp_primary=_ConstDP(dp_evap_pa),
            geom_scalars={"G": 100.0, "D_h": 0.001, "L_cell": 0.3, "rho": 1000.0, "mu": 0.001},
        )
        cond_scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_COND),
            model=_MODEL,
            discretization=_DISC,
            dp_primary=_ConstDP(dp_cond_pa),
            geom_scalars={"G": 100.0, "D_h": 0.001, "L_cell": 0.3, "rho": 1000.0, "mu": 0.001},
        )

        result = _run_basic_loop(evap_component, evap_scenario, cond_component, cond_scenario)

        assert result.dP_evap == pytest.approx(dp_evap_pa)
        assert result.dP_cond == pytest.approx(dp_cond_pa)
        assert result.dP_total == pytest.approx(dp_evap_pa + dp_cond_pa)

    def test_dp_total_is_exact_sum(
        self,
        evap_component: EvaporatorComponent,
        cond_component: CondenserComponent,
    ) -> None:
        dp_a = 123.456
        dp_b = 78.9
        evap_scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_EVAP),
            model=_MODEL,
            discretization=_DISC,
            dp_primary=_ConstDP(dp_a),
            geom_scalars={"G": 100.0, "D_h": 0.001, "L_cell": 0.3, "rho": 1000.0, "mu": 0.001},
        )
        cond_scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_COND),
            model=_MODEL,
            discretization=_DISC,
            dp_primary=_ConstDP(dp_b),
            geom_scalars={"G": 100.0, "D_h": 0.001, "L_cell": 0.3, "rho": 1000.0, "mu": 0.001},
        )
        result = _run_basic_loop(evap_component, evap_scenario, cond_component, cond_scenario)
        assert result.dP_total == pytest.approx(result.dP_evap + result.dP_cond)


# ===========================================================================
# Requirement 6: Net loop imbalance is reported, not hidden.
# ===========================================================================


class TestNetImbalanceReported:
    def test_net_q_is_nonzero_when_loop_not_closed(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.net_Q == pytest.approx(_NET_Q)
        assert result.net_Q != pytest.approx(0.0)

    def test_net_dh_is_nonzero_when_loop_not_closed(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.net_dh == pytest.approx(_NET_DH)
        assert result.net_dh != pytest.approx(0.0)

    def test_net_q_equals_sum_of_component_qs(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.net_Q == pytest.approx(result.Q_evap + result.Q_cond)

    def test_net_dh_equals_final_minus_initial_enthalpy(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.net_dh == pytest.approx(result.h_after_cond - result.h_initial)

    def test_balanced_scenario_reports_zero_imbalance(
        self,
        evap_component: EvaporatorComponent,
        cond_component: CondenserComponent,
    ) -> None:
        """When Q_evap + Q_cond = 0, net_Q and net_dh are zero."""
        evap_scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=500.0),
            model=_MODEL,
            discretization=_DISC,
        )
        cond_scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-500.0),
            model=_MODEL,
            discretization=_DISC,
        )
        result = _run_basic_loop(evap_component, evap_scenario, cond_component, cond_scenario)
        assert result.net_Q == pytest.approx(0.0)
        assert result.net_dh == pytest.approx(0.0)


# ===========================================================================
# Requirement 7: Explicit closures are required/injected.
# ===========================================================================


class TestExplicitClosureInjection:
    def test_loop_works_without_dp_closure(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        """FixedHeatRate does not require HTC or DP closures."""
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert isinstance(result, MinimalLoopResult)

    def test_dp_closure_is_used_when_injected(
        self,
        evap_component: EvaporatorComponent,
        cond_component: CondenserComponent,
    ) -> None:
        """When a DP closure is injected, its output appears in dP_primary."""
        explicit_dp = 750.0
        evap_scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_EVAP),
            model=_MODEL,
            discretization=_DISC,
            dp_primary=_ConstDP(explicit_dp),
            geom_scalars={"G": 100.0, "D_h": 0.001, "L_cell": 0.3, "rho": 1000.0, "mu": 0.001},
        )
        cond_scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_COND),
            model=_MODEL,
            discretization=_DISC,
        )
        result = _run_basic_loop(evap_component, evap_scenario, cond_component, cond_scenario)
        assert result.dP_evap == pytest.approx(explicit_dp)
        assert result.dP_cond == pytest.approx(0.0)

    def test_no_automatic_closure_selection(
        self,
        evap_component: EvaporatorComponent,
        cond_component: CondenserComponent,
    ) -> None:
        """Omitting dp_primary gives dP = 0, not a silently selected default."""
        scenario_no_dp = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_EVAP),
            model=_MODEL,
            discretization=_DISC,
        )
        cond_scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_COND),
            model=_MODEL,
            discretization=_DISC,
        )
        result = _run_basic_loop(evap_component, scenario_no_dp, cond_component, cond_scenario)
        # No closure injected → zero DP, not a hidden default value.
        assert result.dP_evap == pytest.approx(0.0)
        assert result.dP_cond == pytest.approx(0.0)


# ===========================================================================
# Requirement 8: Missing required inputs fail clearly.
# ===========================================================================


class TestMissingRequiredInputs:
    def test_zero_mdot_raises_value_error(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            evaluate_minimal_evaporator_condenser_loop(
                inlet_state=_INLET,
                primary_mdot=0.0,
                evap_component=evap_component,
                evap_scenario=evap_scenario_no_dp,
                cond_component=cond_component,
                cond_scenario=cond_scenario_no_dp,
            )

    def test_negative_mdot_raises_value_error(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            evaluate_minimal_evaporator_condenser_loop(
                inlet_state=_INLET,
                primary_mdot=-1.0,
                evap_component=evap_component,
                evap_scenario=evap_scenario_no_dp,
                cond_component=cond_component,
                cond_scenario=cond_scenario_no_dp,
            )

    def test_infinite_mdot_raises_value_error(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            evaluate_minimal_evaporator_condenser_loop(
                inlet_state=_INLET,
                primary_mdot=float("inf"),
                evap_component=evap_component,
                evap_scenario=evap_scenario_no_dp,
                cond_component=cond_component,
                cond_scenario=cond_scenario_no_dp,
            )

    def test_dp_closure_without_required_geom_scalars_fails_clearly(
        self,
        evap_component: EvaporatorComponent,
        cond_component: CondenserComponent,
    ) -> None:
        """Injecting a DP closure without the required geom_scalars raises ValueError."""
        evap_scenario = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_EVAP),
            model=_MODEL,
            discretization=_DISC,
            dp_primary=_ConstDP(500.0),
            # geom_scalars intentionally empty — "G", "D_h", etc. missing
        )
        cond_scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_COND),
            model=_MODEL,
            discretization=_DISC,
        )
        with pytest.raises(ValueError, match="geom_scalars"):
            evaluate_minimal_evaporator_condenser_loop(
                inlet_state=_INLET,
                primary_mdot=_MDOT,
                evap_component=evap_component,
                evap_scenario=evap_scenario,
                cond_component=cond_component,
                cond_scenario=cond_scenario,
            )


# ===========================================================================
# Requirement 9: No property lookup or registry resolution.
# ===========================================================================


class TestNoBoundaryViolations:
    def test_nonexistent_fluid_name_does_not_cause_property_lookup(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        """FluidState carries only (P, h, identity).  No CoolProp is called.

        If CoolProp were invoked, a nonexistent fluid name would raise an
        error.  The loop completes successfully, proving no property lookup.
        """
        nonexistent_fluid = PureFluid(name="FLUID_THAT_DOES_NOT_EXIST_IN_COOLPROP")
        inlet = FluidState(P=800_000.0, h=250_000.0, identity=nonexistent_fluid)
        result = evaluate_minimal_evaporator_condenser_loop(
            inlet_state=inlet,
            primary_mdot=_MDOT,
            evap_component=evap_component,
            evap_scenario=evap_scenario_no_dp,
            cond_component=cond_component,
            cond_scenario=cond_scenario_no_dp,
        )
        assert isinstance(result, MinimalLoopResult)

    def test_result_fluid_identity_preserved_unchanged(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        """FluidIdentity is threaded through unchanged — no backend resolution."""
        sentinel = PureFluid(name="SENTINEL_FLUID")
        inlet = FluidState(P=800_000.0, h=250_000.0, identity=sentinel)
        result = evaluate_minimal_evaporator_condenser_loop(
            inlet_state=inlet,
            primary_mdot=_MDOT,
            evap_component=evap_component,
            evap_scenario=evap_scenario_no_dp,
            cond_component=cond_component,
            cond_scenario=cond_scenario_no_dp,
        )
        assert result.evap_result.primary_state_out.identity == sentinel
        assert result.cond_result.primary_state_out.identity == sentinel


# ===========================================================================
# Requirements 10 & 12: Public example imports work; smoke test.
# ===========================================================================


class TestExampleSmokeTest:
    def test_example_script_runs_without_error(self) -> None:
        """Requirements 10 & 12: example imports mpl_sim.* and runs to completion."""
        example_path = Path(__file__).parent.parent.parent / "examples"
        example_path = example_path / "minimal_evaporator_condenser_loop.py"
        assert example_path.exists(), f"Example script not found: {example_path}"
        proc = subprocess.run(
            [sys.executable, str(example_path)],
            capture_output=True,
            timeout=60,
        )
        assert proc.returncode == 0, (
            f"Example script exited with code {proc.returncode}.\n"
            f"stdout: {proc.stdout.decode()}\n"
            f"stderr: {proc.stderr.decode()}"
        )

    def test_example_output_contains_net_q(self) -> None:
        """Example prints Net Q diagnostic — verifying the imbalance is surfaced."""
        example_path = (
            Path(__file__).parent.parent.parent
            / "examples"
            / "minimal_evaporator_condenser_loop.py"
        )
        proc = subprocess.run(
            [sys.executable, str(example_path)],
            capture_output=True,
            timeout=60,
        )
        assert proc.returncode == 0
        output = proc.stdout.decode(errors="replace")
        assert "Net Q" in output or "net_Q" in output.lower()


# ===========================================================================
# Additional: MinimalLoopResult is a frozen dataclass (immutable).
# ===========================================================================


class TestMinimalLoopResultImmutability:
    def test_result_is_frozen(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        with pytest.raises((AttributeError, TypeError)):
            result.Q_evap = 999.0  # type: ignore[misc]

    def test_warnings_is_a_tuple(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert isinstance(result.warnings, tuple)

    def test_warnings_empty_when_no_correlations_called(
        self,
        evap_component: EvaporatorComponent,
        evap_scenario_no_dp: EvaporatorScenarioBinding,
        cond_component: CondenserComponent,
        cond_scenario_no_dp: CondenserScenarioBinding,
    ) -> None:
        """FixedHeatRate with no HTC/DP produces no correlation verdicts."""
        result = _run_basic_loop(
            evap_component, evap_scenario_no_dp, cond_component, cond_scenario_no_dp
        )
        assert result.warnings == ()
