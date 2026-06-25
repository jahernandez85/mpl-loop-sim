"""Block 15D-C — Combined Closure Integration and Diagnostics tests.

Covers:
  1. CombinedClosureResidualSet construction and validation.
  2. Residual ordering (hydraulic first, thermal second).
  3. Duplicate residual names across domains rejected.
  4. Hydraulic-only and thermal-only partial sets allowed.
  5. Empty set (both None) rejected.
  6. Missing / bad unknown values rejected.
  7. Extra unknowns silently ignored.
  8. Returned maps are read-only (MappingProxyType).
  9. Max-absolute and L2 norms correct.
 10. Combined diagnostics: both domains missing, one sufficient, both sufficient.
 11. Limitations note documents category-presence restriction.
 12. No rank/DAE claim in results or notes.
 13. Report is plain dict and JSON-serializable.
 14. Report includes hydraulic/thermal/combined residuals and norms.
 15. Report includes limitations section.
 16. Report no_solve flag present.
 17. Report with diagnostic section populated correctly.
 18. Boundary: no forbidden imports in this test file.

Architecture invariants confirmed in this file
-----------------------------------------------
No CoolProp, no PropertyBackend, no CorrelationRegistry.
No HX model imports or calls.
No production component imports.
No SystemState, no FluidState.
No contribute( calls.
No least-squares or root-finding.
No file writing.
No pandas.
"""

from __future__ import annotations

import json
import math
import types

import pytest

