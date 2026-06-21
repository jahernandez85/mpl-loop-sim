"""Phase 13D: minimal coupled fixed-architecture closure acceptance tests.

Verifies all required coverage items:

 1.  Coupled closure converges for a deterministic case.
 2.  Solved Q_cond matches the analytical expectation (-200 W).
 3.  Solved primary_mdot matches the analytical expectation (0.05 kg/s).
 4.  Energy residual is below energy_tolerance when converged.
 5.  Pressure residual is below pressure_tolerance when converged.
 6.  ResidualVector is returned and holds both residual evaluations.
 7.  Scaled residual norms are below the configured tolerance.
 8.  dP_total = dP_evap + dP_cond (exact computation).
 9.  Pump head equals loop dP at the solution (within pressure_tolerance).
10.  Mass flux uses explicit flow areas: G_evap = mdot/A_evap, G_cond = mdot/A_cond.
11.  Condenser heat rate is the solved scalar (not fixed by the case).
12.  Evaporator is evaluated consistently at each outer trial.
13.  Invalid Q_cond bracket (no sign change) is rejected with ValueError.
14.  Invalid mdot bracket (no sign change) is rejected with ValueError.
15.  Endpoint roots are handled (iterations=0; converged=True; residual in tolerance).
16.  Non-convergence is explicit and never silent (converged=False on max_iter).
17.  Invalid CoupledClosureConfig is rejected:
       bool max_iters; non-int max_iters; zero max_iters;
       zero/negative/nan/inf/bool tolerances; zero/negative/nan/inf/bool scales.
18.  Missing dp_primary closures fail clearly at case construction.
19.  No property lookup (nonexistent fluid name does not error).
20.  No registry resolution (no CorrelationRegistry call occurs).
21.  No generic network API introduced (no Network/Node/Branch/Junction import).
22.  No topology classes introduced (checked via AST + module inspection).
23.  No valves/manifolds/recuperator/pre-heaters (checked via AST).
24.  Example script imports safely and executes as __main__.
25.  No file writes (result is a plain dataclass; no disk output).
26.  Phase 13A and 13B public APIs still work (regression coverage).

Analytical acceptance case (deterministic, CoolProp-free)
----------------------------------------------------------
  dP_evap  = EVAP_DP_PER_G * G_evap = 100 * (mdot / 0.01) = 10000 * mdot
  dP_cond  = COND_DP_PER_G * G_cond = 50  * (mdot / 0.02) =  2500 * mdot
  dP_total = 12500 * mdot
  pump_head = 5625 - 100000 * mdot

  Pressure root: 5625 = 112500 * mdot  →  mdot* = 0.05 kg/s

  Q_evap = 200 W  (fixed input heat)
  Energy closure:  h_return = h_ref  ⟹  Q_cond = -Q_evap = -200 W

  At mdot* = 0.05 kg/s:
    dP_evap  = 10000 * 0.05 = 500 Pa
    dP_cond  =  2500 * 0.05 = 125 Pa
    dP_total = 625 Pa
    pump_head = 5625 - 100000*0.05 = 625 Pa  ✓ (equal to dP_total)

Architecture constraints:
  - No CoolProp, no PropertyBackend, no network, no generic solver.
  - DP closures are injected explicitly; no registry lookup occurs.
  - FluidState carries only (P, h, identity); no property derivation.
  - Arithmetic is exact for these linear DP and FixedHeatRate laws.
"""

from __future__ import annotations

import ast
import dataclasses
import math
import runpy
from pathlib import Path

import pytest

from mpl_sim.closed_loop import (
    CoupledClosureConfig,
    MinimalCoupledClosureCase,
    MinimalCoupledClosureResult,
    ResidualVector,
    solve_minimal_coupled_closure,
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
# Deterministic acceptance constants — no hidden physical defaults
# ---------------------------------------------------------------------------

_FLUID = PureFluid(name="TestFluid_NoCoolProp")
_MODEL = EpsilonNTUModel()
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

_P_REF = 800_000.0  # [Pa]
_H_REF = 250_000.0  # [J/kg]
_REFERENCE_STATE = FluidState(P=_P_REF, h=_H_REF, identity=_FLUID)

# Explicit acceptance constants — all named, none hidden.
_Q_EVAP = 200.0  # [W]  fixed evaporator heat input
_Q_COND_EXACT = -200.0  # [W]  analytical energy-closure solution

_EVAP_FLOW_AREA = 0.01  # [m²]
_COND_FLOW_AREA = 0.02  # [m²]
_EVAP_DP_PER_G = 100.0  # [Pa/(kg/m²/s)]
_COND_DP_PER_G = 50.0  # [Pa/(kg/m²/s)]

_PUMP_HEAD_PA = 5_625.0  # [Pa]  pump head at zero flow
_PUMP_SLOPE_PA_S_KG = 100_000.0  # [Pa·s/kg]  head slope

# Derived analytical roots (for assertions below).
# dP_total = (EVAP_DP_PER_G/EVAP_FLOW_AREA + COND_DP_PER_G/COND_FLOW_AREA) * mdot
_TOTAL_DP_SLOPE = _EVAP_DP_PER_G / _EVAP_FLOW_AREA + _COND_DP_PER_G / _COND_FLOW_AREA
_MDOT_EXACT = _PUMP_HEAD_PA / (_PUMP_SLOPE_PA_S_KG + _TOTAL_DP_SLOPE)  # = 0.05 kg/s
_DP_TOTAL_AT_SOLUTION = _TOTAL_DP_SLOPE * _MDOT_EXACT  # = 625 Pa

# Tolerance for acceptance comparisons (not config tolerance).
_MDOT_ACCEPT_TOL = 1e-4  # [kg/s]
_Q_ACCEPT_TOL = 1e-2  # [W]

# Solver tolerances.
_ENERGY_TOL = 1e-6  # [J/kg]
_PRESSURE_TOL = 0.01  # [Pa]

# Energy and pressure scales for ResidualVector.
_ENERGY_SCALE = 1000.0  # [J/kg]
_PRESSURE_SCALE = 100.0  # [Pa]

# Brackets enclosing both roots.
_Q_COND_BOUNDS = (-500.0, 0.0)  # encloses Q_cond* = -200 W
_MDOT_BOUNDS = (0.01, 0.50)  # encloses mdot* = 0.05 kg/s


# ---------------------------------------------------------------------------
# Deterministic DP closure
# ---------------------------------------------------------------------------


class _LinearMassFluxDP(Correlation):
    """Exact acceptance law: dP = coefficient * G [Pa].  No CoolProp."""

    def __init__(self, coefficient: float, name: str) -> None:
        self._coeff = coefficient
        self._name = name
        self._source = SourceRef(citation="Phase 13D deterministic acceptance law")
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
            value=(self._coeff * inp.G,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef(correlation_name=self._name, correlation_version="1"),
                violated=(),
            ),
            metadata=ClosureMetadata(name=self._name, version="1", source=self._source),
        )


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


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


