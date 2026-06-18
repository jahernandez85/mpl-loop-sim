"""Cross-model architecture contracts for the HX model family — Phase 11G.

Verifies:
  - All implemented HX models subclass HeatExchangerModel
  - Each model returns the correct HeatExchangerModelKind
  - All implemented kinds remain distinct
  - HeatExchangerModelKind contains all four declared seams
  - Only implemented strategies are instantiable (no accidental MovingBoundaryModel)
  - All implemented models and diagnostics are exported from mpl_sim.hx_models
  - HeatExchangerModelRegistry can register/resolve all implemented models
  - HeatExchangerModelRegistry remains separate from CorrelationRegistry
  - HX strategies do not appear in CorrelationRole
  - Unsupported BCs in LMTDModel and SegmentedMarchModel remain explicitly unsupported
  - EpsilonNTUModel FixedHeatRate path remains supported
  - MOVING_BOUNDARY is a declared seam only — no accidental implementation
  - lmtd.py and segmented.py do not import forbidden layers (filling gap in
    test_hx_model_architecture_boundaries.py which covered base/epsilon_ntu/registry)
"""

from __future__ import annotations

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import CorrelationRole
from mpl_sim.correlations.registry import CorrelationRegistry
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import (
    AmbientCoupling,
    FixedHeatRate,
    FixedWallTemp,
    HeatExchangerModel,
    HeatExchangerModelKind,
    HXSolveRequest,
    HXSolveResult,
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
    UnsupportedHeatExchangerBoundaryConditionError,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel
from mpl_sim.hx_models.lmtd import LMTDModel
from mpl_sim.hx_models.registry import (
    HeatExchangerModelRegistry,
    create_empty_hx_model_registry,
)
from mpl_sim.hx_models.segmented import SegmentedCellRecord, SegmentedMarchModel, SegmentedProfile

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=1e6, h=250e3, identity=_IDENTITY)
_LUMPED = DiscretizationSpec(mode=DiscretizationMode.LUMPED)


def _lumped_request(bc) -> HXSolveRequest:
    """Build the minimal valid HXSolveRequest for a LUMPED discretization."""
    kw: dict = dict(
        primary_state_in=_STATE_IN,
        primary_mdot=0.05,
        secondary_bc=bc,
        geometry=object(),
        discretization=_LUMPED,
    )
    if isinstance(bc, SinkInletTempAndFlow):
        kw.update(
            primary_T_in=300.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            primary_cp=2000.0,
            ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
            htc_primary=object(),
        )
    return HXSolveRequest(**kw)


# ---------------------------------------------------------------------------
# 1. Subclass contract
# ---------------------------------------------------------------------------


class TestHXModelFamilySubclasses:
    def test_epsilon_ntu_is_hx_model(self) -> None:
        assert issubclass(EpsilonNTUModel, HeatExchangerModel)

    def test_lmtd_is_hx_model(self) -> None:
        assert issubclass(LMTDModel, HeatExchangerModel)

    def test_segmented_march_is_hx_model(self) -> None:
        assert issubclass(SegmentedMarchModel, HeatExchangerModel)

    def test_all_implemented_models_subclass_hx_model(self) -> None:
        for cls in (EpsilonNTUModel, LMTDModel, SegmentedMarchModel):
            assert issubclass(
                cls, HeatExchangerModel
            ), f"{cls.__name__} must subclass HeatExchangerModel"


# ---------------------------------------------------------------------------
# 2. Kind consistency
# ---------------------------------------------------------------------------


class TestHXModelKindConsistency:
    def test_epsilon_ntu_returns_epsilon_ntu_kind(self) -> None:
        assert EpsilonNTUModel().kind() is HeatExchangerModelKind.EPSILON_NTU

    def test_lmtd_returns_lmtd_kind(self) -> None:
        assert LMTDModel().kind() is HeatExchangerModelKind.LMTD

    def test_segmented_march_returns_segmented_march_kind(self) -> None:
        assert SegmentedMarchModel().kind() is HeatExchangerModelKind.SEGMENTED_MARCH

    def test_all_implemented_kinds_are_distinct(self) -> None:
        kinds = [
            EpsilonNTUModel().kind(),
            LMTDModel().kind(),
            SegmentedMarchModel().kind(),
        ]
        assert len(set(kinds)) == len(
            kinds
        ), "Implemented models must return distinct HeatExchangerModelKind values"


