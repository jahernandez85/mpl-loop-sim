"""Architecture boundary tests for hx_models — Phase 11E.

Verifies:
  - HeatExchangerModelRegistry is separate from CorrelationRegistry
  - A HX model cannot be resolved from CorrelationRegistry
  - EpsilonNTU/LMTD kinds are not CorrelationRole values
  - HX models do not import Network, Solver, or CoolProp
  - FluidState remains exactly (P, h, identity) — no Phase 11 additions
  - HXSolveResult stores no derived properties
  - Correlations package does not import hx_models
  - Network does not import hx_models
  - Solver does not import hx_models
  - LMTD is declared in HeatExchangerModelKind but not silently used
"""

from __future__ import annotations

import pytest

from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import CorrelationRole
from mpl_sim.correlations.registry import CorrelationRegistry
from mpl_sim.hx_models.base import (
    FixedHeatRate,
    HeatExchangerModelKind,
    HXSolveRequest,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel
from mpl_sim.hx_models.registry import (
    HeatExchangerModelRegistry,
    create_empty_hx_model_registry,
)

# ---------------------------------------------------------------------------
# Registry separation
# ---------------------------------------------------------------------------


class TestRegistrySeparation:
    def test_hx_registry_is_not_correlation_registry_type(self) -> None:
        reg = create_empty_hx_model_registry()
        assert not isinstance(reg, CorrelationRegistry)

    def test_hx_registry_and_corr_registry_are_distinct_classes(self) -> None:
        assert HeatExchangerModelRegistry is not CorrelationRegistry

    def test_cannot_register_hx_model_in_correlation_registry(self) -> None:
        corr_reg = CorrelationRegistry()
        with pytest.raises(TypeError):
            corr_reg.register("eps_ntu", EpsilonNTUModel())  # type: ignore[arg-type]

    def test_cannot_resolve_hx_model_from_correlation_registry(self) -> None:
        corr_reg = CorrelationRegistry()
        with pytest.raises(KeyError):
            corr_reg.resolve("eps_ntu")


# ---------------------------------------------------------------------------
# HX model kinds are not CorrelationRole values
# ---------------------------------------------------------------------------


class TestKindNotCorrelationRole:
    def test_epsilon_ntu_is_not_a_correlation_role(self) -> None:
        assert HeatExchangerModelKind.EPSILON_NTU not in list(CorrelationRole)

    def test_lmtd_is_not_a_correlation_role(self) -> None:
        assert HeatExchangerModelKind.LMTD not in list(CorrelationRole)

    def test_segmented_march_is_not_a_correlation_role(self) -> None:
        assert HeatExchangerModelKind.SEGMENTED_MARCH not in list(CorrelationRole)

    def test_moving_boundary_is_not_a_correlation_role(self) -> None:
        assert HeatExchangerModelKind.MOVING_BOUNDARY not in list(CorrelationRole)

    def test_no_hx_kind_is_a_correlation_role(self) -> None:
        correlation_roles = set(CorrelationRole)
        for kind in HeatExchangerModelKind:
            assert kind not in correlation_roles, f"{kind} should not be a CorrelationRole"


# ---------------------------------------------------------------------------
# LMTD declared but not silently used
# ---------------------------------------------------------------------------


class TestLMTDDeclaredOnly:
    def test_lmtd_kind_is_declared(self) -> None:
        assert HeatExchangerModelKind.LMTD in list(HeatExchangerModelKind)

    def test_epsilon_ntu_model_kind_is_not_lmtd(self) -> None:
        model = EpsilonNTUModel()
        assert model.kind() is not HeatExchangerModelKind.LMTD

    def test_lmtd_not_registered_by_default(self) -> None:
        reg = create_empty_hx_model_registry()
        assert not reg.is_registered("lmtd")

    def test_no_lmtd_import_in_epsilon_ntu(self) -> None:
        import mpl_sim.hx_models.epsilon_ntu as m

        assert m.__file__ is not None
        with open(m.__file__) as f:
            source = f.read()
        assert "lmtd" not in source.lower(), "epsilon_ntu.py references LMTD logic"


# ---------------------------------------------------------------------------
# FluidState remains (P, h, identity) — no Phase 11 additions
# ---------------------------------------------------------------------------


class TestFluidStateUnchanged:
    def test_fluid_state_has_exactly_p_h_identity(self) -> None:
        import dataclasses

        fields = {f.name for f in dataclasses.fields(FluidState)}
        assert fields == {"P", "h", "identity"}, f"FluidState fields changed: {fields!r}"

    def test_fluid_state_has_no_phase11_additions(self) -> None:
        for attr in ("Q", "dP", "T_wall", "htc", "zone_profile", "hx_model"):
            assert not hasattr(FluidState, attr), f"FluidState should not have {attr!r}"


# ---------------------------------------------------------------------------
# HXSolveRequest has no derived properties
# ---------------------------------------------------------------------------


class TestHXRequestNoDerivedState:
    def test_hx_solve_request_is_data_only(self) -> None:
        from mpl_sim.core.fluid_identity import PureFluid
        from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec

        req = HXSolveRequest(
            primary_state_in=FluidState(P=1e6, h=250e3, identity=PureFluid("R134a")),
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=500.0),
            geometry=object(),
            discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
        )
        for attr in ("T", "x", "rho", "mu", "htc", "dP", "Q_out"):
            assert not hasattr(req, attr), f"HXSolveRequest should not have derived attr {attr!r}"


