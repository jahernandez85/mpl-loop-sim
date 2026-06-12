"""Tests for SystemState, StateLayout, and variable-handle primitives.

Phase 1C acceptance criteria (INTERFACE_SPEC §4.2-§4.4, TEST_PLAN_V1 §7-handles):
- VariableKind has exactly the four expected members.
- StateVariableId is immutable, hashable, and structurally comparable.
- StateLayout preserves variable order, maps ids ↔ indices, detects duplicates.
- StateLayout raises clear errors on unknown lookups.
- PortVariableHandle maps a PortId to P/h/mdot slot indices (no values).
- InternalStateHandle maps (component, name) to a slot index (no values).
- SystemState holds a flat float64 vector; rejects wrong-length input.
- SystemState get/set by index and by StateVariableId.
- SystemState copy is independent; copy-and-bump does not mutate the original.
- SystemState does not expose derived thermodynamic properties.
- state.py does not import CoolProp, solvers, components, or network.
- Port from Phase 1B remains value-free after Phase 1C is introduced.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

from mpl_sim.core.port import Port, PortId, PortRole
from mpl_sim.core.state import (
    InternalStateHandle,
    PortVariableHandle,
    StateLayout,
    StateVariableId,
    SystemState,
    VariableKind,
)

# ---------------------------------------------------------------------------
# VariableKind
# ---------------------------------------------------------------------------


class TestVariableKind:
    def test_p_exists(self):
        assert VariableKind.P is not None

    def test_h_exists(self):
        assert VariableKind.H is not None

    def test_mdot_exists(self):
        assert VariableKind.MDOT is not None

    def test_internal_exists(self):
        assert VariableKind.INTERNAL is not None

    def test_exactly_four_members(self):
        assert len(VariableKind) == 4

    def test_all_are_enum_members(self):
        for kind in (VariableKind.P, VariableKind.H, VariableKind.MDOT, VariableKind.INTERNAL):
            assert isinstance(kind, VariableKind)


# ---------------------------------------------------------------------------
# StateVariableId
# ---------------------------------------------------------------------------


class TestStateVariableId:
    def test_construction(self):
        vid = StateVariableId(kind=VariableKind.P, owner="pump_1", local_name="out")
        assert vid.kind is VariableKind.P
        assert vid.owner == "pump_1"
        assert vid.local_name == "out"

    def test_structural_equality(self):
        a = StateVariableId(VariableKind.P, "pump_1", "out")
        b = StateVariableId(VariableKind.P, "pump_1", "out")
        assert a == b

    def test_inequality_different_kind(self):
        assert StateVariableId(VariableKind.P, "c", "p") != StateVariableId(
            VariableKind.H, "c", "p"
        )

    def test_inequality_different_owner(self):
        assert StateVariableId(VariableKind.P, "c1", "p") != StateVariableId(
            VariableKind.P, "c2", "p"
        )

    def test_inequality_different_local_name(self):
        assert StateVariableId(VariableKind.P, "c", "in") != StateVariableId(
            VariableKind.P, "c", "out"
        )

    def test_hashable_equal_objects_same_hash(self):
        a = StateVariableId(VariableKind.H, "pipe_1", "in")
        b = StateVariableId(VariableKind.H, "pipe_1", "in")
        assert hash(a) == hash(b)

    def test_usable_as_dict_key(self):
        vid = StateVariableId(VariableKind.MDOT, "pump_1", "out")
        d = {vid: 42.0}
        assert d[vid] == 42.0

    def test_usable_in_set(self):
        a = StateVariableId(VariableKind.P, "c", "in")
        b = StateVariableId(VariableKind.P, "c", "in")  # same as a
        c = StateVariableId(VariableKind.H, "c", "in")  # different
        s = {a, b, c}
        assert len(s) == 2

    def test_immutable_kind(self):
        vid = StateVariableId(VariableKind.P, "c", "p")
        with pytest.raises(AttributeError):
            vid.kind = VariableKind.H  # type: ignore[misc]

    def test_immutable_owner(self):
        vid = StateVariableId(VariableKind.P, "c", "p")
        with pytest.raises(AttributeError):
            vid.owner = "c2"  # type: ignore[misc]

    def test_immutable_local_name(self):
        vid = StateVariableId(VariableKind.P, "c", "p")
        with pytest.raises(AttributeError):
            vid.local_name = "q"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StateLayout
# ---------------------------------------------------------------------------


def _make_port_vars(component_id: str, port_name: str) -> list[StateVariableId]:
    """Helper: the three StateVariableIds for one port node."""
    return [
        StateVariableId(VariableKind.P, component_id, port_name),
        StateVariableId(VariableKind.H, component_id, port_name),
        StateVariableId(VariableKind.MDOT, component_id, port_name),
    ]


class TestStateLayoutBasics:
    def test_empty_layout(self):
        layout = StateLayout([])
        assert len(layout) == 0
        assert list(layout) == []

    def test_length_matches_variable_count(self):
        vars_ = _make_port_vars("pump_1", "out")
        layout = StateLayout(vars_)
        assert len(layout) == 3

    def test_preserves_variable_order(self):
        vars_ = _make_port_vars("pump_1", "out")
        layout = StateLayout(vars_)
        assert list(layout) == vars_

    def test_iteration_order(self):
        vars_ = _make_port_vars("pump_1", "out") + _make_port_vars("pipe_1", "in")
        layout = StateLayout(vars_)
        assert list(layout) == vars_


class TestStateLayoutIndexOf:
    def _layout(self) -> tuple[StateLayout, list[StateVariableId]]:
        vars_ = _make_port_vars("pump_1", "out") + _make_port_vars("pipe_1", "in")
        return StateLayout(vars_), vars_

    def test_index_of_first_variable(self):
        layout, vars_ = self._layout()
        assert layout.index_of(vars_[0]) == 0

    def test_index_of_last_variable(self):
        layout, vars_ = self._layout()
        assert layout.index_of(vars_[-1]) == len(vars_) - 1

    def test_index_of_middle_variable(self):
        layout, vars_ = self._layout()
        for i, var in enumerate(vars_):
            assert layout.index_of(var) == i

    def test_unknown_variable_raises_key_error(self):
        layout, _ = self._layout()
        unknown = StateVariableId(VariableKind.P, "nonexistent", "port")
        with pytest.raises(KeyError):
            layout.index_of(unknown)

    def test_key_error_message_contains_variable(self):
        layout = StateLayout([])
        unknown = StateVariableId(VariableKind.P, "comp_X", "port_Y")
        with pytest.raises(KeyError, match="comp_X"):
            layout.index_of(unknown)


class TestStateLayoutVariableAt:
    def _layout(self) -> tuple[StateLayout, list[StateVariableId]]:
        vars_ = _make_port_vars("pump_1", "out")
        return StateLayout(vars_), vars_

    def test_variable_at_index_zero(self):
        layout, vars_ = self._layout()
        assert layout.variable_at(0) == vars_[0]

    def test_variable_at_each_index(self):
        layout, vars_ = self._layout()
        for i, var in enumerate(vars_):
            assert layout.variable_at(i) == var

    def test_out_of_range_raises_index_error(self):
        layout, _ = self._layout()
        with pytest.raises(IndexError):
            layout.variable_at(len(layout))

    def test_negative_out_of_range_raises_index_error(self):
        layout = StateLayout([])
        with pytest.raises(IndexError):
            layout.variable_at(0)


class TestStateLayoutDuplicateDetection:
    def test_duplicate_raises_value_error(self):
        v = StateVariableId(VariableKind.P, "c", "p")
        with pytest.raises(ValueError, match="Duplicate"):
            StateLayout([v, v])

    def test_two_identical_variables_raises(self):
        v1 = StateVariableId(VariableKind.P, "c", "p")
        v2 = StateVariableId(VariableKind.P, "c", "p")  # structurally equal to v1
        with pytest.raises(ValueError):
            StateLayout([v1, v2])

    def test_non_duplicate_different_kind_is_ok(self):
        v_p = StateVariableId(VariableKind.P, "c", "p")
        v_h = StateVariableId(VariableKind.H, "c", "p")
        layout = StateLayout([v_p, v_h])
        assert len(layout) == 2

    def test_non_duplicate_different_port_is_ok(self):
        v_in = StateVariableId(VariableKind.P, "c", "in")
        v_out = StateVariableId(VariableKind.P, "c", "out")
        layout = StateLayout([v_in, v_out])
        assert len(layout) == 2


class TestStateLayoutNames:
    def test_port_variable_qualified_name_format(self):
        vars_ = _make_port_vars("pump_1", "out")
        layout = StateLayout(vars_)
        names = layout.names()
        assert names[0] == "pump_1.out.P"
        assert names[1] == "pump_1.out.H"
        assert names[2] == "pump_1.out.MDOT"

    def test_internal_state_qualified_name_format(self):
        v = StateVariableId(VariableKind.INTERNAL, "pipe_1", "wall_T_0")
        layout = StateLayout([v])
        names = layout.names()
        assert names[0] == "pipe_1.wall_T_0"

    def test_names_length_matches_layout(self):
        vars_ = _make_port_vars("c", "p")
        layout = StateLayout(vars_)
        assert len(layout.names()) == len(layout)

    def test_names_indices_are_correct(self):
        vars_ = _make_port_vars("pump_1", "out")
        layout = StateLayout(vars_)
        names = layout.names()
        for i in range(len(layout)):
            assert i in names

    def test_empty_layout_names_is_empty_dict(self):
        layout = StateLayout([])
        assert layout.names() == {}

    def test_names_ordered_matches_variable_order(self):
        p_var = StateVariableId(VariableKind.P, "c", "out")
        h_var = StateVariableId(VariableKind.H, "c", "out")
        layout = StateLayout([p_var, h_var])
        names = layout.names()
        assert names[0] == "c.out.P"
        assert names[1] == "c.out.H"


class TestStateLayoutPortHandle:
    def _layout_with_port(self, component_id: str, port_name: str) -> StateLayout:
        return StateLayout(_make_port_vars(component_id, port_name))

    def test_port_handle_returns_correct_slots(self):
        layout = self._layout_with_port("pump_1", "out")
        port_id = PortId("pump_1", "out")
        handle = layout.port_handle(port_id)
        assert handle.port == port_id
        assert handle.slot_P == 0
        assert handle.slot_h == 1
        assert handle.slot_mdot == 2

    def test_port_handle_slot_ordering_preserved(self):
        # Add some other variables before the port variables
        other = StateVariableId(VariableKind.INTERNAL, "some_comp", "internal_x")
        port_vars = _make_port_vars("pipe_1", "in")
        layout = StateLayout([other] + port_vars)
        port_id = PortId("pipe_1", "in")
        handle = layout.port_handle(port_id)
        assert handle.slot_P == 1
        assert handle.slot_h == 2
        assert handle.slot_mdot == 3

    def test_port_handle_missing_variable_raises_key_error(self):
        layout = StateLayout([])
        port_id = PortId("nonexistent", "out")
        with pytest.raises(KeyError):
            layout.port_handle(port_id)

    def test_port_handle_is_port_variable_handle_instance(self):
        layout = self._layout_with_port("pump_1", "out")
        handle = layout.port_handle(PortId("pump_1", "out"))
        assert isinstance(handle, PortVariableHandle)


class TestStateLayoutInternalHandle:
    def test_internal_handle_returns_correct_slot(self):
        v = StateVariableId(VariableKind.INTERNAL, "pipe_1", "wall_T_0")
        layout = StateLayout([v])
        handle = layout.internal_handle("pipe_1", "wall_T_0")
        assert handle.component == "pipe_1"
        assert handle.name == "wall_T_0"
        assert handle.slot == 0
        assert handle.slots is None

    def test_internal_handle_offset_slot(self):
        port_vars = _make_port_vars("pump_1", "out")
        int_var = StateVariableId(VariableKind.INTERNAL, "pipe_1", "T_wall")
        layout = StateLayout(port_vars + [int_var])
        handle = layout.internal_handle("pipe_1", "T_wall")
        assert handle.slot == 3

    def test_internal_handle_missing_raises_key_error(self):
        layout = StateLayout([])
        with pytest.raises(KeyError):
            layout.internal_handle("nonexistent", "state")

    def test_internal_handle_is_internal_state_handle_instance(self):
        v = StateVariableId(VariableKind.INTERNAL, "c", "s")
        layout = StateLayout([v])
        handle = layout.internal_handle("c", "s")
        assert isinstance(handle, InternalStateHandle)


# ---------------------------------------------------------------------------
# PortVariableHandle
# ---------------------------------------------------------------------------


class TestPortVariableHandle:
    def _make(self) -> PortVariableHandle:
        port_id = PortId("pump_1", "out")
        return PortVariableHandle(port=port_id, slot_P=0, slot_h=1, slot_mdot=2)

    def test_construction(self):
        h = self._make()
        assert h.port == PortId("pump_1", "out")
        assert h.slot_P == 0
        assert h.slot_h == 1
        assert h.slot_mdot == 2

    def test_slots_are_integers(self):
        h = self._make()
        assert isinstance(h.slot_P, int)
        assert isinstance(h.slot_h, int)
        assert isinstance(h.slot_mdot, int)

    def test_immutable_port(self):
        h = self._make()
        with pytest.raises(AttributeError):
            h.port = PortId("other", "p")  # type: ignore[misc]

    def test_immutable_slot_P(self):
        h = self._make()
        with pytest.raises(AttributeError):
            h.slot_P = 99  # type: ignore[misc]

    def test_immutable_slot_h(self):
        h = self._make()
        with pytest.raises(AttributeError):
            h.slot_h = 99  # type: ignore[misc]

    def test_immutable_slot_mdot(self):
        h = self._make()
        with pytest.raises(AttributeError):
            h.slot_mdot = 99  # type: ignore[misc]

    def test_no_P_value_attribute(self):
        """Handle stores indices, never thermodynamic values."""
        h = self._make()
        assert not hasattr(h, "P")
        assert not hasattr(h, "h_value")
        assert not hasattr(h, "mdot")

    def test_exactly_four_fields(self):
        import dataclasses

        fields = {f.name for f in dataclasses.fields(PortVariableHandle)}
        assert fields == {"port", "slot_P", "slot_h", "slot_mdot"}


# ---------------------------------------------------------------------------
# InternalStateHandle
# ---------------------------------------------------------------------------


class TestInternalStateHandle:
    def test_construction_fixed_count(self):
        h = InternalStateHandle(component="pipe_1", name="wall_T", slot=5)
        assert h.component == "pipe_1"
        assert h.name == "wall_T"
        assert h.slot == 5
        assert h.slots is None

    def test_construction_with_slots(self):
        h = InternalStateHandle(component="cond_1", name="zone_pos", slot=10, slots=(10, 11, 12))
        assert h.slots == (10, 11, 12)

    def test_immutable_component(self):
        h = InternalStateHandle("c", "n", 0)
        with pytest.raises(AttributeError):
            h.component = "other"  # type: ignore[misc]

    def test_immutable_slot(self):
        h = InternalStateHandle("c", "n", 0)
        with pytest.raises(AttributeError):
            h.slot = 99  # type: ignore[misc]

    def test_slots_defaults_to_none(self):
        h = InternalStateHandle("c", "n", 0)
        assert h.slots is None


# ---------------------------------------------------------------------------
# SystemState — construction
# ---------------------------------------------------------------------------


def _simple_layout() -> tuple[StateLayout, list[StateVariableId]]:
    """Return a simple 3-variable layout (P, H, MDOT for pump_1.out)."""
    vars_ = _make_port_vars("pump_1", "out")
    return StateLayout(vars_), vars_


class TestSystemStateConstruction:
    def test_construction_with_list(self):
        layout, _ = _simple_layout()
        state = SystemState(layout, [1.0, 2.0, 3.0])
        assert len(state) == 3

    def test_construction_with_numpy_array(self):
        layout, _ = _simple_layout()
        arr = np.array([1.0, 2.0, 3.0])
        state = SystemState(layout, arr)
        assert len(state) == 3

    def test_wrong_length_raises_value_error(self):
        layout, _ = _simple_layout()
        with pytest.raises(ValueError, match="length"):
            SystemState(layout, [1.0, 2.0])  # too short

    def test_wrong_length_too_long_raises_value_error(self):
        layout, _ = _simple_layout()
        with pytest.raises(ValueError):
            SystemState(layout, [1.0, 2.0, 3.0, 4.0])  # too long

    def test_2d_array_raises_value_error(self):
        layout, _ = _simple_layout()
        with pytest.raises(ValueError, match="1-D"):
            SystemState(layout, np.array([[1.0, 2.0, 3.0]]))

    def test_empty_layout_empty_values_ok(self):
        layout = StateLayout([])
        state = SystemState(layout, [])
        assert len(state) == 0

    def test_layout_property(self):
        layout, _ = _simple_layout()
        state = SystemState(layout, [1.0, 2.0, 3.0])
        assert state.layout is layout

    def test_len_equals_layout_len(self):
        layout, _ = _simple_layout()
        state = SystemState(layout, [1.0, 2.0, 3.0])
        assert len(state) == len(layout)


# ---------------------------------------------------------------------------
# SystemState — read access
# ---------------------------------------------------------------------------


class TestSystemStateReadAccess:
    def _state(self) -> tuple[SystemState, list[StateVariableId]]:
        layout, vars_ = _simple_layout()
        return SystemState(layout, [101325.0, 250000.0, 0.05]), vars_

    def test_get_by_index_0(self):
        state, _ = self._state()
        assert state.get_by_index(0) == pytest.approx(101325.0)

    def test_get_by_index_all(self):
        state, _ = self._state()
        expected = [101325.0, 250000.0, 0.05]
        for i, exp in enumerate(expected):
            assert state.get_by_index(i) == pytest.approx(exp)

    def test_get_by_variable_id(self):
        state, vars_ = self._state()
        assert state.get(vars_[0]) == pytest.approx(101325.0)
        assert state.get(vars_[1]) == pytest.approx(250000.0)
        assert state.get(vars_[2]) == pytest.approx(0.05)

    def test_values_property_returns_array(self):
        state, _ = self._state()
        v = state.values
        assert isinstance(v, np.ndarray)
        assert v.shape == (3,)

    def test_values_property_is_copy(self):
        state, _ = self._state()
        v = state.values
        v[0] = 999999.0
        # Original must be unaffected
        assert state.get_by_index(0) == pytest.approx(101325.0)

    def test_get_unknown_variable_raises_key_error(self):
        state, _ = self._state()
        unknown = StateVariableId(VariableKind.P, "nonexistent", "x")
        with pytest.raises(KeyError):
            state.get(unknown)


# ---------------------------------------------------------------------------
# SystemState — write access (in-place)
# ---------------------------------------------------------------------------


class TestSystemStateWriteAccess:
    def _state(self) -> tuple[SystemState, list[StateVariableId]]:
        layout, vars_ = _simple_layout()
        return SystemState(layout, [0.0, 0.0, 0.0]), vars_

    def test_set_by_index(self):
        state, _ = self._state()
        state.set_by_index(0, 200000.0)
        assert state.get_by_index(0) == pytest.approx(200000.0)

    def test_set_by_variable_id(self):
        state, vars_ = self._state()
        state.set(vars_[1], 300000.0)
        assert state.get(vars_[1]) == pytest.approx(300000.0)

    def test_set_does_not_affect_other_slots(self):
        layout, vars_ = _simple_layout()
        state = SystemState(layout, [1.0, 2.0, 3.0])
        state.set(vars_[0], 99.0)
        assert state.get(vars_[1]) == pytest.approx(2.0)
        assert state.get(vars_[2]) == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# SystemState — copy and copy-and-bump
# ---------------------------------------------------------------------------


class TestSystemStateCopy:
    def _state(self) -> tuple[SystemState, list[StateVariableId]]:
        layout, vars_ = _simple_layout()
        return SystemState(layout, [101325.0, 250000.0, 0.05]), vars_

    def test_copy_returns_new_instance(self):
        state, _ = self._state()
        copy = state.copy()
        assert copy is not state

    def test_copy_has_same_values(self):
        state, _ = self._state()
        copy = state.copy()
        np.testing.assert_array_equal(copy.values, state.values)

    def test_copy_is_independent_set_by_index(self):
        state, _ = self._state()
        copy = state.copy()
        copy.set_by_index(0, 999999.0)
        assert state.get_by_index(0) == pytest.approx(101325.0)

    def test_copy_is_independent_set_by_var(self):
        state, vars_ = self._state()
        copy = state.copy()
        copy.set(vars_[1], 999999.0)
        assert state.get(vars_[1]) == pytest.approx(250000.0)

    def test_with_updated_returns_new_instance(self):
        state, vars_ = self._state()
        new = state.with_updated(vars_[0], 200000.0)
        assert new is not state

    def test_with_updated_new_has_updated_value(self):
        state, vars_ = self._state()
        new = state.with_updated(vars_[0], 200000.0)
        assert new.get(vars_[0]) == pytest.approx(200000.0)

    def test_with_updated_does_not_modify_original(self):
        state, vars_ = self._state()
        _ = state.with_updated(vars_[0], 200000.0)
        assert state.get(vars_[0]) == pytest.approx(101325.0)

    def test_with_updated_preserves_other_slots(self):
        state, vars_ = self._state()
        new = state.with_updated(vars_[0], 200000.0)
        assert new.get(vars_[1]) == pytest.approx(250000.0)
        assert new.get(vars_[2]) == pytest.approx(0.05)

    def test_with_updated_by_index_returns_new_instance(self):
        state, _ = self._state()
        new = state.with_updated_by_index(2, 0.1)
        assert new is not state

    def test_with_updated_by_index_does_not_modify_original(self):
        state, _ = self._state()
        _ = state.with_updated_by_index(2, 0.1)
        assert state.get_by_index(2) == pytest.approx(0.05)

    def test_copy_shares_layout(self):
        state, _ = self._state()
        copy = state.copy()
        assert copy.layout is state.layout


# ---------------------------------------------------------------------------
# SystemState — no forbidden properties
# ---------------------------------------------------------------------------


class TestSystemStateNoForbiddenProperties:
    """SystemState must expose no thermodynamic derived properties."""

    FORBIDDEN = ("T", "x", "rho", "mu", "k", "sigma", "cp", "phase", "fluid_state")

    def test_no_forbidden_attributes(self):
        layout, _ = _simple_layout()
        state = SystemState(layout, [1.0, 2.0, 3.0])
        for attr in self.FORBIDDEN:
            assert not hasattr(state, attr), f"SystemState must not have attribute '{attr}'"


# ---------------------------------------------------------------------------
# No CoolProp / forbidden imports in state module source
# ---------------------------------------------------------------------------


class TestStateNoCoolProp:
    def _source(self) -> str:
        import mpl_sim.core.state as state_module

        return Path(state_module.__file__).read_text(encoding="utf-8")

    def test_no_coolprop_in_source(self):
        source = self._source()
        assert "CoolProp" not in source
        assert "coolprop" not in source.lower()

    def test_importing_state_does_not_load_coolprop(self):
        before = "CoolProp" in sys.modules
        import mpl_sim.core.state  # noqa: F401

        after = "CoolProp" in sys.modules
        if not before:
            assert not after

    def test_no_solvers_import(self):
        assert "solvers" not in self._source()

    def test_no_components_import(self):
        assert "mpl_sim.components" not in self._source()

    def test_no_network_import(self):
        assert "mpl_sim.network" not in self._source()

    def test_no_properties_import(self):
        assert "mpl_sim.properties" not in self._source()


# ---------------------------------------------------------------------------
# Integration: Port remains value-free; SystemState holds numerical values
# ---------------------------------------------------------------------------


class TestPhase1CIntegration:
    """Verify Phase 1B Port is still value-free and SystemState holds values."""

    def test_port_remains_value_free(self):
        """Port should carry no numerical values — still true after Phase 1C."""
        pid = PortId("pump_1", "out")
        port = Port(id=pid, owner="pump_1", role=PortRole.OUTLET)
        for attr in ("P", "h", "mdot", "state", "fluid_state", "T", "x", "rho"):
            assert not hasattr(port, attr)

    def test_system_state_holds_port_values(self):
        """Values at a port live in SystemState, not in Port."""
        port_id = PortId("pump_1", "out")
        vars_ = _make_port_vars("pump_1", "out")
        layout = StateLayout(vars_)
        state = SystemState(layout, [200000.0, 400000.0, 0.03])

        handle = layout.port_handle(port_id)
        # Read P, h, mdot through the handle
        P = state.get_by_index(handle.slot_P)
        h = state.get_by_index(handle.slot_h)
        mdot = state.get_by_index(handle.slot_mdot)

        assert P == pytest.approx(200000.0)
        assert h == pytest.approx(400000.0)
        assert mdot == pytest.approx(0.03)

    def test_port_handle_and_variable_id_consistent(self):
        """PortVariableHandle slots match the variable-id-based indices."""
        port_id = PortId("pipe_1", "in")
        vars_ = _make_port_vars("pipe_1", "in")
        layout = StateLayout(vars_)

        handle = layout.port_handle(port_id)
        p_var = StateVariableId(VariableKind.P, "pipe_1", "in")
        h_var = StateVariableId(VariableKind.H, "pipe_1", "in")
        m_var = StateVariableId(VariableKind.MDOT, "pipe_1", "in")

        assert handle.slot_P == layout.index_of(p_var)
        assert handle.slot_h == layout.index_of(h_var)
        assert handle.slot_mdot == layout.index_of(m_var)

    def test_multi_port_layout_round_trip(self):
        """Two-component layout with port variables and an internal state."""
        pump_vars = _make_port_vars("pump_1", "out")
        pipe_vars = _make_port_vars("pipe_1", "in")
        int_var = StateVariableId(VariableKind.INTERNAL, "pipe_1", "wall_T_0")
        all_vars = pump_vars + pipe_vars + [int_var]

        layout = StateLayout(all_vars)
        state = SystemState(layout, [200e3, 400e3, 0.03, 200e3, 400e3, 0.03, 320.0])

        assert len(layout) == 7
        assert len(state) == 7

        # Verify names are ordered and correct
        names = layout.names()
        assert names[0] == "pump_1.out.P"
        assert names[6] == "pipe_1.wall_T_0"

        # Internal handle
        int_handle = layout.internal_handle("pipe_1", "wall_T_0")
        assert int_handle.slot == 6
        assert state.get_by_index(int_handle.slot) == pytest.approx(320.0)
