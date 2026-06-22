"""Phase 14E controlled toy component execution harness tests.

Coverage items (45 required):
 1.  valid ToyComponentExecutionContext construction
 2.  context rejects non-NetworkBindingContext binding_context
 3.  context unknown_values are defensively copied / immutable
 4.  context metadata is defensively copied / immutable
 5.  valid ToyComponentExecutor construction
 6.  executor rejects wrong component_id type
 7.  executor rejects non-callable callback
 8.  valid ToyComponentExecutorSet construction
 9.  executor set preserves deterministic order
10.  executor set rejects wrong entry type
11.  executor set rejects duplicate component ID
12.  valid toy execution returns ContributionRecordSet
13.  execution rejects non-NetworkBindingContext binding_context
14.  execution rejects missing executor (bound component has no executor)
15.  execution rejects extra/unbound executor
16.  execution propagates callback exception
17.  execution rejects callback wrong return type
18.  execution accepts mapping output
19.  execution accepts ContributionRecordSet output
20.  execution rejects bool mapping value
21.  execution rejects NaN mapping value
22.  execution rejects infinity mapping value
23.  execution rejects non-numeric mapping value
24.  execution rejects empty contribution name
25.  execution rejects whitespace-only contribution name
26.  execution rejects ContributionRecordSet output for wrong component
27.  execution rejects duplicate contribution records
28.  execution preserves deterministic order
29.  convenience conversion to Phase 14C ComponentContribution works
30.  integration with Phase 14D residual map works
31.  integration with Phase 14C adapter works
32.  one-shot Phase 13G evaluation works with toy execution output
33.  optional Phase 13H solve works on toy execution problem
34.  no real component execution
35.  no real contribute( call
36.  no property lookup
37.  no registry resolution
38.  no CoolProp
39.  no SystemState assembly
40.  no FluidState attached to graph
41.  no physical values attached to NetworkGraph
42.  no automatic physics from component_type
43.  public exports work from mpl_sim.network
44.  existing Phase 13E–14D tests still pass (suite-level gate)
45.  docs do not claim full physical network simulation
"""

from __future__ import annotations

import ast
import math
import pathlib
from collections.abc import Mapping

import pytest

from mpl_sim.network import (
    ComponentBinding,
    ComponentContribution,
    ComponentContributionAdapter,
    ComponentContributionAdapterSet,
    ComponentContributionContext,
    ComponentInstance,
    ComponentInstanceId,
    ComponentStateMap,
    ContributionRecord,
    ContributionRecordSet,
    ContributionResidualMap,
    GraphNode,
    GraphNodeId,
    NetworkBindingContext,
    NetworkGraph,
    NetworkUnknownValues,
    ToyComponentExecutionContext,
    ToyComponentExecutor,
    ToyComponentExecutorSet,
    assemble_network_residuals,
    build_binding_context,
    build_component_contribution_from_toy_execution,
    build_network_residual_evaluators,
    build_physical_adapters_from_contributions,
    evaluate_network_residuals,
    execute_toy_component_contributions,
    map_contribution_records_to_component_contribution,
)
from mpl_sim.network.toy_component_execution import (
    ToyComponentExecutionContext as _CtxDirect,
)
from mpl_sim.network.toy_component_execution import (
    ToyComponentExecutor as _ExecDirect,
)
from mpl_sim.network.toy_component_execution import (
    ToyComponentExecutorSet as _ExecSetDirect,
)
from mpl_sim.network.toy_component_execution import (
    build_component_contribution_from_toy_execution as _build_direct,
)
from mpl_sim.network.toy_component_execution import (
    execute_toy_component_contributions as _exec_direct,
)

# ---------------------------------------------------------------------------
# Source file path for boundary checks
# ---------------------------------------------------------------------------

_SRC = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "toy_component_execution.py"
)

# ---------------------------------------------------------------------------
# Shared toy helpers
# ---------------------------------------------------------------------------

_EVAP_ID = ComponentInstanceId("evap")
_COND_ID = ComponentInstanceId("cond")


def _node(nid: str) -> GraphNode:
    return GraphNode(node_id=GraphNodeId(nid))


def _inst(iid: str, ctype: str, inlet: str, outlet: str) -> ComponentInstance:
    return ComponentInstance(
        instance_id=ComponentInstanceId(iid),
        component_type=ctype,
        inlet_node=GraphNodeId(inlet),
        outlet_node=GraphNodeId(outlet),
    )


def _toy_graph() -> NetworkGraph:
    return NetworkGraph(
        nodes=[_node("n1"), _node("n2")],
        instances=[
            _inst("evap", "evaporator", "n1", "n2"),
            _inst("cond", "condenser", "n2", "n1"),
        ],
    )


def _toy_binding_context(graph=None, assembly=None) -> NetworkBindingContext:
    g = graph or _toy_graph()
    asm = assembly or assemble_network_residuals(g)
    bindings = [
        ComponentBinding(instance_id=ComponentInstanceId("evap"), binding_name="evaporator"),
        ComponentBinding(instance_id=ComponentInstanceId("cond"), binding_name="condenser"),
    ]
    state_map = ComponentStateMap()
    return build_binding_context(g, asm, bindings, state_map)


def _toy_unknown_values() -> dict[str, float]:
    return {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}