from mpl_sim.network.closure_integration import (
    ClosureDomain,
    CombinedClosureEvaluationResult,
    CombinedClosureResidualSet,
    build_combined_closure_report,
    build_combined_closure_residuals,
    evaluate_combined_closure_residuals,
    evaluate_combined_closure_sufficiency,
)
from mpl_sim.network.hydraulic_closure_diagnostics import (
    make_two_branch_parallel_diagnostic,
)
from mpl_sim.network.hydraulic_closures import (
    ImposedBranchSplitClosure,
    ImposedMassFlowClosure,
    ImposedPressureClosure,
    LinearPressureDropClosure,
    PressureCompatibilityClosure,
    build_hydraulic_closure_residuals,
)
from mpl_sim.network.thermal_closure_diagnostics import (
    make_basic_thermal_loop_diagnostic,
)
from mpl_sim.network.thermal_closures import (
    EnthalpyFlowHeatRateClosure,
    FixedHeatRateClosure,
    ImposedEnthalpyClosure,
    build_thermal_closure_residuals,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_hydraulic_set():
    return build_hydraulic_closure_residuals(
        [
            ImposedMassFlowClosure(
                unknown_name="mdot_pump",
                imposed_value=1.0,
                residual_name="r_h_total_flow",
            ),
            ImposedBranchSplitClosure(
                total_flow_name="mdot_pump",
                branch_flow_name="mdot_branch_a",
                split_fraction=0.4,
                residual_name="r_h_branch_split",
            ),
        ]
    )


def _make_thermal_set():
    return build_thermal_closure_residuals(
        [
            FixedHeatRateClosure(
                unknown_name="q_elem",
                q_fixed=5000.0,
                residual_name="r_t_heat_rate",
            ),
            EnthalpyFlowHeatRateClosure(
                q_name="q_elem",
                mdot_name="mdot_pump",
                h_in_name="h_in",
                h_out_name="h_out",
                residual_name="r_t_enthalpy_flow",
            ),
        ]
    )


def _make_consistent_unknowns():
    return {
        "mdot_pump": 1.0,
        "mdot_branch_a": 0.4,
        "q_elem": 5000.0,
        "h_in": 200_000.0,
        "h_out": 205_000.0,
    }


# ---------------------------------------------------------------------------
# ClosureDomain enum
# ---------------------------------------------------------------------------


def test_closure_domain_values():
    assert ClosureDomain.HYDRAULIC.value == "hydraulic"
    assert ClosureDomain.THERMAL.value == "thermal"


# ---------------------------------------------------------------------------
# build_combined_closure_residuals — basic construction
# ---------------------------------------------------------------------------


def test_build_combined_from_both_domains():
    h = _make_hydraulic_set()
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    assert combined.hydraulic is h
    assert combined.thermal is t


def test_build_combined_hydraulic_only():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    assert combined.hydraulic is h
    assert combined.thermal is None


def test_build_combined_thermal_only():
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(thermal=t)
    assert combined.hydraulic is None
    assert combined.thermal is t


def test_build_combined_rejects_both_none():
    with pytest.raises(ValueError, match="both are None"):
        build_combined_closure_residuals()


def test_build_combined_wrong_hydraulic_type():
    with pytest.raises(TypeError, match="hydraulic must be a HydraulicClosureResidualSet"):
        build_combined_closure_residuals(hydraulic="bad")


def test_build_combined_wrong_thermal_type():
    with pytest.raises(TypeError, match="thermal must be a ThermalClosureResidualSet"):
        build_combined_closure_residuals(thermal=42)


def test_direct_combined_constructor_rejects_both_none():
    with pytest.raises(ValueError, match="both are None"):
        CombinedClosureResidualSet(hydraulic=None, thermal=None)


def test_direct_combined_constructor_rejects_wrong_hydraulic_type():
    with pytest.raises(TypeError, match="hydraulic must be a HydraulicClosureResidualSet"):
        CombinedClosureResidualSet(hydraulic="bad", thermal=_make_thermal_set())


def test_direct_combined_constructor_rejects_wrong_thermal_type():
    with pytest.raises(TypeError, match="thermal must be a ThermalClosureResidualSet"):
        CombinedClosureResidualSet(hydraulic=_make_hydraulic_set(), thermal=42)


# ---------------------------------------------------------------------------
# Residual ordering — hydraulic first
# ---------------------------------------------------------------------------


def test_combined_residual_names_hydraulic_first():
    h = _make_hydraulic_set()
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    names = combined.residual_names
    h_names = h.residual_names
    t_names = t.residual_names
    assert names[: len(h_names)] == h_names
    assert names[len(h_names) :] == t_names


def test_combined_residual_names_hydraulic_only():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    assert combined.residual_names == h.residual_names


def test_combined_residual_names_thermal_only():
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(thermal=t)
    assert combined.residual_names == t.residual_names


def test_combined_residual_counts():
    h = _make_hydraulic_set()
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    assert combined.hydraulic_count == len(h.closures)
    assert combined.thermal_count == len(t.closures)


def test_combined_residual_counts_hydraulic_only():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    assert combined.hydraulic_count == len(h.closures)
    assert combined.thermal_count == 0


def test_combined_residual_counts_thermal_only():
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(thermal=t)
    assert combined.hydraulic_count == 0
    assert combined.thermal_count == len(t.closures)


# ---------------------------------------------------------------------------
# Duplicate residual names across domains rejected
# ---------------------------------------------------------------------------


def test_duplicate_name_across_domains_rejected():
    h = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot_pump", 1.0, "shared_name")])
    t = build_thermal_closure_residuals([FixedHeatRateClosure("q", 5000.0, "shared_name")])
    with pytest.raises(ValueError, match="duplicate residual names"):
        build_combined_closure_residuals(hydraulic=h, thermal=t)


def test_duplicate_name_includes_the_name_in_message():
    h = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot_pump", 1.0, "clash")])
    t = build_thermal_closure_residuals([FixedHeatRateClosure("q", 5000.0, "clash")])
    with pytest.raises(ValueError, match="clash"):
        build_combined_closure_residuals(hydraulic=h, thermal=t)


def test_direct_combined_constructor_rejects_duplicate_names():
    h = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot_pump", 1.0, "shared_name")])
    t = build_thermal_closure_residuals([FixedHeatRateClosure("q", 5000.0, "shared_name")])
    with pytest.raises(ValueError, match="duplicate residual names"):
        CombinedClosureResidualSet(hydraulic=h, thermal=t)


# ---------------------------------------------------------------------------
# evaluate_all — correct values
# ---------------------------------------------------------------------------


def test_evaluate_all_both_domains_at_consistent_point():
    h = _make_hydraulic_set()
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    unknowns = _make_consistent_unknowns()
    result = combined.evaluate_all(unknowns)
    assert result["r_h_total_flow"] == pytest.approx(0.0)
    assert result["r_h_branch_split"] == pytest.approx(0.0)
    assert result["r_t_heat_rate"] == pytest.approx(0.0)
    assert result["r_t_enthalpy_flow"] == pytest.approx(0.0)


def test_evaluate_all_hydraulic_only():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    unknowns = {"mdot_pump": 1.0, "mdot_branch_a": 0.4}
    result = combined.evaluate_all(unknowns)
    assert result["r_h_total_flow"] == pytest.approx(0.0)
    assert result["r_h_branch_split"] == pytest.approx(0.0)
    assert "r_t_heat_rate" not in result


def test_evaluate_all_thermal_only():
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(thermal=t)
    unknowns = {"q_elem": 5000.0, "mdot_pump": 1.0, "h_in": 200_000.0, "h_out": 205_000.0}
    result = combined.evaluate_all(unknowns)
    assert result["r_t_heat_rate"] == pytest.approx(0.0)
    assert "r_h_total_flow" not in result


# ---------------------------------------------------------------------------
# evaluate_all — returns MappingProxyType (read-only)
# ---------------------------------------------------------------------------


def test_evaluate_all_returns_mapping_proxy_type():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    result = combined.evaluate_all({"mdot_pump": 1.0, "mdot_branch_a": 0.4})
    assert isinstance(result, types.MappingProxyType)


def test_evaluate_all_is_read_only():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    result = combined.evaluate_all({"mdot_pump": 1.0, "mdot_branch_a": 0.4})
    with pytest.raises(TypeError):
        result["r_h_total_flow"] = 999.0  # type: ignore[index]


# ---------------------------------------------------------------------------
# evaluate_all — unknown validation
# ---------------------------------------------------------------------------


def test_missing_hydraulic_unknown_rejected():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    with pytest.raises(KeyError):
        combined.evaluate_all({"mdot_pump": 1.0})  # missing mdot_branch_a


def test_missing_thermal_unknown_rejected():
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(thermal=t)
    with pytest.raises(KeyError):
        combined.evaluate_all({"q_elem": 5000.0, "mdot_pump": 1.0, "h_in": 200_000.0})
        # missing h_out


def test_bool_unknown_value_rejected():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    with pytest.raises(TypeError):
        combined.evaluate_all({"mdot_pump": True, "mdot_branch_a": 0.4})


def test_nan_unknown_value_rejected():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    with pytest.raises(ValueError):
        combined.evaluate_all({"mdot_pump": float("nan"), "mdot_branch_a": 0.4})


def test_inf_unknown_value_rejected():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    with pytest.raises(ValueError):
        combined.evaluate_all({"mdot_pump": float("inf"), "mdot_branch_a": 0.4})


def test_extra_unknowns_silently_ignored():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    unknowns = {
        "mdot_pump": 1.0,
        "mdot_branch_a": 0.4,
        "extra_irrelevant": 999.0,
    }
    result = combined.evaluate_all(unknowns)
    assert result["r_h_total_flow"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# evaluate_combined_closure_residuals
# ---------------------------------------------------------------------------


def test_evaluate_combined_returns_frozen_result():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    result = evaluate_combined_closure_residuals(combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4})
    assert isinstance(result, CombinedClosureEvaluationResult)


def test_evaluate_combined_hydraulic_residuals_populated():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    result = evaluate_combined_closure_residuals(combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4})
    assert "r_h_total_flow" in result.hydraulic_residuals
    assert "r_h_branch_split" in result.hydraulic_residuals


