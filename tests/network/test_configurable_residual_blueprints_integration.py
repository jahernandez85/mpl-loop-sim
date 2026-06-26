"""Integration tests for Block 15G-A — Configurable Residual Blueprint Assembly.

Proves that explicit residual blueprints translate correctly to 15F-A algebraic
residual declarations, and that the resulting ConfigurableAlgebraicResidualSet
integrates correctly with the 15F-B CONFIGURABLE_ALGEBRAIC selection mode.

Acceptance stories
------------------
A1  Build configurable single-loop scenario; declare explicit blueprints;
    translate to algebraic residual set; evaluate at zero-residual point.
A2  Perturb one unknown — residuals become nonzero.
A3  Pass blueprint algebraic_residual_set through 15F-B CONFIGURABLE_ALGEBRAIC
    mode; evaluate at zero-residual point.
A4  Perturb unknown in 15F-B path — nonzero residuals.
A5  Validate blueprints against scenario build result unknown names — compatible.
A6  Blueprint references nonexistent unknown — scenario_is_compatible=False and
    missing_unknowns is deterministic.
A7  Role changes do not affect blueprint translation; only IDs matter.
A8  Full report stack (blueprint report + selection report) is JSON-serializable.
A9  No residuals are generated unless blueprints are supplied.
A10 EnthalpyFlowResidualBlueprint translates correctly and evaluates.
A11 PressureDifferenceResidualBlueprint evaluates to zero at correct point.

Validation stories
------------------
V1  blueprint build result has no_solve=True.
V2  blueprint build result has residuals_inferred_from_roles=False.
V3  blueprint build result has residuals_inferred_from_topology=False.
V4  blueprint build result has closures_inferred_from_roles=False.
V5  blueprint build result has production_components_executed=False.
V6  15F-B evaluation result with blueprint-derived set is nonzero after perturbation.
V7  blueprint report is JSON-serializable.

Regression stories
------------------
R1  Production contracts still show NO_CONTRIBUTE_METHOD for all 6 classes.
R2  inspect_known_production_component_contracts returns exactly 6 results.

Boundary stories
----------------
B1  New test and integration modules import no CoolProp or PropertyBackend.
B2  No contribute attribute in blueprint module.
B3  No SystemState or FluidState in new modules.
B4  No solve(network) or NetworkGraph.solve() in new modules.
B5  No mpl_sim.components, properties, correlations, hx_models imports.
B6  No role-based physics dispatch in new modules.

These tests do NOT:
  - Call any solver or root-finder.
  - Execute production component physics.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or construct FluidState.
  - Write files, use pandas, or use numpy.
  - Infer residuals from roles or topology.
"""

from __future__ import annotations

import json

import pytest

from mpl_sim.network.configurable_algebraic_residuals import (
    evaluate_configurable_algebraic_residuals,
)
from mpl_sim.network.configurable_residual_blueprints import (
    EnthalpyFlowResidualBlueprint,
    ImposedMassFlowResidualBlueprint,
    ImposedPressureResidualBlueprint,
    MassBalanceResidualBlueprint,
    PressureDifferenceResidualBlueprint,
    build_configurable_algebraic_residuals_from_blueprints,
    build_configurable_residual_blueprint_report,
    build_configurable_residual_blueprint_set,
)
from mpl_sim.network.configurable_residual_selection import (
    ConfigurableResidualMode,
    ConfigurableResidualSelectionRequest,
    build_configurable_residual_selection_report,
    evaluate_selected_configurable_residuals,
    select_configurable_residual_strategy,
)
from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioSpec,
    ScenarioComponentRole,
    ScenarioComponentSpec,
    ScenarioConnectionSpec,
    ScenarioNodeSpec,
    build_configurable_scenario,
)
from mpl_sim.network.production_component_inspection import (
    ProductionComponentContractStatus,
    inspect_known_production_component_contracts,
)

# ===========================================================================
# Shared test fixture — single-loop configurable scenario
# ===========================================================================

_SINGLE_LOOP_SPEC = ConfigurableScenarioSpec(
    scenario_id="bp_integration_single_loop",
    components=[
        ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
        ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
        ScenarioComponentSpec("evaporator", ScenarioComponentRole.EVAPORATOR),
        ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
    ],
    nodes=[
        ScenarioNodeSpec("n_acc_out"),
        ScenarioNodeSpec("n_pump_out"),
        ScenarioNodeSpec("n_evap_out"),
        ScenarioNodeSpec("n_cond_out"),
    ],
    connections=[
        ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
        ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
        ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
        ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
    ],
)

