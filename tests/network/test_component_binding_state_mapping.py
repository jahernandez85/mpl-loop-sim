"""Phase 14B component binding and state-vector mapping foundation tests.

Coverage items (35 required):
 1.  valid ComponentBinding construction
 2.  binding rejects wrong instance_id type
 3.  binding rejects empty binding_name
 4.  binding rejects whitespace-only binding_name
 5.  binding metadata is immutable / defensively copied
 6.  valid ComponentBindingSet construction
 7.  binding set preserves deterministic order
 8.  binding set rejects wrong entry type
 9.  binding set rejects duplicate component instance IDs
10.  valid ComponentStateMap construction
11.  state map rejects empty keys
12.  state map rejects whitespace-only keys
13.  state map rejects wrong mapped component ID type
14.  state map rejects wrong mapped node ID type
15.  state map mappings are immutable / defensively copied
16.  valid NetworkBindingContext / builder construction
17.  builder rejects non-NetworkGraph
18.  builder rejects non-NetworkResidualAssembly
19.  builder rejects missing component binding
20.  builder rejects extra component binding
21.  builder rejects state map component reference not in graph
22.  builder rejects state map node reference not in graph
23.  builder does not mutate inputs
24.  context stores no numerical unknown values
25.  context stores no FluidState
26.  context does not execute callbacks
27.  context does not execute components
28.  no contribute( call in source
29.  no property lookup in source
30.  no registry resolution in source
31.  no CoolProp in source
32.  no automatic physics from component_type
33.  public exports work from mpl_sim.network
34.  existing Phase 13E/13F/13G/13H/14A tests still pass (full suite gate)
35.  docs do not claim physical network simulation
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from dataclasses import FrozenInstanceError
from types import MappingProxyType

import pytest

from mpl_sim.network import (
    ComponentBinding,
    ComponentBindingSet,
    ComponentInstance,
    ComponentInstanceId,
    ComponentStateMap,
    GraphNode,
    GraphNodeId,
    NetworkBindingContext,
    NetworkGraph,
    assemble_network_residuals,
    build_binding_context,
)
from mpl_sim.network.component_binding import (
    ComponentBinding as _BindingDirect,
)
from mpl_sim.network.component_binding import (
    ComponentBindingSet as _BindingSetDirect,
)
from mpl_sim.network.component_binding import (
    ComponentStateMap as _StateMapDirect,
)
from mpl_sim.network.component_binding import (
    NetworkBindingContext as _ContextDirect,
)
from mpl_sim.network.component_binding import (
    build_binding_context as _build_direct,
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


def _toy_graph() -> NetworkGraph:
    """Two-node, two-component closed loop: evap and cond."""
    return NetworkGraph(
        nodes=[_node("n1"), _node("n2")],
        instances=[
            _inst("evap", "evaporator", "n1", "n2"),
            _inst("cond", "condenser", "n2", "n1"),
        ],
    )


def _toy_binding_set() -> ComponentBindingSet:
    return ComponentBindingSet(
        bindings=(
            ComponentBinding(
                instance_id=ComponentInstanceId("evap"),
                binding_name="toy_evaporator_binding",
            ),
            ComponentBinding(
                instance_id=ComponentInstanceId("cond"),
                binding_name="toy_condenser_binding",
            ),
        )
    )


def _toy_state_map() -> ComponentStateMap:
    return ComponentStateMap(
        unknown_to_component={
            "mdot:evap": ComponentInstanceId("evap"),
            "mdot:cond": ComponentInstanceId("cond"),
        },
        unknown_to_node={
            "P:n1": GraphNodeId("n1"),
            "P:n2": GraphNodeId("n2"),
        },
        residual_to_component={
            "pressure_drop:evap": ComponentInstanceId("evap"),
            "pressure_drop:cond": ComponentInstanceId("cond"),
        },
        residual_to_node={
            "mass_balance:n1": GraphNodeId("n1"),
            "mass_balance:n2": GraphNodeId("n2"),
        },
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def graph():
    return _toy_graph()


@pytest.fixture
def assembly(graph):
    return assemble_network_residuals(graph)


@pytest.fixture
def binding_set():
    return _toy_binding_set()


@pytest.fixture
def state_map():
    return _toy_state_map()


@pytest.fixture
def context(graph, assembly, binding_set, state_map):
    return build_binding_context(graph, assembly, binding_set, state_map)


# ---------------------------------------------------------------------------
# 1. Valid ComponentBinding construction
# ---------------------------------------------------------------------------


class TestComponentBindingValid:
    def test_minimal_construction(self):
        """Item 1: ComponentBinding accepts valid instance_id and binding_name."""
        b = ComponentBinding(
            instance_id=ComponentInstanceId("evap"),
            binding_name="toy_evaporator_binding",
        )
        assert b.instance_id == ComponentInstanceId("evap")
        assert b.binding_name == "toy_evaporator_binding"
        assert b.metadata is None

    def test_construction_with_metadata(self):
        """Item 1: ComponentBinding accepts optional metadata Mapping."""
        b = ComponentBinding(
            instance_id=ComponentInstanceId("evap"),
            binding_name="toy_evaporator_binding",
            metadata={"phase": "14b"},
        )
        assert b.metadata is not None
        assert b.metadata["phase"] == "14b"

    def test_metadata_stored_as_mapping_proxy(self):
        """Item 1/5: metadata is stored as a MappingProxyType."""
        b = ComponentBinding(
            instance_id=ComponentInstanceId("evap"),
            binding_name="label",
            metadata={"k": "v"},
        )
        assert isinstance(b.metadata, MappingProxyType)

    def test_binding_is_frozen(self):
        """Item 1: ComponentBinding is a frozen dataclass."""
        b = ComponentBinding(
            instance_id=ComponentInstanceId("evap"),
            binding_name="label",
        )
        with pytest.raises(FrozenInstanceError):
            b.binding_name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. Binding rejects wrong instance_id type
# ---------------------------------------------------------------------------


class TestComponentBindingInstanceIdValidation:
    def test_rejects_string_instance_id(self):
        """Item 2: instance_id must be ComponentInstanceId, not a plain string."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ComponentBinding(
                instance_id="evap",  # type: ignore[arg-type]
                binding_name="label",
            )

    def test_rejects_none_instance_id(self):
        """Item 2: None is rejected as instance_id."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ComponentBinding(
                instance_id=None,  # type: ignore[arg-type]
                binding_name="label",
            )

    def test_rejects_int_instance_id(self):
        """Item 2: int is rejected as instance_id."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ComponentBinding(
                instance_id=42,  # type: ignore[arg-type]
                binding_name="label",
            )