def test_evaluate_combined_thermal_residuals_empty_when_no_thermal():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    result = evaluate_combined_closure_residuals(combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4})
    assert dict(result.thermal_residuals) == {}


def test_evaluate_combined_combined_residuals_contains_all():
    h = _make_hydraulic_set()
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    unknowns = _make_consistent_unknowns()
    result = evaluate_combined_closure_residuals(combined, unknowns)
    for name in h.residual_names:
        assert name in result.combined_residuals
    for name in t.residual_names:
        assert name in result.combined_residuals


def test_evaluate_combined_maps_are_mapping_proxy_type():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    result = evaluate_combined_closure_residuals(combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4})
    assert isinstance(result.hydraulic_residuals, types.MappingProxyType)
    assert isinstance(result.thermal_residuals, types.MappingProxyType)
    assert isinstance(result.combined_residuals, types.MappingProxyType)


def test_evaluate_combined_max_abs_zero_at_consistent_point():
    h = _make_hydraulic_set()
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    unknowns = _make_consistent_unknowns()
    result = evaluate_combined_closure_residuals(combined, unknowns)
    assert result.max_absolute_residual == pytest.approx(0.0)


def test_evaluate_combined_l2_norm_zero_at_consistent_point():
    h = _make_hydraulic_set()
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    unknowns = _make_consistent_unknowns()
    result = evaluate_combined_closure_residuals(combined, unknowns)
    assert result.l2_residual_norm == pytest.approx(0.0)


