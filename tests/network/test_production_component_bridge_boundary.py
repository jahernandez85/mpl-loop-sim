"""Block 15A.1 production component bridge boundary tests.

Coverage items (required):

Context immutability:
 1.  valid ProductionBridgeExecutionContext construction
 2.  context rejects non-NetworkBindingContext binding_context
 3.  context unknown_values are defensively copied / immutable
 4.  context metadata is defensively copied / immutable

Binding validation:
 5.  valid ProductionComponentBridgeBinding construction
 6.  binding rejects wrong component_id type (non-ComponentInstanceId)
 7.  binding rejects bridge missing produce_records method
 8.  binding rejects bridge with non-callable produce_records
 9.  valid ProductionComponentBridgeSet construction
10.  bridge set preserves deterministic insertion order
11.  bridge set rejects wrong entry type
12.  bridge set rejects duplicate component ID
13.  source-list mutation does not affect bridge set
14.  bridge set is frozen (immutable)

Protocol / method validation:
15.  bridge stub satisfies ProductionContributionBridgeProtocol
16.  object without produce_records does not satisfy protocol
17.  method named contribute is not defined in bridge module (AST check)
18.  .contribute( not called in bridge module (AST check)
19.  production classes without contribute are not treated as executable

Execution behaviour:
20.  all bridge objects execute in deterministic binding order
21.  valid execution returns ContributionRecordSet
22.  execution rejects non-NetworkBindingContext binding_context
23.  execution rejects missing bridge binding
24.  execution rejects extra/unbound bridge binding
25.  execution propagates bridge exception
26.  execution rejects wrong return type from bridge
27.  execution rejects record for wrong component
28.  execution rejects duplicate (component_id, name) records

Integration with existing stack:
29.  convenience wrapper returns Phase 14C ComponentContribution
30.  returned ContributionRecordSet maps through ContributionResidualMap
31.  one-shot evaluation path through Phase 14D/14C/14A/13G works

Public export tests:
32.  new public symbols exported from mpl_sim.network
33.  no accidental broad exports (symbols individually accessible)

Boundary tests (import-line and AST based):
34.  no CoolProp import in bridge module
35.  no PropertyBackend import in bridge module
36.  no CorrelationRegistry import in bridge module
37.  no contribute( call in bridge module (AST)
38.  no SystemState import in bridge module
39.  no FluidState import in bridge module
40.  no component_type physics inference in bridge module (no attribute access)
41.  no solve(network) or NetworkGraph.solve definition in bridge module
42.  bridge module does not import mpl_sim.components
43.  bridge module does not import mpl_sim.properties

Regression:
44.  Phase 14G inspection still reports NO_CONTRIBUTE_METHOD for all six
     known production component classes
45.  Phase 14F provider adapter still importable and functional
46.  contribute not defined on any new bridge type
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from mpl_sim.network import (
    ComponentBinding,
    ComponentContribution,
    ComponentContributionAdapter,
    ComponentContributionAdapterSet,
    ComponentContributionContext,
    ComponentInstance,
    ComponentInstanceId,
    ContributionRecord,
    ContributionRecordSet,
    ContributionResidualMap,
    GraphNode,
    GraphNodeId,
    NetworkBindingContext,
    NetworkGraph,
    NetworkUnknownValues,
    ProductionBridgeExecutionContext,
    ProductionComponentBridgeBinding,
    ProductionComponentBridgeSet,
    ProductionContributionBridgeProtocol,
    assemble_network_residuals,
    build_binding_context,
    build_component_contribution_from_production_bridge_execution,
    build_network_residual_evaluators,
    build_physical_adapters_from_contributions,
    evaluate_network_residuals,
    execute_production_bridge_contributions,
    inspect_known_production_component_contracts,
    map_contribution_records_to_component_contribution,
)
from mpl_sim.network.component_binding import ComponentStateMap
from mpl_sim.network.production_component_bridge import (
    ProductionBridgeExecutionContext as _CtxDirect,
)
from mpl_sim.network.production_component_bridge import (
    ProductionComponentBridgeBinding as _BindingDirect,
)
from mpl_sim.network.production_component_bridge import (
    ProductionComponentBridgeSet as _SetDirect,
)
from mpl_sim.network.production_component_bridge import (
    build_component_contribution_from_production_bridge_execution as _build_direct,
)
from mpl_sim.network.production_component_bridge import (
    execute_production_bridge_contributions as _exec_direct,
)

# ---------------------------------------------------------------------------
# Source file path for boundary checks
# ---------------------------------------------------------------------------

_SRC = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "production_component_bridge.py"
)

# ---------------------------------------------------------------------------
# Shared helpers
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
# Controlled stub bridge objects — NOT real production component classes.
# These are local test objects only.  They expose produce_records (NOT contribute).
# ---------------------------------------------------------------------------


class StubEvaporatorBridge:
    """Controlled stub bridge for 'evap'. NOT a real production component."""

    def produce_records(self, context: ProductionBridgeExecutionContext) -> ContributionRecordSet:
        v = context.unknown_values
        return ContributionRecordSet(
            records=(
                ContributionRecord(
                    component_id=_EVAP_ID,
                    name="mass_balance",
                    value=v["mdot:evap"] - v["mdot:cond"],
                ),
                ContributionRecord(
                    component_id=_EVAP_ID,
                    name="pressure_drop",
                    value=v["P:n1"] - v["P:n2"] - 600.0,
                ),
            )
        )


class StubCondenserBridge:
    """Controlled stub bridge for 'cond'. NOT a real production component."""

    def produce_records(self, context: ProductionBridgeExecutionContext) -> ContributionRecordSet:
        v = context.unknown_values
        return ContributionRecordSet(
            records=(
                ContributionRecord(
                    component_id=_COND_ID,
                    name="mass_balance",
                    value=v["mdot:cond"] - v["mdot:evap"],
                ),
                ContributionRecord(
                    component_id=_COND_ID,
                    name="pressure_drop",
                    value=v["P:n2"] - v["P:n1"] + 1000.0,
                ),
            )
        )


def _evap_binding() -> ProductionComponentBridgeBinding:
    return ProductionComponentBridgeBinding(component_id=_EVAP_ID, bridge=StubEvaporatorBridge())


def _cond_binding() -> ProductionComponentBridgeBinding:
    return ProductionComponentBridgeBinding(component_id=_COND_ID, bridge=StubCondenserBridge())


def _bridge_set() -> ProductionComponentBridgeSet:
    return ProductionComponentBridgeSet(bindings=(_evap_binding(), _cond_binding()))


# ---------------------------------------------------------------------------
# 1–4: ProductionBridgeExecutionContext
# ---------------------------------------------------------------------------


class TestProductionBridgeExecutionContext:
    def test_valid_construction(self):
        """Item 1: valid context construction."""
        bc = _toy_binding_context()
        ctx = ProductionBridgeExecutionContext(
            binding_context=bc,
            unknown_values={"mdot:evap": 0.05},
        )
        assert ctx.binding_context is bc
        assert ctx.unknown_values["mdot:evap"] == pytest.approx(0.05)
        assert ctx.metadata is None

    def test_valid_construction_with_metadata(self):
        """Item 1: valid context construction with metadata."""
        bc = _toy_binding_context()
        ctx = ProductionBridgeExecutionContext(
            binding_context=bc,
            unknown_values={"x": 1.0},
            metadata={"run_id": "test15a1"},
        )
        assert ctx.metadata["run_id"] == "test15a1"

    def test_rejects_non_binding_context(self):
        """Item 2: non-NetworkBindingContext binding_context rejected."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            ProductionBridgeExecutionContext(
                binding_context="not_a_binding_context",
                unknown_values={},
            )

    def test_rejects_non_mapping_unknown_values(self):
        """Item 2: non-Mapping unknown_values rejected."""
        bc = _toy_binding_context()
        with pytest.raises(TypeError, match="Mapping"):
            ProductionBridgeExecutionContext(
                binding_context=bc,
                unknown_values=[1.0, 2.0],  # type: ignore[arg-type]
            )

    def test_unknown_values_defensively_copied(self):
        """Item 3: post-construction mutation of source dict does not affect context."""
        bc = _toy_binding_context()
        source = {"mdot:evap": 0.05}
        ctx = ProductionBridgeExecutionContext(binding_context=bc, unknown_values=source)
        source["mdot:evap"] = 999.0
        assert ctx.unknown_values["mdot:evap"] == pytest.approx(0.05)

    def test_unknown_values_immutable(self):
        """Item 3: context unknown_values is read-only (MappingProxyType)."""
        bc = _toy_binding_context()
        ctx = ProductionBridgeExecutionContext(
            binding_context=bc, unknown_values={"mdot:evap": 0.05}
        )
        with pytest.raises(TypeError):
            ctx.unknown_values["mdot:evap"] = 0.99  # type: ignore[index]

    def test_metadata_defensively_copied(self):
        """Item 4: post-construction mutation of source metadata does not affect context."""
        bc = _toy_binding_context()
        meta = {"k": "v"}
        ctx = ProductionBridgeExecutionContext(binding_context=bc, unknown_values={}, metadata=meta)
        meta["k"] = "CHANGED"
        assert ctx.metadata["k"] == "v"

    def test_metadata_immutable(self):
        """Item 4: context metadata is read-only (MappingProxyType)."""
        bc = _toy_binding_context()
        ctx = ProductionBridgeExecutionContext(
            binding_context=bc, unknown_values={}, metadata={"k": "v"}
        )
        with pytest.raises(TypeError):
            ctx.metadata["k"] = "CHANGED"  # type: ignore[index]

    def test_metadata_none_by_default(self):
        """Item 1: metadata defaults to None when not supplied."""
        bc = _toy_binding_context()
        ctx = ProductionBridgeExecutionContext(binding_context=bc, unknown_values={})
        assert ctx.metadata is None

    def test_rejects_non_mapping_metadata(self):
        """Item 4: non-Mapping metadata rejected."""
        bc = _toy_binding_context()
        with pytest.raises(TypeError, match="Mapping"):
            ProductionBridgeExecutionContext(
                binding_context=bc,
                unknown_values={},
                metadata="not_a_mapping",  # type: ignore[arg-type]
            )

    def test_context_is_frozen(self):
        """Item 3: context dataclass is frozen (immutable)."""
        bc = _toy_binding_context()
        ctx = ProductionBridgeExecutionContext(binding_context=bc, unknown_values={})
        with pytest.raises((TypeError, AttributeError)):
            ctx.binding_context = bc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 5–14: ProductionComponentBridgeBinding and ProductionComponentBridgeSet