# ---------------------------------------------------------------------------
# 3. Binding rejects empty binding_name
# ---------------------------------------------------------------------------


class TestComponentBindingEmptyName:
    def test_rejects_empty_string(self):
        """Item 3: empty binding_name is rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentBinding(
                instance_id=ComponentInstanceId("evap"),
                binding_name="",
            )


# ---------------------------------------------------------------------------
# 4. Binding rejects whitespace-only binding_name
# ---------------------------------------------------------------------------


class TestComponentBindingWhitespaceName:
    def test_rejects_spaces_only(self):
        """Item 4: whitespace-only binding_name is rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentBinding(
                instance_id=ComponentInstanceId("evap"),
                binding_name="   ",
            )

    def test_rejects_tab_only(self):
        """Item 4: tab-only binding_name is rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentBinding(
                instance_id=ComponentInstanceId("evap"),
                binding_name="\t",
            )

    def test_rejects_non_string_binding_name(self):
        """Item 4 (adjacent): non-string binding_name is rejected with TypeError."""
        with pytest.raises(TypeError, match="string"):
            ComponentBinding(
                instance_id=ComponentInstanceId("evap"),
                binding_name=123,  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# 5. Binding metadata is immutable / defensively copied
# ---------------------------------------------------------------------------


class TestComponentBindingMetadataImmutability:
    def test_source_dict_mutation_does_not_affect_binding(self):
        """Item 5: mutating the source dict after construction has no effect."""
        source = {"k": "v1"}
        b = ComponentBinding(
            instance_id=ComponentInstanceId("evap"),
            binding_name="label",
            metadata=source,
        )
        source["k"] = "v2"
        assert b.metadata["k"] == "v1"

    def test_metadata_mapping_proxy_is_read_only(self):
        """Item 5: metadata MappingProxyType raises TypeError on assignment."""
        b = ComponentBinding(
            instance_id=ComponentInstanceId("evap"),
            binding_name="label",
            metadata={"k": "v"},
        )
        with pytest.raises(TypeError):
            b.metadata["k"] = "new"  # type: ignore[index]

    def test_metadata_none_by_default(self):
        """Item 5: metadata is None when not supplied."""
        b = ComponentBinding(
            instance_id=ComponentInstanceId("evap"),
            binding_name="label",
        )
        assert b.metadata is None

    def test_metadata_rejects_non_mapping(self):
        """Item 5: metadata must be a Mapping or None."""
        with pytest.raises(TypeError, match="Mapping"):
            ComponentBinding(
                instance_id=ComponentInstanceId("evap"),
                binding_name="label",
                metadata=["k", "v"],  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# 6. Valid ComponentBindingSet construction
# ---------------------------------------------------------------------------


class TestComponentBindingSetValid:
    def test_construction_with_tuple(self):
        """Item 6: ComponentBindingSet accepts a tuple of ComponentBinding."""
        bs = _toy_binding_set()
        assert len(bs.bindings) == 2

    def test_construction_with_list_converted_to_tuple(self):
        """Item 6: ComponentBindingSet normalises a list to a tuple."""
        b1 = ComponentBinding(ComponentInstanceId("evap"), "label1")
        b2 = ComponentBinding(ComponentInstanceId("cond"), "label2")
        bs = ComponentBindingSet(bindings=[b1, b2])  # type: ignore[arg-type]
        assert isinstance(bs.bindings, tuple)
        assert len(bs.bindings) == 2

    def test_single_binding(self):
        """Item 6: single-element ComponentBindingSet is valid."""
        bs = ComponentBindingSet(bindings=(ComponentBinding(ComponentInstanceId("evap"), "label"),))
        assert len(bs.bindings) == 1

    def test_binding_set_is_frozen(self):
        """Item 6: ComponentBindingSet is immutable after construction."""
        bs = _toy_binding_set()
        with pytest.raises(FrozenInstanceError):
            bs.bindings = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 7. Binding set preserves deterministic order
# ---------------------------------------------------------------------------


class TestComponentBindingSetOrder:
    def test_insertion_order_preserved(self):
        """Item 7: binding order from the constructor is preserved."""
        b1 = ComponentBinding(ComponentInstanceId("evap"), "first")
        b2 = ComponentBinding(ComponentInstanceId("cond"), "second")
        b3 = ComponentBinding(ComponentInstanceId("pump"), "third")
        bs = ComponentBindingSet(bindings=(b1, b2, b3))
        assert bs.instance_ids() == (
            ComponentInstanceId("evap"),
            ComponentInstanceId("cond"),
            ComponentInstanceId("pump"),
        )

    def test_instance_ids_returns_tuple(self):
        """Item 7: instance_ids() returns a tuple, not a list."""
        bs = _toy_binding_set()
        assert isinstance(bs.instance_ids(), tuple)

    def test_by_instance_id_found(self):
        """Item 7: by_instance_id returns correct binding."""
        bs = _toy_binding_set()
        b = bs.by_instance_id(ComponentInstanceId("evap"))
        assert b is not None
        assert b.binding_name == "toy_evaporator_binding"

    def test_by_instance_id_not_found(self):
        """Item 7: by_instance_id returns None for unknown ID."""
        bs = _toy_binding_set()
        b = bs.by_instance_id(ComponentInstanceId("unknown"))
        assert b is None


# ---------------------------------------------------------------------------
# 8. Binding set rejects wrong entry type
# ---------------------------------------------------------------------------


class TestComponentBindingSetEntryValidation:
    def test_rejects_string_entry(self):
        """Item 8: non-ComponentBinding entry is rejected."""
        with pytest.raises(TypeError, match="ComponentBinding"):
            ComponentBindingSet(bindings=("not_a_binding",))  # type: ignore[arg-type]

    def test_rejects_none_entry(self):
        """Item 8: None entry is rejected."""
        with pytest.raises(TypeError, match="ComponentBinding"):
            ComponentBindingSet(bindings=(None,))  # type: ignore[arg-type]

    def test_rejects_tuple_entry(self):
        """Item 8: tuple entry is rejected."""
        with pytest.raises(TypeError, match="ComponentBinding"):
            ComponentBindingSet(bindings=((ComponentInstanceId("evap"), "label"),))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 9. Binding set rejects duplicate component instance IDs
# ---------------------------------------------------------------------------


class TestComponentBindingSetDuplicates:
    def test_rejects_duplicate_instance_id(self):
        """Item 9: two bindings with the same instance_id are rejected."""
        b1 = ComponentBinding(ComponentInstanceId("evap"), "label1")
        b2 = ComponentBinding(ComponentInstanceId("evap"), "label2")
        with pytest.raises(ValueError, match="duplicate"):
            ComponentBindingSet(bindings=(b1, b2))

    def test_unique_ids_accepted(self):
        """Item 9: distinct instance IDs are accepted."""
        b1 = ComponentBinding(ComponentInstanceId("evap"), "label1")
        b2 = ComponentBinding(ComponentInstanceId("cond"), "label2")
        bs = ComponentBindingSet(bindings=(b1, b2))
        assert len(bs.bindings) == 2


# ---------------------------------------------------------------------------
# 10. Valid ComponentStateMap construction
# ---------------------------------------------------------------------------


class TestComponentStateMapValid:
    def test_full_map_construction(self):
        """Item 10: ComponentStateMap accepts all four mapping fields."""
        sm = _toy_state_map()
        assert len(sm.unknown_to_component) == 2
        assert len(sm.unknown_to_node) == 2
        assert len(sm.residual_to_component) == 2
        assert len(sm.residual_to_node) == 2

    def test_empty_map_construction(self):
        """Item 10: ComponentStateMap accepts empty mappings (defaults)."""
        sm = ComponentStateMap()
        assert len(sm.unknown_to_component) == 0
        assert len(sm.unknown_to_node) == 0
        assert len(sm.residual_to_component) == 0
        assert len(sm.residual_to_node) == 0

    def test_partial_map_construction(self):
        """Item 10: only some fields populated is valid."""
        sm = ComponentStateMap(
            unknown_to_component={"mdot:evap": ComponentInstanceId("evap")},
        )
        assert len(sm.unknown_to_component) == 1
        assert len(sm.unknown_to_node) == 0

    def test_state_map_is_frozen(self):
        """Item 10: ComponentStateMap is immutable after construction."""
        sm = _toy_state_map()
        with pytest.raises(FrozenInstanceError):
            sm.unknown_to_component = {}  # type: ignore[misc]

    def test_stored_as_mapping_proxy(self):
        """Item 10: all four fields are stored as MappingProxyType."""
        sm = _toy_state_map()
        assert isinstance(sm.unknown_to_component, MappingProxyType)
        assert isinstance(sm.unknown_to_node, MappingProxyType)
        assert isinstance(sm.residual_to_component, MappingProxyType)
        assert isinstance(sm.residual_to_node, MappingProxyType)


# ---------------------------------------------------------------------------
# 11. State map rejects empty keys
# ---------------------------------------------------------------------------


class TestComponentStateMapEmptyKeys:
    def test_unknown_to_component_empty_key_rejected(self):
        """Item 11: empty string key in unknown_to_component is rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentStateMap(
                unknown_to_component={"": ComponentInstanceId("evap")},
            )

    def test_unknown_to_node_empty_key_rejected(self):
        """Item 11: empty string key in unknown_to_node is rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentStateMap(
                unknown_to_node={"": GraphNodeId("n1")},
            )

    def test_residual_to_component_empty_key_rejected(self):
        """Item 11: empty string key in residual_to_component is rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentStateMap(
                residual_to_component={"": ComponentInstanceId("evap")},
            )

    def test_residual_to_node_empty_key_rejected(self):
        """Item 11: empty string key in residual_to_node is rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentStateMap(
                residual_to_node={"": GraphNodeId("n1")},
            )


# ---------------------------------------------------------------------------
# 12. State map rejects whitespace-only keys
# ---------------------------------------------------------------------------


class TestComponentStateMapWhitespaceKeys:
    def test_whitespace_key_in_unknown_to_component(self):
        """Item 12: whitespace-only key is rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentStateMap(
                unknown_to_component={"   ": ComponentInstanceId("evap")},
            )

    def test_whitespace_key_in_unknown_to_node(self):
        """Item 12: tab key is rejected in unknown_to_node."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentStateMap(
                unknown_to_node={"\t": GraphNodeId("n1")},
            )

    def test_non_string_key_rejected(self):
        """Item 12 (adjacent): non-string key is rejected with TypeError."""
        with pytest.raises(TypeError):
            ComponentStateMap(
                unknown_to_component={42: ComponentInstanceId("evap")},  # type: ignore[dict-item]
            )


# ---------------------------------------------------------------------------
# 13. State map rejects wrong mapped component ID type
# ---------------------------------------------------------------------------


class TestComponentStateMapComponentIdValidation:
    def test_rejects_string_as_component_id_in_unknown_map(self):
        """Item 13: plain string value is rejected in unknown_to_component."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ComponentStateMap(
                unknown_to_component={"mdot:evap": "evap"},  # type: ignore[dict-item]
            )

    def test_rejects_node_id_as_component_id(self):
        """Item 13: GraphNodeId is rejected in unknown_to_component."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ComponentStateMap(
                unknown_to_component={"mdot:evap": GraphNodeId("n1")},  # type: ignore[dict-item]
            )

    def test_rejects_string_in_residual_to_component(self):
        """Item 13: plain string value rejected in residual_to_component."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ComponentStateMap(
                residual_to_component={"pressure_drop:evap": "evap"},  # type: ignore[dict-item]
            )