def test_evaluate_combined_max_abs_correct():
    h = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r_mdot")])
    combined = build_combined_closure_residuals(hydraulic=h)
    result = evaluate_combined_closure_residuals(combined, {"mdot": 3.0})
    assert result.max_absolute_residual == pytest.approx(2.0)
    assert result.l2_residual_norm == pytest.approx(2.0)


def test_evaluate_combined_l2_norm_correct_multi_residuals():
    h = build_hydraulic_closure_residuals(
        [
            ImposedMassFlowClosure("mdot", 1.0, "r1"),
            ImposedPressureClosure("P", 100.0, "r2"),
        ]
    )
    combined = build_combined_closure_residuals(hydraulic=h)
    result = evaluate_combined_closure_residuals(combined, {"mdot": 4.0, "P": 103.0})
    # r1 = 4 - 1 = 3, r2 = 103 - 100 = 3
    assert result.max_absolute_residual == pytest.approx(3.0)
    assert result.l2_residual_norm == pytest.approx(math.sqrt(9.0 + 9.0))


def test_evaluate_combined_domain_counts():
    h = _make_hydraulic_set()
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    result = evaluate_combined_closure_residuals(combined, _make_consistent_unknowns())
    assert result.hydraulic_count == len(h.closures)
    assert result.thermal_count == len(t.closures)


def test_evaluate_combined_metadata_stored():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    result = evaluate_combined_closure_residuals(
        combined,
        {"mdot_pump": 1.0, "mdot_branch_a": 0.4},
        metadata={"source": "test"},
    )
    assert result.metadata is not None
    assert result.metadata["source"] == "test"


def test_evaluate_combined_wrong_type_raises():
    with pytest.raises(TypeError, match="CombinedClosureResidualSet"):
        evaluate_combined_closure_residuals("bad", {})


# ---------------------------------------------------------------------------
# evaluate_combined_closure_sufficiency — diagnostics
# ---------------------------------------------------------------------------


def test_combined_sufficiency_both_sufficient():
    h = build_hydraulic_closure_residuals(
        [
            ImposedMassFlowClosure("mdot", 1.0, "r_h1"),
            ImposedBranchSplitClosure("mdot", "mdot_a", 0.4, "r_h2"),
            ImposedPressureClosure("P", 1e6, "r_h3"),
            LinearPressureDropClosure("P_in", "P_out", "mdot_a", 1000.0, "r_h4"),
            PressureCompatibilityClosure("mdot_a", "mdot_b", 5000.0, 5000.0, "r_h5"),
        ]
    )
    t = build_thermal_closure_residuals(
        [
            FixedHeatRateClosure("q", 5000.0, "r_t1"),
            EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r_t2"),
        ]
    )
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    h_diag = make_two_branch_parallel_diagnostic()
    t_diag = make_basic_thermal_loop_diagnostic()
    result = evaluate_combined_closure_sufficiency(
        combined, hydraulic_diagnostic=h_diag, thermal_diagnostic=t_diag
    )
    assert result.is_sufficient is True
    assert result.hydraulic_result is not None
    assert result.hydraulic_result.is_sufficient is True
    assert result.thermal_result is not None
    assert result.thermal_result.is_sufficient is True


