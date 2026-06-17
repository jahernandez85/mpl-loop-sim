"""Tests for HeatExchangerModelRegistry — Phase 11A.

Verifies:
  - Registry is separate from CorrelationRegistry
  - Registry resolves HX models by name
  - Registry rejects duplicate names
  - Registry rejects empty names
  - Registry raises KeyError on unknown names
  - create_empty_hx_model_registry returns a fresh registry
  - A Correlation cannot be registered as a HX model
"""

from __future__ import annotations

import pytest

from mpl_sim.correlations.registry import CorrelationRegistry
from mpl_sim.hx_models.base import (
    HeatExchangerModel,
    HeatExchangerModelKind,
    HXSolveRequest,
    HXSolveResult,
)
from mpl_sim.hx_models.registry import (
    HeatExchangerModelRegistry,
    create_empty_hx_model_registry,
)

# ---------------------------------------------------------------------------
# Minimal stub HX model for tests
# ---------------------------------------------------------------------------


class _StubModel(HeatExchangerModel):
    def __init__(self, kind_: HeatExchangerModelKind = HeatExchangerModelKind.EPSILON_NTU) -> None:
        self._kind = kind_

    def kind(self) -> HeatExchangerModelKind:
        return self._kind

    def solve(self, req: HXSolveRequest) -> HXSolveResult:  # pragma: no cover
        raise NotImplementedError("stub")


# ---------------------------------------------------------------------------
# Registry separate from CorrelationRegistry
# ---------------------------------------------------------------------------


class TestRegistrySeparation:
    def test_registry_is_not_correlation_registry(self) -> None:
        reg = create_empty_hx_model_registry()
        assert not isinstance(reg, CorrelationRegistry)

    def test_registry_type_is_hx_model_registry(self) -> None:
        reg = create_empty_hx_model_registry()
        assert isinstance(reg, HeatExchangerModelRegistry)

    def test_correlation_registry_cannot_hold_hx_model(self) -> None:
        corr_reg = CorrelationRegistry()
        model = _StubModel()
        with pytest.raises(TypeError):
            corr_reg.register("epsilon_ntu", model)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_and_resolve(self) -> None:
        reg = create_empty_hx_model_registry()
        model = _StubModel()
        reg.register("eps_ntu", model)
        assert reg.resolve("eps_ntu") is model

    def test_register_multiple(self) -> None:
        reg = create_empty_hx_model_registry()
        m1 = _StubModel(HeatExchangerModelKind.EPSILON_NTU)
        m2 = _StubModel(HeatExchangerModelKind.LMTD)
        reg.register("model_a", m1)
        reg.register("model_b", m2)
        assert reg.resolve("model_a") is m1
        assert reg.resolve("model_b") is m2

    def test_model_names_sorted(self) -> None:
        reg = create_empty_hx_model_registry()
        reg.register("z_model", _StubModel())
        reg.register("a_model", _StubModel())
        names = reg.model_names()
        assert names == ("a_model", "z_model")

    def test_is_registered_true(self) -> None:
        reg = create_empty_hx_model_registry()
        reg.register("mymodel", _StubModel())
        assert reg.is_registered("mymodel") is True

    def test_is_registered_false_for_unknown(self) -> None:
        reg = create_empty_hx_model_registry()
        assert reg.is_registered("nonexistent") is False


# ---------------------------------------------------------------------------
# Rejection cases
# ---------------------------------------------------------------------------


class TestRegistrationRejection:
    def test_duplicate_name_rejected(self) -> None:
        reg = create_empty_hx_model_registry()
        reg.register("same_name", _StubModel())
        with pytest.raises(ValueError, match="same_name"):
            reg.register("same_name", _StubModel())

    def test_empty_name_rejected(self) -> None:
        reg = create_empty_hx_model_registry()
        with pytest.raises(ValueError):
            reg.register("", _StubModel())

    def test_non_model_object_rejected(self) -> None:
        reg = create_empty_hx_model_registry()
        with pytest.raises(TypeError):
            reg.register("bad", object())  # type: ignore[arg-type]

    def test_none_rejected(self) -> None:
        reg = create_empty_hx_model_registry()
        with pytest.raises(TypeError):
            reg.register("bad", None)  # type: ignore[arg-type]

    def test_resolve_unknown_raises_key_error(self) -> None:
        reg = create_empty_hx_model_registry()
        with pytest.raises(KeyError):
            reg.resolve("does_not_exist")

    def test_resolve_empty_name_raises(self) -> None:
        reg = create_empty_hx_model_registry()
        with pytest.raises(KeyError):
            reg.resolve("")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_factory_returns_hx_model_registry(self) -> None:
        reg = create_empty_hx_model_registry()
        assert isinstance(reg, HeatExchangerModelRegistry)

    def test_factory_returns_empty_registry(self) -> None:
        reg = create_empty_hx_model_registry()
        assert reg.model_names() == ()

    def test_factory_returns_new_instance_each_call(self) -> None:
        r1 = create_empty_hx_model_registry()
        r2 = create_empty_hx_model_registry()
        assert r1 is not r2

    def test_registrations_are_independent(self) -> None:
        r1 = create_empty_hx_model_registry()
        r2 = create_empty_hx_model_registry()
        r1.register("model", _StubModel())
        assert not r2.is_registered("model")