# ---------------------------------------------------------------------------
# 3. Kind seams — all four declared seams present
# ---------------------------------------------------------------------------


class TestHXModelKindSeams:
    def test_epsilon_ntu_seam_declared(self) -> None:
        assert HeatExchangerModelKind.EPSILON_NTU in HeatExchangerModelKind

    def test_lmtd_seam_declared(self) -> None:
        assert HeatExchangerModelKind.LMTD in HeatExchangerModelKind

    def test_segmented_march_seam_declared(self) -> None:
        assert HeatExchangerModelKind.SEGMENTED_MARCH in HeatExchangerModelKind

    def test_moving_boundary_seam_declared(self) -> None:
        assert HeatExchangerModelKind.MOVING_BOUNDARY in HeatExchangerModelKind

    def test_exactly_four_seams_declared(self) -> None:
        assert len(HeatExchangerModelKind) == 4


# ---------------------------------------------------------------------------
# 4. Instantiability — only implemented strategies can be instantiated
# ---------------------------------------------------------------------------


class TestHXModelInstantiability:
    def test_epsilon_ntu_instantiable(self) -> None:
        assert isinstance(EpsilonNTUModel(), HeatExchangerModel)

    def test_lmtd_instantiable(self) -> None:
        assert isinstance(LMTDModel(), HeatExchangerModel)

    def test_segmented_march_instantiable(self) -> None:
        assert isinstance(SegmentedMarchModel(), HeatExchangerModel)

    def test_abstract_base_not_instantiable(self) -> None:
        with pytest.raises(TypeError):
            HeatExchangerModel()  # type: ignore[abstract]

    def test_no_moving_boundary_model_in_hx_models_package(self) -> None:
        import mpl_sim.hx_models as pkg

        assert not hasattr(
            pkg, "MovingBoundaryModel"
        ), "MovingBoundaryModel must not be exported from mpl_sim.hx_models"

    def test_no_moving_boundary_model_in_base_module(self) -> None:
        import mpl_sim.hx_models.base as m

        assert not hasattr(m, "MovingBoundaryModel")


# ---------------------------------------------------------------------------
# 5. Export consistency
# ---------------------------------------------------------------------------


class TestHXModelExports:
    def test_epsilon_ntu_model_in_package(self) -> None:
        import mpl_sim.hx_models as pkg

        assert pkg.EpsilonNTUModel is EpsilonNTUModel

    def test_lmtd_model_in_package(self) -> None:
        import mpl_sim.hx_models as pkg

        assert pkg.LMTDModel is LMTDModel

    def test_segmented_march_model_in_package(self) -> None:
        import mpl_sim.hx_models as pkg

        assert pkg.SegmentedMarchModel is SegmentedMarchModel

    def test_segmented_cell_record_in_package(self) -> None:
        import mpl_sim.hx_models as pkg

        assert pkg.SegmentedCellRecord is SegmentedCellRecord

    def test_segmented_profile_in_package(self) -> None:
        import mpl_sim.hx_models as pkg

        assert pkg.SegmentedProfile is SegmentedProfile

    def test_all_concrete_names_in_dunder_all(self) -> None:
        import mpl_sim.hx_models as pkg

        for name in (
            "EpsilonNTUModel",
            "LMTDModel",
            "SegmentedMarchModel",
            "SegmentedCellRecord",
            "SegmentedProfile",
        ):
            assert name in pkg.__all__, f"{name!r} must appear in mpl_sim.hx_models.__all__"


# ---------------------------------------------------------------------------
# 6. Registry — all three concrete models register and resolve
# ---------------------------------------------------------------------------


