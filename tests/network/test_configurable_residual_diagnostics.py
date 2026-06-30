"""Unit tests for Block 15H-A — Explicit Residual/Unknown Structural Diagnostics MVP.

Proves structural bookkeeping diagnostics over an explicit
``ConfigurableAlgebraicResidualSet`` (Block 15F-A), with optional explicit
``ConfigurableScenarioBuildResult`` (Block 15E-A) and optional explicit
unknown-value mappings.

These tests do NOT:
  - Evaluate residual values.
  - Solve, root-find, or least-squares.
  - Build, rank, or factor a Jacobian.
  - Infer residuals, blueprints, or closures from roles or topology.
  - Execute production component physics.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or construct FluidState.
"""

from __future__ import annotations

import dataclasses
import json
import math

import pytest

from mpl_sim.network.configurable_algebraic_residuals import (
    ImposedPressureResidualDeclaration,
    MassBalanceResidualDeclaration,
    build_configurable_algebraic_residual_set,
)
from mpl_sim.network.configurable_residual_diagnostics import (
    ConfigurableResidualStructuralDiagnostic,
    ResidualDeterminationStatus,
    build_configurable_residual_diagnostic_report,
    evaluate_configurable_residual_structure,
)
from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioSpec,
    ScenarioComponentRole,
    ScenarioComponentSpec,
    ScenarioConnectionSpec,
    ScenarioNodeSpec,
    build_configurable_scenario,
)

# ===========================================================================
# Fixtures
# ===========================================================================


def _square_residual_set():
    return build_configurable_algebraic_residual_set(
        [
            ImposedPressureResidualDeclaration(
                residual_name="p_ref_a", pressure_unknown="P:a", imposed_value=100_000.0
            ),
            ImposedPressureResidualDeclaration(
                residual_name="p_ref_b", pressure_unknown="P:b", imposed_value=110_000.0
            ),
        ]
    )


def _underdetermined_residual_set():
    return build_configurable_algebraic_residual_set(
        [
            MassBalanceResidualDeclaration(
                residual_name="mb_node",
                incoming_unknown_names=("mdot:a",),
                outgoing_unknown_names=("mdot:b",),
            )
        ]
    )


def _overdetermined_residual_set():
    return build_configurable_algebraic_residual_set(
        [
            ImposedPressureResidualDeclaration(
                residual_name="p_ref_1", pressure_unknown="P:a", imposed_value=100_000.0
            ),
            ImposedPressureResidualDeclaration(
                residual_name="p_ref_2", pressure_unknown="P:a", imposed_value=105_000.0
            ),
        ]
    )


_SCENARIO_SPEC = ConfigurableScenarioSpec(
    scenario_id="diag_unit_single_loop",
    components=[
        ScenarioComponentSpec("a", ScenarioComponentRole.ACCUMULATOR),
        ScenarioComponentSpec("b", ScenarioComponentRole.PUMP),
    ],
    nodes=[
        ScenarioNodeSpec("n_a"),
        ScenarioNodeSpec("n_b"),
    ],
    connections=[
        ScenarioConnectionSpec("a", "n_b", "n_a"),
        ScenarioConnectionSpec("b", "n_a", "n_b"),
    ],
)


def _build_scenario():
    return build_configurable_scenario(_SCENARIO_SPEC)


# ===========================================================================
# Enum stability
# ===========================================================================


class TestResidualDeterminationStatusEnum:
    def test_exact_values(self) -> None:
        assert ResidualDeterminationStatus.SQUARE.value == "square"
        assert ResidualDeterminationStatus.UNDERDETERMINED.value == "underdetermined"
        assert ResidualDeterminationStatus.OVERDETERMINED.value == "overdetermined"

    def test_exactly_three_members(self) -> None:
        assert len(list(ResidualDeterminationStatus)) == 3


# ===========================================================================
# Input validation
# ===========================================================================


class TestInputValidation:
    def test_rejects_invalid_residual_set_type(self) -> None:
        with pytest.raises(TypeError):
            evaluate_configurable_residual_structure("not a residual set")  # type: ignore[arg-type]

    def test_rejects_invalid_scenario_build_result_type(self) -> None:
        with pytest.raises(TypeError):
            evaluate_configurable_residual_structure(
                _square_residual_set(),
                scenario_build_result="not a scenario build result",  # type: ignore[arg-type]
            )

    def test_rejects_invalid_unknown_values_type(self) -> None:
        with pytest.raises(TypeError):
            evaluate_configurable_residual_structure(
                _square_residual_set(),
                unknown_values="not a mapping",  # type: ignore[arg-type]
            )