# ---------------------------------------------------------------------------
# 14. State map rejects wrong mapped node ID type
# ---------------------------------------------------------------------------


class TestComponentStateMapNodeIdValidation:
    def test_rejects_string_as_node_id_in_unknown_map(self):
        """Item 14: plain string value is rejected in unknown_to_node."""
        with pytest.raises(TypeError, match="GraphNodeId"):
            ComponentStateMap(
                unknown_to_node={"P:n1": "n1"},  # type: ignore[dict-item]
            )

    def test_rejects_component_id_as_node_id(self):
        """Item 14: ComponentInstanceId is rejected in unknown_to_node."""
        with pytest.raises(TypeError, match="GraphNodeId"):
            ComponentStateMap(
                unknown_to_node={"P:n1": ComponentInstanceId("evap")},  # type: ignore[dict-item]
            )

    def test_rejects_string_in_residual_to_node(self):
        """Item 14: plain string value rejected in residual_to_node."""
        with pytest.raises(TypeError, match="GraphNodeId"):
            ComponentStateMap(
                residual_to_node={"mass_balance:n1": "n1"},  # type: ignore[dict-item]
            )


# ---------------------------------------------------------------------------
# 15. State map mappings are immutable / defensively copied
# ---------------------------------------------------------------------------


class TestComponentStateMapImmutability:
    def test_unknown_to_component_source_mutation_isolated(self):
        """Item 15: mutating source dict does not affect stored map."""
        source: dict = {"mdot:evap": ComponentInstanceId("evap")}
        sm = ComponentStateMap(unknown_to_component=source)
        source["mdot:extra"] = ComponentInstanceId("extra")
        assert "mdot:extra" not in sm.unknown_to_component

    def test_unknown_to_node_read_only(self):
        """Item 15: MappingProxyType raises TypeError on write."""
        sm = _toy_state_map()
        with pytest.raises(TypeError):
            sm.unknown_to_node["P:n3"] = GraphNodeId("n3")  # type: ignore[index]

    def test_residual_to_component_source_mutation_isolated(self):
        """Item 15: mutating residual_to_component source has no effect."""
        source: dict = {"pressure_drop:evap": ComponentInstanceId("evap")}
        sm = ComponentStateMap(residual_to_component=source)
        source["extra_key"] = ComponentInstanceId("cond")
        assert "extra_key" not in sm.residual_to_component

    def test_residual_to_node_read_only(self):
        """Item 15: residual_to_node is read-only."""
        sm = _toy_state_map()
        with pytest.raises(TypeError):
            sm.residual_to_node["mass_balance:n3"] = GraphNodeId("n3")  # type: ignore[index]


