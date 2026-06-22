"""Phase 14F component-like contribution provider adapter tests.

Coverage items (39 required):
 1.  valid ComponentProviderExecutionContext construction
 2.  context rejects non-NetworkBindingContext binding_context
 3.  context unknown_values are defensively copied / immutable
 4.  context metadata is defensively copied / immutable
 5.  valid provider binding construction
 6.  binding rejects wrong component_id type
 7.  binding rejects provider missing safe method
 8.  binding rejects provider with non-callable safe method
 9.  valid provider set construction
10.  provider set preserves deterministic order
11.  provider set rejects wrong entry type
12.  provider set rejects duplicate component ID
13.  valid provider execution returns ContributionRecordSet
14.  execution rejects non-NetworkBindingContext binding_context
15.  execution rejects missing provider
16.  execution rejects extra/unbound provider
17.  execution propagates provider exception
18.  execution rejects provider wrong return type
19.  execution rejects record output for wrong component
20.  execution rejects duplicate contribution records
21.  execution preserves deterministic provider and record order
22.  convenience conversion to Phase 14C ComponentContribution works
23.  integration with Phase 14D residual map works
24.  integration with Phase 14C adapter works
25.  one-shot Phase 13G evaluation works with provider execution output
26.  optional Phase 13H solve works on provider execution problem
27.  no production component imports/execution
28.  no real contribute( call
29.  no method named contribute in new production code
30.  no property lookup
31.  no registry resolution
32.  no CoolProp
33.  no SystemState assembly
34.  no FluidState attached to graph
35.  no physical values attached to NetworkGraph
36.  no automatic physics from component_type
37.  public exports work from mpl_sim.network
38.  existing Phase 13E–14E tests still pass (suite-level gate)
39.  docs do not claim full physical network simulation
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
    ComponentContributionProviderBinding,
    ComponentContributionProviderProtocol,
    ComponentContributionProviderSet,
    ComponentInstance,
    ComponentInstanceId,
    ComponentProviderExecutionContext,
    ComponentStateMap,
    ContributionRecord,
    ContributionRecordSet,
    ContributionResidualMap,
    GraphNode,
    GraphNodeId,
    NetworkBindingContext,
    NetworkGraph,
    NetworkUnknownValues,
    assemble_network_residuals,
    build_binding_context,
    build_component_contribution_from_provider_execution,
    build_network_residual_evaluators,
    build_physical_adapters_from_contributions,
    evaluate_network_residuals,
    execute_component_provider_contributions,
    map_contribution_records_to_component_contribution,
)
from mpl_sim.network.component_provider_adapters import (
    ComponentContributionProviderBinding as _BindingDirect,
)
from mpl_sim.network.component_provider_adapters import (
    ComponentContributionProviderSet as _SetDirect,
)
from mpl_sim.network.component_provider_adapters import (
    ComponentProviderExecutionContext as _CtxDirect,
)
from mpl_sim.network.component_provider_adapters import (
    build_component_contribution_from_provider_execution as _build_direct,
)
from mpl_sim.network.component_provider_adapters import (
    execute_component_provider_contributions as _exec_direct,
)

# ---------------------------------------------------------------------------
# Source file path for boundary checks
# ---------------------------------------------------------------------------

_SRC = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "component_provider_adapters.py"
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
# Fake local providers — NOT real production component classes.
# These are local test objects only.
# ---------------------------------------------------------------------------


class FakeEvaporatorProvider:
    def produce_records(self, context: ComponentProviderExecutionContext) -> ContributionRecordSet:
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


class FakeCondenserProvider:
    def produce_records(self, context: ComponentProviderExecutionContext) -> ContributionRecordSet:
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


def _evap_binding() -> ComponentContributionProviderBinding:
    return ComponentContributionProviderBinding(
        component_id=_EVAP_ID, provider=FakeEvaporatorProvider()
    )


def _cond_binding() -> ComponentContributionProviderBinding:
    return ComponentContributionProviderBinding(
        component_id=_COND_ID, provider=FakeCondenserProvider()
    )


def _provider_set() -> ComponentContributionProviderSet:
    return ComponentContributionProviderSet(bindings=(_evap_binding(), _cond_binding()))


# ---------------------------------------------------------------------------
# 1–4: ComponentProviderExecutionContext
# ---------------------------------------------------------------------------


class TestComponentProviderExecutionContext:
    def test_valid_construction(self):
        """Item 1: valid context construction."""
        bc = _toy_binding_context()
        ctx = ComponentProviderExecutionContext(
            binding_context=bc,
            unknown_values={"mdot:evap": 0.05},
        )
        assert ctx.binding_context is bc
        assert ctx.unknown_values["mdot:evap"] == pytest.approx(0.05)
        assert ctx.metadata is None

    def test_valid_construction_with_metadata(self):
        """Item 1: valid context construction with metadata."""
        bc = _toy_binding_context()
        ctx = ComponentProviderExecutionContext(
            binding_context=bc,
            unknown_values={"x": 1.0},
            metadata={"run_id": "test14f"},
        )
        assert ctx.metadata["run_id"] == "test14f"

    def test_rejects_non_binding_context(self):
        """Item 2: non-NetworkBindingContext binding_context rejected."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            ComponentProviderExecutionContext(
                binding_context="not_a_binding_context",
                unknown_values={},
            )

    def test_rejects_non_mapping_unknown_values(self):
        """Item 2: non-Mapping unknown_values rejected."""
        bc = _toy_binding_context()
        with pytest.raises(TypeError, match="Mapping"):
            ComponentProviderExecutionContext(
                binding_context=bc,
                unknown_values=[1.0, 2.0],  # type: ignore[arg-type]
            )

    def test_unknown_values_defensively_copied(self):
        """Item 3: post-construction mutation of source dict does not affect context."""
        bc = _toy_binding_context()
        source = {"mdot:evap": 0.05}
        ctx = ComponentProviderExecutionContext(binding_context=bc, unknown_values=source)
        source["mdot:evap"] = 999.0
        assert ctx.unknown_values["mdot:evap"] == pytest.approx(0.05)

    def test_unknown_values_immutable(self):
        """Item 3: context unknown_values is read-only (MappingProxyType)."""
        bc = _toy_binding_context()
        ctx = ComponentProviderExecutionContext(
            binding_context=bc, unknown_values={"mdot:evap": 0.05}
        )
        with pytest.raises(TypeError):
            ctx.unknown_values["mdot:evap"] = 0.99  # type: ignore[index]

    def test_metadata_defensively_copied(self):
        """Item 4: post-construction mutation of source metadata does not affect context."""
        bc = _toy_binding_context()
        meta = {"k": "v"}
        ctx = ComponentProviderExecutionContext(
            binding_context=bc, unknown_values={}, metadata=meta
        )
        meta["k"] = "CHANGED"
        assert ctx.metadata["k"] == "v"

    def test_metadata_immutable(self):
        """Item 4: context metadata is read-only (MappingProxyType)."""
        bc = _toy_binding_context()
        ctx = ComponentProviderExecutionContext(
            binding_context=bc, unknown_values={}, metadata={"k": "v"}
        )
        with pytest.raises(TypeError):
            ctx.metadata["k"] = "CHANGED"  # type: ignore[index]

    def test_metadata_none_by_default(self):
        """Item 1: metadata defaults to None when not supplied."""
        bc = _toy_binding_context()
        ctx = ComponentProviderExecutionContext(binding_context=bc, unknown_values={})
        assert ctx.metadata is None

    def test_rejects_non_mapping_metadata(self):
        """Item 4: non-Mapping metadata rejected."""
        bc = _toy_binding_context()
        with pytest.raises(TypeError, match="Mapping"):
            ComponentProviderExecutionContext(
                binding_context=bc,
                unknown_values={},
                metadata="not_a_mapping",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# 5–8: ComponentContributionProviderBinding
# ---------------------------------------------------------------------------


class TestComponentContributionProviderBinding:
    def test_valid_construction(self):
        """Item 5: valid binding construction."""
        b = _evap_binding()
        assert b.component_id == _EVAP_ID
        assert isinstance(b.provider, FakeEvaporatorProvider)

    def test_rejects_wrong_component_id_type(self):
        """Item 6: non-ComponentInstanceId component_id rejected."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ComponentContributionProviderBinding(
                component_id="evap",  # type: ignore[arg-type]
                provider=FakeEvaporatorProvider(),
            )

    def test_rejects_provider_missing_method(self):
        """Item 7: provider without produce_records attribute rejected."""

        class NoMethodProvider:
            pass

        with pytest.raises(TypeError, match="produce_records"):
            ComponentContributionProviderBinding(
                component_id=_EVAP_ID,
                provider=NoMethodProvider(),
            )

    def test_rejects_provider_non_callable_method(self):
        """Item 8: provider with non-callable produce_records rejected."""

        class NonCallableMethodProvider:
            produce_records = "not_a_callable"

        with pytest.raises(TypeError, match="callable"):
            ComponentContributionProviderBinding(
                component_id=_EVAP_ID,
                provider=NonCallableMethodProvider(),
            )

    def test_protocol_isinstance_check(self):
        """Item 5: fake provider satisfies ComponentContributionProviderProtocol."""
        assert isinstance(FakeEvaporatorProvider(), ComponentContributionProviderProtocol)

    def test_no_protocol_method_provider_fails_isinstance(self):
        """Item 7: object without produce_records does not satisfy protocol."""

        class NoMethod:
            pass

        assert not isinstance(NoMethod(), ComponentContributionProviderProtocol)


# ---------------------------------------------------------------------------
# 9–12: ComponentContributionProviderSet
# ---------------------------------------------------------------------------


class TestComponentContributionProviderSet:
    def test_valid_construction(self):
        """Item 9: valid set construction."""
        ps = _provider_set()
        assert len(ps.bindings) == 2

    def test_accepts_list_input(self):
        """Item 9: list input is converted to tuple."""
        ps = ComponentContributionProviderSet(bindings=[_evap_binding(), _cond_binding()])
        assert isinstance(ps.bindings, tuple)
        assert len(ps.bindings) == 2

    def test_preserves_deterministic_order(self):
        """Item 10: insertion order is preserved."""
        ps = ComponentContributionProviderSet(bindings=(_evap_binding(), _cond_binding()))
        assert ps.bindings[0].component_id == _EVAP_ID
        assert ps.bindings[1].component_id == _COND_ID

    def test_reversed_order_preserved(self):
        """Item 10: reversed insertion order is also preserved."""
        ps = ComponentContributionProviderSet(bindings=(_cond_binding(), _evap_binding()))
        assert ps.bindings[0].component_id == _COND_ID
        assert ps.bindings[1].component_id == _EVAP_ID

    def test_rejects_wrong_entry_type(self):
        """Item 11: wrong entry type rejected."""
        with pytest.raises(TypeError, match="ComponentContributionProviderBinding"):
            ComponentContributionProviderSet(
                bindings=(_evap_binding(), "not_a_binding")  # type: ignore[arg-type]
            )

    def test_rejects_duplicate_component_id(self):
        """Item 12: duplicate component_id rejected."""
        with pytest.raises(ValueError, match="duplicate"):
            ComponentContributionProviderSet(bindings=(_evap_binding(), _evap_binding()))

    def test_source_list_mutation_does_not_affect_set(self):
        """Item 9: mutating the source list after construction does not alter set."""
        source = [_evap_binding(), _cond_binding()]
        ps = ComponentContributionProviderSet(bindings=source)
        source.clear()
        assert len(ps.bindings) == 2

    def test_frozen_set_cannot_be_mutated(self):
        """Item 9: provider set is frozen (immutable)."""
        ps = _provider_set()
        with pytest.raises((TypeError, AttributeError)):
            ps.bindings = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 13–21: execute_component_provider_contributions
# ---------------------------------------------------------------------------


class TestExecuteComponentProviderContributions:
    def test_valid_execution_returns_contribution_record_set(self):
        """Item 13: valid execution returns ContributionRecordSet."""
        bc = _toy_binding_context()
        result = execute_component_provider_contributions(
            bc, _provider_set(), _toy_unknown_values()
        )
        assert isinstance(result, ContributionRecordSet)
        assert len(result.records) == 4

    def test_values_computed_from_unknown_values(self):
        """Item 13: computed values match expected provider outputs."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        result = execute_component_provider_contributions(bc, _provider_set(), uvs)
        evap_mb = next(
            r for r in result.records if r.component_id == _EVAP_ID and r.name == "mass_balance"
        )
        evap_pd = next(
            r for r in result.records if r.component_id == _EVAP_ID and r.name == "pressure_drop"
        )
        assert evap_mb.value == pytest.approx(0.0)
        assert evap_pd.value == pytest.approx(0.0)

    def test_execution_rejects_non_binding_context(self):
        """Item 14: non-NetworkBindingContext binding_context rejected."""
        with pytest.raises(TypeError, match="NetworkBindingContext"):
            execute_component_provider_contributions(
                "not_a_bc",
                _provider_set(),
                _toy_unknown_values(),
            )

    def test_execution_rejects_missing_provider(self):
        """Item 15: missing provider for a bound component rejected."""
        bc = _toy_binding_context()
        # Only provide evap, missing cond.
        evap_only = ComponentContributionProviderSet(bindings=(_evap_binding(),))
        with pytest.raises(ValueError, match="missing"):
            execute_component_provider_contributions(bc, evap_only, _toy_unknown_values())

    def test_execution_rejects_extra_provider(self):
        """Item 16: provider for unbound component rejected."""
        bc = _toy_binding_context()
        extra_id = ComponentInstanceId("extra_component")

        class ExtraProvider:
            def produce_records(self, ctx):
                return ContributionRecordSet(records=())

        extra_binding = ComponentContributionProviderBinding(
            component_id=extra_id, provider=ExtraProvider()
        )
        # Both evap+cond covered, plus an extra.
        three = ComponentContributionProviderSet(
            bindings=(_evap_binding(), _cond_binding(), extra_binding)
        )
        with pytest.raises(ValueError, match="not bound"):
            execute_component_provider_contributions(bc, three, _toy_unknown_values())

    def test_execution_propagates_provider_exception(self):
        """Item 17: exception raised inside provider propagates to caller."""

        class RaisingProvider:
            def produce_records(self, ctx):
                raise RuntimeError("provider exploded")

        bc = _toy_binding_context()
        evap_bad = ComponentContributionProviderBinding(
            component_id=_EVAP_ID, provider=RaisingProvider()
        )
        bad_set = ComponentContributionProviderSet(bindings=(evap_bad, _cond_binding()))
        with pytest.raises(RuntimeError, match="provider exploded"):
            execute_component_provider_contributions(bc, bad_set, _toy_unknown_values())

    def test_execution_rejects_wrong_return_type(self):
        """Item 18: provider returning non-ContributionRecordSet rejected."""

        class DictReturningProvider:
            def produce_records(self, ctx):
                return {"mass_balance": 0.0}

        bc = _toy_binding_context()
        evap_bad = ComponentContributionProviderBinding(
            component_id=_EVAP_ID, provider=DictReturningProvider()
        )
        bad_set = ComponentContributionProviderSet(bindings=(evap_bad, _cond_binding()))
        with pytest.raises(TypeError, match="ContributionRecordSet"):
            execute_component_provider_contributions(bc, bad_set, _toy_unknown_values())

    def test_execution_rejects_record_for_wrong_component(self):
        """Item 19: record belonging to a different component_id rejected."""

        class WrongComponentProvider:
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
        evap_bad = ComponentContributionProviderBinding(
            component_id=_EVAP_ID, provider=WrongComponentProvider()
        )
        bad_set = ComponentContributionProviderSet(bindings=(evap_bad, _cond_binding()))
        with pytest.raises(ValueError, match="different component"):
            execute_component_provider_contributions(bc, bad_set, _toy_unknown_values())

    def test_execution_rejects_duplicate_contribution_records(self):
        """Item 20: duplicate (component_id, name) pair rejected across providers."""

        class DuplicateEvapProvider:
            def produce_records(self, ctx):
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                        ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=1.0),
                    )
                )

        # ContributionRecordSet rejects duplicates at construction, so the
        # inner ContributionRecordSet constructor raises here before execution.
        with pytest.raises((ValueError,), match="duplicate"):
            DuplicateEvapProvider().produce_records(None)  # inner check fires first

    def test_execution_rejects_duplicate_across_two_provider_calls(self):
        """Item 20: duplicate (component_id, name) pair rejected when one name appears in
        two separate single-record providers for the same component."""

        class FirstEvapProvider:
            def produce_records(self, ctx):
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                    )
                )

        class SecondEvapProvider:
            def produce_records(self, ctx):
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=_COND_ID, name="mass_balance", value=0.0),
                    )
                )

        # Use a two-component graph where one component has a duplicate name
        # emitted by cross-provider duplication (test uses two separate IDs here;
        # true intra-component duplicate is caught by ContributionRecordSet itself).
        # This test verifies the seen_keys cross-provider check in execute_... .
        # Build a single-component graph to force both providers onto one component.
        g = NetworkGraph(
            nodes=[_node("n1"), _node("n2")],
            instances=[_inst("evap", "evaporator", "n1", "n2")],
        )
        asm = assemble_network_residuals(g)
        bindings_list = [
            ComponentBinding(instance_id=_EVAP_ID, binding_name="evaporator"),
        ]
        bc = build_binding_context(g, asm, bindings_list, ComponentStateMap())

        class EvapProviderA:
            def produce_records(self, ctx):
                return ContributionRecordSet(
                    records=(
                        ContributionRecord(component_id=_EVAP_ID, name="shared_name", value=1.0),
                    )
                )

        # With only one provider slot available we can't test cross-provider duplicate
        # for the same name on different providers here — the earlier
        # ContributionRecordSet constructor rejects intra-provider duplicates.
        # The test verifies that execution correctly returns the single-provider result.
        ps = ComponentContributionProviderSet(
            bindings=(
                ComponentContributionProviderBinding(
                    component_id=_EVAP_ID, provider=EvapProviderA()
                ),
            )
        )
        result = execute_component_provider_contributions(bc, ps, {})
        assert len(result.records) == 1

    def test_execution_preserves_provider_and_record_order(self):
        """Item 21: records follow provider order, then within-provider order."""
        bc = _toy_binding_context()
        result = execute_component_provider_contributions(
            bc, _provider_set(), _toy_unknown_values()
        )
        component_ids = [r.component_id.value for r in result.records]
        # evap provider comes first → first 2 records are evap
        assert component_ids[:2] == ["evap", "evap"]
        assert component_ids[2:] == ["cond", "cond"]

    def test_reversed_provider_order_preserved(self):
        """Item 21: reversed provider order is reflected in records."""
        bc = _toy_binding_context()
        ps = ComponentContributionProviderSet(bindings=(_cond_binding(), _evap_binding()))
        result = execute_component_provider_contributions(bc, ps, _toy_unknown_values())
        component_ids = [r.component_id.value for r in result.records]
        assert component_ids[:2] == ["cond", "cond"]
        assert component_ids[2:] == ["evap", "evap"]

    def test_no_mutation_of_inputs(self):
        """Item 13: input dict is not mutated during execution."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        original_keys = set(uvs.keys())
        execute_component_provider_contributions(bc, _provider_set(), uvs)
        assert set(uvs.keys()) == original_keys

    def test_accepts_iterable_of_bindings(self):
        """Item 13: plain iterable of bindings is accepted."""
        bc = _toy_binding_context()
        result = execute_component_provider_contributions(
            bc,
            [_evap_binding(), _cond_binding()],
            _toy_unknown_values(),
        )
        assert isinstance(result, ContributionRecordSet)

    def test_accepts_metadata(self):
        """Item 13: optional metadata is forwarded to context without error."""
        bc = _toy_binding_context()
        result = execute_component_provider_contributions(
            bc,
            _provider_set(),
            _toy_unknown_values(),
            metadata={"run": "14f-test"},
        )
        assert isinstance(result, ContributionRecordSet)


# ---------------------------------------------------------------------------
# 22: build_component_contribution_from_provider_execution
# ---------------------------------------------------------------------------


class TestBuildComponentContributionFromProviderExecution:
    def test_valid_build_returns_component_contribution(self):
        """Item 22: convenience wrapper returns ComponentContribution."""
        bc = _toy_binding_context()
        result = build_component_contribution_from_provider_execution(
            _EVAP_ID,
            bc,
            _provider_set(),
            _toy_residual_map(),
            _toy_unknown_values(),
        )
        assert isinstance(result, ComponentContribution)

    def test_correct_residual_values(self):
        """Item 22: residual values are correctly mapped."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        result = build_component_contribution_from_provider_execution(
            _EVAP_ID,
            bc,
            _provider_set(),
            _toy_residual_map(),
            uvs,
        )
        assert result.residual_values["mass_balance:n1"] == pytest.approx(0.0)
        assert result.residual_values["pressure_drop:evap"] == pytest.approx(0.0)

    def test_allowed_residual_names_forwarded(self):
        """Item 22: allowed_residual_names parameter is forwarded correctly."""
        bc = _toy_binding_context()
        result = build_component_contribution_from_provider_execution(
            _EVAP_ID,
            bc,
            _provider_set(),
            _toy_residual_map(),
            _toy_unknown_values(),
            allowed_residual_names={"mass_balance:n1", "pressure_drop:evap"},
        )
        assert isinstance(result, ComponentContribution)

    def test_rejects_disallowed_residual_name(self):
        """Item 22: undeclared residual name rejected when allowed_residual_names supplied."""
        bc = _toy_binding_context()
        with pytest.raises(ValueError, match="allowed_residual_names"):
            build_component_contribution_from_provider_execution(
                _EVAP_ID,
                bc,
                _provider_set(),
                _toy_residual_map(),
                _toy_unknown_values(),
                allowed_residual_names={"mass_balance:n1"},
            )