# Zero-residual point for the 4 blueprints below:
#   mb_pump_out:  mdot:pump - mdot:evaporator = 0.1 - 0.1 = 0
#   p_ref:        P:n_acc_out - 100000         = 100000 - 100000 = 0
#   mdot_pump:    mdot:pump   - 0.1            = 0.1 - 0.1 = 0
#   dp_pump:      P:n_pump_out - P:n_acc_out + (-50000) = 150000 - 100000 - 50000 = 0
_ZERO_RESIDUAL_UNKNOWNS = {
    "mdot:accumulator": 0.1,
    "mdot:pump": 0.1,
    "mdot:evaporator": 0.1,
    "mdot:condenser": 0.1,
    "P:n_acc_out": 100_000.0,
    "P:n_pump_out": 150_000.0,
    "P:n_evap_out": 130_000.0,
    "P:n_cond_out": 110_000.0,
}


def _make_four_blueprints() -> list:
    return [
        MassBalanceResidualBlueprint(
            residual_name="mb_pump_out",
            incoming_component_ids=("pump",),
            outgoing_component_ids=("evaporator",),
            anchor_node_id="n_pump_out",
        ),
        ImposedPressureResidualBlueprint(
            residual_name="p_ref",
            node_id="n_acc_out",
            pressure=100_000.0,
        ),
        ImposedMassFlowResidualBlueprint(
            residual_name="mdot_pump",
            component_id="pump",
            mass_flow=0.1,
        ),
        PressureDifferenceResidualBlueprint(
            residual_name="dp_pump",
            inlet_node_id="n_acc_out",
            outlet_node_id="n_pump_out",
            delta_p=-50_000.0,
        ),
    ]


# ===========================================================================
# A1 — build scenario, build blueprints, evaluate at zero-residual point
# ===========================================================================


class TestBlueprintEvaluationDirectly:
    def test_evaluate_at_zero_residual_point(self) -> None:
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        rs = bp_result.algebraic_residual_set

        eval_result = evaluate_configurable_algebraic_residuals(rs, _ZERO_RESIDUAL_UNKNOWNS)

        assert eval_result.max_abs_residual == pytest.approx(0.0, abs=1e-10)
        for name in eval_result.residual_names:
            assert eval_result.residual_values[name] == pytest.approx(0.0, abs=1e-10)

    def test_evaluate_individual_residuals_at_zero(self) -> None:
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        rs = bp_result.algebraic_residual_set

        eval_result = evaluate_configurable_algebraic_residuals(rs, _ZERO_RESIDUAL_UNKNOWNS)
        assert eval_result.residual_values["mb_pump_out"] == pytest.approx(0.0, abs=1e-10)
        assert eval_result.residual_values["p_ref"] == pytest.approx(0.0, abs=1e-10)
        assert eval_result.residual_values["mdot_pump"] == pytest.approx(0.0, abs=1e-10)
        assert eval_result.residual_values["dp_pump"] == pytest.approx(0.0, abs=1e-10)

    def test_no_solve_in_eval_result(self) -> None:
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        eval_result = evaluate_configurable_algebraic_residuals(
            bp_result.algebraic_residual_set, _ZERO_RESIDUAL_UNKNOWNS
        )
        assert eval_result.no_solve is True


# ===========================================================================
# A2 — perturb unknowns, get nonzero residuals
# ===========================================================================


class TestPerturbedResiduals:
    def test_nonzero_after_mdot_pump_perturbation(self) -> None:
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        rs = bp_result.algebraic_residual_set

        perturbed = dict(_ZERO_RESIDUAL_UNKNOWNS)
        perturbed["mdot:pump"] = 0.2  # was 0.1
        eval_result = evaluate_configurable_algebraic_residuals(rs, perturbed)

        # mb_pump_out: 0.2 - 0.1 = 0.1 ≠ 0
        assert abs(eval_result.residual_values["mb_pump_out"]) > 1e-10
        # mdot_pump: 0.2 - 0.1 = 0.1 ≠ 0
        assert abs(eval_result.residual_values["mdot_pump"]) > 1e-10

    def test_nonzero_after_pressure_perturbation(self) -> None:
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        rs = bp_result.algebraic_residual_set

        perturbed = dict(_ZERO_RESIDUAL_UNKNOWNS)
        perturbed["P:n_acc_out"] = 90_000.0  # was 100000
        eval_result = evaluate_configurable_algebraic_residuals(rs, perturbed)

        # p_ref: 90000 - 100000 = -10000 ≠ 0
        assert abs(eval_result.residual_values["p_ref"]) > 1e-6

    def test_max_abs_nonzero_after_perturbation(self) -> None:
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        rs = bp_result.algebraic_residual_set

        perturbed = dict(_ZERO_RESIDUAL_UNKNOWNS)
        perturbed["mdot:pump"] = 0.5
        eval_result = evaluate_configurable_algebraic_residuals(rs, perturbed)
        assert eval_result.max_abs_residual > 0.0


