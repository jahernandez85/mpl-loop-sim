"""Block 15B.2 — Fixed Single-Loop Physical Residual Assembly MVP tests.

These tests verify the explicit parameterized algebraic residual assembly for
the fixed single-loop network declared in Block 15B.1.

No production component physics are executed.  No SystemState is assembled.
No FluidState is created.  No CoolProp, PropertyBackend, correlations, or
HX models are called.

This is NOT solve(network).  This is NOT production component execution.
This is NOT arbitrary-topology simulation.  This is a fixed-architecture,
explicitly parameterized algebraic residual assembly for the 15B.1 scenario.

Sign convention (see module docstring of fixed_single_loop_residuals):
    pressure_drop:accumulator = P_n_acc_out - accumulator_pressure_reference
    pressure_drop:pump        = P_n_pump_out - P_n_acc_out - pump_pressure_rise
    pressure_drop:evaporator  = P_n_evap_out - P_n_pump_out + evaporator_pressure_drop
    pressure_drop:condenser   = P_n_cond_out - P_n_evap_out + condenser_pressure_drop
    mass_balance:n_cond_out   = mdot_condenser - mdot_accumulator   (owned by accumulator)
    mass_balance:n_acc_out    = mdot_accumulator - mdot_pump         (owned by pump)
    mass_balance:n_pump_out   = mdot_pump - mdot_evaporator          (owned by evaporator)
    mass_balance:n_evap_out   = mdot_evaporator - mdot_condenser     (owned by condenser)

Consistent solution at equal mass flow m and consistent pressures:
    mdot_* = m (any finite m)
    P_n_acc_out  = P_ref
    P_n_pump_out = P_ref + pump_rise
    P_n_evap_out = P_ref + pump_rise - evap_drop
    P_n_cond_out = P_ref + pump_rise - evap_drop - cond_drop

Coverage items:

Parameter validation:
 1. valid parameters build successfully
 2. all four fields are stored as float
 3. int inputs are accepted and coerced to float
 4. bool rejected for pump_pressure_rise
 5. bool rejected for evaporator_pressure_drop
 6. bool rejected for condenser_pressure_drop
 7. bool rejected for accumulator_pressure_reference
 8. string rejected for pump_pressure_rise
 9. NaN rejected for pump_pressure_rise
10. +inf rejected for evaporator_pressure_drop
11. -inf rejected for condenser_pressure_drop
12. NaN rejected for accumulator_pressure_reference
13. parameters are frozen after construction
14. negative values are accepted (no sign constraint in this MVP)
15. zero values are accepted (degenerate but not invalid)

Assembly construction:
16. builds from valid scenario and parameters
17. returns FixedSingleLoopPhysicalResidualAssembly
18. rejects non-FixedSingleLoopScenario as scenario
19. rejects non-FixedSingleLoopResidualParameters as parameters
20. rejects non-Mapping metadata
21. scenario is stored on assembly
22. parameters are stored on assembly
23. residual_map field is present and correct type
24. adapter_set field is present and correct type
25. metadata defensively copied
26. metadata proxy is read-only
27. metadata is None by default
28. assembly is frozen
29. adapter_set has exactly four adapters
30. residual_map has exactly eight entries

Residual map structure:
31. (accumulator, "mass_balance") → mass_balance:n_cond_out
32. (accumulator, "pressure_drop") → pressure_drop:accumulator
33. (pump, "mass_balance") → mass_balance:n_acc_out
34. (pump, "pressure_drop") → pressure_drop:pump
35. (evaporator, "mass_balance") → mass_balance:n_pump_out
36. (evaporator, "pressure_drop") → pressure_drop:evaporator
37. (condenser, "mass_balance") → mass_balance:n_evap_out
38. (condenser, "pressure_drop") → pressure_drop:condenser

Adapter set structure:
39. adapters are in component declaration order (acc, pump, evap, cond)
40. no duplicate component IDs in adapter_set
41. adapter_set covers exactly the scenario bound components
42. all adapters have callable callbacks
43. adapter callback returns ComponentContribution
44. accumulator adapter contributes two residuals
45. pump adapter contributes two residuals
46. evaporator adapter contributes two residuals
47. condenser adapter contributes two residuals

Residual evaluation at consistent point:
48. evaluation pipeline builds without errors
49. all eight residuals equal zero at the consistent solution
50. mass_balance:n_acc_out equals zero at consistent point
51. mass_balance:n_pump_out equals zero at consistent point
52. mass_balance:n_evap_out equals zero at consistent point
53. mass_balance:n_cond_out equals zero at consistent point
54. pressure_drop:accumulator equals zero at consistent point
55. pressure_drop:pump equals zero at consistent point
56. pressure_drop:evaporator equals zero at consistent point
57. pressure_drop:condenser equals zero at consistent point

Residual evaluation off consistent point:
58. mass_balance:n_acc_out is nonzero when mdot_acc ≠ mdot_pump
59. mass_balance:n_pump_out is nonzero when mdot_pump ≠ mdot_evap
60. mass_balance:n_evap_out is nonzero when mdot_evap ≠ mdot_cond
61. mass_balance:n_cond_out is nonzero when mdot_cond ≠ mdot_acc
62. pressure_drop:accumulator is nonzero when P_acc_out ≠ P_ref
63. pressure_drop:pump is nonzero when pump pressure gap is wrong
64. pressure_drop:evaporator is nonzero when evap pressure gap is wrong
65. pressure_drop:condenser is nonzero when cond pressure gap is wrong

Parameter sensitivity:
66. changing pump_pressure_rise changes pressure_drop:pump residual
67. changing pump_pressure_rise does not change pressure_drop:evaporator
68. changing evaporator_pressure_drop changes pressure_drop:evaporator residual
69. changing condenser_pressure_drop changes pressure_drop:condenser residual
70. changing accumulator_pressure_reference changes pressure_drop:accumulator residual
71. changing mass flow uniformly leaves all pressure residuals at zero

Convenience wrapper:
72. build_component_contribution_from_fixed_single_loop_residuals returns ComponentContribution
73. pump contribution has correct residual values at consistent point
74. rejects non-ComponentInstanceId for component_id
75. rejects non-FixedSingleLoopPhysicalResidualAssembly for assembly
76. rejects non-Mapping for unknown_values
77. rejects component_id not in assembly

Residual ordering:
78. adapter_set ordering is deterministic across two builds
79. residual values ordered as declared in scenario assembly
80. evaluation ordering matches scenario residual_names ordering

Boundary tests (AST / import-level):
81. fixed_single_loop_residuals module: no CoolProp import
82. fixed_single_loop_residuals module: no PropertyBackend import
83. fixed_single_loop_residuals module: no CorrelationRegistry import
84. fixed_single_loop_residuals module: no hx_models import
85. fixed_single_loop_residuals module: no SystemState import
86. fixed_single_loop_residuals module: no FluidState import
87. fixed_single_loop_residuals module: no mpl_sim.components import
88. fixed_single_loop_residuals module: no mpl_sim.properties import
89. fixed_single_loop_residuals module: no contribute attribute-call nodes
90. fixed_single_loop_residuals module: no solve(network) pattern
91. this test file: no CoolProp import
92. this test file: no PropertyBackend import
93. this test file: no contribute attribute-call nodes

Production contract regression:
94. Component reports NO_CONTRIBUTE_METHOD
95. Pipe reports NO_CONTRIBUTE_METHOD
96. PumpComponent reports NO_CONTRIBUTE_METHOD
97. AccumulatorComponent reports NO_CONTRIBUTE_METHOD
98. EvaporatorComponent reports NO_CONTRIBUTE_METHOD
99. CondenserComponent reports NO_CONTRIBUTE_METHOD

Public API:
100. new symbols exported from mpl_sim.network
101. new symbols in __all__
102. no private symbols in __all__
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from mpl_sim.network import (
    ComponentContribution,
    ComponentInstanceId,
    ContributionResidualMap,
    NetworkUnknownValues,
    ProductionComponentContractStatus,
    build_network_residual_evaluators,
    build_physical_adapters_from_contributions,
    evaluate_network_residuals,
    inspect_known_production_component_contracts,
)
from mpl_sim.network.contribution_adapters import ComponentContributionAdapterSet
from mpl_sim.network.fixed_single_loop_residuals import (
    FixedSingleLoopPhysicalResidualAssembly,
    FixedSingleLoopResidualParameters,
    build_component_contribution_from_fixed_single_loop_residuals,
    build_fixed_single_loop_physical_residuals,
)
from mpl_sim.network.fixed_single_loop_scenario import build_fixed_single_loop_scenario

# ---------------------------------------------------------------------------
# Path helpers for boundary (AST) tests
# ---------------------------------------------------------------------------

_RESIDUALS_MODULE = (
    pathlib.Path(__file__).parent.parent.parent
    / "src"
    / "mpl_sim"
    / "network"
    / "fixed_single_loop_residuals.py"
)
_THIS_FILE = pathlib.Path(__file__)


def _read_source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_ast(path: pathlib.Path) -> ast.Module:
    return ast.parse(_read_source(path))


def _has_import(tree: ast.Module, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if name in alias.name:
                    return True
        if isinstance(node, ast.ImportFrom):
            if node.module and name in node.module:
                return True
            for alias in node.names:
                if name in alias.name:
                    return True
    return False


def _has_contribute_attribute_call(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "contribute":
                return True
    return False


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_PUMP_RISE = 50_000.0  # Pa
_EVAP_DROP = 20_000.0  # Pa
_COND_DROP = 10_000.0  # Pa
_P_REF = 100_000.0  # Pa


def _default_params() -> FixedSingleLoopResidualParameters:
    return FixedSingleLoopResidualParameters(
        pump_pressure_rise=_PUMP_RISE,
        evaporator_pressure_drop=_EVAP_DROP,
        condenser_pressure_drop=_COND_DROP,
        accumulator_pressure_reference=_P_REF,
    )


def _default_assembly() -> FixedSingleLoopPhysicalResidualAssembly:
    scenario = build_fixed_single_loop_scenario()
    params = _default_params()
    return build_fixed_single_loop_physical_residuals(scenario, params)


def _consistent_unknowns(mdot: float = 1.0) -> dict[str, float]:
    """Consistent unknown values for the default scenario/parameters."""
    P_acc = _P_REF
    P_pump = _P_REF + _PUMP_RISE
    P_evap = P_pump - _EVAP_DROP
    P_cond = P_evap - _COND_DROP
    return {
        "mdot:accumulator": mdot,
        "mdot:pump": mdot,
        "mdot:evaporator": mdot,
        "mdot:condenser": mdot,
        "P:n_acc_out": P_acc,
        "P:n_pump_out": P_pump,
        "P:n_evap_out": P_evap,
        "P:n_cond_out": P_cond,
    }


def _evaluate(
    assembly: FixedSingleLoopPhysicalResidualAssembly,
    unknown_values: dict[str, float],
) -> dict[str, float]:
    """Evaluate all 8 residuals and return a residual-name → value mapping.

    This is NOT solve(network).  This is NOT production component execution.
    It uses the existing Phase 14A/13G evaluation infrastructure.
    """
    physical_adapter_set = build_physical_adapters_from_contributions(
        assembly.scenario.binding_context,
        assembly.adapter_set,
    )
    evaluators = build_network_residual_evaluators(
        assembly.scenario.assembly,
        physical_adapter_set,
    )
    # Uniform unit scales (1.0) for all residuals — adequate for zero-check tests.
    scales = {name: 1.0 for name in assembly.scenario.assembly.residuals.names()}
    result = evaluate_network_residuals(
        assembly=assembly.scenario.assembly,
        unknown_values=NetworkUnknownValues(unknown_values),
        evaluators=evaluators,
        scales=scales,
    )
    return {ev.spec.name: ev.value for ev in result.evaluations}


# ---------------------------------------------------------------------------
# Group 1: Parameter validation
# ---------------------------------------------------------------------------


def test_valid_parameters_build_successfully():
    params = _default_params()
    assert params is not None


def test_all_four_fields_stored_as_float():
    params = _default_params()
    assert isinstance(params.pump_pressure_rise, float)
    assert isinstance(params.evaporator_pressure_drop, float)
    assert isinstance(params.condenser_pressure_drop, float)
    assert isinstance(params.accumulator_pressure_reference, float)


def test_int_inputs_coerced_to_float():
    params = FixedSingleLoopResidualParameters(
        pump_pressure_rise=50000,
        evaporator_pressure_drop=20000,
        condenser_pressure_drop=10000,
        accumulator_pressure_reference=100000,
    )
    assert isinstance(params.pump_pressure_rise, float)
    assert params.pump_pressure_rise == 50000.0


def test_bool_rejected_for_pump_pressure_rise():
    with pytest.raises(TypeError, match="bool"):
        FixedSingleLoopResidualParameters(
            pump_pressure_rise=True,
            evaporator_pressure_drop=_EVAP_DROP,
            condenser_pressure_drop=_COND_DROP,
            accumulator_pressure_reference=_P_REF,
        )


def test_bool_rejected_for_evaporator_pressure_drop():
    with pytest.raises(TypeError, match="bool"):
        FixedSingleLoopResidualParameters(
            pump_pressure_rise=_PUMP_RISE,
            evaporator_pressure_drop=False,
            condenser_pressure_drop=_COND_DROP,
            accumulator_pressure_reference=_P_REF,
        )


def test_bool_rejected_for_condenser_pressure_drop():
    with pytest.raises(TypeError, match="bool"):
        FixedSingleLoopResidualParameters(
            pump_pressure_rise=_PUMP_RISE,
            evaporator_pressure_drop=_EVAP_DROP,
            condenser_pressure_drop=True,
            accumulator_pressure_reference=_P_REF,
        )


def test_bool_rejected_for_accumulator_pressure_reference():
    with pytest.raises(TypeError, match="bool"):
        FixedSingleLoopResidualParameters(
            pump_pressure_rise=_PUMP_RISE,
            evaporator_pressure_drop=_EVAP_DROP,
            condenser_pressure_drop=_COND_DROP,
            accumulator_pressure_reference=False,
        )


def test_string_rejected_for_pump_pressure_rise():
    with pytest.raises(TypeError):
        FixedSingleLoopResidualParameters(
            pump_pressure_rise="50000",  # type: ignore[arg-type]
            evaporator_pressure_drop=_EVAP_DROP,
            condenser_pressure_drop=_COND_DROP,
            accumulator_pressure_reference=_P_REF,
        )


def test_nan_rejected_for_pump_pressure_rise():
    with pytest.raises(ValueError, match="finite"):
        FixedSingleLoopResidualParameters(
            pump_pressure_rise=float("nan"),
            evaporator_pressure_drop=_EVAP_DROP,
            condenser_pressure_drop=_COND_DROP,
            accumulator_pressure_reference=_P_REF,
        )


def test_pos_inf_rejected_for_evaporator_pressure_drop():
    with pytest.raises(ValueError, match="finite"):
        FixedSingleLoopResidualParameters(
            pump_pressure_rise=_PUMP_RISE,
            evaporator_pressure_drop=float("inf"),
            condenser_pressure_drop=_COND_DROP,
            accumulator_pressure_reference=_P_REF,
        )


def test_neg_inf_rejected_for_condenser_pressure_drop():
    with pytest.raises(ValueError, match="finite"):
        FixedSingleLoopResidualParameters(
            pump_pressure_rise=_PUMP_RISE,
            evaporator_pressure_drop=_EVAP_DROP,
            condenser_pressure_drop=float("-inf"),
            accumulator_pressure_reference=_P_REF,
        )


def test_nan_rejected_for_accumulator_pressure_reference():
    with pytest.raises(ValueError, match="finite"):
        FixedSingleLoopResidualParameters(
            pump_pressure_rise=_PUMP_RISE,
            evaporator_pressure_drop=_EVAP_DROP,
            condenser_pressure_drop=_COND_DROP,
            accumulator_pressure_reference=float("nan"),
        )


def test_parameters_are_frozen():
    params = _default_params()
    with pytest.raises((AttributeError, TypeError)):
        params.pump_pressure_rise = 99.0  # type: ignore[misc]


def test_negative_pump_pressure_rise_accepted():
    params = FixedSingleLoopResidualParameters(
        pump_pressure_rise=-1000.0,
        evaporator_pressure_drop=_EVAP_DROP,
        condenser_pressure_drop=_COND_DROP,
        accumulator_pressure_reference=_P_REF,
    )
    assert params.pump_pressure_rise == -1000.0


def test_zero_values_accepted():
    params = FixedSingleLoopResidualParameters(
        pump_pressure_rise=0.0,
        evaporator_pressure_drop=0.0,
        condenser_pressure_drop=0.0,
        accumulator_pressure_reference=0.0,
    )
    assert params.pump_pressure_rise == 0.0


# ---------------------------------------------------------------------------
# Group 2: Assembly construction
# ---------------------------------------------------------------------------


def test_assembly_builds_successfully():
    assembly = _default_assembly()
    assert assembly is not None


def test_assembly_returns_correct_type():
    assembly = _default_assembly()
    assert isinstance(assembly, FixedSingleLoopPhysicalResidualAssembly)


def test_assembly_rejects_wrong_scenario_type():
    params = _default_params()
    with pytest.raises(TypeError, match="FixedSingleLoopScenario"):
        build_fixed_single_loop_physical_residuals("not_a_scenario", params)


def test_assembly_rejects_wrong_parameters_type():
    scenario = build_fixed_single_loop_scenario()
    with pytest.raises(TypeError, match="FixedSingleLoopResidualParameters"):
        build_fixed_single_loop_physical_residuals(scenario, {"pump_pressure_rise": 1.0})


def test_assembly_rejects_non_mapping_metadata():
    scenario = build_fixed_single_loop_scenario()
    params = _default_params()
    with pytest.raises(TypeError):
        build_fixed_single_loop_physical_residuals(scenario, params, metadata="bad")


def test_assembly_stores_scenario():
    scenario = build_fixed_single_loop_scenario()
    assembly = build_fixed_single_loop_physical_residuals(scenario, _default_params())
    assert assembly.scenario is scenario


def test_assembly_stores_parameters():
    params = _default_params()
    assembly = build_fixed_single_loop_physical_residuals(
        build_fixed_single_loop_scenario(), params
    )
    assert assembly.parameters is params


def test_assembly_residual_map_is_correct_type():
    assembly = _default_assembly()
    assert isinstance(assembly.residual_map, ContributionResidualMap)


def test_assembly_adapter_set_is_correct_type():
    assembly = _default_assembly()
    assert isinstance(assembly.adapter_set, ComponentContributionAdapterSet)


def test_assembly_metadata_defensively_copied():
    meta = {"key": "original"}
    scenario = build_fixed_single_loop_scenario()
    assembly = build_fixed_single_loop_physical_residuals(
        scenario, _default_params(), metadata=meta
    )
    meta["key"] = "mutated"
    assert assembly.metadata is not None
    assert assembly.metadata["key"] == "original"


def test_assembly_metadata_proxy_is_read_only():
    scenario = build_fixed_single_loop_scenario()
    assembly = build_fixed_single_loop_physical_residuals(
        scenario, _default_params(), metadata={"k": "v"}
    )
    assert assembly.metadata is not None
    with pytest.raises(TypeError):
        assembly.metadata["new"] = "oops"  # type: ignore[index]


def test_assembly_metadata_none_by_default():
    assembly = _default_assembly()
    assert assembly.metadata is None


def test_assembly_is_frozen():
    assembly = _default_assembly()
    with pytest.raises((AttributeError, TypeError)):
        assembly.parameters = None  # type: ignore[misc]


def test_adapter_set_has_four_adapters():
    assembly = _default_assembly()
    assert len(assembly.adapter_set.adapters) == 4


def test_residual_map_has_eight_entries():
    assembly = _default_assembly()
    assert len(assembly.residual_map.mapping) == 8


# ---------------------------------------------------------------------------
# Group 3: Residual map structure
# ---------------------------------------------------------------------------


def test_residual_map_accumulator_mass_balance():
    assembly = _default_assembly()
    cid = assembly.scenario.component_ids.accumulator
    rn = assembly.scenario.residual_names
    key = (cid, "mass_balance")
    assert assembly.residual_map.mapping[key] == rn.mass_balance_n_cond_out


def test_residual_map_accumulator_pressure_drop():
    assembly = _default_assembly()
    cid = assembly.scenario.component_ids.accumulator
    rn = assembly.scenario.residual_names
    key = (cid, "pressure_drop")
    assert assembly.residual_map.mapping[key] == rn.pressure_drop_accumulator


def test_residual_map_pump_mass_balance():
    assembly = _default_assembly()
    cid = assembly.scenario.component_ids.pump
    rn = assembly.scenario.residual_names
    key = (cid, "mass_balance")
    assert assembly.residual_map.mapping[key] == rn.mass_balance_n_acc_out


def test_residual_map_pump_pressure_drop():
    assembly = _default_assembly()
    cid = assembly.scenario.component_ids.pump
    rn = assembly.scenario.residual_names
    key = (cid, "pressure_drop")
    assert assembly.residual_map.mapping[key] == rn.pressure_drop_pump


def test_residual_map_evaporator_mass_balance():
    assembly = _default_assembly()
    cid = assembly.scenario.component_ids.evaporator
    rn = assembly.scenario.residual_names
    key = (cid, "mass_balance")
    assert assembly.residual_map.mapping[key] == rn.mass_balance_n_pump_out


def test_residual_map_evaporator_pressure_drop():
    assembly = _default_assembly()
    cid = assembly.scenario.component_ids.evaporator
    rn = assembly.scenario.residual_names
    key = (cid, "pressure_drop")
    assert assembly.residual_map.mapping[key] == rn.pressure_drop_evaporator


def test_residual_map_condenser_mass_balance():
    assembly = _default_assembly()
    cid = assembly.scenario.component_ids.condenser
    rn = assembly.scenario.residual_names
    key = (cid, "mass_balance")
    assert assembly.residual_map.mapping[key] == rn.mass_balance_n_evap_out


def test_residual_map_condenser_pressure_drop():
    assembly = _default_assembly()
    cid = assembly.scenario.component_ids.condenser
    rn = assembly.scenario.residual_names
    key = (cid, "pressure_drop")
    assert assembly.residual_map.mapping[key] == rn.pressure_drop_condenser


# ---------------------------------------------------------------------------
# Group 4: Adapter set structure
# ---------------------------------------------------------------------------


def test_adapters_in_component_declaration_order():
    assembly = _default_assembly()
    cids = assembly.scenario.component_ids
    adapter_ids = [a.instance_id for a in assembly.adapter_set.adapters]
    assert adapter_ids[0] == cids.accumulator
    assert adapter_ids[1] == cids.pump
    assert adapter_ids[2] == cids.evaporator
    assert adapter_ids[3] == cids.condenser


def test_no_duplicate_component_ids_in_adapter_set():
    assembly = _default_assembly()
    ids = [a.instance_id.value for a in assembly.adapter_set.adapters]
    assert len(set(ids)) == len(ids)


def test_adapter_set_covers_exactly_bound_components():
    assembly = _default_assembly()
    adapter_ids = {a.instance_id.value for a in assembly.adapter_set.adapters}
    bound_ids = {
        b.instance_id.value for b in assembly.scenario.binding_context.binding_set.bindings
    }
    assert adapter_ids == bound_ids


def test_all_adapter_callbacks_are_callable():
    assembly = _default_assembly()
    for adapter in assembly.adapter_set.adapters:
        assert callable(adapter.callback)


def test_adapter_callback_returns_component_contribution():
    from mpl_sim.network.contribution_adapters import ComponentContributionContext

    assembly = _default_assembly()
    uv = _consistent_unknowns()
    ctx = ComponentContributionContext(
        binding_context=assembly.scenario.binding_context,
        unknown_values=uv,
    )
    for adapter in assembly.adapter_set.adapters:
        result = adapter.callback(ctx)
        assert isinstance(result, ComponentContribution)


def test_accumulator_adapter_contributes_two_residuals():
    from mpl_sim.network.contribution_adapters import ComponentContributionContext

    assembly = _default_assembly()
    acc_adapter = assembly.adapter_set.adapters[0]
    ctx = ComponentContributionContext(
        binding_context=assembly.scenario.binding_context,
        unknown_values=_consistent_unknowns(),
    )
    result = acc_adapter.callback(ctx)
    assert len(result.residual_values) == 2


def test_pump_adapter_contributes_two_residuals():
    from mpl_sim.network.contribution_adapters import ComponentContributionContext

    assembly = _default_assembly()
    pump_adapter = assembly.adapter_set.adapters[1]
    ctx = ComponentContributionContext(
        binding_context=assembly.scenario.binding_context,
        unknown_values=_consistent_unknowns(),
    )
    result = pump_adapter.callback(ctx)
    assert len(result.residual_values) == 2


def test_evaporator_adapter_contributes_two_residuals():
    from mpl_sim.network.contribution_adapters import ComponentContributionContext

    assembly = _default_assembly()
    evap_adapter = assembly.adapter_set.adapters[2]
    ctx = ComponentContributionContext(
        binding_context=assembly.scenario.binding_context,
        unknown_values=_consistent_unknowns(),
    )
    result = evap_adapter.callback(ctx)
    assert len(result.residual_values) == 2


def test_condenser_adapter_contributes_two_residuals():
    from mpl_sim.network.contribution_adapters import ComponentContributionContext

    assembly = _default_assembly()
    cond_adapter = assembly.adapter_set.adapters[3]
    ctx = ComponentContributionContext(
        binding_context=assembly.scenario.binding_context,
        unknown_values=_consistent_unknowns(),
    )
    result = cond_adapter.callback(ctx)
    assert len(result.residual_values) == 2


# ---------------------------------------------------------------------------
# Group 5: Residual evaluation at consistent point
# ---------------------------------------------------------------------------


def test_evaluation_pipeline_builds_without_errors():
    assembly = _default_assembly()
    physical_adapter_set = build_physical_adapters_from_contributions(
        assembly.scenario.binding_context,
        assembly.adapter_set,
    )
    evaluators = build_network_residual_evaluators(
        assembly.scenario.assembly,
        physical_adapter_set,
    )
    assert evaluators is not None
    assert len(evaluators) == 8


def test_all_residuals_zero_at_consistent_point():
    assembly = _default_assembly()
    residuals = _evaluate(assembly, _consistent_unknowns())
    for name, value in residuals.items():
        assert abs(value) < 1e-9, f"Residual {name!r} = {value} (expected 0)"


def test_mass_balance_n_acc_out_zero_at_consistent_point():
    assembly = _default_assembly()
    residuals = _evaluate(assembly, _consistent_unknowns())
    assert abs(residuals["mass_balance:n_acc_out"]) < 1e-9


def test_mass_balance_n_pump_out_zero_at_consistent_point():
    assembly = _default_assembly()
    residuals = _evaluate(assembly, _consistent_unknowns())
    assert abs(residuals["mass_balance:n_pump_out"]) < 1e-9


def test_mass_balance_n_evap_out_zero_at_consistent_point():
    assembly = _default_assembly()
    residuals = _evaluate(assembly, _consistent_unknowns())
    assert abs(residuals["mass_balance:n_evap_out"]) < 1e-9


def test_mass_balance_n_cond_out_zero_at_consistent_point():
    assembly = _default_assembly()
    residuals = _evaluate(assembly, _consistent_unknowns())
    assert abs(residuals["mass_balance:n_cond_out"]) < 1e-9


def test_pressure_drop_accumulator_zero_at_consistent_point():
    assembly = _default_assembly()
    residuals = _evaluate(assembly, _consistent_unknowns())
    assert abs(residuals["pressure_drop:accumulator"]) < 1e-9


def test_pressure_drop_pump_zero_at_consistent_point():
    assembly = _default_assembly()
    residuals = _evaluate(assembly, _consistent_unknowns())
    assert abs(residuals["pressure_drop:pump"]) < 1e-9


def test_pressure_drop_evaporator_zero_at_consistent_point():
    assembly = _default_assembly()
    residuals = _evaluate(assembly, _consistent_unknowns())
    assert abs(residuals["pressure_drop:evaporator"]) < 1e-9


def test_pressure_drop_condenser_zero_at_consistent_point():
    assembly = _default_assembly()
    residuals = _evaluate(assembly, _consistent_unknowns())
    assert abs(residuals["pressure_drop:condenser"]) < 1e-9


# ---------------------------------------------------------------------------
# Group 6: Residual evaluation off consistent point
# ---------------------------------------------------------------------------


def test_mass_balance_n_acc_out_nonzero_when_mdots_differ():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    uv["mdot:pump"] = uv["mdot:pump"] + 0.5  # mdot_acc ≠ mdot_pump
    residuals = _evaluate(assembly, uv)
    assert abs(residuals["mass_balance:n_acc_out"]) > 0.1


def test_mass_balance_n_pump_out_nonzero_when_mdots_differ():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    uv["mdot:evaporator"] = uv["mdot:evaporator"] + 0.3
    residuals = _evaluate(assembly, uv)
    assert abs(residuals["mass_balance:n_pump_out"]) > 0.1


def test_mass_balance_n_evap_out_nonzero_when_mdots_differ():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    uv["mdot:condenser"] = uv["mdot:condenser"] + 0.2
    residuals = _evaluate(assembly, uv)
    assert abs(residuals["mass_balance:n_evap_out"]) > 0.1


def test_mass_balance_n_cond_out_nonzero_when_mdots_differ():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    uv["mdot:accumulator"] = uv["mdot:accumulator"] + 0.4
    residuals = _evaluate(assembly, uv)
    assert abs(residuals["mass_balance:n_cond_out"]) > 0.1


def test_pressure_drop_accumulator_nonzero_when_P_acc_wrong():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    uv["P:n_acc_out"] = _P_REF + 5000.0  # wrong pressure at accumulator outlet
    residuals = _evaluate(assembly, uv)
    assert abs(residuals["pressure_drop:accumulator"]) > 1.0


def test_pressure_drop_pump_nonzero_when_pump_pressure_gap_wrong():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    uv["P:n_pump_out"] = uv["P:n_pump_out"] + 3000.0  # wrong pump outlet pressure
    residuals = _evaluate(assembly, uv)
    assert abs(residuals["pressure_drop:pump"]) > 1.0


def test_pressure_drop_evaporator_nonzero_when_evap_pressure_gap_wrong():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    uv["P:n_evap_out"] = uv["P:n_evap_out"] + 2000.0  # wrong evap outlet pressure
    residuals = _evaluate(assembly, uv)
    assert abs(residuals["pressure_drop:evaporator"]) > 1.0


def test_pressure_drop_condenser_nonzero_when_cond_pressure_gap_wrong():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    uv["P:n_cond_out"] = uv["P:n_cond_out"] + 1500.0  # wrong cond outlet pressure
    residuals = _evaluate(assembly, uv)
    assert abs(residuals["pressure_drop:condenser"]) > 1.0


# ---------------------------------------------------------------------------
# Group 7: Parameter sensitivity
# ---------------------------------------------------------------------------


def test_changing_pump_rise_changes_pump_residual():
    scenario = build_fixed_single_loop_scenario()
    params1 = _default_params()
    params2 = FixedSingleLoopResidualParameters(
        pump_pressure_rise=_PUMP_RISE + 5000.0,
        evaporator_pressure_drop=_EVAP_DROP,
        condenser_pressure_drop=_COND_DROP,
        accumulator_pressure_reference=_P_REF,
    )
    uv = _consistent_unknowns()  # consistent for params1 only
    res1 = _evaluate(build_fixed_single_loop_physical_residuals(scenario, params1), uv)
    res2 = _evaluate(build_fixed_single_loop_physical_residuals(scenario, params2), uv)
    assert res1["pressure_drop:pump"] != res2["pressure_drop:pump"]


def test_changing_pump_rise_does_not_change_evap_residual():
    scenario = build_fixed_single_loop_scenario()
    params1 = _default_params()
    params2 = FixedSingleLoopResidualParameters(
        pump_pressure_rise=_PUMP_RISE + 5000.0,
        evaporator_pressure_drop=_EVAP_DROP,
        condenser_pressure_drop=_COND_DROP,
        accumulator_pressure_reference=_P_REF,
    )
    uv = _consistent_unknowns()
    res1 = _evaluate(build_fixed_single_loop_physical_residuals(scenario, params1), uv)
    res2 = _evaluate(build_fixed_single_loop_physical_residuals(scenario, params2), uv)
    # Evaporator residual depends on P_n_evap_out - P_n_pump_out + evap_drop.
    # pump_rise does not appear in the evaporator equation, so equal.
    assert res1["pressure_drop:evaporator"] == res2["pressure_drop:evaporator"]


def test_changing_evap_drop_changes_evap_residual():
    scenario = build_fixed_single_loop_scenario()
    params1 = _default_params()
    params2 = FixedSingleLoopResidualParameters(
        pump_pressure_rise=_PUMP_RISE,
        evaporator_pressure_drop=_EVAP_DROP + 3000.0,
        condenser_pressure_drop=_COND_DROP,
        accumulator_pressure_reference=_P_REF,
    )
    uv = _consistent_unknowns()
    res1 = _evaluate(build_fixed_single_loop_physical_residuals(scenario, params1), uv)
    res2 = _evaluate(build_fixed_single_loop_physical_residuals(scenario, params2), uv)
    assert res1["pressure_drop:evaporator"] != res2["pressure_drop:evaporator"]


def test_changing_cond_drop_changes_cond_residual():
    scenario = build_fixed_single_loop_scenario()
    params1 = _default_params()
    params2 = FixedSingleLoopResidualParameters(
        pump_pressure_rise=_PUMP_RISE,
        evaporator_pressure_drop=_EVAP_DROP,
        condenser_pressure_drop=_COND_DROP + 2000.0,
        accumulator_pressure_reference=_P_REF,
    )
    uv = _consistent_unknowns()
    res1 = _evaluate(build_fixed_single_loop_physical_residuals(scenario, params1), uv)
    res2 = _evaluate(build_fixed_single_loop_physical_residuals(scenario, params2), uv)
    assert res1["pressure_drop:condenser"] != res2["pressure_drop:condenser"]


def test_changing_acc_ref_changes_acc_residual():
    scenario = build_fixed_single_loop_scenario()
    params1 = _default_params()
    params2 = FixedSingleLoopResidualParameters(
        pump_pressure_rise=_PUMP_RISE,
        evaporator_pressure_drop=_EVAP_DROP,
        condenser_pressure_drop=_COND_DROP,
        accumulator_pressure_reference=_P_REF + 5000.0,
    )
    uv = _consistent_unknowns()  # P_n_acc_out = _P_REF (consistent for params1)
    res1 = _evaluate(build_fixed_single_loop_physical_residuals(scenario, params1), uv)
    res2 = _evaluate(build_fixed_single_loop_physical_residuals(scenario, params2), uv)
    assert res1["pressure_drop:accumulator"] != res2["pressure_drop:accumulator"]


def test_uniform_mass_flow_change_leaves_pressure_residuals_at_zero():
    assembly = _default_assembly()
    # At consistent pressures, any uniform mass flow satisfies both pressure and
    # mass-balance residuals.
    uv_high = _consistent_unknowns(mdot=5.0)
    residuals = _evaluate(assembly, uv_high)
    for pres_name in [
        "pressure_drop:accumulator",
        "pressure_drop:pump",
        "pressure_drop:evaporator",
        "pressure_drop:condenser",
    ]:
        assert abs(residuals[pres_name]) < 1e-9, f"{pres_name} = {residuals[pres_name]}"


# ---------------------------------------------------------------------------
# Group 8: Convenience wrapper
# ---------------------------------------------------------------------------


def test_convenience_wrapper_returns_component_contribution():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    pump_cid = assembly.scenario.component_ids.pump
    result = build_component_contribution_from_fixed_single_loop_residuals(pump_cid, assembly, uv)
    assert isinstance(result, ComponentContribution)


def test_convenience_wrapper_pump_correct_values_at_consistent_point():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    pump_cid = assembly.scenario.component_ids.pump
    result = build_component_contribution_from_fixed_single_loop_residuals(pump_cid, assembly, uv)
    rn = assembly.scenario.residual_names
    assert abs(result.residual_values[rn.mass_balance_n_acc_out]) < 1e-9
    assert abs(result.residual_values[rn.pressure_drop_pump]) < 1e-9


def test_convenience_wrapper_rejects_wrong_component_id_type():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    with pytest.raises(TypeError, match="ComponentInstanceId"):
        build_component_contribution_from_fixed_single_loop_residuals(
            "pump", assembly, uv  # type: ignore[arg-type]
        )


def test_convenience_wrapper_rejects_wrong_assembly_type():
    uv = _consistent_unknowns()
    pump_cid = ComponentInstanceId("pump")
    with pytest.raises(TypeError, match="FixedSingleLoopPhysicalResidualAssembly"):
        build_component_contribution_from_fixed_single_loop_residuals(
            pump_cid, "not_an_assembly", uv  # type: ignore[arg-type]
        )


def test_convenience_wrapper_rejects_wrong_unknown_values_type():
    assembly = _default_assembly()
    pump_cid = assembly.scenario.component_ids.pump
    with pytest.raises(TypeError, match="Mapping"):
        build_component_contribution_from_fixed_single_loop_residuals(
            pump_cid, assembly, [1.0, 2.0]  # type: ignore[arg-type]
        )


def test_convenience_wrapper_rejects_unknown_component_id():
    assembly = _default_assembly()
    uv = _consistent_unknowns()
    alien_cid = ComponentInstanceId("alien_component")
    with pytest.raises(ValueError, match="no adapter"):
        build_component_contribution_from_fixed_single_loop_residuals(alien_cid, assembly, uv)


# ---------------------------------------------------------------------------
# Group 9: Residual ordering and determinism
# ---------------------------------------------------------------------------


def test_adapter_ordering_deterministic_across_two_builds():
    scenario = build_fixed_single_loop_scenario()
    params = _default_params()
    a1 = build_fixed_single_loop_physical_residuals(scenario, params)
    a2 = build_fixed_single_loop_physical_residuals(scenario, params)
    ids1 = [a.instance_id.value for a in a1.adapter_set.adapters]
    ids2 = [a.instance_id.value for a in a2.adapter_set.adapters]
    assert ids1 == ids2


def test_evaluation_produces_eight_residuals():
    assembly = _default_assembly()
    residuals = _evaluate(assembly, _consistent_unknowns())
    assert len(residuals) == 8


def test_evaluation_ordering_matches_scenario_residual_names():
    """Residuals from evaluate_network_residuals appear in assembly declaration order."""
    assembly = _default_assembly()
    physical_adapter_set = build_physical_adapters_from_contributions(
        assembly.scenario.binding_context,
        assembly.adapter_set,
    )
    evaluators = build_network_residual_evaluators(
        assembly.scenario.assembly,
        physical_adapter_set,
    )
    scales = {name: 1.0 for name in assembly.scenario.assembly.residuals.names()}
    result = evaluate_network_residuals(
        assembly=assembly.scenario.assembly,
        unknown_values=NetworkUnknownValues(_consistent_unknowns()),
        evaluators=evaluators,
        scales=scales,
    )
    declared_order = list(assembly.scenario.assembly.residuals.names())
    evaluated_order = [ev.spec.name for ev in result.evaluations]
    assert evaluated_order == declared_order


# ---------------------------------------------------------------------------
# Group 10: Boundary tests — AST / import-level
# ---------------------------------------------------------------------------


def test_residuals_module_no_coolprop_import():
    tree = _parse_ast(_RESIDUALS_MODULE)
    assert not _has_import(tree, "CoolProp")


def test_residuals_module_no_property_backend_import():
    tree = _parse_ast(_RESIDUALS_MODULE)
    assert not _has_import(tree, "PropertyBackend")


def test_residuals_module_no_correlation_registry_import():
    tree = _parse_ast(_RESIDUALS_MODULE)
    assert not _has_import(tree, "CorrelationRegistry")


def test_residuals_module_no_hx_models_import():
    tree = _parse_ast(_RESIDUALS_MODULE)
    assert not _has_import(tree, "hx_models")


def test_residuals_module_no_system_state_import():
    tree = _parse_ast(_RESIDUALS_MODULE)
    assert not _has_import(tree, "SystemState")


def test_residuals_module_no_fluid_state_import():
    tree = _parse_ast(_RESIDUALS_MODULE)
    assert not _has_import(tree, "FluidState")


def test_residuals_module_no_mpl_sim_components_import():
    tree = _parse_ast(_RESIDUALS_MODULE)
    assert not _has_import(tree, "mpl_sim.components")


def test_residuals_module_no_mpl_sim_properties_import():
    tree = _parse_ast(_RESIDUALS_MODULE)
    assert not _has_import(tree, "mpl_sim.properties")


def test_residuals_module_no_contribute_attribute_calls():
    tree = _parse_ast(_RESIDUALS_MODULE)
    assert not _has_contribute_attribute_call(tree)


def test_residuals_module_no_solve_network_pattern():
    """No .solve() or bare solve() call appears as executable AST in the module."""
    tree = _parse_ast(_RESIDUALS_MODULE)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "solve":
                pytest.fail("Found .solve() attribute call in residuals module")
            if isinstance(func, ast.Name) and func.id == "solve":
                pytest.fail("Found bare solve() call in residuals module")


def test_this_file_no_coolprop_import():
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(tree, "CoolProp")


def test_this_file_no_property_backend_import():
    tree = _parse_ast(_THIS_FILE)
    assert not _has_import(tree, "PropertyBackend")


def test_this_file_no_contribute_attribute_calls():
    tree = _parse_ast(_THIS_FILE)
    assert not _has_contribute_attribute_call(tree)


# ---------------------------------------------------------------------------
# Group 11: Production contract regression
# ---------------------------------------------------------------------------


def _get_contract_statuses() -> dict[str, str]:
    results = inspect_known_production_component_contracts()
    return {r.class_name: r.status for r in results}


def test_component_no_contribute_method():
    statuses = _get_contract_statuses()
    assert statuses.get("Component") == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_pipe_no_contribute_method():
    statuses = _get_contract_statuses()
    assert statuses.get("Pipe") == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_pump_component_no_contribute_method():
    statuses = _get_contract_statuses()
    assert statuses.get("PumpComponent") == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD


def test_accumulator_component_no_contribute_method():
    statuses = _get_contract_statuses()
    expected = ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
    assert statuses.get("AccumulatorComponent") == expected


def test_evaporator_component_no_contribute_method():
    statuses = _get_contract_statuses()
    expected = ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
    assert statuses.get("EvaporatorComponent") == expected


def test_condenser_component_no_contribute_method():
    statuses = _get_contract_statuses()
    assert (
        statuses.get("CondenserComponent") == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
    )


# ---------------------------------------------------------------------------
# Group 12: Public API
# ---------------------------------------------------------------------------

_EXPECTED_15B2_SYMBOLS = {
    "FixedSingleLoopResidualParameters",
    "FixedSingleLoopPhysicalResidualAssembly",
    "build_fixed_single_loop_physical_residuals",
    "build_component_contribution_from_fixed_single_loop_residuals",
}


def test_new_symbols_exported_from_mpl_sim_network():
    import mpl_sim.network as net

    for symbol in _EXPECTED_15B2_SYMBOLS:
        assert hasattr(net, symbol), f"mpl_sim.network missing symbol: {symbol!r}"


def test_new_symbols_in_all_list():
    import mpl_sim.network as net

    for symbol in _EXPECTED_15B2_SYMBOLS:
        assert symbol in net.__all__, f"mpl_sim.network.__all__ missing: {symbol!r}"


def test_no_private_symbols_in_all():
    import mpl_sim.network as net

    for name in net.__all__:
        assert not name.startswith("_"), f"private symbol in __all__: {name!r}"