def test_combined_sufficiency_hydraulic_missing_thermal_sufficient():
    h = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r_h1")])
    t = build_thermal_closure_residuals(
        [
            FixedHeatRateClosure("q", 5000.0, "r_t1"),
            EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r_t2"),
        ]
    )
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    h_diag = make_two_branch_parallel_diagnostic()
    t_diag = make_basic_thermal_loop_diagnostic()
    result = evaluate_combined_closure_sufficiency(
        combined, hydraulic_diagnostic=h_diag, thermal_diagnostic=t_diag
    )
    assert result.is_sufficient is False
    assert result.hydraulic_result.is_sufficient is False
    assert result.thermal_result.is_sufficient is True


def test_combined_sufficiency_thermal_missing_hydraulic_sufficient():
    h = build_hydraulic_closure_residuals(
        [
            ImposedMassFlowClosure("mdot", 1.0, "r_h1"),
            ImposedBranchSplitClosure("mdot", "mdot_a", 0.4, "r_h2"),
            ImposedPressureClosure("P", 1e6, "r_h3"),
            LinearPressureDropClosure("P_in", "P_out", "mdot_a", 1000.0, "r_h4"),
            PressureCompatibilityClosure("mdot_a", "mdot_b", 5000.0, 5000.0, "r_h5"),
        ]
    )
    t = build_thermal_closure_residuals([ImposedEnthalpyClosure("h_ref", 200_000.0, "r_t1")])
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    h_diag = make_two_branch_parallel_diagnostic()
    t_diag = make_basic_thermal_loop_diagnostic()
    result = evaluate_combined_closure_sufficiency(
        combined, hydraulic_diagnostic=h_diag, thermal_diagnostic=t_diag
    )
    assert result.is_sufficient is False
    assert result.hydraulic_result.is_sufficient is True
    assert result.thermal_result.is_sufficient is False


def test_combined_sufficiency_both_missing():
    h = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r_h1")])
    t = build_thermal_closure_residuals([ImposedEnthalpyClosure("h_ref", 200_000.0, "r_t1")])
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    h_diag = make_two_branch_parallel_diagnostic()
    t_diag = make_basic_thermal_loop_diagnostic()
    result = evaluate_combined_closure_sufficiency(
        combined, hydraulic_diagnostic=h_diag, thermal_diagnostic=t_diag
    )
    assert result.is_sufficient is False
    assert result.hydraulic_result.is_sufficient is False
    assert result.thermal_result.is_sufficient is False


def test_combined_sufficiency_no_diagnostics_supplied():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    result = evaluate_combined_closure_sufficiency(combined)
    assert result.is_sufficient is True
    assert result.hydraulic_result is None
    assert result.thermal_result is None


def test_combined_sufficiency_limitations_note_present():
    combined = build_combined_closure_residuals(hydraulic=_make_hydraulic_set())
    result = evaluate_combined_closure_sufficiency(combined)
    assert isinstance(result.limitations_note, str)
    assert len(result.limitations_note) > 0


def test_combined_sufficiency_limitations_note_no_rank_claim():
    combined = build_combined_closure_residuals(hydraulic=_make_hydraulic_set())
    result = evaluate_combined_closure_sufficiency(combined)
    note_lower = result.limitations_note.lower()
    assert "category-presence" in note_lower or "category" in note_lower
    assert "rank" in note_lower or "solvability" in note_lower or "algebraic" in note_lower


def test_combined_sufficiency_is_sufficient_field_is_bool():
    combined = build_combined_closure_residuals(hydraulic=_make_hydraulic_set())
    result = evaluate_combined_closure_sufficiency(combined)
    assert isinstance(result.is_sufficient, bool)