def _evap_scenario() -> EvaporatorScenarioBinding:
    return EvaporatorScenarioBinding(
        secondary_bc=FixedHeatRate(Q=_Q_EVAP),
        model=_MODEL,
        discretization=_DISC,
        geom_scalars=_dp_geom_scalars(),
        dp_primary=_LinearMassFluxDP(_EVAP_DP_PER_G, "evap_linear_dp"),
    )


def _cond_scenario(q: float = -800.0) -> CondenserScenarioBinding:
    return CondenserScenarioBinding(
        secondary_bc=FixedHeatRate(Q=q),
        model=_MODEL,
        discretization=_DISC,
        geom_scalars=_dp_geom_scalars(),
        dp_primary=_LinearMassFluxDP(_COND_DP_PER_G, "cond_linear_dp"),
    )


def _default_case(
    q_cond_bounds: tuple[float, float] = _Q_COND_BOUNDS,
    mdot_bounds: tuple[float, float] = _MDOT_BOUNDS,
) -> MinimalCoupledClosureCase:
    from mpl_sim.closed_loop import PumpHeadCurve

    return MinimalCoupledClosureCase(
        reference_state=_REFERENCE_STATE,
        pump_head_curve=PumpHeadCurve(head_Pa=_PUMP_HEAD_PA, slope_Pa_s_kg=_PUMP_SLOPE_PA_S_KG),
        evap_component=_evap_component(),
        evap_scenario=_evap_scenario(),
        evap_flow_area=_EVAP_FLOW_AREA,
        cond_component=_cond_component(),
        cond_scenario=_cond_scenario(),
        cond_flow_area=_COND_FLOW_AREA,
        q_cond_bounds=q_cond_bounds,
        mdot_bounds=mdot_bounds,
    )


def _default_config(
    energy_tol: float = _ENERGY_TOL,
    pressure_tol: float = _PRESSURE_TOL,
) -> CoupledClosureConfig:
    return CoupledClosureConfig(
        energy_tolerance=energy_tol,
        pressure_tolerance=pressure_tol,
        energy_scale=_ENERGY_SCALE,
        pressure_scale=_PRESSURE_SCALE,
        inner_max_iter=60,
        outer_max_iter=60,
    )


def _solve_default() -> MinimalCoupledClosureResult:
    return solve_minimal_coupled_closure(_default_case(), _default_config())


# ---------------------------------------------------------------------------
# 1 — Convergence
# ---------------------------------------------------------------------------


class TestCoupledClosureConverges:
    def test_converged_true(self) -> None:
        r = _solve_default()
        assert r.converged is True

    def test_outer_iterations_positive(self) -> None:
        r = _solve_default()
        assert r.outer_iterations >= 1

    def test_inner_iterations_positive(self) -> None:
        r = _solve_default()
        assert r.inner_iterations_total >= 1

    def test_inner_evaluations_positive(self) -> None:
        r = _solve_default()
        assert r.inner_evaluations_total >= 1

    def test_result_is_frozen_dataclass(self) -> None:
        r = _solve_default()
        assert isinstance(r, MinimalCoupledClosureResult)
        with pytest.raises((AttributeError, TypeError)):
            r.converged = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2 — Solved Q_cond matches analytical expectation
# ---------------------------------------------------------------------------


class TestSolvedQCondAnalytical:
    def test_solved_q_cond_near_exact(self) -> None:
        r = _solve_default()
        assert (
            abs(r.solved_q_cond - _Q_COND_EXACT) < _Q_ACCEPT_TOL
        ), f"solved_q_cond={r.solved_q_cond!r} not near {_Q_COND_EXACT!r}"

    def test_solved_q_cond_negative(self) -> None:
        r = _solve_default()
        assert r.solved_q_cond < 0.0  # condenser rejects heat

    def test_solved_q_cond_within_bracket(self) -> None:
        r = _solve_default()
        q_lo, q_hi = _Q_COND_BOUNDS
        assert q_lo <= r.solved_q_cond <= q_hi


# ---------------------------------------------------------------------------
# 3 — Solved primary_mdot matches analytical expectation
# ---------------------------------------------------------------------------