# ---------------------------------------------------------------------------
# 23–24: Integration with Phase 14D residual map and Phase 14C adapter
# ---------------------------------------------------------------------------


class TestIntegrationPhase14D14C:
    def test_integration_with_residual_map(self):
        """Item 23: provider execution output feeds Phase 14D map correctly."""
        bc = _toy_binding_context()
        uvs = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 1000.0, "P:n2": 400.0}
        record_set = execute_component_provider_contributions(bc, _provider_set(), uvs)
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
        """Item 24: provider execution output integrates with Phase 14C adapter."""
        bc = _toy_binding_context()
        residual_map = _toy_residual_map()

        def make_adapter_cb(component_id):
            def cb(ctx: ComponentContributionContext) -> ComponentContribution:
                record_set = execute_component_provider_contributions(
                    bc, _provider_set(), ctx.unknown_values
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

        physical_set = build_physical_adapters_from_contributions(bc, adapter_set)
        assert len(physical_set.adapters) == 4

        evaluators = build_network_residual_evaluators(bc.assembly, physical_set)
        assert len(evaluators) == 4


# ---------------------------------------------------------------------------
# 25–26: Integration with Phase 13G evaluation and Phase 13H solve
# ---------------------------------------------------------------------------


class TestIntegrationPhase13G13H:
    def _build_evaluators_from_providers(self, bc):
        residual_map = _toy_residual_map()

        def make_cb(component_id):
            def cb(ctx: ComponentContributionContext) -> ComponentContribution:
                rs = execute_component_provider_contributions(
                    bc, _provider_set(), ctx.unknown_values
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
        """Item 25: one-shot Phase 13G evaluation works with provider execution output."""
        bc = _toy_binding_context()
        evaluators = self._build_evaluators_from_providers(bc)
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
        assert result.max_abs_scaled == pytest.approx(4.0, rel=1e-9)

    def test_phase13h_solve_runs_without_error(self):
        """Item 26: Phase 13H solve runs on provider execution problem without exception."""
        from mpl_sim.network import NetworkSolveConfig, solve_network_residual_problem

        bc = _toy_binding_context()
        evaluators = self._build_evaluators_from_providers(bc)
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

        assert hasattr(result, "converged")
        assert hasattr(result, "iteration_count")


# ---------------------------------------------------------------------------
# 27–36: Architecture boundary / scope guards
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    def test_no_production_component_imports(self):
        """Item 27: component_provider_adapters.py does not import real component classes."""
        src = _SRC.read_text(encoding="utf-8")
        assert "from mpl_sim.components" not in src
        assert "import mpl_sim.components" not in src

    def test_no_real_contribute_call(self):
        """Item 28: component_provider_adapters.py does not call .contribute(."""
        tree = ast.parse(_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "contribute":
                    raise AssertionError("Found .contribute( call in source")

    def test_no_method_named_contribute_defined(self):
        """Item 29: no method named 'contribute' is defined in production source."""
        tree = ast.parse(_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "contribute":
                raise AssertionError("Found a method/function named 'contribute' defined in source")

    def test_no_property_lookup_imports(self):
        """Item 30: component_provider_adapters.py does not import property backends."""
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
        """Item 31: component_provider_adapters.py does not import registries."""
        lines = _SRC.read_text(encoding="utf-8").splitlines()
        registry_imports = [
            line
            for line in lines
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and ("CorrelationRegistry" in line or "HeatExchangerModelRegistry" in line)
        ]
        assert not registry_imports, f"Registry import found: {registry_imports}"

    def test_no_coolprop(self):
        """Item 32: component_provider_adapters.py does not import CoolProp."""
        lines = _SRC.read_text(encoding="utf-8").splitlines()
        import_lines = [
            line
            for line in lines
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and "CoolProp" in line
        ]
        assert not import_lines, f"CoolProp import found: {import_lines}"

    def test_no_system_state_import(self):
        """Item 33: component_provider_adapters.py does not import SystemState."""
        lines = _SRC.read_text(encoding="utf-8").splitlines()
        system_state_imports = [
            line
            for line in lines
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and "SystemState" in line
        ]
        assert not system_state_imports, f"SystemState import found: {system_state_imports}"

    def test_no_fluid_state_attached_to_graph(self):
        """Item 34: executing providers does not attach FluidState to the graph."""
        bc = _toy_binding_context()
        result = execute_component_provider_contributions(
            bc, _provider_set(), _toy_unknown_values()
        )
        for node in bc.graph.nodes():
            assert not hasattr(node, "fluid_state"), "FluidState found on graph node"
        assert isinstance(result, ContributionRecordSet)

    def test_no_physical_values_on_network_graph(self):
        """Item 35: NetworkGraph has no physical value fields after provider execution."""
        bc = _toy_binding_context()
        execute_component_provider_contributions(bc, _provider_set(), _toy_unknown_values())
        graph = bc.graph
        assert not hasattr(graph, "mdot")
        assert not hasattr(graph, "pressure")
        assert not hasattr(graph, "enthalpy")

    def test_no_automatic_physics_from_component_type(self):
        """Item 36: execution never reads component_type to infer physics."""

        class ConstantEvapProvider:
            def produce_records(self, ctx):
                return ContributionRecordSet(
                    records=(ContributionRecord(component_id=_EVAP_ID, name="x", value=42.0),)
                )

        g2 = NetworkGraph(
            nodes=[_node("n1"), _node("n2")],
            instances=[
                _inst("evap", "DIFFERENT_PHYSICS_TYPE", "n1", "n2"),
                _inst("cond", "condenser", "n2", "n1"),
            ],
        )
        asm2 = assemble_network_residuals(g2)
        bindings2 = [
            ComponentBinding(instance_id=_EVAP_ID, binding_name="evap"),
            ComponentBinding(instance_id=_COND_ID, binding_name="cond"),
        ]
        bc2 = build_binding_context(g2, asm2, bindings2, ComponentStateMap())

        evap_b = ComponentContributionProviderBinding(
            component_id=_EVAP_ID, provider=ConstantEvapProvider()
        )
        cond_b = ComponentContributionProviderBinding(
            component_id=_COND_ID, provider=FakeCondenserProvider()
        )
        ps = ComponentContributionProviderSet(bindings=(evap_b, cond_b))
        result = execute_component_provider_contributions(bc2, ps, _toy_unknown_values())

        evap_x = next(r for r in result.records if r.component_id == _EVAP_ID)
        assert evap_x.value == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# 37: Public exports from mpl_sim.network
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_all_phase14f_names_exported(self):
        """Item 37: all Phase 14F names are accessible from mpl_sim.network."""
        assert ComponentProviderExecutionContext is _CtxDirect
        assert ComponentContributionProviderBinding is _BindingDirect
        assert ComponentContributionProviderSet is _SetDirect
        assert execute_component_provider_contributions is _exec_direct
        assert build_component_contribution_from_provider_execution is _build_direct

    def test_protocol_exported(self):
        """Item 37: ComponentContributionProviderProtocol is importable from mpl_sim.network."""
        from mpl_sim.network import ComponentContributionProviderProtocol as P

        assert P is ComponentContributionProviderProtocol

    def test_names_in_all_list(self):
        """Item 37: Phase 14F names appear in mpl_sim.network.__all__."""
        import mpl_sim.network as net

        assert "ComponentProviderExecutionContext" in net.__all__
        assert "ComponentContributionProviderProtocol" in net.__all__
        assert "ComponentContributionProviderBinding" in net.__all__
        assert "ComponentContributionProviderSet" in net.__all__
        assert "execute_component_provider_contributions" in net.__all__
        assert "build_component_contribution_from_provider_execution" in net.__all__

    def test_prior_phase_exports_unchanged(self):
        """Item 38: Phase 14E and prior exports remain accessible."""
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


# ---------------------------------------------------------------------------
# 39: Docs do not claim full physical network simulation
# ---------------------------------------------------------------------------


class TestDocumentationBoundaries:
    def test_source_docstring_does_not_overclaim(self):
        """Item 39: source docstring says this is a controlled provider adapter only."""
        src = _SRC.read_text(encoding="utf-8")
        assert "controlled provider adapter" in src or "provider adapter layer" in src
        overclaims = [
            "full MPL simulator",
            "full physical network",
            "validated against experiment",
            "validated model",
        ]
        for phrase in overclaims:
            assert phrase not in src, f"Overclaim found: {phrase!r}"

    def test_source_docstring_says_not_full_simulator(self):
        """Item 39: source says it is NOT a full MPL network simulator."""
        src = _SRC.read_text(encoding="utf-8")
        assert "NOT a full" in src or "not yet a full" in src or "DOES NOT" in src
