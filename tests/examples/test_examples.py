"""Smoke tests for all example scripts in examples/.

Coverage:
 1. All example scripts can be imported without side effects.
 2. All example scripts run end-to-end as standalone scripts (exit code 0).
 3. Examples import from public package APIs only (not private modules).
 4. Examples produce expected diagnostics (heat signs, convergence flags).
 5. Examples do not write files.
 6. Examples do not require external data or internet.
 7. Phase 12A minimal loop tests continue to pass (suite-level gate).
 8. Example file references used in tests match actual filenames.
 9. No example makes false claims about validation or full-loop convergence.

Architecture constraints:
  - No CoolProp, no PropertyBackend, no Network, no Solver.
  - All examples import from mpl_sim public packages only.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_example(filename: str) -> types.ModuleType:
    """Import an example script as a module (runs top-level code)."""
    spec = importlib.util.spec_from_file_location(
        filename.removesuffix(".py"), EXAMPLES_DIR / filename
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _run_example(filename: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run an example script as __main__ and return the result."""
    script = EXAMPLES_DIR / filename
    env = os.environ.copy()
    pythonpath = [str(REPO_ROOT), str(REPO_ROOT / "src")]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=cwd,
        env=env,
    )


# ---------------------------------------------------------------------------
# 1+8 — files exist and have expected names
# ---------------------------------------------------------------------------


class TestExampleFilesExist:
    def test_minimal_loop_exists(self) -> None:
        assert (EXAMPLES_DIR / "minimal_evaporator_condenser_loop.py").is_file()

    def test_fixed_heat_rate_hx_exists(self) -> None:
        assert (EXAMPLES_DIR / "fixed_heat_rate_hx.py").is_file()

    def test_segmented_counterflow_hx_exists(self) -> None:
        assert (EXAMPLES_DIR / "segmented_counterflow_hx.py").is_file()

    def test_minimal_closed_mpl_solver_exists(self) -> None:
        assert (EXAMPLES_DIR / "minimal_closed_mpl_solver.py").is_file()

    def test_minimal_pressure_closure_exists(self) -> None:
        assert (EXAMPLES_DIR / "minimal_pressure_closure.py").is_file()

    def test_examples_readme_exists(self) -> None:
        docs = (
            REPO_ROOT / "README.md",
            EXAMPLES_DIR / "README.md",
            REPO_ROOT / "docs" / "user_guide" / "QUICKSTART.md",
            REPO_ROOT / "docs" / "user_guide" / "EXAMPLES.md",
        )
        for doc in docs:
            text = doc.read_text(encoding="utf-8")
            for filename in (
                "minimal_evaporator_condenser_loop.py",
                "fixed_heat_rate_hx.py",
                "segmented_counterflow_hx.py",
                "minimal_closed_mpl_solver.py",
                "minimal_pressure_closure.py",
            ):
                assert filename in text, f"{doc} does not reference {filename}"
                assert (EXAMPLES_DIR / filename).is_file()


# ---------------------------------------------------------------------------
# 1 — examples can be imported without side effects from the package
# ---------------------------------------------------------------------------


class TestExampleImports:
    def test_minimal_loop_importable_from_package(self) -> None:
        from examples.minimal_evaporator_condenser_loop import (  # noqa: F401
            MinimalLoopResult,
            evaluate_minimal_evaporator_condenser_loop,
        )

    def test_fixed_heat_rate_hx_importable(self) -> None:
        mod = _import_example("fixed_heat_rate_hx.py")
        assert callable(mod.evaluate_example)
        assert not hasattr(mod, "result")

    def test_segmented_counterflow_hx_importable(self) -> None:
        mod = _import_example("segmented_counterflow_hx.py")
        assert callable(mod.evaluate_example)
        assert not hasattr(mod, "result")

    def test_minimal_closed_mpl_solver_importable(self) -> None:
        mod = _import_example("minimal_closed_mpl_solver.py")
        # All logic is under __main__; importing must succeed with no side effects.
        assert not hasattr(mod, "result")

    def test_minimal_pressure_closure_importable(self) -> None:
        mod = _import_example("minimal_pressure_closure.py")
        # All logic is under __main__; importing must succeed with no side effects.
        assert not hasattr(mod, "result")


# ---------------------------------------------------------------------------
# 2 — examples run as standalone scripts (exit code 0)
# ---------------------------------------------------------------------------


