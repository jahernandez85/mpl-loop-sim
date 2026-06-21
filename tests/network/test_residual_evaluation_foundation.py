"""Phase 13G network residual evaluation foundation tests.

Coverage items (34 required):
 1.  valid unknown value map from assembly declarations
 2.  missing unknown value rejected
 3.  extra unknown value rejected
 4.  non-finite unknown value rejected (nan; inf)
 5.  bool unknown value rejected
 6.  valid residual evaluator/callback mapping
 7.  missing evaluator rejected
 8.  extra evaluator rejected
 9.  duplicate evaluator names rejected (list input)
10.  callback non-callable rejected
11.  callback returning nan rejected
12.  callback returning inf rejected
13.  callback returning bool rejected
14.  callback exceptions propagate
15.  missing scale rejected
16.  extra scale rejected
17.  invalid scale rejected (zero; negative; nan; inf; bool)
18.  evaluation preserves residual declaration order
19.  raw residual values equal callback outputs
20.  residual units match declarations
21.  scales match explicit scale map
22.  returned ResidualVector is correct
23.  max_abs_scaled correct
24.  l2_scaled correct
25.  evaluation does not mutate inputs
26.  no solve method exists
27.  no iterative solver or optimization imported
28.  no component execution
29.  no property lookup
30.  no registry resolution
31.  no graph physical-state attachment
32.  public exports work from mpl_sim.network
33.  existing Phase 13E/13F tests still pass (ensured by full suite)
34.  docs do not claim network solving for Phase 13G
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from mpl_sim.closed_loop.residuals import ResidualEvaluation, ResidualVector
from mpl_sim.network import (
    ComponentInstance,
    ComponentInstanceId,
    GraphNode,
    GraphNodeId,
    NetworkGraph,
    NetworkResidualEvaluationResult,
    NetworkResidualEvaluator,
    NetworkUnknownValues,
    assemble_network_residuals,
    evaluate_network_residuals,
)
from mpl_sim.network.residual_evaluation import (
    NetworkResidualEvaluationResult as _ResultDirect,
)
from mpl_sim.network.residual_evaluation import (
    NetworkResidualEvaluator as _EvaluatorDirect,
)
from mpl_sim.network.residual_evaluation import (
    NetworkUnknownValues as _ValuesDirect,
)
from mpl_sim.network.residual_evaluation import (
    evaluate_network_residuals as _eval_direct,
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
    """Two nodes, two components forming a closed loop."""
    return NetworkGraph(
        nodes=[_node("n1"), _node("n2")],
        instances=[
            _inst("evap", "evaporator", "n1", "n2"),
            _inst("cond", "condenser", "n2", "n1"),
        ],
    )


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
def unknown_values():
    return NetworkUnknownValues(
        values={
            "mdot:evap": 0.05,
            "mdot:cond": 0.05,
            "P:n1": 100_000.0,
            "P:n2": 99_000.0,
        }
    )


@pytest.fixture
def evaluators():
    return [
        NetworkResidualEvaluator(
            name="mass_balance:n1",
            callback=lambda v: v["mdot:evap"] - v["mdot:cond"],
        ),
        NetworkResidualEvaluator(
            name="mass_balance:n2",
            callback=lambda v: v["mdot:cond"] - v["mdot:evap"],
        ),
        NetworkResidualEvaluator(
            name="pressure_drop:evap",
            callback=lambda v: v["P:n1"] - v["P:n2"] - 600.0,
        ),
        NetworkResidualEvaluator(
            name="pressure_drop:cond",
            callback=lambda v: v["P:n2"] - v["P:n1"] + 1000.0,
        ),
    ]


@pytest.fixture
def scales():
    return {
        "mass_balance:n1": 0.01,
        "mass_balance:n2": 0.01,
        "pressure_drop:evap": 100.0,
        "pressure_drop:cond": 100.0,
    }


@pytest.fixture
def result(assembly, unknown_values, evaluators, scales):
    return evaluate_network_residuals(assembly, unknown_values, evaluators, scales)


# ---------------------------------------------------------------------------
# 1–5: Unknown value map validation
# ---------------------------------------------------------------------------


class TestNetworkUnknownValues:
    def test_valid_values_construction(self):
        """Item 1 (partial): NetworkUnknownValues accepts finite floats."""
        uv = NetworkUnknownValues(values={"mdot:evap": 0.05, "P:n1": 100_000.0})
        assert uv.values["mdot:evap"] == 0.05
        assert uv.values["P:n1"] == 100_000.0

    def test_values_stored_as_mapping_proxy(self):
        """Values are stored as an immutable MappingProxyType."""
        from types import MappingProxyType

        uv = NetworkUnknownValues(values={"a": 1.0})
        assert isinstance(uv.values, MappingProxyType)

    def test_dict_input_converted_to_proxy(self):
        """Plain dict input is converted to immutable MappingProxyType."""
        from types import MappingProxyType

        source = {"x": 3.14}
        uv = NetworkUnknownValues(values=source)
        assert isinstance(uv.values, MappingProxyType)

    def test_mapping_proxy_input_is_defensively_copied(self):
        """A proxy over mutable input cannot mutate stored unknown values."""
        from types import MappingProxyType

        source = {"x": 3.14}
        uv = NetworkUnknownValues(values=MappingProxyType(source))
        source["x"] = 99.0
        source["y"] = 1.0
        assert dict(uv.values) == {"x": 3.14}

    def test_proxy_is_immutable(self):
        """MappingProxyType raises TypeError on assignment."""
        uv = NetworkUnknownValues(values={"a": 1.0})
        with pytest.raises(TypeError):
            uv.values["a"] = 99.0  # type: ignore[index]

    def test_accepts_int_value(self):
        """Integer values are accepted (finite non-bool numeric)."""
        uv = NetworkUnknownValues(values={"P": 100_000})
        assert uv.values["P"] == 100_000

    def test_nan_value_rejected(self):
        """Item 4a: NaN unknown value rejected."""
        with pytest.raises(ValueError, match="finite"):
            NetworkUnknownValues(values={"mdot": float("nan")})

    def test_pos_inf_value_rejected(self):
        """Item 4b: +inf unknown value rejected."""
        with pytest.raises(ValueError, match="finite"):
            NetworkUnknownValues(values={"P": float("inf")})

    def test_neg_inf_value_rejected(self):
        """Item 4b: -inf unknown value rejected."""
        with pytest.raises(ValueError, match="finite"):
            NetworkUnknownValues(values={"P": float("-inf")})

    def test_bool_true_value_rejected(self):
        """Item 5: True rejected even though bool is a subclass of int."""
        with pytest.raises(ValueError, match="bool"):
            NetworkUnknownValues(values={"mdot": True})

    def test_bool_false_value_rejected(self):
        """Item 5: False rejected."""
        with pytest.raises(ValueError, match="bool"):
            NetworkUnknownValues(values={"P": False})

    def test_non_numeric_value_rejected(self):
        """Non-numeric values are rejected."""
        with pytest.raises(TypeError):
            NetworkUnknownValues(values={"mdot": "0.05"})  # type: ignore[dict-item]

    def test_empty_key_rejected(self):
        """Empty-string key is rejected."""
        with pytest.raises(ValueError):
            NetworkUnknownValues(values={"": 1.0})

    def test_whitespace_key_rejected(self):
        """Whitespace-only key is rejected."""
        with pytest.raises(ValueError):
            NetworkUnknownValues(values={"   ": 1.0})

    def test_empty_mapping_accepted(self):
        """Empty mapping is valid at construction (no entries to validate)."""
        uv = NetworkUnknownValues(values={})
        assert len(uv.values) == 0


class TestUnknownValuesAgainstAssembly:
    def test_valid_values_match_assembly(self, assembly, unknown_values):
        """Item 1: full round-trip with matching unknown values passes."""
        assert set(unknown_values.values.keys()) == set(assembly.unknowns.names())

    def test_missing_unknown_value_rejected(self, assembly, evaluators, scales):
        """Item 2: missing unknown value is rejected by evaluate_network_residuals."""
        partial = NetworkUnknownValues(values={"mdot:evap": 0.05, "mdot:cond": 0.05})
        with pytest.raises(ValueError, match="missing"):
            evaluate_network_residuals(assembly, partial, evaluators, scales)

    def test_extra_unknown_value_rejected(self, assembly, evaluators, scales):
        """Item 3: extra unknown name not in declarations is rejected."""
        extra = NetworkUnknownValues(
            values={
                "mdot:evap": 0.05,
                "mdot:cond": 0.05,
                "P:n1": 100_000.0,
                "P:n2": 99_000.0,
                "EXTRA:unknown": 999.0,
            }
        )
        with pytest.raises(ValueError, match="EXTRA:unknown"):
            evaluate_network_residuals(assembly, extra, evaluators, scales)


# ---------------------------------------------------------------------------
# 6–14: Evaluator validation
# ---------------------------------------------------------------------------


class TestNetworkResidualEvaluator:
    def test_valid_evaluator_construction(self):
        """Item 6 (partial): valid name + callable is accepted."""
        ev = NetworkResidualEvaluator(name="mass_balance:n1", callback=lambda v: 0.0)
        assert ev.name == "mass_balance:n1"
        assert callable(ev.callback)

    def test_evaluator_is_frozen(self):
        """NetworkResidualEvaluator is frozen (immutable)."""
        ev = NetworkResidualEvaluator(name="r1", callback=lambda v: 0.0)
        with pytest.raises((AttributeError, TypeError)):
            ev.name = "other"  # type: ignore[misc]

    def test_empty_name_rejected(self):
        """Item 10 (partial): empty evaluator name rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            NetworkResidualEvaluator(name="", callback=lambda v: 0.0)

    def test_whitespace_name_rejected(self):
        """Whitespace-only name rejected."""
        with pytest.raises(ValueError, match="non-empty"):
            NetworkResidualEvaluator(name="   ", callback=lambda v: 0.0)

    def test_non_callable_rejected(self):
        """Item 10: non-callable callback rejected at construction."""
        with pytest.raises(TypeError, match="callable"):
            NetworkResidualEvaluator(name="r1", callback="not_a_function")  # type: ignore[arg-type]

    def test_none_callback_rejected(self):
        """None is not callable — rejected at construction."""
        with pytest.raises(TypeError, match="callable"):
            NetworkResidualEvaluator(name="r1", callback=None)  # type: ignore[arg-type]


