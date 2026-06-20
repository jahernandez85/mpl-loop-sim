"""Phase 13A: minimal closed MPL solver acceptance tests.

Verifies all 15 required coverage items:

 1.  Solver closes energy residual for a simple deterministic case.
 2.  Solved condenser heat rate equals expected value from energy balance.
 3.  Final enthalpy matches reference within tolerance.
 4.  converged=True, residual reported, iteration count reported.
 5.  Non-convergence (max_iter too small) and invalid bracket are explicit.
 6.  Invalid ClosedLoopSolveConfig is rejected (bool/float/zero max_iter;
     zero/nan/inf tolerance).
 7.  Evaporator outlet is passed to condenser as its inlet.
 8.  net_Q and net_dh are reported.
 9.  Pressure-drop accumulation is diagnostic (dP_total).
10.  No pressure closure is claimed.
11.  Missing/invalid required inputs fail clearly (primary_mdot, q_cond_bounds,
     BC type mismatch).
12.  No property lookup (nonexistent fluid name completes without error).
13.  No registry resolution.
14.  No full-network solve API introduced.
15.  Public API import tests for the new package.

Architecture constraints:
  - No CoolProp, no PropertyBackend, no network, no generic solver.
  - All correlations are replaced by the FixedHeatRate BC (no HTC/DP injection).
  - FluidState carries only (P, h, identity); no property derivation occurs.
  - Arithmetic is exact and deterministic for FixedHeatRate BC.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from mpl_sim.closed_loop import (
    ClosedLoopSolveConfig,
    MinimalClosedMPLCase,
    MinimalClosedMPLResult,
    solve_minimal_closed_mpl,
)
from mpl_sim.components import (
    ComponentId,
    CondenserComponent,
    CondenserScenarioBinding,
    EvaporatorComponent,
    EvaporatorScenarioBinding,
)
from mpl_sim.core import FluidState, PureFluid
from mpl_sim.discretization import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry import (
    FinGeometry,
    MicrochannelGeometry,
    PlateGeometry,
    PortDimensions,
)
from mpl_sim.hx_models import (
    EpsilonNTUModel,
    FixedHeatRate,
    FixedWallTemp,
    HXSolveRequest,
    HXSolveResult,
)

# ---------------------------------------------------------------------------
# Module-level constants (deterministic; no hidden defaults)
# ---------------------------------------------------------------------------

_FLUID = PureFluid(name="TestFluid_NoCoolProp")
_MODEL = EpsilonNTUModel()
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

# Reference / inlet state (no CoolProp call).
_P_REF = 800_000.0  # [Pa]
_H_REF = 250_000.0  # [J/kg]
_MDOT = 0.05  # [kg/s]
_REFERENCE_STATE = FluidState(P=_P_REF, h=_H_REF, identity=_FLUID)

# Prescribed evaporator heat rate [W].
_Q_EVAP = 1000.0

# Expected post-evaporator enthalpy.
_H_AFTER_EVAP = _H_REF + _Q_EVAP / _MDOT  # 270 000 J/kg

# Exact closed-loop solution (analytical): Q_cond = -Q_evap.
_Q_COND_EXACT = -_Q_EVAP  # -1000 W

# Bracket that encloses the root.
# r(q_lo=-5000) = (1000-5000)/0.05 = -80 000  (< 0)
# r(q_hi=  0  ) =  1000/0.05       = +20 000  (> 0)
_Q_COND_BOUNDS = (-5000.0, 0.0)

# Solver tolerance used in all convergence tests.
_TOLERANCE = 1.0  # [J/kg] — deliberately loose to keep tests fast


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _evap_component() -> EvaporatorComponent:
    geom = MicrochannelGeometry(
        N_channels=20,
        D_h_channel=0.001,
        fin_geometry=FinGeometry(fin_pitch=500.0, fin_height=0.010, fin_thickness=0.0002),
        A_heated=0.05,
        wall_mass=0.20,
        wall_material="aluminium",
    )
    return EvaporatorComponent(component_id=ComponentId(name="evap"), geometry=geom)


def _cond_component() -> CondenserComponent:
    geom = PlateGeometry(
        N_plates=10,
        chevron_angle=45.0,
        plate_spacing=0.002,
        port_dims=PortDimensions(diameter=0.015),
        A_per_plate=0.05,
    )
    return CondenserComponent(component_id=ComponentId(name="cond"), geometry=geom)


def _evap_scenario(
    q_evap: float = _Q_EVAP,
    model: EpsilonNTUModel = _MODEL,
) -> EvaporatorScenarioBinding:
    return EvaporatorScenarioBinding(
        secondary_bc=FixedHeatRate(Q=q_evap),
        model=model,
        discretization=_DISC,
    )


def _cond_scenario_template(
    q_cond_placeholder: float = 0.0,
    model: EpsilonNTUModel = _MODEL,
) -> CondenserScenarioBinding:
    return CondenserScenarioBinding(
        secondary_bc=FixedHeatRate(Q=q_cond_placeholder),
        model=model,
        discretization=_DISC,
    )


def _make_case(
    q_evap: float = _Q_EVAP,
    q_cond_bounds: tuple[float, float] = _Q_COND_BOUNDS,
    reference_state: FluidState = _REFERENCE_STATE,
    primary_mdot: float = _MDOT,
) -> MinimalClosedMPLCase:
    return MinimalClosedMPLCase(
        reference_state=reference_state,
        primary_mdot=primary_mdot,
        evap_component=_evap_component(),
        evap_scenario=_evap_scenario(q_evap),
        cond_component=_cond_component(),
        cond_scenario=_cond_scenario_template(),
        q_cond_bounds=q_cond_bounds,
    )


def _default_config() -> ClosedLoopSolveConfig:
    return ClosedLoopSolveConfig(max_iter=60, tolerance=_TOLERANCE)


# ---------------------------------------------------------------------------
# 1. Solver closes energy residual for a simple deterministic case
# ---------------------------------------------------------------------------


class TestSolverClosesEnergyResidual:
    def test_converged_flag_is_true(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert result.converged is True

    def test_energy_residual_within_tolerance(self) -> None:
        config = _default_config()
        result = solve_minimal_closed_mpl(_make_case(), config)
        assert abs(result.energy_residual) <= config.tolerance

    def test_residual_equals_energy_residual(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert result.residual == result.energy_residual

    def test_h_return_within_tolerance_of_h_reference(self) -> None:
        config = _default_config()
        result = solve_minimal_closed_mpl(_make_case(), config)
        assert abs(result.h_return - result.h_reference) <= config.tolerance

    def test_iteration_count_positive(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert result.iterations >= 1


# ---------------------------------------------------------------------------
# 2. Solved condenser heat rate equals expected value from energy balance
# ---------------------------------------------------------------------------


class TestSolvedQCondValue:
    def test_solved_q_cond_close_to_negative_q_evap(self) -> None:
        config = _default_config()
        result = solve_minimal_closed_mpl(_make_case(), config)
        # Exact solution: Q_cond = -Q_evap = -1000 W
        # With tolerance=1 J/kg and mdot=0.05 kg/s, Q error <= 0.05 W
        assert abs(result.solved_q_cond - _Q_COND_EXACT) < 5.0  # [W] generous

    def test_solved_q_cond_is_negative(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert result.solved_q_cond < 0.0

    def test_q_cond_consistent_with_h_return(self) -> None:
        config = _default_config()
        result = solve_minimal_closed_mpl(_make_case(), config)
        # h_return = h_after_evap + Q_cond/mdot
        h_reconstructed = result.h_after_evap + result.solved_q_cond / _MDOT
        assert abs(h_reconstructed - result.h_return) < 1e-9


# ---------------------------------------------------------------------------
# 3. Final enthalpy matches reference within tolerance
# ---------------------------------------------------------------------------


class TestFinalEnthalpyMatchesReference:
    def test_h_return_close_to_h_ref(self) -> None:
        config = _default_config()
        result = solve_minimal_closed_mpl(_make_case(), config)
        assert abs(result.h_return - _H_REF) <= config.tolerance

    def test_h_reference_equals_inlet_h(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert result.h_reference == _H_REF

    def test_h_after_evap_equals_expected(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert abs(result.h_after_evap - _H_AFTER_EVAP) < 1e-9


# ---------------------------------------------------------------------------
# 4. converged=True, residual, iteration count
# ---------------------------------------------------------------------------


class TestConvergenceReporting:
    def test_converged_is_bool(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert isinstance(result.converged, bool)

    def test_residual_is_finite(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert math.isfinite(result.residual)

    def test_iteration_count_is_nonneg_int(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert isinstance(result.iterations, int)
        assert result.iterations >= 0

    def test_default_config_none_uses_defaults(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), config=None)
        assert result.converged is True
        assert math.isfinite(result.residual)


# ---------------------------------------------------------------------------
# 5. Non-convergence and invalid bracket are explicit
# ---------------------------------------------------------------------------


class TestNonConvergenceAndBadBracket:
    def test_non_convergence_returns_converged_false(self) -> None:
        tiny_cfg = ClosedLoopSolveConfig(max_iter=1, tolerance=1e-20)
        result = solve_minimal_closed_mpl(_make_case(), tiny_cfg)
        assert result.converged is False

    def test_non_convergence_still_reports_residual(self) -> None:
        tiny_cfg = ClosedLoopSolveConfig(max_iter=1, tolerance=1e-20)
        result = solve_minimal_closed_mpl(_make_case(), tiny_cfg)
        assert math.isfinite(result.residual)
        assert result.iterations == 1

    def test_same_sign_bracket_raises(self) -> None:
        # r(lo=-500) = (1000-500)/0.05 = +10 000 > 0
        # r(hi= 0  ) = 1000/0.05       = +20 000 > 0  — same sign
        bad_bracket = (-500.0, 0.0)
        with pytest.raises(ValueError, match="does not enclose a root"):
            solve_minimal_closed_mpl(_make_case(q_cond_bounds=bad_bracket), _default_config())

    def test_same_sign_bracket_message_shows_residuals(self) -> None:
        bad_bracket = (-500.0, 0.0)
        with pytest.raises(ValueError) as exc:
            solve_minimal_closed_mpl(_make_case(q_cond_bounds=bad_bracket), _default_config())
        assert "r(lo)" in str(exc.value)
        assert "r(hi)" in str(exc.value)

    @pytest.mark.parametrize("bounds", [(-1000.0, 0.0), (-5000.0, -1000.0)])
    def test_root_at_bracket_endpoint_converges(self, bounds: tuple[float, float]) -> None:
        result = solve_minimal_closed_mpl(
            _make_case(q_cond_bounds=bounds),
            ClosedLoopSolveConfig(max_iter=1, tolerance=1e-12),
        )
        assert result.converged is True
        assert result.iterations == 0
        assert result.solved_q_cond == _Q_COND_EXACT
        assert result.energy_residual == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# 6. Invalid ClosedLoopSolveConfig rejected
# ---------------------------------------------------------------------------


class TestInvalidConfig:
    def test_max_iter_bool_true_raises(self) -> None:
        with pytest.raises(ValueError, match="max_iter"):
            ClosedLoopSolveConfig(max_iter=True)  # type: ignore[arg-type]

    def test_max_iter_bool_false_raises(self) -> None:
        with pytest.raises(ValueError, match="max_iter"):
            ClosedLoopSolveConfig(max_iter=False)  # type: ignore[arg-type]

    def test_max_iter_float_raises(self) -> None:
        with pytest.raises(ValueError, match="max_iter"):
            ClosedLoopSolveConfig(max_iter=1.5)  # type: ignore[arg-type]

    def test_max_iter_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="max_iter"):
            ClosedLoopSolveConfig(max_iter=0)

    def test_max_iter_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="max_iter"):
            ClosedLoopSolveConfig(max_iter=-1)

    def test_tolerance_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            ClosedLoopSolveConfig(tolerance=0.0)

    def test_tolerance_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            ClosedLoopSolveConfig(tolerance=float("nan"))

    def test_tolerance_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            ClosedLoopSolveConfig(tolerance=float("inf"))

    def test_tolerance_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            ClosedLoopSolveConfig(tolerance=-1e-6)

    def test_valid_config_constructs(self) -> None:
        cfg = ClosedLoopSolveConfig(max_iter=10, tolerance=0.01)
        assert cfg.max_iter == 10
        assert cfg.tolerance == 0.01


# ---------------------------------------------------------------------------
# 7. Evaporator outlet is passed to condenser as its inlet
# ---------------------------------------------------------------------------


class TestEvapOutletFeedsCondenser:
    def test_exact_evap_outlet_object_feeds_every_condenser_evaluation(self) -> None:
        class RecordingModel(EpsilonNTUModel):
            def __init__(self) -> None:
                self.requests: list[HXSolveRequest] = []

            def solve(self, req: HXSolveRequest) -> HXSolveResult:
                self.requests.append(req)
                return super().solve(req)

        evap_model = RecordingModel()
        cond_model = RecordingModel()
        case = MinimalClosedMPLCase(
            reference_state=_REFERENCE_STATE,
            primary_mdot=_MDOT,
            evap_component=_evap_component(),
            evap_scenario=_evap_scenario(model=evap_model),
            cond_component=_cond_component(),
            cond_scenario=_cond_scenario_template(model=cond_model),
            q_cond_bounds=_Q_COND_BOUNDS,
        )

        result = solve_minimal_closed_mpl(case, _default_config())

        assert len(evap_model.requests) == 1
        assert cond_model.requests
        assert all(
            request.primary_state_in is result.state_after_evap for request in cond_model.requests
        )

    def test_state_after_evap_is_cond_inlet(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        # Condenser inlet is evap outlet: primary_state_in of cond == state_after_evap
        assert result.state_after_evap.h == pytest.approx(result.h_after_evap, abs=1e-9)
        assert result.state_after_evap.P == _P_REF

    def test_h_after_evap_from_q_evap(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        expected = _H_REF + _Q_EVAP / _MDOT
        assert abs(result.h_after_evap - expected) < 1e-9

    def test_evap_result_primary_state_out_equals_state_after_evap(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert result.evap_result.primary_state_out.h == pytest.approx(
            result.state_after_evap.h, abs=1e-9
        )

    def test_different_q_evap_changes_h_after_evap(self) -> None:
        q_evap_alt = 2000.0
        case_alt = _make_case(q_evap=q_evap_alt, q_cond_bounds=(-8000.0, 0.0))
        result = solve_minimal_closed_mpl(case_alt, _default_config())
        expected_h = _H_REF + q_evap_alt / _MDOT
        assert abs(result.h_after_evap - expected_h) < 1e-9


# ---------------------------------------------------------------------------
# 8. net_Q and net_dh are reported
# ---------------------------------------------------------------------------


class TestNetQAndNetDH:
    def test_net_q_reported(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert math.isfinite(result.net_Q)

    def test_net_dh_reported(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert math.isfinite(result.net_dh)

    def test_net_dh_equals_h_return_minus_h_reference(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert result.net_dh == pytest.approx(result.h_return - result.h_reference, abs=1e-9)

    def test_net_q_equals_q_evap_plus_q_cond(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        expected = result.evap_result.Q + result.cond_result.Q
        assert result.net_Q == pytest.approx(expected, abs=1e-9)

    def test_converged_net_q_near_zero(self) -> None:
        config = _default_config()
        result = solve_minimal_closed_mpl(_make_case(), config)
        assert result.converged
        # net_Q = (Q_evap + Q_cond) and Q_cond ≈ -Q_evap when converged
        assert abs(result.net_Q) < _MDOT * config.tolerance + 1.0

    def test_converged_net_dh_within_tolerance(self) -> None:
        config = _default_config()
        result = solve_minimal_closed_mpl(_make_case(), config)
        assert result.converged
        assert abs(result.net_dh) <= config.tolerance


# ---------------------------------------------------------------------------
# 9. Pressure-drop accumulation is diagnostic
# ---------------------------------------------------------------------------


class TestPressureDropDiagnostic:
    def test_dp_total_is_finite(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert math.isfinite(result.dP_total)

    def test_dp_total_equals_sum(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        expected = result.evap_result.dP_primary + result.cond_result.dP_primary
        assert result.dP_total == pytest.approx(expected, abs=1e-9)

    def test_dp_total_zero_for_no_dp_correlations(self) -> None:
        # FixedHeatRate with no dp_primary injected → dP = 0 on both sides
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert result.dP_total == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 10. No pressure closure claimed
# ---------------------------------------------------------------------------


class TestNoPressureClosure:
    def test_result_has_no_pressure_residual_attribute(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert not hasattr(result, "pressure_residual")

    def test_result_has_no_dp_pump_attribute(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert not hasattr(result, "dP_pump")

    def test_result_exposes_dp_total_as_diagnostic_only(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        # dP_total exists but is 0 when no DP correlations are injected
        assert hasattr(result, "dP_total")
        assert math.isfinite(result.dP_total)


# ---------------------------------------------------------------------------
# 11. Missing/invalid required inputs fail clearly
# ---------------------------------------------------------------------------


class TestMissingInputsFail:
    def test_primary_mdot_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            _make_case(primary_mdot=0.0)

    def test_primary_mdot_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            _make_case(primary_mdot=-0.1)

    def test_primary_mdot_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            _make_case(primary_mdot=float("nan"))

    def test_primary_mdot_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            _make_case(primary_mdot=float("inf"))

    def test_q_cond_bounds_lo_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="q_cond_bounds"):
            _make_case(q_cond_bounds=(float("-inf"), 0.0))

    def test_q_cond_bounds_hi_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="q_cond_bounds"):
            _make_case(q_cond_bounds=(-5000.0, float("nan")))

    def test_q_cond_bounds_lo_ge_hi_raises(self) -> None:
        with pytest.raises(ValueError, match="q_cond_bounds"):
            _make_case(q_cond_bounds=(0.0, -5000.0))

    def test_q_cond_bounds_equal_raises(self) -> None:
        with pytest.raises(ValueError, match="q_cond_bounds"):
            _make_case(q_cond_bounds=(-500.0, -500.0))

    def test_non_fixed_heat_rate_bc_raises(self) -> None:
        cond_scenario_bad = CondenserScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=_MODEL,
            discretization=_DISC,
        )
        case = MinimalClosedMPLCase(
            reference_state=_REFERENCE_STATE,
            primary_mdot=_MDOT,
            evap_component=_evap_component(),
            evap_scenario=_evap_scenario(),
            cond_component=_cond_component(),
            cond_scenario=cond_scenario_bad,
            q_cond_bounds=_Q_COND_BOUNDS,
        )
        with pytest.raises(ValueError, match="FixedHeatRate"):
            solve_minimal_closed_mpl(case, _default_config())

    def test_non_fixed_heat_rate_error_names_type(self) -> None:
        cond_scenario_bad = CondenserScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=_MODEL,
            discretization=_DISC,
        )
        case = MinimalClosedMPLCase(
            reference_state=_REFERENCE_STATE,
            primary_mdot=_MDOT,
            evap_component=_evap_component(),
            evap_scenario=_evap_scenario(),
            cond_component=_cond_component(),
            cond_scenario=cond_scenario_bad,
            q_cond_bounds=_Q_COND_BOUNDS,
        )
        with pytest.raises(ValueError) as exc:
            solve_minimal_closed_mpl(case, _default_config())
        assert "FixedWallTemp" in str(exc.value)


# ---------------------------------------------------------------------------
# 12. No property lookup (nonexistent fluid name)
# ---------------------------------------------------------------------------


class TestNoPropertyLookup:
    def test_nonexistent_fluid_completes_without_error(self) -> None:
        fake_fluid = PureFluid(name="NoSuchFluid_XYZ_CoolPropWouldFail")
        fake_state = FluidState(P=_P_REF, h=_H_REF, identity=fake_fluid)
        case = _make_case(reference_state=fake_state)
        result = solve_minimal_closed_mpl(case, _default_config())
        assert result.converged is True

    def test_arbitrary_h_and_p_work(self) -> None:
        # No property lookup means arbitrary (P, h) pairs are valid
        exotic_state = FluidState(P=1.0, h=1e9, identity=_FLUID)
        case = _make_case(
            reference_state=exotic_state,
            q_cond_bounds=(-5000.0, 0.0),
        )
        result = solve_minimal_closed_mpl(case, _default_config())
        assert result.converged is True
        assert result.reference_state.P == 1.0
        assert result.reference_state.h == 1e9


# ---------------------------------------------------------------------------
# 13. No registry resolution
# ---------------------------------------------------------------------------


class TestNoRegistryResolution:
    def test_no_correlation_registry_import_in_closed_loop(self) -> None:
        import ast

        import mpl_sim.closed_loop.minimal_solver as mod

        tree = ast.parse(Path(mod.__file__).read_text())
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        for node in imports:
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "CorrelationRegistry" not in (node.module or "")
            for alias in (node.names if isinstance(node, ast.Import) else node.names):
                assert alias.name != "CorrelationRegistry"

    def test_no_hx_registry_import_in_closed_loop(self) -> None:
        import ast

        import mpl_sim.closed_loop.minimal_solver as mod

        tree = ast.parse(Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name != "HeatExchangerModelRegistry"


# ---------------------------------------------------------------------------
# 14. No full-network solve API introduced
# ---------------------------------------------------------------------------


class TestNoNetworkSolveAPI:
    def test_no_network_import_in_closed_loop(self) -> None:
        import ast

        import mpl_sim.closed_loop.minimal_solver as mod

        tree = ast.parse(Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("mpl_sim.network")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("mpl_sim.network")

    def test_no_solver_import_in_closed_loop(self) -> None:
        import ast

        import mpl_sim.closed_loop.minimal_solver as mod

        tree = ast.parse(Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("mpl_sim.solvers")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("mpl_sim.solvers")

    def test_closed_loop_module_has_no_solve_network_function(self) -> None:
        import mpl_sim.closed_loop as pkg

        assert not hasattr(pkg, "solve_network")
        assert not hasattr(pkg, "solve")

    def test_no_arbitrary_topology_in_api(self) -> None:
        import mpl_sim.closed_loop as pkg

        assert not hasattr(pkg, "Network")
        assert not hasattr(pkg, "network")


# ---------------------------------------------------------------------------
# 15. Public API import tests
# ---------------------------------------------------------------------------


class TestPublicAPIImports:
    def test_import_closed_loop_solve_config(self) -> None:
        from mpl_sim.closed_loop import ClosedLoopSolveConfig as _C

        assert _C is ClosedLoopSolveConfig

    def test_import_minimal_closed_mpl_case(self) -> None:
        from mpl_sim.closed_loop import MinimalClosedMPLCase as _C

        assert _C is MinimalClosedMPLCase

    def test_import_minimal_closed_mpl_result(self) -> None:
        from mpl_sim.closed_loop import MinimalClosedMPLResult as _C

        assert _C is MinimalClosedMPLResult

    def test_import_solve_minimal_closed_mpl(self) -> None:
        from mpl_sim.closed_loop import solve_minimal_closed_mpl as _fn

        assert _fn is solve_minimal_closed_mpl

    def test_package_all_exports(self) -> None:
        import mpl_sim.closed_loop as pkg

        assert "ClosedLoopSolveConfig" in pkg.__all__
        assert "MinimalClosedMPLCase" in pkg.__all__
        assert "MinimalClosedMPLResult" in pkg.__all__
        assert "solve_minimal_closed_mpl" in pkg.__all__

    def test_result_is_frozen_dataclass(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        with pytest.raises((AttributeError, TypeError)):
            result.converged = False  # type: ignore[misc]

    def test_case_is_frozen_dataclass(self) -> None:
        case = _make_case()
        with pytest.raises((AttributeError, TypeError)):
            case.primary_mdot = 99.0  # type: ignore[misc]

    def test_config_is_frozen_dataclass(self) -> None:
        cfg = _default_config()
        with pytest.raises((AttributeError, TypeError)):
            cfg.max_iter = 999  # type: ignore[misc]

    def test_result_type_is_minimal_closed_mpl_result(self) -> None:
        result = solve_minimal_closed_mpl(_make_case(), _default_config())
        assert isinstance(result, MinimalClosedMPLResult)


# ---------------------------------------------------------------------------
# Additional: energy balance at different Q_evap values
# ---------------------------------------------------------------------------


class TestEnergyBalanceScaling:
    @pytest.mark.parametrize("q_evap", [500.0, 1000.0, 2000.0, 5000.0])
    def test_solver_closes_for_various_q_evap(self, q_evap: float) -> None:
        # Bracket must cover [-2*q_evap, 0]
        bounds = (-3.0 * q_evap, 0.0)
        case = _make_case(q_evap=q_evap, q_cond_bounds=bounds)
        config = ClosedLoopSolveConfig(max_iter=80, tolerance=1.0)
        result = solve_minimal_closed_mpl(case, config)
        assert result.converged is True
        assert abs(result.energy_residual) <= config.tolerance

    @pytest.mark.parametrize("q_evap", [500.0, 1000.0, 2000.0, 5000.0])
    def test_solved_q_cond_is_minus_q_evap(self, q_evap: float) -> None:
        bounds = (-3.0 * q_evap, 0.0)
        case = _make_case(q_evap=q_evap, q_cond_bounds=bounds)
        config = ClosedLoopSolveConfig(max_iter=80, tolerance=1.0)
        result = solve_minimal_closed_mpl(case, config)
        # Exact: Q_cond = -Q_evap
        assert abs(result.solved_q_cond - (-q_evap)) < 5.0  # [W]


# ---------------------------------------------------------------------------
# No CoolProp in closed_loop module source
# ---------------------------------------------------------------------------


class TestNoCoolPropInSource:
    def test_no_coolprop_import_in_minimal_solver(self) -> None:
        import ast

        import mpl_sim.closed_loop.minimal_solver as mod

        tree = ast.parse(Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "coolprop" not in alias.name.lower()
            elif isinstance(node, ast.ImportFrom):
                assert "coolprop" not in (node.module or "").lower()

    def test_no_property_backend_import_in_minimal_solver(self) -> None:
        import ast

        import mpl_sim.closed_loop.minimal_solver as mod

        tree = ast.parse(Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("mpl_sim.properties")
