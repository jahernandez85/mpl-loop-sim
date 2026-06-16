"""Solver contract primitive tests — Phase 8A/8D.

Covers:
  SolverId — construction, non-empty validation, hashable, immutable.
  SolverStatus — all five status values present.
  SolverOptions — construction, tolerance/max_iterations/relaxation validation.
  SolverReport — construction, finite residual_norm validation, immutable.
  SolverResult — construction, immutable.
  ConvergenceStrategy — all four values present (Phase 8D).
  ConvergenceMetadata — construction, validation, immutability (Phase 8D).
  SolverReport with convergence_metadata (Phase 8D).

Import-boundary assertions:
  solvers/base.py must not import CoolProp, properties, correlations,
  calibration, network, or components.
  network package must not import solvers.
  components package must not import solvers.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from mpl_sim.core.state import StateLayout, StateVariableId, SystemState, VariableKind
from mpl_sim.solvers.base import (
    ConvergenceMetadata,
    ConvergenceStrategy,
    SolverId,
    SolverOptions,
    SolverReport,
    SolverResult,
    SolverStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_state() -> SystemState:
    var = StateVariableId(VariableKind.P, "comp", "port")
    layout = StateLayout([var])
    return SystemState(layout, [1.0])


def _source(module_name: str) -> str:
    import importlib

    mod = importlib.import_module(module_name)
    return Path(mod.__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]


def _import_lines(module_name: str) -> list[str]:
    """Return only the import-statement lines from a module's source file."""
    src = _source(module_name)
    return [
        line.strip() for line in src.splitlines() if line.strip().startswith(("import ", "from "))
    ]


# ---------------------------------------------------------------------------
# SolverId
# ---------------------------------------------------------------------------


class TestSolverId:
    def test_construction_stores_name(self) -> None:
        sid = SolverId(name="fixed_point")
        assert sid.name == "fixed_point"

    def test_structural_equality(self) -> None:
        assert SolverId("fixed_point") == SolverId("fixed_point")
        assert SolverId("fixed_point") != SolverId("newton")

    def test_is_hashable(self) -> None:
        sid = SolverId("fixed_point")
        d = {sid: 1}
        assert d[SolverId("fixed_point")] == 1

    def test_usable_in_set(self) -> None:
        s = {SolverId("a"), SolverId("b"), SolverId("a")}
        assert len(s) == 2

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            SolverId(name="")

    def test_is_immutable(self) -> None:
        sid = SolverId(name="fixed_point")
        with pytest.raises((AttributeError, TypeError)):
            sid.name = "other"  # type: ignore[misc]

    def test_repr_contains_name(self) -> None:
        sid = SolverId("my_solver")
        assert "my_solver" in repr(sid)


# ---------------------------------------------------------------------------
# SolverStatus
# ---------------------------------------------------------------------------


class TestSolverStatus:
    def test_not_started_exists(self) -> None:
        assert SolverStatus.NOT_STARTED is not None

    def test_converged_exists(self) -> None:
        assert SolverStatus.CONVERGED is not None

    def test_failed_exists(self) -> None:
        assert SolverStatus.FAILED is not None

    def test_max_iterations_exists(self) -> None:
        assert SolverStatus.MAX_ITERATIONS is not None

    def test_invalid_problem_exists(self) -> None:
        assert SolverStatus.INVALID_PROBLEM is not None

    def test_all_five_values_present(self) -> None:
        names = {s.name for s in SolverStatus}
        assert names == {
            "NOT_STARTED",
            "CONVERGED",
            "FAILED",
            "MAX_ITERATIONS",
            "INVALID_PROBLEM",
        }

    def test_members_are_distinct(self) -> None:
        all_statuses = list(SolverStatus)
        assert len(all_statuses) == len(set(all_statuses))

    def test_string_values(self) -> None:
        for status in SolverStatus:
            assert isinstance(status.value, str)

    def test_identity_by_member(self) -> None:
        assert SolverStatus.CONVERGED is SolverStatus.CONVERGED
        assert SolverStatus.CONVERGED is not SolverStatus.FAILED


# ---------------------------------------------------------------------------
# SolverOptions
# ---------------------------------------------------------------------------