# ---------------------------------------------------------------------------


class TestProductionComponentBridgeBinding:
    def test_valid_construction(self):
        """Item 5: valid binding construction."""
        b = _evap_binding()
        assert b.component_id == _EVAP_ID
        assert isinstance(b.bridge, StubEvaporatorBridge)

    def test_rejects_wrong_component_id_type_str(self):
        """Item 6: string component_id rejected."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ProductionComponentBridgeBinding(
                component_id="evap",  # type: ignore[arg-type]
                bridge=StubEvaporatorBridge(),
            )

    def test_rejects_integer_component_id(self):
        """Item 6: integer component_id rejected."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ProductionComponentBridgeBinding(
                component_id=42,  # type: ignore[arg-type]
                bridge=StubEvaporatorBridge(),
            )

    def test_rejects_bridge_missing_method(self):
        """Item 7: bridge without produce_records attribute rejected."""

        class NoBridgeMethod:
            pass

        with pytest.raises(TypeError, match="produce_records"):
            ProductionComponentBridgeBinding(
                component_id=_EVAP_ID,
                bridge=NoBridgeMethod(),
            )

    def test_rejects_bridge_non_callable_method(self):
        """Item 8: bridge with non-callable produce_records rejected."""

        class NonCallableBridge:
            produce_records = "not_a_callable"

        with pytest.raises(TypeError, match="callable"):
            ProductionComponentBridgeBinding(
                component_id=_EVAP_ID,
                bridge=NonCallableBridge(),
            )

    def test_binding_is_frozen(self):
        """Item 5: binding is immutable (frozen dataclass)."""
        b = _evap_binding()
        with pytest.raises((TypeError, AttributeError)):
            b.component_id = _COND_ID  # type: ignore[misc]