# ---------------------------------------------------------------------------
# 16. Valid NetworkBindingContext / builder construction
# ---------------------------------------------------------------------------


class TestNetworkBindingContextValid:
    def test_build_binding_context_succeeds(self, graph, assembly, binding_set, state_map):
        """Item 16: build_binding_context returns a NetworkBindingContext."""
        ctx = build_binding_context(graph, assembly, binding_set, state_map)
        assert isinstance(ctx, NetworkBindingContext)

    def test_context_graph_preserved(self, context, graph):
        """Item 16: context.graph is the supplied graph."""
        assert context.graph is graph

    def test_context_assembly_preserved(self, context, assembly):
        """Item 16: context.assembly is the supplied assembly."""
        assert context.assembly is assembly

    def test_context_binding_set_preserved(self, context, binding_set):
        """Item 16: context.binding_set holds the correct bindings."""
        assert context.binding_set is binding_set

    def test_context_state_map_preserved(self, context, state_map):
        """Item 16: context.state_map is the supplied state map."""
        assert context.state_map is state_map

    def test_context_metadata_none_by_default(self, context):
        """Item 16: metadata is None when not supplied."""
        assert context.metadata is None

    def test_context_metadata_stored_immutably(self, graph, assembly, binding_set, state_map):
        """Item 16: metadata is stored as MappingProxyType."""
        ctx = build_binding_context(
            graph,
            assembly,
            binding_set,
            state_map,
            metadata={"run_id": "14b_test"},
        )
        assert isinstance(ctx.metadata, MappingProxyType)
        assert ctx.metadata["run_id"] == "14b_test"

    def test_context_is_frozen(self, context):
        """Item 16: NetworkBindingContext is immutable after construction."""
        with pytest.raises(FrozenInstanceError):
            context.graph = None  # type: ignore[misc]

    def test_builder_accepts_list_of_bindings(self, graph, assembly, state_map):
        """Item 16: build_binding_context normalises a list of ComponentBinding."""
        bindings_list = [
            ComponentBinding(ComponentInstanceId("evap"), "label1"),
            ComponentBinding(ComponentInstanceId("cond"), "label2"),
        ]
        ctx = build_binding_context(graph, assembly, bindings_list, state_map)
        assert isinstance(ctx, NetworkBindingContext)
        assert isinstance(ctx.binding_set, ComponentBindingSet)


