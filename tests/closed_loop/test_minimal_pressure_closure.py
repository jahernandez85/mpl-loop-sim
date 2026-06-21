"""Phase 13B: minimal pressure closure solver acceptance tests.

Verifies all 15 required coverage items:

 1.  Pressure closure converges for a deterministic case.
 2.  Solved primary_mdot matches the analytical expectation for explicit
     linear pump-head and mass-flux-dependent pressure-drop laws.
 3.  Pressure residual is below config.tolerance when converged=True.
 4.  dP_total = dP_evap + dP_cond (exact computation).
 5.  Pump head at solution is reported.
 6.  Energy residual is diagnostic only (not solved in Phase 13B, Option A).
 7.  Invalid bracket (same-sign residuals) is rejected with ValueError.
 8.  Exact endpoint roots are accepted and returned with iterations=0.
 9.  Non-convergence (max_iter too small) is explicit and never silent.
10.  Invalid PressureClosureConfig is rejected:
       max_iter=True, max_iter=False, max_iter=1.5, max_iter=0,
       tolerance=0, tolerance=nan, tolerance=inf.
11.  Invalid mdot_bounds (non-positive lo, lo >= hi, non-finite) fail clearly.
12.  No property lookup (nonexistent fluid name completes without error).
13.  No registry resolution.
14.  No generic network API introduced.
15.  Public API import tests for all Phase 13B exports.

Also verifies that Phase 13A (minimal_solver) behaviour is preserved after
the bisection refactoring to use _bisect_bounded.

Architecture constraints:
  - No CoolProp, no PropertyBackend, no network, no generic solver.
  - Deterministic DP closures are injected explicitly; no registry lookup occurs.
  - FluidState carries only (P, h, identity); no property derivation occurs.
  - Arithmetic is exact and deterministic for the acceptance pressure laws.
"""

from __future__ import annotations

import ast
import dataclasses
import math
from pathlib import Path

import pytest