class TestExampleRuns:
    def test_minimal_loop_runs(self) -> None:
        proc = _run_example("minimal_evaporator_condenser_loop.py")
        assert proc.returncode == 0, proc.stderr

    def test_fixed_heat_rate_hx_runs(self) -> None:
        proc = _run_example("fixed_heat_rate_hx.py")
        assert proc.returncode == 0, proc.stderr

    def test_segmented_counterflow_hx_runs(self) -> None:
        proc = _run_example("segmented_counterflow_hx.py")
        assert proc.returncode == 0, proc.stderr

    def test_minimal_closed_mpl_solver_runs(self) -> None:
        proc = _run_example("minimal_closed_mpl_solver.py")
        assert proc.returncode == 0, proc.stderr

    def test_minimal_pressure_closure_runs(self) -> None:
        proc = _run_example("minimal_pressure_closure.py")
        assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# 3 — public API imports only (no private module imports)
# ---------------------------------------------------------------------------


class TestPublicAPIOnly:
    """Examples must import from mpl_sim top-level packages, not internals."""

    _public_packages = {
        "mpl_sim.closed_loop",
        "mpl_sim.components",
        "mpl_sim.core",
        "mpl_sim.correlations",
        "mpl_sim.discretization",
        "mpl_sim.geometry",
        "mpl_sim.hx_models",
    }

    def _check(self, filename: str) -> None:
        text = (EXAMPLES_DIR / filename).read_text(encoding="utf-8")
        tree = ast.parse(text, filename=filename)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("mpl_sim"):
                    assert (
                        node.module in self._public_packages
                    ), f"{filename} imports private package path {node.module!r}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("mpl_sim"):
                        assert (
                            alias.name in self._public_packages
                        ), f"{filename} imports private package path {alias.name!r}"

    def test_minimal_loop_public_api(self) -> None:
        self._check("minimal_evaporator_condenser_loop.py")

    def test_fixed_heat_rate_hx_public_api(self) -> None:
        self._check("fixed_heat_rate_hx.py")

    def test_segmented_counterflow_hx_public_api(self) -> None:
        self._check("segmented_counterflow_hx.py")

    def test_minimal_closed_mpl_solver_public_api(self) -> None:
        self._check("minimal_closed_mpl_solver.py")

    def test_minimal_pressure_closure_public_api(self) -> None:
        self._check("minimal_pressure_closure.py")


# ---------------------------------------------------------------------------
# 4 — examples produce expected diagnostics
# ---------------------------------------------------------------------------


class TestExampleDiagnostics:
    def test_fixed_heat_rate_q_correct_sign(self) -> None:
        mod = _import_example("fixed_heat_rate_hx.py")
        result = mod.evaluate_example()
        assert result.Q > 0, "FixedHeatRate evaporator Q must be positive (heats primary)"

    def test_fixed_heat_rate_enthalpy_increases(self) -> None:
        mod = _import_example("fixed_heat_rate_hx.py")
        result = mod.evaluate_example()
        assert result.primary_state_out.h > mod.INLET_H_JKG

    def test_fixed_heat_rate_dh_equals_q_over_mdot(self) -> None:
        mod = _import_example("fixed_heat_rate_hx.py")
        result = mod.evaluate_example()
        expected_dh = result.Q / mod.PRIMARY_MDOT
        actual_dh = result.primary_state_out.h - mod.INLET_H_JKG
        assert abs(actual_dh - expected_dh) < 1e-6

    def test_segmented_counterflow_converged(self) -> None:
        mod = _import_example("segmented_counterflow_hx.py")
        assert mod.evaluate_example().converged is True

    def test_segmented_counterflow_positive_q(self) -> None:
        mod = _import_example("segmented_counterflow_hx.py")
        assert mod.evaluate_example().Q > 0

    def test_segmented_counterflow_iteration_count_positive(self) -> None:
        mod = _import_example("segmented_counterflow_hx.py")
        assert mod.evaluate_example().iteration_count >= 1

    def test_segmented_counterflow_residual_finite(self) -> None:
        import math

        mod = _import_example("segmented_counterflow_hx.py")
        result = mod.evaluate_example()
        assert result.residual is not None
        assert math.isfinite(result.residual)
        assert result.residual >= 0.0

    def test_segmented_counterflow_all_verdicts_in_envelope(self) -> None:
        from mpl_sim.correlations import ValidityStatus

        mod = _import_example("segmented_counterflow_hx.py")
        for v in mod.evaluate_example().verdicts:
            assert (
                v.verdict.status is ValidityStatus.IN_ENVELOPE
            ), f"Verdict not IN_ENVELOPE: {v.metadata.name} → {v.verdict.status}"

    def test_segmented_counterflow_zone_profile_has_cells(self) -> None:
        mod = _import_example("segmented_counterflow_hx.py")
        result = mod.evaluate_example()
        assert result.zone_profile is not None
        assert len(result.zone_profile.cells) == mod.N_CELLS