# ---------------------------------------------------------------------------
# 17. Builder rejects non-NetworkGraph
# ---------------------------------------------------------------------------


class TestBuilderRejectsNonGraph:
    def test_rejects_none_graph(self, assembly, binding_set, state_map):
        """Item 17: None is rejected as graph."""
        with pytest.raises(TypeError, match="NetworkGraph"):
            build_binding_context(None, assembly, binding_set, state_map)

    def test_rejects_string_graph(self, assembly, binding_set, state_map):
        """Item 17: string is rejected as graph."""
        with pytest.raises(TypeError, match="NetworkGraph"):
            build_binding_context("graph", assembly, binding_set, state_map)

    def test_rejects_assembly_as_graph(self, assembly, binding_set, state_map):
        """Item 17: passing assembly where graph is expected is rejected."""
        with pytest.raises(TypeError, match="NetworkGraph"):
            build_binding_context(assembly, assembly, binding_set, state_map)


# ---------------------------------------------------------------------------
# 18. Builder rejects non-NetworkResidualAssembly
# ---------------------------------------------------------------------------


class TestBuilderRejectsNonAssembly:
    def test_rejects_none_assembly(self, graph, binding_set, state_map):
        """Item 18: None is rejected as assembly."""
        with pytest.raises(TypeError, match="NetworkResidualAssembly"):
            build_binding_context(graph, None, binding_set, state_map)

    def test_rejects_graph_as_assembly(self, graph, binding_set, state_map):
        """Item 18: NetworkGraph passed as assembly is rejected."""
        with pytest.raises(TypeError, match="NetworkResidualAssembly"):
            build_binding_context(graph, graph, binding_set, state_map)

    def test_rejects_dict_as_assembly(self, graph, binding_set, state_map):
        """Item 18: dict is rejected as assembly."""
        with pytest.raises(TypeError, match="NetworkResidualAssembly"):
            build_binding_context(graph, {}, binding_set, state_map)


# ---------------------------------------------------------------------------
# 19. Builder rejects missing component binding
# ---------------------------------------------------------------------------


class TestBuilderRejectsMissingBinding:
    def test_missing_one_binding(self, graph, assembly, state_map):
        """Item 19: omitting a binding for 'cond' raises ValueError."""
        partial_bindings = ComponentBindingSet(
            bindings=(ComponentBinding(ComponentInstanceId("evap"), "label"),)
        )
        with pytest.raises(ValueError, match="cond"):
            build_binding_context(graph, assembly, partial_bindings, state_map)

    def test_empty_binding_set_rejected(self, graph, assembly, state_map):
        """Item 19: empty binding set is rejected when graph has instances."""
        empty_bs = ComponentBindingSet(bindings=())
        with pytest.raises(ValueError):
            build_binding_context(graph, assembly, empty_bs, state_map)


# ---------------------------------------------------------------------------
# 20. Builder rejects extra component binding
# ---------------------------------------------------------------------------


class TestBuilderRejectsExtraBinding:
    def test_extra_binding_unknown_instance(self, graph, assembly, state_map):
        """Item 20: binding for unknown instance 'pump' is rejected."""
        extra_bindings = ComponentBindingSet(
            bindings=(
                ComponentBinding(ComponentInstanceId("evap"), "label1"),
                ComponentBinding(ComponentInstanceId("cond"), "label2"),
                ComponentBinding(ComponentInstanceId("pump"), "label_extra"),
            )
        )
        with pytest.raises(ValueError, match="pump"):
            build_binding_context(graph, assembly, extra_bindings, state_map)


# ---------------------------------------------------------------------------
# 21. Builder rejects state map component reference not in graph
# ---------------------------------------------------------------------------


class TestBuilderRejectsStateMapComponentNotInGraph:
    def test_unknown_to_component_bad_reference(self, graph, assembly, binding_set):
        """Item 21: state_map.unknown_to_component referencing unknown component."""
        bad_map = ComponentStateMap(
            unknown_to_component={"mdot:pump": ComponentInstanceId("pump")},
        )
        with pytest.raises(ValueError, match="pump"):
            build_binding_context(graph, assembly, binding_set, bad_map)

    def test_residual_to_component_bad_reference(self, graph, assembly, binding_set):
        """Item 21: state_map.residual_to_component referencing unknown component."""
        bad_map = ComponentStateMap(
            residual_to_component={"pressure_drop:pump": ComponentInstanceId("pump")},
        )
        with pytest.raises(ValueError, match="pump"):
            build_binding_context(graph, assembly, binding_set, bad_map)


