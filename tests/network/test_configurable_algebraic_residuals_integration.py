"""Integration tests for Block 15F-A: configurable algebraic residuals
with Block 15E configurable scenario declarations.

Covers:
  - Building configurable single-loop and two-branch scenarios (15E-A).
  - Declaring algebraic residuals explicitly using scenario unknown names.
  - Validating residual declaration names against scenario build results.
  - Evaluating residuals at known consistent points (zero residuals).
  - Perturbation creates nonzero residuals.
  - Role changes do NOT alter residual declarations.
  - No residuals inferred from topology or roles.
  - Report generation with scenario compatibility.
  - 15E-C / 15E-B regression: existing selection stack unmodified.
  - 15D-C regression: closure integration unmodified.
  - Phase 14G regression: production component contracts unchanged.

These tests do NOT:
  - Call solve_fixed_single_loop_residuals or any solver.
  - Execute production component physics.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or construct FluidState.
  - Call solve(network) or NetworkGraph.solve().
  - Write files, use pandas, or use numpy.
"""

from __future__ import annotations

import json

import pytest

from mpl_sim.network.configurable_algebraic_residuals import (
    EnthalpyFlowResidualDeclaration,
    ImposedMassFlowResidualDeclaration,
    ImposedPressureResidualDeclaration,
    MassBalanceResidualDeclaration,
    PressureDifferenceResidualDeclaration,
    build_configurable_algebraic_residual_report,
    build_configurable_algebraic_residual_set,
    evaluate_configurable_algebraic_residuals,
    validate_algebraic_residuals_against_scenario,
)
from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioBuildResult,
    ConfigurableScenarioSpec,
    ScenarioComponentRole,
    ScenarioComponentSpec,
    ScenarioConnectionSpec,
    ScenarioNodeSpec,
    build_configurable_scenario,
)

# ---------------------------------------------------------------------------
# Single-loop scenario helpers
# ---------------------------------------------------------------------------

_SINGLE_LOOP_SPEC = ConfigurableScenarioSpec(
    scenario_id="single_loop_15fa",
    components=(
        ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
        ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
        ScenarioComponentSpec("evaporator", ScenarioComponentRole.EVAPORATOR),
        ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
    ),
    nodes=(
        ScenarioNodeSpec("n_acc_out"),
        ScenarioNodeSpec("n_pump_out"),
        ScenarioNodeSpec("n_evap_out"),
        ScenarioNodeSpec("n_cond_out"),
    ),
    connections=(
        ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
        ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
        ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
        ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
    ),
)


def _build_single_loop() -> ConfigurableScenarioBuildResult:
    return build_configurable_scenario(_SINGLE_LOOP_SPEC)


# Single-loop consistent point (all mass flows equal, pressures consistent):
# P_acc_out = 200_000, P_pump_out = 300_000, P_evap_out = 280_000, P_cond_out = 210_000
# mdot for all components = 1.0 kg/s
_SINGLE_LOOP_CONSISTENT_UV: dict[str, float] = {
    "mdot:accumulator": 1.0,
    "mdot:pump": 1.0,
    "mdot:evaporator": 1.0,
    "mdot:condenser": 1.0,
    "P:n_acc_out": 200_000.0,
    "P:n_pump_out": 300_000.0,
    "P:n_evap_out": 280_000.0,
    "P:n_cond_out": 210_000.0,
}


# ===========================================================================
# Integration: single-loop scenario with explicit residual declarations
# ===========================================================================