class TestHXModelRegistryConsistency:
    def test_register_and_resolve_epsilon_ntu(self) -> None:
        reg = create_empty_hx_model_registry()
        model = EpsilonNTUModel()
        reg.register("epsilon_ntu", model)
        assert reg.resolve("epsilon_ntu") is model

    def test_register_and_resolve_lmtd(self) -> None:
        reg = create_empty_hx_model_registry()
        model = LMTDModel()
        reg.register("lmtd", model)
        assert reg.resolve("lmtd") is model

    def test_register_and_resolve_segmented_march(self) -> None:
        reg = create_empty_hx_model_registry()
        model = SegmentedMarchModel()
        reg.register("segmented_march", model)
        assert reg.resolve("segmented_march") is model

    def test_all_three_models_coexist_in_registry(self) -> None:
        reg = create_empty_hx_model_registry()
        reg.register("eps_ntu", EpsilonNTUModel())
        reg.register("lmtd", LMTDModel())
        reg.register("segmented", SegmentedMarchModel())
        assert reg.model_names() == ("eps_ntu", "lmtd", "segmented")

    def test_registry_is_hx_model_registry_not_correlation_registry(self) -> None:
        reg = create_empty_hx_model_registry()
        assert isinstance(reg, HeatExchangerModelRegistry)
        assert not isinstance(reg, CorrelationRegistry)


# ---------------------------------------------------------------------------
# 7. HX kinds must not appear in CorrelationRole
# ---------------------------------------------------------------------------


class TestHXKindsNotInCorrelationRole:
    def test_no_hx_kind_is_a_correlation_role(self) -> None:
        correlation_roles = set(CorrelationRole)
        for kind in HeatExchangerModelKind:
            assert kind not in correlation_roles, f"{kind} must not be a CorrelationRole"


# ---------------------------------------------------------------------------
# 8. Unsupported BC seams — LMTDModel
# ---------------------------------------------------------------------------


class TestLMTDModelUnsupportedBCs:
    def test_lmtd_rejects_fixed_heat_rate(self) -> None:
        req = _lumped_request(FixedHeatRate(Q=500.0))
        with pytest.raises(UnsupportedHeatExchangerBoundaryConditionError):
            LMTDModel().solve(req)

    def test_lmtd_rejects_sink_inlet_temp_and_flow(self) -> None:
        bc = SinkInletTempAndFlow(T_in=350.0, mdot_secondary=0.1, cp_secondary=4180.0)
        req = _lumped_request(bc)
        with pytest.raises(UnsupportedHeatExchangerBoundaryConditionError):
            LMTDModel().solve(req)


# ---------------------------------------------------------------------------
# 9. Unsupported BC seams — SegmentedMarchModel
# ---------------------------------------------------------------------------


class TestSegmentedMarchModelUnsupportedBCs:
    def test_segmented_rejects_sink_inlet_temp_and_flow(self) -> None:
        bc = SinkInletTempAndFlow(T_in=350.0, mdot_secondary=0.1, cp_secondary=4180.0)
        req = _lumped_request(bc)
        with pytest.raises(UnsupportedHeatExchangerBoundaryConditionError):
            SegmentedMarchModel().solve(req)

    def test_segmented_does_not_reject_fixed_wall_temp_as_unsupported(self) -> None:
        """FixedWallTemp is now supported in Phase 11H.
        The model must not raise UnsupportedHeatExchangerBoundaryConditionError;
        it may raise ValueError for missing required inputs (LUMPED mode or missing
        primary_T_in / primary_cp / A_ht / htc_primary).
        """
        req = _lumped_request(FixedWallTemp(T_wall=350.0))
        try:
            SegmentedMarchModel().solve(req)
        except UnsupportedHeatExchangerBoundaryConditionError:
            pytest.fail(
                "SegmentedMarchModel raised UnsupportedHeatExchangerBoundaryConditionError "
                "for FixedWallTemp; this BC is supported in Phase 11H"
            )
        except ValueError:
            pass  # expected — LUMPED mode or missing FixedWallTemp required inputs

    def test_segmented_rejects_ambient_coupling(self) -> None:
        req = _lumped_request(AmbientCoupling(T_ambient=300.0, UA_ambient=50.0))
        with pytest.raises(UnsupportedHeatExchangerBoundaryConditionError):
            SegmentedMarchModel().solve(req)


# ---------------------------------------------------------------------------
# 10. Supported BC — EpsilonNTUModel FixedHeatRate path remains functional
# ---------------------------------------------------------------------------