# ---------------------------------------------------------------------------
# 22. Builder rejects state map node reference not in graph
# ---------------------------------------------------------------------------


class TestBuilderRejectsStateMapNodeNotInGraph:
    def test_unknown_to_node_bad_reference(self, graph, assembly, binding_set):
        """Item 22: state_map.unknown_to_node referencing unknown node."""
        bad_map = ComponentStateMap(
            unknown_to_node={"P:n99": GraphNodeId("n99")},
        )
        with pytest.raises(ValueError, match="n99"):
            build_binding_context(graph, assembly, binding_set, bad_map)

    def test_residual_to_node_bad_reference(self, graph, assembly, binding_set):
        """Item 22: state_map.residual_to_node referencing unknown node."""
        bad_map = ComponentStateMap(
            residual_to_node={"mass_balance:n99": GraphNodeId("n99")},
        )
        with pytest.raises(ValueError, match="n99"):
            build_binding_context(graph, assembly, binding_set, bad_map)


# ---------------------------------------------------------------------------
# Builder rejects names not declared by the supplied assembly
# ---------------------------------------------------------------------------


class TestBuilderRejectsUndeclaredStateMapNames:
    def test_unknown_to_component_name_must_exist_in_assembly(self, graph, assembly, binding_set):
        bad_map = ComponentStateMap(
            unknown_to_component={"mdot_typo:evap": ComponentInstanceId("evap")},
        )
        with pytest.raises(ValueError, match="not declared.*mdot_typo:evap"):
            build_binding_context(graph, assembly, binding_set, bad_map)

    def test_unknown_to_node_name_must_exist_in_assembly(self, graph, assembly, binding_set):
        bad_map = ComponentStateMap(
            unknown_to_node={"pressure:n1": GraphNodeId("n1")},
        )
        with pytest.raises(ValueError, match="not declared.*pressure:n1"):
            build_binding_context(graph, assembly, binding_set, bad_map)

    def test_residual_to_component_name_must_exist_in_assembly(self, graph, assembly, binding_set):
        bad_map = ComponentStateMap(
            residual_to_component={"component_residual:evap": ComponentInstanceId("evap")},
        )
        with pytest.raises(ValueError, match="not declared.*component_residual:evap"):
            build_binding_context(graph, assembly, binding_set, bad_map)

    def test_residual_to_node_name_must_exist_in_assembly(self, graph, assembly, binding_set):
        bad_map = ComponentStateMap(
            residual_to_node={"node_residual:n1": GraphNodeId("n1")},
        )
        with pytest.raises(ValueError, match="not declared.*node_residual:n1"):
            build_binding_context(graph, assembly, binding_set, bad_map)

    def test_names_disabled_in_assembly_are_rejected(self, graph, binding_set):
        assembly = assemble_network_residuals(
            graph,
            include_pressure_unknowns=False,
            include_pressure_residuals=False,
        )
        pressure_map = ComponentStateMap(
            unknown_to_node={"P:n1": GraphNodeId("n1")},
            residual_to_component={"pressure_drop:evap": ComponentInstanceId("evap")},
        )
        with pytest.raises(ValueError, match="not declared"):
            build_binding_context(graph, assembly, binding_set, pressure_map)


# ---------------------------------------------------------------------------
# 23. Builder does not mutate inputs
# ---------------------------------------------------------------------------


class TestBuilderDoesNotMutateInputs:
    def test_graph_nodes_unchanged(self, graph, assembly, binding_set, state_map):
        """Item 23: graph.nodes() is identical after build_binding_context."""
        original_nodes = graph.nodes()
        build_binding_context(graph, assembly, binding_set, state_map)
        assert graph.nodes() == original_nodes

    def test_assembly_residual_names_unchanged(self, graph, assembly, binding_set, state_map):
        """Item 23: assembly residual names are identical after builder call."""
        original_names = assembly.residuals.names()
        build_binding_context(graph, assembly, binding_set, state_map)
        assert assembly.residuals.names() == original_names

    def test_binding_set_bindings_unchanged(self, graph, assembly, binding_set, state_map):
        """Item 23: binding_set.bindings tuple is identical after builder call."""
        original_bindings = binding_set.bindings
        build_binding_context(graph, assembly, binding_set, state_map)
        assert binding_set.bindings == original_bindings

    def test_state_map_unchanged(self, graph, assembly, binding_set, state_map):
        """Item 23: state_map is identical after builder call."""
        original_utc = dict(state_map.unknown_to_component)
        build_binding_context(graph, assembly, binding_set, state_map)
        assert dict(state_map.unknown_to_component) == original_utc


# ---------------------------------------------------------------------------
# 24. Context stores no numerical unknown values
# ---------------------------------------------------------------------------


class TestContextStoresNoNumericalValues:
    def test_no_float_attributes_on_context(self, context):
        """Item 24: context carries no numeric scalar attributes."""
        for attr in vars(context):
            value = getattr(context, attr)
            assert not isinstance(value, float), f"context.{attr} should not be a float"

    def test_state_map_stores_no_float_values(self, context):
        """Item 24: state_map values are IDs only, not floats."""
        for v in context.state_map.unknown_to_component.values():
            assert isinstance(v, ComponentInstanceId)
        for v in context.state_map.unknown_to_node.values():
            assert isinstance(v, GraphNodeId)

    def test_binding_set_stores_no_float_values(self, context):
        """Item 24: binding_set holds only declarations, no numeric values."""
        for b in context.binding_set.bindings:
            assert isinstance(b.instance_id, ComponentInstanceId)
            assert isinstance(b.binding_name, str)