class TestEvaluatorAgainstAssembly:
    def test_valid_evaluators_accepted(self, assembly, unknown_values, evaluators, scales):
        """Item 6: all evaluators matching assembly residuals are accepted."""
        result = evaluate_network_residuals(assembly, unknown_values, evaluators, scales)
        assert isinstance(result, NetworkResidualEvaluationResult)

    def test_missing_evaluator_rejected(self, assembly, unknown_values, scales):
        """Item 7: missing evaluator for a declared residual is rejected."""
        partial = [
            NetworkResidualEvaluator(name="mass_balance:n1", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="mass_balance:n2", callback=lambda v: 0.0),
            # missing pressure_drop:evap and pressure_drop:cond
        ]
        with pytest.raises(ValueError, match="missing"):
            evaluate_network_residuals(assembly, unknown_values, partial, scales)

    def test_extra_evaluator_rejected(self, assembly, unknown_values, evaluators, scales):
        """Item 8: extra evaluator not in declarations is rejected."""
        extra_list = list(evaluators) + [
            NetworkResidualEvaluator(name="EXTRA:residual", callback=lambda v: 0.0)
        ]
        with pytest.raises(ValueError, match="EXTRA:residual"):
            evaluate_network_residuals(assembly, unknown_values, extra_list, scales)

    def test_duplicate_evaluator_names_rejected(self, assembly, unknown_values, scales):
        """Item 9: duplicate evaluator names in list input are rejected."""
        dup_list = [
            NetworkResidualEvaluator(name="mass_balance:n1", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="mass_balance:n1", callback=lambda v: 1.0),
            NetworkResidualEvaluator(name="mass_balance:n2", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="pressure_drop:evap", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="pressure_drop:cond", callback=lambda v: 0.0),
        ]
        with pytest.raises(ValueError, match="duplicate"):
            evaluate_network_residuals(assembly, unknown_values, dup_list, scales)

    def test_mapping_evaluators_rejected(self, assembly, unknown_values, scales):
        """Mapping is not accepted for evaluators; Sequence is required."""
        ev_map = {
            "mass_balance:n1": NetworkResidualEvaluator(
                name="mass_balance:n1", callback=lambda v: 0.0
            )
        }
        with pytest.raises(TypeError, match="Sequence"):
            evaluate_network_residuals(assembly, unknown_values, ev_map, scales)  # type: ignore[arg-type]

    def test_callback_nan_return_rejected(self, assembly, unknown_values, scales):
        """Item 11: callback returning NaN is rejected."""
        ev_nan = [
            NetworkResidualEvaluator(name="mass_balance:n1", callback=lambda v: float("nan")),
            NetworkResidualEvaluator(name="mass_balance:n2", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="pressure_drop:evap", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="pressure_drop:cond", callback=lambda v: 0.0),
        ]
        with pytest.raises(ValueError, match="non-finite"):
            evaluate_network_residuals(assembly, unknown_values, ev_nan, scales)

    def test_callback_inf_return_rejected(self, assembly, unknown_values, scales):
        """Item 12: callback returning inf is rejected."""
        ev_inf = [
            NetworkResidualEvaluator(name="mass_balance:n1", callback=lambda v: float("inf")),
            NetworkResidualEvaluator(name="mass_balance:n2", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="pressure_drop:evap", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="pressure_drop:cond", callback=lambda v: 0.0),
        ]
        with pytest.raises(ValueError, match="non-finite"):
            evaluate_network_residuals(assembly, unknown_values, ev_inf, scales)

    def test_callback_bool_return_rejected(self, assembly, unknown_values, scales):
        """Item 13: callback returning bool is rejected."""
        ev_bool = [
            NetworkResidualEvaluator(name="mass_balance:n1", callback=lambda v: True),
            NetworkResidualEvaluator(name="mass_balance:n2", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="pressure_drop:evap", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="pressure_drop:cond", callback=lambda v: 0.0),
        ]
        with pytest.raises(ValueError, match="bool"):
            evaluate_network_residuals(assembly, unknown_values, ev_bool, scales)

    def test_callback_exception_propagates(self, assembly, unknown_values, scales):
        """Item 14: exceptions from callbacks propagate without being swallowed."""

        class _Boom(RuntimeError):
            pass

        def _raise(v: object) -> float:
            raise _Boom("callback blew up")

        ev_err = [
            NetworkResidualEvaluator(name="mass_balance:n1", callback=_raise),
            NetworkResidualEvaluator(name="mass_balance:n2", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="pressure_drop:evap", callback=lambda v: 0.0),
            NetworkResidualEvaluator(name="pressure_drop:cond", callback=lambda v: 0.0),
        ]
        with pytest.raises(_Boom, match="callback blew up"):
            evaluate_network_residuals(assembly, unknown_values, ev_err, scales)