class TestSolverOptions:
    def test_construction_minimal(self) -> None:
        opts = SolverOptions(tolerance=1e-6, max_iterations=100)
        assert opts.tolerance == 1e-6
        assert opts.max_iterations == 100
        assert opts.relaxation is None

    def test_construction_with_relaxation(self) -> None:
        opts = SolverOptions(tolerance=1e-4, max_iterations=50, relaxation=0.8)
        assert opts.relaxation == 0.8

    def test_rejects_zero_tolerance(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            SolverOptions(tolerance=0.0, max_iterations=100)

    def test_rejects_negative_tolerance(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            SolverOptions(tolerance=-1e-6, max_iterations=100)

    def test_rejects_zero_max_iterations(self) -> None:
        with pytest.raises(ValueError, match="max_iterations"):
            SolverOptions(tolerance=1e-6, max_iterations=0)

    def test_rejects_negative_max_iterations(self) -> None:
        with pytest.raises(ValueError, match="max_iterations"):
            SolverOptions(tolerance=1e-6, max_iterations=-1)

    def test_rejects_zero_relaxation(self) -> None:
        with pytest.raises(ValueError, match="relaxation"):
            SolverOptions(tolerance=1e-6, max_iterations=100, relaxation=0.0)

    def test_rejects_negative_relaxation(self) -> None:
        with pytest.raises(ValueError, match="relaxation"):
            SolverOptions(tolerance=1e-6, max_iterations=100, relaxation=-0.5)

    def test_none_relaxation_accepted(self) -> None:
        opts = SolverOptions(tolerance=1e-6, max_iterations=100, relaxation=None)
        assert opts.relaxation is None

    def test_is_immutable(self) -> None:
        opts = SolverOptions(tolerance=1e-6, max_iterations=100)
        with pytest.raises((AttributeError, TypeError)):
            opts.tolerance = 1e-3  # type: ignore[misc]

    def test_structural_equality(self) -> None:
        a = SolverOptions(tolerance=1e-6, max_iterations=100)
        b = SolverOptions(tolerance=1e-6, max_iterations=100)
        assert a == b

    def test_different_tolerance_not_equal(self) -> None:
        a = SolverOptions(tolerance=1e-6, max_iterations=100)
        b = SolverOptions(tolerance=1e-4, max_iterations=100)
        assert a != b


# ---------------------------------------------------------------------------
# SolverReport
# ---------------------------------------------------------------------------


class TestSolverReport:
    def test_construction(self) -> None:
        report = SolverReport(
            status=SolverStatus.CONVERGED,
            iterations=5,
            residual_norm=1e-8,
            message="OK",
        )
        assert report.status is SolverStatus.CONVERGED
        assert report.iterations == 5
        assert report.residual_norm == pytest.approx(1e-8)
        assert report.message == "OK"

    def test_none_residual_norm_accepted(self) -> None:
        report = SolverReport(
            status=SolverStatus.NOT_STARTED,
            iterations=0,
            residual_norm=None,
            message="not started",
        )
        assert report.residual_norm is None

    def test_zero_residual_norm_accepted(self) -> None:
        report = SolverReport(
            status=SolverStatus.CONVERGED,
            iterations=1,
            residual_norm=0.0,
            message="zero residual",
        )
        assert report.residual_norm == 0.0

    def test_rejects_nan_residual_norm(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            SolverReport(
                status=SolverStatus.FAILED,
                iterations=1,
                residual_norm=float("nan"),
                message="nan",
            )

    def test_rejects_inf_residual_norm(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            SolverReport(
                status=SolverStatus.FAILED,
                iterations=1,
                residual_norm=float("inf"),
                message="inf",
            )

    def test_rejects_neg_inf_residual_norm(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            SolverReport(
                status=SolverStatus.FAILED,
                iterations=1,
                residual_norm=float("-inf"),
                message="-inf",
            )

    def test_is_immutable(self) -> None:
        report = SolverReport(
            status=SolverStatus.CONVERGED,
            iterations=1,
            residual_norm=1e-8,
            message="OK",
        )
        with pytest.raises((AttributeError, TypeError)):
            report.iterations = 99  # type: ignore[misc]

    def test_structural_equality(self) -> None:
        r1 = SolverReport(
            status=SolverStatus.CONVERGED, iterations=5, residual_norm=1e-8, message="OK"
        )
        r2 = SolverReport(
            status=SolverStatus.CONVERGED, iterations=5, residual_norm=1e-8, message="OK"
        )
        assert r1 == r2

    def test_finite_positive_norm_accepted(self) -> None:
        report = SolverReport(
            status=SolverStatus.FAILED,
            iterations=100,
            residual_norm=1.5,
            message="not converged",
        )
        assert math.isfinite(report.residual_norm)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SolverResult
# ---------------------------------------------------------------------------


class TestSolverResult:
    def test_construction_with_state(self) -> None:
        state = _simple_state()
        report = SolverReport(
            status=SolverStatus.CONVERGED,
            iterations=1,
            residual_norm=0.0,
            message="OK",
        )
        result = SolverResult(state=state, report=report)
        assert result.state is state
        assert result.report is report

    def test_construction_with_none_state(self) -> None:
        report = SolverReport(
            status=SolverStatus.INVALID_PROBLEM,
            iterations=0,
            residual_norm=None,
            message="no state available",
        )
        result = SolverResult(state=None, report=report)
        assert result.state is None

    def test_is_immutable(self) -> None:
        state = _simple_state()
        report = SolverReport(
            status=SolverStatus.CONVERGED,
            iterations=1,
            residual_norm=0.0,
            message="OK",
        )
        result = SolverResult(state=state, report=report)
        with pytest.raises((AttributeError, TypeError)):
            result.report = report  # type: ignore[misc]

    def test_report_accessible(self) -> None:
        report = SolverReport(
            status=SolverStatus.MAX_ITERATIONS,
            iterations=200,
            residual_norm=0.05,
            message="did not converge",
        )
        result = SolverResult(state=None, report=report)
        assert result.report.status is SolverStatus.MAX_ITERATIONS
        assert result.report.iterations == 200


# ---------------------------------------------------------------------------
# Import-boundary assertions
# ---------------------------------------------------------------------------


class TestSolverBaseImportBoundaries:
    def _imports(self) -> list[str]:
        return _import_lines("mpl_sim.solvers.base")

    def test_no_coolprop_import(self) -> None:
        imports = self._imports()
        assert not any("coolprop" in line.lower() for line in imports)

    def test_no_properties_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.properties" in line for line in imports)

    def test_no_correlations_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.correlations" in line for line in imports)

    def test_no_calibration_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.calibration" in line for line in imports)

    def test_no_network_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.network" in line for line in imports)

    def test_no_components_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.components" in line for line in imports)

    def test_no_geometry_import(self) -> None:
        imports = self._imports()
        assert not any("mpl_sim.geometry" in line for line in imports)


class TestNetworkDoesNotImportSolvers:
    def test_network_init_does_not_import_solvers(self) -> None:
        imports = _import_lines("mpl_sim.network")
        assert not any("solvers" in line for line in imports)

    def test_network_topology_does_not_import_solvers(self) -> None:
        imports = _import_lines("mpl_sim.network.topology")
        assert not any("solvers" in line for line in imports)

    def test_network_validation_does_not_import_solvers(self) -> None:
        imports = _import_lines("mpl_sim.network.validation")
        assert not any("solvers" in line for line in imports)

    def test_network_assembly_does_not_import_solvers(self) -> None:
        imports = _import_lines("mpl_sim.network.assembly")
        assert not any("solvers" in line for line in imports)


class TestComponentsDoNotImportSolvers:
    def test_components_base_does_not_import_solvers(self) -> None:
        imports = _import_lines("mpl_sim.components.base")
        assert not any("solvers" in line for line in imports)

    def test_pipe_does_not_import_solvers(self) -> None:
        imports = _import_lines("mpl_sim.components.pipe")
        assert not any("solvers" in line for line in imports)


# ---------------------------------------------------------------------------
# ConvergenceStrategy — Phase 8D
# ---------------------------------------------------------------------------


class TestConvergenceStrategy:
    def test_residual_gate_exists(self) -> None:
        assert ConvergenceStrategy.RESIDUAL_GATE is not None

    def test_fixed_point_exists(self) -> None:
        assert ConvergenceStrategy.FIXED_POINT is not None

    def test_newton_exists(self) -> None:
        assert ConvergenceStrategy.NEWTON is not None

    def test_user_provided_exists(self) -> None:
        assert ConvergenceStrategy.USER_PROVIDED is not None

    def test_all_four_values_present(self) -> None:
        names = {s.name for s in ConvergenceStrategy}
        assert names == {"RESIDUAL_GATE", "FIXED_POINT", "NEWTON", "USER_PROVIDED"}

    def test_members_are_distinct(self) -> None:
        all_strategies = list(ConvergenceStrategy)
        assert len(all_strategies) == len(set(all_strategies))

    def test_string_values(self) -> None:
        for strategy in ConvergenceStrategy:
            assert isinstance(strategy.value, str)

    def test_identity_by_member(self) -> None:
        assert ConvergenceStrategy.RESIDUAL_GATE is ConvergenceStrategy.RESIDUAL_GATE
        assert ConvergenceStrategy.RESIDUAL_GATE is not ConvergenceStrategy.NEWTON


# ---------------------------------------------------------------------------
# ConvergenceMetadata — Phase 8D
# ---------------------------------------------------------------------------


def _default_metadata(**overrides) -> ConvergenceMetadata:
    defaults = dict(
        strategy=ConvergenceStrategy.RESIDUAL_GATE,
        tolerance=1e-6,
        max_iterations=100,
        iterations=1,
        converged=True,
        final_residual_norm=0.0,
        message="ok",
    )
    defaults.update(overrides)
    return ConvergenceMetadata(**defaults)


class TestConvergenceMetadata:
    def test_construction(self) -> None:
        meta = _default_metadata()
        assert meta.strategy is ConvergenceStrategy.RESIDUAL_GATE
        assert meta.tolerance == pytest.approx(1e-6)
        assert meta.max_iterations == 100
        assert meta.iterations == 1
        assert meta.converged is True
        assert meta.final_residual_norm == pytest.approx(0.0)
        assert meta.message == "ok"

    def test_optional_fields_default_to_none(self) -> None:
        meta = ConvergenceMetadata(
            strategy=ConvergenceStrategy.RESIDUAL_GATE,
            tolerance=1e-6,
            max_iterations=100,
            iterations=0,
            converged=False,
        )
        assert meta.final_residual_norm is None
        assert meta.message is None

    def test_is_immutable(self) -> None:
        meta = _default_metadata()
        with pytest.raises((AttributeError, TypeError)):
            meta.iterations = 99  # type: ignore[misc]

    def test_rejects_zero_tolerance(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            _default_metadata(tolerance=0.0)

    def test_rejects_negative_tolerance(self) -> None:
        with pytest.raises(ValueError, match="tolerance"):
            _default_metadata(tolerance=-1e-6)

    def test_rejects_zero_max_iterations(self) -> None:
        with pytest.raises(ValueError, match="max_iterations"):
            _default_metadata(max_iterations=0)

    def test_rejects_negative_max_iterations(self) -> None:
        with pytest.raises(ValueError, match="max_iterations"):
            _default_metadata(max_iterations=-1)

    def test_rejects_negative_iterations(self) -> None:
        with pytest.raises(ValueError, match="iterations"):
            _default_metadata(iterations=-1)

    def test_zero_iterations_accepted(self) -> None:
        meta = _default_metadata(iterations=0)
        assert meta.iterations == 0

    def test_rejects_nan_residual_norm(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _default_metadata(final_residual_norm=float("nan"))

    def test_rejects_inf_residual_norm(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            _default_metadata(final_residual_norm=float("inf"))

    def test_rejects_negative_residual_norm(self) -> None:
        with pytest.raises(ValueError, match=">= 0"):
            _default_metadata(final_residual_norm=-1.0)

    def test_zero_residual_norm_accepted(self) -> None:
        meta = _default_metadata(final_residual_norm=0.0)
        assert meta.final_residual_norm == 0.0

    def test_positive_residual_norm_accepted(self) -> None:
        meta = _default_metadata(final_residual_norm=1e-8, converged=False)
        assert math.isfinite(meta.final_residual_norm)  # type: ignore[arg-type]

    def test_none_residual_norm_accepted(self) -> None:
        meta = _default_metadata(final_residual_norm=None)
        assert meta.final_residual_norm is None

    def test_structural_equality(self) -> None:
        m1 = _default_metadata()
        m2 = _default_metadata()
        assert m1 == m2

    def test_different_strategy_not_equal(self) -> None:
        m1 = _default_metadata(strategy=ConvergenceStrategy.RESIDUAL_GATE)
        m2 = _default_metadata(strategy=ConvergenceStrategy.FIXED_POINT)
        assert m1 != m2


# ---------------------------------------------------------------------------
# SolverReport with convergence_metadata — Phase 8D
# ---------------------------------------------------------------------------


class TestSolverReportWithMetadata:
    def test_report_accepts_metadata(self) -> None:
        meta = _default_metadata()
        report = SolverReport(
            status=SolverStatus.CONVERGED,
            iterations=1,
            residual_norm=0.0,
            message="ok",
            convergence_metadata=meta,
        )
        assert report.convergence_metadata is meta

    def test_report_metadata_defaults_to_none(self) -> None:
        report = SolverReport(
            status=SolverStatus.CONVERGED,
            iterations=1,
            residual_norm=0.0,
            message="ok",
        )
        assert report.convergence_metadata is None

    def test_report_with_metadata_is_immutable(self) -> None:
        meta = _default_metadata()
        report = SolverReport(
            status=SolverStatus.CONVERGED,
            iterations=1,
            residual_norm=0.0,
            message="ok",
            convergence_metadata=meta,
        )
        with pytest.raises((AttributeError, TypeError)):
            report.convergence_metadata = None  # type: ignore[misc]

    def test_metadata_strategy_accessible_via_report(self) -> None:
        meta = _default_metadata(strategy=ConvergenceStrategy.RESIDUAL_GATE)
        report = SolverReport(
            status=SolverStatus.CONVERGED,
            iterations=1,
            residual_norm=0.0,
            message="ok",
            convergence_metadata=meta,
        )
        assert report.convergence_metadata is not None
        assert report.convergence_metadata.strategy is ConvergenceStrategy.RESIDUAL_GATE