from mpl_sim.closed_loop import (
    MinimalPressureClosureCase,
    MinimalPressureClosureResult,
    PressureClosureConfig,
    PumpHeadCurve,
    solve_minimal_pressure_closure,
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
    ClosureMetadata,
    Correlation,
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
from mpl_sim.hx_models import EpsilonNTUModel, FixedHeatRate

# ---------------------------------------------------------------------------
# Deterministic test constants — no hidden physical defaults
# ---------------------------------------------------------------------------

_FLUID = PureFluid(name="TestFluid_NoCoolProp")
_MODEL = EpsilonNTUModel()
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

_P_REF = 800_000.0  # [Pa]
_H_REF = 250_000.0  # [J/kg]
_REFERENCE_STATE = FluidState(P=_P_REF, h=_H_REF, identity=_FLUID)

# Fixed heat rates for evaporator and condenser (not energy-balanced).
_Q_EVAP = 1_000.0  # [W] — evaporator gains heat
_Q_COND = -800.0  # [W] — condenser rejects heat (not equal to -Q_evap)

# Pump curve: ΔP_pump(mdot) = HEAD - SLOPE * mdot
# The loop-loss slope is included in the analytical pressure-balance root.
_EVAP_FLOW_AREA_M2 = 0.01
_COND_FLOW_AREA_M2 = 0.02
_EVAP_DP_PER_G = 100.0
_COND_DP_PER_G = 50.0

_PUMP_HEAD_PA = 5_625.0  # [Pa]
_PUMP_SLOPE_PA_S_KG = 100_000.0  # [Pa·s/kg]
# Analytical solution: mdot* = 5625 / (100000 + 12500) = 0.05 kg/s.
_TOTAL_DP_SLOPE = _EVAP_DP_PER_G / _EVAP_FLOW_AREA_M2 + _COND_DP_PER_G / _COND_FLOW_AREA_M2
_MDOT_EXACT = _PUMP_HEAD_PA / (_PUMP_SLOPE_PA_S_KG + _TOTAL_DP_SLOPE)

# Bracket that encloses the root:
#   r(0.01) = +4500 Pa; r(0.50) = -50625 Pa.
_MDOT_BOUNDS = (0.01, 0.50)

# Pressure tolerance for convergence tests.
_P_TOLERANCE = 0.01  # [Pa] — tight enough to verify mdot precisely


# ---------------------------------------------------------------------------
# Shared component + scenario builders
# ---------------------------------------------------------------------------


class _LinearMassFluxDP(Correlation):
    """Deterministic acceptance closure: dP = coefficient * G [Pa]."""

    def __init__(self, coefficient: float, name: str) -> None:
        self.coefficient = coefficient
        self.name = name
        self._source = SourceRef(citation="Phase 13B deterministic acceptance law")
        self._envelope = ValidityEnvelope(
            fluid_families=(AnyFluid(),),
            bounds=(),
            source=self._source,
        )

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return self._envelope

    def evaluate(self, inp: SinglePhaseDPInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(self.coefficient * inp.G,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef(correlation_name=self.name, correlation_version="1"),
                violated=(),
            ),
            metadata=ClosureMetadata(name=self.name, version="1", source=self._source),
        )


def _dp_geom_scalars() -> dict[str, float]:
    return {
        "G": 1.0,
        "D_h": 0.001,
        "L_cell": 1.0,
        "rho": 1000.0,
        "mu": 0.001,
        "roughness": 0.0,
    }


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


def _evap_scenario(q: float = _Q_EVAP) -> EvaporatorScenarioBinding:
    return EvaporatorScenarioBinding(
        secondary_bc=FixedHeatRate(Q=q),
        model=_MODEL,
        discretization=_DISC,
        geom_scalars=_dp_geom_scalars(),
        dp_primary=_LinearMassFluxDP(_EVAP_DP_PER_G, "evap_linear_dp"),
    )


def _cond_scenario(q: float = _Q_COND) -> CondenserScenarioBinding:
    return CondenserScenarioBinding(
        secondary_bc=FixedHeatRate(Q=q),
        model=_MODEL,
        discretization=_DISC,
        geom_scalars=_dp_geom_scalars(),
        dp_primary=_LinearMassFluxDP(_COND_DP_PER_G, "cond_linear_dp"),
    )


def _default_pump() -> PumpHeadCurve:
    return PumpHeadCurve(head_Pa=_PUMP_HEAD_PA, slope_Pa_s_kg=_PUMP_SLOPE_PA_S_KG)


def _default_case(
    mdot_bounds: tuple[float, float] = _MDOT_BOUNDS,
    pump: PumpHeadCurve | None = None,
) -> MinimalPressureClosureCase:
    return MinimalPressureClosureCase(
        reference_state=_REFERENCE_STATE,
        pump_head_curve=pump if pump is not None else _default_pump(),
        evap_component=_evap_component(),
        evap_scenario=_evap_scenario(),
        evap_flow_area=_EVAP_FLOW_AREA_M2,
        cond_component=_cond_component(),
        cond_scenario=_cond_scenario(),
        cond_flow_area=_COND_FLOW_AREA_M2,
        mdot_bounds=mdot_bounds,
    )


def _default_config(tolerance: float = _P_TOLERANCE) -> PressureClosureConfig:
    return PressureClosureConfig(max_iter=60, tolerance=tolerance)


def _solve_default() -> MinimalPressureClosureResult:
    return solve_minimal_pressure_closure(_default_case(), _default_config())


# ---------------------------------------------------------------------------
# Coverage item 1 — convergence
# ---------------------------------------------------------------------------


class TestPressureClosureConverges:
    def test_converged_true(self) -> None:
        r = _solve_default()
        assert r.converged is True

    def test_iterations_positive(self) -> None:
        r = _solve_default()
        assert r.iterations >= 1

    def test_evaluations_include_bracket_and_iterations(self) -> None:
        r = _solve_default()
        assert r.evaluations == r.iterations + 2

    def test_result_is_frozen_dataclass(self) -> None:
        r = _solve_default()
        assert isinstance(r, MinimalPressureClosureResult)
        with pytest.raises((AttributeError, TypeError)):
            r.converged = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Coverage item 2 — solved mdot matches analytical expectation
# ---------------------------------------------------------------------------


class TestSolvedMdotAnalytical:
    def test_solved_mdot_near_exact(self) -> None:
        r = _solve_default()
        # Analytical root includes the pump and loop-loss slopes.
        assert (
            abs(r.solved_primary_mdot - _MDOT_EXACT) < 1e-4
        ), f"solved_primary_mdot={r.solved_primary_mdot} not near {_MDOT_EXACT}"

    def test_solved_mdot_positive(self) -> None:
        r = _solve_default()
        assert r.solved_primary_mdot > 0.0

    def test_solved_mdot_within_bracket(self) -> None:
        r = _solve_default()
        lo, hi = _MDOT_BOUNDS
        assert lo <= r.solved_primary_mdot <= hi

    def test_pump_head_at_solution_near_dp_total(self) -> None:
        r = _solve_default()
        # At solution: pump_head ≈ dP_total (within pressure tolerance).
        assert abs(r.pump_head - r.dP_total) <= _P_TOLERANCE * 2


# ---------------------------------------------------------------------------
# Coverage item 3 — pressure residual below tolerance
# ---------------------------------------------------------------------------


class TestPressureResidualBelowTolerance:
    def test_residual_finite(self) -> None:
        r = _solve_default()
        assert math.isfinite(r.pressure_residual)

    def test_residual_below_tolerance(self) -> None:
        tol = _P_TOLERANCE
        r = solve_minimal_pressure_closure(
            _default_case(), PressureClosureConfig(max_iter=60, tolerance=tol)
        )
        assert abs(r.pressure_residual) <= tol

    def test_residual_equals_pump_head_minus_dp_total(self) -> None:
        r = _solve_default()
        # pressure_residual is defined as pump_head - dP_total at the solution.
        expected = r.pump_head - r.dP_total
        assert abs(r.pressure_residual - expected) < 1e-10


# ---------------------------------------------------------------------------
# Coverage item 4 — dP_total = dP_evap + dP_cond
# ---------------------------------------------------------------------------


class TestDPTotalSumCorrect:
    def test_dp_total_equals_sum(self) -> None:
        r = _solve_default()
        assert r.dP_total == r.dP_evap + r.dP_cond

    def test_dp_fields_finite(self) -> None:
        r = _solve_default()
        assert math.isfinite(r.dP_evap)
        assert math.isfinite(r.dP_cond)
        assert math.isfinite(r.dP_total)

    def test_dp_is_nonzero_and_flow_dependent(self) -> None:
        r = _solve_default()
        assert r.dP_evap == pytest.approx(
            _EVAP_DP_PER_G * r.solved_primary_mdot / _EVAP_FLOW_AREA_M2
        )
        assert r.dP_cond == pytest.approx(
            _COND_DP_PER_G * r.solved_primary_mdot / _COND_FLOW_AREA_M2
        )
        assert r.dP_total > 0.0

    def test_dp_total_from_result_objects(self) -> None:
        r = _solve_default()
        assert r.dP_evap == r.evap_result.dP_primary
        assert r.dP_cond == r.cond_result.dP_primary


# ---------------------------------------------------------------------------
# Coverage item 5 — pump head at solution is reported
# ---------------------------------------------------------------------------


class TestPumpHeadReported:
    def test_pump_head_finite(self) -> None:
        r = _solve_default()
        assert math.isfinite(r.pump_head)

    def test_pump_head_matches_curve_at_solved_mdot(self) -> None:
        r = _solve_default()
        expected = _default_pump().evaluate(r.solved_primary_mdot)
        assert abs(r.pump_head - expected) < 1e-10

    def test_pump_head_positive_for_linear_curve(self) -> None:
        r = _solve_default()
        # At mdot < HEAD/SLOPE, pump head is positive.
        assert r.pump_head >= 0.0


# ---------------------------------------------------------------------------
# Coverage item 6 — energy residual is diagnostic, NOT solved (Option A)
# ---------------------------------------------------------------------------


class TestEnergyResidualIsDiagnostic:
    def test_energy_residual_reported(self) -> None:
        r = _solve_default()
        assert math.isfinite(r.energy_residual)

    def test_energy_residual_nonzero_when_not_balanced(self) -> None:
        # Q_evap=1000 W, Q_cond=-800 W — not energy-balanced.
        # At any mdot: energy_residual = (Q_evap + Q_cond) / mdot != 0.
        r = _solve_default()
        assert (
            abs(r.energy_residual) > 0.0
        ), "energy_residual should be non-zero when Q_evap + Q_cond != 0"

    def test_energy_residual_not_below_pressure_tolerance(self) -> None:
        # The solver does not enforce |energy_residual| <= pressure_tolerance.
        r = _solve_default()
        # energy_residual ≈ (1000 - 800) / 0.05 = 4000 J/kg >> P_TOLERANCE.
        assert (
            abs(r.energy_residual) > 1.0
        ), "energy_residual should not be near zero for unbalanced scenario"

    def test_h_reference_and_h_return_reported(self) -> None:
        r = _solve_default()
        assert r.h_reference == _H_REF
        assert math.isfinite(r.h_return)
        assert r.energy_residual == pytest.approx(r.h_return - r.h_reference, abs=1e-10)

    def test_state_fields_present(self) -> None:
        r = _solve_default()
        assert r.reference_state is _REFERENCE_STATE
        assert r.state_after_evap is not None
        assert r.return_state is not None


# ---------------------------------------------------------------------------
# Coverage item 7 — invalid bracket rejected
# ---------------------------------------------------------------------------


class TestInvalidBracketRejected:
    def test_same_sign_residuals_raise(self) -> None:
        # r(0.3) = 5000 - 30000 = -25000 < 0
        # r(0.5) = 5000 - 50000 = -45000 < 0  → same sign
        case = _default_case(mdot_bounds=(0.30, 0.50))
        with pytest.raises(ValueError, match="does not enclose a root"):
            solve_minimal_pressure_closure(case, _default_config())

    def test_same_sign_both_positive_raise(self) -> None:
        # r(0.001) = 5000 - 100 = +4900 > 0
        # r(0.010) = 5000 - 1000 = +4000 > 0 → same sign
        case = _default_case(mdot_bounds=(0.001, 0.010))
        with pytest.raises(ValueError, match="does not enclose a root"):
            solve_minimal_pressure_closure(case, _default_config())


# ---------------------------------------------------------------------------
# Coverage item 8 — exact endpoint roots accepted
# ---------------------------------------------------------------------------


class TestEndpointRootsAccepted:
    def test_lower_endpoint_root(self) -> None:
        # r(mdot_lo) = 0 exactly: HEAD - SLOPE * mdot_lo = 0 → mdot_lo = HEAD/SLOPE.
        mdot_lo = _MDOT_EXACT  # 0.05 kg/s — exact root
        mdot_hi = 0.50
        case = _default_case(mdot_bounds=(mdot_lo, mdot_hi))
        config = PressureClosureConfig(max_iter=60, tolerance=1e-6)
        r = solve_minimal_pressure_closure(case, config)
        assert r.converged is True
        assert r.iterations == 0
        assert abs(r.solved_primary_mdot - mdot_lo) < 1e-12
        assert abs(r.pressure_residual) <= 1e-6

    def test_upper_endpoint_root(self) -> None:
        # r(mdot_hi) = 0 exactly: HEAD - SLOPE * mdot_hi = 0 → mdot_hi = HEAD/SLOPE.
        mdot_lo = 0.01
        mdot_hi = _MDOT_EXACT  # 0.05 kg/s — exact root
        case = _default_case(mdot_bounds=(mdot_lo, mdot_hi))
        config = PressureClosureConfig(max_iter=60, tolerance=1e-6)
        r = solve_minimal_pressure_closure(case, config)
        assert r.converged is True
        assert r.iterations == 0
        assert abs(r.solved_primary_mdot - mdot_hi) < 1e-12
        assert abs(r.pressure_residual) <= 1e-6


# ---------------------------------------------------------------------------
# Coverage item 9 — non-convergence is explicit
# ---------------------------------------------------------------------------


class TestNonConvergence:
    def test_max_iter_one_does_not_converge(self) -> None:
        config = PressureClosureConfig(max_iter=1, tolerance=1e-12)
        r = solve_minimal_pressure_closure(_default_case(), config)
        assert r.converged is False

    def test_non_convergence_iterations_reported(self) -> None:
        config = PressureClosureConfig(max_iter=2, tolerance=1e-12)
        r = solve_minimal_pressure_closure(_default_case(), config)
        assert not r.converged
        assert r.iterations == 2

    def test_non_convergence_residual_finite(self) -> None:
        config = PressureClosureConfig(max_iter=1, tolerance=1e-12)
        r = solve_minimal_pressure_closure(_default_case(), config)
        assert math.isfinite(r.pressure_residual)

    def test_non_convergence_still_returns_result(self) -> None:
        config = PressureClosureConfig(max_iter=1, tolerance=1e-12)
        r = solve_minimal_pressure_closure(_default_case(), config)
        assert isinstance(r, MinimalPressureClosureResult)


# ---------------------------------------------------------------------------
# Coverage item 10 — invalid PressureClosureConfig rejected
# ---------------------------------------------------------------------------


class TestInvalidConfig:
    def test_max_iter_bool_true_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_iter"):
            PressureClosureConfig(max_iter=True)  # type: ignore[arg-type]

    def test_max_iter_bool_false_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_iter"):
            PressureClosureConfig(max_iter=False)  # type: ignore[arg-type]

    def test_max_iter_float_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_iter"):
            PressureClosureConfig(max_iter=1.5)  # type: ignore[arg-type]

    def test_max_iter_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_iter"):
            PressureClosureConfig(max_iter=0)

    def test_tolerance_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            PressureClosureConfig(tolerance=0.0)

    def test_tolerance_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            PressureClosureConfig(tolerance=float("nan"))

    def test_tolerance_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            PressureClosureConfig(tolerance=float("inf"))


# ---------------------------------------------------------------------------
# Coverage item 11 — invalid mdot_bounds fail clearly
# ---------------------------------------------------------------------------


class TestInvalidMdotBounds:
    def test_lo_not_positive_raises(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            MinimalPressureClosureCase(
                reference_state=_REFERENCE_STATE,
                pump_head_curve=_default_pump(),
                evap_component=_evap_component(),
                evap_scenario=_evap_scenario(),
                evap_flow_area=_EVAP_FLOW_AREA_M2,
                cond_component=_cond_component(),
                cond_scenario=_cond_scenario(),
                cond_flow_area=_COND_FLOW_AREA_M2,
                mdot_bounds=(0.0, 0.5),
            )

    def test_lo_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            MinimalPressureClosureCase(
                reference_state=_REFERENCE_STATE,
                pump_head_curve=_default_pump(),
                evap_component=_evap_component(),
                evap_scenario=_evap_scenario(),
                evap_flow_area=_EVAP_FLOW_AREA_M2,
                cond_component=_cond_component(),
                cond_scenario=_cond_scenario(),
                cond_flow_area=_COND_FLOW_AREA_M2,
                mdot_bounds=(-0.1, 0.5),
            )

    def test_lo_ge_hi_raises(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            MinimalPressureClosureCase(
                reference_state=_REFERENCE_STATE,
                pump_head_curve=_default_pump(),
                evap_component=_evap_component(),
                evap_scenario=_evap_scenario(),
                evap_flow_area=_EVAP_FLOW_AREA_M2,
                cond_component=_cond_component(),
                cond_scenario=_cond_scenario(),
                cond_flow_area=_COND_FLOW_AREA_M2,
                mdot_bounds=(0.5, 0.1),
            )

    def test_lo_equal_hi_raises(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            MinimalPressureClosureCase(
                reference_state=_REFERENCE_STATE,
                pump_head_curve=_default_pump(),
                evap_component=_evap_component(),
                evap_scenario=_evap_scenario(),
                evap_flow_area=_EVAP_FLOW_AREA_M2,
                cond_component=_cond_component(),
                cond_scenario=_cond_scenario(),
                cond_flow_area=_COND_FLOW_AREA_M2,
                mdot_bounds=(0.1, 0.1),
            )

    def test_lo_infinite_raises(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            MinimalPressureClosureCase(
                reference_state=_REFERENCE_STATE,
                pump_head_curve=_default_pump(),
                evap_component=_evap_component(),
                evap_scenario=_evap_scenario(),
                evap_flow_area=_EVAP_FLOW_AREA_M2,
                cond_component=_cond_component(),
                cond_scenario=_cond_scenario(),
                cond_flow_area=_COND_FLOW_AREA_M2,
                mdot_bounds=(float("inf"), 1.0),
            )

    def test_hi_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            MinimalPressureClosureCase(
                reference_state=_REFERENCE_STATE,
                pump_head_curve=_default_pump(),
                evap_component=_evap_component(),
                evap_scenario=_evap_scenario(),
                evap_flow_area=_EVAP_FLOW_AREA_M2,
                cond_component=_cond_component(),
                cond_scenario=_cond_scenario(),
                cond_flow_area=_COND_FLOW_AREA_M2,
                mdot_bounds=(0.01, float("nan")),
            )


class TestRequiredPressureInputs:
    def test_missing_evaporator_dp_rejected(self) -> None:
        scenario = dataclasses.replace(_evap_scenario(), dp_primary=None)
        with pytest.raises(ValueError, match="evap_scenario.dp_primary"):
            dataclasses.replace(_default_case(), evap_scenario=scenario)

    def test_missing_condenser_dp_rejected(self) -> None:
        scenario = dataclasses.replace(_cond_scenario(), dp_primary=None)
        with pytest.raises(ValueError, match="cond_scenario.dp_primary"):
            dataclasses.replace(_default_case(), cond_scenario=scenario)

    @pytest.mark.parametrize("field", ["evap_flow_area", "cond_flow_area"])
    @pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
    def test_invalid_flow_area_rejected(self, field: str, value: float) -> None:
        with pytest.raises(ValueError, match=field):
            dataclasses.replace(_default_case(), **{field: value})


# ---------------------------------------------------------------------------
# Coverage item 12 — no property lookup
# ---------------------------------------------------------------------------


class TestNoPropertyLookup:
    def test_nonexistent_fluid_completes(self) -> None:
        fluid = PureFluid(name="SomeFluidThatDoesNotExistInCoolProp_XYZ123")
        state = FluidState(P=_P_REF, h=_H_REF, identity=fluid)
        case = MinimalPressureClosureCase(
            reference_state=state,
            pump_head_curve=_default_pump(),
            evap_component=_evap_component(),
            evap_scenario=_evap_scenario(),
            evap_flow_area=_EVAP_FLOW_AREA_M2,
            cond_component=_cond_component(),
            cond_scenario=_cond_scenario(),
            cond_flow_area=_COND_FLOW_AREA_M2,
            mdot_bounds=_MDOT_BOUNDS,
        )
        r = solve_minimal_pressure_closure(case, _default_config())
        # If property lookup were attempted, this would raise. Since FluidState
        # is pure (P, h, identity), it completes without error.
        assert isinstance(r, MinimalPressureClosureResult)

    def test_no_coolprop_import_in_pressure_solver(self) -> None:
        src = Path(__file__).parents[2] / "src" / "mpl_sim" / "closed_loop" / "pressure_solver.py"
        text = src.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "CoolProp" not in (node.module or ""), "pressure_solver.py imports CoolProp"
                assert "PropertyBackend" not in (node.module or "")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "CoolProp" not in alias.name
                    assert "PropertyBackend" not in alias.name

    def test_no_coolprop_import_in_scalar_solve(self) -> None:
        src = Path(__file__).parents[2] / "src" / "mpl_sim" / "closed_loop" / "_scalar_solve.py"
        text = src.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "CoolProp" not in (node.module or "")
                assert "PropertyBackend" not in (node.module or "")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "CoolProp" not in alias.name


# ---------------------------------------------------------------------------
# Coverage item 13 — no registry resolution
# ---------------------------------------------------------------------------


class TestNoRegistryResolution:
    def test_no_correlation_registry_in_pressure_solver(self) -> None:
        src = Path(__file__).parents[2] / "src" / "mpl_sim" / "closed_loop" / "pressure_solver.py"
        text = src.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "CorrelationRegistry" not in (node.module or "")
                assert "HeatExchangerModelRegistry" not in (node.module or "")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "CorrelationRegistry" not in alias.name
                    assert "HeatExchangerModelRegistry" not in alias.name

    def test_no_registry_import_in_ast(self) -> None:
        src = Path(__file__).parents[2] / "src" / "mpl_sim" / "closed_loop" / "pressure_solver.py"
        text = src.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(
                    "mpl_sim.network"
                ), f"pressure_solver.py imports mpl_sim.network: {node.module}"
                assert not node.module.startswith(
                    "mpl_sim.solvers"
                ), f"pressure_solver.py imports mpl_sim.solvers: {node.module}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("mpl_sim.network")
                    assert not alias.name.startswith("mpl_sim.solvers")


# ---------------------------------------------------------------------------
# Coverage item 14 — no generic network API introduced
# ---------------------------------------------------------------------------


class TestNoGenericNetworkAPI:
    def test_no_solve_network_in_pressure_solver(self) -> None:
        # Check via AST: no import of mpl_sim.network or mpl_sim.solvers.
        src = Path(__file__).parents[2] / "src" / "mpl_sim" / "closed_loop" / "pressure_solver.py"
        text = src.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not (node.module or "").startswith(
                    "mpl_sim.network"
                ), f"pressure_solver.py imports mpl_sim.network: {node.module}"
                assert not (node.module or "").startswith(
                    "mpl_sim.solvers"
                ), f"pressure_solver.py imports mpl_sim.solvers: {node.module}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("mpl_sim.network")
                    assert not alias.name.startswith("mpl_sim.solvers")

    def test_no_mpl_sim_network_import(self) -> None:
        # The pressure solver must not import mpl_sim.network (checked via AST above).
        # Also confirm the module doesn't reference arbitrary-network solve patterns.
        src = Path(__file__).parents[2] / "src" / "mpl_sim" / "closed_loop" / "pressure_solver.py"
        text = src.read_text(encoding="utf-8")
        # "solve(network)" as Python code would need parens — simple substring check is safe.
        assert "solve(network)" not in text

    def test_solve_minimal_pressure_closure_signature_no_network(self) -> None:
        import inspect

        sig = inspect.signature(solve_minimal_pressure_closure)
        params = list(sig.parameters.keys())
        # Should be exactly (case, config).
        assert "network" not in params
        assert "topology" not in params
        assert len(params) == 2


# ---------------------------------------------------------------------------
# Coverage item 15 — public API import tests
# ---------------------------------------------------------------------------


class TestPublicAPIImports:
    def test_pump_head_curve_importable(self) -> None:
        from mpl_sim.closed_loop import PumpHeadCurve as _PumpHeadCurve  # noqa: F401

        assert _PumpHeadCurve is PumpHeadCurve

    def test_pressure_closure_config_importable(self) -> None:
        from mpl_sim.closed_loop import PressureClosureConfig as _PCC  # noqa: F401

        assert _PCC is PressureClosureConfig

    def test_case_importable(self) -> None:
        from mpl_sim.closed_loop import MinimalPressureClosureCase as _MPCC  # noqa: F401

        assert _MPCC is MinimalPressureClosureCase

    def test_result_importable(self) -> None:
        from mpl_sim.closed_loop import MinimalPressureClosureResult as _MPCR  # noqa: F401

        assert _MPCR is MinimalPressureClosureResult

    def test_solver_importable(self) -> None:
        from mpl_sim.closed_loop import solve_minimal_pressure_closure as _smpc  # noqa: F401

        assert _smpc is solve_minimal_pressure_closure

    def test_all_phase_13b_names_in_all(self) -> None:
        import mpl_sim.closed_loop as pkg

        for name in (
            "PumpHeadCurve",
            "PressureClosureConfig",
            "MinimalPressureClosureCase",
            "MinimalPressureClosureResult",
            "solve_minimal_pressure_closure",
        ):
            assert name in pkg.__all__, f"{name!r} not in mpl_sim.closed_loop.__all__"

    def test_phase_13a_exports_unchanged(self) -> None:
        import mpl_sim.closed_loop as pkg

        for name in (
            "ClosedLoopSolveConfig",
            "MinimalClosedMPLCase",
            "MinimalClosedMPLResult",
            "solve_minimal_closed_mpl",
        ):
            assert name in pkg.__all__, f"Phase 13A export {name!r} missing from __all__"

    def test_result_is_frozen_dataclass(self) -> None:
        import dataclasses

        assert dataclasses.is_dataclass(MinimalPressureClosureResult)
        fields = {f.name for f in dataclasses.fields(MinimalPressureClosureResult)}
        required = {
            "converged",
            "iterations",
            "evaluations",
            "pressure_residual",
            "solved_primary_mdot",
            "pump_head",
            "dP_evap",
            "dP_cond",
            "dP_total",
            "evap_result",
            "cond_result",
            "reference_state",
            "state_after_evap",
            "return_state",
            "h_reference",
            "h_return",
            "energy_residual",
            "warnings",
        }
        assert required <= fields


# ---------------------------------------------------------------------------
# PumpHeadCurve unit tests
# ---------------------------------------------------------------------------


class TestPumpHeadCurve:
    def test_constant_head(self) -> None:
        c = PumpHeadCurve(head_Pa=3000.0)
        assert c.evaluate(0.0) == pytest.approx(3000.0)
        assert c.evaluate(0.5) == pytest.approx(3000.0)

    def test_linear_head(self) -> None:
        c = PumpHeadCurve(head_Pa=5000.0, slope_Pa_s_kg=100_000.0)
        assert c.evaluate(0.0) == pytest.approx(5000.0)
        assert c.evaluate(0.05) == pytest.approx(0.0, abs=1e-9)
        assert c.evaluate(0.1) == pytest.approx(-5000.0)

    def test_head_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="head_Pa"):
            PumpHeadCurve(head_Pa=float("nan"))

    def test_head_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="head_Pa"):
            PumpHeadCurve(head_Pa=float("inf"))

    def test_slope_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="slope_Pa_s_kg"):
            PumpHeadCurve(head_Pa=1000.0, slope_Pa_s_kg=float("nan"))

    def test_slope_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="slope_Pa_s_kg"):
            PumpHeadCurve(head_Pa=1000.0, slope_Pa_s_kg=float("inf"))

    def test_frozen(self) -> None:
        c = PumpHeadCurve(head_Pa=1000.0)
        with pytest.raises((AttributeError, TypeError)):
            c.head_Pa = 2000.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Phase 13A regression — bisection refactoring must not change behaviour
# ---------------------------------------------------------------------------


class TestPhase13ARegression:
    """Verify that the minimal_solver.py bisection refactoring preserves
    all Phase 13A acceptance criteria.  These tests confirm the shared
    _bisect_bounded utility produces identical results to the old inline loop.
    """

    def test_phase_13a_still_converges(self) -> None:
        from mpl_sim.closed_loop import (
            ClosedLoopSolveConfig,
            MinimalClosedMPLCase,
            solve_minimal_closed_mpl,
        )

        mdot = 0.05
        q_evap = 1000.0
        h_ref = 250_000.0
        reference_state = FluidState(P=800_000.0, h=h_ref, identity=_FLUID)
        evap_scenario = _evap_scenario(q=q_evap)
        cond_scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=0.0),
            model=_MODEL,
            discretization=_DISC,
        )
        case = MinimalClosedMPLCase(
            reference_state=reference_state,
            primary_mdot=mdot,
            evap_component=_evap_component(),
            evap_scenario=evap_scenario,
            cond_component=_cond_component(),
            cond_scenario=cond_scenario,
            q_cond_bounds=(-5000.0, 0.0),
        )
        config = ClosedLoopSolveConfig(max_iter=60, tolerance=1.0)
        r = solve_minimal_closed_mpl(case, config)
        assert r.converged is True
        # Analytical: Q_cond = -Q_evap = -1000 W.
        assert abs(r.solved_q_cond - (-q_evap)) < 1.0
        assert abs(r.energy_residual) <= 1.0

    def test_phase_13a_endpoint_root_lower(self) -> None:
        from mpl_sim.closed_loop import (
            ClosedLoopSolveConfig,
            MinimalClosedMPLCase,
            solve_minimal_closed_mpl,
        )

        mdot = 0.05
        q_evap = 1000.0
        reference_state = FluidState(P=800_000.0, h=250_000.0, identity=_FLUID)
        evap_scenario = _evap_scenario(q=q_evap)
        cond_scenario = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=0.0),
            model=_MODEL,
            discretization=_DISC,
        )
        # Lower endpoint root: q_lo = -q_evap = exact solution.
        q_lo = -q_evap
        case = MinimalClosedMPLCase(
            reference_state=reference_state,
            primary_mdot=mdot,
            evap_component=_evap_component(),
            evap_scenario=evap_scenario,
            cond_component=_cond_component(),
            cond_scenario=cond_scenario,
            q_cond_bounds=(q_lo, 0.0),
        )
        config = ClosedLoopSolveConfig(max_iter=60, tolerance=1e-6)
        r = solve_minimal_closed_mpl(case, config)
        assert r.converged is True
        assert r.iterations == 0
        assert abs(r.solved_q_cond - q_lo) < 1e-12
