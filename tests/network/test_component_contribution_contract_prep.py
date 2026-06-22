"""Phase 14D component contribution contract adapter prep tests.

Coverage items (49 required):
 1.  valid ContributionRecord construction
 2.  record rejects wrong component ID type
 3.  record rejects empty name
 4.  record rejects whitespace-only name
 5.  record rejects non-string name
 6.  record rejects bool value
 7.  record rejects NaN value
 8.  record rejects infinity value
 9.  record rejects non-numeric value
10.  record accepts valid unit
11.  record rejects empty unit
12.  record rejects whitespace-only unit
13.  record rejects non-string unit
14.  valid ContributionRecordSet construction
15.  record set preserves deterministic order
16.  record set rejects wrong entry type
17.  record set rejects duplicate (component_id, name)
18.  valid ContributionResidualMap construction
19.  residual map rejects malformed key
20.  residual map rejects wrong component ID in key
21.  residual map rejects empty contribution-name key
22.  residual map rejects whitespace contribution-name key
23.  residual map rejects empty residual name
24.  residual map rejects whitespace residual name
25.  residual map is immutable/defensively copied
26.  valid record-to-component-contribution conversion
27.  conversion selects records for requested component only
28.  conversion preserves deterministic order
29.  conversion rejects wrong component ID type
30.  conversion rejects wrong record-set type
31.  conversion rejects wrong map type
32.  conversion rejects missing mapping
33.  conversion rejects undeclared residual when allowed residuals supplied
34.  conversion rejects duplicate output residual names
35.  output is Phase 14C ComponentContribution
36.  integration with Phase 14C adapter works using explicit pre-built records
37.  one-shot Phase 13G evaluation works with mapped contribution
38.  no real component execution
39.  no contribute( call
40.  no property lookup
41.  no registry resolution
42.  no CoolProp
43.  no SystemState assembly
44.  no FluidState attached to graph
45.  no physical values attached to NetworkGraph
46.  no automatic physics from component_type
47.  public exports work from mpl_sim.network
48.  existing Phase 13E/13F/13G/13H/14A/14B/14C tests still pass (suite-level gate)
49.  docs do not claim full physical network simulation
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
    build_network_residual_evaluators,
    build_physical_adapters_from_contributions,
    evaluate_network_residuals,
    map_contribution_records_to_component_contribution,
)
from mpl_sim.network.contribution_contract import (
    ContributionRecord as _ContractDirect,
)
from mpl_sim.network.contribution_contract import (
    ContributionRecordSet as _RecordSetDirect,
)
from mpl_sim.network.contribution_contract import (
    ContributionResidualMap as _ResidualMapDirect,
)
from mpl_sim.network.contribution_contract import (
    map_contribution_records_to_component_contribution as _map_direct,
)

# ---------------------------------------------------------------------------
# Source file path for boundary checks
# ---------------------------------------------------------------------------

_SRC = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "contribution_contract.py"
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


def _toy_record_set() -> ContributionRecordSet:
    return ContributionRecordSet(
        records=(
            ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
            ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=400.0),
            ContributionRecord(component_id=_COND_ID, name="mass_balance", value=0.0),
            ContributionRecord(component_id=_COND_ID, name="pressure_drop", value=0.0),
        )
    )


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
# 1–13: ContributionRecord
# ---------------------------------------------------------------------------


class TestContributionRecord:
    def test_valid_construction_no_unit(self):
        """Item 1: valid construction without unit."""
        r = ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0)
        assert r.component_id == _EVAP_ID
        assert r.name == "mass_balance"
        assert r.value == 0.0
        assert r.unit is None

    def test_valid_construction_with_unit(self):
        """Item 1 / 10: valid construction with unit."""
        r = ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=400.0, unit="Pa")
        assert r.unit == "Pa"

    def test_value_stored_as_float(self):
        """Item 1: integer value is normalised to float."""
        r = ContributionRecord(component_id=_EVAP_ID, name="x", value=5)
        assert isinstance(r.value, float)
        assert r.value == 5.0

    def test_rejects_wrong_component_id_type_string(self):
        """Item 2: string rejected as component_id."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ContributionRecord(component_id="evap", name="x", value=0.0)

    def test_rejects_wrong_component_id_type_none(self):
        """Item 2: None rejected as component_id."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ContributionRecord(component_id=None, name="x", value=0.0)

    def test_rejects_empty_name(self):
        """Item 3: empty name rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ContributionRecord(component_id=_EVAP_ID, name="", value=0.0)

    def test_rejects_whitespace_only_name(self):
        """Item 4: whitespace-only name rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ContributionRecord(component_id=_EVAP_ID, name="   ", value=0.0)

    def test_rejects_non_string_name_int(self):
        """Item 5: int rejected as name."""
        with pytest.raises(TypeError, match="str"):
            ContributionRecord(component_id=_EVAP_ID, name=42, value=0.0)

    def test_rejects_non_string_name_none(self):
        """Item 5: None rejected as name."""
        with pytest.raises(TypeError, match="str"):
            ContributionRecord(component_id=_EVAP_ID, name=None, value=0.0)

    def test_rejects_bool_value(self):
        """Item 6: bool value rejected."""
        with pytest.raises(TypeError, match="bool"):
            ContributionRecord(component_id=_EVAP_ID, name="x", value=True)

    def test_rejects_nan_value(self):
        """Item 7: NaN value rejected."""
        with pytest.raises(ValueError, match="finite"):
            ContributionRecord(component_id=_EVAP_ID, name="x", value=float("nan"))

    def test_rejects_positive_infinity(self):
        """Item 8: positive infinity rejected."""
        with pytest.raises(ValueError, match="finite"):
            ContributionRecord(component_id=_EVAP_ID, name="x", value=float("inf"))

    def test_rejects_negative_infinity(self):
        """Item 8: negative infinity rejected."""
        with pytest.raises(ValueError, match="finite"):
            ContributionRecord(component_id=_EVAP_ID, name="x", value=float("-inf"))

    def test_rejects_non_numeric_value_string(self):
        """Item 9: string value rejected."""
        with pytest.raises(TypeError, match="numeric"):
            ContributionRecord(component_id=_EVAP_ID, name="x", value="0.0")

    def test_rejects_non_numeric_value_none(self):
        """Item 9: None value rejected."""
        with pytest.raises(TypeError, match="numeric"):
            ContributionRecord(component_id=_EVAP_ID, name="x", value=None)

    def test_accepts_valid_unit(self):
        """Item 10: valid unit accepted."""
        r = ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0, unit="kg/s")
        assert r.unit == "kg/s"

    def test_rejects_empty_unit(self):
        """Item 11: empty unit rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0, unit="")

    def test_rejects_whitespace_unit(self):
        """Item 12: whitespace-only unit rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0, unit="  ")

    def test_rejects_non_string_unit_int(self):
        """Item 13: int rejected as unit."""
        with pytest.raises(TypeError, match="str"):
            ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0, unit=42)

    def test_rejects_non_string_unit_list(self):
        """Item 13: list rejected as unit."""
        with pytest.raises(TypeError, match="str"):
            ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0, unit=["Pa"])

    def test_frozen(self):
        """Item 1: record is frozen after construction."""
        from dataclasses import FrozenInstanceError

        r = ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0)
        with pytest.raises(FrozenInstanceError):
            r.value = 2.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 14–17: ContributionRecordSet
# ---------------------------------------------------------------------------


class TestContributionRecordSet:
    def test_valid_construction(self):
        """Item 14: valid construction from tuple."""
        r1 = ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0)
        r2 = ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=400.0)
        rs = ContributionRecordSet(records=(r1, r2))
        assert len(rs.records) == 2
        assert rs.records[0] is r1
        assert rs.records[1] is r2

    def test_accepts_list_input(self):
        """Item 14: list input is normalised to tuple."""
        r1 = ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0)
        rs = ContributionRecordSet(records=[r1])
        assert isinstance(rs.records, tuple)
        assert len(rs.records) == 1

    def test_source_list_mutation_does_not_change_record_set(self):
        """Item 16: source iterable mutation cannot change stored records."""
        r1 = ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0)
        source = [r1]
        rs = ContributionRecordSet(records=source)
        source.clear()
        assert rs.records == (r1,)

    def test_empty_record_set(self):
        """Item 14: empty set is valid."""
        rs = ContributionRecordSet(records=())
        assert rs.records == ()

    def test_preserves_deterministic_order(self):
        """Item 15: insertion order is preserved."""
        names = ["c", "a", "b", "z"]
        records = tuple(
            ContributionRecord(component_id=_EVAP_ID, name=n, value=float(i))
            for i, n in enumerate(names)
        )
        rs = ContributionRecordSet(records=records)
        assert [r.name for r in rs.records] == names

    def test_rejects_wrong_entry_type_string(self):
        """Item 16: string entry rejected."""
        with pytest.raises(TypeError, match="ContributionRecord"):
            ContributionRecordSet(records=("not_a_record",))

    def test_rejects_wrong_entry_type_none(self):
        """Item 16: None entry rejected."""
        r1 = ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0)
        with pytest.raises(TypeError, match="ContributionRecord"):
            ContributionRecordSet(records=(r1, None))

    def test_rejects_duplicate_component_id_name(self):
        """Item 17: duplicate (component_id, name) pair rejected."""
        r1 = ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0)
        r2 = ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=1.0)
        with pytest.raises(ValueError, match="duplicate"):
            ContributionRecordSet(records=(r1, r2))

    def test_same_name_different_components_allowed(self):
        """Item 17: same name for different components is valid."""
        r1 = ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0)
        r2 = ContributionRecord(component_id=_COND_ID, name="mass_balance", value=0.0)
        rs = ContributionRecordSet(records=(r1, r2))
        assert len(rs.records) == 2

    def test_frozen(self):
        """Item 14: record-set fields cannot be reassigned."""
        from dataclasses import FrozenInstanceError

        rs = ContributionRecordSet(records=())
        with pytest.raises(FrozenInstanceError):
            rs.records = ()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 18–25: ContributionResidualMap
# ---------------------------------------------------------------------------


class TestContributionResidualMap:
    def test_valid_construction(self):
        """Item 18: valid construction from dict."""
        crm = ContributionResidualMap(
            mapping={
                (_EVAP_ID, "mass_balance"): "mass_balance:n1",
                (_EVAP_ID, "pressure_drop"): "pressure_drop:evap",
            }
        )
        assert len(crm.mapping) == 2

    def test_empty_mapping(self):
        """Item 18: empty mapping is valid."""
        crm = ContributionResidualMap(mapping={})
        assert len(crm.mapping) == 0

    def test_lookup_by_key(self):
        """Item 18: stored values are retrievable."""
        crm = ContributionResidualMap(mapping={(_EVAP_ID, "mass_balance"): "mass_balance:n1"})
        assert crm.mapping[(_EVAP_ID, "mass_balance")] == "mass_balance:n1"

    def test_rejects_malformed_key_string(self):
        """Item 19: string key rejected (not a 2-tuple)."""
        with pytest.raises(TypeError, match="2-tuples"):
            ContributionResidualMap(mapping={"not_a_tuple": "residual"})

    def test_rejects_malformed_key_three_tuple(self):
        """Item 19: 3-tuple key rejected."""
        with pytest.raises(TypeError, match="2-tuples"):
            ContributionResidualMap(mapping={(_EVAP_ID, "x", "extra"): "residual"})

    def test_rejects_malformed_key_one_tuple(self):
        """Item 19: 1-tuple key rejected."""
        with pytest.raises(TypeError, match="2-tuples"):
            ContributionResidualMap(mapping={(_EVAP_ID,): "residual"})

    def test_rejects_wrong_component_id_in_key_string(self):
        """Item 20: string in key[0] position rejected."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ContributionResidualMap(mapping={("evap", "mass_balance"): "residual"})

    def test_rejects_wrong_component_id_in_key_none(self):
        """Item 20: None in key[0] position rejected."""
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            ContributionResidualMap(mapping={(None, "mass_balance"): "residual"})

    def test_rejects_empty_contribution_name_key(self):
        """Item 21: empty contribution-name key rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ContributionResidualMap(mapping={(_EVAP_ID, ""): "residual"})

    def test_rejects_whitespace_contribution_name_key(self):
        """Item 22: whitespace-only contribution-name key rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ContributionResidualMap(mapping={(_EVAP_ID, "  "): "residual"})

    def test_rejects_empty_residual_name(self):
        """Item 23: empty residual name value rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ContributionResidualMap(mapping={(_EVAP_ID, "x"): ""})

    def test_rejects_whitespace_residual_name(self):
        """Item 24: whitespace-only residual name rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            ContributionResidualMap(mapping={(_EVAP_ID, "x"): "   "})

    def test_defensively_copied(self):
        """Item 25: post-construction mutation of source dict does not affect mapping."""
        source = {(_EVAP_ID, "mass_balance"): "mass_balance:n1"}
        crm = ContributionResidualMap(mapping=source)
        source[(_EVAP_ID, "new_key")] = "new_residual"
        assert (_EVAP_ID, "new_key") not in crm.mapping

    def test_mapping_is_immutable_proxy(self):
        """Item 25: stored mapping is a MappingProxyType."""
        from types import MappingProxyType

        crm = ContributionResidualMap(mapping={(_EVAP_ID, "x"): "r"})
        assert isinstance(crm.mapping, MappingProxyType)

    def test_frozen(self):
        """Item 25: residual-map fields cannot be reassigned."""
        from dataclasses import FrozenInstanceError

        crm = ContributionResidualMap(mapping={})
        with pytest.raises(FrozenInstanceError):
            crm.mapping = {}  # type: ignore[misc]

    def test_rejects_non_string_contribution_name_in_key(self):
        """Item 19/20: non-string contribution name (int) in key rejected."""
        with pytest.raises(TypeError):
            ContributionResidualMap(mapping={(_EVAP_ID, 42): "residual"})


