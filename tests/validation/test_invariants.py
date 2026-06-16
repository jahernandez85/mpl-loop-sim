"""Tests for validation invariant primitives — Phase 9C.

Covers: InvariantStatus, InvariantKind, ValidationInvariant,
InvariantCheckResult, ValidationReport.
No CoolProp, properties, correlations, components, network, or solvers imported.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.validation.invariants import (
    InvariantCheckResult,
    InvariantKind,
    InvariantStatus,
    ValidationInvariant,
    ValidationReport,
)

# ---------------------------------------------------------------------------
# Import isolation guard
# ---------------------------------------------------------------------------


def test_no_forbidden_imports() -> None:
    import ast

    import mpl_sim.validation.invariants as mod

    with open(mod.__file__, encoding="utf-8") as f:  # type: ignore[arg-type]
        text = f.read()
    tree = ast.parse(text)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.append(node.module)
    forbidden_prefixes = [
        "CoolProp",
        "coolprop",
        "mpl_sim.properties",
        "mpl_sim.correlations",
        "mpl_sim.components",
        "mpl_sim.network",
        "mpl_sim.solvers",
    ]
    for imp in imported:
        for prefix in forbidden_prefixes:
            assert not imp.startswith(prefix), f"Forbidden import: {imp!r}"


# ---------------------------------------------------------------------------
# InvariantStatus
# ---------------------------------------------------------------------------


class TestInvariantStatus:
    def test_all_values_present(self) -> None:
        names = {s.name for s in InvariantStatus}
        assert "OK" in names
        assert "WARNING" in names
        assert "FAILED" in names
        assert "NOT_EVALUATED" in names

    def test_is_enum(self) -> None:
        import enum

        assert isinstance(InvariantStatus.OK, enum.Enum)


# ---------------------------------------------------------------------------
# InvariantKind
# ---------------------------------------------------------------------------


class TestInvariantKind:
    def test_all_values_present(self) -> None:
        names = {k.name for k in InvariantKind}
        assert "MASS_BALANCE" in names
        assert "ENERGY_BALANCE" in names
        assert "PRESSURE_CLOSURE" in names
        assert "STATE_BOUNDS" in names
        assert "CUSTOM" in names

    def test_is_enum(self) -> None:
        import enum

        assert isinstance(InvariantKind.MASS_BALANCE, enum.Enum)


# ---------------------------------------------------------------------------
# ValidationInvariant
# ---------------------------------------------------------------------------


class TestValidationInvariant:
    def test_basic_construction(self) -> None:
        inv = ValidationInvariant(
            kind=InvariantKind.MASS_BALANCE,
            name="global_mass",
            tolerance=1e-6,
        )
        assert inv.kind is InvariantKind.MASS_BALANCE
        assert inv.name == "global_mass"
        assert inv.tolerance == 1e-6
        assert inv.units is None
        assert inv.description is None

    def test_with_optional_fields(self) -> None:
        inv = ValidationInvariant(
            kind=InvariantKind.ENERGY_BALANCE,
            name="global_energy",
            tolerance=1e-3,
            units="W",
            description="Net power balance",
        )
        assert inv.units == "W"
        assert inv.description == "Net power balance"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name must be non-empty"):
            ValidationInvariant(kind=InvariantKind.MASS_BALANCE, name="", tolerance=1e-6)

    def test_negative_tolerance_rejected(self) -> None:
        with pytest.raises(ValueError, match="tolerance must be >= 0"):
            ValidationInvariant(kind=InvariantKind.MASS_BALANCE, name="m", tolerance=-1e-6)

    def test_nan_tolerance_rejected(self) -> None:
        with pytest.raises(ValueError, match="tolerance must be finite"):
            ValidationInvariant(kind=InvariantKind.MASS_BALANCE, name="m", tolerance=math.nan)

    def test_inf_tolerance_rejected(self) -> None:
        with pytest.raises(ValueError, match="tolerance must be finite"):
            ValidationInvariant(kind=InvariantKind.MASS_BALANCE, name="m", tolerance=math.inf)

    def test_zero_tolerance_allowed(self) -> None:
        inv = ValidationInvariant(kind=InvariantKind.STATE_BOUNDS, name="bounds", tolerance=0.0)
        assert inv.tolerance == 0.0

    def test_immutable(self) -> None:
        inv = ValidationInvariant(kind=InvariantKind.CUSTOM, name="c", tolerance=1.0)
        with pytest.raises(Exception):
            inv.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# InvariantCheckResult
# ---------------------------------------------------------------------------


class TestInvariantCheckResult:
    def _inv(self) -> ValidationInvariant:
        return ValidationInvariant(kind=InvariantKind.MASS_BALANCE, name="mass", tolerance=1e-6)

    def test_basic_construction(self) -> None:
        result = InvariantCheckResult(
            invariant=self._inv(),
            residual=5e-8,
            tolerance=1e-6,
            status=InvariantStatus.OK,
        )
        assert result.residual == 5e-8
        assert result.status is InvariantStatus.OK
        assert result.message is None

    def test_with_message(self) -> None:
        result = InvariantCheckResult(
            invariant=self._inv(),
            residual=2e-3,
            tolerance=1e-6,
            status=InvariantStatus.FAILED,
            message="Mass imbalance exceeds tolerance",
        )
        assert result.message == "Mass imbalance exceeds tolerance"

    def test_nan_residual_rejected(self) -> None:
        with pytest.raises(ValueError, match="residual must be finite"):
            InvariantCheckResult(
                invariant=self._inv(),
                residual=math.nan,
                tolerance=1e-6,
                status=InvariantStatus.FAILED,
            )

    def test_inf_residual_rejected(self) -> None:
        with pytest.raises(ValueError, match="residual must be finite"):
            InvariantCheckResult(
                invariant=self._inv(),
                residual=math.inf,
                tolerance=1e-6,
                status=InvariantStatus.FAILED,
            )

    def test_negative_inf_residual_rejected(self) -> None:
        with pytest.raises(ValueError, match="residual must be finite"):
            InvariantCheckResult(
                invariant=self._inv(),
                residual=-math.inf,
                tolerance=1e-6,
                status=InvariantStatus.FAILED,
            )

    def test_negative_tolerance_rejected(self) -> None:
        with pytest.raises(ValueError, match="tolerance must be >= 0"):
            InvariantCheckResult(
                invariant=self._inv(),
                residual=1e-8,
                tolerance=-1.0,
                status=InvariantStatus.OK,
            )

    def test_zero_residual_ok(self) -> None:
        result = InvariantCheckResult(
            invariant=self._inv(),
            residual=0.0,
            tolerance=1e-6,
            status=InvariantStatus.OK,
        )
        assert result.residual == 0.0

    def test_immutable(self) -> None:
        result = InvariantCheckResult(
            invariant=self._inv(),
            residual=0.0,
            tolerance=1e-6,
            status=InvariantStatus.OK,
        )
        with pytest.raises(Exception):
            result.residual = 1.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------


def _inv(name: str = "test") -> ValidationInvariant:
    return ValidationInvariant(kind=InvariantKind.MASS_BALANCE, name=name, tolerance=1e-6)


def _check(status: InvariantStatus, residual: float = 0.0) -> InvariantCheckResult:
    return InvariantCheckResult(invariant=_inv(), residual=residual, tolerance=1e-6, status=status)


class TestValidationReport:
    def test_empty_report_not_evaluated(self) -> None:
        report = ValidationReport()
        assert report.overall_status is InvariantStatus.NOT_EVALUATED
        assert report.checks == ()

    def test_all_ok(self) -> None:
        report = ValidationReport([_check(InvariantStatus.OK)])
        assert report.overall_status is InvariantStatus.OK

    def test_one_warning(self) -> None:
        report = ValidationReport(
            [
                _check(InvariantStatus.OK),
                _check(InvariantStatus.WARNING),
            ]
        )
        assert report.overall_status is InvariantStatus.WARNING

    def test_one_failure_dominates(self) -> None:
        report = ValidationReport(
            [
                _check(InvariantStatus.OK),
                _check(InvariantStatus.WARNING),
                _check(InvariantStatus.FAILED),
            ]
        )
        assert report.overall_status is InvariantStatus.FAILED

    def test_all_not_evaluated(self) -> None:
        report = ValidationReport([_check(InvariantStatus.NOT_EVALUATED)])
        assert report.overall_status is InvariantStatus.NOT_EVALUATED

    def test_failed_checks_property(self) -> None:
        f = _check(InvariantStatus.FAILED)
        o = _check(InvariantStatus.OK)
        report = ValidationReport([o, f])
        assert report.failed_checks == (f,)

    def test_warning_checks_property(self) -> None:
        w = _check(InvariantStatus.WARNING)
        o = _check(InvariantStatus.OK)
        report = ValidationReport([o, w])
        assert report.warning_checks == (w,)

    def test_source_list_mutation_isolated(self) -> None:
        checks = [_check(InvariantStatus.OK)]
        report = ValidationReport(checks)
        checks.clear()
        assert len(report.checks) == 1

    def test_equality(self) -> None:
        c = _check(InvariantStatus.OK)
        a = ValidationReport([c])
        b = ValidationReport([c])
        assert a == b

    def test_deterministic_ordering(self) -> None:
        c1 = _check(InvariantStatus.OK)
        c2 = _check(InvariantStatus.WARNING)
        report = ValidationReport([c1, c2])
        assert report.checks[0] is c1
        assert report.checks[1] is c2

    def test_repr(self) -> None:
        report = ValidationReport([_check(InvariantStatus.OK)])
        r = repr(report)
        assert "ValidationReport" in r
        assert "OK" in r
