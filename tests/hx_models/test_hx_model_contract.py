"""Tests for HeatExchangerModel contract primitives — Phase 11A.

Verifies:
  - HeatExchangerModelKind contains expected values
  - HXSolveRequest and HXSolveResult are frozen dataclasses (immutable)
  - HXSolveRequest validates primary_mdot (must be > 0 and finite)
  - HXSolveRequest validates htc_multiplier and friction_multiplier (>= 0, finite)
  - HXSolveResult fields are accessible and correct
  - HeatExchangerModel is an abstract base (cannot be instantiated directly)
  - HeatExchangerModel does not implement the Correlation contract
  - Importing hx_models does not require Network, Solver, or CoolProp
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import (
    FixedHeatRate,
    HeatExchangerModel,
    HeatExchangerModelKind,
    HXSolveRequest,
    HXSolveResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=1e6, h=250e3, identity=_IDENTITY)
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)
_BC = FixedHeatRate(Q=500.0)


def _make_request(**kwargs) -> HXSolveRequest:
    defaults = dict(
        primary_state_in=_STATE_IN,
        primary_mdot=0.05,
        secondary_bc=_BC,
        geometry=object(),
        discretization=_DISC,
    )
    defaults.update(kwargs)
    return HXSolveRequest(**defaults)


# ---------------------------------------------------------------------------
# HeatExchangerModelKind — kind enumeration
# ---------------------------------------------------------------------------


class TestHXModelKind:
    def test_epsilon_ntu_exists(self) -> None:
        assert HeatExchangerModelKind.EPSILON_NTU is not None

    def test_lmtd_exists(self) -> None:
        assert HeatExchangerModelKind.LMTD is not None

    def test_segmented_march_exists(self) -> None:
        assert HeatExchangerModelKind.SEGMENTED_MARCH is not None

    def test_moving_boundary_exists(self) -> None:
        assert HeatExchangerModelKind.MOVING_BOUNDARY is not None

    def test_has_four_kinds(self) -> None:
        assert len(HeatExchangerModelKind) == 4

    def test_epsilon_ntu_is_distinct_from_lmtd(self) -> None:
        assert HeatExchangerModelKind.EPSILON_NTU is not HeatExchangerModelKind.LMTD

    def test_all_kinds_are_enum_members(self) -> None:
        for kind in HeatExchangerModelKind:
            assert isinstance(kind, HeatExchangerModelKind)


# ---------------------------------------------------------------------------
# HXSolveRequest — frozen dataclass
# ---------------------------------------------------------------------------


class TestHXSolveRequestImmutability:
    def test_is_frozen(self) -> None:
        req = _make_request()
        with pytest.raises((AttributeError, TypeError)):
            req.primary_mdot = 99.0  # type: ignore[misc]

    def test_geom_scalars_is_immutable_mapping(self) -> None:
        req = _make_request(geom_scalars={"G": 100.0})
        with pytest.raises((TypeError, AttributeError)):
            req.geom_scalars["G"] = 999.0  # type: ignore[index]


class TestHXSolveRequestValidation:
    def test_valid_request_constructs(self) -> None:
        req = _make_request()
        assert req.primary_mdot == 0.05

    def test_zero_mdot_rejected(self) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            _make_request(primary_mdot=0.0)

    def test_negative_mdot_rejected(self) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            _make_request(primary_mdot=-1.0)

    def test_nan_mdot_rejected(self) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            _make_request(primary_mdot=math.nan)

    def test_inf_mdot_rejected(self) -> None:
        with pytest.raises(ValueError, match="primary_mdot"):
            _make_request(primary_mdot=math.inf)

    def test_nan_htc_multiplier_rejected(self) -> None:
        with pytest.raises(ValueError, match="htc_multiplier"):
            _make_request(htc_multiplier=math.nan)

    def test_negative_htc_multiplier_rejected(self) -> None:
        with pytest.raises(ValueError, match="htc_multiplier"):
            _make_request(htc_multiplier=-0.1)

    def test_nan_friction_multiplier_rejected(self) -> None:
        with pytest.raises(ValueError, match="friction_multiplier"):
            _make_request(friction_multiplier=math.nan)

    def test_negative_friction_multiplier_rejected(self) -> None:
        with pytest.raises(ValueError, match="friction_multiplier"):
            _make_request(friction_multiplier=-1.0)

    def test_zero_htc_multiplier_allowed(self) -> None:
        req = _make_request(htc_multiplier=0.0)
        assert req.htc_multiplier == 0.0

    def test_zero_friction_multiplier_allowed(self) -> None:
        req = _make_request(friction_multiplier=0.0)
        assert req.friction_multiplier == 0.0

    def test_default_multipliers_are_one(self) -> None:
        req = _make_request()
        assert req.htc_multiplier == 1.0
        assert req.friction_multiplier == 1.0

    def test_optional_correlations_default_to_none(self) -> None:
        req = _make_request()
        assert req.htc_primary is None
        assert req.htc_secondary is None
        assert req.dp_primary is None


class TestHXSolveRequestFields:
    def test_primary_state_in_stored(self) -> None:
        req = _make_request()
        assert req.primary_state_in is _STATE_IN

    def test_primary_mdot_stored(self) -> None:
        req = _make_request(primary_mdot=0.1)
        assert req.primary_mdot == 0.1

    def test_secondary_bc_stored(self) -> None:
        req = _make_request()
        assert req.secondary_bc is _BC

    def test_discretization_stored(self) -> None:
        req = _make_request()
        assert req.discretization is _DISC

    def test_geom_scalars_stored(self) -> None:
        req = _make_request(geom_scalars={"D_h": 0.002})
        assert req.geom_scalars["D_h"] == 0.002

    def test_default_geom_scalars_is_empty_mapping(self) -> None:
        req = _make_request()
        assert len(req.geom_scalars) == 0


# ---------------------------------------------------------------------------
# HXSolveResult — frozen dataclass
# ---------------------------------------------------------------------------


class TestHXSolveResultImmutability:
    def _make_result(self) -> HXSolveResult:
        state_out = FluidState(P=1e6, h=260e3, identity=_IDENTITY)
        return HXSolveResult(
            primary_state_out=state_out,
            Q=500.0,
            dP_primary=100.0,
            verdicts=(),
        )

    def test_is_frozen(self) -> None:
        result = self._make_result()
        with pytest.raises((AttributeError, TypeError)):
            result.Q = 0.0  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        result = self._make_result()
        assert result.Q == 500.0
        assert result.dP_primary == 100.0
        assert isinstance(result.primary_state_out, FluidState)
        assert result.verdicts == ()

    def test_default_zone_profile_is_none(self) -> None:
        result = self._make_result()
        assert result.zone_profile is None

    def test_default_multipliers_stored(self) -> None:
        result = self._make_result()
        assert result.htc_multiplier == 1.0
        assert result.friction_multiplier == 1.0


# ---------------------------------------------------------------------------
# HeatExchangerModel — abstract base
# ---------------------------------------------------------------------------


class TestHeatExchangerModelAbstract:
    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            HeatExchangerModel()  # type: ignore[abstract]

    def test_is_not_a_correlation(self) -> None:
        from mpl_sim.correlations.contract import Correlation

        assert not issubclass(HeatExchangerModel, Correlation)

    def test_kind_method_is_abstract(self) -> None:
        assert getattr(HeatExchangerModel.kind, "__isabstractmethod__", False)

    def test_solve_method_is_abstract(self) -> None:
        assert getattr(HeatExchangerModel.solve, "__isabstractmethod__", False)


# ---------------------------------------------------------------------------
# Import boundary — hx_models must not require Network, Solver, or CoolProp
# ---------------------------------------------------------------------------


def _import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        return [ln.strip() for ln in f if ln.strip().startswith(("import ", "from "))]


class TestHXModelContractImportBoundary:
    def _base_imports(self) -> list[str]:
        import mpl_sim.hx_models.base as m

        assert m.__file__ is not None
        return _import_lines(m.__file__)

    def test_base_does_not_import_network(self) -> None:
        for ln in self._base_imports():
            assert "network" not in ln, f"base.py must not import network: {ln!r}"

    def test_base_does_not_import_solvers(self) -> None:
        for ln in self._base_imports():
            assert "solvers" not in ln, f"base.py must not import solvers: {ln!r}"

    def test_base_does_not_import_coolprop(self) -> None:
        for ln in self._base_imports():
            assert "coolprop" not in ln.lower(), f"base.py must not import CoolProp: {ln!r}"

    def test_base_does_not_import_components(self) -> None:
        for ln in self._base_imports():
            assert "components" not in ln, f"base.py must not import components: {ln!r}"

    def test_base_does_not_import_properties(self) -> None:
        for ln in self._base_imports():
            assert "properties" not in ln, f"base.py must not import properties: {ln!r}"