# ---------------------------------------------------------------------------
# 15–17: Scale validation
# ---------------------------------------------------------------------------


class TestScaleValidation:
    def test_missing_scale_rejected(self, assembly, unknown_values, evaluators):
        """Item 15: missing scale for a declared residual is rejected."""
        partial_scales = {
            "mass_balance:n1": 0.01,
            "mass_balance:n2": 0.01,
            # missing pressure_drop scales
        }
        with pytest.raises(ValueError, match="missing"):
            evaluate_network_residuals(assembly, unknown_values, evaluators, partial_scales)

    def test_extra_scale_rejected(self, assembly, unknown_values, evaluators, scales):
        """Item 16: extra scale key not in declarations is rejected."""
        extra_scales = dict(scales)
        extra_scales["EXTRA:scale"] = 1.0
        with pytest.raises(ValueError, match="EXTRA:scale"):
            evaluate_network_residuals(assembly, unknown_values, evaluators, extra_scales)

    def test_zero_scale_rejected(self, assembly, unknown_values, evaluators, scales):
        """Item 17a: zero scale is rejected."""
        bad = dict(scales, **{"mass_balance:n1": 0.0})
        with pytest.raises(ValueError, match="> 0"):
            evaluate_network_residuals(assembly, unknown_values, evaluators, bad)

    def test_negative_scale_rejected(self, assembly, unknown_values, evaluators, scales):
        """Item 17b: negative scale is rejected."""
        bad = dict(scales, **{"mass_balance:n1": -0.01})
        with pytest.raises(ValueError, match="> 0"):
            evaluate_network_residuals(assembly, unknown_values, evaluators, bad)

    def test_nan_scale_rejected(self, assembly, unknown_values, evaluators, scales):
        """Item 17c: NaN scale is rejected."""
        bad = dict(scales, **{"pressure_drop:evap": float("nan")})
        with pytest.raises(ValueError, match="finite"):
            evaluate_network_residuals(assembly, unknown_values, evaluators, bad)

    def test_inf_scale_rejected(self, assembly, unknown_values, evaluators, scales):
        """Item 17d: inf scale is rejected."""
        bad = dict(scales, **{"pressure_drop:evap": float("inf")})
        with pytest.raises(ValueError, match="finite"):
            evaluate_network_residuals(assembly, unknown_values, evaluators, bad)

    def test_bool_scale_rejected(self, assembly, unknown_values, evaluators, scales):
        """Item 17e: bool scale is rejected."""
        bad = dict(scales, **{"mass_balance:n1": True})
        with pytest.raises(ValueError, match="bool"):
            evaluate_network_residuals(assembly, unknown_values, evaluators, bad)

    def test_bool_false_scale_rejected(self, assembly, unknown_values, evaluators, scales):
        """False is also a bool — rejected as scale."""
        bad = dict(scales, **{"mass_balance:n2": False})
        with pytest.raises(ValueError, match="bool"):
            evaluate_network_residuals(assembly, unknown_values, evaluators, bad)