# ---------------------------------------------------------------------------
# 5 — examples do not write files
# ---------------------------------------------------------------------------


class TestExamplesDoNotWriteFiles:
    def _check(self, filename: str, tmp_path: Path) -> None:
        before = set(tmp_path.iterdir())
        proc = _run_example(filename, cwd=tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert set(tmp_path.iterdir()) == before

    def test_minimal_loop_no_file_writes(self, tmp_path: Path) -> None:
        self._check("minimal_evaporator_condenser_loop.py", tmp_path)

    def test_fixed_heat_rate_hx_no_file_writes(self, tmp_path: Path) -> None:
        self._check("fixed_heat_rate_hx.py", tmp_path)

    def test_segmented_counterflow_hx_no_file_writes(self, tmp_path: Path) -> None:
        self._check("segmented_counterflow_hx.py", tmp_path)

    def test_minimal_closed_mpl_solver_no_file_writes(self, tmp_path: Path) -> None:
        self._check("minimal_closed_mpl_solver.py", tmp_path)

    def test_minimal_pressure_closure_no_file_writes(self, tmp_path: Path) -> None:
        self._check("minimal_pressure_closure.py", tmp_path)


# ---------------------------------------------------------------------------
# 6 — examples do not use external data or internet
# ---------------------------------------------------------------------------


class TestExamplesNoExternalDependencies:
    # Patterns indicating actual import/use, not just documentation mentions.
    _external_imports = ["import requests", "import urllib", "import CoolProp", "import socket"]

    def _check(self, filename: str) -> None:
        text = (EXAMPLES_DIR / filename).read_text(encoding="utf-8")
        for marker in self._external_imports:
            assert marker not in text, f"{filename} imports external dependency: '{marker}'"

    def test_minimal_loop_no_external(self) -> None:
        self._check("minimal_evaporator_condenser_loop.py")

    def test_fixed_heat_rate_hx_no_external(self) -> None:
        self._check("fixed_heat_rate_hx.py")

    def test_segmented_counterflow_hx_no_external(self) -> None:
        self._check("segmented_counterflow_hx.py")

    def test_minimal_closed_mpl_solver_no_external(self) -> None:
        self._check("minimal_closed_mpl_solver.py")

    def test_minimal_pressure_closure_no_external(self) -> None:
        self._check("minimal_pressure_closure.py")


# ---------------------------------------------------------------------------
# 9 — no example asserts validation or full-loop convergence as achieved
# ---------------------------------------------------------------------------


class TestExamplesHonestClaims:
    # These are POSITIVE claims — the docstrings already disclaim these things
    # using "not" / "is not", so checking for the raw phrase could false-positive.
    # Instead check for phrasing that asserts the capability as present.
    _positive_claims = [
        "is a validated",
        "is validated against",
        "is a converged loop solution",
        "is a full network solver",
        "complete simulator",
        "implements automatic phase inference",
        "supports automatic phase inference",
    ]

    def _check(self, filename: str) -> None:
        text = (EXAMPLES_DIR / filename).read_text(encoding="utf-8").lower()
        for claim in self._positive_claims:
            assert claim not in text, f"{filename} makes an unsupported claim: '{claim}'"

    def test_minimal_loop_honest_claims(self) -> None:
        self._check("minimal_evaporator_condenser_loop.py")

    def test_fixed_heat_rate_hx_honest_claims(self) -> None:
        self._check("fixed_heat_rate_hx.py")

    def test_segmented_counterflow_hx_honest_claims(self) -> None:
        self._check("segmented_counterflow_hx.py")

    def test_minimal_loop_states_not_converged(self) -> None:
        text = (EXAMPLES_DIR / "minimal_evaporator_condenser_loop.py").read_text(encoding="utf-8")
        assert "not a converged" in text.lower() or "not full" in text.lower()

    def test_fixed_heat_rate_states_not_validated(self) -> None:
        text = (EXAMPLES_DIR / "fixed_heat_rate_hx.py").read_text(encoding="utf-8")
        assert "not a validated" in text.lower()

    def test_segmented_counterflow_states_not_validated(self) -> None:
        text = (EXAMPLES_DIR / "segmented_counterflow_hx.py").read_text(encoding="utf-8")
        assert "not a validated" in text.lower()

    def test_minimal_closed_mpl_solver_honest_claims(self) -> None:
        self._check("minimal_closed_mpl_solver.py")

    def test_minimal_closed_mpl_solver_states_not_generic(self) -> None:
        text = (EXAMPLES_DIR / "minimal_closed_mpl_solver.py").read_text(encoding="utf-8")
        assert "not a generic" in text.lower()

    def test_minimal_pressure_closure_honest_claims(self) -> None:
        self._check("minimal_pressure_closure.py")

    def test_minimal_pressure_closure_states_not_generic(self) -> None:
        text = (EXAMPLES_DIR / "minimal_pressure_closure.py").read_text(encoding="utf-8")
        assert "not a generic" in text.lower()

    def test_minimal_pressure_closure_states_not_validated(self) -> None:
        text = (EXAMPLES_DIR / "minimal_pressure_closure.py").read_text(encoding="utf-8")
        assert "not a validated" in text.lower()


# ---------------------------------------------------------------------------
# Phase 13A — closed-loop solver output diagnostics
# ---------------------------------------------------------------------------


class TestPhase13AMinimalClosedSolverDiagnostics:
    """Run the Phase 13A example as a script and inspect its stdout."""

    def test_converged_reported(self) -> None:
        proc = _run_example("minimal_closed_mpl_solver.py")
        assert "Converged:          True" in proc.stdout

    def test_energy_residual_small(self) -> None:
        import re

        proc = _run_example("minimal_closed_mpl_solver.py")
        m = re.search(r"Energy residual:\s+([+-]?\d+\.\d+e[+-]\d+)", proc.stdout)
        assert m is not None, "Energy residual line not found in output"
        residual = float(m.group(1))
        assert abs(residual) < 1.0, f"Residual too large: {residual}"

    def test_solved_q_cond_near_minus_q_evap(self) -> None:
        import re

        proc = _run_example("minimal_closed_mpl_solver.py")
        m = re.search(r"Solved Q_cond:\s+([+-]?\d+\.\d+)", proc.stdout)
        assert m is not None, "Solved Q_cond line not found in output"
        q_cond = float(m.group(1))
        assert abs(q_cond - (-1000.0)) < 1.0, f"Q_cond not near -1000 W: {q_cond}"

    def test_pressure_note_present(self) -> None:
        proc = _run_example("minimal_closed_mpl_solver.py")
        assert "Pressure closure is NOT implemented" in proc.stdout


# ---------------------------------------------------------------------------
# Phase 13B — pressure closure solver output diagnostics
# ---------------------------------------------------------------------------


class TestPhase13BMinimalPressureClosureDiagnostics:
    """Run the Phase 13B example as a script and inspect its stdout."""

    def test_converged_reported(self) -> None:
        proc = _run_example("minimal_pressure_closure.py")
        assert "Converged:            True" in proc.stdout

    def test_pressure_residual_small(self) -> None:
        import re

        proc = _run_example("minimal_pressure_closure.py")
        m = re.search(r"Pressure residual:\s+([+-]?\d+\.\d+e[+-]\d+)", proc.stdout)
        assert m is not None, "Pressure residual line not found in output"
        residual = float(m.group(1))
        assert abs(residual) < 1.0, f"Pressure residual too large: {residual} Pa"

    def test_solved_mdot_near_analytical(self) -> None:
        import re

        proc = _run_example("minimal_pressure_closure.py")
        m = re.search(r"Solved primary_mdot:\s+([0-9.]+)", proc.stdout)
        assert m is not None, "Solved primary_mdot line not found in output"
        mdot = float(m.group(1))
        assert abs(mdot - 0.05) < 1e-3, f"Solved mdot not near 0.05 kg/s: {mdot}"

    def test_energy_residual_reported_not_solved(self) -> None:
        proc = _run_example("minimal_pressure_closure.py")
        assert "Energy residual" in proc.stdout or "energy residual" in proc.stdout.lower()
        # Energy residual should be non-zero (diagnostic, not solved).
        assert "NOT solved" in proc.stdout or "diagnostic" in proc.stdout.lower()

    def test_fixed_architecture_note_present(self) -> None:
        proc = _run_example("minimal_pressure_closure.py")
        assert "fixed architecture" in proc.stdout.lower() or "Phase 13B" in proc.stdout