def test_combined_sufficiency_missing_messages_deterministic():
    h = build_hydraulic_closure_residuals([ImposedMassFlowClosure("mdot", 1.0, "r1")])
    combined = build_combined_closure_residuals(hydraulic=h)
    h_diag = make_two_branch_parallel_diagnostic()
    r1 = evaluate_combined_closure_sufficiency(combined, hydraulic_diagnostic=h_diag)
    r2 = evaluate_combined_closure_sufficiency(combined, hydraulic_diagnostic=h_diag)
    assert r1.hydraulic_result.missing_messages == r2.hydraulic_result.missing_messages


def test_combined_sufficiency_wrong_combined_type():
    with pytest.raises(TypeError, match="CombinedClosureResidualSet"):
        evaluate_combined_closure_sufficiency("bad")


def test_combined_sufficiency_hydraulic_only_with_only_thermal_diagnostic():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    t_diag = make_basic_thermal_loop_diagnostic()
    result = evaluate_combined_closure_sufficiency(combined, thermal_diagnostic=t_diag)
    assert result.hydraulic_result is None
    assert result.thermal_result is None
    assert result.is_sufficient is True


# ---------------------------------------------------------------------------
# build_combined_closure_report
# ---------------------------------------------------------------------------


def test_report_is_dict():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    evaluation = evaluate_combined_closure_residuals(
        combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4}
    )
    report = build_combined_closure_report(evaluation)
    assert isinstance(report, dict)


def test_report_json_serializable():
    h = _make_hydraulic_set()
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    evaluation = evaluate_combined_closure_residuals(combined, _make_consistent_unknowns())
    diagnostic = evaluate_combined_closure_sufficiency(
        combined,
        hydraulic_diagnostic=make_two_branch_parallel_diagnostic(),
        thermal_diagnostic=make_basic_thermal_loop_diagnostic(),
    )
    report = build_combined_closure_report(evaluation, diagnostic)
    serialized = json.dumps(report)
    assert isinstance(serialized, str)
    restored = json.loads(serialized)
    assert isinstance(restored, dict)


def test_report_includes_hydraulic_residuals():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    evaluation = evaluate_combined_closure_residuals(
        combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4}
    )
    report = build_combined_closure_report(evaluation)
    assert "hydraulic" in report["residuals"]
    assert isinstance(report["residuals"]["hydraulic"], dict)


def test_report_includes_thermal_residuals():
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(thermal=t)
    evaluation = evaluate_combined_closure_residuals(
        combined,
        {"q_elem": 5000.0, "mdot_pump": 1.0, "h_in": 200_000.0, "h_out": 205_000.0},
    )
    report = build_combined_closure_report(evaluation)
    assert "thermal" in report["residuals"]
    assert isinstance(report["residuals"]["thermal"], dict)


def test_report_includes_combined_residuals():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    evaluation = evaluate_combined_closure_residuals(
        combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4}
    )
    report = build_combined_closure_report(evaluation)
    assert "combined" in report["residuals"]


def test_report_includes_norms():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    evaluation = evaluate_combined_closure_residuals(
        combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4}
    )
    report = build_combined_closure_report(evaluation)
    assert "norms" in report
    assert "max_absolute" in report["norms"]
    assert "l2" in report["norms"]


def test_report_no_solve_flag():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    evaluation = evaluate_combined_closure_residuals(
        combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4}
    )
    report = build_combined_closure_report(evaluation)
    assert report["no_solve"] is True


def test_report_includes_limitations():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    evaluation = evaluate_combined_closure_residuals(
        combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4}
    )
    report = build_combined_closure_report(evaluation)
    assert "limitations" in report
    limitations = report["limitations"]
    assert isinstance(limitations, list)
    assert len(limitations) > 0
    combined_text = " ".join(str(s) for s in limitations).lower()
    assert "no solve" in combined_text
    assert "production" in combined_text