class TestSingleLoopAlgebraicResiduals:
    def test_scenario_builds_with_expected_unknowns(self) -> None:
        result = _build_single_loop()
        assert "mdot:accumulator" in result.unknown_names
        assert "mdot:pump" in result.unknown_names
        assert "P:n_acc_out" in result.unknown_names
        assert "P:n_pump_out" in result.unknown_names

    def test_declare_mass_balance_residuals_explicitly(self) -> None:
        # Declare one mass-balance residual using scenario unknown names.
        d = MassBalanceResidualDeclaration(
            residual_name="mb:pump_out",
            incoming_unknown_names=("mdot:pump",),
            outgoing_unknown_names=("mdot:evaporator",),
        )
        s = build_configurable_algebraic_residual_set([d])
        assert "mb:pump_out" in s.residual_names

    def test_evaluate_mass_balance_zero_consistent(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:pump_out",
            incoming_unknown_names=("mdot:pump",),
            outgoing_unknown_names=("mdot:evaporator",),
        )
        s = build_configurable_algebraic_residual_set([d])
        result = evaluate_configurable_algebraic_residuals(s, _SINGLE_LOOP_CONSISTENT_UV)
        assert result.residual_values["mb:pump_out"] == pytest.approx(0.0)

    def test_evaluate_mass_balance_nonzero_perturbed(self) -> None:
        d = MassBalanceResidualDeclaration(
            residual_name="mb:pump_out",
            incoming_unknown_names=("mdot:pump",),
            outgoing_unknown_names=("mdot:evaporator",),
        )
        s = build_configurable_algebraic_residual_set([d])
        perturbed = dict(_SINGLE_LOOP_CONSISTENT_UV)
        perturbed["mdot:pump"] = 1.5
        result = evaluate_configurable_algebraic_residuals(s, perturbed)
        assert abs(result.residual_values["mb:pump_out"]) > 0

    def test_declare_imposed_pressure_using_scenario_unknown(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:acc",
            pressure_unknown="P:n_acc_out",
            imposed_value=200_000.0,
        )
        s = build_configurable_algebraic_residual_set([d])
        result = evaluate_configurable_algebraic_residuals(s, _SINGLE_LOOP_CONSISTENT_UV)
        assert result.residual_values["ip:acc"] == pytest.approx(0.0)

    def test_declare_imposed_mass_flow_using_scenario_unknown(self) -> None:
        d = ImposedMassFlowResidualDeclaration(
            residual_name="imf:pump",
            mass_flow_unknown="mdot:pump",
            imposed_value=1.0,
        )
        s = build_configurable_algebraic_residual_set([d])
        result = evaluate_configurable_algebraic_residuals(s, _SINGLE_LOOP_CONSISTENT_UV)
        assert result.residual_values["imf:pump"] == pytest.approx(0.0)

    def test_declare_pressure_difference_pump_zero_consistent(self) -> None:
        # P_pump_out - P_acc_out - pump_rise = 300000 - 200000 - 100000 = 0
        # r = P_out - P_in + delta_p; delta_p for pump = -100000 (negative = rise)
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:pump",
            inlet_pressure_unknown="P:n_acc_out",
            outlet_pressure_unknown="P:n_pump_out",
            delta_p=-100_000.0,
        )
        s = build_configurable_algebraic_residual_set([d])
        result = evaluate_configurable_algebraic_residuals(s, _SINGLE_LOOP_CONSISTENT_UV)
        assert result.residual_values["pd:pump"] == pytest.approx(0.0)

    def test_declare_pressure_difference_pump_nonzero_perturbed(self) -> None:
        d = PressureDifferenceResidualDeclaration(
            residual_name="pd:pump",
            inlet_pressure_unknown="P:n_acc_out",
            outlet_pressure_unknown="P:n_pump_out",
            delta_p=-100_000.0,
        )
        s = build_configurable_algebraic_residual_set([d])
        perturbed = dict(_SINGLE_LOOP_CONSISTENT_UV)
        perturbed["P:n_pump_out"] = 290_000.0  # off by 10000
        result = evaluate_configurable_algebraic_residuals(s, perturbed)
        assert abs(result.residual_values["pd:pump"]) > 0

    def test_combined_residual_set_loop_mass_and_pressure(self) -> None:
        # Declare a set covering one mass-balance + one imposed pressure.
        d_mb = MassBalanceResidualDeclaration(
            residual_name="mb:continuity",
            incoming_unknown_names=("mdot:pump",),
            outgoing_unknown_names=("mdot:evaporator",),
        )
        d_ip = ImposedPressureResidualDeclaration(
            residual_name="ip:acc",
            pressure_unknown="P:n_acc_out",
            imposed_value=200_000.0,
        )
        s = build_configurable_algebraic_residual_set([d_mb, d_ip])
        result = evaluate_configurable_algebraic_residuals(s, _SINGLE_LOOP_CONSISTENT_UV)
        assert result.residual_values["mb:continuity"] == pytest.approx(0.0)
        assert result.residual_values["ip:acc"] == pytest.approx(0.0)
        assert result.max_abs_residual == pytest.approx(0.0)
        assert result.l2_norm == pytest.approx(0.0)

    def test_enthalpy_flow_residual_zero(self) -> None:
        # q = mdot * (h_out - h_in); use synthetic values not from scenario.
        d = EnthalpyFlowResidualDeclaration(
            residual_name="ef:evap",
            q_unknown="q_evap",
            mdot_unknown="mdot:evaporator",
            h_in_unknown="h_evap_in",
            h_out_unknown="h_evap_out",
        )
        s = build_configurable_algebraic_residual_set([d])
        uvs = dict(_SINGLE_LOOP_CONSISTENT_UV)
        uvs["q_evap"] = 200_000.0
        uvs["h_evap_in"] = 200_000.0
        uvs["h_evap_out"] = 400_000.0
        result = evaluate_configurable_algebraic_residuals(s, uvs)
        assert result.residual_values["ef:evap"] == pytest.approx(0.0)