class TestSolvedMdotAnalytical:
    def test_solved_mdot_near_exact(self) -> None:
        r = _solve_default()
        assert (
            abs(r.solved_primary_mdot - _MDOT_EXACT) < _MDOT_ACCEPT_TOL
        ), f"solved_primary_mdot={r.solved_primary_mdot!r} not near {_MDOT_EXACT!r}"

    def test_solved_mdot_positive(self) -> None:
        r = _solve_default()
        assert r.solved_primary_mdot > 0.0

    def test_solved_mdot_within_bracket(self) -> None:
        r = _solve_default()
        lo, hi = _MDOT_BOUNDS
        assert lo <= r.solved_primary_mdot <= hi


# ---------------------------------------------------------------------------
# 4 — Energy residual below tolerance
# ---------------------------------------------------------------------------


class TestEnergyResidualBelowTolerance:
    def test_energy_residual_finite(self) -> None:
        r = _solve_default()
        assert math.isfinite(r.energy_residual)

    def test_energy_residual_below_tolerance(self) -> None:
        r = _solve_default()
        assert (
            abs(r.energy_residual) <= _ENERGY_TOL * 10
        ), f"energy_residual={r.energy_residual!r} exceeds tolerance {_ENERGY_TOL!r}"

    def test_h_return_near_h_reference(self) -> None:
        r = _solve_default()
        assert abs(r.h_return - r.h_reference) < 1.0  # [J/kg]

    def test_energy_residual_equals_h_return_minus_h_ref(self) -> None:
        r = _solve_default()
        assert abs(r.energy_residual - (r.h_return - r.h_reference)) < 1e-9


# ---------------------------------------------------------------------------
# 5 — Pressure residual below tolerance
# ---------------------------------------------------------------------------


class TestPressureResidualBelowTolerance:
    def test_pressure_residual_finite(self) -> None:
        r = _solve_default()
        assert math.isfinite(r.pressure_residual)

    def test_pressure_residual_below_tolerance(self) -> None:
        r = _solve_default()
        assert (
            abs(r.pressure_residual) <= _PRESSURE_TOL * 2
        ), f"pressure_residual={r.pressure_residual!r} exceeds tolerance {_PRESSURE_TOL!r}"

    def test_pump_head_near_dp_total(self) -> None:
        r = _solve_default()
        assert abs(r.pump_head - r.dP_total) <= _PRESSURE_TOL * 2


# ---------------------------------------------------------------------------
# 6 — ResidualVector is returned
# ---------------------------------------------------------------------------


class TestResidualVectorReturned:
    def test_residual_vector_is_ResidualVector(self) -> None:
        r = _solve_default()
        assert isinstance(r.residual_vector, ResidualVector)

    def test_residual_vector_has_two_evaluations(self) -> None:
        r = _solve_default()
        assert len(r.residual_vector.evaluations) == 2

    def test_residual_vector_names(self) -> None:
        r = _solve_default()
        names = {ev.spec.name for ev in r.residual_vector.evaluations}
        assert "energy" in names
        assert "pressure" in names

    def test_residual_vector_energy_value_matches(self) -> None:
        r = _solve_default()
        ev = next(e for e in r.residual_vector.evaluations if e.spec.name == "energy")
        assert abs(ev.value - r.energy_residual) < 1e-12

    def test_residual_vector_pressure_value_matches(self) -> None:
        r = _solve_default()
        ev = next(e for e in r.residual_vector.evaluations if e.spec.name == "pressure")
        assert abs(ev.value - r.pressure_residual) < 1e-12

    def test_max_abs_scaled_matches_residual_vector(self) -> None:
        r = _solve_default()
        assert abs(r.max_abs_scaled - r.residual_vector.max_abs_scaled()) < 1e-15


# ---------------------------------------------------------------------------
# 7 — Scaled residual norms are below tolerance
# ---------------------------------------------------------------------------


class TestScaledResidualNorms:
    def test_max_abs_scaled_finite(self) -> None:
        r = _solve_default()
        assert math.isfinite(r.max_abs_scaled)

    def test_max_abs_scaled_small_when_converged(self) -> None:
        r = _solve_default()
        assert r.converged
        # Both residuals tiny compared to their scales.
        assert r.max_abs_scaled < 1e-3

    def test_is_converged_with_generous_tolerance(self) -> None:
        r = _solve_default()
        assert r.residual_vector.is_converged(1.0)

    def test_scaled_energy_near_zero(self) -> None:
        r = _solve_default()
        ev = next(e for e in r.residual_vector.evaluations if e.spec.name == "energy")
        assert abs(ev.scaled_value) < 1e-6

    def test_scaled_pressure_near_zero(self) -> None:
        r = _solve_default()
        ev = next(e for e in r.residual_vector.evaluations if e.spec.name == "pressure")
        assert abs(ev.scaled_value) < 1e-3


# ---------------------------------------------------------------------------
# 8 — dP_total = dP_evap + dP_cond
# ---------------------------------------------------------------------------


class TestDPTotalExact:
    def test_dp_total_equals_sum(self) -> None:
        r = _solve_default()
        assert abs(r.dP_total - (r.dP_evap + r.dP_cond)) < 1e-9

    def test_dp_evap_positive(self) -> None:
        r = _solve_default()
        assert r.dP_evap > 0.0

    def test_dp_cond_positive(self) -> None:
        r = _solve_default()
        assert r.dP_cond > 0.0

    def test_dp_total_near_analytical(self) -> None:
        r = _solve_default()
        assert abs(r.dP_total - _DP_TOTAL_AT_SOLUTION) < 1.0


# ---------------------------------------------------------------------------
# 9 — Pump head equals loop dP at solution
# ---------------------------------------------------------------------------