# ---------------------------------------------------------------------------
# 18–24: Evaluation result correctness
# ---------------------------------------------------------------------------


class TestEvaluationResultCorrectness:
    def test_preserves_residual_declaration_order(self, result, assembly):
        """Item 18: evaluations tuple follows assembly residual declaration order."""
        declared_order = assembly.residuals.names()
        result_names = tuple(ev.spec.name for ev in result.evaluations)
        assert result_names == declared_order

    def test_residual_vector_order_matches_assembly(self, result, assembly):
        """Item 18 (vector): ResidualVector entries follow assembly order."""
        declared_order = assembly.residuals.names()
        vector_names = tuple(ev.spec.name for ev in result.residual_vector.evaluations)
        assert vector_names == declared_order

    def test_raw_values_equal_callback_outputs(self, result):
        """Item 19: raw residual values match deterministic callback outputs.

        Deterministic values from fixtures:
        mass_balance:n1    = 0.05 - 0.05 = 0.0
        mass_balance:n2    = 0.05 - 0.05 = 0.0
        pressure_drop:evap = 100000 - 99000 - 600 = 400.0
        pressure_drop:cond = 99000 - 100000 + 1000 = 0.0
        """
        by_name = {ev.spec.name: ev.value for ev in result.evaluations}
        assert by_name["mass_balance:n1"] == pytest.approx(0.0)
        assert by_name["mass_balance:n2"] == pytest.approx(0.0)
        assert by_name["pressure_drop:evap"] == pytest.approx(400.0)
        assert by_name["pressure_drop:cond"] == pytest.approx(0.0)

    def test_residual_units_match_declarations(self, result, assembly):
        """Item 20: residual units in evaluations match assembly declarations."""
        decl_by_name = {d.name: d.unit for d in assembly.residuals.residuals}
        for ev in result.evaluations:
            assert ev.spec.unit == decl_by_name[ev.spec.name]

    def test_scales_match_explicit_scale_map(self, result, scales):
        """Item 21: scales in evaluations match the explicit scale map."""
        for ev in result.evaluations:
            assert ev.spec.scale == pytest.approx(scales[ev.spec.name])

    def test_returned_residual_vector_is_correct_type(self, result):
        """Item 22: result contains a ResidualVector."""
        assert isinstance(result.residual_vector, ResidualVector)

    def test_residual_vector_entries_are_evaluations(self, result):
        """Item 22: ResidualVector entries are ResidualEvaluation objects."""
        for ev in result.residual_vector.evaluations:
            assert isinstance(ev, ResidualEvaluation)

    def test_max_abs_scaled_correct(self, result):
        """Item 23: max_abs_scaled == 4.0 for the deterministic fixture.

        Scaled residuals:
          mass_balance:n1    = 0.0  / 0.01  = 0.0
          mass_balance:n2    = 0.0  / 0.01  = 0.0
          pressure_drop:evap = 400.0 / 100.0 = 4.0
          pressure_drop:cond = 0.0  / 100.0 = 0.0
        max_abs = 4.0
        """
        assert result.max_abs_scaled == pytest.approx(4.0)

    def test_max_abs_scaled_matches_vector_method(self, result):
        """Item 23: stored max_abs_scaled matches ResidualVector.max_abs_scaled()."""
        assert result.max_abs_scaled == pytest.approx(result.residual_vector.max_abs_scaled())

    def test_l2_scaled_correct(self, result):
        """Item 24: l2_scaled == 4.0 for the deterministic fixture.

        l2 = sqrt(0^2 + 0^2 + 4^2 + 0^2) = sqrt(16) = 4.0
        """
        assert result.l2_scaled == pytest.approx(4.0)

    def test_l2_scaled_matches_vector_method(self, result):
        """Item 24: stored l2_scaled matches ResidualVector.l2_scaled()."""
        assert result.l2_scaled == pytest.approx(result.residual_vector.l2_scaled())

    def test_scaled_values_field_is_correct(self, result):
        """scaled_values tuple contains (0.0, 0.0, 4.0, 0.0)."""
        assert result.scaled_values == pytest.approx((0.0, 0.0, 4.0, 0.0))

    def test_scaled_values_matches_vector_method(self, result):
        """scaled_values field matches ResidualVector.scaled_values()."""
        assert result.scaled_values == pytest.approx(result.residual_vector.scaled_values())

    def test_assembly_stored_in_result(self, result, assembly):
        """Result holds the original assembly object."""
        assert result.assembly is assembly

    def test_unknown_values_stored_in_result(self, result, unknown_values):
        """Result holds the original unknown_values object."""
        assert result.unknown_values is unknown_values