# ===========================================================================
# Required unknown / residual name extraction
# ===========================================================================


class TestNameExtraction:
    def test_residual_names_match_set(self) -> None:
        rs = _square_residual_set()
        diag = evaluate_configurable_residual_structure(rs)
        assert diag.residual_names == rs.residual_names

    def test_required_unknown_names_match_set(self) -> None:
        rs = _square_residual_set()
        diag = evaluate_configurable_residual_structure(rs)
        assert diag.required_unknown_names == rs.required_unknown_names

    def test_counts_are_deterministic(self) -> None:
        rs = _square_residual_set()
        diag1 = evaluate_configurable_residual_structure(rs)
        diag2 = evaluate_configurable_residual_structure(rs)
        assert diag1.residual_count == diag2.residual_count
        assert diag1.required_unknown_count == diag2.required_unknown_count


# ===========================================================================
# Determination status
# ===========================================================================


class TestDeterminationStatus:
    def test_square(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        assert diag.residual_count == 2
        assert diag.required_unknown_count == 2
        assert diag.determination_status is ResidualDeterminationStatus.SQUARE

    def test_underdetermined(self) -> None:
        diag = evaluate_configurable_residual_structure(_underdetermined_residual_set())
        assert diag.residual_count == 1
        assert diag.required_unknown_count == 2
        assert diag.determination_status is ResidualDeterminationStatus.UNDERDETERMINED

    def test_overdetermined(self) -> None:
        diag = evaluate_configurable_residual_structure(_overdetermined_residual_set())
        assert diag.residual_count == 2
        assert diag.required_unknown_count == 1
        assert diag.determination_status is ResidualDeterminationStatus.OVERDETERMINED


# ===========================================================================
# Scenario compatibility diagnostics
# ===========================================================================


class TestScenarioCompatibility:
    def test_scenario_omitted(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        assert diag.scenario_unknown_names is None
        assert diag.scenario_compatible is None
        assert diag.missing_from_scenario == ()
        assert diag.extra_scenario_unknowns == ()

    def test_scenario_compatible_true(self) -> None:
        rs = build_configurable_algebraic_residual_set(
            [
                ImposedPressureResidualDeclaration(
                    residual_name="p_ref_a", pressure_unknown="P:n_a", imposed_value=100_000.0
                )
            ]
        )
        sbr = _build_scenario()
        diag = evaluate_configurable_residual_structure(rs, scenario_build_result=sbr)
        assert diag.scenario_unknown_names == sbr.unknown_names
        assert diag.missing_from_scenario == ()
        assert diag.scenario_compatible is True

    def test_missing_from_scenario(self) -> None:
        rs = build_configurable_algebraic_residual_set(
            [
                ImposedPressureResidualDeclaration(
                    residual_name="p_ref_x",
                    pressure_unknown="P:does_not_exist",
                    imposed_value=100_000.0,
                )
            ]
        )
        sbr = _build_scenario()
        diag = evaluate_configurable_residual_structure(rs, scenario_build_result=sbr)
        assert diag.missing_from_scenario == ("P:does_not_exist",)
        assert diag.scenario_compatible is False

    def test_extra_scenario_unknowns(self) -> None:
        rs = build_configurable_algebraic_residual_set(
            [
                ImposedPressureResidualDeclaration(
                    residual_name="p_ref_a", pressure_unknown="P:n_a", imposed_value=100_000.0
                )
            ]
        )
        sbr = _build_scenario()
        diag = evaluate_configurable_residual_structure(rs, scenario_build_result=sbr)
        # scenario declares more unknowns than this single residual requires
        assert len(diag.extra_scenario_unknowns) > 0
        assert diag.scenario_compatible is True


# ===========================================================================
# Unknown value diagnostics
# ===========================================================================


class TestUnknownValueDiagnostics:
    def test_unknown_values_omitted(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        assert diag.supplied_unknown_names is None
        assert diag.unknown_values_complete is None
        assert diag.missing_from_values == ()
        assert diag.extra_supplied_unknowns == ()

    def test_unknown_values_complete(self) -> None:
        rs = _square_residual_set()
        diag = evaluate_configurable_residual_structure(
            rs, unknown_values={"P:a": 100_000.0, "P:b": 110_000.0}
        )
        assert diag.missing_from_values == ()
        assert diag.unknown_values_complete is True

    def test_missing_unknown_values(self) -> None:
        rs = _square_residual_set()
        diag = evaluate_configurable_residual_structure(rs, unknown_values={"P:a": 100_000.0})
        assert diag.missing_from_values == ("P:b",)
        assert diag.unknown_values_complete is False

    def test_extra_unknown_values(self) -> None:
        rs = _square_residual_set()
        diag = evaluate_configurable_residual_structure(
            rs,
            unknown_values={
                "P:a": 100_000.0,
                "P:b": 110_000.0,
                "P:extra": 1.0,
            },
        )
        assert diag.extra_supplied_unknowns == ("P:extra",)
        assert diag.unknown_values_complete is True

    @pytest.mark.parametrize(
        "bad_value",
        [True, False, "not a number", None, [], {}],
    )
    def test_rejects_non_numeric_or_bool_values(self, bad_value: object) -> None:
        rs = _square_residual_set()
        with pytest.raises(TypeError):
            evaluate_configurable_residual_structure(
                rs, unknown_values={"P:a": bad_value, "P:b": 1.0}
            )

    def test_rejects_nan_value(self) -> None:
        rs = _square_residual_set()
        with pytest.raises(ValueError):
            evaluate_configurable_residual_structure(
                rs, unknown_values={"P:a": math.nan, "P:b": 1.0}
            )

    def test_rejects_infinite_value(self) -> None:
        rs = _square_residual_set()
        with pytest.raises(ValueError):
            evaluate_configurable_residual_structure(
                rs, unknown_values={"P:a": math.inf, "P:b": 1.0}
            )


# ===========================================================================
# Evaluation readiness
# ===========================================================================


class TestEvaluationReadiness:
    def test_complete_scenario_and_complete_values_ready(self) -> None:
        rs = build_configurable_algebraic_residual_set(
            [
                ImposedPressureResidualDeclaration(
                    residual_name="p_ref_a", pressure_unknown="P:n_a", imposed_value=100_000.0
                )
            ]
        )
        sbr = _build_scenario()
        diag = evaluate_configurable_residual_structure(
            rs, scenario_build_result=sbr, unknown_values={"P:n_a": 100_000.0}
        )
        assert diag.scenario_compatible is True
        assert diag.unknown_values_complete is True
        assert diag.evaluation_ready is True

    def test_missing_scenario_unknowns_not_ready(self) -> None:
        rs = build_configurable_algebraic_residual_set(
            [
                ImposedPressureResidualDeclaration(
                    residual_name="p_ref_x",
                    pressure_unknown="P:does_not_exist",
                    imposed_value=100_000.0,
                )
            ]
        )
        sbr = _build_scenario()
        diag = evaluate_configurable_residual_structure(
            rs,
            scenario_build_result=sbr,
            unknown_values={"P:does_not_exist": 100_000.0},
        )
        assert diag.scenario_compatible is False
        assert diag.unknown_values_complete is True
        assert diag.evaluation_ready is False

    def test_missing_values_not_ready(self) -> None:
        rs = _square_residual_set()
        sbr = _build_scenario()
        diag = evaluate_configurable_residual_structure(
            rs, scenario_build_result=sbr, unknown_values={"P:a": 1.0}
        )
        assert diag.unknown_values_complete is False
        assert diag.evaluation_ready is False

    def test_omitted_scenario_with_complete_values_ready(self) -> None:
        rs = _square_residual_set()
        diag = evaluate_configurable_residual_structure(rs, unknown_values={"P:a": 1.0, "P:b": 2.0})
        assert diag.scenario_compatible is None
        assert diag.unknown_values_complete is True
        assert diag.evaluation_ready is True

    def test_omitted_values_never_ready(self) -> None:
        rs = _square_residual_set()
        sbr = _build_scenario()
        diag = evaluate_configurable_residual_structure(rs, scenario_build_result=sbr)
        assert diag.unknown_values_complete is None
        assert diag.evaluation_ready is False

    def test_both_omitted_not_ready(self) -> None:
        rs = _square_residual_set()
        diag = evaluate_configurable_residual_structure(rs)
        assert diag.evaluation_ready is False


# ===========================================================================
# Solve readiness / no-solve invariants
# ===========================================================================


class TestSolveReadiness:
    def test_solve_ready_always_false(self) -> None:
        for rs in (
            _square_residual_set(),
            _underdetermined_residual_set(),
            _overdetermined_residual_set(),
        ):
            diag = evaluate_configurable_residual_structure(
                rs, unknown_values={n: 1.0 for n in rs.required_unknown_names}
            )
            assert diag.solve_ready is False

    def test_no_solve_always_true(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        assert diag.no_solve is True

    def test_square_does_not_imply_solve_ready(self) -> None:
        rs = _square_residual_set()
        diag = evaluate_configurable_residual_structure(
            rs, unknown_values={"P:a": 100_000.0, "P:b": 110_000.0}
        )
        assert diag.determination_status is ResidualDeterminationStatus.SQUARE
        assert diag.evaluation_ready is True
        assert diag.solve_ready is False


# ===========================================================================
# No-inference flags
# ===========================================================================


class TestNoInferenceFlags:
    def test_all_flags_false(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        assert diag.residuals_inferred_from_roles is False
        assert diag.residuals_inferred_from_topology is False
        assert diag.blueprints_inferred_from_roles is False
        assert diag.blueprints_inferred_from_topology is False
        assert diag.closures_inferred_from_roles is False
        assert diag.production_components_executed is False


# ===========================================================================
# Immutability
# ===========================================================================


class TestImmutability:
    def test_result_is_frozen(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        with pytest.raises(dataclasses.FrozenInstanceError):
            diag.evaluation_ready = True  # type: ignore[misc]

    def test_construction_rejects_solve_ready_true(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        kwargs = {f.name: getattr(diag, f.name) for f in dataclasses.fields(diag)}
        kwargs["solve_ready"] = True
        with pytest.raises(ValueError):
            ConfigurableResidualStructuralDiagnostic(**kwargs)

    def test_construction_rejects_no_solve_false(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        kwargs = {f.name: getattr(diag, f.name) for f in dataclasses.fields(diag)}
        kwargs["no_solve"] = False
        with pytest.raises(ValueError):
            ConfigurableResidualStructuralDiagnostic(**kwargs)

    @pytest.mark.parametrize(
        "flag_name",
        [
            "residuals_inferred_from_roles",
            "residuals_inferred_from_topology",
            "blueprints_inferred_from_roles",
            "blueprints_inferred_from_topology",
            "closures_inferred_from_roles",
            "production_components_executed",
        ],
    )
    def test_construction_rejects_true_inference_flags(self, flag_name: str) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        kwargs = {f.name: getattr(diag, f.name) for f in dataclasses.fields(diag)}
        kwargs[flag_name] = True
        with pytest.raises(ValueError):
            ConfigurableResidualStructuralDiagnostic(**kwargs)


# ===========================================================================
# Report behavior
# ===========================================================================


class TestReportBehavior:
    def test_report_is_json_serializable(self) -> None:
        diag = evaluate_configurable_residual_structure(
            _square_residual_set(), unknown_values={"P:a": 1.0, "P:b": 2.0}
        )
        report = build_configurable_residual_diagnostic_report(diag)
        json_str = json.dumps(report)
        parsed = json.loads(json_str)
        assert parsed["status"] == "configurable_residual_structural_diagnostic"

    def test_report_rejects_invalid_diagnostic_type(self) -> None:
        with pytest.raises(TypeError):
            build_configurable_residual_diagnostic_report("not a diagnostic")  # type: ignore[arg-type]

    def test_report_contains_no_inference_flags(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        report = build_configurable_residual_diagnostic_report(diag)
        assert report["residuals_inferred_from_roles"] is False
        assert report["residuals_inferred_from_topology"] is False
        assert report["blueprints_inferred_from_roles"] is False
        assert report["blueprints_inferred_from_topology"] is False
        assert report["closures_inferred_from_roles"] is False
        assert report["production_components_executed"] is False

    def test_report_contains_limitations(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        report = build_configurable_residual_diagnostic_report(diag)
        assert isinstance(report["limitations"], list)
        assert len(report["limitations"]) > 0

    def test_report_contains_no_solve_and_solve_ready(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        report = build_configurable_residual_diagnostic_report(diag)
        assert report["no_solve"] is True
        assert report["solve_ready"] is False

    def test_report_scenario_and_unknown_sections_not_checked_when_omitted(self) -> None:
        diag = evaluate_configurable_residual_structure(_square_residual_set())
        report = build_configurable_residual_diagnostic_report(diag)
        assert report["scenario_compatibility"]["checked"] is False
        assert report["scenario_compatibility"]["scenario_compatible"] is None
        assert report["unknown_value_completeness"]["checked"] is False
        assert report["unknown_value_completeness"]["unknown_values_complete"] is None