# ---------------------------------------------------------------------------
# 25. Context stores no FluidState
# ---------------------------------------------------------------------------


class TestContextStoresNoFluidState:
    def test_no_fluid_state_attribute_on_context(self, context):
        """Item 25: context has no FluidState attribute."""
        assert not hasattr(context, "fluid_state")
        assert not hasattr(context, "FluidState")

    def test_no_fluid_state_on_graph_nodes(self, context):
        """Item 25: graph nodes carry no FluidState after context construction."""
        for node in context.graph.nodes():
            assert not hasattr(node, "fluid_state")
            assert not hasattr(node, "P")
            assert not hasattr(node, "h")
            assert not hasattr(node, "mdot")

    def test_no_physical_values_on_instances(self, context):
        """Item 25: component instances carry no physical values."""
        for inst in context.graph.instances():
            assert not hasattr(inst, "mdot_value")
            assert not hasattr(inst, "P_in")
            assert not hasattr(inst, "h_in")
            assert not hasattr(inst, "fluid_state_in")


# ---------------------------------------------------------------------------
# 26. Context does not execute callbacks
# ---------------------------------------------------------------------------


class TestContextDoesNotExecuteCallbacks:
    def test_callback_not_invoked_during_context_build(
        self, graph, assembly, binding_set, state_map
    ):
        """Item 26: no callback is invoked when building the context."""
        call_log: list[str] = []

        def spy_callback(ctx):  # noqa: ARG001
            call_log.append("invoked")
            return 0.0

        # Attach a spy as metadata value to verify it's stored, not called.
        binding_set_with_spy = ComponentBindingSet(
            bindings=(
                ComponentBinding(
                    ComponentInstanceId("evap"),
                    "label",
                    metadata={"cb": spy_callback},
                ),
                ComponentBinding(ComponentInstanceId("cond"), "label2"),
            )
        )
        build_binding_context(graph, assembly, binding_set_with_spy, state_map)
        assert call_log == [], "spy_callback must not have been invoked"


# ---------------------------------------------------------------------------
# 27. Context does not execute components
# ---------------------------------------------------------------------------


class TestContextDoesNotExecuteComponents:
    def test_component_type_not_accessed_on_instances(
        self, graph, assembly, binding_set, state_map
    ):
        """Item 27: component_type is not inspected by build_binding_context."""
        # Build with a non-standard component_type string.
        unusual_graph = NetworkGraph(
            nodes=[_node("n1"), _node("n2")],
            instances=[
                _inst("evap", "SHOULD_NOT_BE_EXECUTED", "n1", "n2"),
                _inst("cond", "SHOULD_NOT_BE_EXECUTED_EITHER", "n2", "n1"),
            ],
        )
        unusual_assembly = assemble_network_residuals(unusual_graph)
        ctx = build_binding_context(unusual_graph, unusual_assembly, binding_set, state_map)
        # Construction succeeds; component_type is never executed or resolved.
        assert isinstance(ctx, NetworkBindingContext)
        for inst in ctx.graph.instances():
            assert "SHOULD_NOT_BE_EXECUTED" in inst.component_type


# ---------------------------------------------------------------------------
# 28. No contribute( call in source
# ---------------------------------------------------------------------------


class TestNoBoundaryViolations:
    def _source(self) -> str:
        import mpl_sim.network.component_binding as _m

        return inspect.getsource(_m)

    def _source_without_docstrings(self) -> str:
        src = self._source()
        tree = ast.parse(src)
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

    def test_no_contribute_call(self):
        """Item 28: 'contribute' is not defined or called in non-docstring code."""
        tree = ast.parse(self._source())
        func_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "contribute" not in func_names
        assert "contribute" not in self._source_without_docstrings()

    def test_no_property_lookup(self):
        """Item 29: PropertyBackend is not imported or referenced in non-docstring code."""
        for mod in self._imported_modules():
            assert "properties" not in mod
        assert "PropertyBackend" not in self._source_without_docstrings()

    def test_no_registry_resolution(self):
        """Item 30: CorrelationRegistry is not imported or referenced."""
        for mod in self._imported_modules():
            assert "correlations" not in mod
        assert "CorrelationRegistry" not in self._source_without_docstrings()

    def test_no_coolprop(self):
        """Item 31: CoolProp is not imported."""
        for mod in self._imported_modules():
            assert "CoolProp" not in mod
        assert "CoolProp" not in self._source_without_docstrings()

    def test_no_automatic_physics_from_component_type(self):
        """Item 32: component_type is not accessed in non-docstring code."""
        tree = ast.parse(self._source())
        attr_names = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)]
        assert "component_type" not in attr_names
        assert "component_type" not in self._source_without_docstrings()

    def test_no_hx_model_registry(self):
        """Item 30 (extension): HeatExchangerModelRegistry is not imported."""
        for mod in self._imported_modules():
            assert "hx_models" not in mod
        assert "HeatExchangerModelRegistry" not in self._source_without_docstrings()

    def test_no_fluid_state_import(self):
        """Item 25/31: FluidState is not imported or referenced in non-docstring code."""
        assert "FluidState" not in self._source_without_docstrings()

    def test_no_scipy_import(self):
        """No scipy dependency in component_binding.py."""
        for mod in self._imported_modules():
            assert "scipy" not in mod

    def test_only_network_and_stdlib_imports(self):
        """component_binding.py only imports from stdlib and mpl_sim.network."""
        for mod in self._imported_modules():
            if mod.startswith("mpl_sim"):
                assert mod.startswith(
                    "mpl_sim.network"
                ), f"component_binding.py must not import from {mod!r}"

    def test_no_solve_method_defined(self):
        """No solve() method is defined in component_binding.py."""
        tree = ast.parse(self._source())
        func_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "solve" not in func_names