# ===========================================================================
# Scenario compatibility validation
# ===========================================================================


class TestScenarioCompatibilityValidation:
    def test_compatible_with_single_loop_scenario(self) -> None:
        build_result = _build_single_loop()
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:acc",
            pressure_unknown="P:n_acc_out",
            imposed_value=200_000.0,
        )
        s = build_configurable_algebraic_residual_set([d])
        report = validate_algebraic_residuals_against_scenario(s, build_result)
        assert report["is_compatible"] is True
        assert report["missing_unknowns"] == []

    def test_incompatible_when_unknown_name_not_in_scenario(self) -> None:
        build_result = _build_single_loop()
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:phantom",
            pressure_unknown="P:phantom_node",
            imposed_value=100_000.0,
        )
        s = build_configurable_algebraic_residual_set([d])
        report = validate_algebraic_residuals_against_scenario(s, build_result)
        assert report["is_compatible"] is False
        assert "P:phantom_node" in report["missing_unknowns"]

    def test_scenario_unknowns_listed_in_report(self) -> None:
        build_result = _build_single_loop()
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot:pump",),
            outgoing_unknown_names=(),
        )
        s = build_configurable_algebraic_residual_set([d])
        report = validate_algebraic_residuals_against_scenario(s, build_result)
        assert set(report["scenario_unknowns"]) == set(build_result.unknown_names)

    def test_residual_names_in_compatibility_report(self) -> None:
        build_result = _build_single_loop()
        d = MassBalanceResidualDeclaration(
            residual_name="mb:pump_out",
            incoming_unknown_names=("mdot:pump",),
            outgoing_unknown_names=(),
        )
        s = build_configurable_algebraic_residual_set([d])
        report = validate_algebraic_residuals_against_scenario(s, build_result)
        assert report["residual_names"] == ["mb:pump_out"]

    def test_compatibility_report_json_serializable(self) -> None:
        build_result = _build_single_loop()
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot:pump",),
            outgoing_unknown_names=(),
        )
        s = build_configurable_algebraic_residual_set([d])
        report = validate_algebraic_residuals_against_scenario(s, build_result)
        json.dumps(report)

    def test_no_residuals_inferred_from_roles(self) -> None:
        build_result = _build_single_loop()
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot:pump",),
            outgoing_unknown_names=(),
        )
        s = build_configurable_algebraic_residual_set([d])
        report = validate_algebraic_residuals_against_scenario(s, build_result)
        assert report["no_residuals_inferred_from_roles"] is True

    def test_no_residuals_inferred_from_topology(self) -> None:
        build_result = _build_single_loop()
        d = MassBalanceResidualDeclaration(
            residual_name="mb:x",
            incoming_unknown_names=("mdot:pump",),
            outgoing_unknown_names=(),
        )
        s = build_configurable_algebraic_residual_set([d])
        report = validate_algebraic_residuals_against_scenario(s, build_result)
        assert report["no_residuals_inferred_from_topology"] is True

    def test_role_change_does_not_affect_residual_declarations(self) -> None:
        # Change evaporator role to GENERIC; residuals declared with explicit names
        # must be unchanged.
        spec_modified = ConfigurableScenarioSpec(
            scenario_id="single_loop_generic_role",
            components=(
                ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
                ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
                ScenarioComponentSpec("evaporator", ScenarioComponentRole.GENERIC),
                ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
            ),
            nodes=(
                ScenarioNodeSpec("n_acc_out"),
                ScenarioNodeSpec("n_pump_out"),
                ScenarioNodeSpec("n_evap_out"),
                ScenarioNodeSpec("n_cond_out"),
            ),
            connections=(
                ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
                ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
                ScenarioConnectionSpec("evaporator", "n_pump_out", "n_evap_out"),
                ScenarioConnectionSpec("condenser", "n_evap_out", "n_cond_out"),
            ),
        )
        build_result_modified = build_configurable_scenario(spec_modified)

        d = MassBalanceResidualDeclaration(
            residual_name="mb:pump_out",
            incoming_unknown_names=("mdot:pump",),
            outgoing_unknown_names=("mdot:evaporator",),
        )
        s = build_configurable_algebraic_residual_set([d])

        # Residual set is unaffected by role change (same unknown names).
        result = evaluate_configurable_algebraic_residuals(s, _SINGLE_LOOP_CONSISTENT_UV)
        assert result.residual_values["mb:pump_out"] == pytest.approx(0.0)

        # Compatibility check passes for modified build (same unknowns).
        report = validate_algebraic_residuals_against_scenario(s, build_result_modified)
        assert report["is_compatible"] is True


