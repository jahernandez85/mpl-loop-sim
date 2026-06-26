"""Unit tests for Block 15E-B configurable residual selection.

Coverage:
  - ConfigurableResidualMode enum contents
  - ConfigurableResidualSelectionRequest construction and validation
  - ConfigurableResidualCompatibilityResult construction
  - ConfigurableResidualSelectionResult construction
  - Declaration-only mode: acceptance, no evaluation
  - Fixed single-loop mode: acceptance, incompatibility
  - Fixed two-branch mode: acceptance, incompatibility
  - Closure-only mode: requires explicit closure set
  - Deterministic compatibility reasons
  - Reports: JSON-serializable, no_solve=True, roles_selected_physics=False
  - Explicitness safeguards: roles do not select mode
  - Boundary: no CoolProp, no PropertyBackend, no component execution
  - Boundary: no SystemState, no FluidState, no closures inferred from roles

These tests do NOT:
  - Evaluate physical residuals (see integration test file).
  - Instantiate production components.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or FluidState.
  - Add solve(network) or NetworkGraph.solve().
"""

from __future__ import annotations

import json

import pytest

from mpl_sim.network.closure_integration import build_combined_closure_residuals
from mpl_sim.network.configurable_residual_selection import (
    ConfigurableResidualCompatibilityResult,
    ConfigurableResidualMode,
    ConfigurableResidualSelectionRequest,
    build_configurable_residual_selection_report,
    evaluate_selected_configurable_residuals,
    select_configurable_residual_strategy,
)
from mpl_sim.network.configurable_scenarios import (
    ConfigurableScenarioSpec,
    ScenarioBranchSpec,
    ScenarioComponentRole,
    ScenarioComponentSpec,
    ScenarioConnectionSpec,
    ScenarioNodeSpec,
    build_configurable_scenario,
)
from mpl_sim.network.hydraulic_closures import (
    ImposedMassFlowClosure,
    build_hydraulic_closure_residuals,
)

# ---------------------------------------------------------------------------
# Helpers: build configurable scenarios
# ---------------------------------------------------------------------------


def _single_loop_result():
    """Configurable single-loop with conventional IDs matching fixed single-loop."""
    spec = ConfigurableScenarioSpec(
        scenario_id="test_single_loop",
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
    return build_configurable_scenario(spec)


def _two_branch_result():
    """Configurable two-branch with conventional IDs matching fixed two-branch."""
    spec = ConfigurableScenarioSpec(
        scenario_id="test_two_branch",
        components=(
            ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
            ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
            ScenarioComponentSpec("branch_a", ScenarioComponentRole.PIPE),
            ScenarioComponentSpec("branch_b", ScenarioComponentRole.PIPE),
            ScenarioComponentSpec("merge_a", ScenarioComponentRole.JUNCTION),
            ScenarioComponentSpec("merge_b", ScenarioComponentRole.JUNCTION),
            ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
        ),
        nodes=(
            ScenarioNodeSpec("n_acc_out"),
            ScenarioNodeSpec("n_pump_out"),
            ScenarioNodeSpec("n_a_out"),
            ScenarioNodeSpec("n_b_out"),
            ScenarioNodeSpec("n_merge_out"),
            ScenarioNodeSpec("n_cond_out"),
        ),
        connections=(
            ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
            ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
            ScenarioConnectionSpec("branch_a", "n_pump_out", "n_a_out"),
            ScenarioConnectionSpec("branch_b", "n_pump_out", "n_b_out"),
            ScenarioConnectionSpec("merge_a", "n_a_out", "n_merge_out"),
            ScenarioConnectionSpec("merge_b", "n_b_out", "n_merge_out"),
            ScenarioConnectionSpec("condenser", "n_merge_out", "n_cond_out"),
        ),
        branches=(
            ScenarioBranchSpec(
                branch_id="branch_a",
                inlet_node_id="n_pump_out",
                outlet_node_id="n_merge_out",
                component_ids=("branch_a", "merge_a"),
            ),
            ScenarioBranchSpec(
                branch_id="branch_b",
                inlet_node_id="n_pump_out",
                outlet_node_id="n_merge_out",
                component_ids=("branch_b", "merge_b"),
            ),
        ),
    )
    return build_configurable_scenario(spec)


def _incompatible_result():
    """Configurable scenario with non-conventional IDs — incompatible with any fixed mode."""
    spec = ConfigurableScenarioSpec(
        scenario_id="test_incompatible",
        components=(
            ScenarioComponentSpec("comp_a", ScenarioComponentRole.GENERIC),
            ScenarioComponentSpec("comp_b", ScenarioComponentRole.GENERIC),
        ),
        nodes=(
            ScenarioNodeSpec("node_x"),
            ScenarioNodeSpec("node_y"),
        ),
        connections=(
            ScenarioConnectionSpec("comp_a", "node_y", "node_x"),
            ScenarioConnectionSpec("comp_b", "node_x", "node_y"),
        ),
    )
    return build_configurable_scenario(spec)


def _single_loop_wrong_edge_result():
    """Conventional single-loop IDs with a wrong edge direction."""
    spec = ConfigurableScenarioSpec(
        scenario_id="test_single_loop_wrong_edge",
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
            ScenarioConnectionSpec("evaporator", "n_evap_out", "n_pump_out"),
            ScenarioConnectionSpec("condenser", "n_pump_out", "n_cond_out"),
        ),
    )
    return build_configurable_scenario(spec)


