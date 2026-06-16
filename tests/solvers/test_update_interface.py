"""Generic state update interface tests — Phase 8D.

Covers:
  StateUpdate — construction, immutability, step_norm validation.
  StateUpdateProvider — abstract; concrete dummy returns a valid StateUpdate
    without mutating the input state.

Import-boundary assertions:
  solvers/updates.py must not import CoolProp, properties, correlations,
  calibration, network, components, or geometry.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from mpl_sim.core.state import StateLayout, StateVariableId, SystemState, VariableKind
from mpl_sim.solvers.residuals import ResidualEvaluation, ResidualVector
from mpl_sim.solvers.updates import StateUpdate, StateUpdateProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_lines(module_name: str) -> list[str]:
    import importlib

    mod = importlib.import_module(module_name)
    src = Path(mod.__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
    return [
        line.strip() for line in src.splitlines() if line.strip().startswith(("import ", "from "))
    ]


def _simple_state(n: int = 2) -> SystemState:
    vars_ = [StateVariableId(VariableKind.P, "c", f"p{i}") for i in range(n)]
    layout = StateLayout(vars_)
    return SystemState(layout, [1.0] * n)


def _zero_evaluation(state: SystemState) -> ResidualEvaluation:
    n = len(state)
    vec = ResidualVector([0.0] * n)
    return ResidualEvaluation(vector=vec, norm=0.0)


class _IdentityUpdateProvider(StateUpdateProvider):
    """Dummy: returns a copy of the input state unchanged."""

    def propose_update(
        self,
        state: SystemState,
        residual: ResidualEvaluation,
    ) -> StateUpdate:
        return StateUpdate(state=state.copy(), step_norm=0.0, message="identity")


class _ScaledUpdateProvider(StateUpdateProvider):
    """Dummy: returns a copy of the state with all values scaled by factor."""

    def __init__(self, factor: float) -> None:
        self._factor = factor

    def propose_update(
        self,
        state: SystemState,
        residual: ResidualEvaluation,
    ) -> StateUpdate:
        new_state = state.copy()
        for i in range(len(new_state)):
            new_state.set_by_index(i, new_state.get_by_index(i) * self._factor)
        step_norm = float(sum(abs(v) for v in new_state.values))
        return StateUpdate(state=new_state, step_norm=step_norm)


# ---------------------------------------------------------------------------
# StateUpdate construction
# ---------------------------------------------------------------------------


class TestStateUpdateConstruction:
    def test_minimal_construction(self) -> None:
        state = _simple_state()
        update = StateUpdate(state=state)
        assert update.state is state
        assert update.step_norm is None
        assert update.message is None

    def test_construction_with_step_norm(self) -> None:
        state = _simple_state()
        update = StateUpdate(state=state, step_norm=1.5)
        assert update.step_norm == pytest.approx(1.5)

    def test_construction_with_message(self) -> None:
        state = _simple_state()
        update = StateUpdate(state=state, message="step ok")
        assert update.message == "step ok"

    def test_construction_with_all_fields(self) -> None:
        state = _simple_state()
        update = StateUpdate(state=state, step_norm=0.5, message="step")
        assert update.state is state
        assert update.step_norm == pytest.approx(0.5)
        assert update.message == "step"

    def test_zero_step_norm_accepted(self) -> None:
        update = StateUpdate(state=_simple_state(), step_norm=0.0)
        assert update.step_norm == 0.0

    def test_none_step_norm_accepted(self) -> None:
        update = StateUpdate(state=_simple_state(), step_norm=None)
        assert update.step_norm is None


# ---------------------------------------------------------------------------
# StateUpdate validation
# ---------------------------------------------------------------------------


class TestStateUpdateValidation:
    def test_rejects_nan_step_norm(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            StateUpdate(state=_simple_state(), step_norm=float("nan"))

    def test_rejects_inf_step_norm(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            StateUpdate(state=_simple_state(), step_norm=float("inf"))

    def test_rejects_neg_inf_step_norm(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            StateUpdate(state=_simple_state(), step_norm=float("-inf"))

    def test_rejects_negative_step_norm(self) -> None:
        with pytest.raises(ValueError, match=">= 0"):
            StateUpdate(state=_simple_state(), step_norm=-1.0)


# ---------------------------------------------------------------------------
# StateUpdate immutability
# ---------------------------------------------------------------------------


class TestStateUpdateImmutability:
    def test_state_field_is_immutable(self) -> None:
        update = StateUpdate(state=_simple_state())
        with pytest.raises((AttributeError, TypeError)):
            update.state = _simple_state()  # type: ignore[misc]

    def test_step_norm_field_is_immutable(self) -> None:
        update = StateUpdate(state=_simple_state(), step_norm=1.0)
        with pytest.raises((AttributeError, TypeError)):
            update.step_norm = 2.0  # type: ignore[misc]

    def test_message_field_is_immutable(self) -> None:
        update = StateUpdate(state=_simple_state(), message="a")
        with pytest.raises((AttributeError, TypeError)):
            update.message = "b"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StateUpdateProvider — abstract interface
# ---------------------------------------------------------------------------


class TestStateUpdateProviderAbstract:
    def test_cannot_instantiate_abstract_provider(self) -> None:
        with pytest.raises(TypeError):
            StateUpdateProvider()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# StateUpdateProvider — dummy implementations
# ---------------------------------------------------------------------------


class TestStateUpdateProviderDummy:
    def test_identity_provider_returns_state_update(self) -> None:
        state = _simple_state()
        provider = _IdentityUpdateProvider()
        update = provider.propose_update(state, _zero_evaluation(state))
        assert isinstance(update, StateUpdate)

    def test_identity_provider_returns_new_state_object(self) -> None:
        state = _simple_state()
        provider = _IdentityUpdateProvider()
        update = provider.propose_update(state, _zero_evaluation(state))
        assert update.state is not state

    def test_identity_provider_does_not_mutate_input_state(self) -> None:

        state = _simple_state(3)
        original_values = state.values.copy()
        provider = _IdentityUpdateProvider()
        provider.propose_update(state, _zero_evaluation(state))
        assert (state.values == original_values).all()

    def test_identity_provider_candidate_has_same_values(self) -> None:

        state = _simple_state(2)
        original_values = state.values.copy()
        provider = _IdentityUpdateProvider()
        update = provider.propose_update(state, _zero_evaluation(state))
        assert (update.state.values == original_values).all()

    def test_scaled_provider_does_not_mutate_input(self) -> None:

        state = _simple_state(2)
        original_values = state.values.copy()
        provider = _ScaledUpdateProvider(factor=2.0)
        provider.propose_update(state, _zero_evaluation(state))
        assert (state.values == original_values).all()

    def test_scaled_provider_returns_new_values(self) -> None:

        state = _simple_state(2)
        provider = _ScaledUpdateProvider(factor=3.0)
        update = provider.propose_update(state, _zero_evaluation(state))
        expected = state.values * 3.0
        assert update.state.values == pytest.approx(expected)

    def test_step_norm_is_finite_when_provided(self) -> None:
        state = _simple_state(2)
        provider = _IdentityUpdateProvider()
        update = provider.propose_update(state, _zero_evaluation(state))
        if update.step_norm is not None:
            assert math.isfinite(update.step_norm)


# ---------------------------------------------------------------------------
# Import-boundary assertions
# ---------------------------------------------------------------------------


class TestUpdateInterfaceImportBoundaries:
    def _imports(self) -> list[str]:
        return _import_lines("mpl_sim.solvers.updates")

    def test_no_coolprop_import(self) -> None:
        assert not any("coolprop" in line.lower() for line in self._imports())

    def test_no_properties_import(self) -> None:
        assert not any("mpl_sim.properties" in line for line in self._imports())

    def test_no_correlations_import(self) -> None:
        assert not any("mpl_sim.correlations" in line for line in self._imports())

    def test_no_calibration_import(self) -> None:
        assert not any("mpl_sim.calibration" in line for line in self._imports())

    def test_no_network_import(self) -> None:
        assert not any("mpl_sim.network" in line for line in self._imports())

    def test_no_components_import(self) -> None:
        assert not any("mpl_sim.components" in line for line in self._imports())

    def test_no_geometry_import(self) -> None:
        assert not any("mpl_sim.geometry" in line for line in self._imports())