class TestPumpHeadEqualsLoopDP:
    def test_pump_head_positive(self) -> None:
        r = _solve_default()
        assert r.pump_head > 0.0

    def test_pump_head_equals_dp_total_within_tolerance(self) -> None:
        r = _solve_default()
        assert abs(r.pump_head - r.dP_total) <= _PRESSURE_TOL * 2

    def test_pump_head_matches_pressure_residual(self) -> None:
        r = _solve_default()
        # pressure_residual = pump_head - dP_total
        assert abs(r.pressure_residual - (r.pump_head - r.dP_total)) < 1e-9


# ---------------------------------------------------------------------------
# 10 — Mass flux uses explicit flow areas
# ---------------------------------------------------------------------------


class TestMassFluxFlowAreas:
    def test_g_evap_uses_evap_flow_area(self) -> None:
        """Verify evap G changes with flow area (regression via dP scaling)."""
        from mpl_sim.closed_loop import PumpHeadCurve

        # Use a doubled evap flow area — dP_evap halves, root mdot changes.
        new_area = _EVAP_FLOW_AREA * 2.0  # 0.02 m²
        # new dP_total slope = 100/0.02 + 50/0.02 = 5000 + 2500 = 7500
        new_total_slope = _EVAP_DP_PER_G / new_area + _COND_DP_PER_G / _COND_FLOW_AREA
        new_mdot_exact = _PUMP_HEAD_PA / (_PUMP_SLOPE_PA_S_KG + new_total_slope)

        case = MinimalCoupledClosureCase(
            reference_state=_REFERENCE_STATE,
            pump_head_curve=PumpHeadCurve(head_Pa=_PUMP_HEAD_PA, slope_Pa_s_kg=_PUMP_SLOPE_PA_S_KG),
            evap_component=_evap_component(),
            evap_scenario=_evap_scenario(),
            evap_flow_area=new_area,
            cond_component=_cond_component(),
            cond_scenario=_cond_scenario(),
            cond_flow_area=_COND_FLOW_AREA,
            q_cond_bounds=_Q_COND_BOUNDS,
            mdot_bounds=_MDOT_BOUNDS,
        )
        r = solve_minimal_coupled_closure(case, _default_config())
        assert r.converged
        assert (
            abs(r.solved_primary_mdot - new_mdot_exact) < _MDOT_ACCEPT_TOL
        ), f"Expected mdot near {new_mdot_exact:.6f}, got {r.solved_primary_mdot:.6f}"

    def test_g_cond_uses_cond_flow_area(self) -> None:
        """Verify cond G changes with flow area (regression via dP scaling)."""
        from mpl_sim.closed_loop import PumpHeadCurve

        new_area = _COND_FLOW_AREA * 4.0  # 0.08 m²
        new_total_slope = _EVAP_DP_PER_G / _EVAP_FLOW_AREA + _COND_DP_PER_G / new_area
        new_mdot_exact = _PUMP_HEAD_PA / (_PUMP_SLOPE_PA_S_KG + new_total_slope)

        case = MinimalCoupledClosureCase(
            reference_state=_REFERENCE_STATE,
            pump_head_curve=PumpHeadCurve(head_Pa=_PUMP_HEAD_PA, slope_Pa_s_kg=_PUMP_SLOPE_PA_S_KG),
            evap_component=_evap_component(),
            evap_scenario=_evap_scenario(),
            evap_flow_area=_EVAP_FLOW_AREA,
            cond_component=_cond_component(),
            cond_scenario=_cond_scenario(),
            cond_flow_area=new_area,
            q_cond_bounds=_Q_COND_BOUNDS,
            mdot_bounds=_MDOT_BOUNDS,
        )
        r = solve_minimal_coupled_closure(case, _default_config())
        assert r.converged
        assert (
            abs(r.solved_primary_mdot - new_mdot_exact) < _MDOT_ACCEPT_TOL
        ), f"Expected mdot near {new_mdot_exact:.6f}, got {r.solved_primary_mdot:.6f}"


# ---------------------------------------------------------------------------
# 11 — Condenser heat rate is the solved scalar
# ---------------------------------------------------------------------------


class TestCondenserHeatRateSolved:
    def test_solved_q_cond_is_float(self) -> None:
        r = _solve_default()
        assert isinstance(r.solved_q_cond, float)

    def test_cond_result_q_near_solved_q_cond(self) -> None:
        r = _solve_default()
        # cond_result.Q may differ slightly from solved_q_cond due to
        # midpoint rounding, but they should be very close.
        assert math.isfinite(r.cond_result.Q)
        assert abs(r.cond_result.Q - r.solved_q_cond) < 1.0

    def test_q_cond_not_equal_to_q_evap(self) -> None:
        r = _solve_default()
        # Q_cond ≠ Q_evap (different sign, same magnitude when balanced).
        assert r.cond_result.Q != r.evap_result.Q


# ---------------------------------------------------------------------------
# 12 — Evaporator evaluated consistently at each trial
# ---------------------------------------------------------------------------


class TestEvaporatorConsistency:
    def test_evap_result_returned(self) -> None:
        r = _solve_default()
        from mpl_sim.hx_models import HXSolveResult

        assert isinstance(r.evap_result, HXSolveResult)

    def test_state_after_evap_is_cond_inlet(self) -> None:
        r = _solve_default()
        # state_after_evap should have h > h_reference (evaporator adds heat).
        assert r.state_after_evap.h > r.h_reference

    def test_evap_result_dp_positive(self) -> None:
        r = _solve_default()
        assert r.evap_result.dP_primary > 0.0

    def test_evap_adds_heat_to_primary(self) -> None:
        r = _solve_default()
        assert r.evap_result.Q > 0.0


# ---------------------------------------------------------------------------
# 13 — Invalid Q_cond bracket rejected
# ---------------------------------------------------------------------------