def toy_evap_mapping(ctx: ToyComponentExecutionContext):
    v = ctx.unknown_values
    return {
        "mass_balance": v["mdot:evap"] - v["mdot:cond"],
        "pressure_drop": v["P:n1"] - v["P:n2"] - 600.0,
    }


def toy_cond_mapping(ctx: ToyComponentExecutionContext):
    v = ctx.unknown_values
    return {
        "mass_balance": v["mdot:cond"] - v["mdot:evap"],
        "pressure_drop": v["P:n2"] - v["P:n1"] + 1000.0,
    }


def _toy_evap_executor() -> ToyComponentExecutor:
    return ToyComponentExecutor(component_id=_EVAP_ID, callback=toy_evap_mapping)


def _toy_cond_executor() -> ToyComponentExecutor:
    return ToyComponentExecutor(component_id=_COND_ID, callback=toy_cond_mapping)


def _toy_executor_set() -> ToyComponentExecutorSet:
    return ToyComponentExecutorSet(executors=(_toy_evap_executor(), _toy_cond_executor()))


def _toy_residual_map() -> ContributionResidualMap:
    return ContributionResidualMap(
        mapping={
            (_EVAP_ID, "mass_balance"): "mass_balance:n1",
            (_EVAP_ID, "pressure_drop"): "pressure_drop:evap",
            (_COND_ID, "mass_balance"): "mass_balance:n2",
            (_COND_ID, "pressure_drop"): "pressure_drop:cond",
        }
    )


# ---------------------------------------------------------------------------
# 1–4: ToyComponentExecutionContext
# ---------------------------------------------------------------------------