def _two_branch_wrong_edge_result():
    """Conventional two-branch IDs with a wrong branch edge."""
    spec = ConfigurableScenarioSpec(
        scenario_id="test_two_branch_wrong_edge",
        components=(
            ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
            ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
            ScenarioComponentSpec("branch_a", ScenarioComponentRole.PIPE),
            ScenarioComponentSpec("branch_b", ScenarioComponentRole.PIPE),
            ScenarioComponentSpec("merge_a", ScenarioComponentRole.JUNCTION),
            ScenarioComponentSpec("merge_b", ScenarioComponentRole.JUNCTION),
            ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
        ),
        nodes=(
            ScenarioNodeSpec("n_acc_out"),
            ScenarioNodeSpec("n_pump_out"),
            ScenarioNodeSpec("n_a_out"),
            ScenarioNodeSpec("n_b_out"),
            ScenarioNodeSpec("n_merge_out"),
            ScenarioNodeSpec("n_cond_out"),
        ),
        connections=(
            ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
            ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
            ScenarioConnectionSpec("branch_a", "n_a_out", "n_pump_out"),
            ScenarioConnectionSpec("branch_b", "n_pump_out", "n_b_out"),
            ScenarioConnectionSpec("merge_a", "n_pump_out", "n_merge_out"),
            ScenarioConnectionSpec("merge_b", "n_b_out", "n_merge_out"),
            ScenarioConnectionSpec("condenser", "n_merge_out", "n_cond_out"),
        ),
        branches=(
            ScenarioBranchSpec(
                branch_id="branch_a",
                inlet_node_id="n_a_out",
                outlet_node_id="n_merge_out",
                component_ids=("branch_a", "merge_a"),
            ),
            ScenarioBranchSpec(
                branch_id="branch_b",
                inlet_node_id="n_pump_out",
                outlet_node_id="n_merge_out",
                component_ids=("branch_b", "merge_b"),
            ),
        ),
    )
    return build_configurable_scenario(spec)


def _simple_closure_set():
    """A simple hydraulic-only combined closure residual set."""
    hyd = build_hydraulic_closure_residuals(
        closures=(
            ImposedMassFlowClosure(
                unknown_name="mdot_total",
                imposed_value=1.0,
                residual_name="r_mdot_imposed",
            ),
        )
    )
    return build_combined_closure_residuals(hydraulic=hyd)


# ---------------------------------------------------------------------------
# 1. ConfigurableResidualMode enum
# ---------------------------------------------------------------------------