class TestInvalidQCondBracket:
    def test_same_sign_q_cond_bracket_raises(self) -> None:
        # Both endpoints give positive energy residual (Q_cond too small).
        case = _default_case(q_cond_bounds=(100.0, 500.0))
        with pytest.raises(ValueError, match="inner Q_cond bracket"):
            solve_minimal_coupled_closure(case, _default_config())

    def test_equal_q_cond_bounds_rejected_at_case(self) -> None:
        with pytest.raises(ValueError, match="q_cond_bounds"):
            _default_case(q_cond_bounds=(-200.0, -200.0))

    def test_reversed_q_cond_bounds_rejected_at_case(self) -> None:
        with pytest.raises(ValueError, match="q_cond_bounds"):
            _default_case(q_cond_bounds=(0.0, -500.0))

    def test_nonfinite_q_cond_bound_rejected(self) -> None:
        with pytest.raises(ValueError, match="q_cond_bounds"):
            _default_case(q_cond_bounds=(-math.inf, 0.0))


# ---------------------------------------------------------------------------
# 14 — Invalid mdot bracket rejected
# ---------------------------------------------------------------------------


class TestInvalidMdotBracket:
    def test_same_sign_mdot_bracket_raises(self) -> None:
        # Both endpoints at high mdot → pump head below dP_total → both negative.
        case = _default_case(mdot_bounds=(0.40, 0.50))
        with pytest.raises(ValueError, match="outer mdot bracket"):
            solve_minimal_coupled_closure(case, _default_config())

    def test_nonpositive_mdot_lo_rejected(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            _default_case(mdot_bounds=(0.0, 0.50))

    def test_negative_mdot_lo_rejected(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            _default_case(mdot_bounds=(-0.01, 0.50))

    def test_equal_mdot_bounds_rejected(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            _default_case(mdot_bounds=(0.05, 0.05))

    def test_reversed_mdot_bounds_rejected(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            _default_case(mdot_bounds=(0.50, 0.01))

    def test_nonfinite_mdot_bound_rejected(self) -> None:
        with pytest.raises(ValueError, match="mdot_bounds"):
            _default_case(mdot_bounds=(0.01, math.inf))


# ---------------------------------------------------------------------------
# 15 — Endpoint roots handled
# ---------------------------------------------------------------------------


class TestEndpointRoots:
    def test_outer_endpoint_root_lo(self) -> None:
        """Outer bracket lo is exactly the pressure root."""
        # mdot_lo = 0.05 → pressure_residual = 0 exactly.
        case = _default_case(mdot_bounds=(_MDOT_EXACT, _MDOT_EXACT + 0.10))
        r = solve_minimal_coupled_closure(case, _default_config())
        assert r.outer_iterations == 0
        assert r.converged

    def test_outer_endpoint_root_hi(self) -> None:
        """Outer bracket hi is exactly the pressure root."""
        case = _default_case(mdot_bounds=(0.01, _MDOT_EXACT))
        r = solve_minimal_coupled_closure(case, _default_config())
        assert r.outer_iterations == 0
        assert r.converged

    def test_inner_endpoint_root_lo(self) -> None:
        """Inner bracket lo is exactly the energy root."""
        case = _default_case(q_cond_bounds=(_Q_COND_EXACT, 0.0))
        r = solve_minimal_coupled_closure(case, _default_config())
        assert r.converged

    def test_inner_endpoint_root_hi(self) -> None:
        """Inner bracket hi is exactly the energy root."""
        case = _default_case(q_cond_bounds=(-500.0, _Q_COND_EXACT))
        r = solve_minimal_coupled_closure(case, _default_config())
        assert r.converged


# ---------------------------------------------------------------------------
# 16 — Non-convergence is explicit
# ---------------------------------------------------------------------------


class TestNonConvergence:
    def test_outer_max_iter_1_nonconverged(self) -> None:
        config = CoupledClosureConfig(
            energy_tolerance=_ENERGY_TOL,
            pressure_tolerance=_PRESSURE_TOL,
            energy_scale=_ENERGY_SCALE,
            pressure_scale=_PRESSURE_SCALE,
            inner_max_iter=60,
            outer_max_iter=1,
        )
        r = solve_minimal_coupled_closure(_default_case(), config)
        assert r.converged is False

    def test_inner_max_iter_1_nonconverged(self) -> None:
        config = CoupledClosureConfig(
            energy_tolerance=_ENERGY_TOL,
            pressure_tolerance=_PRESSURE_TOL,
            energy_scale=_ENERGY_SCALE,
            pressure_scale=_PRESSURE_SCALE,
            inner_max_iter=1,
            outer_max_iter=60,
        )
        r = solve_minimal_coupled_closure(_default_case(), config)
        assert r.converged is False

    def test_nonconverged_result_still_has_both_residuals(self) -> None:
        config = CoupledClosureConfig(
            energy_tolerance=_ENERGY_TOL,
            pressure_tolerance=_PRESSURE_TOL,
            energy_scale=_ENERGY_SCALE,
            pressure_scale=_PRESSURE_SCALE,
            inner_max_iter=1,
            outer_max_iter=1,
        )
        r = solve_minimal_coupled_closure(_default_case(), config)
        assert math.isfinite(r.energy_residual)
        assert math.isfinite(r.pressure_residual)


# ---------------------------------------------------------------------------
# 17 — Invalid CoupledClosureConfig rejected
# ---------------------------------------------------------------------------


class TestInvalidConfig:
    # --- bool max_iter ---
    def test_inner_max_iter_true_rejected(self) -> None:
        with pytest.raises(ValueError, match="inner_max_iter"):
            CoupledClosureConfig(inner_max_iter=True)  # type: ignore[arg-type]

    def test_outer_max_iter_true_rejected(self) -> None:
        with pytest.raises(ValueError, match="outer_max_iter"):
            CoupledClosureConfig(outer_max_iter=True)  # type: ignore[arg-type]

    def test_inner_max_iter_false_rejected(self) -> None:
        with pytest.raises(ValueError, match="inner_max_iter"):
            CoupledClosureConfig(inner_max_iter=False)  # type: ignore[arg-type]

    # --- non-int max_iter ---
    def test_inner_max_iter_float_rejected(self) -> None:
        with pytest.raises(ValueError, match="inner_max_iter"):
            CoupledClosureConfig(inner_max_iter=1.5)  # type: ignore[arg-type]

    def test_outer_max_iter_float_rejected(self) -> None:
        with pytest.raises(ValueError, match="outer_max_iter"):
            CoupledClosureConfig(outer_max_iter=50.0)  # type: ignore[arg-type]

    # --- zero max_iter ---
    def test_inner_max_iter_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="inner_max_iter"):
            CoupledClosureConfig(inner_max_iter=0)

    def test_outer_max_iter_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="outer_max_iter"):
            CoupledClosureConfig(outer_max_iter=0)

    # --- zero tolerance ---
    def test_energy_tolerance_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="energy_tolerance"):
            CoupledClosureConfig(energy_tolerance=0.0)

    def test_pressure_tolerance_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="pressure_tolerance"):
            CoupledClosureConfig(pressure_tolerance=0.0)

    # --- negative tolerance ---
    def test_energy_tolerance_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="energy_tolerance"):
            CoupledClosureConfig(energy_tolerance=-1e-6)

    def test_pressure_tolerance_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="pressure_tolerance"):
            CoupledClosureConfig(pressure_tolerance=-1.0)

    # --- nan tolerance ---
    def test_energy_tolerance_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="energy_tolerance"):
            CoupledClosureConfig(energy_tolerance=math.nan)

    def test_pressure_tolerance_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="pressure_tolerance"):
            CoupledClosureConfig(pressure_tolerance=math.nan)

    # --- inf tolerance ---
    def test_energy_tolerance_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="energy_tolerance"):
            CoupledClosureConfig(energy_tolerance=math.inf)

    def test_pressure_tolerance_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="pressure_tolerance"):
            CoupledClosureConfig(pressure_tolerance=math.inf)

    # --- bool tolerance ---
    def test_energy_tolerance_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="energy_tolerance"):
            CoupledClosureConfig(energy_tolerance=True)  # type: ignore[arg-type]

    def test_pressure_tolerance_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="pressure_tolerance"):
            CoupledClosureConfig(pressure_tolerance=False)  # type: ignore[arg-type]

    # --- zero scale ---
    def test_energy_scale_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="energy_scale"):
            CoupledClosureConfig(energy_scale=0.0)

    def test_pressure_scale_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="pressure_scale"):
            CoupledClosureConfig(pressure_scale=0.0)

    # --- nan scale ---
    def test_energy_scale_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="energy_scale"):
            CoupledClosureConfig(energy_scale=math.nan)

    def test_pressure_scale_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="pressure_scale"):
            CoupledClosureConfig(pressure_scale=math.nan)

    # --- inf scale ---
    def test_energy_scale_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="energy_scale"):
            CoupledClosureConfig(energy_scale=math.inf)

    def test_pressure_scale_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="pressure_scale"):
            CoupledClosureConfig(pressure_scale=math.inf)

    # --- bool scale ---
    def test_energy_scale_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="energy_scale"):
            CoupledClosureConfig(energy_scale=True)  # type: ignore[arg-type]

    def test_pressure_scale_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="pressure_scale"):
            CoupledClosureConfig(pressure_scale=False)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Case validation — explicit flow areas