# ---------------------------------------------------------------------------
# 26–35: map_contribution_records_to_component_contribution
# ---------------------------------------------------------------------------


class TestMapContributionRecords:
    def test_valid_conversion(self):
        """Item 26: valid conversion returns expected ComponentContribution."""
        rs = ContributionRecordSet(
            records=(
                ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
                ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=400.0),
            )
        )
        crm = ContributionResidualMap(
            mapping={
                (_EVAP_ID, "mass_balance"): "mass_balance:n1",
                (_EVAP_ID, "pressure_drop"): "pressure_drop:evap",
            }
        )
        result = map_contribution_records_to_component_contribution(_EVAP_ID, rs, crm)
        assert result.residual_values["mass_balance:n1"] == 0.0
        assert result.residual_values["pressure_drop:evap"] == 400.0

    def test_selects_only_requested_component(self):
        """Item 27: records for other components are ignored."""
        rs = _toy_record_set()
        crm = _toy_residual_map()
        result = map_contribution_records_to_component_contribution(_EVAP_ID, rs, crm)
        assert set(result.residual_values.keys()) == {"mass_balance:n1", "pressure_drop:evap"}

    def test_preserves_deterministic_order(self):
        """Item 28: output keys follow record_set insertion order."""
        rs = ContributionRecordSet(
            records=(
                ContributionRecord(component_id=_EVAP_ID, name="pressure_drop", value=400.0),
                ContributionRecord(component_id=_EVAP_ID, name="mass_balance", value=0.0),
            )
        )
        crm = ContributionResidualMap(
            mapping={
                (_EVAP_ID, "pressure_drop"): "pressure_drop:evap",
                (_EVAP_ID, "mass_balance"): "mass_balance:n1",
            }
        )
        result = map_contribution_records_to_component_contribution(_EVAP_ID, rs, crm)
        keys = list(result.residual_values.keys())
        assert keys == ["pressure_drop:evap", "mass_balance:n1"]

    def test_rejects_wrong_component_id_type(self):
        """Item 29: string rejected as component_id."""
        rs = ContributionRecordSet(records=())
        crm = ContributionResidualMap(mapping={})
        with pytest.raises(TypeError, match="ComponentInstanceId"):
            map_contribution_records_to_component_contribution("evap", rs, crm)

    def test_rejects_wrong_record_set_type(self):
        """Item 30: list rejected as record_set."""
        crm = ContributionResidualMap(mapping={})
        with pytest.raises(TypeError, match="ContributionRecordSet"):
            map_contribution_records_to_component_contribution(_EVAP_ID, [], crm)

    def test_rejects_wrong_map_type(self):
        """Item 31: plain dict rejected as residual_map."""
        rs = ContributionRecordSet(records=())
        with pytest.raises(TypeError, match="ContributionResidualMap"):
            map_contribution_records_to_component_contribution(_EVAP_ID, rs, {})

    def test_rejects_missing_mapping(self):
        """Item 32: record with no mapping entry raises ValueError."""
        rs = ContributionRecordSet(
            records=(ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0),)
        )
        crm = ContributionResidualMap(mapping={})
        with pytest.raises(ValueError, match="no residual mapping"):
            map_contribution_records_to_component_contribution(_EVAP_ID, rs, crm)

    def test_rejects_undeclared_residual_when_allowed_supplied(self):
        """Item 33: residual name not in allowed_residual_names raises ValueError."""
        rs = ContributionRecordSet(
            records=(ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0),)
        )
        crm = ContributionResidualMap(mapping={(_EVAP_ID, "x"): "some_residual:n1"})
        with pytest.raises(ValueError, match="allowed_residual_names"):
            map_contribution_records_to_component_contribution(
                _EVAP_ID,
                rs,
                crm,
                allowed_residual_names={"declared_residual:n1"},
            )

    def test_rejects_duplicate_output_residual_names(self):
        """Item 34: two records mapping to the same residual name raises ValueError."""
        rs = ContributionRecordSet(
            records=(
                ContributionRecord(component_id=_EVAP_ID, name="a", value=1.0),
                ContributionRecord(component_id=_EVAP_ID, name="b", value=2.0),
            )
        )
        crm = ContributionResidualMap(
            mapping={
                (_EVAP_ID, "a"): "same_residual:n1",
                (_EVAP_ID, "b"): "same_residual:n1",
            }
        )
        with pytest.raises(ValueError, match="duplicate output residual"):
            map_contribution_records_to_component_contribution(_EVAP_ID, rs, crm)

    def test_output_is_component_contribution(self):
        """Item 35: return value is a Phase 14C ComponentContribution."""
        rs = ContributionRecordSet(
            records=(ContributionRecord(component_id=_EVAP_ID, name="x", value=1.0),)
        )
        crm = ContributionResidualMap(mapping={(_EVAP_ID, "x"): "residual:n1"})
        result = map_contribution_records_to_component_contribution(_EVAP_ID, rs, crm)
        assert isinstance(result, ComponentContribution)

    def test_allowed_residual_names_passes_when_declared(self):
        """Item 33 (positive): declared residual in allowed set is accepted."""
        rs = ContributionRecordSet(
            records=(ContributionRecord(component_id=_EVAP_ID, name="x", value=5.0),)
        )
        crm = ContributionResidualMap(mapping={(_EVAP_ID, "x"): "r:n1"})
        result = map_contribution_records_to_component_contribution(
            _EVAP_ID, rs, crm, allowed_residual_names={"r:n1"}
        )
        assert result.residual_values["r:n1"] == 5.0

    @pytest.mark.parametrize("allowed", ["r:n1", ["r:n1"], ("r:n1",)])
    def test_rejects_wrong_allowed_residual_names_container(self, allowed):
        """Allowed residual declarations require an explicit set or frozenset."""
        rs = ContributionRecordSet(
            records=(ContributionRecord(component_id=_EVAP_ID, name="x", value=5.0),)
        )
        crm = ContributionResidualMap(mapping={(_EVAP_ID, "x"): "r:n1"})
        with pytest.raises(TypeError, match="set or frozenset"):
            map_contribution_records_to_component_contribution(
                _EVAP_ID, rs, crm, allowed_residual_names=allowed
            )

    def test_rejects_non_string_allowed_residual_name(self):
        """Every allowed residual declaration must be a string."""
        rs = ContributionRecordSet(records=())
        crm = ContributionResidualMap(mapping={})
        with pytest.raises(TypeError, match="entry must be a str"):
            map_contribution_records_to_component_contribution(
                _EVAP_ID, rs, crm, allowed_residual_names={"r:n1", 42}
            )

    @pytest.mark.parametrize("name", ["", "   "])
    def test_rejects_empty_or_whitespace_allowed_residual_name(self, name):
        """Allowed residual declarations must be non-empty and non-whitespace."""
        rs = ContributionRecordSet(records=())
        crm = ContributionResidualMap(mapping={})
        with pytest.raises(ValueError, match="non-empty"):
            map_contribution_records_to_component_contribution(
                _EVAP_ID, rs, crm, allowed_residual_names={name}
            )

    def test_allowed_residual_names_source_is_not_mutated(self):
        """Conversion does not mutate the caller's allowed-name set."""
        rs = ContributionRecordSet(
            records=(ContributionRecord(component_id=_EVAP_ID, name="x", value=5.0),)
        )
        crm = ContributionResidualMap(mapping={(_EVAP_ID, "x"): "r:n1"})
        allowed = {"r:n1"}
        before = allowed.copy()
        map_contribution_records_to_component_contribution(
            _EVAP_ID, rs, crm, allowed_residual_names=allowed
        )
        assert allowed == before

    def test_empty_component_returns_empty_contribution(self):
        """Item 27: no records for a component returns empty ComponentContribution."""
        rs = ContributionRecordSet(
            records=(ContributionRecord(component_id=_COND_ID, name="x", value=1.0),)
        )
        crm = ContributionResidualMap(mapping={(_COND_ID, "x"): "r:n1"})
        result = map_contribution_records_to_component_contribution(_EVAP_ID, rs, crm)
        assert result.residual_values == {}