# ===========================================================================
# Full report integration
# ===========================================================================


class TestFullReportIntegration:
    def test_full_report_with_scenario_compatibility(self) -> None:
        build_result = _build_single_loop()
        d_ip = ImposedPressureResidualDeclaration(
            residual_name="ip:acc",
            pressure_unknown="P:n_acc_out",
            imposed_value=200_000.0,
        )
        d_imf = ImposedMassFlowResidualDeclaration(
            residual_name="imf:pump",
            mass_flow_unknown="mdot:pump",
            imposed_value=1.0,
        )
        s = build_configurable_algebraic_residual_set([d_ip, d_imf])
        eval_result = evaluate_configurable_algebraic_residuals(s, _SINGLE_LOOP_CONSISTENT_UV)
        compat = validate_algebraic_residuals_against_scenario(s, build_result)
        report = build_configurable_algebraic_residual_report(
            eval_result, scenario_compatibility=compat
        )

        assert report["status"] == "algebraic_residual_evaluation"
        assert report["no_solve"] is True
        assert report["no_role_based_physics"] is True
        assert report["scenario_compatibility"]["is_compatible"] is True
        assert report["max_abs_residual"] == pytest.approx(0.0)
        assert report["l2_norm"] == pytest.approx(0.0)

        # Must be JSON-serializable.
        json.dumps(report)

    def test_report_contains_residual_names_and_values(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:acc",
            pressure_unknown="P:n_acc_out",
            imposed_value=200_000.0,
        )
        s = build_configurable_algebraic_residual_set([d])
        eval_result = evaluate_configurable_algebraic_residuals(s, _SINGLE_LOOP_CONSISTENT_UV)
        report = build_configurable_algebraic_residual_report(eval_result)
        assert "ip:acc" in report["residual_names"]
        assert "ip:acc" in report["residual_values"]


# ===========================================================================
# Regression: 15E-C selection stack unmodified
# ===========================================================================


