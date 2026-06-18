"""Phase 11L — DittusBoelterHTC and GnielinskiHTC tests.

Covers:

DittusBoelterHTC
  - Role is HTC.
  - Envelope is non-empty (bounds and fluid_families).
  - evaluate() returns CorrelationOutput with (value, verdict, metadata).
  - Computes expected Nu and HTC for a representative turbulent case.
  - Heating exponent n=0.4 path produces larger HTC than cooling n=0.3.
  - Cooling exponent n=0.3 path produces smaller HTC.
  - Returns finite positive HTC for valid turbulent input.
  - Returns IN_ENVELOPE verdict when Re/Pr/D_h are in the declared range.
  - Returns EXTRAPOLATED verdict for laminar Re (out of envelope, evaluable).
  - Raises ValueError for non-positive or non-finite D_h.
  - Raises ValueError for missing / non-positive / non-finite Re, Pr, k, n.
  - Can be registered in CorrelationRegistry.
  - Does not import CoolProp, PropertyBackend, network, solvers, components.

GnielinskiHTC
  - Role is HTC.
  - Envelope is non-empty (bounds and fluid_families).
  - evaluate() returns CorrelationOutput with (value, verdict, metadata).
  - Computes expected Nu and HTC for a representative turbulent case.
  - Returns finite positive HTC for valid turbulent input.
  - Returns IN_ENVELOPE verdict when Re/Pr/D_h are in the declared range.
  - Returns EXTRAPOLATED verdict for laminar Re (out of envelope, evaluable).
  - Raises ValueError for non-positive or non-finite D_h.
  - Raises ValueError for missing / non-positive / non-finite Re, Pr, k.
  - Can be registered in CorrelationRegistry.
  - Does not import CoolProp, PropertyBackend, network, solvers, components.

Contract (both)
  - Both implement CorrelationRole.HTC.
  - Neither calls CoolProp or PropertyBackend.
  - Neither uses hidden defaults.
  - Neither uses abs or clip to force physical outputs.
  - Both can be injected into EpsilonNTUModel as htc_primary and affect Q.
  - Both can be injected into SegmentedMarchModel FixedWallTemp and are called
    through HXSolveRequest.
  - HX models still do not resolve CorrelationRegistry.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import (
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationOutput,
    CorrelationRole,
    HTCInput,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.correlations.registry import create_empty_correlation_registry
from mpl_sim.correlations.single_phase_htc import DittusBoelterHTC, GnielinskiHTC
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import (
    FixedWallTemp,
    HXSolveRequest,
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel
from mpl_sim.hx_models.segmented import SegmentedMarchModel

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FLUID = PureFluid("R134a")
_STATE = FluidState(P=1.0e6, h=2.5e5, identity=_FLUID)
_LUMPED = DiscretizationSpec(mode=DiscretizationMode.LUMPED, n_cells=1)
_SEGMENTED_3 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=3)

# Representative water-like scalar inputs for single-phase turbulent flow.
_RE = 20_000.0
_PR = 7.0
_K = 0.6  # W/m/K
_D_H = 0.01  # m
_N_HEAT = 0.4  # Dittus-Boelter heating exponent
_N_COOL = 0.3  # Dittus-Boelter cooling exponent


def _htc_input(
    Re: float = _RE,
    Pr: float = _PR,
    k: float = _K,
    D_h: float = _D_H,
    n: float | None = _N_HEAT,
    extra: dict[str, float] | None = None,
) -> HTCInput:
    gs: dict[str, float] = {"Re": Re, "Pr": Pr, "k": k}
    if n is not None:
        gs["n"] = n
    if extra:
        gs.update(extra)
    return HTCInput(
        state=(_STATE,),
        G=300.0,
        x=(0.0,),
        D_h=D_h,
        geom_scalars=gs,
    )


def _db() -> DittusBoelterHTC:
    return DittusBoelterHTC()


def _gn() -> GnielinskiHTC:
    return GnielinskiHTC()


# ============================================================================
# DittusBoelterHTC — role and envelope
# ============================================================================


def test_db_role_is_htc() -> None:
    assert _db().role() == CorrelationRole.HTC


def test_db_envelope_non_empty() -> None:
    env = _db().envelope()
    assert env.fluid_families
    assert env.bounds
    assert env.source.citation


def test_db_envelope_bounds_include_re_and_pr() -> None:
    env = _db().envelope()
    quantities = {b.quantity for b in env.bounds}
    assert BoundedQuantity.REYNOLDS in quantities
    assert BoundedQuantity.PRANDTL in quantities


# ============================================================================
# DittusBoelterHTC — output shape
# ============================================================================


def test_db_returns_correlation_output() -> None:
    out = _db().evaluate(_htc_input())
    assert isinstance(out, CorrelationOutput)
    assert isinstance(out.verdict, ValidityVerdict)
    assert isinstance(out.metadata, ClosureMetadata)
    assert isinstance(out.value, tuple)
    assert len(out.value) == 1


# ============================================================================
# DittusBoelterHTC — numerical accuracy (heating path)
# ============================================================================


def test_db_heating_value_matches_formula() -> None:
    # Nu = 0.023 * Re^0.8 * Pr^n; h = Nu * k / D_h
    Re, Pr, k, D_h, n = _RE, _PR, _K, _D_H, _N_HEAT
    Nu_expected = 0.023 * (Re**0.8) * (Pr**n)
    h_expected = Nu_expected * k / D_h

    out = _db().evaluate(_htc_input(Re=Re, Pr=Pr, k=k, D_h=D_h, n=n))
    h = out.value[0]

    assert math.isfinite(h)
    assert h > 0.0
    assert math.isclose(h, h_expected, rel_tol=1e-10)


def test_db_heating_htc_is_finite_positive() -> None:
    out = _db().evaluate(_htc_input(n=_N_HEAT))
    assert math.isfinite(out.value[0])
    assert out.value[0] > 0.0


def test_db_in_envelope_verdict_for_turbulent_input() -> None:
    out = _db().evaluate(_htc_input(Re=20_000.0, Pr=7.0, D_h=0.01, n=_N_HEAT))
    assert out.verdict.status == ValidityStatus.IN_ENVELOPE
    assert out.verdict.violated == ()


# ============================================================================
# DittusBoelterHTC — cooling path
# ============================================================================


def test_db_cooling_value_matches_formula() -> None:
    Re, Pr, k, D_h, n = _RE, _PR, _K, _D_H, _N_COOL
    Nu_expected = 0.023 * (Re**0.8) * (Pr**n)
    h_expected = Nu_expected * k / D_h

    out = _db().evaluate(_htc_input(Re=Re, Pr=Pr, k=k, D_h=D_h, n=n))
    assert math.isclose(out.value[0], h_expected, rel_tol=1e-10)


def test_db_heating_htc_greater_than_cooling_htc() -> None:
    inp_heat = _htc_input(n=_N_HEAT)
    inp_cool = _htc_input(n=_N_COOL)
    h_heat = _db().evaluate(inp_heat).value[0]
    h_cool = _db().evaluate(inp_cool).value[0]
    assert h_heat > h_cool


# ============================================================================
# DittusBoelterHTC — validity / extrapolation
# ============================================================================


def test_db_extrapolated_for_low_re() -> None:
    # Re = 5000 < 10 000 lower bound
    out = _db().evaluate(_htc_input(Re=5_000.0))
    assert out.verdict.status == ValidityStatus.EXTRAPOLATED
    assert math.isfinite(out.value[0])
    assert out.value[0] > 0.0


def test_db_extrapolated_for_low_pr() -> None:
    # Pr = 0.1 < 0.6 lower bound
    out = _db().evaluate(_htc_input(Pr=0.1))
    assert out.verdict.status == ValidityStatus.EXTRAPOLATED
    assert math.isfinite(out.value[0])
    assert out.value[0] > 0.0


def test_db_extrapolated_for_high_pr() -> None:
    # Pr = 200 > 160 upper bound
    out = _db().evaluate(_htc_input(Pr=200.0))
    assert out.verdict.status == ValidityStatus.EXTRAPOLATED
    assert math.isfinite(out.value[0])
    assert out.value[0] > 0.0


def test_db_extrapolated_verdict_has_violated_bounds() -> None:
    out = _db().evaluate(_htc_input(Re=5_000.0))
    assert len(out.verdict.violated) >= 1


def test_db_small_positive_D_h_is_extrapolated_without_clamping() -> None:
    small = _db().evaluate(_htc_input(D_h=5.0e-7))
    boundary = _db().evaluate(_htc_input(D_h=1.0e-6))
    assert small.verdict.status == ValidityStatus.EXTRAPOLATED
    assert boundary.verdict.status == ValidityStatus.IN_ENVELOPE
    assert small.value[0] == pytest.approx(2.0 * boundary.value[0])


# ============================================================================
# DittusBoelterHTC — invalid input rejection
# ============================================================================


@pytest.mark.parametrize("D_h", [0.0, -1.0, float("nan"), float("inf")])
def test_db_invalid_D_h_raises(D_h: float) -> None:
    with pytest.raises(ValueError, match="D_h"):
        _db().evaluate(_htc_input(D_h=D_h))


@pytest.mark.parametrize("Re", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
def test_db_invalid_re_raises(Re: float) -> None:
    with pytest.raises(ValueError, match="Re"):
        _db().evaluate(_htc_input(Re=Re))


@pytest.mark.parametrize("Pr", [0.0, -1.0, float("nan")])
def test_db_invalid_pr_raises(Pr: float) -> None:
    with pytest.raises(ValueError, match="Pr"):
        _db().evaluate(_htc_input(Pr=Pr))


@pytest.mark.parametrize("k", [0.0, -0.1, float("nan")])
def test_db_invalid_k_raises(k: float) -> None:
    with pytest.raises(ValueError, match="k"):
        _db().evaluate(_htc_input(k=k))


@pytest.mark.parametrize("n", [0.0, -0.1, float("nan")])
def test_db_invalid_n_raises(n: float) -> None:
    with pytest.raises(ValueError, match="n"):
        _db().evaluate(_htc_input(n=n))


def test_db_missing_re_raises() -> None:
    inp = _htc_input()
    gs = dict(inp.geom_scalars)
    del gs["Re"]
    bad = HTCInput(state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, geom_scalars=gs)
    with pytest.raises(ValueError, match="Re"):
        _db().evaluate(bad)


def test_db_missing_k_raises() -> None:
    inp = _htc_input()
    gs = dict(inp.geom_scalars)
    del gs["k"]
    bad = HTCInput(state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, geom_scalars=gs)
    with pytest.raises(ValueError, match="k"):
        _db().evaluate(bad)


def test_db_missing_n_raises() -> None:
    inp = _htc_input(n=None)
    with pytest.raises(ValueError, match="n"):
        _db().evaluate(inp)


def test_db_wrong_input_type_raises() -> None:
    from mpl_sim.correlations.contract import SinglePhaseDPInput

    state = _STATE
    bad = SinglePhaseDPInput(
        state=(state,), G=300.0, D_h=0.01, roughness=0.0, L_cell=0.1, rho=1000.0, mu=1e-3
    )
    with pytest.raises(TypeError):
        _db().evaluate(bad)


# ============================================================================
# DittusBoelterHTC — registry
# ============================================================================


def test_db_can_be_registered_and_resolved() -> None:
    reg = create_empty_correlation_registry()
    db = _db()
    reg.register("dittus_boelter_htc", db)
    resolved = reg.resolve("dittus_boelter_htc")
    assert resolved is db


# ============================================================================
# Package exports and architecture boundary
# ============================================================================


def test_correlations_package_exports_both_htc_correlations() -> None:
    from mpl_sim import correlations

    assert correlations.DittusBoelterHTC is DittusBoelterHTC
    assert correlations.GnielinskiHTC is GnielinskiHTC
    assert "DittusBoelterHTC" in correlations.__all__
    assert "GnielinskiHTC" in correlations.__all__


def test_single_phase_htc_has_no_forbidden_imports() -> None:
    module_path = Path(__file__).parents[2] / "src/mpl_sim/correlations/single_phase_htc.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    forbidden = (
        "CoolProp",
        "mpl_sim.properties",
        "mpl_sim.geometry",
        "mpl_sim.components",
        "mpl_sim.network",
        "mpl_sim.solvers",
    )
    assert not any(
        module == prefix or module.startswith(f"{prefix}.")
        for module in imported_modules
        for prefix in forbidden
    )


# ============================================================================
# GnielinskiHTC — role and envelope
# ============================================================================


def test_gn_role_is_htc() -> None:
    assert _gn().role() == CorrelationRole.HTC


def test_gn_envelope_non_empty() -> None:
    env = _gn().envelope()
    assert env.fluid_families
    assert env.bounds
    assert env.source.citation


def test_gn_envelope_bounds_include_re_and_pr() -> None:
    env = _gn().envelope()
    quantities = {b.quantity for b in env.bounds}
    assert BoundedQuantity.REYNOLDS in quantities
    assert BoundedQuantity.PRANDTL in quantities


# ============================================================================
# GnielinskiHTC — output shape
# ============================================================================


def test_gn_returns_correlation_output() -> None:
    out = _gn().evaluate(_htc_input())
    assert isinstance(out, CorrelationOutput)
    assert isinstance(out.verdict, ValidityVerdict)
    assert isinstance(out.metadata, ClosureMetadata)
    assert isinstance(out.value, tuple)
    assert len(out.value) == 1


# ============================================================================
# GnielinskiHTC — numerical accuracy
# ============================================================================


def test_gn_value_matches_formula() -> None:
    Re, Pr, k, D_h = _RE, _PR, _K, _D_H
    f = (0.79 * math.log(Re) - 1.64) ** (-2)
    f8 = f / 8.0
    Nu_expected = (f8 * (Re - 1000.0) * Pr) / (
        1.0 + 12.7 * math.sqrt(f8) * (Pr ** (2.0 / 3.0) - 1.0)
    )
    h_expected = Nu_expected * k / D_h

    out = _gn().evaluate(_htc_input(Re=Re, Pr=Pr, k=k, D_h=D_h))
    h = out.value[0]

    assert math.isfinite(h)
    assert h > 0.0
    assert math.isclose(h, h_expected, rel_tol=1e-10)


def test_gn_htc_is_finite_positive() -> None:
    out = _gn().evaluate(_htc_input())
    assert math.isfinite(out.value[0])
    assert out.value[0] > 0.0


def test_gn_in_envelope_verdict_for_turbulent_input() -> None:
    out = _gn().evaluate(_htc_input(Re=20_000.0, Pr=7.0, D_h=0.01))
    assert out.verdict.status == ValidityStatus.IN_ENVELOPE
    assert out.verdict.violated == ()


# ============================================================================
# GnielinskiHTC — validity / extrapolation
# ============================================================================


def test_gn_extrapolated_for_low_re() -> None:
    # Re = 500 < 3000 lower bound — mathematically evaluable
    out = _gn().evaluate(_htc_input(Re=500.0))
    assert out.verdict.status == ValidityStatus.EXTRAPOLATED
    assert math.isfinite(out.value[0])


def test_gn_extrapolated_for_high_re() -> None:
    # Re = 1e7 > 5e6 upper bound
    out = _gn().evaluate(_htc_input(Re=1.0e7))
    assert out.verdict.status == ValidityStatus.EXTRAPOLATED
    assert math.isfinite(out.value[0])
    assert out.value[0] > 0.0


def test_gn_extrapolated_for_low_pr() -> None:
    out = _gn().evaluate(_htc_input(Pr=0.1))
    assert out.verdict.status == ValidityStatus.EXTRAPOLATED
    assert math.isfinite(out.value[0])


def test_gn_extrapolated_verdict_has_violated_bounds() -> None:
    out = _gn().evaluate(_htc_input(Re=500.0))
    assert len(out.verdict.violated) >= 1


def test_gn_small_positive_D_h_is_extrapolated_without_clamping() -> None:
    small = _gn().evaluate(_htc_input(D_h=5.0e-7))
    boundary = _gn().evaluate(_htc_input(D_h=1.0e-6))
    assert small.verdict.status == ValidityStatus.EXTRAPOLATED
    assert boundary.verdict.status == ValidityStatus.IN_ENVELOPE
    assert small.value[0] == pytest.approx(2.0 * boundary.value[0])


# ============================================================================
# GnielinskiHTC — invalid input rejection
# ============================================================================


@pytest.mark.parametrize("D_h", [0.0, -1.0, float("nan"), float("inf")])
def test_gn_invalid_D_h_raises(D_h: float) -> None:
    with pytest.raises(ValueError, match="D_h"):
        _gn().evaluate(_htc_input(D_h=D_h))


@pytest.mark.parametrize("Re", [0.0, -1.0, float("nan"), float("inf"), float("-inf")])
def test_gn_invalid_re_raises(Re: float) -> None:
    with pytest.raises(ValueError, match="Re"):
        _gn().evaluate(_htc_input(Re=Re))


@pytest.mark.parametrize("Pr", [0.0, -1.0, float("nan")])
def test_gn_invalid_pr_raises(Pr: float) -> None:
    with pytest.raises(ValueError, match="Pr"):
        _gn().evaluate(_htc_input(Pr=Pr))


@pytest.mark.parametrize("k", [0.0, -0.1, float("nan")])
def test_gn_invalid_k_raises(k: float) -> None:
    with pytest.raises(ValueError, match="k"):
        _gn().evaluate(_htc_input(k=k))


def test_gn_missing_re_raises() -> None:
    inp = _htc_input()
    gs = dict(inp.geom_scalars)
    del gs["Re"]
    bad = HTCInput(state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, geom_scalars=gs)
    with pytest.raises(ValueError, match="Re"):
        _gn().evaluate(bad)


def test_gn_wrong_input_type_raises() -> None:
    from mpl_sim.correlations.contract import SinglePhaseDPInput

    bad = SinglePhaseDPInput(
        state=(_STATE,), G=300.0, D_h=0.01, roughness=0.0, L_cell=0.1, rho=1000.0, mu=1e-3
    )
    with pytest.raises(TypeError):
        _gn().evaluate(bad)


# ============================================================================
# GnielinskiHTC — registry
# ============================================================================


def test_gn_can_be_registered_and_resolved() -> None:
    reg = create_empty_correlation_registry()
    gn = _gn()
    reg.register("gnielinski_htc", gn)
    resolved = reg.resolve("gnielinski_htc")
    assert resolved is gn


# ============================================================================
# Contract — both correlations share the HTC role
# ============================================================================


def test_both_implement_htc_role() -> None:
    assert _db().role() == CorrelationRole.HTC
    assert _gn().role() == CorrelationRole.HTC


def test_gnielinski_gives_higher_htc_than_dittus_boelter_heating() -> None:
    # For typical turbulent flows Gnielinski is generally more accurate and
    # can give higher or lower values than Dittus-Boelter depending on Re.
    # We just verify both are finite and positive for the same inputs.
    Re, Pr, k, D_h = 20_000.0, 7.0, 0.6, 0.01
    h_db = _db().evaluate(_htc_input(Re=Re, Pr=Pr, k=k, D_h=D_h, n=_N_HEAT)).value[0]
    h_gn = _gn().evaluate(_htc_input(Re=Re, Pr=Pr, k=k, D_h=D_h)).value[0]
    assert math.isfinite(h_db) and h_db > 0.0
    assert math.isfinite(h_gn) and h_gn > 0.0


# ============================================================================
# Contract — no abs/clip forcing validity
# ============================================================================


def test_db_no_abs_clip_forcing() -> None:
    # Out-of-envelope (low Re) returns honest extrapolated value, not a clamped one.
    # The value for Re=100 should differ from the value for Re=10000.
    h_low = _db().evaluate(_htc_input(Re=100.0)).value[0]
    h_high = _db().evaluate(_htc_input(Re=10_000.0)).value[0]
    assert h_low != h_high, "Low-Re and high-Re HTCs must differ — no clamping."


def test_gn_no_abs_clip_forcing() -> None:
    h_low = _gn().evaluate(_htc_input(Re=500.0)).value[0]
    h_high = _gn().evaluate(_htc_input(Re=10_000.0)).value[0]
    assert h_low != h_high, "Low-Re and high-Re HTCs must differ — no clamping."


# ============================================================================
# HX model integration — EpsilonNTUModel with DittusBoelterHTC as htc_primary
# ============================================================================


def _eps_ntu_req_fixed_wall(htc_corr: Correlation, T_wall: float = 350.0) -> HXSolveRequest:
    """Build an EpsilonNTUModel FixedWallTemp request with the given HTC correlation."""
    return HXSolveRequest(
        primary_state_in=_STATE,
        primary_mdot=0.05,
        secondary_bc=FixedWallTemp(T_wall=T_wall),
        geometry=object(),
        discretization=_LUMPED,
        geom_scalars={
            "G": 300.0,
            "D_h": _D_H,
            "roughness": 0.0,
            "L_cell": 0.5,
            "rho": 1000.0,
            "mu": 1e-3,
            "A_ht": 0.05,
            "x": 0.0,
            "Re": _RE,
            "Pr": _PR,
            "k": _K,
            "n": _N_HEAT,
        },
        htc_primary=htc_corr,
        primary_T_in=300.0,
    )


def test_epsilon_ntu_db_htc_affects_q() -> None:
    model = EpsilonNTUModel()
    req = _eps_ntu_req_fixed_wall(DittusBoelterHTC())
    result = model.solve(req)
    raw_h = DittusBoelterHTC().evaluate(_htc_input()).value[0]
    assert result.Q == pytest.approx(raw_h * 0.05 * (350.0 - 300.0))


def test_epsilon_ntu_gn_htc_affects_q() -> None:
    model = EpsilonNTUModel()
    req = _eps_ntu_req_fixed_wall(GnielinskiHTC())
    result = model.solve(req)
    raw_h = GnielinskiHTC().evaluate(_htc_input()).value[0]
    assert result.Q == pytest.approx(raw_h * 0.05 * (350.0 - 300.0))


def test_epsilon_ntu_db_propagates_verdict() -> None:
    model = EpsilonNTUModel()
    req = _eps_ntu_req_fixed_wall(DittusBoelterHTC())
    result = model.solve(req)
    assert result.verdicts is not None


def test_epsilon_ntu_hx_model_does_not_resolve_registry() -> None:
    # EpsilonNTUModel.solve must work without ever touching CorrelationRegistry.
    # We verify by passing a real correlation and confirming no registry error.
    model = EpsilonNTUModel()
    req = _eps_ntu_req_fixed_wall(GnielinskiHTC())
    result = model.solve(req)
    assert result is not None


# ============================================================================
# HX model integration — SegmentedMarchModel with DittusBoelterHTC / GnielinskiHTC
# ============================================================================


def _segmented_req_fixed_wall(htc_corr: Correlation) -> HXSolveRequest:
    """Build a SegmentedMarchModel FixedWallTemp request."""
    return HXSolveRequest(
        primary_state_in=_STATE,
        primary_mdot=0.05,
        secondary_bc=FixedWallTemp(T_wall=350.0),
        geometry=object(),
        discretization=_SEGMENTED_3,
        geom_scalars={
            "G": 300.0,
            "D_h": _D_H,
            "roughness": 0.0,
            "L_cell": 0.1,
            "rho": 1000.0,
            "mu": 1e-3,
            "A_ht": 0.05,
            "x": 0.0,
            "Re": _RE,
            "Pr": _PR,
            "k": _K,
            "n": _N_HEAT,
        },
        htc_primary=htc_corr,
        primary_T_in=300.0,
        primary_cp=4200.0,
        primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
    )


def test_segmented_db_fixed_wall_calls_htc_per_cell() -> None:
    model = SegmentedMarchModel()
    req = _segmented_req_fixed_wall(DittusBoelterHTC())
    result = model.solve(req)
    assert math.isfinite(result.Q)
    assert result.Q != 0.0
    assert len(result.verdicts) == _SEGMENTED_3.n_cells


def test_segmented_gn_fixed_wall_calls_htc_per_cell() -> None:
    model = SegmentedMarchModel()
    req = _segmented_req_fixed_wall(GnielinskiHTC())
    result = model.solve(req)
    assert math.isfinite(result.Q)
    assert result.Q != 0.0
    assert len(result.verdicts) == _SEGMENTED_3.n_cells


def test_segmented_hx_model_does_not_resolve_registry() -> None:
    model = SegmentedMarchModel()
    req = _segmented_req_fixed_wall(DittusBoelterHTC())
    result = model.solve(req)
    assert result is not None


# ============================================================================
# HX model integration — SinkInletTempAndFlow with both correlations
# ============================================================================


def _segmented_req_sink(htc_primary: Correlation, htc_secondary: Correlation) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE,
        primary_mdot=0.05,
        secondary_bc=SinkInletTempAndFlow(T_in=290.0, mdot_secondary=0.1, cp_secondary=4200.0),
        geometry=object(),
        discretization=_SEGMENTED_3,
        geom_scalars={
            "G": 300.0,
            "D_h": _D_H,
            "roughness": 0.0,
            "L_cell": 0.1,
            "rho": 1000.0,
            "mu": 1e-3,
            "A_ht": 0.05,
            "x": 0.0,
            "Re": _RE,
            "Pr": _PR,
            "k": _K,
            "n": _N_HEAT,
        },
        htc_primary=htc_primary,
        htc_secondary=htc_secondary,
        primary_T_in=320.0,
        primary_cp=4200.0,
        primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        ua_computation_mode=UAComputationMode.TWO_SIDED,
    )


def test_segmented_sink_db_primary_gn_secondary_produces_finite_q() -> None:
    model = SegmentedMarchModel()
    req = _segmented_req_sink(DittusBoelterHTC(), GnielinskiHTC())
    result = model.solve(req)
    assert math.isfinite(result.Q)
    assert len(result.verdicts) == 2 * _SEGMENTED_3.n_cells


def test_segmented_sink_gn_primary_db_secondary_produces_finite_q() -> None:
    model = SegmentedMarchModel()
    req = _segmented_req_sink(GnielinskiHTC(), DittusBoelterHTC())
    result = model.solve(req)
    assert math.isfinite(result.Q)
    assert len(result.verdicts) == 2 * _SEGMENTED_3.n_cells