# ---------------------------------------------------------------------------
# 36: Integration with Phase 14C adapter using explicit pre-built records
# ---------------------------------------------------------------------------


class TestPhase14CIntegration:
    def test_integration_with_phase_14c_adapter(self):
        """Item 36: map_contribution_records_to_component_contribution inside
        a ComponentContributionAdapter callback, verified through
        build_physical_adapters_from_contributions."""
        record_set = _toy_record_set()
        residual_map = _toy_residual_map()
        binding_ctx = _toy_binding_context()

        def evap_cb(ctx: ComponentContributionContext) -> ComponentContribution:
            return map_contribution_records_to_component_contribution(
                ComponentInstanceId("evap"), record_set, residual_map
            )

        def cond_cb(ctx: ComponentContributionContext) -> ComponentContribution:
            return map_contribution_records_to_component_contribution(
                ComponentInstanceId("cond"), record_set, residual_map
            )

        adapter_set = ComponentContributionAdapterSet(
            adapters=(
                ComponentContributionAdapter(
                    instance_id=ComponentInstanceId("evap"), callback=evap_cb
                ),
                ComponentContributionAdapter(
                    instance_id=ComponentInstanceId("cond"), callback=cond_cb
                ),
            )
        )

        physical_adapter_set = build_physical_adapters_from_contributions(binding_ctx, adapter_set)
        assembly = binding_ctx.assembly
        evaluators = build_network_residual_evaluators(assembly, physical_adapter_set)

        unknown_values = NetworkUnknownValues(
            values={
                "mdot:evap": 0.05,
                "mdot:cond": 0.05,
                "P:n1": 100_000.0,
                "P:n2": 99_000.0,
            }
        )
        scales = {
            "mass_balance:n1": 0.01,
            "mass_balance:n2": 0.01,
            "pressure_drop:evap": 100.0,
            "pressure_drop:cond": 100.0,
        }
        result = evaluate_network_residuals(
            assembly=assembly,
            unknown_values=unknown_values,
            evaluators=evaluators,
            scales=scales,
        )
        rv = {e.spec.name: e.value for e in result.residual_vector.evaluations}
        assert rv["mass_balance:n1"] == pytest.approx(0.0)
        assert rv["pressure_drop:evap"] == pytest.approx(400.0)
        assert rv["mass_balance:n2"] == pytest.approx(0.0)
        assert rv["pressure_drop:cond"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 37: One-shot Phase 13G evaluation with mapped contribution
# ---------------------------------------------------------------------------


class TestPhase13GEvaluation:
    def test_one_shot_evaluation_with_mapped_contribution(self):
        """Item 37: full pipeline — Phase 14D records → 14C adapters → 14A adapters
        → 13G evaluation — returns expected toy residual values."""
        evap_id = ComponentInstanceId("evap")
        cond_id = ComponentInstanceId("cond")

        evap_records = ContributionRecordSet(
            records=(
                ContributionRecord(component_id=evap_id, name="mass_balance", value=0.0),
                ContributionRecord(component_id=evap_id, name="pressure_drop", value=400.0),
            )
        )
        cond_records = ContributionRecordSet(
            records=(
                ContributionRecord(component_id=cond_id, name="mass_balance", value=0.0),
                ContributionRecord(component_id=cond_id, name="pressure_drop", value=0.0),
            )
        )
        residual_map_evap = ContributionResidualMap(
            mapping={
                (evap_id, "mass_balance"): "mass_balance:n1",
                (evap_id, "pressure_drop"): "pressure_drop:evap",
            }
        )
        residual_map_cond = ContributionResidualMap(
            mapping={
                (cond_id, "mass_balance"): "mass_balance:n2",
                (cond_id, "pressure_drop"): "pressure_drop:cond",
            }
        )

        binding_ctx = _toy_binding_context()

        def evap_cb(ctx: ComponentContributionContext) -> ComponentContribution:
            return map_contribution_records_to_component_contribution(
                evap_id, evap_records, residual_map_evap
            )

        def cond_cb(ctx: ComponentContributionContext) -> ComponentContribution:
            return map_contribution_records_to_component_contribution(
                cond_id, cond_records, residual_map_cond
            )

        adapter_set = ComponentContributionAdapterSet(
            adapters=(
                ComponentContributionAdapter(instance_id=evap_id, callback=evap_cb),
                ComponentContributionAdapter(instance_id=cond_id, callback=cond_cb),
            )
        )
        physical_adapter_set = build_physical_adapters_from_contributions(binding_ctx, adapter_set)
        assembly = binding_ctx.assembly
        evaluators = build_network_residual_evaluators(assembly, physical_adapter_set)
        unknown_values = NetworkUnknownValues(
            values={
                "mdot:evap": 0.05,
                "mdot:cond": 0.05,
                "P:n1": 100_000.0,
                "P:n2": 99_000.0,
            }
        )
        scales = {
            "mass_balance:n1": 0.01,
            "mass_balance:n2": 0.01,
            "pressure_drop:evap": 100.0,
            "pressure_drop:cond": 100.0,
        }
        result = evaluate_network_residuals(
            assembly=assembly,
            unknown_values=unknown_values,
            evaluators=evaluators,
            scales=scales,
        )
        rv = {e.spec.name: e.value for e in result.residual_vector.evaluations}
        assert rv["mass_balance:n1"] == pytest.approx(0.0)
        assert rv["pressure_drop:evap"] == pytest.approx(400.0)
        assert rv["mass_balance:n2"] == pytest.approx(0.0)
        assert rv["pressure_drop:cond"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 38-46: Architecture boundary checks (AST-based source inspection)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def src_text() -> str:
    return _SRC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def src_tree(src_text) -> ast.Module:
    return ast.parse(src_text)


def _source_without_docstrings(src: str) -> str:
    """Return source text with all module/class/function docstrings removed."""
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


def _imported_modules(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


class TestArchitectureBoundaries:
    def test_no_real_component_execution(self, src_tree):
        """Item 38: source does not import mpl_sim.components."""
        for mod in _imported_modules(src_tree):
            assert "components" not in mod

    def test_no_contribute_call_in_source(self, src_text, src_tree):
        """Item 39: 'contribute' does not appear in non-docstring code."""
        code = _source_without_docstrings(src_text)
        func_names = [
            node.name
            for node in ast.walk(src_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "contribute" not in func_names
        assert "contribute" not in code

    def test_no_property_lookup(self, src_tree):
        """Item 40: source does not import mpl_sim.properties or PropertyBackend."""
        for mod in _imported_modules(src_tree):
            assert "properties" not in mod

    def test_no_registry_resolution(self, src_tree):
        """Item 41: source does not import CorrelationRegistry or HX registry."""
        for mod in _imported_modules(src_tree):
            assert "correlations" not in mod
            assert "registry" not in mod.lower()

    def test_no_coolprop(self, src_text, src_tree):
        """Item 42: CoolProp does not appear as a live import or in non-docstring code."""
        for mod in _imported_modules(src_tree):
            assert "CoolProp" not in mod
        code = _source_without_docstrings(src_text)
        assert "CoolProp" not in code

    def test_no_system_state_assembly(self, src_text, src_tree):
        """Item 43: SystemState does not appear as an import or in non-docstring code."""
        for mod in _imported_modules(src_tree):
            assert "SystemState" not in mod
            assert "solvers" not in mod
        code = _source_without_docstrings(src_text)
        assert "SystemState" not in code

    def test_no_fluid_state_attached_to_graph(self, src_text, src_tree):
        """Item 44: FluidState is not imported or in non-docstring code."""
        for mod in _imported_modules(src_tree):
            assert "FluidState" not in mod
        code = _source_without_docstrings(src_text)
        assert "FluidState" not in code

    def test_no_physical_values_attached_to_network_graph(self, src_text):
        """Item 45: P_out, h_out not in source."""
        for forbidden in ("P_out", "h_out"):
            assert forbidden not in src_text

    def test_no_automatic_physics_from_component_type(self, src_text, src_tree):
        """Item 46: component_type is not accessed in non-docstring code."""
        code = _source_without_docstrings(src_text)
        attr_names = [node.attr for node in ast.walk(src_tree) if isinstance(node, ast.Attribute)]
        assert "component_type" not in attr_names
        assert "component_type" not in code

    def test_no_scipy_in_source(self, src_tree):
        """Boundary: scipy not imported."""
        for mod in _imported_modules(src_tree):
            assert "scipy" not in mod

    def test_no_hx_models_in_source(self, src_tree):
        """Boundary: hx_models not imported."""
        for mod in _imported_modules(src_tree):
            assert "hx_models" not in mod

    def test_no_calibration_in_source(self, src_tree):
        """Boundary: calibration not imported."""
        for mod in _imported_modules(src_tree):
            assert "calibration" not in mod


# ---------------------------------------------------------------------------
# 47: Public exports from mpl_sim.network
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_contribution_record_exported(self):
        """Item 47: ContributionRecord is in mpl_sim.network."""
        from mpl_sim import network

        assert hasattr(network, "ContributionRecord")
        assert network.ContributionRecord is ContributionRecord

    def test_contribution_record_set_exported(self):
        """Item 47: ContributionRecordSet is in mpl_sim.network."""
        from mpl_sim import network

        assert hasattr(network, "ContributionRecordSet")
        assert network.ContributionRecordSet is ContributionRecordSet

    def test_contribution_residual_map_exported(self):
        """Item 47: ContributionResidualMap is in mpl_sim.network."""
        from mpl_sim import network

        assert hasattr(network, "ContributionResidualMap")
        assert network.ContributionResidualMap is ContributionResidualMap

    def test_map_function_exported(self):
        """Item 47: map_contribution_records_to_component_contribution is in mpl_sim.network."""
        from mpl_sim import network

        assert hasattr(network, "map_contribution_records_to_component_contribution")
        assert (
            network.map_contribution_records_to_component_contribution
            is map_contribution_records_to_component_contribution
        )

    def test_all_four_in___all__(self):
        """Item 47: all four Phase 14D names are in __all__."""
        import mpl_sim.network as net

        assert "ContributionRecord" in net.__all__
        assert "ContributionRecordSet" in net.__all__
        assert "ContributionResidualMap" in net.__all__
        assert "map_contribution_records_to_component_contribution" in net.__all__

    def test_direct_module_imports_match_package_imports(self):
        """Item 47: direct module imports are the same objects as package imports."""
        assert _ContractDirect is ContributionRecord
        assert _RecordSetDirect is ContributionRecordSet
        assert _ResidualMapDirect is ContributionResidualMap
        assert _map_direct is map_contribution_records_to_component_contribution

    def test_prior_phase_exports_unchanged(self):
        """Item 47/48: all prior-phase exports remain available."""
        import mpl_sim.network as net

        phase_13e = [
            "GraphNodeId",
            "ComponentInstanceId",
            "GraphNode",
            "ComponentInstance",
            "NetworkGraph",
        ]
        phase_14c = [
            "ComponentContributionContext",
            "ComponentContribution",
            "ComponentContributionAdapter",
            "ComponentContributionAdapterSet",
            "build_physical_adapters_from_contributions",
        ]
        for name in phase_13e + phase_14c:
            assert hasattr(net, name), f"missing export: {name}"


# ---------------------------------------------------------------------------
# 48: Existing prior-phase network tests gate (suite-level)
# ---------------------------------------------------------------------------


class TestPriorPhaseRegression:
    def test_graph_foundation_imports(self):
        """Item 48: Phase 13E types import correctly."""
        from mpl_sim.network import GraphNode, GraphNodeId, NetworkGraph

        g = NetworkGraph(nodes=[GraphNode(node_id=GraphNodeId("n1"))], instances=[])
        assert g is not None

    def test_residual_assembly_imports(self):
        """Item 48: Phase 13F types import and assemble correctly."""
        from mpl_sim.network import assemble_network_residuals

        g = _toy_graph()
        asm = assemble_network_residuals(g)
        assert len(list(asm.residuals.residuals)) == 4

    def test_contribution_adapter_imports(self):
        """Item 48: Phase 14C types import correctly."""
        from mpl_sim.network import (
            ComponentContribution,
            ComponentContributionAdapter,
            ComponentContributionAdapterSet,
            ComponentContributionContext,
            build_physical_adapters_from_contributions,
        )

        assert ComponentContribution is not None
        assert ComponentContributionAdapter is not None
        assert ComponentContributionAdapterSet is not None
        assert ComponentContributionContext is not None
        assert build_physical_adapters_from_contributions is not None


# ---------------------------------------------------------------------------
# 49: Docs do not claim full physical network simulation
# ---------------------------------------------------------------------------


class TestDocumentationBoundary:
    def test_concepts_doc_does_not_claim_physical_simulation(self):
        """Item 49: CONCEPTS.md Phase 14D section does not claim full simulation."""
        concepts_path = (
            pathlib.Path(__file__).parent.parent.parent / "docs" / "user_guide" / "CONCEPTS.md"
        )
        text = concepts_path.read_text(encoding="utf-8")
        assert "Phase 14D" in text, "CONCEPTS.md should document Phase 14D"
        # Check that the Phase 14D section contains the required negative boundaries.
        assert "Does NOT execute real component classes" in text
        assert "Does NOT call" in text
        assert "Is NOT a full MPL network simulator" in text
        # Ensure no line makes a bare positive claim about executing components
        # or providing a full simulator without a preceding "NOT" qualifier.
        for line in text.splitlines():
            line_stripped = line.strip()
            if "executes real components" in line_stripped:
                assert (
                    "NOT" in line_stripped or "not" in line_stripped
                ), f"Docs line makes positive claim: {line_stripped!r}"
            if "calls Component.contribute" in line_stripped:
                assert (
                    "NOT" in line_stripped or "not" in line_stripped
                ), f"Docs line makes positive claim: {line_stripped!r}"

    def test_contribution_contract_source_does_not_claim_full_simulation(self, src_text):
        """Item 49: contribution_contract.py does not claim full simulation."""
        forbidden = [
            "validated against experiment",
            "full physical network simulator",
            "validated model",
        ]
        for phrase in forbidden:
            assert phrase not in src_text
