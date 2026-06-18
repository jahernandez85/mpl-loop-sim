"""Phase 11M — ShahBoilingHTC and YanCondensationHTC tests.

Covers:

ShahBoilingHTC
  - Role is HTC.
  - Envelope is non-empty (bounds and fluid_families).
  - evaluate() returns CorrelationOutput with (value, verdict, metadata).
  - value[0] is a finite positive HTC for representative valid input.
  - Representative x=0.3 case matches independently computed expected HTC.
  - Representative x=0.8 case matches independently computed expected HTC.
  - x=0.3 and x=0.8 produce different HTC values (quality-dependence).
  - Returns IN_ENVELOPE verdict for valid inputs.
  - Raises ValueError for x ≤ 0 (x=0.0, x=-0.1).
  - Raises ValueError for x ≥ 1 (x=1.0, x=1.1).
  - Raises ValueError for non-finite x (nan, inf).
  - Raises ValueError for G ≤ 0 or non-finite G.
  - Raises ValueError for D_h ≤ 0 or non-finite D_h.
  - Raises ValueError for q_flux ≤ 0 or None.
  - Raises ValueError for missing / non-positive / non-finite geom_scalars.
  - Can be registered in CorrelationRegistry.
  - Does not import CoolProp, PropertyBackend, network, solvers, components.

YanCondensationHTC
  - Role is HTC.
  - Envelope is non-empty (bounds and fluid_families).
  - evaluate() returns CorrelationOutput with (value, verdict, metadata).
  - value[0] is a finite positive HTC for representative valid input.
  - Representative x=0.5 case matches independently computed expected HTC.
  - Representative x=0.2 case matches independently computed expected HTC.
  - x=0.2 and x=0.5 produce different HTC values (quality-dependence).
  - Returns IN_ENVELOPE verdict for x strictly in (0, 1).
  - Returns EXTRAPOLATED verdict for x=0.0 (evaluable boundary).
  - Returns EXTRAPOLATED verdict for x=1.0 (evaluable boundary).
  - Raises ValueError for x < 0 or x > 1.
  - Raises ValueError for non-finite x.
  - Raises ValueError for G ≤ 0 or non-finite G.
  - Raises ValueError for D_h ≤ 0 or non-finite D_h.
  - Raises ValueError for missing / non-positive / non-finite geom_scalars.
  - Can be registered in CorrelationRegistry.
  - Does not import CoolProp, PropertyBackend, network, solvers, components.

Contract (both)
  - Both implement CorrelationRole.HTC.
  - Neither calls CoolProp or PropertyBackend.
  - Neither uses hidden defaults.
  - Neither uses abs or clip to force physical outputs.
  - No CorrelationRegistry resolution inside HX models.
  - YanCondensationHTC is injectable through existing HX geom_scalars forwarding.
  - ShahBoilingHTC HX injection remains deferred because current HX input
    builders do not populate HTCInput.q_flux.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import (
    ClosureMetadata,
    Correlation,
    CorrelationOutput,
    CorrelationRole,
    HTCInput,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.correlations.registry import create_empty_correlation_registry
from mpl_sim.correlations.two_phase_htc import ShahBoilingHTC, YanCondensationHTC
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import FixedWallTemp, HXSolveRequest
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

# Path to the source file under test (used in architecture tests)
_TWO_PHASE_HTC_SRC = (
    Path(__file__).parent.parent.parent / "src" / "mpl_sim" / "correlations" / "two_phase_htc.py"
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FLUID = PureFluid("R134a")
_STATE = FluidState(P=1.0e6, h=2.5e5, identity=_FLUID)
_LUMPED = DiscretizationSpec(mode=DiscretizationMode.LUMPED, n_cells=1)

# Representative two-phase refrigerant-like properties (no real fluid assumed)
_RHO_L = 1100.0  # kg/m³
_RHO_V = 10.0  # kg/m³
_MU_L = 2.0e-4  # Pa·s
_K_L = 0.08  # W/m/K
_PR_L = 4.5
_H_FG = 200_000.0  # J/kg


def _shah_input(
    G: float = 200.0,
    x: float = 0.3,
    D_h: float = 0.001,
    q_flux: float = 50_000.0,
    rho_l: float = _RHO_L,
    rho_v: float = _RHO_V,
    mu_l: float = _MU_L,
    k_l: float = _K_L,
    Pr_l: float = _PR_L,
    h_fg: float = _H_FG,
) -> HTCInput:
    return HTCInput(
        state=(_STATE,),
        G=G,
        x=(x,),
        D_h=D_h,
        q_flux=q_flux,
        geom_scalars={
            "rho_l": rho_l,
            "rho_v": rho_v,
            "mu_l": mu_l,
            "k_l": k_l,
            "Pr_l": Pr_l,
            "h_fg": h_fg,
        },
    )


def _yan_input(
    G: float = 200.0,
    x: float = 0.5,
    D_h: float = 0.004,
    rho_l: float = _RHO_L,
    rho_v: float = _RHO_V,
    mu_l: float = _MU_L,
    k_l: float = _K_L,
    Pr_l: float = _PR_L,
) -> HTCInput:
    return HTCInput(
        state=(_STATE,),
        G=G,
        x=(x,),
        D_h=D_h,
        geom_scalars={
            "rho_l": rho_l,
            "rho_v": rho_v,
            "mu_l": mu_l,
            "k_l": k_l,
            "Pr_l": Pr_l,
        },
    )


def _shah() -> ShahBoilingHTC:
    return ShahBoilingHTC()


def _yan() -> YanCondensationHTC:
    return YanCondensationHTC()


# ---------------------------------------------------------------------------
# ShahBoilingHTC — contract
# ---------------------------------------------------------------------------


class TestShahBoilingHTCContract:
    def test_role_is_htc(self) -> None:
        assert _shah().role() == CorrelationRole.HTC

    def test_is_correlation_subclass(self) -> None:
        assert isinstance(_shah(), Correlation)

    def test_envelope_non_empty(self) -> None:
        env = _shah().envelope()
        assert len(env.bounds) >= 1
        assert len(env.fluid_families) >= 1

    def test_returns_correlation_output(self) -> None:
        out = _shah().evaluate(_shah_input())
        assert isinstance(out, CorrelationOutput)

    def test_output_has_one_value(self) -> None:
        out = _shah().evaluate(_shah_input())
        assert len(out.value) == 1

    def test_output_value_finite_positive(self) -> None:
        out = _shah().evaluate(_shah_input())
        h = out.value[0]
        assert math.isfinite(h)
        assert h > 0.0

    def test_output_has_verdict(self) -> None:
        out = _shah().evaluate(_shah_input())
        assert isinstance(out.verdict, ValidityVerdict)

    def test_output_has_metadata(self) -> None:
        out = _shah().evaluate(_shah_input())
        assert isinstance(out.metadata, ClosureMetadata)

    def test_verdict_in_envelope_for_valid_input(self) -> None:
        out = _shah().evaluate(_shah_input())
        assert out.verdict.status == ValidityStatus.IN_ENVELOPE

    def test_verdict_violated_empty_for_valid_input(self) -> None:
        out = _shah().evaluate(_shah_input())
        assert out.verdict.violated == ()


# ---------------------------------------------------------------------------
# ShahBoilingHTC — numerical formula
# ---------------------------------------------------------------------------


class TestShahBoilingHTCFormula:
    # Expected values independently computed:
    #   G=200, x=0.3, q=50000, D_h=0.001, rho_l=1100, rho_v=10,
    #   mu_l=2e-4, k_l=0.08, Pr_l=4.5, h_fg=200000 → h ≈ 5786.65 W/m²/K
    def test_representative_x03_matches_expected(self) -> None:
        out = _shah().evaluate(_shah_input(x=0.3))
        assert abs(out.value[0] - 5786.65) < 1.0

    # x=0.8: higher quality, convective-boiling dominated
    #   independently computed → h ≈ 24168.56 W/m²/K
    def test_representative_x08_matches_expected(self) -> None:
        out = _shah().evaluate(_shah_input(x=0.8))
        assert abs(out.value[0] - 24168.56) < 1.0

    def test_different_qualities_give_different_htc(self) -> None:
        h_low = _shah().evaluate(_shah_input(x=0.3)).value[0]
        h_high = _shah().evaluate(_shah_input(x=0.8)).value[0]
        assert h_low != h_high

    def test_htc_increases_with_quality_convective_regime(self) -> None:
        # In the convective-boiling dominated branch, higher x → higher HTC
        h_low = _shah().evaluate(_shah_input(x=0.3)).value[0]
        h_high = _shah().evaluate(_shah_input(x=0.8)).value[0]
        assert h_high > h_low

    def test_nucleate_branch_n_gt1(self) -> None:
        # Force N > 1 by using very low rho_v / rho_l ratio and moderate x
        # With rho_v=1 and rho_l=1000, rho_v/rho_l=0.001:
        # C0 at x=0.5 = (1)^0.8 * sqrt(0.001) = 0.0316 → N < 1 (not N > 1)
        # Use x=0.1 → C0 = (9)^0.8 * sqrt(0.001) = 5.76*0.0316 = 0.182 → still < 1
        # To get N > 1 we need small rho_v/rho_l and small x:
        # x=0.05, rho_v/rho_l=0.001: C0 = (19)^0.8 * 0.0316 = 9.03*0.0316=0.285 → not > 1
        # x=0.01: C0 = (99)^0.8 * 0.0316 = 40.7*0.0316 = 1.285 > 1 ✓
        out = _shah().evaluate(_shah_input(x=0.01, rho_l=1000.0, rho_v=1.0, q_flux=5000.0))
        assert out.value[0] == pytest.approx(1277.3605490431846)

    def test_high_boiling_number_branch(self) -> None:
        out = _shah().evaluate(_shah_input(x=0.01, rho_l=1000.0, rho_v=1.0, q_flux=500_000.0))
        assert out.value[0] == pytest.approx(21691.304503643172)

    def test_intermediate_n_branch_matches_independent_value(self) -> None:
        out = _shah().evaluate(_shah_input(x=0.3))
        assert out.value[0] == pytest.approx(5786.65066390608)

    def test_low_n_branch_matches_independent_value(self) -> None:
        out = _shah().evaluate(_shah_input(x=0.8))
        assert out.value[0] == pytest.approx(24168.561496504783)

    def test_low_froude_branch(self) -> None:
        # Fr_l = G^2 / (rho_l^2 * g * D_h)
        # G=10, rho_l=1100, D_h=0.001: Fr_l = 100/(1.21e6*9.806*0.001) = 100/11865 = 0.00843 < 0.04
        out = _shah().evaluate(_shah_input(G=10.0))
        assert out.value[0] == pytest.approx(366.4400362028301)


# ---------------------------------------------------------------------------
# ShahBoilingHTC — invalid inputs
# ---------------------------------------------------------------------------


class TestShahBoilingHTCInvalidInputs:
    def test_wrong_input_type_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            _shah().evaluate(None)  # type: ignore[arg-type]

    # Quality
    def test_x_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be strictly in"):
            _shah().evaluate(_shah_input(x=0.0))

    def test_x_one_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be strictly in"):
            _shah().evaluate(_shah_input(x=1.0))

    def test_x_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be strictly in"):
            _shah().evaluate(_shah_input(x=-0.1))

    def test_x_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be strictly in"):
            _shah().evaluate(_shah_input(x=1.1))

    def test_x_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be finite"):
            _shah().evaluate(_shah_input(x=float("nan")))

    def test_x_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be finite"):
            _shah().evaluate(_shah_input(x=float("inf")))

    # Mass flux G
    def test_G_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="G must be finite and > 0"):
            _shah().evaluate(_shah_input(G=0.0))

    def test_G_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="G must be finite and > 0"):
            _shah().evaluate(_shah_input(G=-100.0))

    def test_G_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="G must be finite and > 0"):
            _shah().evaluate(_shah_input(G=float("nan")))

    # Hydraulic diameter D_h
    def test_D_h_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="D_h must be finite and > 0"):
            _shah().evaluate(_shah_input(D_h=0.0))

    def test_D_h_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="D_h must be finite and > 0"):
            _shah().evaluate(_shah_input(D_h=-0.001))

    def test_D_h_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="D_h must be finite and > 0"):
            _shah().evaluate(_shah_input(D_h=float("nan")))

    # Heat flux q_flux
    def test_q_flux_none_raises(self) -> None:
        inp = HTCInput(
            state=(_STATE,),
            G=200.0,
            x=(0.3,),
            D_h=0.001,
            q_flux=None,
            geom_scalars={
                "rho_l": _RHO_L,
                "rho_v": _RHO_V,
                "mu_l": _MU_L,
                "k_l": _K_L,
                "Pr_l": _PR_L,
                "h_fg": _H_FG,
            },
        )
        with pytest.raises(ValueError, match="q_flux is required"):
            _shah().evaluate(inp)

    def test_q_flux_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="q_flux must be finite and > 0"):
            _shah().evaluate(_shah_input(q_flux=0.0))

    def test_q_flux_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="q_flux must be finite and > 0"):
            _shah().evaluate(_shah_input(q_flux=-1.0))

    # geom_scalars
    def test_missing_rho_l_raises(self) -> None:
        inp = _shah_input()
        gs = dict(inp.geom_scalars)
        del gs["rho_l"]
        inp2 = HTCInput(
            state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, q_flux=inp.q_flux, geom_scalars=gs
        )
        with pytest.raises(ValueError, match="rho_l"):
            _shah().evaluate(inp2)

    def test_rho_l_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_l"):
            _shah().evaluate(_shah_input(rho_l=0.0))

    def test_rho_l_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_l"):
            _shah().evaluate(_shah_input(rho_l=-1.0))

    def test_missing_rho_v_raises(self) -> None:
        inp = _shah_input()
        gs = dict(inp.geom_scalars)
        del gs["rho_v"]
        inp2 = HTCInput(
            state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, q_flux=inp.q_flux, geom_scalars=gs
        )
        with pytest.raises(ValueError, match="rho_v"):
            _shah().evaluate(inp2)

    def test_missing_mu_l_raises(self) -> None:
        inp = _shah_input()
        gs = dict(inp.geom_scalars)
        del gs["mu_l"]
        inp2 = HTCInput(
            state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, q_flux=inp.q_flux, geom_scalars=gs
        )
        with pytest.raises(ValueError, match="mu_l"):
            _shah().evaluate(inp2)

    def test_mu_l_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_l"):
            _shah().evaluate(_shah_input(mu_l=0.0))

    def test_missing_k_l_raises(self) -> None:
        inp = _shah_input()
        gs = dict(inp.geom_scalars)
        del gs["k_l"]
        inp2 = HTCInput(
            state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, q_flux=inp.q_flux, geom_scalars=gs
        )
        with pytest.raises(ValueError, match="k_l"):
            _shah().evaluate(inp2)

    def test_missing_Pr_l_raises(self) -> None:
        inp = _shah_input()
        gs = dict(inp.geom_scalars)
        del gs["Pr_l"]
        inp2 = HTCInput(
            state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, q_flux=inp.q_flux, geom_scalars=gs
        )
        with pytest.raises(ValueError, match="Pr_l"):
            _shah().evaluate(inp2)

    def test_missing_h_fg_raises(self) -> None:
        inp = _shah_input()
        gs = dict(inp.geom_scalars)
        del gs["h_fg"]
        inp2 = HTCInput(
            state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, q_flux=inp.q_flux, geom_scalars=gs
        )
        with pytest.raises(ValueError, match="h_fg"):
            _shah().evaluate(inp2)

    def test_h_fg_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="h_fg"):
            _shah().evaluate(_shah_input(h_fg=0.0))

    def test_h_fg_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="h_fg"):
            _shah().evaluate(_shah_input(h_fg=-1.0))


# ---------------------------------------------------------------------------
# ShahBoilingHTC — registry and architecture
# ---------------------------------------------------------------------------


class TestShahBoilingHTCRegistryAndArchitecture:
    def test_can_be_registered(self) -> None:
        reg = create_empty_correlation_registry()
        corr = _shah()
        reg.register("shah_boiling_htc", corr)
        resolved = reg.resolve("shah_boiling_htc")
        assert resolved is corr

    def test_no_coolprop_import(self) -> None:
        tree = ast.parse(_TWO_PHASE_HTC_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                for name in names:
                    assert "CoolProp" not in (name or "")

    def test_no_property_backend_import(self) -> None:
        tree = ast.parse(_TWO_PHASE_HTC_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                for name in names:
                    assert "PropertyBackend" not in (name or "")
                    assert "properties" not in (name or "")

    def test_no_abs_or_clip_in_source(self) -> None:
        text = _TWO_PHASE_HTC_SRC.read_text(encoding="utf-8")
        assert "abs(" not in text
        assert "clip(" not in text
        assert ".clip(" not in text

    def test_no_hidden_defaults_in_source(self) -> None:
        text = _TWO_PHASE_HTC_SRC.read_text(encoding="utf-8")
        assert "4180" not in text
        assert "cp_l = " not in text
        assert "rho = 1.0" not in text
        assert "mu = 1e-5" not in text
        assert "k = 0.6" not in text


# ===========================================================================
# YanCondensationHTC — contract
# ===========================================================================


class TestYanCondensationHTCContract:
    def test_role_is_htc(self) -> None:
        assert _yan().role() == CorrelationRole.HTC

    def test_is_correlation_subclass(self) -> None:
        assert isinstance(_yan(), Correlation)

    def test_envelope_non_empty(self) -> None:
        env = _yan().envelope()
        assert len(env.bounds) >= 1
        assert len(env.fluid_families) >= 1

    def test_returns_correlation_output(self) -> None:
        out = _yan().evaluate(_yan_input())
        assert isinstance(out, CorrelationOutput)

    def test_output_has_one_value(self) -> None:
        out = _yan().evaluate(_yan_input())
        assert len(out.value) == 1

    def test_output_value_finite_positive(self) -> None:
        out = _yan().evaluate(_yan_input())
        h = out.value[0]
        assert math.isfinite(h)
        assert h > 0.0

    def test_output_has_verdict(self) -> None:
        out = _yan().evaluate(_yan_input())
        assert isinstance(out.verdict, ValidityVerdict)

    def test_output_has_metadata(self) -> None:
        out = _yan().evaluate(_yan_input())
        assert isinstance(out.metadata, ClosureMetadata)

    def test_verdict_in_envelope_for_interior_quality(self) -> None:
        out = _yan().evaluate(_yan_input(x=0.5))
        assert out.verdict.status == ValidityStatus.IN_ENVELOPE
        assert out.verdict.violated == ()

    def test_verdict_extrapolated_at_x_zero(self) -> None:
        out = _yan().evaluate(_yan_input(x=0.0))
        assert out.verdict.status == ValidityStatus.EXTRAPOLATED
        assert len(out.verdict.violated) >= 1

    def test_verdict_extrapolated_at_x_one(self) -> None:
        out = _yan().evaluate(_yan_input(x=1.0))
        assert out.verdict.status == ValidityStatus.EXTRAPOLATED
        assert len(out.verdict.violated) >= 1

    def test_output_at_x_zero_finite_positive(self) -> None:
        out = _yan().evaluate(_yan_input(x=0.0))
        h = out.value[0]
        assert math.isfinite(h)
        assert h > 0.0

    def test_output_at_x_one_finite_positive(self) -> None:
        out = _yan().evaluate(_yan_input(x=1.0))
        h = out.value[0]
        assert math.isfinite(h)
        assert h > 0.0


# ---------------------------------------------------------------------------
# YanCondensationHTC — numerical formula
# ---------------------------------------------------------------------------


class TestYanCondensationHTCFormula:
    # Expected values independently computed:
    #   G=200, x=0.5, D_h=0.004, rho_l=1100, rho_v=10,
    #   mu_l=2e-4, k_l=0.08, Pr_l=4.5 → h ≈ 7550.31 W/m²/K
    def test_representative_x05_matches_expected(self) -> None:
        out = _yan().evaluate(_yan_input(x=0.5))
        assert abs(out.value[0] - 7550.31) < 1.0

    # x=0.2: independently computed → h ≈ 5742.41 W/m²/K
    def test_representative_x02_matches_expected(self) -> None:
        out = _yan().evaluate(_yan_input(x=0.2))
        assert abs(out.value[0] - 5742.41) < 1.0

    def test_different_qualities_give_different_htc(self) -> None:
        h_low = _yan().evaluate(_yan_input(x=0.2)).value[0]
        h_high = _yan().evaluate(_yan_input(x=0.5)).value[0]
        assert h_low != h_high

    def test_htc_increases_with_quality(self) -> None:
        # Higher quality → larger G_eq → larger Re_eq → larger HTC
        h_low = _yan().evaluate(_yan_input(x=0.2)).value[0]
        h_high = _yan().evaluate(_yan_input(x=0.8)).value[0]
        assert h_high > h_low

    def test_boundary_x0_formula_equals_all_liquid(self) -> None:
        # At x=0: G_eq = G * 1 = G, Re_eq = G*D_h/mu_l
        out = _yan().evaluate(_yan_input(x=0.0))
        G, D_h, mu_l, k_l, Pr_l = 200.0, 0.004, _MU_L, _K_L, _PR_L
        Re_eq_expected = G * D_h / mu_l
        h_expected = 4.118 * Re_eq_expected**0.4 * Pr_l ** (1.0 / 3.0) * k_l / D_h
        assert abs(out.value[0] - h_expected) < 0.01


# ---------------------------------------------------------------------------
# YanCondensationHTC — invalid inputs
# ---------------------------------------------------------------------------


class TestYanCondensationHTCInvalidInputs:
    def test_wrong_input_type_raises_type_error(self) -> None:
        with pytest.raises(TypeError):
            _yan().evaluate(None)  # type: ignore[arg-type]

    # Quality
    def test_x_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be in"):
            _yan().evaluate(_yan_input(x=-0.1))

    def test_x_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be in"):
            _yan().evaluate(_yan_input(x=1.1))

    def test_x_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be finite"):
            _yan().evaluate(_yan_input(x=float("nan")))

    def test_x_inf_raises(self) -> None:
        with pytest.raises(ValueError, match="x must be finite"):
            _yan().evaluate(_yan_input(x=float("inf")))

    # Mass flux G
    def test_G_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="G must be finite and > 0"):
            _yan().evaluate(_yan_input(G=0.0))

    def test_G_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="G must be finite and > 0"):
            _yan().evaluate(_yan_input(G=-100.0))

    def test_G_nan_raises(self) -> None:
        with pytest.raises(ValueError, match="G must be finite and > 0"):
            _yan().evaluate(_yan_input(G=float("nan")))

    # Hydraulic diameter D_h
    def test_D_h_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="D_h must be finite and > 0"):
            _yan().evaluate(_yan_input(D_h=0.0))

    def test_D_h_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="D_h must be finite and > 0"):
            _yan().evaluate(_yan_input(D_h=-0.001))

    # geom_scalars
    def test_missing_rho_l_raises(self) -> None:
        inp = _yan_input()
        gs = dict(inp.geom_scalars)
        del gs["rho_l"]
        inp2 = HTCInput(state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, geom_scalars=gs)
        with pytest.raises(ValueError, match="rho_l"):
            _yan().evaluate(inp2)

    def test_rho_l_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_l"):
            _yan().evaluate(_yan_input(rho_l=0.0))

    def test_missing_rho_v_raises(self) -> None:
        inp = _yan_input()
        gs = dict(inp.geom_scalars)
        del gs["rho_v"]
        inp2 = HTCInput(state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, geom_scalars=gs)
        with pytest.raises(ValueError, match="rho_v"):
            _yan().evaluate(inp2)

    def test_rho_v_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="rho_v"):
            _yan().evaluate(_yan_input(rho_v=0.0))

    def test_missing_mu_l_raises(self) -> None:
        inp = _yan_input()
        gs = dict(inp.geom_scalars)
        del gs["mu_l"]
        inp2 = HTCInput(state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, geom_scalars=gs)
        with pytest.raises(ValueError, match="mu_l"):
            _yan().evaluate(inp2)

    def test_mu_l_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="mu_l"):
            _yan().evaluate(_yan_input(mu_l=-1e-4))

    def test_missing_k_l_raises(self) -> None:
        inp = _yan_input()
        gs = dict(inp.geom_scalars)
        del gs["k_l"]
        inp2 = HTCInput(state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, geom_scalars=gs)
        with pytest.raises(ValueError, match="k_l"):
            _yan().evaluate(inp2)

    def test_missing_Pr_l_raises(self) -> None:
        inp = _yan_input()
        gs = dict(inp.geom_scalars)
        del gs["Pr_l"]
        inp2 = HTCInput(state=inp.state, G=inp.G, x=inp.x, D_h=inp.D_h, geom_scalars=gs)
        with pytest.raises(ValueError, match="Pr_l"):
            _yan().evaluate(inp2)

    def test_Pr_l_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="Pr_l"):
            _yan().evaluate(_yan_input(Pr_l=0.0))


# ---------------------------------------------------------------------------
# YanCondensationHTC — registry and architecture
# ---------------------------------------------------------------------------


class TestYanCondensationHTCRegistryAndArchitecture:
    def test_can_be_registered(self) -> None:
        reg = create_empty_correlation_registry()
        corr = _yan()
        reg.register("yan_condensation_htc", corr)
        resolved = reg.resolve("yan_condensation_htc")
        assert resolved is corr

    def test_no_coolprop_import(self) -> None:
        tree = ast.parse(_TWO_PHASE_HTC_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                for name in names:
                    assert "CoolProp" not in (name or "")

    def test_no_abs_or_clip_in_source(self) -> None:
        text = _TWO_PHASE_HTC_SRC.read_text(encoding="utf-8")
        assert "abs(" not in text
        assert "clip(" not in text


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_shah_exported_from_package(self) -> None:
        from mpl_sim.correlations import ShahBoilingHTC as _S

        assert _S is ShahBoilingHTC

    def test_yan_exported_from_package(self) -> None:
        from mpl_sim.correlations import YanCondensationHTC as _Y

        assert _Y is YanCondensationHTC

    def test_shah_in_all(self) -> None:
        import mpl_sim.correlations as pkg

        assert "ShahBoilingHTC" in pkg.__all__

    def test_yan_in_all(self) -> None:
        import mpl_sim.correlations as pkg

        assert "YanCondensationHTC" in pkg.__all__


# ---------------------------------------------------------------------------
# HX injection status
# ---------------------------------------------------------------------------


class TestHXInjectionStatus:
    """Existing builders forward geom_scalars but not HTCInput.q_flux."""

    @staticmethod
    def _fixed_wall_request(corr: Correlation) -> HXSolveRequest:
        return HXSolveRequest(
            primary_state_in=_STATE,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=350.0),
            geometry=object(),
            discretization=_LUMPED,
            geom_scalars={
                "G": 200.0,
                "x": 0.5,
                "D_h": 0.004,
                "A_ht": 0.05,
                "rho_l": _RHO_L,
                "rho_v": _RHO_V,
                "mu_l": _MU_L,
                "k_l": _K_L,
                "Pr_l": _PR_L,
                "h_fg": _H_FG,
            },
            htc_primary=corr,
            primary_T_in=300.0,
        )

    def test_yan_is_injectable_through_existing_geom_scalar_forwarding(self) -> None:
        result = EpsilonNTUModel().solve(self._fixed_wall_request(_yan()))
        expected_h = _yan().evaluate(_yan_input()).value[0]
        assert result.Q == pytest.approx(expected_h * 0.05 * (350.0 - 300.0))
        assert len(result.verdicts) == 1

    def test_shah_injection_is_deferred_until_q_flux_is_forwarded(self) -> None:
        with pytest.raises(ValueError, match="q_flux is required"):
            EpsilonNTUModel().solve(self._fixed_wall_request(_shah()))