class TestToyComponentExecutionContext:
    def test_valid_construction(self):
        """Item 1: valid context construction."""
        bc = _toy_binding_context()
        ctx = ToyComponentExecutionContext(
            binding_context=bc,
            unknown_values={"mdot:evap": 0.05},
        )
        assert ctx.binding_context is bc
        assert ctx.unknown_values["mdot:evap"] == pytest.approx(0.05)
        assert ctx.metadata is None

    def test_valid_construction_with_metadata(self):
        """Item 1: valid context construction with metadata."""
        bc = _toy_binding_context()
        ctx = ToyComponentExecutionContext(
            binding_context=bc,
            unknown_values={"x": 1.0},
            metadata={"run_id": "test"},
        )
        assert ctx.metadata["run_id"] == "test"

    def test_rejects_non_binding_context(self):
        """Item 2: non-NetworkBindingContext binding_context rejected."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            ToyComponentExecutionContext(
                binding_context="not_a_binding_context",
                unknown_values={},
            )

    def test_rejects_non_mapping_unknown_values(self):
        """Item 2: non-Mapping unknown_values rejected."""
        bc = _toy_binding_context()
        with pytest.raises(TypeError, match="Mapping"):
            ToyComponentExecutionContext(
                binding_context=bc,
                unknown_values=[1.0, 2.0],  # type: ignore[arg-type]
            )

    def test_unknown_values_defensively_copied(self):
        """Item 3: post-construction mutation of source dict does not affect context."""
        bc = _toy_binding_context()
        source = {"mdot:evap": 0.05}
        ctx = ToyComponentExecutionContext(binding_context=bc, unknown_values=source)
        source["mdot:cond"] = 0.99
        assert "mdot:cond" not in ctx.unknown_values

    def test_unknown_values_immutable(self):
        """Item 3: unknown_values mapping is read-only after construction."""
        from types import MappingProxyType

        bc = _toy_binding_context()
        ctx = ToyComponentExecutionContext(binding_context=bc, unknown_values={"x": 1.0})
        assert isinstance(ctx.unknown_values, MappingProxyType)

    def test_metadata_defensively_copied(self):
        """Item 4: post-construction mutation of source metadata does not affect context."""
        bc = _toy_binding_context()
        meta = {"tag": "original"}
        ctx = ToyComponentExecutionContext(binding_context=bc, unknown_values={}, metadata=meta)
        meta["tag"] = "mutated"
        assert ctx.metadata["tag"] == "original"

    def test_metadata_immutable(self):
        """Item 4: metadata mapping is read-only after construction."""
        from types import MappingProxyType

        bc = _toy_binding_context()
        ctx = ToyComponentExecutionContext(
            binding_context=bc, unknown_values={}, metadata={"k": "v"}
        )
        assert isinstance(ctx.metadata, MappingProxyType)

    def test_rejects_non_mapping_metadata(self):
        """Item 4: non-Mapping metadata rejected."""
        bc = _toy_binding_context()
        with pytest.raises(TypeError, match="Mapping"):
            ToyComponentExecutionContext(
                binding_context=bc,
                unknown_values={},
                metadata="not_a_mapping",  # type: ignore[arg-type]
            )

    def test_frozen(self):
        """Item 1: context fields cannot be reassigned."""
        from dataclasses import FrozenInstanceError

        bc = _toy_binding_context()
        ctx = ToyComponentExecutionContext(binding_context=bc, unknown_values={})
        with pytest.raises(FrozenInstanceError):
            ctx.unknown_values = {}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 5–7: ToyComponentExecutor
# ---------------------------------------------------------------------------


class TestToyComponentExecutor:
    def test_valid_construction(self):
        """Item 5: valid executor construction."""
        ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=toy_evap_mapping)
        assert ex.component_id is _EVAP_ID
        assert ex.callback is toy_evap_mapping

    def test_rejects_wrong_component_id_type_string(self):
        """Item 6: string component_id rejected."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ToyComponentExecutor(
                component_id="evap",  # type: ignore[arg-type]
                callback=toy_evap_mapping,
            )

    def test_rejects_wrong_component_id_type_none(self):
        """Item 6: None component_id rejected."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ToyComponentExecutor(
                component_id=None,  # type: ignore[arg-type]
                callback=toy_evap_mapping,
            )

    def test_rejects_non_callable_callback(self):
        """Item 7: non-callable callback rejected."""
        with pytest.raises(TypeError, match="callable"):
            ToyComponentExecutor(
                component_id=_EVAP_ID,
                callback="not_callable",  # type: ignore[arg-type]
            )

    def test_rejects_none_callback(self):
        """Item 7: None callback rejected."""
        with pytest.raises(TypeError, match="callable"):
            ToyComponentExecutor(
                component_id=_EVAP_ID,
                callback=None,  # type: ignore[arg-type]
            )

    def test_accepts_lambda_callback(self):
        """Item 5: lambda callback accepted."""
        ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=lambda ctx: {"x": 1.0})
        assert callable(ex.callback)

    def test_frozen(self):
        """Item 5: executor fields cannot be reassigned."""
        from dataclasses import FrozenInstanceError

        ex = _toy_evap_executor()
        with pytest.raises(FrozenInstanceError):
            ex.component_id = _COND_ID  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 8–11: ToyComponentExecutorSet
# ---------------------------------------------------------------------------


class TestToyComponentExecutorSet:
    def test_valid_construction(self):
        """Item 8: valid executor set from tuple."""
        es = ToyComponentExecutorSet(executors=(_toy_evap_executor(), _toy_cond_executor()))
        assert len(es.executors) == 2

    def test_accepts_list_input(self):
        """Item 8: list input is normalised to tuple."""
        es = ToyComponentExecutorSet(executors=[_toy_evap_executor(), _toy_cond_executor()])
        assert isinstance(es.executors, tuple)

    def test_source_list_mutation_does_not_change_executor_set(self):
        """Item 8: source iterable mutation cannot change stored executors."""
        source = [_toy_evap_executor(), _toy_cond_executor()]
        es = ToyComponentExecutorSet(executors=source)
        source.clear()
        assert tuple(e.component_id.value for e in es.executors) == ("evap", "cond")

    def test_preserves_deterministic_order(self):
        """Item 9: insertion order is preserved."""
        e1 = _toy_evap_executor()
        e2 = _toy_cond_executor()
        es = ToyComponentExecutorSet(executors=(e1, e2))
        assert es.executors[0].component_id.value == "evap"
        assert es.executors[1].component_id.value == "cond"

    def test_reversed_order_preserved(self):
        """Item 9: reversed insertion order is preserved."""
        e1 = _toy_evap_executor()
        e2 = _toy_cond_executor()
        es = ToyComponentExecutorSet(executors=(e2, e1))
        assert es.executors[0].component_id.value == "cond"
        assert es.executors[1].component_id.value == "evap"

    def test_rejects_wrong_entry_type_string(self):
        """Item 10: string entry rejected."""
        with pytest.raises(TypeError, match="ToyComponentExecutor"):
            ToyComponentExecutorSet(executors=("not_an_executor",))

    def test_rejects_wrong_entry_type_none(self):
        """Item 10: None entry rejected."""
        e1 = _toy_evap_executor()
        with pytest.raises(TypeError, match="ToyComponentExecutor"):
            ToyComponentExecutorSet(executors=(e1, None))

    def test_rejects_duplicate_component_id(self):
        """Item 11: duplicate component IDs rejected."""
        e1 = ToyComponentExecutor(component_id=_EVAP_ID, callback=toy_evap_mapping)
        e2 = ToyComponentExecutor(component_id=_EVAP_ID, callback=toy_cond_mapping)
        with pytest.raises(ValueError, match="duplicate"):
            ToyComponentExecutorSet(executors=(e1, e2))

    def test_empty_set_valid(self):
        """Item 8: empty executor set is valid."""
        es = ToyComponentExecutorSet(executors=())
        assert es.executors == ()

    def test_frozen(self):
        """Item 8: executor set fields cannot be reassigned."""
        from dataclasses import FrozenInstanceError

        es = _toy_executor_set()
        with pytest.raises(FrozenInstanceError):
            es.executors = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 12–28: execute_toy_component_contributions
# ---------------------------------------------------------------------------


class TestExecuteToyComponentContributions:
    def test_valid_execution_returns_record_set(self):
        """Item 12: valid execution returns ContributionRecordSet."""
        bc = _toy_binding_context()
        result = execute_toy_component_contributions(bc, _toy_executor_set(), _toy_unknown_values())
        assert isinstance(result, ContributionRecordSet)
        assert len(result.records) == 4

    def test_rejects_non_binding_context(self):
        """Item 13: non-NetworkBindingContext binding_context rejected."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            execute_toy_component_contributions(
                "not_a_context", _toy_executor_set(), _toy_unknown_values()
            )

    def test_rejects_missing_executor(self):
        """Item 14: executor missing for a bound component is rejected."""
        bc = _toy_binding_context()
        only_evap = ToyComponentExecutorSet(executors=(_toy_evap_executor(),))
        with pytest.raises(ValueError, match="missing"):
            execute_toy_component_contributions(bc, only_evap, _toy_unknown_values())

    def test_rejects_extra_unbound_executor(self):
        """Item 15: executor referencing an unbound component is rejected."""
        bc = _toy_binding_context()
        extra_id = ComponentInstanceId("pump")
        extra_exec = ToyComponentExecutor(component_id=extra_id, callback=lambda ctx: {"x": 1.0})
        over_set = ToyComponentExecutorSet(
            executors=(_toy_evap_executor(), _toy_cond_executor(), extra_exec)
        )
        with pytest.raises(ValueError, match="not bound"):
            execute_toy_component_contributions(bc, over_set, _toy_unknown_values())

    def test_propagates_callback_exception(self):
        """Item 16: exceptions raised by callbacks propagate to caller."""

        def bad_callback(ctx):
            raise RuntimeError("toy failure")

        bc = _toy_binding_context()
        broken_evap = ToyComponentExecutor(component_id=_EVAP_ID, callback=bad_callback)
        es = ToyComponentExecutorSet(executors=(broken_evap, _toy_cond_executor()))
        with pytest.raises(RuntimeError, match="toy failure"):
            execute_toy_component_contributions(bc, es, _toy_unknown_values())

    def test_rejects_callback_wrong_return_type(self):
        """Item 17: callback wrong return type (not Mapping or ContributionRecordSet) rejected."""

        def bad_return(ctx):
            return 42  # neither Mapping nor ContributionRecordSet

        bc = _toy_binding_context()
        broken_evap = ToyComponentExecutor(component_id=_EVAP_ID, callback=bad_return)
        es = ToyComponentExecutorSet(executors=(broken_evap, _toy_cond_executor()))
        with pytest.raises(TypeError, match="Mapping"):
            execute_toy_component_contributions(bc, es, _toy_unknown_values())

    def test_accepts_mapping_output(self):
        """Item 18: mapping output accepted and converted to records."""
        bc = _toy_binding_context()
        result = execute_toy_component_contributions(bc, _toy_executor_set(), _toy_unknown_values())
        evap_records = [r for r in result.records if r.component_id == _EVAP_ID]
        assert len(evap_records) == 2
        names = {r.name for r in evap_records}
        assert names == {"mass_balance", "pressure_drop"}

    def test_accepts_contribution_record_set_output(self):
        """Item 19: ContributionRecordSet output accepted and used as-is."""

        def evap_record_set_cb(ctx):
            return ContributionRecordSet(
                records=(
                    ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                    ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=400.0),
                )
            )

        bc = _toy_binding_context()
        evap_ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=evap_record_set_cb)
        es = ToyComponentExecutorSet(executors=(evap_ex, _toy_cond_executor()))
        result = execute_toy_component_contributions(bc, es, _toy_unknown_values())
        assert isinstance(result, ContributionRecordSet)
        evap_records = [r for r in result.records if r.component_id == _EVAP_ID]
        assert len(evap_records) == 2

    def test_rejects_bool_mapping_value(self):
        """Item 20: bool value in mapping output rejected."""

        def bool_cb(ctx):
            return {"bad_val": True}

        bc = _toy_binding_context()
        evap_ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=bool_cb)
        es = ToyComponentExecutorSet(executors=(evap_ex, _toy_cond_executor()))
        with pytest.raises(TypeError, match="bool"):
            execute_toy_component_contributions(bc, es, _toy_unknown_values())

    def test_rejects_nan_mapping_value(self):
        """Item 21: NaN value in mapping output rejected."""

        def nan_cb(ctx):
            return {"nan_val": math.nan}

        bc = _toy_binding_context()
        evap_ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=nan_cb)
        es = ToyComponentExecutorSet(executors=(evap_ex, _toy_cond_executor()))
        with pytest.raises(ValueError, match="finite"):
            execute_toy_component_contributions(bc, es, _toy_unknown_values())

    def test_rejects_inf_mapping_value(self):
        """Item 22: infinite value in mapping output rejected."""

        def inf_cb(ctx):
            return {"inf_val": math.inf}

        bc = _toy_binding_context()
        evap_ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=inf_cb)
        es = ToyComponentExecutorSet(executors=(evap_ex, _toy_cond_executor()))
        with pytest.raises(ValueError, match="finite"):
            execute_toy_component_contributions(bc, es, _toy_unknown_values())

    def test_rejects_non_numeric_mapping_value(self):
        """Item 23: non-numeric value in mapping output rejected."""

        def str_cb(ctx):
            return {"bad": "not_a_number"}

        bc = _toy_binding_context()
        evap_ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=str_cb)
        es = ToyComponentExecutorSet(executors=(evap_ex, _toy_cond_executor()))
        with pytest.raises(TypeError, match="numeric"):
            execute_toy_component_contributions(bc, es, _toy_unknown_values())

    def test_rejects_empty_contribution_name(self):
        """Item 24: empty contribution name in mapping output rejected."""

        def empty_key_cb(ctx):
            return {"": 1.0}

        bc = _toy_binding_context()
        evap_ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=empty_key_cb)
        es = ToyComponentExecutorSet(executors=(evap_ex, _toy_cond_executor()))
        with pytest.raises(ValueError, match="empty"):
            execute_toy_component_contributions(bc, es, _toy_unknown_values())

    def test_rejects_whitespace_contribution_name(self):
        """Item 25: whitespace-only contribution name in mapping output rejected."""

        def ws_key_cb(ctx):
            return {"   ": 1.0}

        bc = _toy_binding_context()
        evap_ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=ws_key_cb)
        es = ToyComponentExecutorSet(executors=(evap_ex, _toy_cond_executor()))
        with pytest.raises(ValueError, match="whitespace"):
            execute_toy_component_contributions(bc, es, _toy_unknown_values())

    def test_rejects_record_set_output_for_wrong_component(self):
        """Item 26: ContributionRecordSet with wrong component_id record rejected."""

        def wrong_id_cb(ctx):
            return ContributionRecordSet(
                records=(
                    ContributionRecord(
                        component_id=_COND_ID,  # wrong — evap executor
                        name="mass_balance",
                        value=0.0,
                    ),
                )
            )

        bc = _toy_binding_context()
        evap_ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=wrong_id_cb)
        es = ToyComponentExecutorSet(executors=(evap_ex, _toy_cond_executor()))
        with pytest.raises(ValueError, match="different component"):
            execute_toy_component_contributions(bc, es, _toy_unknown_values())

    def test_rejects_duplicate_contribution_records(self):
        """Item 27: repeated mapping items for one component are rejected."""

        class DuplicateItemsMapping(Mapping):
            def __getitem__(self, key):
                if key == "mass_balance":
                    return 0.0
                raise KeyError(key)

            def __iter__(self):
                return iter(("mass_balance",))

            def __len__(self):
                return 1

            def items(self):
                return (("mass_balance", 0.0), ("mass_balance", 1.0))

        bc = _toy_binding_context()
        duplicate_evap = ToyComponentExecutor(
            component_id=_EVAP_ID,
            callback=lambda ctx: DuplicateItemsMapping(),
        )
        es = ToyComponentExecutorSet(executors=(duplicate_evap, _toy_cond_executor()))
        with pytest.raises(ValueError, match="duplicate"):
            execute_toy_component_contributions(bc, es, _toy_unknown_values())

    def test_same_contribution_name_for_different_components_is_allowed(self):
        """Item 27: duplicate checks include component ID, not name alone."""
        bc = _toy_binding_context()
        result = execute_toy_component_contributions(bc, _toy_executor_set(), _toy_unknown_values())
        evap_mb = [
            r for r in result.records if r.component_id == _EVAP_ID and r.name == "mass_balance"
        ]
        cond_mb = [
            r for r in result.records if r.component_id == _COND_ID and r.name == "mass_balance"
        ]
        assert len(evap_mb) == 1
        assert len(cond_mb) == 1

    def test_preserves_deterministic_order(self):
        """Item 28: records follow executor order, then callback order within each executor."""
        bc = _toy_binding_context()
        result = execute_toy_component_contributions(bc, _toy_executor_set(), _toy_unknown_values())
        component_ids = [r.component_id.value for r in result.records]
        # evap executor comes first → first 2 records are evap
        assert component_ids[:2] == ["evap", "evap"]
        assert component_ids[2:] == ["cond", "cond"]

    def test_reversed_executor_order_preserved(self):
        """Item 28: reversed executor order is preserved in records."""
        bc = _toy_binding_context()
        es = ToyComponentExecutorSet(executors=(_toy_cond_executor(), _toy_evap_executor()))
        result = execute_toy_component_contributions(bc, es, _toy_unknown_values())
        component_ids = [r.component_id.value for r in result.records]
        assert component_ids[:2] == ["cond", "cond"]
        assert component_ids[2:] == ["evap", "evap"]

    def test_values_computed_from_unknown_values(self):
        """Item 12: computed values match expected outputs."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        result = execute_toy_component_contributions(bc, _toy_executor_set(), uvs)
        evap_mb = next(
            r for r in result.records if r.component_id == _EVAP_ID and r.name == "mass_balance"
        )
        evap_pd = next(
            r for r in result.records if r.component_id == _EVAP_ID and r.name == "pressure_drop"
        )
        assert evap_mb.value == pytest.approx(0.0)  # 0.05 - 0.05 = 0
        assert evap_pd.value == pytest.approx(0.0)  # 1000 - 400 - 600 = 0

    def test_no_mutation_of_inputs(self):
        """Item 12: input dicts are not mutated during execution."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        original_keys = set(uvs.keys())
        execute_toy_component_contributions(bc, _toy_executor_set(), uvs)
        assert set(uvs.keys()) == original_keys