# ---------------------------------------------------------------------------
# 25: Mutation safety
# ---------------------------------------------------------------------------


class TestMutationSafety:
    def test_evaluation_does_not_mutate_assembly(
        self, assembly, unknown_values, evaluators, scales
    ):
        """Item 25a: assembly unknown names are unchanged after evaluation."""
        names_before = assembly.unknowns.names()
        residuals_before = assembly.residuals.names()
        evaluate_network_residuals(assembly, unknown_values, evaluators, scales)
        assert assembly.unknowns.names() == names_before
        assert assembly.residuals.names() == residuals_before

    def test_evaluation_does_not_mutate_value_map(
        self, assembly, unknown_values, evaluators, scales
    ):
        """Item 25b: NetworkUnknownValues proxy is unchanged after evaluation."""
        keys_before = set(unknown_values.values.keys())
        vals_before = dict(unknown_values.values)
        evaluate_network_residuals(assembly, unknown_values, evaluators, scales)
        assert set(unknown_values.values.keys()) == keys_before
        assert dict(unknown_values.values) == vals_before

    def test_evaluation_does_not_mutate_evaluator_list(
        self, assembly, unknown_values, evaluators, scales
    ):
        """Item 25c: evaluator list length and names are unchanged after evaluation."""
        names_before = [ev.name for ev in evaluators]
        evaluate_network_residuals(assembly, unknown_values, evaluators, scales)
        assert [ev.name for ev in evaluators] == names_before

    def test_source_dict_isolation(self, assembly, evaluators, scales):
        """Mutating the source dict after construction does not affect values."""
        source = {"mdot:evap": 0.05, "mdot:cond": 0.05, "P:n1": 100_000.0, "P:n2": 99_000.0}
        uv = NetworkUnknownValues(values=source)
        source["mdot:evap"] = 999.0  # mutate source
        assert uv.values["mdot:evap"] == 0.05  # stored copy is unaffected

    def test_result_is_frozen(self, result):
        """NetworkResidualEvaluationResult is a frozen dataclass."""
        with pytest.raises((AttributeError, TypeError)):
            result.max_abs_scaled = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 26–31: Architecture boundary assertions
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    def _source(self) -> str:
        import mpl_sim.network.residual_evaluation as _m

        return inspect.getsource(_m)

    def _imported_modules(self) -> list[str]:
        """Return all module names imported by residual_evaluation.py."""
        src = self._source()
        tree = ast.parse(src)
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        return modules

    def test_no_solve_method_on_result(self, result):
        """Item 26: NetworkResidualEvaluationResult has no solve() method."""
        assert not hasattr(result, "solve")

    def test_no_solve_method_on_unknown_values(self, unknown_values):
        """Item 26: NetworkUnknownValues has no solve() method."""
        assert not hasattr(unknown_values, "solve")

    def test_no_solve_method_on_evaluator(self):
        """Item 26: NetworkResidualEvaluator has no solve() method."""
        ev = NetworkResidualEvaluator(name="r", callback=lambda v: 0.0)
        assert not hasattr(ev, "solve")

    def test_no_scipy_import(self):
        """Item 27: scipy is not imported in residual_evaluation module."""
        for mod in self._imported_modules():
            assert "scipy" not in mod

    def test_no_numpy_import(self):
        """Item 27: numpy is not imported in residual_evaluation module."""
        for mod in self._imported_modules():
            assert "numpy" not in mod

    def test_no_fsolve_or_root(self):
        """Item 27: no iterative solver calls in residual_evaluation module."""
        src = self._source()
        assert "fsolve" not in src
        assert "least_squares" not in src
        # 'root(' — check only code lines (not docstring mentions)
        tree = ast.parse(src)
        func_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "minimize" not in func_names

    def test_no_component_import(self):
        """Item 28: mpl_sim.components is not imported."""
        for mod in self._imported_modules():
            assert "components" not in mod

    def test_no_coolprop_import(self):
        """Item 29: CoolProp is not imported."""
        for mod in self._imported_modules():
            assert "CoolProp" not in mod

    def test_no_property_backend_import(self):
        """Item 29: PropertyBackend is not imported."""
        for mod in self._imported_modules():
            assert "properties" not in mod

    def test_no_correlation_registry_import(self):
        """Item 30: CorrelationRegistry is not imported."""
        for mod in self._imported_modules():
            assert "correlations" not in mod

    def test_no_hx_model_registry_import(self):
        """Item 30: HeatExchangerModelRegistry is not imported."""
        for mod in self._imported_modules():
            assert "hx_models" not in mod

    def test_no_fluid_state_in_imports(self):
        """Item 31: FluidState-carrying modules are not imported."""
        for mod in self._imported_modules():
            assert "properties" not in mod
            assert "core" not in mod

    def test_no_system_state_in_imports(self):
        """Item 31: SystemState-carrying modules are not imported."""
        for mod in self._imported_modules():
            assert "solvers" not in mod

    def test_no_solver_import(self):
        """No solver module from closed_loop is imported."""
        for mod in self._imported_modules():
            assert "minimal_solver" not in mod
            assert "pressure_solver" not in mod
            assert "coupled_solver" not in mod
            assert "_scalar_solve" not in mod

    def test_imports_only_residuals_from_closed_loop(self):
        """Only mpl_sim.closed_loop.residuals is imported from closed_loop."""
        imported = self._imported_modules()
        closed_loop_mods = [m for m in imported if "closed_loop" in m]
        assert closed_loop_mods == ["mpl_sim.closed_loop.residuals"]

    def test_no_contribute_method(self):
        """No contribute() component execution method is present."""
        src = self._source()
        tree = ast.parse(src)
        method_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "contribute" not in method_names

    def test_ast_no_solve_def(self):
        """Item 27: no 'def solve' is defined in residual_evaluation module."""
        import mpl_sim.network.residual_evaluation as _m

        src = inspect.getsource(_m)
        tree = ast.parse(src)
        func_names = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "solve" not in func_names