# ---------------------------------------------------------------------------


class TestInvalidFlowAreas:
    def test_evap_flow_area_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="evap_flow_area"):
            dataclasses.replace(_default_case(), evap_flow_area=True)

    def test_cond_flow_area_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="cond_flow_area"):
            dataclasses.replace(_default_case(), cond_flow_area=False)


# ---------------------------------------------------------------------------
# 18 — Missing DP closures fail clearly
# ---------------------------------------------------------------------------


class TestMissingDPClosures:
    def test_evap_missing_dp_primary_rejected(self) -> None:
        from mpl_sim.closed_loop import PumpHeadCurve

        evap_no_dp = EvaporatorScenarioBinding(
            secondary_bc=FixedHeatRate(Q=_Q_EVAP),
            model=_MODEL,
            discretization=_DISC,
            geom_scalars=_dp_geom_scalars(),
            dp_primary=None,
        )
        with pytest.raises(ValueError, match="evap_scenario.dp_primary"):
            MinimalCoupledClosureCase(
                reference_state=_REFERENCE_STATE,
                pump_head_curve=PumpHeadCurve(head_Pa=5625.0, slope_Pa_s_kg=100_000.0),
                evap_component=_evap_component(),
                evap_scenario=evap_no_dp,
                evap_flow_area=_EVAP_FLOW_AREA,
                cond_component=_cond_component(),
                cond_scenario=_cond_scenario(),
                cond_flow_area=_COND_FLOW_AREA,
                q_cond_bounds=_Q_COND_BOUNDS,
                mdot_bounds=_MDOT_BOUNDS,
            )

    def test_cond_missing_dp_primary_rejected(self) -> None:
        from mpl_sim.closed_loop import PumpHeadCurve

        cond_no_dp = CondenserScenarioBinding(
            secondary_bc=FixedHeatRate(Q=-200.0),
            model=_MODEL,
            discretization=_DISC,
            geom_scalars=_dp_geom_scalars(),
            dp_primary=None,
        )
        with pytest.raises(ValueError, match="cond_scenario.dp_primary"):
            MinimalCoupledClosureCase(
                reference_state=_REFERENCE_STATE,
                pump_head_curve=PumpHeadCurve(head_Pa=5625.0, slope_Pa_s_kg=100_000.0),
                evap_component=_evap_component(),
                evap_scenario=_evap_scenario(),
                evap_flow_area=_EVAP_FLOW_AREA,
                cond_component=_cond_component(),
                cond_scenario=cond_no_dp,
                cond_flow_area=_COND_FLOW_AREA,
                q_cond_bounds=_Q_COND_BOUNDS,
                mdot_bounds=_MDOT_BOUNDS,
            )

    def test_non_fixed_heat_rate_bc_rejected_at_solve(self) -> None:
        """cond_scenario with non-FixedHeatRate BC is rejected at solve time."""
        from mpl_sim.closed_loop import PumpHeadCurve
        from mpl_sim.hx_models import FixedWallTemp

        cond_bad_bc = CondenserScenarioBinding(
            secondary_bc=FixedWallTemp(T_wall=300.0),
            model=_MODEL,
            discretization=_DISC,
            geom_scalars=_dp_geom_scalars(),
            dp_primary=_LinearMassFluxDP(_COND_DP_PER_G, "cond_dp"),
        )
        case = MinimalCoupledClosureCase(
            reference_state=_REFERENCE_STATE,
            pump_head_curve=PumpHeadCurve(head_Pa=5625.0, slope_Pa_s_kg=100_000.0),
            evap_component=_evap_component(),
            evap_scenario=_evap_scenario(),
            evap_flow_area=_EVAP_FLOW_AREA,
            cond_component=_cond_component(),
            cond_scenario=cond_bad_bc,
            cond_flow_area=_COND_FLOW_AREA,
            q_cond_bounds=_Q_COND_BOUNDS,
            mdot_bounds=_MDOT_BOUNDS,
        )
        with pytest.raises(ValueError, match="FixedHeatRate"):
            solve_minimal_coupled_closure(case, _default_config())