class TestEpsilonNTUModelFixedHeatRateSupported:
    def test_fixed_heat_rate_returns_hx_solve_result(self) -> None:
        req = _lumped_request(FixedHeatRate(Q=500.0))
        result = EpsilonNTUModel().solve(req)
        assert isinstance(result, HXSolveResult)

    def test_fixed_heat_rate_q_is_preserved(self) -> None:
        req = _lumped_request(FixedHeatRate(Q=500.0))
        result = EpsilonNTUModel().solve(req)
        assert result.Q == 500.0

    def test_fixed_heat_rate_negative_q_allowed(self) -> None:
        req = _lumped_request(FixedHeatRate(Q=-300.0))
        result = EpsilonNTUModel().solve(req)
        assert result.Q == -300.0


# ---------------------------------------------------------------------------
# 11. MOVING_BOUNDARY is a declared seam only — no accidental implementation
# ---------------------------------------------------------------------------


class TestMovingBoundaryDeclaredSeamOnly:
    def test_moving_boundary_kind_declared_in_enum(self) -> None:
        assert HeatExchangerModelKind.MOVING_BOUNDARY in HeatExchangerModelKind

    def test_no_moving_boundary_model_exported(self) -> None:
        import mpl_sim.hx_models as pkg

        assert not hasattr(pkg, "MovingBoundaryModel")

    def test_no_implemented_model_returns_moving_boundary_kind(self) -> None:
        for model in (EpsilonNTUModel(), LMTDModel(), SegmentedMarchModel()):
            assert (
                model.kind() is not HeatExchangerModelKind.MOVING_BOUNDARY
            ), f"{type(model).__name__} must not return MOVING_BOUNDARY kind"


# ---------------------------------------------------------------------------
# 12. Import boundary — lmtd.py and segmented.py
#
# The existing test_hx_model_architecture_boundaries.py covers base.py,
# epsilon_ntu.py, and registry.py.  These tests fill the gap for lmtd.py
# and segmented.py, completing full coverage of the five HX model modules.
# ---------------------------------------------------------------------------


def _source_import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        return [ln.strip() for ln in f if ln.strip().startswith(("import ", "from "))]


class TestLMTDImportBoundary:
    def _lines(self) -> list[str]:
        import mpl_sim.hx_models.lmtd as m

        assert m.__file__ is not None
        return _source_import_lines(m.__file__)

    def test_lmtd_does_not_import_coolprop(self) -> None:
        for ln in self._lines():
            assert "coolprop" not in ln.lower()

    def test_lmtd_does_not_import_properties(self) -> None:
        for ln in self._lines():
            assert "properties" not in ln

    def test_lmtd_does_not_import_network(self) -> None:
        for ln in self._lines():
            assert "network" not in ln

    def test_lmtd_does_not_import_solvers(self) -> None:
        for ln in self._lines():
            assert "solvers" not in ln

    def test_lmtd_does_not_import_components(self) -> None:
        for ln in self._lines():
            assert "components" not in ln

    def test_lmtd_does_not_import_correlation_registry(self) -> None:
        for ln in self._lines():
            assert "CorrelationRegistry" not in ln


class TestSegmentedImportBoundary:
    def _lines(self) -> list[str]:
        import mpl_sim.hx_models.segmented as m

        assert m.__file__ is not None
        return _source_import_lines(m.__file__)

    def test_segmented_does_not_import_coolprop(self) -> None:
        for ln in self._lines():
            assert "coolprop" not in ln.lower()

    def test_segmented_does_not_import_properties(self) -> None:
        for ln in self._lines():
            assert "properties" not in ln

    def test_segmented_does_not_import_network(self) -> None:
        for ln in self._lines():
            assert "network" not in ln

    def test_segmented_does_not_import_solvers(self) -> None:
        for ln in self._lines():
            assert "solvers" not in ln

    def test_segmented_does_not_import_components(self) -> None:
        for ln in self._lines():
            assert "components" not in ln

    def test_segmented_does_not_import_correlation_registry(self) -> None:
        for ln in self._lines():
            assert "CorrelationRegistry" not in ln