# ---------------------------------------------------------------------------
# 32: Public exports
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_network_unknown_values_exported(self):
        """Item 32: NetworkUnknownValues is importable from mpl_sim.network."""
        from mpl_sim.network import NetworkUnknownValues as _NUV

        assert _NUV is NetworkUnknownValues

    def test_network_residual_evaluator_exported(self):
        """Item 32: NetworkResidualEvaluator is importable from mpl_sim.network."""
        from mpl_sim.network import NetworkResidualEvaluator as _NRE

        assert _NRE is NetworkResidualEvaluator

    def test_network_residual_evaluation_result_exported(self):
        """Item 32: NetworkResidualEvaluationResult is importable from mpl_sim.network."""
        from mpl_sim.network import NetworkResidualEvaluationResult as _NRER

        assert _NRER is NetworkResidualEvaluationResult

    def test_evaluate_network_residuals_exported(self):
        """Item 32: evaluate_network_residuals is importable from mpl_sim.network."""
        from mpl_sim.network import evaluate_network_residuals as _enr

        assert _enr is evaluate_network_residuals

    def test_all_four_symbols_in_dunder_all(self):
        """Item 32: all four Phase 13G symbols are in mpl_sim.network.__all__."""
        import mpl_sim.network as _n

        all_names = set(_n.__all__)
        assert "NetworkUnknownValues" in all_names
        assert "NetworkResidualEvaluator" in all_names
        assert "NetworkResidualEvaluationResult" in all_names
        assert "evaluate_network_residuals" in all_names

    def test_phase_13f_exports_still_present(self):
        """Item 33 proxy: Phase 13F symbols remain in mpl_sim.network.__all__."""
        import mpl_sim.network as _n

        all_names = set(_n.__all__)
        assert "NetworkUnknownDeclaration" in all_names
        assert "NetworkResidualDeclaration" in all_names
        assert "NetworkUnknownSet" in all_names
        assert "NetworkResidualSet" in all_names
        assert "NetworkResidualAssembly" in all_names
        assert "assemble_network_residuals" in all_names

    def test_phase_13e_exports_still_present(self):
        """Item 33 proxy: Phase 13E symbols remain in mpl_sim.network.__all__."""
        import mpl_sim.network as _n

        all_names = set(_n.__all__)
        assert "GraphNodeId" in all_names
        assert "ComponentInstanceId" in all_names
        assert "GraphNode" in all_names
        assert "ComponentInstance" in all_names
        assert "NetworkGraph" in all_names

    def test_public_and_direct_module_are_same_objects(self):
        """Item 32: public re-exports are the same objects as direct submodule imports."""
        assert NetworkUnknownValues is _ValuesDirect
        assert NetworkResidualEvaluator is _EvaluatorDirect
        assert NetworkResidualEvaluationResult is _ResultDirect
        assert evaluate_network_residuals is _eval_direct