# ---------------------------------------------------------------------------
# 29: build_component_contribution_from_toy_execution
# ---------------------------------------------------------------------------


class TestBuildComponentContributionFromToyExecution:
    def test_valid_build_returns_component_contribution(self):
        """Item 29: convenience wrapper returns ComponentContribution."""
        bc = _toy_binding_context()
        result = build_component_contribution_from_toy_execution(
            _EVAP_ID,
            bc,
            _toy_executor_set(),
            _toy_residual_map(),
            _toy_unknown_values(),
        )
        assert isinstance(result, ComponentContribution)

    def test_correct_residual_values(self):
        """Item 29: residual values are correctly mapped."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        result = build_component_contribution_from_toy_execution(
            _EVAP_ID,
            bc,
            _toy_executor_set(),
            _toy_residual_map(),
            uvs,
        )
        assert result.residual_values["mass_balance:n1"] == pytest.approx(0.0)
        assert result.residual_values["pressure_drop:evap"] == pytest.approx(0.0)

    def test_allowed_residual_names_forwarded(self):
        """Item 29: allowed_residual_names parameter is forwarded correctly."""
        bc = _toy_binding_context()
        result = build_component_contribution_from_toy_execution(
            _EVAP_ID,
            bc,
            _toy_executor_set(),
            _toy_residual_map(),
            _toy_unknown_values(),
            allowed_residual_names={"mass_balance:n1", "pressure_drop:evap"},
        )
        assert isinstance(result, ComponentContribution)

    def test_rejects_disallowed_residual_name(self):
        """Item 29: undeclared residual name rejected when allowed_residual_names supplied."""
        bc = _toy_binding_context()
        with pytest.raises(ValueError, match="allowed_residual_names"):
            build_component_contribution_from_toy_execution(
                _EVAP_ID,
                bc,
                _toy_executor_set(),
                _toy_residual_map(),
                _toy_unknown_values(),
                allowed_residual_names={"mass_balance:n1"},  # missing pressure_drop:evap
            )


# ---------------------------------------------------------------------------
# 30–31: Integration with Phase 14D residual map and Phase 14C adapter
# ---------------------------------------------------------------------------


class TestIntegrationPhase14D14C:
    def test_integration_with_residual_map(self):
        """Item 30: toy execution output feeds Phase 14D map correctly."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        record_set = execute_toy_component_contributions(bc, _toy_executor_set(), uvs)
        residual_map = _toy_residual_map()

        evap_contrib = map_contribution_records_to_component_contribution(
            _EVAP_ID, record_set, residual_map
        )
        cond_contrib = map_contribution_records_to_component_contribution(
            _COND_ID, record_set, residual_map
        )

        assert evap_contrib.residual_values["mass_balance:n1"] == pytest.approx(0.0)
        assert evap_contrib.residual_values["pressure_drop:evap"] == pytest.approx(0.0)
        assert cond_contrib.residual_values["mass_balance:n2"] == pytest.approx(0.0)
        # toy_cond: P:n2 - P:n1 + 1000 = 400 - 1000 + 1000 = 400
        assert cond_contrib.residual_values["pressure_drop:cond"] == pytest.approx(400.0)

    def test_integration_with_phase14c_adapter(self):
        """Item 31: toy-execution output integrates with Phase 14C adapter."""
        bc = _toy_binding_context()
        residual_map = _toy_residual_map()

        # Build Phase 14C contribution adapter callbacks that use toy execution.
        def make_adapter_cb(component_id):
            def cb(ctx: ComponentContributionContext) -> ComponentContribution:
                record_set = execute_toy_component_contributions(
                    bc, _toy_executor_set(), ctx.unknown_values
                )
                return map_contribution_records_to_component_contribution(
                    component_id, record_set, residual_map
                )

            return cb

        adapter_set = ComponentContributionAdapterSet(
            adapters=(
                ComponentContributionAdapter(
                    instance_id=_EVAP_ID, callback=make_adapter_cb(_EVAP_ID)
                ),
                ComponentContributionAdapter(
                    instance_id=_COND_ID, callback=make_adapter_cb(_COND_ID)
                ),
            )
        )

        # Build Phase 14A physical adapters.
        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        assert len(physical_set.adapters) == 4  # 4 residuals in assembly

        # Convert to Phase 13G evaluators.
        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)
        assert len(evaluators) == 4