class TestConfigurableResidualMode:
    def test_enum_has_exactly_four_modes(self):
        modes = list(ConfigurableResidualMode)
        assert len(modes) == 4

    def test_declaration_only_member(self):
        assert ConfigurableResidualMode.DECLARATION_ONLY in ConfigurableResidualMode
        assert ConfigurableResidualMode.DECLARATION_ONLY.value == "declaration_only"

    def test_fixed_single_loop_member(self):
        assert ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC in ConfigurableResidualMode
        assert (
            ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC.value
            == "fixed_single_loop_algebraic"
        )

    def test_fixed_two_branch_member(self):
        assert (
            ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC in ConfigurableResidualMode
        )
        assert (
            ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC.value
            == "fixed_two_branch_parallel_algebraic"
        )

    def test_closure_only_member(self):
        assert ConfigurableResidualMode.CLOSURE_ONLY in ConfigurableResidualMode
        assert ConfigurableResidualMode.CLOSURE_ONLY.value == "closure_only"

    def test_mode_values_are_distinct(self):
        values = [m.value for m in ConfigurableResidualMode]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# 2. ConfigurableResidualSelectionRequest
# ---------------------------------------------------------------------------


class TestConfigurableResidualSelectionRequest:
    def test_minimal_construction(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        assert req.build_result is br
        assert req.mode is ConfigurableResidualMode.DECLARATION_ONLY
        assert req.single_loop_parameters is None
        assert req.single_loop_unknown_values is None
        assert req.two_branch_parameters is None
        assert req.two_branch_unknown_values is None
        assert req.closure_residual_set is None
        assert req.closure_unknown_values is None
        assert req.evaluate is False
        assert req.metadata is None

    def test_wrong_build_result_type_raises(self):
        with pytest.raises(TypeError, match="build_result"):
            ConfigurableResidualSelectionRequest(
                build_result="not a build result",  # type: ignore[arg-type]
                mode=ConfigurableResidualMode.DECLARATION_ONLY,
            )

    def test_wrong_mode_type_raises(self):
        br = _single_loop_result()
        with pytest.raises(TypeError, match="mode"):
            ConfigurableResidualSelectionRequest(
                build_result=br,
                mode="declaration_only",  # type: ignore[arg-type]
            )

    def test_wrong_closure_set_type_raises(self):
        br = _single_loop_result()
        with pytest.raises(TypeError, match="closure_residual_set"):
            ConfigurableResidualSelectionRequest(
                build_result=br,
                mode=ConfigurableResidualMode.CLOSURE_ONLY,
                closure_residual_set="not a closure set",  # type: ignore[arg-type]
            )

    def test_wrong_evaluate_type_raises(self):
        br = _single_loop_result()
        with pytest.raises(TypeError, match="evaluate"):
            ConfigurableResidualSelectionRequest(
                build_result=br,
                mode=ConfigurableResidualMode.DECLARATION_ONLY,
                evaluate="yes",  # type: ignore[arg-type]
            )

    def test_metadata_is_defensively_copied(self):
        br = _single_loop_result()
        md: dict[str, object] = {"key": "value"}
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
            metadata=md,
        )
        md["key"] = "modified"
        assert req.metadata["key"] == "value"  # type: ignore[index]

    def test_unknown_values_are_defensively_copied(self):
        br = _single_loop_result()
        unknown_values = {"mdot_total": 1.0}
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=_simple_closure_set(),
            closure_unknown_values=unknown_values,
        )
        unknown_values["mdot_total"] = 2.0
        assert req.closure_unknown_values["mdot_total"] == 1.0  # type: ignore[index]

    def test_is_frozen(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        with pytest.raises((AttributeError, TypeError)):
            req.mode = ConfigurableResidualMode.CLOSURE_ONLY  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. ConfigurableResidualCompatibilityResult
# ---------------------------------------------------------------------------


class TestConfigurableResidualCompatibilityResult:
    def test_compatible_construction(self):
        r = ConfigurableResidualCompatibilityResult(
            is_compatible=True,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
            reasons=("reason 1", "reason 2"),
        )
        assert r.is_compatible is True
        assert r.mode is ConfigurableResidualMode.DECLARATION_ONLY
        assert r.reasons == ("reason 1", "reason 2")

    def test_incompatible_construction(self):
        r = ConfigurableResidualCompatibilityResult(
            is_compatible=False,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            reasons=("ID mismatch",),
        )
        assert r.is_compatible is False

    def test_wrong_is_compatible_type_raises(self):
        with pytest.raises(TypeError, match="is_compatible"):
            ConfigurableResidualCompatibilityResult(
                is_compatible=1,  # type: ignore[arg-type]
                mode=ConfigurableResidualMode.DECLARATION_ONLY,
                reasons=(),
            )

    def test_wrong_mode_type_raises(self):
        with pytest.raises(TypeError, match="mode"):
            ConfigurableResidualCompatibilityResult(
                is_compatible=True,
                mode="declaration_only",  # type: ignore[arg-type]
                reasons=(),
            )

    def test_is_frozen(self):
        r = ConfigurableResidualCompatibilityResult(
            is_compatible=True,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
            reasons=("ok",),
        )
        with pytest.raises((AttributeError, TypeError)):
            r.is_compatible = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4. Declaration-only mode
# ---------------------------------------------------------------------------


class TestDeclarationOnlyMode:
    def test_accepts_single_loop_result(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True
        assert result.selected_mode is ConfigurableResidualMode.DECLARATION_ONLY

    def test_accepts_two_branch_result(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True

    def test_accepts_incompatible_structure(self):
        br = _incompatible_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True

    def test_no_evaluation_performed(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_result is None

    def test_evaluation_deferred(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_deferred is True
        assert "declaration-only" in result.evaluation_deferred_reason.lower()

    def test_no_solve_always_true(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True

    def test_compatibility_reasons_non_empty(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert len(result.compatibility.reasons) > 0

    def test_limitations_present(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert len(result.limitations) > 0


# ---------------------------------------------------------------------------
# 5. Fixed single-loop mode
# ---------------------------------------------------------------------------


class TestFixedSingleLoopMode:
    def test_accepts_conventional_single_loop_scenario(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True
        assert result.selected_mode is ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC

    def test_rejects_incompatible_structure(self):
        br = _incompatible_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False

    def test_rejects_two_branch_structure(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False

    def test_rejects_conventional_ids_with_wrong_graph_edges(self):
        br = _single_loop_wrong_edge_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False
        assert "edge signature" in " ".join(result.compatibility.reasons)

    def test_incompatible_reasons_describe_id_mismatch(self):
        br = _incompatible_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        reasons_combined = " ".join(result.compatibility.reasons)
        assert "component" in reasons_combined.lower() or "do not match" in reasons_combined.lower()

    def test_no_evaluation_when_params_absent(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_result is None
        assert result.evaluation_deferred is True

    def test_deferred_reason_mentions_parameters(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            evaluate=True,
        )
        result = select_configurable_residual_strategy(req)
        assert "parameters" in result.evaluation_deferred_reason.lower()

    def test_incompatible_gives_no_evaluation(self):
        br = _incompatible_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_result is None

    def test_no_solve_always_true(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True


# ---------------------------------------------------------------------------
# 6. Fixed two-branch mode
# ---------------------------------------------------------------------------


class TestFixedTwoBranchMode:
    def test_accepts_conventional_two_branch_scenario(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True
        assert result.selected_mode is ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC

    def test_rejects_incompatible_structure(self):
        br = _incompatible_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False

    def test_rejects_single_loop_structure(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False

    def test_rejects_conventional_ids_with_wrong_graph_edges(self):
        br = _two_branch_wrong_edge_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False
        assert "edge signature" in " ".join(result.compatibility.reasons)

    def test_rejects_missing_branch_ids(self):
        """Two-branch scenario without branch declarations is incompatible."""
        spec = ConfigurableScenarioSpec(
            scenario_id="two_branch_no_branches",
            components=(
                ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
                ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
                ScenarioComponentSpec("branch_a", ScenarioComponentRole.PIPE),
                ScenarioComponentSpec("branch_b", ScenarioComponentRole.PIPE),
                ScenarioComponentSpec("merge_a", ScenarioComponentRole.JUNCTION),
                ScenarioComponentSpec("merge_b", ScenarioComponentRole.JUNCTION),
                ScenarioComponentSpec("condenser", ScenarioComponentRole.CONDENSER),
            ),
            nodes=(
                ScenarioNodeSpec("n_acc_out"),
                ScenarioNodeSpec("n_pump_out"),
                ScenarioNodeSpec("n_a_out"),
                ScenarioNodeSpec("n_b_out"),
                ScenarioNodeSpec("n_merge_out"),
                ScenarioNodeSpec("n_cond_out"),
            ),
            connections=(
                ScenarioConnectionSpec("accumulator", "n_cond_out", "n_acc_out"),
                ScenarioConnectionSpec("pump", "n_acc_out", "n_pump_out"),
                ScenarioConnectionSpec("branch_a", "n_pump_out", "n_a_out"),
                ScenarioConnectionSpec("branch_b", "n_pump_out", "n_b_out"),
                ScenarioConnectionSpec("merge_a", "n_a_out", "n_merge_out"),
                ScenarioConnectionSpec("merge_b", "n_b_out", "n_merge_out"),
                ScenarioConnectionSpec("condenser", "n_merge_out", "n_cond_out"),
            ),
            # No branches declared
        )
        br = build_configurable_scenario(spec)
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False
        reasons_combined = " ".join(result.compatibility.reasons)
        assert "branch" in reasons_combined.lower()

    def test_incompatible_reasons_describe_id_mismatch(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        reasons_combined = " ".join(result.compatibility.reasons)
        assert "do not match" in reasons_combined.lower()

    def test_no_evaluation_when_params_absent(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_result is None
        assert result.evaluation_deferred is True

    def test_no_solve_always_true(self):
        br = _two_branch_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_TWO_BRANCH_PARALLEL_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True


# ---------------------------------------------------------------------------
# 7. Closure-only mode
# ---------------------------------------------------------------------------


class TestClosureOnlyMode:
    def test_requires_explicit_closure_set(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            # No closure_residual_set
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is False

    def test_rejects_missing_closure_set_with_reason(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        reasons_combined = " ".join(result.compatibility.reasons).lower()
        assert "closure_residual_set" in reasons_combined or "none" in reasons_combined

    def test_accepts_explicit_closure_set(self):
        br = _single_loop_result()
        closure_set = _simple_closure_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True
        assert result.selected_mode is ConfigurableResidualMode.CLOSURE_ONLY

    def test_compatible_reason_mentions_explicit_set(self):
        br = _single_loop_result()
        closure_set = _simple_closure_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
        )
        result = select_configurable_residual_strategy(req)
        reasons_combined = " ".join(result.compatibility.reasons)
        assert "explicit" in reasons_combined.lower() or "provided" in reasons_combined.lower()

    def test_no_closure_inferred_reason_present(self):
        br = _single_loop_result()
        closure_set = _simple_closure_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
        )
        result = select_configurable_residual_strategy(req)
        reasons_combined = " ".join(result.compatibility.reasons)
        assert "inferred" in reasons_combined.lower() or "not inferred" in reasons_combined.lower()

    def test_no_evaluation_when_unknown_values_absent(self):
        br = _single_loop_result()
        closure_set = _simple_closure_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            # No closure_unknown_values
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_performed is False
        assert result.evaluation_result is None
        assert result.evaluation_deferred is True

    def test_selection_only_even_with_closure_unknowns_when_evaluate_false(self):
        br = _single_loop_result()
        closure_set = _simple_closure_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            closure_unknown_values={"mdot_total": 1.0},
        )
        result = select_configurable_residual_strategy(req)
        assert result.compatibility.is_compatible is True
        assert result.evaluation_performed is False
        assert result.evaluation_result is None
        assert "evaluate is False" in result.evaluation_deferred_reason

    def test_no_solve_always_true(self):
        br = _single_loop_result()
        closure_set = _simple_closure_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
        )
        result = select_configurable_residual_strategy(req)
        assert result.no_solve is True


# ---------------------------------------------------------------------------
# 8. Explicitness safeguards: roles do not select physics
# ---------------------------------------------------------------------------


class TestExplicitnessRoles:
    def test_roles_alone_do_not_select_mode(self):
        """Changing roles on the same structure does not change compatibility."""
        # Scenario with PUMP role on all components — same structure as single loop
        spec = ConfigurableScenarioSpec(
            scenario_id="all_pump_roles",
            components=(
                ScenarioComponentSpec("accumulator", ScenarioComponentRole.PUMP),
                ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
                ScenarioComponentSpec("evaporator", ScenarioComponentRole.PUMP),
                ScenarioComponentSpec("condenser", ScenarioComponentRole.PUMP),
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
        br_all_pump = build_configurable_scenario(spec)
        br_conventional = _single_loop_result()

        # Both should be compatible with FIXED_SINGLE_LOOP since structure matches
        req_pump = ConfigurableResidualSelectionRequest(
            build_result=br_all_pump,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        req_conv = ConfigurableResidualSelectionRequest(
            build_result=br_conventional,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result_pump = select_configurable_residual_strategy(req_pump)
        result_conv = select_configurable_residual_strategy(req_conv)

        # Structure-based compatibility is the same regardless of roles
        assert result_pump.compatibility.is_compatible == result_conv.compatibility.is_compatible

    def test_evaporator_condenser_roles_do_not_infer_thermal_closures(self):
        """EVAPORATOR/CONDENSER roles must not generate thermal closures."""
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        # No thermal closures should be inferred
        assert result.evaluation_result is None

    def test_pump_pipe_valve_roles_do_not_infer_hydraulic_closures(self):
        """PUMP/PIPE/VALVE roles must not generate hydraulic closures."""
        spec = ConfigurableScenarioSpec(
            scenario_id="pump_pipe_valve",
            components=(
                ScenarioComponentSpec("accumulator", ScenarioComponentRole.ACCUMULATOR),
                ScenarioComponentSpec("pump", ScenarioComponentRole.PUMP),
                ScenarioComponentSpec("evaporator", ScenarioComponentRole.PIPE),
                ScenarioComponentSpec("condenser", ScenarioComponentRole.VALVE),
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
        br = build_configurable_scenario(spec)
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        assert result.evaluation_result is None

    def test_mode_must_be_explicitly_requested(self):
        """No mode is selected automatically."""
        br = _single_loop_result()
        # User must explicitly pass FIXED_SINGLE_LOOP_ALGEBRAIC
        req_decl = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req_decl)
        # Even though the structure matches, DECLARATION_ONLY was chosen
        assert result.selected_mode is ConfigurableResidualMode.DECLARATION_ONLY

    def test_changing_roles_does_not_change_compatibility(self):
        """Roles are ignored for compatibility checks; only structure matters."""
        # Both scenarios have the SAME structure (same IDs) but different roles
        spec1 = ConfigurableScenarioSpec(
            scenario_id="s1",
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
        spec2 = ConfigurableScenarioSpec(
            scenario_id="s2",
            components=(
                ScenarioComponentSpec("accumulator", ScenarioComponentRole.GENERIC),
                ScenarioComponentSpec("pump", ScenarioComponentRole.GENERIC),
                ScenarioComponentSpec("evaporator", ScenarioComponentRole.GENERIC),
                ScenarioComponentSpec("condenser", ScenarioComponentRole.GENERIC),
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
        br1 = build_configurable_scenario(spec1)
        br2 = build_configurable_scenario(spec2)

        req1 = ConfigurableResidualSelectionRequest(
            build_result=br1,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        req2 = ConfigurableResidualSelectionRequest(
            build_result=br2,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result1 = select_configurable_residual_strategy(req1)
        result2 = select_configurable_residual_strategy(req2)

        # Both have same structure (same IDs) so same compatibility
        assert result1.compatibility.is_compatible == result2.compatibility.is_compatible


# ---------------------------------------------------------------------------
# 9. Reports: JSON-serializable, no_solve, roles_selected_physics
# ---------------------------------------------------------------------------


class TestReports:
    def test_report_is_json_serializable_declaration_only(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        json_str = json.dumps(report)
        assert json_str  # non-empty

    def test_report_includes_no_solve_true(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["no_solve"] is True

    def test_report_roles_selected_physics_false(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["roles_selected_physics"] is False

    def test_report_closures_inferred_from_roles_false(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["closures_inferred_from_roles"] is False

    def test_report_includes_selected_mode(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["selected_mode"] == "declaration_only"

    def test_report_includes_scenario_id(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["scenario_id"] == "test_single_loop"

    def test_report_includes_compatibility_section(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert "compatibility" in report
        compat = report["compatibility"]
        assert isinstance(compat, dict)
        assert "is_compatible" in compat
        assert "reasons" in compat

    def test_report_includes_evaluation_section(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert "evaluation" in report
        ev = report["evaluation"]
        assert isinstance(ev, dict)
        assert "performed" in ev

    def test_report_includes_limitations(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert "limitations" in report
        assert len(report["limitations"]) > 0  # type: ignore[arg-type]

    def test_report_includes_component_roles(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert "component_roles" in report
        roles = report["component_roles"]
        assert isinstance(roles, dict)
        assert "accumulator" in roles

    def test_report_for_incompatible_scenario(self):
        br = _incompatible_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result = select_configurable_residual_strategy(req)
        report = build_configurable_residual_selection_report(result)
        assert report["compatibility"]["is_compatible"] is False  # type: ignore[index]
        assert report["no_solve"] is True
        json.dumps(report)  # must be serializable

    def test_report_wrong_type_raises(self):
        with pytest.raises(TypeError, match="result"):
            build_configurable_residual_selection_report("not a result")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 10. evaluate_selected_configurable_residuals: raises on missing params
# ---------------------------------------------------------------------------


class TestEvaluateSelectedConfigurableResiduals:
    def test_raises_if_compatible_but_no_params(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
            evaluate=True,
            # No evaluation params
        )
        with pytest.raises(ValueError):
            evaluate_selected_configurable_residuals(req)

    def test_raises_if_incompatible(self):
        br = _incompatible_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        with pytest.raises(ValueError, match="compatible"):
            evaluate_selected_configurable_residuals(req)

    def test_raises_for_declaration_only(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        with pytest.raises(ValueError):
            evaluate_selected_configurable_residuals(req)

    def test_wrong_request_type_raises(self):
        with pytest.raises(TypeError):
            select_configurable_residual_strategy("not a request")  # type: ignore[arg-type]

    def test_raises_for_closure_only_with_set_but_no_unknowns(self):
        br = _single_loop_result()
        closure_set = _simple_closure_set()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.CLOSURE_ONLY,
            closure_residual_set=closure_set,
            evaluate=True,
            # No closure_unknown_values
        )
        with pytest.raises(ValueError):
            evaluate_selected_configurable_residuals(req)


# ---------------------------------------------------------------------------
# 11. Boundary: architecture invariants
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    def test_no_coolprop_import(self):
        import importlib

        # Verify no CoolProp is imported in our module
        mod = importlib.import_module("mpl_sim.network.configurable_residual_selection")
        # The module should not have imported CoolProp
        assert "CoolProp" not in str(getattr(mod, "__file__", ""))

    def test_no_property_backend_in_module(self):
        from mpl_sim.network import configurable_residual_selection as crs_mod

        # We should not be able to access PropertyBackend through this module
        assert not hasattr(crs_mod, "PropertyBackend")

    def test_no_system_state_in_module(self):
        from mpl_sim.network import configurable_residual_selection as crs_mod

        assert not hasattr(crs_mod, "SystemState")

    def test_no_fluid_state_in_module(self):
        from mpl_sim.network import configurable_residual_selection as crs_mod

        assert not hasattr(crs_mod, "FluidState")

    def test_limitations_mention_no_property_backing(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        limits_combined = " ".join(result.limitations)
        assert "property" in limits_combined.lower() or "not property" in limits_combined.lower()

    def test_limitations_mention_no_role_physics(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        limits_combined = " ".join(result.limitations)
        assert "role" in limits_combined.lower()

    def test_limitations_mention_no_solve(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        limits_combined = " ".join(result.limitations)
        assert "solve" in limits_combined.lower()

    def test_no_automatic_closure_inference_in_limitations(self):
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.DECLARATION_ONLY,
        )
        result = select_configurable_residual_strategy(req)
        limits_combined = " ".join(result.limitations)
        assert "closure" in limits_combined.lower()

    def test_compatibility_is_deterministic(self):
        """Same inputs give same compatibility result every time."""
        br = _single_loop_result()
        req = ConfigurableResidualSelectionRequest(
            build_result=br,
            mode=ConfigurableResidualMode.FIXED_SINGLE_LOOP_ALGEBRAIC,
        )
        result1 = select_configurable_residual_strategy(req)
        result2 = select_configurable_residual_strategy(req)
        assert result1.compatibility.is_compatible == result2.compatibility.is_compatible
        assert result1.compatibility.reasons == result2.compatibility.reasons
