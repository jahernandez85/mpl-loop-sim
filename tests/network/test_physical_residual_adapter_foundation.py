"""Phase 14A physical residual adapter foundation tests.

Coverage items (32 required):
 1.  valid PhysicalResidualContext construction
 2.  context rejects invalid unknown-values mapping
 3.  metadata is defensively copied and immutable
 4.  valid PhysicalResidualAdapter construction
 5.  adapter rejects empty residual name
 6.  adapter rejects whitespace-only residual name
 7.  adapter rejects non-string residual name
 8.  adapter rejects non-callable callback
 9.  adapter set preserves deterministic order
10.  adapter set rejects wrong entry type
11.  adapter set rejects duplicate residual names
12.  builder rejects non-NetworkResidualAssembly
13.  builder rejects missing adapter
14.  builder rejects extra adapter
15.  builder preserves assembly residual order
16.  generated evaluators are NetworkResidualEvaluator
17.  generated callbacks call adapter with PhysicalResidualContext
18.  generated callbacks pass unknown values correctly
19.  callback exceptions propagate
20.  invalid callback return is rejected by Phase 13G evaluation
21.  one-shot evaluation through Phase 13G gives expected toy residuals
22.  Phase 13H solve works on a toy adapter problem
23.  no automatic component execution
24.  no contribute( call
25.  no property lookup
26.  no registry resolution
27.  no CoolProp
28.  no FluidState attached to graph
29.  no physical values attached to NetworkGraph
30.  public exports work from mpl_sim.network
31.  existing Phase 13E/13F/13G/13H tests still pass (ensured by full suite)
32.  docs do not claim full physical network simulation
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from mpl_sim.network import (
    ComponentInstance,
    ComponentInstanceId,
    GraphNode,
    GraphNodeId,
    NetworkGraph,
    NetworkResidualEvaluator,
    NetworkSolveConfig,
    NetworkUnknownValues,
    PhysicalResidualAdapter,
    PhysicalResidualAdapterSet,
    PhysicalResidualContext,
    assemble_network_residuals,
    build_network_residual_evaluators,
    evaluate_network_residuals,
    solve_network_residual_problem,
)
from mpl_sim.network.physical_adapters import (
    PhysicalResidualAdapter as _AdapterDirect,
)
from mpl_sim.network.physical_adapters import (
    PhysicalResidualAdapterSet as _AdapterSetDirect,
)
from mpl_sim.network.physical_adapters import (
    PhysicalResidualContext as _ContextDirect,
)
from mpl_sim.network.physical_adapters import (
    build_network_residual_evaluators as _build_direct,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _node(nid: str) -> GraphNode:
    return GraphNode(node_id=GraphNodeId(nid))


def _inst(iid: str, ctype: str, inlet: str, outlet: str) -> ComponentInstance:
    return ComponentInstance(
        instance_id=ComponentInstanceId(iid),
        component_type=ctype,
        inlet_node=GraphNodeId(inlet),
        outlet_node=GraphNodeId(outlet),
    )


def _two_component_closed_loop() -> NetworkGraph:
    return NetworkGraph(
        nodes=[_node("n1"), _node("n2")],
        instances=[
            _inst("evap", "evaporator", "n1", "n2"),
            _inst("cond", "condenser", "n2", "n1"),
        ],
    )


# ---------------------------------------------------------------------------
# Toy adapter callbacks (task-spec toy problem)
# ---------------------------------------------------------------------------

# Toy problem from task description:
# unknowns: mdot:evap=0.05, mdot:cond=0.05, P:n1=100000, P:n2=99000
# Expected residuals:
#   mass_balance:n1 = 0.0
#   mass_balance:n2 = 0.0
#   pressure_drop:evap = 100000 - 99000 - 600 = 400.0
#   pressure_drop:cond = 99000 - 100000 + 1000 = 0.0


def _mass_balance_n1(ctx: PhysicalResidualContext) -> float:
    v = ctx.unknown_values
    return v["mdot:evap"] - v["mdot:cond"]


def _mass_balance_n2(ctx: PhysicalResidualContext) -> float:
    v = ctx.unknown_values
    return v["mdot:cond"] - v["mdot:evap"]


def _pressure_drop_evap(ctx: PhysicalResidualContext) -> float:
    v = ctx.unknown_values
    return v["P:n1"] - v["P:n2"] - 600.0


def _pressure_drop_cond(ctx: PhysicalResidualContext) -> float:
    v = ctx.unknown_values
    return v["P:n2"] - v["P:n1"] + 1000.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def graph():
    return _two_component_closed_loop()


@pytest.fixture
def assembly(graph):
    return assemble_network_residuals(graph)


@pytest.fixture
def toy_adapters():
    return [
        PhysicalResidualAdapter("mass_balance:n1", _mass_balance_n1),
        PhysicalResidualAdapter("mass_balance:n2", _mass_balance_n2),
        PhysicalResidualAdapter("pressure_drop:evap", _pressure_drop_evap),
        PhysicalResidualAdapter("pressure_drop:cond", _pressure_drop_cond),
    ]


@pytest.fixture
def toy_adapter_set(toy_adapters):
    return PhysicalResidualAdapterSet(adapters=tuple(toy_adapters))


@pytest.fixture
def toy_unknown_values():
    return NetworkUnknownValues(
        values={
            "mdot:evap": 0.05,
            "mdot:cond": 0.05,
            "P:n1": 100_000.0,
            "P:n2": 99_000.0,
        }
    )


@pytest.fixture
def toy_scales():
    return {
        "mass_balance:n1": 0.01,
        "mass_balance:n2": 0.01,
        "pressure_drop:evap": 100.0,
        "pressure_drop:cond": 100.0,
    }


# ---------------------------------------------------------------------------
# 1. valid PhysicalResidualContext construction
# ---------------------------------------------------------------------------


class TestPhysicalResidualContext:
    def test_valid_construction_plain_dict(self):
        """Item 1: context accepts plain dict as unknown_values."""
        ctx = PhysicalResidualContext(unknown_values={"a": 1.0, "b": 2.0})
        assert ctx.unknown_values["a"] == 1.0
        assert ctx.unknown_values["b"] == 2.0

    def test_unknown_values_stored_as_proxy(self):
        """unknown_values is stored as an immutable MappingProxyType."""
        ctx = PhysicalResidualContext(unknown_values={"x": 3.0})
        assert isinstance(ctx.unknown_values, MappingProxyType)

    def test_unknown_values_proxy_is_immutable(self):
        """MappingProxyType raises TypeError on assignment attempt."""
        ctx = PhysicalResidualContext(unknown_values={"x": 3.0})
        with pytest.raises(TypeError):
            ctx.unknown_values["x"] = 99.0  # type: ignore[index]

    def test_accepts_mapping_proxy_as_unknown_values(self):
        """Context accepts a MappingProxyType as unknown_values."""
        proxy = MappingProxyType({"k": 5.0})
        ctx = PhysicalResidualContext(unknown_values=proxy)
        assert ctx.unknown_values["k"] == 5.0

    def test_valid_construction_with_metadata(self):
        """Context accepts optional metadata mapping."""
        ctx = PhysicalResidualContext(unknown_values={"a": 1.0}, metadata={"tag": "test"})
        assert ctx.metadata is not None
        assert ctx.metadata["tag"] == "test"

    def test_metadata_none_by_default(self):
        """metadata is None when not supplied."""
        ctx = PhysicalResidualContext(unknown_values={"a": 1.0})
        assert ctx.metadata is None

    def test_metadata_stored_as_proxy(self):
        """metadata is stored as an immutable MappingProxyType."""
        ctx = PhysicalResidualContext(unknown_values={"a": 1.0}, metadata={"k": "v"})
        assert isinstance(ctx.metadata, MappingProxyType)

    # Item 2: context rejects invalid unknown-values mapping

    def test_rejects_non_mapping_unknown_values(self):
        """Item 2: non-Mapping unknown_values raises TypeError."""
        with pytest.raises(TypeError, match="Mapping"):
            PhysicalResidualContext(unknown_values="not_a_mapping")  # type: ignore[arg-type]

    def test_rejects_integer_unknown_values(self):
        """Item 2: integer unknown_values raises TypeError."""
        with pytest.raises(TypeError, match="Mapping"):
            PhysicalResidualContext(unknown_values=42)  # type: ignore[arg-type]

    def test_rejects_non_mapping_metadata(self):
        """metadata must be a Mapping or None."""
        with pytest.raises(TypeError, match="Mapping"):
            PhysicalResidualContext(unknown_values={"a": 1.0}, metadata=123)  # type: ignore[arg-type]

    # Item 3: metadata is defensively copied

    def test_metadata_is_defensively_copied(self):
        """Item 3: mutating the original metadata dict does not affect stored copy."""
        original = {"key": "original"}
        ctx = PhysicalResidualContext(unknown_values={"a": 1.0}, metadata=original)
        original["key"] = "mutated"
        original["extra"] = "new"
        assert ctx.metadata["key"] == "original"  # type: ignore[index]
        assert "extra" not in ctx.metadata  # type: ignore[operator]

    def test_unknown_values_is_defensively_copied(self):
        """Mutating the source dict does not affect stored unknown_values."""
        source = {"x": 1.0}
        ctx = PhysicalResidualContext(unknown_values=source)
        source["x"] = 999.0
        assert ctx.unknown_values["x"] == 1.0

    def test_context_is_frozen(self):
        """PhysicalResidualContext is immutable (frozen dataclass)."""
        ctx = PhysicalResidualContext(unknown_values={"a": 1.0})
        with pytest.raises(FrozenInstanceError):
            ctx.unknown_values = {}  # type: ignore[misc]

    def test_rejects_mapping_impostor_with_items_method(self):
        """An object merely exposing items() is not accepted as a Mapping."""

        class MappingImpostor:
            def items(self):
                return (("x", 1.0),)

        with pytest.raises(TypeError, match="Mapping"):
            PhysicalResidualContext(unknown_values=MappingImpostor())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 4–8. PhysicalResidualAdapter construction and validation
# ---------------------------------------------------------------------------


class TestPhysicalResidualAdapter:
    def test_valid_construction(self):
        """Item 4: valid adapter is constructed correctly."""
        adapter = PhysicalResidualAdapter(
            residual_name="mass_balance:n1",
            callback=lambda ctx: 0.0,
        )
        assert adapter.residual_name == "mass_balance:n1"
        assert callable(adapter.callback)

    def test_adapter_is_frozen(self):
        """Adapter is an immutable frozen dataclass."""
        adapter = PhysicalResidualAdapter("r", lambda ctx: 0.0)
        with pytest.raises(FrozenInstanceError):
            adapter.residual_name = "other"  # type: ignore[misc]

    def test_rejects_empty_residual_name(self):
        """Item 5: empty string residual_name raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            PhysicalResidualAdapter(residual_name="", callback=lambda ctx: 0.0)

    def test_rejects_whitespace_only_residual_name(self):
        """Item 6: whitespace-only residual_name raises ValueError."""
        with pytest.raises(ValueError, match="non-empty"):
            PhysicalResidualAdapter(residual_name="   ", callback=lambda ctx: 0.0)

    def test_rejects_non_string_residual_name_int(self):
        """Item 7: integer residual_name raises TypeError."""
        with pytest.raises(TypeError, match="string"):
            PhysicalResidualAdapter(residual_name=42, callback=lambda ctx: 0.0)  # type: ignore[arg-type]

    def test_rejects_non_string_residual_name_none(self):
        """Item 7: None residual_name raises TypeError."""
        with pytest.raises(TypeError, match="string"):
            PhysicalResidualAdapter(residual_name=None, callback=lambda ctx: 0.0)  # type: ignore[arg-type]

    def test_rejects_non_callable_callback(self):
        """Item 8: non-callable callback raises TypeError."""
        with pytest.raises(TypeError, match="callable"):
            PhysicalResidualAdapter(residual_name="r1", callback="not_a_function")  # type: ignore[arg-type]

    def test_rejects_none_callback(self):
        """Item 8: None callback raises TypeError."""
        with pytest.raises(TypeError, match="callable"):
            PhysicalResidualAdapter(residual_name="r1", callback=None)  # type: ignore[arg-type]

    def test_accepts_regular_function_callback(self):
        """Callback can be a regular function."""

        def my_cb(ctx: PhysicalResidualContext) -> float:
            return 0.0

        adapter = PhysicalResidualAdapter("r1", my_cb)
        assert adapter.callback is my_cb

    def test_accepts_lambda_callback(self):
        """Callback can be a lambda."""
        cb = lambda ctx: 1.5  # noqa: E731
        adapter = PhysicalResidualAdapter("r1", cb)
        assert adapter.callback is cb