class TestProductionComponentBridgeSet:
    def test_valid_construction(self):
        """Item 9: valid set construction."""
        bs = _bridge_set()
        assert len(bs.bindings) == 2

    def test_accepts_list_input(self):
        """Item 9: list input is converted to tuple."""
        bs = ProductionComponentBridgeSet(bindings=[_evap_binding(), _cond_binding()])
        assert isinstance(bs.bindings, tuple)
        assert len(bs.bindings) == 2

    def test_preserves_deterministic_order(self):
        """Item 10: insertion order is preserved."""
        bs = ProductionComponentBridgeSet(bindings=(_evap_binding(), _cond_binding()))
        assert bs.bindings[0].component_id == _EVAP_ID
        assert bs.bindings[1].component_id == _COND_ID

    def test_reversed_order_preserved(self):
        """Item 10: reversed insertion order is also preserved."""
        bs = ProductionComponentBridgeSet(bindings=(_cond_binding(), _evap_binding()))
        assert bs.bindings[0].component_id == _COND_ID
        assert bs.bindings[1].component_id == _EVAP_ID

    def test_rejects_wrong_entry_type(self):
        """Item 11: wrong entry type rejected."""
        with pytest.raises(TypeError, match="ProductionComponentBridgeBinding"):
            ProductionComponentBridgeSet(
                bindings=(_evap_binding(), "not_a_binding")  # type: ignore[arg-type]
            )

    def test_rejects_duplicate_component_id(self):
        """Item 12: duplicate component_id rejected."""
        with pytest.raises(ValueError, match="duplicate"):
            ProductionComponentBridgeSet(bindings=(_evap_binding(), _evap_binding()))

    def test_source_list_mutation_does_not_affect_set(self):
        """Item 13: mutating source list after construction does not alter set."""
        source = [_evap_binding(), _cond_binding()]
        bs = ProductionComponentBridgeSet(bindings=source)
        source.clear()
        assert len(bs.bindings) == 2

    def test_bridge_set_is_frozen(self):
        """Item 14: bridge set is frozen (immutable)."""
        bs = _bridge_set()
        with pytest.raises((TypeError, AttributeError)):
            bs.bindings = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 15–19: Protocol / method validation