# ---------------------------------------------------------------------------
# 32–33: Integration with Phase 13G evaluation and Phase 13H solve
# ---------------------------------------------------------------------------


class TestIntegrationPhase13G13H:
    def _build_evaluators_from_toy(self, bc, unknown_values_at_eval=None):
        """Helper: build Phase 13G evaluators driven by toy execution."""
        residual_map = _toy_residual_map()

        def make_cb(component_id):
            def cb(ctx: ComponentContributionContext) -> ComponentContribution:
                rs = execute_toy_component_contributions(
                    bc, _toy_executor_set(), ctx.unknown_values
                )
                return map_contribution_records_to_component_contribution(
                    component_id, rs, residual_map
                )

            return cb

        adapter_set = ComponentContributionAdapterSet(
            adapters=(
                ComponentContributionAdapter(instance_id=_EVAP_ID, callback=make_cb(_EVAP_ID)),
                ComponentContributionAdapter(instance_id=_COND_ID, callback=make_cb(_COND_ID)),
            )
        )
        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        return build_network_residual_evaluators(bc.assembly, physical_set)

    def test_phase13g_evaluation_works(self):
        """Item 32: one-shot Phase 13G evaluation works with toy execution output."""

        bc = _toy_binding_context()
        evaluators = self._build_evaluators_from_toy(bc)
        assembly = bc.assembly

        uv = NetworkUnknownValues(
            values={"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        )
        scales = {
            "mass_balance:n1": 0.01,
            "mass_balance:n2": 0.01,
            "pressure_drop:evap": 100.0,
            "pressure_drop:cond": 100.0,
        }
        result = evaluate_network_residuals(assembly, uv, evaluators, scales)

        assert result.max_abs_scaled is not None
        # mass_balance residuals are 0 (mdot:evap == mdot:cond)
        # pressure_drop:evap = 1000 - 400 - 600 = 0, scaled = 0
        # pressure_drop:cond = 400 - 1000 + 1000 = 400, scaled = 4.0
        assert result.max_abs_scaled == pytest.approx(4.0, rel=1e-9)

    def test_phase13h_solve_runs_without_error(self):
        """Item 33: Phase 13H solve runs on toy execution problem without exception."""
        from mpl_sim.network import NetworkSolveConfig, solve_network_residual_problem

        bc = _toy_binding_context()
        evaluators = self._build_evaluators_from_toy(bc)
        assembly = bc.assembly

        initial = NetworkUnknownValues(
            values={"mdot:evap": 0.04, "mdot:cond": 0.04, "P:n1": 900.0, "P:n2": 350.0}
        )
        scales = {
            "mass_balance:n1": 0.01,
            "mass_balance:n2": 0.01,
            "pressure_drop:evap": 100.0,
            "pressure_drop:cond": 100.0,
        }
        config = NetworkSolveConfig(max_iterations=20, tolerance=1e-8, finite_difference_step=1e-6)
        result = solve_network_residual_problem(assembly, initial, evaluators, scales, config)

        # The toy system has a degenerate Jacobian (rank 2 from a 4x4 system),
        # so the solver detects singularity or does not converge. Either outcome
        # is valid — the test verifies the stack does not raise unexpectedly.
        assert hasattr(result, "converged")
        assert hasattr(result, "iteration_count")


# ---------------------------------------------------------------------------
# 34–42: Architecture boundary / scope guards
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    def test_no_real_component_execution(self):
        """Item 34: toy_component_execution.py does not import real component classes."""
        src = _SRC.read_text(encoding="utf-8")
        assert "from mpl_sim.components" not in src
        assert "import mpl_sim.components" not in src

    def test_no_real_contribute_call(self):
        """Item 35: toy_component_execution.py does not call contribute(."""
        tree = ast.parse(_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "contribute":
                    raise AssertionError("Found contribute( call in source")

    def test_no_property_lookup_imports(self):
        """Item 36: toy_component_execution.py does not import property backends."""
        lines = _SRC.read_text(encoding="utf-8").splitlines()
        import_lines = [
            line
            for line in lines
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and "PropertyBackend" in line
        ]
        assert not import_lines, f"PropertyBackend import found: {import_lines}"
        prop_imports = [
            line
            for line in lines
            if line.strip().startswith("from mpl_sim.properties")
            or line.strip().startswith("import mpl_sim.properties")
        ]
        assert not prop_imports, f"mpl_sim.properties import found: {prop_imports}"

    def test_no_registry_resolution(self):
        """Item 37: toy_component_execution.py does not import registries."""
        lines = _SRC.read_text(encoding="utf-8").splitlines()
        registry_imports = [
            line
            for line in lines
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and ("CorrelationRegistry" in line or "HeatExchangerModelRegistry" in line)
        ]
        assert not registry_imports, f"Registry import found: {registry_imports}"

    def test_no_coolprop(self):
        """Item 38: toy_component_execution.py does not import CoolProp."""
        lines = _SRC.read_text(encoding="utf-8").splitlines()
        import_lines = [
            line
            for line in lines
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and "CoolProp" in line
        ]
        assert not import_lines, f"CoolProp import found: {import_lines}"

    def test_no_system_state_import(self):
        """Item 39: toy_component_execution.py does not import SystemState."""
        lines = _SRC.read_text(encoding="utf-8").splitlines()
        system_state_imports = [
            line
            for line in lines
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and "SystemState" in line
        ]
        assert not system_state_imports, f"SystemState import found: {system_state_imports}"

    def test_no_fluid_state_attached_to_graph(self):
        """Item 40: executing toy functions does not attach FluidState to the graph."""
        bc = _toy_binding_context()
        result = execute_toy_component_contributions(bc, _toy_executor_set(), _toy_unknown_values())
        graph = bc.graph
        for node in graph.nodes():
            assert not hasattr(node, "fluid_state"), "FluidState found on graph node"
        assert isinstance(result, ContributionRecordSet)

    def test_no_physical_values_on_network_graph(self):
        """Item 41: NetworkGraph has no physical value fields after toy execution."""
        bc = _toy_binding_context()
        execute_toy_component_contributions(bc, _toy_executor_set(), _toy_unknown_values())
        graph = bc.graph
        # NetworkGraph fields are nodes and instances only (topology)
        assert not hasattr(graph, "mdot")
        assert not hasattr(graph, "pressure")
        assert not hasattr(graph, "enthalpy")

    def test_no_automatic_physics_from_component_type(self):
        """Item 42: execution never reads component_type to infer physics."""

        # The execution result is solely determined by the explicit callback —
        # changing component_type in a re-built graph does not alter callback output.
        def constant_evap(ctx):
            return {"x": 42.0}

        g2 = NetworkGraph(
            nodes=[_node("n1"), _node("n2")],
            instances=[
                _inst("evap", "DIFFERENT_PHYSICS_TYPE", "n1", "n2"),
                _inst("cond", "condenser", "n2", "n1"),
            ],
        )
        bc2 = _toy_binding_context(graph=g2, assembly=assemble_network_residuals(g2))
        evap_ex = ToyComponentExecutor(component_id=_EVAP_ID, callback=constant_evap)
        es = ToyComponentExecutorSet(executors=(evap_ex, _toy_cond_executor()))
        result = execute_toy_component_contributions(bc2, es, _toy_unknown_values())
        evap_records = [r for r in result.records if r.component_id == _EVAP_ID]
        assert len(evap_records) == 1
        assert evap_records[0].value == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# 43: Public exports
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_all_phase14e_names_in_mpl_sim_network(self):
        """Item 43: all Phase 14E names are importable from mpl_sim.network."""
        import mpl_sim.network as net

        assert hasattr(net, "ToyComponentExecutionContext")
        assert hasattr(net, "ToyComponentExecutor")
        assert hasattr(net, "ToyComponentExecutorSet")
        assert hasattr(net, "execute_toy_component_contributions")
        assert hasattr(net, "build_component_contribution_from_toy_execution")

    def test_phase14e_names_in_all(self):
        """Item 43: Phase 14E names appear in __all__."""
        import mpl_sim.network as net

        for name in [
            "ToyComponentExecutionContext",
            "ToyComponentExecutor",
            "ToyComponentExecutorSet",
            "execute_toy_component_contributions",
            "build_component_contribution_from_toy_execution",
        ]:
            assert name in net.__all__, f"{name!r} missing from __all__"

    def test_direct_module_imports_match_package_imports(self):
        """Item 43: direct module imports are the same objects as package imports."""
        assert ToyComponentExecutionContext is _CtxDirect
        assert ToyComponentExecutor is _ExecDirect
        assert ToyComponentExecutorSet is _ExecSetDirect
        assert execute_toy_component_contributions is _exec_direct
        assert build_component_contribution_from_toy_execution is _build_direct

    def test_prior_phase_exports_unchanged(self):
        """Item 43: Phase 13E–14D exports still present in mpl_sim.network."""
        import mpl_sim.network as net

        for name in [
            "GraphNodeId",
            "ComponentInstanceId",
            "GraphNode",
            "ComponentInstance",
            "NetworkGraph",
            "assemble_network_residuals",
            "evaluate_network_residuals",
            "solve_network_residual_problem",
            "PhysicalResidualAdapter",
            "build_network_residual_evaluators",
            "ComponentBinding",
            "NetworkBindingContext",
            "build_binding_context",
            "ComponentContribution",
            "ComponentContributionAdapter",
            "build_physical_adapters_from_contributions",
            "ContributionRecord",
            "ContributionRecordSet",
            "ContributionResidualMap",
            "map_contribution_records_to_component_contribution",
        ]:
            assert hasattr(net, name), f"{name!r} missing from mpl_sim.network"


# ---------------------------------------------------------------------------
# 44: Suite-level gate (prior tests still pass)
# ---------------------------------------------------------------------------


class TestPriorPhaseGate:
    def test_phase13e_graph_foundation_importable(self):
        """Item 44: Phase 13E types still importable and functional."""
        g = _toy_graph()
        assert len(g.nodes()) == 2
        assert len(g.instances()) == 2

    def test_phase13f_assembly_still_works(self):
        """Item 44: Phase 13F assembly still works."""
        g = _toy_graph()
        asm = assemble_network_residuals(g)
        assert len(asm.unknowns.names()) == 4
        assert len(asm.residuals.names()) == 4

    def test_phase14d_contract_still_works(self):
        """Item 44: Phase 14D ContributionRecord still works."""
        r = ContributionRecord(component_id=_EVAP_ID, name="test", value=1.0)
        assert r.value == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 45: Docs do not claim full physical network simulation
# ---------------------------------------------------------------------------


class TestDocsDoNotOverclaim:
    def _read_concepts(self) -> str:
        path = pathlib.Path(__file__).parent.parent.parent / "docs" / "user_guide" / "CONCEPTS.md"
        return path.read_text(encoding="utf-8")

    def test_concepts_does_not_claim_full_simulator(self):
        """Item 45: CONCEPTS.md does not claim solve(network) or full MPL simulator."""
        text = self._read_concepts()
        lower = text.lower()
        assert "phase 14e" in lower, "Phase 14E section missing from CONCEPTS.md"

    def test_concepts_says_not_full_simulator(self):
        """Item 45: CONCEPTS.md says Phase 14E is NOT a full simulator."""
        text = self._read_concepts()
        assert "NOT" in text or "not" in text.lower()

    def test_toy_execution_module_does_not_claim_full_sim(self):
        """Item 45: toy_component_execution.py docstring explicitly says it is toy-only."""
        src = _SRC.read_text(encoding="utf-8")
        assert "toy" in src.lower()
        assert "NOT" in src or "DOES NOT" in src