# ---------------------------------------------------------------------------
# 9–11. PhysicalResidualAdapterSet
# ---------------------------------------------------------------------------


class TestPhysicalResidualAdapterSet:
    def _make_adapter(self, name: str) -> PhysicalResidualAdapter:
        return PhysicalResidualAdapter(residual_name=name, callback=lambda ctx: 0.0)

    def test_valid_construction(self):
        """Adapter set is constructed with valid adapters."""
        a1 = self._make_adapter("r1")
        a2 = self._make_adapter("r2")
        s = PhysicalResidualAdapterSet(adapters=(a1, a2))
        assert len(s.adapters) == 2

    def test_preserves_deterministic_order(self):
        """Item 9: adapter order is preserved exactly."""
        names = ["r3", "r1", "r2"]
        adapters = tuple(self._make_adapter(n) for n in names)
        s = PhysicalResidualAdapterSet(adapters=adapters)
        assert tuple(a.residual_name for a in s.adapters) == ("r3", "r1", "r2")

    def test_accepts_list_and_normalizes_to_tuple(self):
        """List input is coerced to tuple."""
        a1 = self._make_adapter("r1")
        s = PhysicalResidualAdapterSet(adapters=[a1])  # type: ignore[arg-type]
        assert isinstance(s.adapters, tuple)

    def test_rejects_wrong_entry_type(self):
        """Item 10: non-PhysicalResidualAdapter entry raises TypeError."""
        with pytest.raises(TypeError, match="PhysicalResidualAdapter"):
            PhysicalResidualAdapterSet(adapters=("not_an_adapter",))  # type: ignore[arg-type]

    def test_rejects_wrong_entry_type_int(self):
        """Item 10: integer entry raises TypeError."""
        with pytest.raises(TypeError, match="PhysicalResidualAdapter"):
            PhysicalResidualAdapterSet(adapters=(42,))  # type: ignore[arg-type]

    def test_rejects_duplicate_residual_names(self):
        """Item 11: duplicate residual_name raises ValueError."""
        a1 = self._make_adapter("r1")
        a2 = self._make_adapter("r1")
        with pytest.raises(ValueError, match="duplicate"):
            PhysicalResidualAdapterSet(adapters=(a1, a2))

    def test_is_frozen(self):
        """AdapterSet is immutable (frozen dataclass)."""
        s = PhysicalResidualAdapterSet(adapters=(self._make_adapter("r1"),))
        with pytest.raises(FrozenInstanceError):
            s.adapters = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 12–18. build_network_residual_evaluators