def test_report_with_diagnostic_section():
    h = build_hydraulic_closure_residuals(
        [
            ImposedMassFlowClosure("mdot", 1.0, "r1"),
            ImposedBranchSplitClosure("mdot", "mdot_a", 0.4, "r2"),
            ImposedPressureClosure("P", 1e6, "r3"),
            LinearPressureDropClosure("P_in", "P_out", "mdot_a", 1000.0, "r4"),
            PressureCompatibilityClosure("mdot_a", "mdot_b", 5000.0, 5000.0, "r5"),
        ]
    )
    t = build_thermal_closure_residuals(
        [
            FixedHeatRateClosure("q", 5000.0, "r_t1"),
            EnthalpyFlowHeatRateClosure("q", "mdot", "h_in", "h_out", "r_t2"),
        ]
    )
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    unknowns = {
        "mdot": 1.0,
        "mdot_a": 0.4,
        "mdot_b": 0.6,
        "P": 1e6,
        "P_in": 1.1e6,
        "P_out": 1.1e6 - 400.0,
        "q": 5000.0,
        "h_in": 200_000.0,
        "h_out": 205_000.0,
    }
    evaluation = evaluate_combined_closure_residuals(combined, unknowns)
    diagnostic = evaluate_combined_closure_sufficiency(
        combined,
        hydraulic_diagnostic=make_two_branch_parallel_diagnostic(),
        thermal_diagnostic=make_basic_thermal_loop_diagnostic(),
    )
    report = build_combined_closure_report(evaluation, diagnostic)
    assert "diagnostic" in report
    assert "is_sufficient" in report["diagnostic"]
    assert "hydraulic" in report["diagnostic"]
    assert "thermal" in report["diagnostic"]


def test_report_wrong_evaluation_type():
    with pytest.raises(TypeError, match="CombinedClosureEvaluationResult"):
        build_combined_closure_report("bad")


def test_report_wrong_diagnostic_type():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    evaluation = evaluate_combined_closure_residuals(
        combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4}
    )
    with pytest.raises(TypeError, match="CombinedClosureDiagnosticResult"):
        build_combined_closure_report(evaluation, "bad")


def test_report_block_field():
    h = _make_hydraulic_set()
    combined = build_combined_closure_residuals(hydraulic=h)
    evaluation = evaluate_combined_closure_residuals(
        combined, {"mdot_pump": 1.0, "mdot_branch_a": 0.4}
    )
    report = build_combined_closure_report(evaluation)
    assert report["block"] == "15D-C"
    assert report["status"] == "evaluation_only"


def test_report_domain_counts():
    h = _make_hydraulic_set()
    t = _make_thermal_set()
    combined = build_combined_closure_residuals(hydraulic=h, thermal=t)
    evaluation = evaluate_combined_closure_residuals(combined, _make_consistent_unknowns())
    report = build_combined_closure_report(evaluation)
    assert report["domain_counts"]["hydraulic"] == len(h.closures)
    assert report["domain_counts"]["thermal"] == len(t.closures)
    assert report["domain_counts"]["total"] == len(h.closures) + len(t.closures)


# ---------------------------------------------------------------------------
# Boundary: no forbidden imports used in this test
# ---------------------------------------------------------------------------


def _get_import_lines(filepath: str) -> list[str]:
    with open(filepath, encoding="utf-8") as fh:
        lines = fh.readlines()
    return [
        line.rstrip()
        for line in lines
        if line.strip().startswith(("import ", "from ")) and not line.strip().startswith("#")
    ]


def test_boundary_no_coolprop_import_in_module():
    import mpl_sim.network.closure_integration as ci

    import_lines = _get_import_lines(ci.__file__)
    import_text = "\n".join(import_lines)
    assert "CoolProp" not in import_text
    assert "PropertyBackend" not in import_text
    assert "CorrelationRegistry" not in import_text


def test_boundary_no_pandas_import_in_module():
    import mpl_sim.network.closure_integration as ci

    import_lines = _get_import_lines(ci.__file__)
    import_text = "\n".join(import_lines)
    assert "pandas" not in import_text


def test_boundary_no_solve_implementation_in_module():
    import mpl_sim.network.closure_integration as ci

    with open(ci.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "def solve(" not in text
    assert "least_squares" not in text
    assert "fsolve" not in text
    assert "lstsq" not in text