# ---------------------------------------------------------------------------
# 34: Documentation honest-claims check
# ---------------------------------------------------------------------------


class TestDocumentationHonestClaims:
    _SECTION_HEADER = "## Network Residual Evaluation Foundation (Phase 13G)"

    def _concepts_text(self) -> str:
        path = pathlib.Path(__file__).parents[2] / "docs" / "user_guide" / "CONCEPTS.md"
        return path.read_text(encoding="utf-8")

    def _phase_13g_section(self) -> str:
        """Extract the Phase 13G section body from CONCEPTS.md."""
        text = self._concepts_text()
        start = text.find(self._SECTION_HEADER)
        assert start != -1, f"{self._SECTION_HEADER!r} not found in CONCEPTS.md"
        # Section ends at the next top-level '## ' heading or end of file
        end = text.find("\n## ", start + 1)
        if end == -1:
            return text[start:]
        return text[start:end]

    def test_phase_13g_section_exists(self):
        """Item 34: CONCEPTS.md contains the Phase 13G section header."""
        text = self._concepts_text()
        assert self._SECTION_HEADER in text

    def test_docs_say_evaluation_not_solving(self):
        """Item 34: Phase 13G section says evaluation."""
        section = self._phase_13g_section()
        assert "evaluation" in section.lower()

    def test_docs_say_does_not_solve(self):
        """Item 34: Phase 13G section explicitly says it does not solve."""
        section = self._phase_13g_section()
        lower = section.lower()
        assert "not solve" in lower or "does not solve" in lower

    def test_docs_say_no_component_execution(self):
        """Item 34: Phase 13G section says no component execution."""
        section = self._phase_13g_section()
        assert "component" in section.lower()

    def test_docs_say_no_property_lookup(self):
        """Item 34: Phase 13G section says no property lookup."""
        section = self._phase_13g_section()
        lower = section.lower()
        assert "property" in lower or "coolprop" in lower

    def test_docs_network_residual_evaluation_marked_implemented(self):
        """Item 34: 'What is NOT implemented' table shows Phase 13G as implemented."""
        text = self._concepts_text()
        assert "Network residual evaluation" in text
        # Find the table entry
        idx = text.find("Network residual evaluation")
        assert idx != -1
        line = text[idx : idx + 150]
        assert "Phase 13G" in line or "Implemented" in line

    def test_docs_solver_still_deferred(self):
        """Item 34: generic network solver is still listed as deferred in CONCEPTS.md."""
        text = self._concepts_text()
        assert "Deferred" in text
        assert "solve(network)" in text or "network solver" in text.lower()