# ---------------------------------------------------------------------------
# Import boundary — modules that must not import hx_models
# ---------------------------------------------------------------------------


def _import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        return [ln.strip() for ln in f if ln.strip().startswith(("import ", "from "))]


class TestCorrelationsDoNotImportHXModels:
    def test_correlations_contract_does_not_import_hx_models(self) -> None:
        import mpl_sim.correlations.contract as m

        assert m.__file__ is not None
        for ln in _import_lines(m.__file__):
            assert "hx_models" not in ln

    def test_correlations_registry_does_not_import_hx_models(self) -> None:
        import mpl_sim.correlations.registry as m

        assert m.__file__ is not None
        for ln in _import_lines(m.__file__):
            assert "hx_models" not in ln


class TestNetworkDoesNotImportHXModels:
    def test_network_topology_does_not_import_hx_models(self) -> None:
        import mpl_sim.network.topology as m

        assert m.__file__ is not None
        for ln in _import_lines(m.__file__):
            assert "hx_models" not in ln

    def test_network_assembly_does_not_import_hx_models(self) -> None:
        import mpl_sim.network.assembly as m

        assert m.__file__ is not None
        for ln in _import_lines(m.__file__):
            assert "hx_models" not in ln


class TestSolverDoesNotImportHXModels:
    def test_solver_base_does_not_import_hx_models(self) -> None:
        import mpl_sim.solvers.base as m

        assert m.__file__ is not None
        for ln in _import_lines(m.__file__):
            assert "hx_models" not in ln

    def test_solver_steady_does_not_import_hx_models(self) -> None:
        import mpl_sim.solvers.steady as m

        assert m.__file__ is not None
        for ln in _import_lines(m.__file__):
            assert "hx_models" not in ln


class TestHXModelsDoNotImportForbiddenLayers:
    def _check_file(self, filepath: str, forbidden: str) -> None:
        with open(filepath) as f:
            for ln in f:
                stripped = ln.strip()
                if stripped.startswith(("import ", "from ")):
                    assert (
                        forbidden not in stripped.lower()
                    ), f"{filepath}: found forbidden import {forbidden!r}: {stripped!r}"

    def test_base_does_not_import_network(self) -> None:
        import mpl_sim.hx_models.base as m

        assert m.__file__ is not None
        self._check_file(m.__file__, "network")

    def test_base_does_not_import_solvers(self) -> None:
        import mpl_sim.hx_models.base as m

        assert m.__file__ is not None
        self._check_file(m.__file__, "solvers")

    def test_base_does_not_import_coolprop(self) -> None:
        import mpl_sim.hx_models.base as m

        assert m.__file__ is not None
        self._check_file(m.__file__, "coolprop")

    def test_epsilon_ntu_does_not_import_network(self) -> None:
        import mpl_sim.hx_models.epsilon_ntu as m

        assert m.__file__ is not None
        self._check_file(m.__file__, "network")

    def test_epsilon_ntu_does_not_import_solvers(self) -> None:
        import mpl_sim.hx_models.epsilon_ntu as m

        assert m.__file__ is not None
        self._check_file(m.__file__, "solvers")

    def test_epsilon_ntu_does_not_import_coolprop(self) -> None:
        import mpl_sim.hx_models.epsilon_ntu as m

        assert m.__file__ is not None
        self._check_file(m.__file__, "coolprop")

    def test_registry_does_not_import_network(self) -> None:
        import mpl_sim.hx_models.registry as m

        assert m.__file__ is not None
        self._check_file(m.__file__, "network")

    def test_registry_does_not_import_coolprop(self) -> None:
        import mpl_sim.hx_models.registry as m

        assert m.__file__ is not None
        self._check_file(m.__file__, "coolprop")