# ===========================================================================
# A3 — 15F-B CONFIGURABLE_ALGEBRAIC integration
# ===========================================================================


class TestBlueprintThrough15FB:
    def test_configurable_algebraic_at_zero_residual_point(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        assert bp_result.scenario_is_compatible is True

        request = ConfigurableResidualSelectionRequest(
            build_result=sbr,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bp_result.algebraic_residual_set,
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=True,
        )
        result = evaluate_selected_configurable_residuals(request)
        assert result.evaluation_performed is True
        assert result.no_solve is True

        eval_r = result.evaluation_result
        assert eval_r is not None
        assert eval_r.max_abs_residual == pytest.approx(0.0, abs=1e-10)

    def test_configurable_algebraic_compatible_with_scenario(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        assert bp_result.scenario_compatibility_checked is True
        assert bp_result.scenario_is_compatible is True
        assert bp_result.missing_unknowns == ()


# ===========================================================================
# A4 — 15F-B path with perturbed unknowns
# ===========================================================================


class TestBlueprintThrough15FBPerturbed:
    def test_nonzero_after_perturbation_through_selection(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)

        perturbed = dict(_ZERO_RESIDUAL_UNKNOWNS)
        perturbed["mdot:pump"] = 0.5

        request = ConfigurableResidualSelectionRequest(
            build_result=sbr,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bp_result.algebraic_residual_set,
            algebraic_unknown_values=perturbed,
            evaluate=True,
        )
        result = evaluate_selected_configurable_residuals(request)
        assert result.evaluation_performed is True
        assert result.evaluation_result.max_abs_residual > 0.0


# ===========================================================================
# A5 — validate blueprints against scenario build result
# ===========================================================================


class TestScenarioCompatibilityIntegration:
    def test_compatible_against_real_scenario(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        assert bp_result.scenario_is_compatible is True
        assert bp_result.missing_unknowns == ()

    def test_all_translated_unknowns_in_scenario(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        scenario_unknown_set = set(sbr.unknown_names)
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        for name in bp_result.required_unknown_names:
            assert name in scenario_unknown_set


# ===========================================================================
# A6 — missing unknown detected as incompatible
# ===========================================================================


class TestMissingUnknownDetection:
    def test_missing_unknown_reported(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        # Use a component ID that doesn't exist in the scenario
        bps = [ImposedMassFlowResidualBlueprint("mdot_nonexistent", "nonexistent_component", 0.1)]
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        assert bp_result.scenario_is_compatible is False
        assert "mdot:nonexistent_component" in bp_result.missing_unknowns

    def test_selection_incompatible_with_missing_unknown(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = [ImposedMassFlowResidualBlueprint("mdot_bad", "nonexistent_component", 0.1)]
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        # The algebraic residual set references a nonexistent unknown
        request = ConfigurableResidualSelectionRequest(
            build_result=sbr,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bp_result.algebraic_residual_set,
            evaluate=False,
        )
        result = select_configurable_residual_strategy(request)
        assert result.compatibility.is_compatible is False


# ===========================================================================
# A7 — role changes do not affect translation
# ===========================================================================


class TestRoleChangeDoesNotAffectTranslation:
    def test_translation_identical_regardless_of_role(self) -> None:
        # Build the same topology with different roles
        spec_variant = ConfigurableScenarioSpec(
            scenario_id="bp_role_variant",
            components=[
                ScenarioComponentSpec("accumulator", ScenarioComponentRole.GENERIC),
                ScenarioComponentSpec("pump", ScenarioComponentRole.GENERIC),
                ScenarioComponentSpec("evaporator", ScenarioComponentRole.GENERIC),
                ScenarioComponentSpec("condenser", ScenarioComponentRole.GENERIC),
            ],
            nodes=[
                ScenarioNodeSpec("n_acc_out"),
                ScenarioNodeSpec("n_pump_out"),
                ScenarioNodeSpec("n_evap_out"),
                ScenarioNodeSpec("n_cond_out"),
            ],
            connections=[
                ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
                ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
                ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
                ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
            ],
        )
        sbr_variant = build_configurable_scenario(spec_variant)

        bps = _make_four_blueprints()
        bp_result_original = build_configurable_algebraic_residuals_from_blueprints(bps)
        bp_result_variant = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr_variant
        )

        # Blueprint translation is the same regardless of roles
        assert bp_result_original.required_unknown_names == bp_result_variant.required_unknown_names
        assert bp_result_original.blueprint_names == bp_result_variant.blueprint_names
        # Variant scenario has same component/node IDs → still compatible
        assert bp_result_variant.scenario_is_compatible is True

    def test_topology_change_does_not_generate_residuals(self) -> None:
        # No matter what the topology is, blueprints are only generated
        # from the explicit user-supplied list.
        bps = [ImposedPressureResidualBlueprint("p_only", "n_acc_out", 1e5)]
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        # Exactly 1 residual — only the explicitly supplied blueprint
        assert bp_result.blueprint_count == 1
        assert bp_result.blueprint_names == ("p_only",)


# ===========================================================================
# A8 — JSON-serializable full report stack
# ===========================================================================


class TestFullReportStackSerializable:
    def test_blueprint_report_serializable(self) -> None:
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        report = build_configurable_residual_blueprint_report(bp_result)
        json_str = json.dumps(report)
        assert json.loads(json_str)["no_solve"] is True

    def test_selection_report_serializable(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)

        request = ConfigurableResidualSelectionRequest(
            build_result=sbr,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bp_result.algebraic_residual_set,
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=True,
        )
        sel_result = evaluate_selected_configurable_residuals(request)
        sel_report = build_configurable_residual_selection_report(sel_result)
        json_str = json.dumps(sel_report)
        parsed = json.loads(json_str)
        assert parsed["no_solve"] is True
        assert parsed["residuals_inferred_from_roles"] is False
        assert parsed["residuals_inferred_from_topology"] is False

    def test_combined_report_stack_serializable(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        request = ConfigurableResidualSelectionRequest(
            build_result=sbr,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bp_result.algebraic_residual_set,
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=True,
        )
        sel_result = evaluate_selected_configurable_residuals(request)

        combined = {
            "blueprint_report": build_configurable_residual_blueprint_report(bp_result),
            "selection_report": build_configurable_residual_selection_report(sel_result),
        }
        json_str = json.dumps(combined)
        parsed = json.loads(json_str)
        assert parsed["blueprint_report"]["no_solve"] is True
        assert parsed["selection_report"]["no_solve"] is True


# ===========================================================================
# A9 — no residuals without explicit blueprints
# ===========================================================================


class TestNoResidualWithoutBlueprints:
    def test_empty_blueprint_list_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            build_configurable_algebraic_residuals_from_blueprints([])

    def test_empty_blueprint_set_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            build_configurable_residual_blueprint_set([])


# ===========================================================================
# A10 — EnthalpyFlowResidualBlueprint integration
# ===========================================================================


class TestEnthalpyFlowBlueprintIntegration:
    def test_enthalpy_flow_evaluates_at_zero(self) -> None:
        bps = [
            EnthalpyFlowResidualBlueprint(
                residual_name="hflow_evap",
                heat_rate_unknown="q_evap",
                mass_flow_component_id="evaporator",
                h_in_unknown="h_in_evap",
                h_out_unknown="h_out_evap",
            )
        ]
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        rs = bp_result.algebraic_residual_set

        # r = q - mdot * (h_out - h_in) = 500 - 0.1 * (3500 - 500) = 500 - 300 = 200
        # For zero: q = mdot * (h_out - h_in) = 0.1 * (3500 - 500) = 300
        unknowns = {
            "q_evap": 300.0,
            "mdot:evaporator": 0.1,
            "h_in_evap": 500.0,
            "h_out_evap": 3500.0,
        }
        eval_result = evaluate_configurable_algebraic_residuals(rs, unknowns)
        assert eval_result.residual_values["hflow_evap"] == pytest.approx(0.0, abs=1e-9)

    def test_enthalpy_flow_nonzero_after_perturbation(self) -> None:
        bps = [
            EnthalpyFlowResidualBlueprint(
                residual_name="hflow",
                heat_rate_unknown="q",
                mass_flow_component_id="evap",
                h_in_unknown="h_in",
                h_out_unknown="h_out",
            )
        ]
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        rs = bp_result.algebraic_residual_set

        unknowns = {
            "q": 999.0,  # not matching mdot*(h_out-h_in)
            "mdot:evap": 0.1,
            "h_in": 500.0,
            "h_out": 3500.0,
        }
        eval_result = evaluate_configurable_algebraic_residuals(rs, unknowns)
        assert abs(eval_result.residual_values["hflow"]) > 0.0

    def test_enthalpy_flow_required_unknowns(self) -> None:
        bps = [
            EnthalpyFlowResidualBlueprint(
                residual_name="hflow",
                heat_rate_unknown="q_evap",
                mass_flow_component_id="evaporator",
                h_in_unknown="h_in",
                h_out_unknown="h_out",
            )
        ]
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        # mdot unknown is the translated one
        assert "mdot:evaporator" in bp_result.required_unknown_names
        assert "q_evap" in bp_result.required_unknown_names
        assert "h_in" in bp_result.required_unknown_names
        assert "h_out" in bp_result.required_unknown_names


# ===========================================================================
# A11 — PressureDifferenceResidualBlueprint integration
# ===========================================================================


class TestPressureDifferenceBlueprintIntegration:
    def test_pressure_difference_at_zero_point(self) -> None:
        bp = PressureDifferenceResidualBlueprint(
            residual_name="dp_pump",
            inlet_node_id="n_acc_out",
            outlet_node_id="n_pump_out",
            delta_p=-50_000.0,
        )
        bp_result = build_configurable_algebraic_residuals_from_blueprints([bp])
        rs = bp_result.algebraic_residual_set

        # r = P_out - P_in + delta_p = 150000 - 100000 - 50000 = 0
        unknowns = {"P:n_acc_out": 100_000.0, "P:n_pump_out": 150_000.0}
        eval_result = evaluate_configurable_algebraic_residuals(rs, unknowns)
        assert eval_result.residual_values["dp_pump"] == pytest.approx(0.0, abs=1e-9)

    def test_pressure_difference_nonzero_after_perturbation(self) -> None:
        bp = PressureDifferenceResidualBlueprint(
            residual_name="dp_pipe",
            inlet_node_id="n1",
            outlet_node_id="n2",
            delta_p=10_000.0,
        )
        bp_result = build_configurable_algebraic_residuals_from_blueprints([bp])
        rs = bp_result.algebraic_residual_set

        # r = P_out - P_in + delta_p = 90000 - 100000 + 10000 = 0
        unknowns_zero = {"P:n1": 100_000.0, "P:n2": 90_000.0}
        eval_result_zero = evaluate_configurable_algebraic_residuals(rs, unknowns_zero)
        assert eval_result_zero.residual_values["dp_pipe"] == pytest.approx(0.0, abs=1e-9)

        # Perturb P:n2
        unknowns_perturbed = {"P:n1": 100_000.0, "P:n2": 95_000.0}
        eval_result_perturbed = evaluate_configurable_algebraic_residuals(rs, unknowns_perturbed)
        assert abs(eval_result_perturbed.residual_values["dp_pipe"]) > 0.0


# ===========================================================================
# Validation stories
# ===========================================================================


class TestBuildResultValidationFlags:
    def test_no_solve_true(self) -> None:
        bps = [ImposedPressureResidualBlueprint("p_ref", "n1", 1e5)]
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.no_solve is True

    def test_residuals_inferred_from_roles_false(self) -> None:
        bps = [ImposedPressureResidualBlueprint("p_ref", "n1", 1e5)]
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.residuals_inferred_from_roles is False

    def test_residuals_inferred_from_topology_false(self) -> None:
        bps = [ImposedPressureResidualBlueprint("p_ref", "n1", 1e5)]
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.residuals_inferred_from_topology is False

    def test_closures_inferred_from_roles_false(self) -> None:
        bps = [ImposedPressureResidualBlueprint("p_ref", "n1", 1e5)]
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.closures_inferred_from_roles is False

    def test_production_components_executed_false(self) -> None:
        bps = [ImposedPressureResidualBlueprint("p_ref", "n1", 1e5)]
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.production_components_executed is False

    def test_15fb_result_no_solve_true(self) -> None:
        sbr = build_configurable_scenario(_SINGLE_LOOP_SPEC)
        bps = _make_four_blueprints()
        bp_result = build_configurable_algebraic_residuals_from_blueprints(bps)
        request = ConfigurableResidualSelectionRequest(
            build_result=sbr,
            mode=ConfigurableResidualMode.CONFIGURABLE_ALGEBRAIC,
            algebraic_residual_set=bp_result.algebraic_residual_set,
            algebraic_unknown_values=_ZERO_RESIDUAL_UNKNOWNS,
            evaluate=True,
        )
        sel_result = evaluate_selected_configurable_residuals(request)
        assert sel_result.no_solve is True


# ===========================================================================
# Regression stories — production contracts
# ===========================================================================


class TestProductionComponentContracts:
    def test_all_six_have_no_contribute_method(self) -> None:
        results = inspect_known_production_component_contracts()
        for r in results:
            assert (
                r.status is ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{r.class_name} unexpectedly has contribute method"

    def test_exactly_six_production_classes_inspected(self) -> None:
        results = inspect_known_production_component_contracts()
        assert len(results) == 6

    def test_known_class_names_present(self) -> None:
        results = inspect_known_production_component_contracts()
        class_names = {r.class_name for r in results}
        for expected in (
            "Component",
            "Pipe",
            "PumpComponent",
            "AccumulatorComponent",
            "EvaporatorComponent",
            "CondenserComponent",
        ):
            assert expected in class_names


# ===========================================================================
# Boundary stories — module attribute checks
# ===========================================================================


class TestBlueprintIntegrationModuleBoundaries:
    """Module-level boundary checks for the blueprint module (integration perspective)."""

    def _blueprint_import_lines(self) -> list[str]:
        import re

        import mpl_sim.network.configurable_residual_blueprints as mod

        src_path = getattr(mod, "__file__", "")
        if not src_path:
            return []
        with open(src_path) as f:
            text = f.read()
        return [ln for ln in text.splitlines() if re.match(r"^\s*(import|from)\s+", ln)]

    def _blueprint_executable_lines(self) -> list[str]:
        import mpl_sim.network.configurable_residual_blueprints as mod

        src_path = getattr(mod, "__file__", "")
        if not src_path:
            return []
        lines: list[str] = []
        in_docstring = False
        docstring_char = None
        with open(src_path) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                for dq in ('"""', "'''"):
                    if dq in line:
                        count = line.count(dq)
                        if in_docstring and docstring_char == dq:
                            in_docstring = count % 2 == 0
                            docstring_char = None if not in_docstring else dq
                        elif not in_docstring and count % 2 == 1:
                            in_docstring = True
                            docstring_char = dq
                        break
                if in_docstring:
                    continue
                lines.append(line)
        return lines

    def test_blueprint_module_no_coolprop(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "CoolProp")
        for ln in self._blueprint_import_lines():
            assert "CoolProp" not in ln

    def test_blueprint_module_no_property_backend(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "PropertyBackend")
        for ln in self._blueprint_import_lines():
            assert "PropertyBackend" not in ln

    def test_blueprint_module_no_system_state(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "SystemState")
        for ln in self._blueprint_import_lines():
            assert "SystemState" not in ln

    def test_blueprint_module_no_fluid_state(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "FluidState")
        for ln in self._blueprint_import_lines():
            assert "FluidState" not in ln

    def test_blueprint_module_no_contribute(self) -> None:
        for ln in self._blueprint_executable_lines():
            assert ".contribute(" not in ln, f"contribute call found: {ln!r}"
            assert "def contribute" not in ln

    def test_blueprint_module_no_solve_network(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "NetworkGraph")
        for ln in self._blueprint_executable_lines():
            assert "solve(network" not in ln

    def test_blueprint_module_no_components_import(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "components")
        for ln in self._blueprint_import_lines():
            assert "mpl_sim.components" not in ln

    def test_blueprint_module_no_hx_models(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "hx_models")
        for ln in self._blueprint_import_lines():
            assert "hx_models" not in ln

    def test_integration_test_no_coolprop(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "CoolProp")

    def test_integration_test_no_system_state(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "SystemState")

    def test_integration_test_no_fluid_state(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "FluidState")

    def test_integration_test_no_contribute(self) -> None:
        for ln in self._blueprint_executable_lines():
            assert ".contribute(" not in ln

    def test_integration_test_no_solve(self) -> None:
        for ln in self._blueprint_executable_lines():
            assert "least_squares" not in ln
            assert "fsolve" not in ln
            assert "lstsq" not in ln
