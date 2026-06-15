"""Phase 5A — CalibrationRegistry tests.

Validates:
- CalibrationRegistry construction.
- Registry registers and resolves named CalibrationSet objects.
- Registry rejects duplicate names.
- Registry rejects unknown names.
- Registry lists names in deterministic (sorted) order.
- Registry rejects empty names and non-CalibrationSet values.
"""

from __future__ import annotations

import pytest

from mpl_sim.calibration import (
    CalibrationModifier,
    CalibrationRegistry,
    CalibrationSet,
    CalibrationTargetId,
    CalibrationTargetKind,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> CalibrationRegistry:
    return CalibrationRegistry()


@pytest.fixture()
def target_id() -> CalibrationTargetId:
    return CalibrationTargetId(
        kind=CalibrationTargetKind.CORRELATION,
        name="churchill",
    )


@pytest.fixture()
def empty_set() -> CalibrationSet:
    return CalibrationSet.empty()


@pytest.fixture()
def non_empty_set(target_id: CalibrationTargetId) -> CalibrationSet:
    m = CalibrationModifier.multiplier(target_id, factor=1.1)
    return CalibrationSet([m])


# ---------------------------------------------------------------------------
# CalibrationRegistry
# ---------------------------------------------------------------------------


class TestCalibrationRegistry:
    def test_construction_starts_empty(self) -> None:
        reg = CalibrationRegistry()
        assert len(reg) == 0
        assert reg.names() == ()

    def test_register_and_resolve(
        self,
        registry: CalibrationRegistry,
        empty_set: CalibrationSet,
    ) -> None:
        registry.register("baseline", empty_set)
        resolved = registry.resolve("baseline")
        assert resolved is empty_set

    def test_register_multiple(
        self,
        registry: CalibrationRegistry,
        empty_set: CalibrationSet,
        non_empty_set: CalibrationSet,
    ) -> None:
        registry.register("baseline", empty_set)
        registry.register("target_run", non_empty_set)
        assert len(registry) == 2

    def test_rejects_duplicate_name(
        self,
        registry: CalibrationRegistry,
        empty_set: CalibrationSet,
    ) -> None:
        registry.register("baseline", empty_set)
        with pytest.raises(ValueError, match="already registered"):
            registry.register("baseline", CalibrationSet.empty())

    def test_rejects_empty_name(
        self,
        registry: CalibrationRegistry,
        empty_set: CalibrationSet,
    ) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            registry.register("", empty_set)

    def test_rejects_unknown_name(self, registry: CalibrationRegistry) -> None:
        with pytest.raises(KeyError):
            registry.resolve("does_not_exist")

    def test_names_are_sorted(
        self,
        registry: CalibrationRegistry,
        empty_set: CalibrationSet,
    ) -> None:
        registry.register("zebra", empty_set)
        registry.register("alpha", CalibrationSet.empty())
        registry.register("middle", CalibrationSet.empty())
        assert registry.names() == ("alpha", "middle", "zebra")

    def test_names_empty_registry(self, registry: CalibrationRegistry) -> None:
        assert registry.names() == ()

    def test_names_returns_tuple(
        self,
        registry: CalibrationRegistry,
        empty_set: CalibrationSet,
    ) -> None:
        registry.register("x", empty_set)
        assert isinstance(registry.names(), tuple)

    def test_is_registered_true(
        self,
        registry: CalibrationRegistry,
        empty_set: CalibrationSet,
    ) -> None:
        registry.register("x", empty_set)
        assert registry.is_registered("x")

    def test_is_registered_false(self, registry: CalibrationRegistry) -> None:
        assert not registry.is_registered("x")

    def test_rejects_non_calibration_set(self, registry: CalibrationRegistry) -> None:
        with pytest.raises(TypeError):
            registry.register("bad", "not a calibration set")  # type: ignore[arg-type]

    def test_rejects_none_value(self, registry: CalibrationRegistry) -> None:
        with pytest.raises(TypeError):
            registry.register("bad", None)  # type: ignore[arg-type]

    def test_resolve_returns_exact_object(
        self,
        registry: CalibrationRegistry,
        non_empty_set: CalibrationSet,
    ) -> None:
        registry.register("run_a", non_empty_set)
        result = registry.resolve("run_a")
        assert result is non_empty_set

    def test_len_grows_with_registrations(
        self,
        registry: CalibrationRegistry,
    ) -> None:
        assert len(registry) == 0
        registry.register("a", CalibrationSet.empty())
        assert len(registry) == 1
        registry.register("b", CalibrationSet.empty())
        assert len(registry) == 2

    def test_deterministic_names_order_is_sorted(self, registry: CalibrationRegistry) -> None:
        names_to_register = ["c_run", "a_run", "b_run"]
        for name in names_to_register:
            registry.register(name, CalibrationSet.empty())
        assert list(registry.names()) == sorted(names_to_register)