# ---------------------------------------------------------------------------


class TestProductionContributionBridgeProtocol:
    def test_stub_satisfies_protocol(self):
        """Item 15: stub bridge satisfies ProductionContributionBridgeProtocol."""
        assert isinstance(StubEvaporatorBridge(), ProductionContributionBridgeProtocol)
        assert isinstance(StubCondenserBridge(), ProductionContributionBridgeProtocol)

    def test_object_without_produce_records_fails_protocol(self):
        """Item 16: object without produce_records does not satisfy protocol."""

        class NoMethod:
            pass

        assert not isinstance(NoMethod(), ProductionContributionBridgeProtocol)

    def test_no_method_named_contribute_defined_in_module(self):
        """Item 17: no function or method named 'contribute' is defined in bridge module (AST)."""
        tree = ast.parse(_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "contribute":
                raise AssertionError(
                    "Found a method/function named 'contribute' defined in bridge module"
                )

    def test_no_contribute_attribute_call_in_bridge_module(self):
        """Item 18: .contribute( attribute call absent from bridge module (AST)."""
        tree = ast.parse(_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "contribute":
                    raise AssertionError("Found .contribute( call in bridge module source")

    def test_bridge_stubs_do_not_have_contribute(self):
        """Item 17: bridge stub objects do not define a method named contribute."""
        assert not hasattr(StubEvaporatorBridge(), "contribute")
        assert not hasattr(StubCondenserBridge(), "contribute")

    def test_production_classes_without_contribute_not_executable(self):
        """Item 19: known production classes without contribute are not bridge-ready.

        Phase 14G confirmed all six known production classes have NO_CONTRIBUTE_METHOD.
        The bridge boundary does not pretend they are executable bridge objects.
        """
        from mpl_sim.network import ProductionComponentContractStatus

        results = inspect_known_production_component_contracts()
        for r in results:
            assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD, (
                f"{r.class_name} unexpectedly has status {r.status!r}; "
                "bridge boundary must not treat non-contribute classes as executable"
            )

    def test_production_class_instances_do_not_satisfy_protocol(self):
        """Item 19: real production class instances do not satisfy the bridge protocol.

        They lack produce_records, so isinstance check is False.
        Imports are inside function body only, never at module level.
        """
        from mpl_sim.components.base import Component  # noqa: PLC0415
        from mpl_sim.components.pipe import Pipe  # noqa: PLC0415

        assert not isinstance(Component, ProductionContributionBridgeProtocol)
        assert not isinstance(Pipe, ProductionContributionBridgeProtocol)


# ---------------------------------------------------------------------------
# 20–28: execute_production_bridge_contributions
# ---------------------------------------------------------------------------


class TestExecuteProductionBridgeContributions:
    def test_execution_in_deterministic_order(self):
        """Item 20: bridge objects execute in binding order; records preserved."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        result = execute_production_bridge_contributions(bc, _bridge_set(), uvs)
        cids = [r.component_id for r in result.records]
        assert cids[0] == _EVAP_ID
        assert cids[1] == _EVAP_ID
        assert cids[2] == _COND_ID
        assert cids[3] == _COND_ID

    def test_valid_execution_returns_contribution_record_set(self):
        """Item 21: valid execution returns ContributionRecordSet."""
        bc = _toy_binding_context()
        result = execute_production_bridge_contributions(bc, _bridge_set(), _toy_unknown_values())
        assert isinstance(result, ContributionRecordSet)
        assert len(result.records) == 4

    def test_values_computed_from_unknown_values(self):
        """Item 21: computed values match expected bridge outputs."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        result = execute_production_bridge_contributions(bc, _bridge_set(), uvs)
        evap_mb = next(
            r for r in result.records if r.component_id == _EVAP_ID and r.name == "mass_balance"
        )
        evap_pd = next(
            r for r in result.records if r.component_id == _EVAP_ID and r.name == "pressure_drop"
        )
        assert evap_mb.value == pytest.approx(0.0)
        assert evap_pd.value == pytest.approx(0.0)

    def test_execution_rejects_non_binding_context(self):
        """Item 22: non-NetworkBindingContext binding_context rejected."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            execute_production_bridge_contributions(
                "not_a_bc",
                _bridge_set(),
                _toy_unknown_values(),
            )

    def test_execution_rejects_missing_bridge_binding(self):
        """Item 23: missing bridge binding for a bound component rejected."""
        bc = _toy_binding_context()
        evap_only = ProductionComponentBridgeSet(bindings=(_evap_binding(),))
        with pytest.raises(ValueError, match="missing"):
            execute_production_bridge_contributions(bc, evap_only, _toy_unknown_values())

    def test_execution_rejects_extra_bridge_binding(self):
        """Item 24: bridge binding for unbound component rejected."""
        bc = _toy_binding_context()
        extra_id = ComponentInstanceId("extra_component")

        class ExtraBridge:
            def produce_records(self, ctx):
                return ContributionRecordSet(records=())

        extra_binding = ProductionComponentBridgeBinding(
            component_id=extra_id, bridge=ExtraBridge()
        )
        three = ProductionComponentBridgeSet(
            bindings=(_evap_binding(), _cond_binding(), extra_binding)
        )
        with pytest.raises(ValueError, match="not bound"):
            execute_production_bridge_contributions(bc, three, _toy_unknown_values())

    def test_execution_propagates_bridge_exception(self):
        """Item 25: exception raised inside bridge propagates to caller."""

        class RaisingBridge:
            def produce_records(self, ctx):
                raise RuntimeError("bridge exploded")

        bc = _toy_binding_context()
        evap_bad = ProductionComponentBridgeBinding(component_id=_EVAP_ID, bridge=RaisingBridge())
        bad_set = ProductionComponentBridgeSet(bindings=(evap_bad, _cond_binding()))
        with pytest.raises(RuntimeError, match="bridge exploded"):
            execute_production_bridge_contributions(bc, bad_set, _toy_unknown_values())

    def test_execution_rejects_wrong_return_type(self):
        """Item 26: bridge returning non-ContributionRecordSet rejected."""

        class DictReturningBridge:
            def produce_records(self, ctx):
                return {"mass_balance": 0.0}

        bc = _toy_binding_context()
        evap_bad = ProductionComponentBridgeBinding(
            component_id=_EVAP_ID, bridge=DictReturningBridge()
        )
        bad_set = ProductionComponentBridgeSet(bindings=(evap_bad, _cond_binding()))
        with pytest.raises(TypeError, match="ContributionRecordSet"):
            execute_production_bridge_contributions(bc, bad_set, _toy_unknown_values())

    def test_execution_rejects_record_for_wrong_component(self):
        """Item 27: record belonging to a different component_id rejected."""

        class WrongComponentBridge:
            def produce_records(self, ctx):
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(
                            component_id=_COND_ID,  # Wrong — evap expected
                            name="mass_balance",
                            value=0.0,
                        ),
                    )
                )

        bc = _toy_binding_context()
        evap_bad = ProductionComponentBridgeBinding(
            component_id=_EVAP_ID, bridge=WrongComponentBridge()
        )
        bad_set = ProductionComponentBridgeSet(bindings=(evap_bad, _cond_binding()))
        with pytest.raises(ValueError, match="different component"):
            execute_production_bridge_contributions(bc, bad_set, _toy_unknown_values())

    def test_execution_rejects_duplicate_records_within_bridge(self):
        """Item 28: duplicate (component_id, name) pair within single bridge rejected
        at ContributionRecordSet construction time."""
        with pytest.raises(ValueError, match="duplicate"):
            ContributionRecordSet(
                records=(
                    ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                    ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=1.0),
                )
            )

    def test_execution_accepts_iterable_of_bindings(self):
        """Item 21: plain iterable of bridge bindings is accepted."""
        bc = _toy_binding_context()
        result = execute_production_bridge_contributions(
            bc,
            [_evap_binding(), _cond_binding()],
            _toy_unknown_values(),
        )
        assert isinstance(result, ContributionRecordSet)

    def test_execution_accepts_metadata(self):
        """Item 21: optional metadata is forwarded to context without error."""
        bc = _toy_binding_context()
        result = execute_production_bridge_contributions(
            bc,
            _bridge_set(),
            _toy_unknown_values(),
            metadata={"run": "15a1-test"},
        )
        assert isinstance(result, ContributionRecordSet)

    def test_no_mutation_of_inputs(self):
        """Item 21: input dict is not mutated during execution."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        original_keys = set(uvs.keys())
        execute_production_bridge_contributions(bc, _bridge_set(), uvs)
        assert set(uvs.keys()) == original_keys

    def test_reversed_bridge_order_preserved(self):
        """Item 20: reversed bridge order is reflected in record order."""
        bc = _toy_binding_context()
        bs = ProductionComponentBridgeSet(bindings=(_cond_binding(), _evap_binding()))
        result = execute_production_bridge_contributions(bc, bs, _toy_unknown_values())
        cids = [r.component_id for r in result.records]
        assert cids[0] == _COND_ID
        assert cids[1] == _COND_ID
        assert cids[2] == _EVAP_ID
        assert cids[3] == _EVAP_ID


# ---------------------------------------------------------------------------
# 29–31: Integration with existing stack
# ---------------------------------------------------------------------------


class TestBridgeIntegrationWithExistingStack:
    def test_convenience_wrapper_returns_component_contribution(self):
        """Item 29: convenience wrapper returns Phase 14C ComponentContribution."""
        bc = _toy_binding_context()
        result = build_component_contribution_from_production_bridge_execution(
            component_id=_EVAP_ID,
            binding_context=bc,
            bridge_set=_bridge_set(),
            residual_map=_toy_residual_map(),
            unknown_values=_toy_unknown_values(),
        )
        assert isinstance(result, ComponentContribution)

    def test_residual_map_translation(self):
        """Item 30: ContributionRecordSet maps through ContributionResidualMap correctly."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        result = execute_production_bridge_contributions(bc, _bridge_set(), uvs)
        contribution = map_contribution_records_to_component_contribution(
            _EVAP_ID, result, _toy_residual_map()
        )
        assert "mass_balance:n1" in contribution.residual_values
        assert "pressure_drop:evap" in contribution.residual_values
        assert contribution.residual_values["mass_balance:n1"] == pytest.approx(0.0)
        assert contribution.residual_values["pressure_drop:evap"] == pytest.approx(0.0)

    def test_one_shot_evaluation_through_14d_14c_14a_13g(self):
        """Item 31: one-shot evaluation through Phase 14D/14C/14A/13G."""
        bc = _toy_binding_context()
        residual_map = _toy_residual_map()

        def make_cb(component_id):
            def cb(ctx: ComponentContributionContext) -> ComponentContribution:
                record_set = execute_production_bridge_contributions(
                    bc, _bridge_set(), ctx.unknown_values
                )
                return map_contribution_records_to_component_contribution(
                    component_id, record_set, residual_map
                )

            return cb

        adapter_set = ComponentContributionAdapterSet(
            adapters=(
                ComponentContributionAdapter(instance_id=_EVAP_ID, callback=make_cb(_EVAP_ID)),
                ComponentContributionAdapter(instance_id=_COND_ID, callback=make_cb(_COND_ID)),
            )
        )

        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)

        uv = NetworkUnknownValues(
            values={"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        )
        scales = {
            "mass_balance:n1": 0.01,
            "mass_balance:n2": 0.01,
            "pressure_drop:evap": 100.0,
            "pressure_drop:cond": 100.0,
        }
        eval_result = evaluate_network_residuals(bc.assembly, uv, evaluators, scales)
        assert eval_result is not None
        assert eval_result.max_abs_scaled is not None


# ---------------------------------------------------------------------------
# 32–33: Public export tests
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_bridge_context_exported_from_network(self):
        """Item 32: ProductionBridgeExecutionContext exported from mpl_sim.network."""
        from mpl_sim import network

        assert hasattr(network, "ProductionBridgeExecutionContext")

    def test_bridge_protocol_exported_from_network(self):
        """Item 32: ProductionContributionBridgeProtocol exported from mpl_sim.network."""
        from mpl_sim import network

        assert hasattr(network, "ProductionContributionBridgeProtocol")

    def test_bridge_binding_exported_from_network(self):
        """Item 32: ProductionComponentBridgeBinding exported from mpl_sim.network."""
        from mpl_sim import network

        assert hasattr(network, "ProductionComponentBridgeBinding")

    def test_bridge_set_exported_from_network(self):
        """Item 32: ProductionComponentBridgeSet exported from mpl_sim.network."""
        from mpl_sim import network

        assert hasattr(network, "ProductionComponentBridgeSet")

    def test_execute_function_exported_from_network(self):
        """Item 32: execute_production_bridge_contributions exported from mpl_sim.network."""
        from mpl_sim import network

        assert hasattr(network, "execute_production_bridge_contributions")
        assert callable(network.execute_production_bridge_contributions)

    def test_build_function_exported_from_network(self):
        """Item 32: build_component_contribution_from_production_bridge_execution exported."""
        from mpl_sim import network

        assert hasattr(network, "build_component_contribution_from_production_bridge_execution")
        assert callable(network.build_component_contribution_from_production_bridge_execution)

    def test_symbols_in_all(self):
        """Item 33: all new symbols appear in mpl_sim.network.__all__."""
        from mpl_sim import network

        expected = {
            "ProductionBridgeExecutionContext",
            "ProductionContributionBridgeProtocol",
            "ProductionComponentBridgeBinding",
            "ProductionComponentBridgeSet",
            "execute_production_bridge_contributions",
            "build_component_contribution_from_production_bridge_execution",
        }
        for name in expected:
            assert name in network.__all__, f"{name!r} missing from mpl_sim.network.__all__"

    def test_direct_module_import_works(self):
        """Item 33: direct import from production_component_bridge module works."""
        assert _CtxDirect is ProductionBridgeExecutionContext
        assert _BindingDirect is ProductionComponentBridgeBinding
        assert _SetDirect is ProductionComponentBridgeSet
        assert _exec_direct is execute_production_bridge_contributions
        assert _build_direct is build_component_contribution_from_production_bridge_execution


# ---------------------------------------------------------------------------
# 34–43: Boundary tests (import-line and AST based)
# ---------------------------------------------------------------------------


def _import_lines(source: str) -> list[str]:
    """Return all import-statement lines from source."""
    return [
        line
        for line in source.splitlines()
        if line.strip().startswith("import ") or line.strip().startswith("from ")
    ]


class TestBridgeBoundaryChecks:
    def test_no_coolprop_import(self):
        """Item 34: bridge module does not import CoolProp."""
        lines = _import_lines(_SRC.read_text(encoding="utf-8"))
        hits = [ln for ln in lines if "CoolProp" in ln]
        assert not hits, f"CoolProp import found: {hits}"

    def test_no_property_backend_import(self):
        """Item 35: bridge module does not import PropertyBackend."""
        lines = _import_lines(_SRC.read_text(encoding="utf-8"))
        hits = [ln for ln in lines if "PropertyBackend" in ln]
        assert not hits, f"PropertyBackend import found: {hits}"

    def test_no_correlation_registry_import(self):
        """Item 36: bridge module does not import CorrelationRegistry."""
        lines = _import_lines(_SRC.read_text(encoding="utf-8"))
        hits = [
            ln for ln in lines if "CorrelationRegistry" in ln or "HeatExchangerModelRegistry" in ln
        ]
        assert not hits, f"Registry import found: {hits}"

    def test_no_contribute_attribute_call_ast(self):
        """Item 37: .contribute( attribute call absent from bridge module (AST)."""
        tree = ast.parse(_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "contribute":
                    raise AssertionError("Found .contribute( attribute call in bridge module")

    def test_no_contribute_function_defined(self):
        """Item 37: no function or method named 'contribute' defined in bridge module (AST)."""
        tree = ast.parse(_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "contribute":
                raise AssertionError(
                    "Found function/method named 'contribute' defined in bridge module"
                )

    def test_no_system_state_import(self):
        """Item 38: bridge module does not import SystemState."""
        lines = _import_lines(_SRC.read_text(encoding="utf-8"))
        hits = [ln for ln in lines if "SystemState" in ln]
        assert not hits, f"SystemState import found: {hits}"

    def test_no_fluid_state_import(self):
        """Item 39: bridge module does not import FluidState."""
        lines = _import_lines(_SRC.read_text(encoding="utf-8"))
        hits = [ln for ln in lines if "FluidState" in ln]
        assert not hits, f"FluidState import found: {hits}"

    def test_no_component_type_attribute_access(self):
        """Item 40: bridge module does not read component_type attribute to drive physics."""
        tree = ast.parse(_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "component_type":
                raise AssertionError("Found .component_type attribute access in bridge module")

    def test_no_solve_function_defined(self):
        """Item 41: bridge module does not define a function named 'solve'."""
        tree = ast.parse(_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "solve":
                raise AssertionError("Found 'def solve' in bridge module")

    def test_no_components_import(self):
        """Item 42: bridge module does not import from mpl_sim.components."""
        lines = _import_lines(_SRC.read_text(encoding="utf-8"))
        hits = [ln for ln in lines if "mpl_sim.components" in ln]
        assert not hits, f"mpl_sim.components import found: {hits}"

    def test_no_properties_import(self):
        """Item 43: bridge module does not import from mpl_sim.properties."""
        lines = _import_lines(_SRC.read_text(encoding="utf-8"))
        hits = [ln for ln in lines if "mpl_sim.properties" in ln]
        assert not hits, f"mpl_sim.properties import found: {hits}"

    def test_no_fluid_state_attached_to_graph(self):
        """Item 39: executing bridge objects does not attach FluidState to graph nodes."""
        bc = _toy_binding_context()
        execute_production_bridge_contributions(bc, _bridge_set(), _toy_unknown_values())
        for node in bc.graph.nodes():
            assert not hasattr(node, "fluid_state"), "FluidState found on graph node"

    def test_no_physical_values_on_network_graph(self):
        """Item 40: NetworkGraph has no physical value fields after bridge execution."""
        bc = _toy_binding_context()
        execute_production_bridge_contributions(bc, _bridge_set(), _toy_unknown_values())
        graph = bc.graph
        assert not hasattr(graph, "mdot")
        assert not hasattr(graph, "pressure")
        assert not hasattr(graph, "enthalpy")

    def test_no_automatic_physics_from_component_type(self):
        """Item 40: execution is not affected by component_type on graph instances."""

        class ConstantBridge:
            def produce_records(self, ctx):
                return ContributionRecordSet(
                    records=(ContributionRecord(component_id=_EVAP_ID, name="x", value=42.0),)
                )

        g2 = NetworkGraph(
            nodes=[_node("n1"), _node("n2")],
            instances=[
                _inst("evap", "COMPLETELY_UNKNOWN_PHYSICS_TYPE", "n1", "n2"),
                _inst("cond", "condenser", "n2", "n1"),
            ],
        )
        asm2 = assemble_network_residuals(g2)
        bc2 = build_binding_context(
            g2,
            asm2,
            [
                ComponentBinding(instance_id=_EVAP_ID, binding_name="evap"),
                ComponentBinding(instance_id=_COND_ID, binding_name="cond"),
            ],
            ComponentStateMap(),
        )
        evap_b = ProductionComponentBridgeBinding(component_id=_EVAP_ID, bridge=ConstantBridge())
        cond_b = ProductionComponentBridgeBinding(
            component_id=_COND_ID, bridge=StubCondenserBridge()
        )
        bs = ProductionComponentBridgeSet(bindings=(evap_b, cond_b))
        result = execute_production_bridge_contributions(bc2, bs, _toy_unknown_values())
        evap_x = next(r for r in result.records if r.component_id == _EVAP_ID)
        assert evap_x.value == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# 44–46: Regression tests
# ---------------------------------------------------------------------------


class TestRegression:
    def test_phase14g_still_reports_no_contribute_method(self):
        """Item 44: Phase 14G inspection still reports NO_CONTRIBUTE_METHOD for all six
        known production component classes."""
        from mpl_sim.network import (
            ProductionComponentContractStatus,
            inspect_known_production_component_contracts,
        )

        results = inspect_known_production_component_contracts()
        assert len(results) == 6, f"Expected 6 known production classes, got {len(results)}"
        for r in results:
            assert (
                r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{r.class_name}: expected NO_CONTRIBUTE_METHOD, got {r.status!r}"

    def test_phase14f_provider_adapter_still_importable_and_functional(self):
        """Item 45: Phase 14F provider adapter still importable and functional."""
        from mpl_sim.network import (
            ComponentContributionProviderBinding,
            ComponentContributionProviderSet,
            execute_component_provider_contributions,
        )

        class MinimalProvider:
            def produce_records(self, ctx):
                return ContributionRecordSet(
                    records=(ContributionRecord(component_id=_EVAP_ID, name="check", value=1.0),)
                )

        class EmptyProvider:
            def produce_records(self, ctx):
                return ContributionRecordSet(records=())

        bc = _toy_binding_context()
        ps = ComponentContributionProviderSet(
            bindings=(
                ComponentContributionProviderBinding(
                    component_id=_EVAP_ID, provider=MinimalProvider()
                ),
                ComponentContributionProviderBinding(
                    component_id=_COND_ID, provider=EmptyProvider()
                ),
            )
        )
        result = execute_component_provider_contributions(bc, ps, {})
        assert isinstance(result, ContributionRecordSet)

    def test_contribute_not_defined_on_bridge_types(self):
        """Item 46: Bridge types themselves have no 'contribute' attribute."""
        assert not hasattr(ProductionBridgeExecutionContext, "contribute")
        assert not hasattr(ProductionContributionBridgeProtocol, "contribute")
        assert not hasattr(ProductionComponentBridgeBinding, "contribute")
        assert not hasattr(ProductionComponentBridgeSet, "contribute")

    def test_prior_phase_exports_unchanged(self):
        """Item 45: Phase 14E and prior exports remain accessible from mpl_sim.network."""
        from mpl_sim.network import (
            ToyComponentExecutionContext,
            ToyComponentExecutor,
            ToyComponentExecutorSet,
            build_component_contribution_from_toy_execution,
            execute_toy_component_contributions,
        )

        assert ToyComponentExecutionContext is not None
        assert ToyComponentExecutor is not None
        assert ToyComponentExecutorSet is not None
        assert execute_toy_component_contributions is not None
        assert build_component_contribution_from_toy_execution is not None