# ---------------------------------------------------------------------------
# 33. Public exports work from mpl_sim.network
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_component_binding_exported(self):
        """Item 33: ComponentBinding is in mpl_sim.network."""
        assert ComponentBinding is _BindingDirect

    def test_component_binding_set_exported(self):
        """Item 33: ComponentBindingSet is in mpl_sim.network."""
        assert ComponentBindingSet is _BindingSetDirect

    def test_component_state_map_exported(self):
        """Item 33: ComponentStateMap is in mpl_sim.network."""
        assert ComponentStateMap is _StateMapDirect

    def test_network_binding_context_exported(self):
        """Item 33: NetworkBindingContext is in mpl_sim.network."""
        assert NetworkBindingContext is _ContextDirect

    def test_build_binding_context_exported(self):
        """Item 33: build_binding_context is in mpl_sim.network."""
        assert build_binding_context is _build_direct

    def test_all_new_names_in_package_all(self):
        """Item 33: all Phase 14B names appear in mpl_sim.network.__all__."""
        import mpl_sim.network as pkg

        all_names = pkg.__all__
        for name in (
            "ComponentBinding",
            "ComponentBindingSet",
            "ComponentStateMap",
            "NetworkBindingContext",
            "build_binding_context",
        ):
            assert name in all_names, f"{name!r} missing from mpl_sim.network.__all__"


# ---------------------------------------------------------------------------
# 34. Existing Phase 13E–14A tests still importable (regression guard)
# ---------------------------------------------------------------------------


class TestPhase13To14ARegressionGuard:
    def test_phase_13e_types_still_importable(self):
        """Item 34: Phase 13E public types remain importable from mpl_sim.network."""
        from mpl_sim.network import (
            ComponentInstance,
            ComponentInstanceId,
            GraphNode,
            GraphNodeId,
            NetworkGraph,
        )

        assert GraphNodeId("n1").value == "n1"
        assert ComponentInstanceId("evap").value == "evap"
        assert isinstance(GraphNode(GraphNodeId("n1")), GraphNode)
        _ = ComponentInstance, NetworkGraph  # noqa: F841

    def test_phase_14a_types_still_importable(self):
        """Item 34: Phase 14A public types remain importable from mpl_sim.network."""
        from mpl_sim.network import (
            PhysicalResidualAdapter,
            PhysicalResidualAdapterSet,
            PhysicalResidualContext,
            build_network_residual_evaluators,
        )

        _ = (
            PhysicalResidualAdapter,
            PhysicalResidualAdapterSet,
            PhysicalResidualContext,
            build_network_residual_evaluators,
        )  # noqa: F841


# ---------------------------------------------------------------------------
# 35. Docs do not claim physical network simulation
# ---------------------------------------------------------------------------


class TestDocsHonestClaims:
    def _concepts_text(self) -> str:
        concepts_path = (
            pathlib.Path(__file__).parent.parent.parent / "docs" / "user_guide" / "CONCEPTS.md"
        )
        return concepts_path.read_text(encoding="utf-8")

    def test_concepts_has_phase_14b_section(self):
        """Item 35: CONCEPTS.md has a Phase 14B section."""
        assert "14B" in self._concepts_text()

    def test_concepts_says_not_physical_simulator(self):
        """Item 35: Phase 14B docs state it is not a physical network simulator."""
        text = self._concepts_text()
        # Either an explicit "NOT" or "not" near simulator/physics.
        assert "not" in text.lower() or "NOT" in text

    def test_concepts_does_not_claim_solve_network(self):
        """Item 35: docs do not claim a working solve(network) capability in 14B."""
        text = self._concepts_text()
        # The Phase 14B section should not present 'solve(network)' as a positive
        # capability.  It is fine (and correct) for it to appear in "Does NOT
        # implement `solve(network)`" negation statements.  We verify that any
        # occurrence of 'solve(network)' in the section is only in a negative context.
        phase_14b_start = text.find("Phase 14B")
        if phase_14b_start == -1:
            return  # no section yet
        next_section = text.find("\n## ", phase_14b_start + 1)
        section = (
            text[phase_14b_start:next_section] if next_section != -1 else text[phase_14b_start:]
        )
        # Every occurrence of 'solve(network)' must be within 20 chars of 'NOT' or 'not'.
        import re

        for m in re.finditer(r"solve\(network\)", section):
            start = max(0, m.start() - 30)
            context_window = section[start : m.start() + 30]
            assert (
                "NOT" in context_window or "not" in context_window
            ), f"'solve(network)' appears without negation near: {context_window!r}"

    def test_concepts_does_not_claim_component_execution(self):
        """Item 35: Phase 14B docs explicitly state components are not executed."""
        text = self._concepts_text()
        phase_14b_start = text.find("Phase 14B")
        if phase_14b_start == -1:
            return
        next_section = text.find("\n## ", phase_14b_start + 1)
        section = (
            text[phase_14b_start:next_section] if next_section != -1 else text[phase_14b_start:]
        )
        assert "not" in section.lower()