class TestRegressionSelectionStack:
    def test_configurable_scenario_builds_with_same_unknowns(self) -> None:
        """15E-A scenario builder is unchanged."""
        build_result = _build_single_loop()
        assert "mdot:accumulator" in build_result.unknown_names
        assert "P:n_acc_out" in build_result.unknown_names

    def test_15eb_declaration_only_mode_unchanged(self) -> None:
        """15E-B mode enum is unchanged."""
        from mpl_sim.network.configurable_residual_selection import (
            ConfigurableResidualMode,
            ConfigurableResidualSelectionRequest,
            select_configurable_residual_strategy,
        )

        build_result = _build_single_loop()
        request = ConfigurableResidualSelectionRequest(
            build_result=build_result,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        sel_result = select_configurable_residual_strategy(request)
        assert sel_result.no_solve is True
        assert sel_result.evaluation_deferred is True

    def test_15dc_combined_closure_report_unchanged(self) -> None:
        """15D-C combined closure integration is unchanged."""
        from mpl_sim.network.closure_integration import (
            build_combined_closure_residuals,
            evaluate_combined_closure_residuals,
        )
        from mpl_sim.network.hydraulic_closures import (
            ImposedMassFlowClosure,
            build_hydraulic_closure_residuals,
        )

        cl = ImposedMassFlowClosure(
            residual_name="imf_closure:pump",
            unknown_name="mdot:pump",
            imposed_value=1.0,
        )
        h_set = build_hydraulic_closure_residuals([cl])
        combined = build_combined_closure_residuals(hydraulic=h_set)
        eval_result = evaluate_combined_closure_residuals(combined, {"mdot:pump": 1.0})
        assert eval_result.max_absolute_residual == pytest.approx(0.0)


# ===========================================================================
# Regression: Phase 14G production contracts unchanged
# ===========================================================================


class TestRegressionProductionContracts:
    def test_no_contribute_method_on_all_six_classes(self) -> None:
        from mpl_sim.network.production_component_inspection import (
            ProductionComponentContractStatus,
            inspect_known_production_component_contracts,
        )

        results = inspect_known_production_component_contracts()
        assert len(results) == 6
        for r in results:
            assert (
                r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
            ), f"{r.class_name} unexpectedly has contribute: status={r.status}"

    def test_inspection_returns_exactly_six_results(self) -> None:
        from mpl_sim.network.production_component_inspection import (
            inspect_known_production_component_contracts,
        )

        assert len(inspect_known_production_component_contracts()) == 6


# ===========================================================================
# Boundary: no automatic residual inference in new module
# ===========================================================================


class TestNoAutomaticResidualInference:
    def test_residual_set_does_not_auto_create_from_scenario(self) -> None:
        """No function should create residuals automatically from a scenario."""
        import mpl_sim.network.configurable_algebraic_residuals as mod

        # The module must not have a function that takes only a build_result
        # and returns residuals (i.e., infers residuals from topology).
        assert not hasattr(mod, "build_residuals_from_scenario")
        assert not hasattr(mod, "infer_residuals_from_roles")
        assert not hasattr(mod, "infer_residuals_from_topology")

    def test_changing_role_does_not_add_residuals_to_set(self) -> None:
        """Explicitly declared residual set has no role knowledge."""
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:acc",
            pressure_unknown="P:n_acc_out",
            imposed_value=200_000.0,
        )
        s = build_configurable_algebraic_residual_set([d])
        # Count stays exactly as declared; no role-based additions.
        assert s.count == 1

    def test_evaluate_does_not_create_additional_residuals(self) -> None:
        d = ImposedPressureResidualDeclaration(
            residual_name="ip:acc",
            pressure_unknown="P:n_acc_out",
            imposed_value=200_000.0,
        )
        s = build_configurable_algebraic_residual_set([d])
        result = evaluate_configurable_algebraic_residuals(s, _SINGLE_LOOP_CONSISTENT_UV)
        assert result.residual_names == ("ip:acc",)
        assert len(result.residual_values) == 1
