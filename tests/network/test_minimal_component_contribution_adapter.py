"""Phase 14C minimal component contribution adapter foundation tests.

Coverage items (42 required):
 1.  valid ComponentContributionContext construction
 2.  context rejects non-NetworkBindingContext
 3.  unknown values mapping is immutable / defensively copied
 4.  metadata is immutable / defensively copied
 5.  valid ComponentContribution construction
 6.  contribution rejects empty residual name
 7.  contribution rejects whitespace-only residual name
 8.  contribution rejects non-string residual name
 9.  contribution rejects non-finite value: nan
10.  contribution rejects non-finite value: inf
11.  contribution rejects bool value
12.  contribution mapping is immutable / defensively copied
13.  valid ComponentContributionAdapter construction
14.  adapter rejects wrong component ID type
15.  adapter rejects non-callable callback
16.  adapter set preserves deterministic order
17.  adapter set rejects wrong entry type
18.  adapter set rejects duplicate component IDs
19.  builder rejects non-NetworkBindingContext
20.  builder rejects missing contribution adapter
21.  builder rejects extra contribution adapter
22.  builder rejects contribution for unbound component
23.  generated physical adapters are PhysicalResidualAdapter
24.  generated physical adapters preserve assembly residual order
25.  generated callbacks call explicit contribution callbacks
26.  callback exceptions propagate
27.  callback returning wrong type rejected
28.  missing required residual value rejected
29.  undeclared residual value rejected
30.  one-shot evaluation through Phase 13G gives expected toy residuals
31.  Phase 13H solve works on toy contribution problem
32.  no real component execution
33.  no contribute( call in source
34.  no property lookup in source
35.  no registry resolution in source
36.  no CoolProp in source
37.  no SystemState assembly in source
38.  no FluidState attached to graph in source
39.  no physical values attached to NetworkGraph in source
40.  no automatic physics from component_type in source
41.  public exports work from mpl_sim.network
42.  existing Phase 13E/13F/13G/13H/14A/14B tests still pass (suite-level gate)
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import FrozenInstanceError
from types import MappingProxyType

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
    GraphNode,
    GraphNodeId,
    NetworkBindingContext,
    NetworkGraph,
    NetworkSolveConfig,
    NetworkUnknownValues,
    PhysicalResidualAdapter,
    PhysicalResidualAdapterSet,
    assemble_network_residuals,
    build_binding_context,
    build_network_residual_evaluators,
    build_physical_adapters_from_contributions,
    evaluate_network_residuals,
    solve_network_residual_problem,
)
from mpl_sim.network.contribution_adapters import (
    ComponentContribution as _ContributionDirect,
)
from mpl_sim.network.contribution_adapters import (
    ComponentContributionAdapter as _AdapterDirect,
)
from mpl_sim.network.contribution_adapters import (
    ComponentContributionAdapterSet as _AdapterSetDirect,
)
from mpl_sim.network.contribution_adapters import (
    ComponentContributionContext as _ContextDirect,
)
from mpl_sim.network.contribution_adapters import (
    build_physical_adapters_from_contributions as _build_direct,
)

# ---------------------------------------------------------------------------
# Shared toy graph / assembly / binding helpers
# ---------------------------------------------------------------------------

_SRC = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "contribution_adapters.py"
)


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


# ---------------------------------------------------------------------------
# Toy contribution callbacks (Phase 14C task-spec toy problem)
#
# unknowns: mdot:evap, mdot:cond, P:n1, P:n2
# expected one-shot residuals at
#   mdot:evap=0.05, mdot:cond=0.05, P:n1=100_000, P:n2=99_000:
#   mass_balance:n1 = 0.0
#   mass_balance:n2 = 0.0
#   pressure_drop:evap = 100_000 - 99_000 - 600 = 400.0
#   pressure_drop:cond =  99_000 - 100_000 + 1000 = 0.0
# ---------------------------------------------------------------------------


def _evap_contribution(ctx: ComponentContributionContext) -> ComponentContribution:
    v = ctx.unknown_values
    return ComponentContribution(
        residual_values={
            "mass_balance:n1": v["mdot:evap"] - v["mdot:cond"],
            "pressure_drop:evap": v["P:n1"] - v["P:n2"] - 600.0,
        }
    )


def _cond_contribution(ctx: ComponentContributionContext) -> ComponentContribution:
    v = ctx.unknown_values
    return ComponentContribution(
        residual_values={
            "mass_balance:n2": v["mdot:cond"] - v["mdot:evap"],
            "pressure_drop:cond": v["P:n2"] - v["P:n1"] + 1000.0,
        }
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def toy_graph():
    return _toy_graph()


@pytest.fixture
def toy_assembly(toy_graph):
    return assemble_network_residuals(toy_graph)


@pytest.fixture
def toy_binding_context(toy_graph, toy_assembly):
    return _toy_binding_context(toy_graph, toy_assembly)


@pytest.fixture
def toy_contribution_adapters():
    return [
        ComponentContributionAdapter(
            instance_id=ComponentInstanceId("evap"),
            callback=_evap_contribution,
        ),
        ComponentContributionAdapter(
            instance_id=ComponentInstanceId("cond"),
            callback=_cond_contribution,
        ),
    ]


@pytest.fixture
def toy_contribution_adapter_set(toy_contribution_adapters):
    return ComponentContributionAdapterSet(adapters=tuple(toy_contribution_adapters))


@pytest.fixture
def toy_unknown_values():
    return {
        "mdot:evap": 0.05,
        "mdot:cond": 0.05,
        "P:n1": 100_000.0,
        "P:n2": 99_000.0,
    }


@pytest.fixture
def toy_scales():
    return {
        "mass_balance:n1": 0.01,
        "mass_balance:n2": 0.01,
        "pressure_drop:evap": 100.0,
        "pressure_drop:cond": 100.0,
    }


# ---------------------------------------------------------------------------
# 1. valid ComponentContributionContext construction
# ---------------------------------------------------------------------------


class TestComponentContributionContext:
    def test_valid_construction(self, toy_binding_context):
        """Item 1: valid construction with all fields."""
        ctx = ComponentContributionContext(
            binding_context=toy_binding_context,
            unknown_values={"mdot:evap": 0.05},
        )
        assert ctx.binding_context is toy_binding_context
        assert ctx.unknown_values["mdot:evap"] == 0.05
        assert ctx.metadata is None

    def test_valid_construction_with_metadata(self, toy_binding_context):
        """Item 1: valid construction with optional metadata."""
        ctx = ComponentContributionContext(
            binding_context=toy_binding_context,
            unknown_values={"a": 1.0},
            metadata={"tag": "test"},
        )
        assert ctx.metadata["tag"] == "test"

    # ------------------------------------------------------------------
    # Item 2: context rejects non-NetworkBindingContext
    # ------------------------------------------------------------------

    def test_rejects_non_binding_context_string(self, toy_binding_context):
        """Item 2: string rejected as binding_context."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            ComponentContributionContext(
                binding_context="not_a_context",  # type: ignore[arg-type]
                unknown_values={"a": 1.0},
            )

    def test_rejects_non_binding_context_none(self, toy_binding_context):
        """Item 2: None rejected as binding_context."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            ComponentContributionContext(
                binding_context=None,  # type: ignore[arg-type]
                unknown_values={"a": 1.0},
            )

    # ------------------------------------------------------------------
    # Item 3: unknown values immutable / defensively copied
    # ------------------------------------------------------------------

    def test_unknown_values_is_mapping_proxy(self, toy_binding_context):
        """Item 3: unknown_values stored as MappingProxyType."""
        ctx = ComponentContributionContext(
            binding_context=toy_binding_context,
            unknown_values={"a": 1.0},
        )
        assert isinstance(ctx.unknown_values, MappingProxyType)

    def test_unknown_values_source_mutation_ignored(self, toy_binding_context):
        """Item 3: mutating source dict after construction has no effect."""
        source = {"a": 1.0}
        ctx = ComponentContributionContext(
            binding_context=toy_binding_context,
            unknown_values=source,
        )
        source["a"] = 999.0
        assert ctx.unknown_values["a"] == 1.0

    def test_unknown_values_immutable(self, toy_binding_context):
        """Item 3: stored mapping is immutable."""
        ctx = ComponentContributionContext(
            binding_context=toy_binding_context,
            unknown_values={"a": 1.0},
        )
        with pytest.raises((TypeError, FrozenInstanceError)):
            ctx.unknown_values["a"] = 2.0  # type: ignore[index]

    # ------------------------------------------------------------------
    # Item 4: metadata immutable / defensively copied
    # ------------------------------------------------------------------

    def test_metadata_is_mapping_proxy(self, toy_binding_context):
        """Item 4: metadata stored as MappingProxyType."""
        ctx = ComponentContributionContext(
            binding_context=toy_binding_context,
            unknown_values={},
            metadata={"key": "val"},
        )
        assert isinstance(ctx.metadata, MappingProxyType)

    def test_metadata_source_mutation_ignored(self, toy_binding_context):
        """Item 4: mutating source dict after construction has no effect."""
        source = {"key": "original"}
        ctx = ComponentContributionContext(
            binding_context=toy_binding_context,
            unknown_values={},
            metadata=source,
        )
        source["key"] = "changed"
        assert ctx.metadata["key"] == "original"  # type: ignore[index]

    def test_metadata_immutable(self, toy_binding_context):
        """Item 4: stored metadata is immutable."""
        ctx = ComponentContributionContext(
            binding_context=toy_binding_context,
            unknown_values={},
            metadata={"key": "val"},
        )
        with pytest.raises((TypeError, FrozenInstanceError)):
            ctx.metadata["key"] = "new"  # type: ignore[index]

    def test_frozen_dataclass(self, toy_binding_context):
        """Context is frozen: field assignment raises."""
        ctx = ComponentContributionContext(
            binding_context=toy_binding_context,
            unknown_values={"a": 1.0},
        )
        with pytest.raises(FrozenInstanceError):
            ctx.metadata = {}  # type: ignore[misc]

    def test_direct_import_same_as_public(self, toy_binding_context):
        """Public and direct module imports refer to the same class."""
        assert ComponentContributionContext is _ContextDirect


# ---------------------------------------------------------------------------
# 5. valid ComponentContribution construction
# ---------------------------------------------------------------------------


class TestComponentContribution:
    def test_valid_construction(self):
        """Item 5: valid construction with finite values."""
        cc = ComponentContribution(residual_values={"r:a": 1.0, "r:b": -2.5})
        assert cc.residual_values["r:a"] == 1.0
        assert cc.residual_values["r:b"] == -2.5

    def test_valid_construction_empty(self):
        """Item 5: empty mapping is valid."""
        cc = ComponentContribution(residual_values={})
        assert len(cc.residual_values) == 0

    def test_valid_construction_int_value(self):
        """Item 5: integer values accepted and promoted to float."""
        cc = ComponentContribution(residual_values={"r:a": 3})
        assert isinstance(cc.residual_values["r:a"], float)

    # ------------------------------------------------------------------
    # Item 6: contribution rejects empty residual name
    # ------------------------------------------------------------------

    def test_rejects_empty_key(self):
        """Item 6: empty string key rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentContribution(residual_values={"": 1.0})

    # ------------------------------------------------------------------
    # Item 7: contribution rejects whitespace-only residual name
    # ------------------------------------------------------------------

    def test_rejects_whitespace_key(self):
        """Item 7: whitespace-only key rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ComponentContribution(residual_values={"   ": 1.0})

    # ------------------------------------------------------------------
    # Item 8: contribution rejects non-string residual name
    # ------------------------------------------------------------------

    def test_rejects_non_string_key_int(self):
        """Item 8: integer key rejected."""
        with pytest.raises(TypeError, match="strings"):
            ComponentContribution(residual_values={42: 1.0})  # type: ignore[dict-item]

    def test_rejects_non_string_key_none(self):
        """Item 8: None key rejected."""
        with pytest.raises(TypeError, match="strings"):
            ComponentContribution(residual_values={None: 1.0})  # type: ignore[dict-item]

    # ------------------------------------------------------------------
    # Item 9: contribution rejects non-finite value: nan
    # ------------------------------------------------------------------

    def test_rejects_nan_value(self):
        """Item 9: NaN value rejected."""
        with pytest.raises(ValueError, match="finite"):
            ComponentContribution(residual_values={"r:a": float("nan")})

    # ------------------------------------------------------------------
    # Item 10: contribution rejects non-finite value: inf
    # ------------------------------------------------------------------

    def test_rejects_inf_value(self):
        """Item 10: positive infinity rejected."""
        with pytest.raises(ValueError, match="finite"):
            ComponentContribution(residual_values={"r:a": float("inf")})

    def test_rejects_neg_inf_value(self):
        """Item 10: negative infinity rejected."""
        with pytest.raises(ValueError, match="finite"):
            ComponentContribution(residual_values={"r:a": float("-inf")})

    # ------------------------------------------------------------------
    # Item 11: contribution rejects bool value
    # ------------------------------------------------------------------

    def test_rejects_bool_true(self):
        """Item 11: True rejected as bool."""
        with pytest.raises(TypeError, match="bool"):
            ComponentContribution(residual_values={"r:a": True})

    def test_rejects_bool_false(self):
        """Item 11: False rejected as bool."""
        with pytest.raises(TypeError, match="bool"):
            ComponentContribution(residual_values={"r:a": False})

    # ------------------------------------------------------------------
    # Item 12: contribution mapping immutable / defensively copied
    # ------------------------------------------------------------------

    def test_mapping_is_mapping_proxy(self):
        """Item 12: residual_values stored as MappingProxyType."""
        cc = ComponentContribution(residual_values={"r:a": 1.0})
        assert isinstance(cc.residual_values, MappingProxyType)

    def test_mapping_source_mutation_ignored(self):
        """Item 12: mutating source dict after construction has no effect."""
        source = {"r:a": 1.0}
        cc = ComponentContribution(residual_values=source)
        source["r:a"] = 999.0
        assert cc.residual_values["r:a"] == 1.0

    def test_mapping_immutable(self):
        """Item 12: stored mapping is immutable."""
        cc = ComponentContribution(residual_values={"r:a": 1.0})
        with pytest.raises((TypeError, FrozenInstanceError)):
            cc.residual_values["r:a"] = 2.0  # type: ignore[index]

    def test_frozen_dataclass(self):
        """Contribution is frozen."""
        cc = ComponentContribution(residual_values={"r:a": 1.0})
        with pytest.raises(FrozenInstanceError):
            cc.residual_values = {}  # type: ignore[misc]

    def test_direct_import_same_as_public(self):
        """Public and direct module imports refer to the same class."""
        assert ComponentContribution is _ContributionDirect


# ---------------------------------------------------------------------------
# 13. valid ComponentContributionAdapter construction
# ---------------------------------------------------------------------------


class TestComponentContributionAdapter:
    def test_valid_construction(self):
        """Item 13: valid construction with callable callback."""
        adapter = ComponentContributionAdapter(
            instance_id=ComponentInstanceId("evap"),
            callback=lambda ctx: ComponentContribution(residual_values={}),
        )
        assert adapter.instance_id == ComponentInstanceId("evap")
        assert callable(adapter.callback)

    # ------------------------------------------------------------------
    # Item 14: adapter rejects wrong component ID type
    # ------------------------------------------------------------------

    def test_rejects_string_instance_id(self):
        """Item 14: string rejected as instance_id."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ComponentContributionAdapter(
                instance_id="evap",  # type: ignore[arg-type]
                callback=lambda ctx: ComponentContribution(residual_values={}),
            )

    def test_rejects_none_instance_id(self):
        """Item 14: None rejected as instance_id."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ComponentContributionAdapter(
                instance_id=None,  # type: ignore[arg-type]
                callback=lambda ctx: ComponentContribution(residual_values={}),
            )

    # ------------------------------------------------------------------
    # Item 15: adapter rejects non-callable callback
    # ------------------------------------------------------------------

    def test_rejects_non_callable_callback_string(self):
        """Item 15: string rejected as callback."""
        with pytest.raises(TypeError, match="callable"):
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("evap"),
                callback="not_callable",  # type: ignore[arg-type]
            )

    def test_rejects_non_callable_callback_none(self):
        """Item 15: None rejected as callback."""
        with pytest.raises(TypeError, match="callable"):
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("evap"),
                callback=None,  # type: ignore[arg-type]
            )

    def test_frozen_dataclass(self):
        """Adapter is frozen."""
        adapter = ComponentContributionAdapter(
            instance_id=ComponentInstanceId("evap"),
            callback=lambda ctx: ComponentContribution(residual_values={}),
        )
        with pytest.raises(FrozenInstanceError):
            adapter.instance_id = ComponentInstanceId("other")  # type: ignore[misc]

    def test_direct_import_same_as_public(self):
        """Public and direct module imports refer to the same class."""
        assert ComponentContributionAdapter is _AdapterDirect


# ---------------------------------------------------------------------------
# 16. adapter set preserves deterministic order
# ---------------------------------------------------------------------------


class TestComponentContributionAdapterSet:
    def test_preserves_deterministic_order(self):
        """Item 16: insertion order preserved."""
        a1 = ComponentContributionAdapter(
            instance_id=ComponentInstanceId("c1"),
            callback=lambda ctx: ComponentContribution(residual_values={}),
        )
        a2 = ComponentContributionAdapter(
            instance_id=ComponentInstanceId("c2"),
            callback=lambda ctx: ComponentContribution(residual_values={}),
        )
        a3 = ComponentContributionAdapter(
            instance_id=ComponentInstanceId("c3"),
            callback=lambda ctx: ComponentContribution(residual_values={}),
        )
        s = ComponentContributionAdapterSet(adapters=(a1, a2, a3))
        assert [a.instance_id.value for a in s.adapters] == ["c1", "c2", "c3"]

    def test_normalizes_list_to_tuple(self):
        """Item 16: list input normalised to tuple."""
        a = ComponentContributionAdapter(
            instance_id=ComponentInstanceId("c1"),
            callback=lambda ctx: ComponentContribution(residual_values={}),
        )
        s = ComponentContributionAdapterSet(adapters=[a])  # type: ignore[arg-type]
        assert isinstance(s.adapters, tuple)

    # ------------------------------------------------------------------
    # Item 17: adapter set rejects wrong entry type
    # ------------------------------------------------------------------

    def test_rejects_wrong_entry_type_string(self):
        """Item 17: string entry rejected."""
        with pytest.raises(TypeError, match="ComponentContributionAdapter"):
            ComponentContributionAdapterSet(adapters=("not_an_adapter",))  # type: ignore[arg-type]

    def test_rejects_wrong_entry_type_none(self):
        """Item 17: None entry rejected."""
        with pytest.raises(TypeError, match="ComponentContributionAdapter"):
            ComponentContributionAdapterSet(adapters=(None,))  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Item 18: adapter set rejects duplicate component IDs
    # ------------------------------------------------------------------

    def test_rejects_duplicate_instance_ids(self):
        """Item 18: duplicate instance_id rejected."""
        a1 = ComponentContributionAdapter(
            instance_id=ComponentInstanceId("evap"),
            callback=lambda ctx: ComponentContribution(residual_values={}),
        )
        a2 = ComponentContributionAdapter(
            instance_id=ComponentInstanceId("evap"),
            callback=lambda ctx: ComponentContribution(residual_values={}),
        )
        with pytest.raises(ValueError, match="duplicate"):
            ComponentContributionAdapterSet(adapters=(a1, a2))

    def test_direct_import_same_as_public(self):
        """Public and direct module imports refer to the same class."""
        assert ComponentContributionAdapterSet is _AdapterSetDirect


# ---------------------------------------------------------------------------
# 19–22. build_physical_adapters_from_contributions validation
# ---------------------------------------------------------------------------


class TestBuildPhysicalAdaptersFromContributions:
    # ------------------------------------------------------------------
    # Item 19: builder rejects non-NetworkBindingContext
    # ------------------------------------------------------------------

    def test_rejects_non_binding_context_string(self, toy_contribution_adapters):
        """Item 19: string rejected as binding_context."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            build_physical_adapters_from_contributions(
                "not_a_context",  # type: ignore[arg-type]
                toy_contribution_adapters,
            )

    def test_rejects_non_binding_context_none(self, toy_contribution_adapters):
        """Item 19: None rejected as binding_context."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            build_physical_adapters_from_contributions(
                None,  # type: ignore[arg-type]
                toy_contribution_adapters,
            )

    # ------------------------------------------------------------------
    # Item 20: builder rejects missing contribution adapter
    # ------------------------------------------------------------------

    def test_rejects_missing_adapter(self, toy_binding_context):
        """Item 20: missing contribution adapter for a bound component."""
        only_evap = [
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("evap"),
                callback=_evap_contribution,
            )
        ]
        with pytest.raises(ValueError, match="missing"):
            build_physical_adapters_from_contributions(toy_binding_context, only_evap)

    # ------------------------------------------------------------------
    # Item 21: builder rejects extra contribution adapter
    # ------------------------------------------------------------------

    def test_rejects_extra_adapter(self, toy_binding_context):
        """Item 21: extra contribution adapter for a non-bound component."""
        extra = [
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("evap"),
                callback=_evap_contribution,
            ),
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("cond"),
                callback=_cond_contribution,
            ),
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("pump"),  # not in binding_context
                callback=lambda ctx: ComponentContribution(residual_values={}),
            ),
        ]
        with pytest.raises(ValueError, match="not bound"):
            build_physical_adapters_from_contributions(toy_binding_context, extra)

    # ------------------------------------------------------------------
    # Item 22: builder rejects contribution for unbound component
    # ------------------------------------------------------------------

    def test_rejects_unbound_component(self, toy_binding_context):
        """Item 22: only an adapter for an unbound component → missing bound components."""
        # Provide adapter only for a component that is not in the binding set
        unbound_only = [
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("definitely_unbound"),
                callback=lambda ctx: ComponentContribution(residual_values={}),
            ),
        ]
        with pytest.raises(ValueError, match="bound"):
            build_physical_adapters_from_contributions(toy_binding_context, unbound_only)

    def test_direct_import_same_as_public(self):
        """Public and direct module imports refer to the same function."""
        assert build_physical_adapters_from_contributions is _build_direct


# ---------------------------------------------------------------------------
# 23–29. generated physical adapter behavior
# ---------------------------------------------------------------------------


class TestGeneratedPhysicalAdapters:
    @pytest.fixture
    def physical_set(self, toy_binding_context, toy_contribution_adapters):
        return build_physical_adapters_from_contributions(
            toy_binding_context, toy_contribution_adapters
        )

    # ------------------------------------------------------------------
    # Item 23: generated physical adapters are PhysicalResidualAdapter
    # ------------------------------------------------------------------

    def test_generated_adapters_are_physical_residual_adapters(self, physical_set):
        """Item 23: every entry in the set is a PhysicalResidualAdapter."""
        assert isinstance(physical_set, PhysicalResidualAdapterSet)
        for a in physical_set.adapters:
            assert isinstance(a, PhysicalResidualAdapter)

    # ------------------------------------------------------------------
    # Item 24: generated physical adapters preserve assembly residual order
    # ------------------------------------------------------------------

    def test_generated_adapters_preserve_assembly_order(self, toy_assembly, physical_set):
        """Item 24: physical adapters are in assembly declaration order."""
        declared = list(toy_assembly.residuals.names())
        generated = [a.residual_name for a in physical_set.adapters]
        assert generated == declared

    # ------------------------------------------------------------------
    # Item 25: generated callbacks call explicit contribution callbacks
    # ------------------------------------------------------------------

    def test_generated_callbacks_call_contribution_callbacks(
        self, toy_binding_context, toy_unknown_values
    ):
        """Item 25: contribution callbacks are called during evaluation."""
        call_log: list[str] = []

        def evap_cb(ctx: ComponentContributionContext) -> ComponentContribution:
            call_log.append("evap")
            v = ctx.unknown_values
            return ComponentContribution(
                residual_values={
                    "mass_balance:n1": v["mdot:evap"] - v["mdot:cond"],
                    "pressure_drop:evap": v["P:n1"] - v["P:n2"] - 600.0,
                }
            )

        def cond_cb(ctx: ComponentContributionContext) -> ComponentContribution:
            call_log.append("cond")
            v = ctx.unknown_values
            return ComponentContribution(
                residual_values={
                    "mass_balance:n2": v["mdot:cond"] - v["mdot:evap"],
                    "pressure_drop:cond": v["P:n2"] - v["P:n1"] + 1000.0,
                }
            )

        adapters = [
            ComponentContributionAdapter(instance_id=ComponentInstanceId("evap"), callback=evap_cb),
            ComponentContributionAdapter(instance_id=ComponentInstanceId("cond"), callback=cond_cb),
        ]
        physical_set = build_physical_adapters_from_contributions(toy_binding_context, adapters)
        from mpl_sim.network.physical_adapters import PhysicalResidualContext

        ctx_pa = PhysicalResidualContext(unknown_values=toy_unknown_values)
        # Call the first physical adapter; both contribution callbacks should fire
        call_log.clear()
        physical_set.adapters[0].callback(ctx_pa)
        assert "evap" in call_log
        assert "cond" in call_log

    # ------------------------------------------------------------------
    # Item 26: callback exceptions propagate
    # ------------------------------------------------------------------

    def test_callback_exceptions_propagate(self, toy_binding_context):
        """Item 26: exceptions from contribution callbacks propagate unchanged."""

        def exploding_cb(ctx: ComponentContributionContext) -> ComponentContribution:
            raise RuntimeError("contribution exploded")

        adapters = [
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("evap"), callback=exploding_cb
            ),
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("cond"),
                callback=lambda ctx: ComponentContribution(residual_values={}),
            ),
        ]
        physical_set = build_physical_adapters_from_contributions(toy_binding_context, adapters)
        from mpl_sim.network.physical_adapters import PhysicalResidualContext

        ctx_pa = PhysicalResidualContext(unknown_values={"x": 1.0})
        with pytest.raises(RuntimeError, match="contribution exploded"):
            physical_set.adapters[0].callback(ctx_pa)

    # ------------------------------------------------------------------
    # Item 27: callback returning wrong type rejected
    # ------------------------------------------------------------------

    def test_callback_returning_wrong_type_rejected(self, toy_binding_context):
        """Item 27: callback that returns a dict instead of ComponentContribution."""

        def bad_cb(ctx: ComponentContributionContext):
            return {"mass_balance:n1": 0.0}  # wrong type

        adapters = [
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("evap"),
                callback=bad_cb,  # type: ignore[arg-type]
            ),
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("cond"),
                callback=lambda ctx: ComponentContribution(residual_values={}),
            ),
        ]
        physical_set = build_physical_adapters_from_contributions(toy_binding_context, adapters)
        from mpl_sim.network.physical_adapters import PhysicalResidualContext

        ctx_pa = PhysicalResidualContext(unknown_values={"x": 1.0})
        with pytest.raises(TypeError, match="ComponentContribution"):
            physical_set.adapters[0].callback(ctx_pa)

    # ------------------------------------------------------------------
    # Item 28: missing required residual value rejected
    # ------------------------------------------------------------------

    def test_missing_required_residual_rejected(self, toy_binding_context):
        """Item 28: required residual not provided by any callback → ValueError."""
        # Both callbacks return nothing; no residual values covered
        adapters = [
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("evap"),
                callback=lambda ctx: ComponentContribution(residual_values={}),
            ),
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("cond"),
                callback=lambda ctx: ComponentContribution(residual_values={}),
            ),
        ]
        physical_set = build_physical_adapters_from_contributions(toy_binding_context, adapters)
        from mpl_sim.network.physical_adapters import PhysicalResidualContext

        ctx_pa = PhysicalResidualContext(unknown_values={"x": 1.0})
        with pytest.raises(ValueError, match="not provided"):
            physical_set.adapters[0].callback(ctx_pa)

    # ------------------------------------------------------------------
    # Item 29: undeclared residual value rejected
    # ------------------------------------------------------------------

    def test_undeclared_residual_rejected(self, toy_binding_context):
        """Item 29: callback returning undeclared residual name → ValueError."""

        def undeclared_cb(ctx: ComponentContributionContext) -> ComponentContribution:
            return ComponentContribution(
                residual_values={
                    "mass_balance:n1": 0.0,
                    "pressure_drop:evap": 0.0,
                    "UNDECLARED_RESIDUAL": 99.0,  # not in assembly
                }
            )

        adapters = [
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("evap"), callback=undeclared_cb
            ),
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("cond"),
                callback=lambda ctx: ComponentContribution(
                    residual_values={
                        "mass_balance:n2": 0.0,
                        "pressure_drop:cond": 0.0,
                    }
                ),
            ),
        ]
        physical_set = build_physical_adapters_from_contributions(toy_binding_context, adapters)
        from mpl_sim.network.physical_adapters import PhysicalResidualContext

        ctx_pa = PhysicalResidualContext(unknown_values={"x": 1.0})
        with pytest.raises(ValueError, match="undeclared"):
            physical_set.adapters[0].callback(ctx_pa)


# ---------------------------------------------------------------------------
# 30. one-shot evaluation through Phase 13G
# ---------------------------------------------------------------------------


class TestPhase13GIntegration:
    def test_one_shot_evaluation_gives_expected_residuals(
        self,
        toy_binding_context,
        toy_contribution_adapters,
        toy_unknown_values,
        toy_assembly,
        toy_scales,
    ):
        """Item 30: Phase 13G one-shot evaluation gives expected toy residuals."""
        physical_set = build_physical_adapters_from_contributions(
            toy_binding_context, toy_contribution_adapters
        )
        evaluators = build_network_residual_evaluators(toy_assembly, physical_set)
        uv = NetworkUnknownValues(values=toy_unknown_values)

        result = evaluate_network_residuals(toy_assembly, uv, evaluators, toy_scales)

        rv = {e.spec.name: e.value for e in result.evaluations}
        assert rv["mass_balance:n1"] == pytest.approx(0.0)
        assert rv["mass_balance:n2"] == pytest.approx(0.0)
        assert rv["pressure_drop:evap"] == pytest.approx(400.0)
        assert rv["pressure_drop:cond"] == pytest.approx(0.0)

    def test_residual_order_matches_assembly_declaration(
        self,
        toy_binding_context,
        toy_contribution_adapters,
        toy_unknown_values,
        toy_assembly,
        toy_scales,
    ):
        """Item 30 (order): evaluation result order matches assembly declaration."""
        physical_set = build_physical_adapters_from_contributions(
            toy_binding_context, toy_contribution_adapters
        )
        evaluators = build_network_residual_evaluators(toy_assembly, physical_set)
        uv = NetworkUnknownValues(values=toy_unknown_values)

        result = evaluate_network_residuals(toy_assembly, uv, evaluators, toy_scales)

        names = [e.spec.name for e in result.evaluations]
        assert names == list(toy_assembly.residuals.names())


# ---------------------------------------------------------------------------
# 31. Phase 13H solve on solvable 2-unknown toy problem
# ---------------------------------------------------------------------------


class TestPhase13HSolve:
    """Item 31: Phase 13H solve works on a solvable toy contribution problem.

    Toy solvable system (no pressure, 2 unknowns, 2 residuals):
      unknowns: mdot:c1, mdot:c2
      residuals: mass_balance:n1, mass_balance:n2

    c1 contributes:  mass_balance:n1 = mdot:c1 + mdot:c2 - 5
    c2 contributes:  mass_balance:n2 = mdot:c1 - mdot:c2 - 1

    Solution: mdot:c1 = 3.0, mdot:c2 = 2.0  (linear; converges in 1 Newton step)
    """

    @pytest.fixture
    def solvable_graph(self):
        return NetworkGraph(
            nodes=[_node("n1"), _node("n2")],
            instances=[
                _inst("c1", "comp_type", "n1", "n2"),
                _inst("c2", "comp_type", "n2", "n1"),
            ],
        )

    @pytest.fixture
    def solvable_assembly(self, solvable_graph):
        return assemble_network_residuals(
            solvable_graph,
            include_pressure_unknowns=False,
            include_pressure_residuals=False,
        )

    @pytest.fixture
    def solvable_binding_context(self, solvable_graph, solvable_assembly):
        bindings = [
            ComponentBinding(instance_id=ComponentInstanceId("c1"), binding_name="comp1"),
            ComponentBinding(instance_id=ComponentInstanceId("c2"), binding_name="comp2"),
        ]
        return build_binding_context(
            solvable_graph, solvable_assembly, bindings, ComponentStateMap()
        )

    def _c1_cb(self, ctx: ComponentContributionContext) -> ComponentContribution:
        v = ctx.unknown_values
        return ComponentContribution(
            residual_values={"mass_balance:n1": v["mdot:c1"] + v["mdot:c2"] - 5.0}
        )

    def _c2_cb(self, ctx: ComponentContributionContext) -> ComponentContribution:
        v = ctx.unknown_values
        return ComponentContribution(
            residual_values={"mass_balance:n2": v["mdot:c1"] - v["mdot:c2"] - 1.0}
        )

    def test_13h_solve_converges(self, solvable_binding_context, solvable_assembly):
        """Item 31: Phase 13H Newton solver finds exact solution in 1 step."""
        adapters = [
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("c1"), callback=self._c1_cb
            ),
            ComponentContributionAdapter(
                instance_id=ComponentInstanceId("c2"), callback=self._c2_cb
            ),
        ]
        physical_set = build_physical_adapters_from_contributions(
            solvable_binding_context, adapters
        )
        evaluators = build_network_residual_evaluators(solvable_assembly, physical_set)
        initial = NetworkUnknownValues(values={"mdot:c1": 0.0, "mdot:c2": 0.0})
        scales = {"mass_balance:n1": 1.0, "mass_balance:n2": 1.0}
        config = NetworkSolveConfig(
            max_iterations=20,
            tolerance=1e-10,
            finite_difference_step=1e-6,
        )
        result = solve_network_residual_problem(
            solvable_assembly, initial, evaluators, scales, config
        )

        assert result.converged, f"expected convergence; reason: {result.reason}"
        sol = result.final_unknown_values.values
        assert sol["mdot:c1"] == pytest.approx(3.0, abs=1e-9)
        assert sol["mdot:c2"] == pytest.approx(2.0, abs=1e-9)


# ---------------------------------------------------------------------------
# 32–40. Architecture boundary: AST checks on contribution_adapters.py source
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    """Items 32–40: AST-based boundary checks on contribution_adapters.py."""

    def _source(self) -> str:
        return _SRC.read_text(encoding="utf-8")

    def _source_without_docstrings(self) -> str:
        src = self._source()
        tree = ast.parse(src)
        docstring_linenos: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
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

    def test_source_file_exists(self):
        """Source file is present."""
        assert _SRC.exists(), f"expected {_SRC}"

    def test_no_real_component_execution(self):
        """Item 32: no import of mpl_sim.components."""
        for mod in self._imported_modules():
            assert "components" not in mod

    def test_no_contribute_call_in_source(self):
        """Item 33: 'contribute' does not appear in non-docstring code."""
        tree = ast.parse(self._source())
        func_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "contribute" not in func_names
        assert "contribute" not in self._source_without_docstrings()

    def test_no_property_lookup_in_source(self):
        """Item 34: PropertyBackend is not imported or referenced in non-docstring code."""
        for mod in self._imported_modules():
            assert "properties" not in mod
        assert "PropertyBackend" not in self._source_without_docstrings()

    def test_no_registry_resolution_in_source(self):
        """Item 35: CorrelationRegistry is not imported or referenced."""
        for mod in self._imported_modules():
            assert "correlations" not in mod
        assert "CorrelationRegistry" not in self._source_without_docstrings()
        assert "HeatExchangerModelRegistry" not in self._source_without_docstrings()

    def test_no_coolprop_in_source(self):
        """Item 36: no CoolProp import."""
        for mod in self._imported_modules():
            assert "CoolProp" not in mod
        assert "CoolProp" not in self._source_without_docstrings()

    def test_no_system_state_in_source(self):
        """Item 37: no SystemState or solvers import in non-docstring code."""
        for mod in self._imported_modules():
            assert "solvers" not in mod
        assert "SystemState" not in self._source_without_docstrings()

    def test_no_fluid_state_attached_to_graph(self):
        """Item 38: FluidState not referenced in non-docstring code."""
        assert "FluidState" not in self._source_without_docstrings()

    def test_no_physical_values_on_graph(self):
        """Item 39: no hx_models or calibration import."""
        for mod in self._imported_modules():
            assert "hx_models" not in mod
            assert "calibration" not in mod

    def test_no_automatic_physics_from_component_type(self):
        """Item 40: component_type not accessed in non-docstring code."""
        tree = ast.parse(self._source())
        attr_names = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)]
        assert "component_type" not in attr_names
        assert "component_type" not in self._source_without_docstrings()


# ---------------------------------------------------------------------------
# 41. Public exports from mpl_sim.network
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_contribution_context_exported(self):
        """Item 41: ComponentContributionContext in mpl_sim.network.__all__."""
        import mpl_sim.network as net

        assert "ComponentContributionContext" in net.__all__
        assert net.ComponentContributionContext is ComponentContributionContext

    def test_contribution_exported(self):
        """Item 41: ComponentContribution in mpl_sim.network.__all__."""
        import mpl_sim.network as net

        assert "ComponentContribution" in net.__all__
        assert net.ComponentContribution is ComponentContribution

    def test_contribution_adapter_exported(self):
        """Item 41: ComponentContributionAdapter in mpl_sim.network.__all__."""
        import mpl_sim.network as net

        assert "ComponentContributionAdapter" in net.__all__
        assert net.ComponentContributionAdapter is ComponentContributionAdapter

    def test_contribution_adapter_set_exported(self):
        """Item 41: ComponentContributionAdapterSet in mpl_sim.network.__all__."""
        import mpl_sim.network as net

        assert "ComponentContributionAdapterSet" in net.__all__
        assert net.ComponentContributionAdapterSet is ComponentContributionAdapterSet

    def test_builder_exported(self):
        """Item 41: build_physical_adapters_from_contributions in mpl_sim.network.__all__."""
        import mpl_sim.network as net

        assert "build_physical_adapters_from_contributions" in net.__all__
        assert (
            net.build_physical_adapters_from_contributions
            is build_physical_adapters_from_contributions
        )

    def test_prior_phase_exports_intact(self):
        """Item 41: prior Phase 14B exports still present."""
        import mpl_sim.network as net

        for name in [
            "NetworkBindingContext",
            "ComponentBinding",
            "ComponentBindingSet",
            "ComponentStateMap",
            "build_binding_context",
            "PhysicalResidualContext",
            "PhysicalResidualAdapter",
            "PhysicalResidualAdapterSet",
            "build_network_residual_evaluators",
            "NetworkGraph",
            "ComponentInstanceId",
            "GraphNodeId",
            "assemble_network_residuals",
            "evaluate_network_residuals",
            "solve_network_residual_problem",
        ]:
            assert name in net.__all__, f"{name} missing from __all__"


# ---------------------------------------------------------------------------
# 42. Existing phase regression gate
# ---------------------------------------------------------------------------


class TestExistingPhaseRegression:
    def test_phase_14b_binding_context_construction(self):
        """Item 42: Phase 14B NetworkBindingContext still constructs correctly."""
        ctx = _toy_binding_context()
        assert isinstance(ctx, NetworkBindingContext)
        assert len(ctx.binding_set.bindings) == 2

    def test_phase_14a_physical_adapter_construction(self):
        """Item 42: Phase 14A PhysicalResidualAdapter still constructs correctly."""
        a = PhysicalResidualAdapter(
            residual_name="r:test",
            callback=lambda ctx: 0.0,
        )
        assert a.residual_name == "r:test"

    def test_phase_13g_evaluation_still_works(self):
        """Item 42: Phase 13G evaluate_network_residuals still works."""
        from mpl_sim.network import NetworkResidualEvaluator

        graph = _toy_graph()
        asm = assemble_network_residuals(graph)
        evaluators = [
            NetworkResidualEvaluator(name=n, callback=lambda v: 0.0) for n in asm.residuals.names()
        ]
        uv = NetworkUnknownValues(values={n: 1.0 for n in asm.unknowns.names()})
        scales = {n: 1.0 for n in asm.residuals.names()}
        result = evaluate_network_residuals(asm, uv, evaluators, scales)
        assert result.max_abs_scaled == pytest.approx(0.0)

    def test_docs_do_not_claim_full_physical_simulator(self):
        """Item 42: contribution_adapters.py docstring is explicit about limitations."""
        src_text = _SRC.read_text(encoding="utf-8")
        assert "contribution-adapter foundation only" in src_text
        assert "DOES NOT" in src_text