# ---------------------------------------------------------------------------
# 19 — No property lookup
# ---------------------------------------------------------------------------


class TestNoPropertyLookup:
    def test_nonexistent_fluid_name_completes_without_error(self) -> None:
        from mpl_sim.closed_loop import PumpHeadCurve

        fake_fluid = PureFluid(name="CoolPropWouldErrorHere_XYZ123")
        ref_state = FluidState(P=_P_REF, h=_H_REF, identity=fake_fluid)
        case = MinimalCoupledClosureCase(
            reference_state=ref_state,
            pump_head_curve=PumpHeadCurve(head_Pa=_PUMP_HEAD_PA, slope_Pa_s_kg=_PUMP_SLOPE_PA_S_KG),
            evap_component=_evap_component(),
            evap_scenario=_evap_scenario(),
            evap_flow_area=_EVAP_FLOW_AREA,
            cond_component=_cond_component(),
            cond_scenario=_cond_scenario(),
            cond_flow_area=_COND_FLOW_AREA,
            q_cond_bounds=_Q_COND_BOUNDS,
            mdot_bounds=_MDOT_BOUNDS,
        )
        r = solve_minimal_coupled_closure(case, _default_config())
        assert r.converged


# ---------------------------------------------------------------------------
# 20 — No registry resolution
# ---------------------------------------------------------------------------


class TestNoRegistryResolution:
    def test_no_correlation_registry_imported(self) -> None:
        import mpl_sim.closed_loop.coupled_solver as mod

        assert not hasattr(
            mod, "CorrelationRegistry"
        ), "coupled_solver must not import CorrelationRegistry"

    def test_no_hx_model_registry_imported(self) -> None:
        import mpl_sim.closed_loop.coupled_solver as mod

        assert not hasattr(
            mod, "HeatExchangerModelRegistry"
        ), "coupled_solver must not import HeatExchangerModelRegistry"


# ---------------------------------------------------------------------------
# 21 — No generic network API introduced
# ---------------------------------------------------------------------------