# ---------------------------------------------------------------------------
# Additional deterministic scenario: mass-flow-only assembly
# ---------------------------------------------------------------------------


class TestMassFlowOnlyAssembly:
    def test_mass_flow_only_evaluation(self):
        """Evaluation works when pressure unknowns/residuals are excluded."""
        graph = _two_component_closed_loop()
        asm = assemble_network_residuals(
            graph,
            include_pressure_unknowns=False,
            include_pressure_residuals=False,
        )
        # Only mass-flow unknowns: mdot:evap, mdot:cond
        uv = NetworkUnknownValues(values={"mdot:evap": 0.1, "mdot:cond": 0.1})
        evs = [
            NetworkResidualEvaluator(
                name="mass_balance:n1",
                callback=lambda v: v["mdot:evap"] - v["mdot:cond"],
            ),
            NetworkResidualEvaluator(
                name="mass_balance:n2",
                callback=lambda v: v["mdot:cond"] - v["mdot:evap"],
            ),
        ]
        sc = {"mass_balance:n1": 0.01, "mass_balance:n2": 0.01}
        res = evaluate_network_residuals(asm, uv, evs, sc)
        assert res.max_abs_scaled == pytest.approx(0.0)
        assert res.l2_scaled == pytest.approx(0.0)
        assert len(res.evaluations) == 2

    def test_order_with_larger_graph(self):
        """Residual order matches assembly order for a three-component graph."""
        graph = NetworkGraph(
            nodes=[_node("a"), _node("b"), _node("c")],
            instances=[
                _inst("comp1", "evaporator", "a", "b"),
                _inst("comp2", "condenser", "b", "c"),
                _inst("comp3", "pump", "c", "a"),
            ],
        )
        asm = assemble_network_residuals(graph)
        uv = NetworkUnknownValues(
            values={
                "mdot:comp1": 0.05,
                "mdot:comp2": 0.05,
                "mdot:comp3": 0.05,
                "P:a": 100_000.0,
                "P:b": 99_000.0,
                "P:c": 98_000.0,
            }
        )
        evs = [
            NetworkResidualEvaluator(name=n, callback=lambda v, _n=n: 0.0)
            for n in asm.residuals.names()
        ]
        sc = {n: 1.0 for n in asm.residuals.names()}
        res = evaluate_network_residuals(asm, uv, evs, sc)
        assert tuple(ev.spec.name for ev in res.evaluations) == asm.residuals.names()