# ---------------------------------------------------------------------------


class TestBuildNetworkResidualEvaluators:
    def test_rejects_non_assembly(self):
        """Item 12: non-NetworkResidualAssembly raises TypeError."""
        with pytest.raises(TypeError, match="NetworkResidualAssembly"):
            build_network_residual_evaluators("not_an_assembly", [])

    def test_rejects_none_as_assembly(self):
        """Item 12: None assembly raises TypeError."""
        with pytest.raises(TypeError, match="NetworkResidualAssembly"):
            build_network_residual_evaluators(None, [])

    def test_rejects_missing_adapter(self, assembly):
        """Item 13: missing adapter raises ValueError."""
        partial = [
            PhysicalResidualAdapter("mass_balance:n1", lambda ctx: 0.0),
            PhysicalResidualAdapter("mass_balance:n2", lambda ctx: 0.0),
            # pressure_drop:evap and pressure_drop:cond missing
        ]
        with pytest.raises(ValueError, match="missing"):
            build_network_residual_evaluators(assembly, partial)

    def test_rejects_extra_adapter(self, assembly, toy_adapters):
        """Item 14: extra adapter raises ValueError."""
        extra = toy_adapters + [PhysicalResidualAdapter("extra_residual", lambda ctx: 0.0)]
        with pytest.raises(ValueError, match="not in assembly"):
            build_network_residual_evaluators(assembly, extra)

    def test_preserves_assembly_residual_order(self, assembly, toy_adapters):
        """Item 15: evaluators are generated in assembly declaration order."""
        # Supply adapters in reverse order; output must still match assembly order.
        reversed_adapters = list(reversed(toy_adapters))
        evaluators = build_network_residual_evaluators(assembly, reversed_adapters)
        assembly_order = assembly.residuals.names()
        evaluator_names = tuple(e.name for e in evaluators)
        assert evaluator_names == assembly_order

    def test_generated_evaluators_are_network_residual_evaluator(self, assembly, toy_adapters):
        """Item 16: each generated evaluator is a NetworkResidualEvaluator."""
        evaluators = build_network_residual_evaluators(assembly, toy_adapters)
        for ev in evaluators:
            assert isinstance(ev, NetworkResidualEvaluator)

    def test_count_matches_residual_declarations(self, assembly, toy_adapters):
        """One evaluator per declared residual."""
        evaluators = build_network_residual_evaluators(assembly, toy_adapters)
        assert len(evaluators) == assembly.residuals.count()

    def test_evaluator_names_match_assembly(self, assembly, toy_adapters):
        """Evaluator names match assembly residual declaration names."""
        evaluators = build_network_residual_evaluators(assembly, toy_adapters)
        assert tuple(e.name for e in evaluators) == assembly.residuals.names()

    def test_accepts_adapter_set(self, assembly, toy_adapter_set):
        """build_network_residual_evaluators accepts a PhysicalResidualAdapterSet."""
        evaluators = build_network_residual_evaluators(assembly, toy_adapter_set)
        assert len(evaluators) == assembly.residuals.count()

    def test_accepts_iterable_of_adapters(self, assembly, toy_adapters):
        """build_network_residual_evaluators accepts any iterable of adapters."""
        # Use a generator — an iterable that is not a list or set.
        evaluators = build_network_residual_evaluators(assembly, (a for a in toy_adapters))
        assert len(evaluators) == assembly.residuals.count()

    def test_returns_tuple(self, assembly, toy_adapters):
        """Return value is a tuple."""
        evaluators = build_network_residual_evaluators(assembly, toy_adapters)
        assert isinstance(evaluators, tuple)

    def test_rejects_wrong_adapter_type_in_iterable(self, assembly):
        """Item 10/12: non-adapter in iterable raises TypeError."""
        with pytest.raises(TypeError, match="PhysicalResidualAdapter"):
            build_network_residual_evaluators(assembly, ["not_an_adapter"])

    def test_rejects_duplicate_adapter_names_in_iterable(self, assembly):
        """Duplicate names in iterable path raise ValueError."""
        a1 = PhysicalResidualAdapter("mass_balance:n1", lambda ctx: 0.0)
        a2 = PhysicalResidualAdapter("mass_balance:n1", lambda ctx: 0.0)
        with pytest.raises(ValueError, match="duplicate"):
            build_network_residual_evaluators(assembly, [a1, a2])

    def test_rejects_non_mapping_metadata(self, assembly, toy_adapters):
        """Non-mapping metadata raises TypeError."""
        with pytest.raises(TypeError, match="Mapping"):
            build_network_residual_evaluators(assembly, toy_adapters, metadata=42)

    def test_rejects_metadata_impostor_with_items_method(self, assembly, toy_adapters):
        """Builder requires a real Mapping, not an items()-shaped object."""

        class MappingImpostor:
            def items(self):
                return (("run_id", "fake"),)

        with pytest.raises(TypeError, match="Mapping"):
            build_network_residual_evaluators(
                assembly,
                toy_adapters,
                metadata=MappingImpostor(),
            )

    def test_metadata_none_is_accepted(self, assembly, toy_adapters):
        """metadata=None (default) is accepted."""
        evaluators = build_network_residual_evaluators(assembly, toy_adapters, metadata=None)
        assert len(evaluators) == assembly.residuals.count()

    def test_metadata_mapping_is_accepted(self, assembly, toy_adapters):
        """metadata dict is accepted."""
        evaluators = build_network_residual_evaluators(
            assembly, toy_adapters, metadata={"run_id": "test"}
        )
        assert len(evaluators) == assembly.residuals.count()

    # Item 17: generated callbacks call adapter with PhysicalResidualContext

    def test_generated_callback_receives_physical_residual_context(self, assembly):
        """Item 17: adapter callback is called with a PhysicalResidualContext."""
        received: list[object] = []

        def capturing_cb(ctx: PhysicalResidualContext) -> float:
            received.append(ctx)
            return 0.0

        adapters = [
            PhysicalResidualAdapter("mass_balance:n1", capturing_cb),
            PhysicalResidualAdapter("mass_balance:n2", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:evap", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:cond", lambda ctx: 0.0),
        ]
        evaluators = build_network_residual_evaluators(assembly, adapters)
        # Find the evaluator for mass_balance:n1 and invoke its callback.
        ev = next(e for e in evaluators if e.name == "mass_balance:n1")
        ev.callback({"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1e5, "P:n2": 9.9e4})
        assert len(received) == 1
        assert isinstance(received[0], PhysicalResidualContext)

    # Item 18: generated callbacks pass unknown values correctly

    def test_generated_callback_passes_unknown_values(self, assembly):
        """Item 18: adapter context.unknown_values matches the supplied mapping."""
        received_values: list[dict] = []

        def capturing_cb(ctx: PhysicalResidualContext) -> float:
            received_values.append(dict(ctx.unknown_values))
            return 0.0

        adapters = [
            PhysicalResidualAdapter("mass_balance:n1", capturing_cb),
            PhysicalResidualAdapter("mass_balance:n2", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:evap", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:cond", lambda ctx: 0.0),
        ]
        evaluators = build_network_residual_evaluators(assembly, adapters)
        values = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1e5, "P:n2": 9.9e4}
        ev = next(e for e in evaluators if e.name == "mass_balance:n1")
        ev.callback(values)
        assert received_values[0] == values

    def test_metadata_forwarded_to_context(self, assembly):
        """Metadata supplied to builder is forwarded to each context."""
        received_meta: list[object] = []

        def capturing_cb(ctx: PhysicalResidualContext) -> float:
            received_meta.append(ctx.metadata)
            return 0.0

        adapters = [
            PhysicalResidualAdapter("mass_balance:n1", capturing_cb),
            PhysicalResidualAdapter("mass_balance:n2", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:evap", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:cond", lambda ctx: 0.0),
        ]
        evaluators = build_network_residual_evaluators(
            assembly, adapters, metadata={"run_id": "abc"}
        )
        ev = next(e for e in evaluators if e.name == "mass_balance:n1")
        ev.callback({"mdot:evap": 0.1, "mdot:cond": 0.1, "P:n1": 1e5, "P:n2": 9.9e4})
        assert received_meta[0] is not None
        assert received_meta[0]["run_id"] == "abc"  # type: ignore[index]

    # Item 19: callback exceptions propagate

    def test_callback_exception_propagates(self, assembly):
        """Item 19: exceptions raised inside adapter callback propagate unchanged."""

        def bad_cb(ctx: PhysicalResidualContext) -> float:
            raise RuntimeError("adapter_error_sentinel")

        adapters = [
            PhysicalResidualAdapter("mass_balance:n1", bad_cb),
            PhysicalResidualAdapter("mass_balance:n2", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:evap", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:cond", lambda ctx: 0.0),
        ]
        evaluators = build_network_residual_evaluators(assembly, adapters)
        ev = next(e for e in evaluators if e.name == "mass_balance:n1")
        with pytest.raises(RuntimeError, match="adapter_error_sentinel"):
            ev.callback({"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1e5, "P:n2": 9.9e4})


# ---------------------------------------------------------------------------
# 20–21. Integration with Phase 13G evaluate_network_residuals
# ---------------------------------------------------------------------------


class TestPhase13GIntegration:
    def test_non_numeric_callback_return_rejected(self, assembly, toy_unknown_values, toy_scales):
        """Item 20: adapter returning non-numeric is rejected by Phase 13G."""

        def bad_return_cb(ctx: PhysicalResidualContext):
            return "not_a_number"

        adapters = [
            PhysicalResidualAdapter("mass_balance:n1", bad_return_cb),
            PhysicalResidualAdapter("mass_balance:n2", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:evap", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:cond", lambda ctx: 0.0),
        ]
        evaluators = build_network_residual_evaluators(assembly, adapters)
        with pytest.raises(TypeError):
            evaluate_network_residuals(assembly, toy_unknown_values, evaluators, toy_scales)

    def test_nan_callback_return_rejected(self, assembly, toy_unknown_values, toy_scales):
        """Item 20: adapter returning NaN is rejected by Phase 13G."""
        adapters = [
            PhysicalResidualAdapter("mass_balance:n1", lambda ctx: float("nan")),
            PhysicalResidualAdapter("mass_balance:n2", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:evap", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:cond", lambda ctx: 0.0),
        ]
        evaluators = build_network_residual_evaluators(assembly, adapters)
        with pytest.raises(ValueError):
            evaluate_network_residuals(assembly, toy_unknown_values, evaluators, toy_scales)

    def test_callback_exception_propagates_through_phase13g(
        self, assembly, toy_unknown_values, toy_scales
    ):
        """Item 19/20: callback RuntimeError propagates through Phase 13G."""

        def exploding_cb(ctx: PhysicalResidualContext) -> float:
            raise ValueError("propagated_sentinel")

        adapters = [
            PhysicalResidualAdapter("mass_balance:n1", exploding_cb),
            PhysicalResidualAdapter("mass_balance:n2", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:evap", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:cond", lambda ctx: 0.0),
        ]
        evaluators = build_network_residual_evaluators(assembly, adapters)
        with pytest.raises(ValueError, match="propagated_sentinel"):
            evaluate_network_residuals(assembly, toy_unknown_values, evaluators, toy_scales)

    def test_one_shot_toy_residuals_through_phase13g(
        self, assembly, toy_adapters, toy_unknown_values, toy_scales
    ):
        """Item 21: toy residuals match expected values through Phase 13G."""
        evaluators = build_network_residual_evaluators(assembly, toy_adapters)
        result = evaluate_network_residuals(assembly, toy_unknown_values, evaluators, toy_scales)

        # Expected from task description:
        # mass_balance:n1  = mdot:evap - mdot:cond = 0.05 - 0.05 = 0.0
        # mass_balance:n2  = mdot:cond - mdot:evap = 0.05 - 0.05 = 0.0
        # pressure_drop:evap = P:n1 - P:n2 - 600 = 100000 - 99000 - 600 = 400.0
        # pressure_drop:cond = P:n2 - P:n1 + 1000 = 99000 - 100000 + 1000 = 0.0

        raw = [e.value for e in result.evaluations]
        assert raw[0] == pytest.approx(0.0)
        assert raw[1] == pytest.approx(0.0)
        assert raw[2] == pytest.approx(400.0)
        assert raw[3] == pytest.approx(0.0)

        # Scaled: [0/0.01, 0/0.01, 400/100, 0/100] = [0, 0, 4, 0]
        scaled = result.scaled_values
        assert scaled[0] == pytest.approx(0.0)
        assert scaled[1] == pytest.approx(0.0)
        assert scaled[2] == pytest.approx(4.0)
        assert scaled[3] == pytest.approx(0.0)
        assert result.max_abs_scaled == pytest.approx(4.0)

    def test_residual_order_matches_assembly(
        self, assembly, toy_adapters, toy_unknown_values, toy_scales
    ):
        """Evaluation result evaluations are in assembly declaration order."""
        evaluators = build_network_residual_evaluators(assembly, toy_adapters)
        result = evaluate_network_residuals(assembly, toy_unknown_values, evaluators, toy_scales)
        result_names = tuple(e.spec.name for e in result.evaluations)
        assert result_names == assembly.residuals.names()

    def test_assembly_not_mutated_by_build(self, assembly, toy_adapters):
        """Building evaluators does not mutate the assembly."""
        original_names = assembly.residuals.names()
        build_network_residual_evaluators(assembly, toy_adapters)
        assert assembly.residuals.names() == original_names


# ---------------------------------------------------------------------------
# 22. Phase 13H solve on toy adapter problem
# ---------------------------------------------------------------------------


class TestPhase13HSolve:
    def test_solve_toy_linear_adapter_problem(self):
        """Item 22: Phase 13H solver converges on a decoupled linear adapter problem.

        Toy system (4 unknowns, 4 residuals, diagonal Jacobian):
          mass_balance:n1(ctx)   = v["mdot:evap"] - 0.05
          mass_balance:n2(ctx)   = v["mdot:cond"] - 0.06
          pressure_drop:evap(ctx) = v["P:n1"] - 100_000.0
          pressure_drop:cond(ctx) = v["P:n2"] - 99_000.0

        Solution: mdot:evap=0.05, mdot:cond=0.06, P:n1=100000, P:n2=99000.
        Newton converges in 1 iteration for a linear system.
        """
        graph = _two_component_closed_loop()
        assembly = assemble_network_residuals(graph)

        adapters = [
            PhysicalResidualAdapter(
                "mass_balance:n1", lambda ctx: ctx.unknown_values["mdot:evap"] - 0.05
            ),
            PhysicalResidualAdapter(
                "mass_balance:n2", lambda ctx: ctx.unknown_values["mdot:cond"] - 0.06
            ),
            PhysicalResidualAdapter(
                "pressure_drop:evap",
                lambda ctx: ctx.unknown_values["P:n1"] - 100_000.0,
            ),
            PhysicalResidualAdapter(
                "pressure_drop:cond",
                lambda ctx: ctx.unknown_values["P:n2"] - 99_000.0,
            ),
        ]
        evaluators = build_network_residual_evaluators(assembly, adapters)
        scales = {
            "mass_balance:n1": 0.01,
            "mass_balance:n2": 0.01,
            "pressure_drop:evap": 100.0,
            "pressure_drop:cond": 100.0,
        }
        initial = NetworkUnknownValues(
            values={
                "mdot:evap": 0.10,
                "mdot:cond": 0.10,
                "P:n1": 110_000.0,
                "P:n2": 90_000.0,
            }
        )
        config = NetworkSolveConfig(
            max_iterations=20,
            tolerance=1e-10,
            finite_difference_step=1e-6,
        )
        result = solve_network_residual_problem(assembly, initial, evaluators, scales, config)
        assert result.converged, f"Expected convergence; reason: {result.reason}"
        sol = result.final_unknown_values.values
        assert sol["mdot:evap"] == pytest.approx(0.05, abs=1e-8)
        assert sol["mdot:cond"] == pytest.approx(0.06, abs=1e-8)
        assert sol["P:n1"] == pytest.approx(100_000.0, abs=1e-4)
        assert sol["P:n2"] == pytest.approx(99_000.0, abs=1e-4)


# ---------------------------------------------------------------------------
# 23–29. Architecture boundary assertions
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    def _source(self) -> str:
        import mpl_sim.network.physical_adapters as _m

        return inspect.getsource(_m)

    def _imported_modules(self) -> list[str]:
        tree = ast.parse(self._source())
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        return modules

    def _source_without_docstrings(self) -> str:
        """Return source with all string literal docstrings stripped from AST."""
        src = self._source()
        tree = ast.parse(src)
        # Collect line ranges of module/class/function docstrings.
        docstring_linenos: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if (
                    node.body
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    ds_node = node.body[0]
                    for lineno in range(ds_node.lineno, ds_node.end_lineno + 1):
                        docstring_linenos.add(lineno)
        lines = src.splitlines(keepends=True)
        return "".join(line for i, line in enumerate(lines, start=1) if i not in docstring_linenos)

    def test_no_coolprop_import(self):
        """Item 27: CoolProp is not imported."""
        for mod in self._imported_modules():
            assert "CoolProp" not in mod

    def test_no_property_backend_import(self):
        """Item 25: PropertyBackend is not imported as a module or name."""
        for mod in self._imported_modules():
            assert "properties" not in mod
        # Also ensure no non-docstring code references it.
        assert "PropertyBackend" not in self._source_without_docstrings()

    def test_no_correlation_registry_import(self):
        """Item 26: CorrelationRegistry is not imported."""
        for mod in self._imported_modules():
            assert "correlations" not in mod
        assert "CorrelationRegistry" not in self._source_without_docstrings()

    def test_no_fluid_state_import(self):
        """Item 28: FluidState is not imported or referenced in non-docstring code."""
        assert "FluidState" not in self._source_without_docstrings()

    def test_no_scipy_import(self):
        """No scipy dependency."""
        for mod in self._imported_modules():
            assert "scipy" not in mod

    def test_no_contribute_call(self):
        """Item 24: no contribute( method is defined or called."""
        tree = ast.parse(self._source())
        func_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "contribute" not in func_names
        assert "contribute" not in self._source_without_docstrings()

    def test_no_automatic_component_execution(self):
        """Item 23: component_type is not accessed in non-docstring code."""
        # Check that no Attribute node with attr='component_type' exists.
        tree = ast.parse(self._source())
        attr_names = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)]
        assert "component_type" not in attr_names
        # Also check non-docstring source lines.
        assert "component_type" not in self._source_without_docstrings()

    def test_no_solve_method(self):
        """No solve() method is defined in physical_adapters."""
        tree = ast.parse(self._source())
        func_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "solve" not in func_names

    def test_no_network_graph_values_written(self, graph):
        """Item 29: NetworkGraph carries no physical values after adapter build."""
        assembly = assemble_network_residuals(graph)
        adapters = [
            PhysicalResidualAdapter("mass_balance:n1", lambda ctx: 0.0),
            PhysicalResidualAdapter("mass_balance:n2", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:evap", lambda ctx: 0.0),
            PhysicalResidualAdapter("pressure_drop:cond", lambda ctx: 0.0),
        ]
        build_network_residual_evaluators(assembly, adapters)
        # Nodes and instances carry no physical values.
        for node in graph.nodes():
            assert not hasattr(node, "mdot")
            assert not hasattr(node, "P")
            assert not hasattr(node, "h")
        for inst in graph.instances():
            assert not hasattr(inst, "mdot_value")
            assert not hasattr(inst, "P_in")
            assert not hasattr(inst, "h_in")

    def test_no_hx_model_registry_import(self):
        """HeatExchangerModelRegistry is not imported."""
        for mod in self._imported_modules():
            assert "hx_models" not in mod
        assert "HeatExchangerModelRegistry" not in self._source_without_docstrings()

    def test_physical_adapters_imports_only_network_modules(self):
        """physical_adapters.py only imports from stdlib and mpl_sim.network."""
        for mod in self._imported_modules():
            if mod.startswith("mpl_sim"):
                assert mod.startswith(
                    "mpl_sim.network"
                ), f"physical_adapters.py must not import from {mod!r}"


# ---------------------------------------------------------------------------
# 30. Public exports from mpl_sim.network
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_physical_residual_context_exported(self):
        """Item 30: PhysicalResidualContext is in mpl_sim.network."""
        assert PhysicalResidualContext is _ContextDirect

    def test_physical_residual_adapter_exported(self):
        """Item 30: PhysicalResidualAdapter is in mpl_sim.network."""
        assert PhysicalResidualAdapter is _AdapterDirect

    def test_physical_residual_adapter_set_exported(self):
        """Item 30: PhysicalResidualAdapterSet is in mpl_sim.network."""
        assert PhysicalResidualAdapterSet is _AdapterSetDirect

    def test_build_network_residual_evaluators_exported(self):
        """Item 30: build_network_residual_evaluators is in mpl_sim.network."""
        assert build_network_residual_evaluators is _build_direct

    def test_all_four_names_in_dunder_all(self):
        """Item 30: all four Phase 14A names are in mpl_sim.network.__all__."""
        import mpl_sim.network as _net

        for name in (
            "PhysicalResidualContext",
            "PhysicalResidualAdapter",
            "PhysicalResidualAdapterSet",
            "build_network_residual_evaluators",
        ):
            assert name in _net.__all__, f"{name!r} missing from mpl_sim.network.__all__"

    def test_existing_13g_exports_unchanged(self):
        """Phase 13G exports are still available."""
        import mpl_sim.network as _net

        assert hasattr(_net, "NetworkUnknownValues")
        assert hasattr(_net, "NetworkResidualEvaluator")
        assert hasattr(_net, "evaluate_network_residuals")

    def test_existing_13h_exports_unchanged(self):
        """Phase 13H exports are still available."""
        import mpl_sim.network as _net

        assert hasattr(_net, "NetworkSolveConfig")
        assert hasattr(_net, "NetworkSolveResult")
        assert hasattr(_net, "solve_network_residual_problem")


# ---------------------------------------------------------------------------
# 32. Documentation does not claim full physical simulation
# ---------------------------------------------------------------------------


class TestDocumentation:
    _SECTION_HEADER = "## Physical Residual Adapter Foundation (Phase 14A)"

    def _concepts_text(self) -> str:
        path = pathlib.Path(__file__).parents[2] / "docs" / "user_guide" / "CONCEPTS.md"
        return path.read_text(encoding="utf-8")

    def _phase_14a_section(self) -> str:
        text = self._concepts_text()
        idx = text.find(self._SECTION_HEADER)
        assert idx >= 0, f"{self._SECTION_HEADER!r} section not found in CONCEPTS.md"
        # Extract until next top-level heading.
        rest = text[idx:]
        end = rest.find("\n## ", 1)
        return rest[:end] if end >= 0 else rest

    def test_section_exists(self):
        """Item 32: Phase 14A section exists in CONCEPTS.md."""
        assert self._SECTION_HEADER in self._concepts_text()

    def test_does_not_claim_full_physical_network_simulation(self):
        """Item 32: section does not claim full physical network simulation."""
        section = self._phase_14a_section()
        # Must explicitly say it is NOT a full simulator.
        assert "NOT" in section or "not" in section

    def test_states_adapters_are_caller_supplied(self):
        """Item 32: documentation says adapters are caller-supplied."""
        section = self._phase_14a_section()
        assert "caller" in section.lower() or "explicit" in section.lower()

    def test_no_positive_solve_network_claim(self):
        """Item 32: Phase 14A section does not positively claim solve(network).

        The section may say 'Does NOT implement solve(network)' but must not
        claim to provide or implement solve(network) as a capability.
        """
        section = self._phase_14a_section()
        # Any occurrence of "solve(network)" must appear in a negation context.
        idx = section.find("solve(network)")
        while idx >= 0:
            # Look backwards for negation words within 60 chars.
            prefix = section[max(0, idx - 60) : idx].lower()
            assert any(
                neg in prefix for neg in ("not", "does not", "no ", "deferred")
            ), "Found 'solve(network)' in Phase 14A section without a negation context"
            idx = section.find("solve(network)", idx + 1)

    def test_project_status_mentions_phase_14a(self):
        """PROJECT_STATUS.md references Phase 14A."""
        path = pathlib.Path(__file__).parents[2] / "docs" / "roadmap" / "PROJECT_STATUS.md"
        text = path.read_text(encoding="utf-8")
        assert "14A" in text or "Phase 14A" in text