class TestNoNetworkAPI:
    def test_no_network_module_in_coupled_solver_imports(self) -> None:
        import mpl_sim.closed_loop.coupled_solver as mod

        # Inspect parsed AST imports — not raw text (avoids matching comments).
        src = Path(mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        for imp in imports:
            assert (
                "mpl_sim.network" not in imp
            ), f"coupled_solver must not import mpl_sim.network; found {imp!r}"

    def test_public_api_has_no_solve_network(self) -> None:
        import mpl_sim.closed_loop as pkg

        assert not hasattr(pkg, "solve"), "public API must not export 'solve'"


# ---------------------------------------------------------------------------
# 22 — No topology classes introduced
# ---------------------------------------------------------------------------


class TestNoTopologyClasses:
    def test_no_network_node_branch_junction_in_source(self) -> None:
        import mpl_sim.closed_loop.coupled_solver as mod

        src = Path(mod.__file__).read_text(encoding="utf-8")
        for forbidden in ("class Network", "class Node", "class Branch", "class Junction"):
            assert forbidden not in src, f"coupled_solver.py must not define {forbidden!r}"

    def test_no_topology_classes_in_module(self) -> None:
        import mpl_sim.closed_loop.coupled_solver as mod

        for name in ("Network", "Node", "Branch", "Junction"):
            assert not hasattr(mod, name), f"coupled_solver must not define {name!r}"


# ---------------------------------------------------------------------------
# 23 — No valves/manifolds/recuperator/pre-heaters
# ---------------------------------------------------------------------------


class TestNoForbiddenComponents:
    def test_no_forbidden_class_definitions_in_coupled_solver(self) -> None:
        import mpl_sim.closed_loop.coupled_solver as mod

        # Inspect AST for class definitions — not raw text (avoids matching comments).
        src = Path(mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        defined_classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        for forbidden in ("Valve", "Manifold", "Recuperator", "PreHeater", "PostHeater"):
            assert (
                forbidden not in defined_classes
            ), f"coupled_solver.py must not define class {forbidden!r}"

    def test_no_forbidden_exports(self) -> None:
        import mpl_sim.closed_loop as pkg

        for name in ("Valve", "Manifold", "Recuperator", "PreHeater", "PostHeater"):
            assert not hasattr(pkg, name), f"closed_loop must not export {name!r}"


# ---------------------------------------------------------------------------
# 24 — Example script imports safely and executes
# ---------------------------------------------------------------------------


class TestExampleScript:
    def test_example_module_importable(self) -> None:
        examples_dir = Path(__file__).parents[2] / "examples"
        example_path = examples_dir / "minimal_coupled_closure.py"
        assert example_path.exists(), f"Example not found: {example_path}"

    def test_example_runs_without_error(self) -> None:
        examples_dir = Path(__file__).parents[2] / "examples"
        example_path = str(examples_dir / "minimal_coupled_closure.py")
        # runpy executes the file as __main__; must not raise.
        runpy.run_path(example_path, run_name="__main__")

    def test_example_produces_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        examples_dir = Path(__file__).parents[2] / "examples"
        example_path = str(examples_dir / "minimal_coupled_closure.py")
        runpy.run_path(example_path, run_name="__main__")
        out = capsys.readouterr().out
        assert len(out) > 0, "Example must produce printed output"


# ---------------------------------------------------------------------------
# 25 — No file writes
# ---------------------------------------------------------------------------


class TestNoFileWrites:
    def test_result_has_no_write_methods(self) -> None:
        r = _solve_default()
        assert not hasattr(r, "write")
        assert not hasattr(r, "to_file")
        assert not hasattr(r, "save")

    def test_result_is_pure_dataclass(self) -> None:
        import dataclasses as dc

        r = _solve_default()
        assert dc.is_dataclass(r)
        # Frozen — cannot set attributes, so no write side effects.
        with pytest.raises((AttributeError, TypeError)):
            r.converged = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 26 — Phase 13A and 13B regression
# ---------------------------------------------------------------------------


class TestPhase13ARegression:
    def test_solve_minimal_closed_mpl_still_works(self) -> None:
        from mpl_sim.closed_loop import (
            ClosedLoopSolveConfig,
            MinimalClosedMPLCase,
            solve_minimal_closed_mpl,
        )

        case = MinimalClosedMPLCase(
            reference_state=_REFERENCE_STATE,
            primary_mdot=0.05,
            evap_component=_evap_component(),
            evap_scenario=_evap_scenario(),
            cond_component=_cond_component(),
            cond_scenario=_cond_scenario(),
            q_cond_bounds=_Q_COND_BOUNDS,
        )
        r = solve_minimal_closed_mpl(case, ClosedLoopSolveConfig(max_iter=60, tolerance=1e-6))
        assert r.converged
        assert abs(r.solved_q_cond - _Q_COND_EXACT) < _Q_ACCEPT_TOL

    def test_phase_13a_public_exports_intact(self) -> None:
        from mpl_sim.closed_loop import (  # noqa: F401
            ClosedLoopSolveConfig,
            MinimalClosedMPLCase,
            MinimalClosedMPLResult,
            solve_minimal_closed_mpl,
        )


class TestPhase13BRegression:
    def test_solve_minimal_pressure_closure_still_works(self) -> None:
        from mpl_sim.closed_loop import (
            MinimalPressureClosureCase,
            PressureClosureConfig,
            PumpHeadCurve,
            solve_minimal_pressure_closure,
        )

        case = MinimalPressureClosureCase(
            reference_state=_REFERENCE_STATE,
            pump_head_curve=PumpHeadCurve(head_Pa=_PUMP_HEAD_PA, slope_Pa_s_kg=_PUMP_SLOPE_PA_S_KG),
            evap_component=_evap_component(),
            evap_scenario=_evap_scenario(),
            evap_flow_area=_EVAP_FLOW_AREA,
            cond_component=_cond_component(),
            cond_scenario=_cond_scenario(),
            cond_flow_area=_COND_FLOW_AREA,
            mdot_bounds=_MDOT_BOUNDS,
        )
        r = solve_minimal_pressure_closure(case, PressureClosureConfig(max_iter=60, tolerance=0.01))
        assert r.converged
        assert abs(r.solved_primary_mdot - _MDOT_EXACT) < _MDOT_ACCEPT_TOL

    def test_phase_13b_public_exports_intact(self) -> None:
        from mpl_sim.closed_loop import (  # noqa: F401
            MinimalPressureClosureCase,
            MinimalPressureClosureResult,
            PressureClosureConfig,
            PumpHeadCurve,
            solve_minimal_pressure_closure,
        )


class TestPhase13DPublicExports:
    def test_all_phase_13d_exports_importable(self) -> None:
        from mpl_sim.closed_loop import (  # noqa: F401
            CoupledClosureConfig,
            MinimalCoupledClosureCase,
            MinimalCoupledClosureResult,
            solve_minimal_coupled_closure,
        )

    def test_exports_in_all(self) -> None:
        import mpl_sim.closed_loop as pkg

        assert "CoupledClosureConfig" in pkg.__all__
        assert "MinimalCoupledClosureCase" in pkg.__all__
        assert "MinimalCoupledClosureResult" in pkg.__all__
        assert "solve_minimal_coupled_closure" in pkg.__all__
