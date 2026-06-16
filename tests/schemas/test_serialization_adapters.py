"""Integration tests for serialization adapters — Phase 9D.

Covers: serialize_solver_report, serialize_solver_report_as_object,
serialize_solver_result_report, serialize_result_bundle,
serialize_validation_report.

Verifies: determinism, no source mutation, no physics calls, correct schema
name/version, consistent content hash across repeated calls.
"""

from __future__ import annotations

from mpl_sim.results.primitives import (
    ResultBundle,
    ResultMessage,
    ResultMetadata,
    ResultStatus,
)
from mpl_sim.schema.adapters import (
    serialize_result_bundle,
    serialize_solver_report,
    serialize_solver_report_as_object,
    serialize_solver_result_report,
    serialize_validation_report,
)
from mpl_sim.schema.primitives import SchemaVersion, SerializedObject
from mpl_sim.solvers.base import (
    ConvergenceMetadata,
    ConvergenceStrategy,
    SolverReport,
    SolverResult,
    SolverStatus,
)
from mpl_sim.validation.invariants import (
    InvariantCheckResult,
    InvariantKind,
    InvariantStatus,
    ValidationInvariant,
    ValidationReport,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _simple_report() -> SolverReport:
    return SolverReport(
        status=SolverStatus.CONVERGED,
        iterations=5,
        residual_norm=1e-9,
        message="Converged normally",
    )


def _report_with_meta() -> SolverReport:
    meta = ConvergenceMetadata(
        strategy=ConvergenceStrategy.FIXED_POINT,
        tolerance=1e-8,
        max_iterations=100,
        iterations=5,
        converged=True,
        final_residual_norm=1e-9,
        message="OK",
    )
    return SolverReport(
        status=SolverStatus.CONVERGED,
        iterations=5,
        residual_norm=1e-9,
        message="Converged normally",
        convergence_metadata=meta,
    )


def _result_bundle() -> ResultBundle:
    meta = ResultMetadata(producer="test_adapter", schema_version="1.0.0")
    msg = ResultMessage(status=ResultStatus.OK, text="all good")
    return ResultBundle(
        status=ResultStatus.OK,
        metadata=meta,
        messages=[msg],
        payload={"answer": 42},
    )


def _validation_report() -> ValidationReport:
    inv = ValidationInvariant(
        kind=InvariantKind.MASS_BALANCE,
        name="global_mass",
        tolerance=1e-6,
        units="kg/s",
    )
    check = InvariantCheckResult(
        invariant=inv,
        residual=1e-8,
        tolerance=1e-6,
        status=InvariantStatus.OK,
    )
    return ValidationReport([check])


# ---------------------------------------------------------------------------
# serialize_solver_report (plain dict)
# ---------------------------------------------------------------------------


class TestSerializeSolverReport:
    def test_basic_fields(self) -> None:
        d = serialize_solver_report(_simple_report())
        assert d["status"] == "CONVERGED"
        assert d["iterations"] == 5
        assert d["residual_norm"] == 1e-9
        assert d["message"] == "Converged normally"
        assert d["convergence_metadata"] is None

    def test_with_convergence_metadata(self) -> None:
        d = serialize_solver_report(_report_with_meta())
        meta = d["convergence_metadata"]
        assert meta is not None
        assert meta["strategy"] == "FIXED_POINT"
        assert meta["converged"] is True
        assert meta["final_residual_norm"] == 1e-9

    def test_does_not_mutate_source(self) -> None:
        report = _simple_report()
        original_status = report.status
        original_iterations = report.iterations
        serialize_solver_report(report)
        assert report.status == original_status
        assert report.iterations == original_iterations

    def test_deterministic(self) -> None:
        report = _report_with_meta()
        d1 = serialize_solver_report(report)
        d2 = serialize_solver_report(report)
        assert d1 == d2

    def test_null_residual_norm(self) -> None:
        report = SolverReport(
            status=SolverStatus.FAILED,
            iterations=0,
            residual_norm=None,
            message="Failed immediately",
        )
        d = serialize_solver_report(report)
        assert d["residual_norm"] is None


# ---------------------------------------------------------------------------
# serialize_solver_report_as_object
# ---------------------------------------------------------------------------


class TestSerializeSolverReportAsObject:
    def test_returns_serialized_object(self) -> None:
        obj = serialize_solver_report_as_object(_simple_report())
        assert isinstance(obj, SerializedObject)

    def test_schema_name(self) -> None:
        obj = serialize_solver_report_as_object(_simple_report())
        assert obj.schema_name == "SolverReport"

    def test_schema_version(self) -> None:
        obj = serialize_solver_report_as_object(_simple_report())
        assert obj.schema_version == SchemaVersion(1, 0, 0)

    def test_has_content_hash(self) -> None:
        obj = serialize_solver_report_as_object(_simple_report())
        assert obj.content_hash is not None
        assert len(obj.content_hash) == 64

    def test_deterministic_hash(self) -> None:
        report = _simple_report()
        a = serialize_solver_report_as_object(report)
        b = serialize_solver_report_as_object(report)
        assert a.content_hash == b.content_hash

    def test_different_reports_different_hash(self) -> None:
        a = serialize_solver_report_as_object(_simple_report())
        other = SolverReport(
            status=SolverStatus.FAILED,
            iterations=1,
            residual_norm=0.5,
            message="Failed",
        )
        b = serialize_solver_report_as_object(other)
        assert a.content_hash != b.content_hash

    def test_does_not_mutate_source(self) -> None:
        report = _simple_report()
        original_message = report.message
        serialize_solver_report_as_object(report)
        assert report.message == original_message


# ---------------------------------------------------------------------------
# serialize_solver_result_report
# ---------------------------------------------------------------------------


class TestSerializeSolverResultReport:
    def test_serializes_report_only(self) -> None:
        import numpy as np

        from mpl_sim.core.state import StateLayout, SystemState

        layout = StateLayout(variables=())
        state = SystemState(layout=layout, values=np.array([], dtype=float))
        report = _simple_report()
        result = SolverResult(state=state, report=report)

        obj = serialize_solver_result_report(result)
        assert isinstance(obj, SerializedObject)
        assert obj.schema_name == "SolverReport"

    def test_state_none_case(self) -> None:
        result = SolverResult(state=None, report=_simple_report())
        obj = serialize_solver_result_report(result)
        assert isinstance(obj, SerializedObject)
        assert obj.schema_name == "SolverReport"

    def test_deterministic(self) -> None:
        result = SolverResult(state=None, report=_simple_report())
        a = serialize_solver_result_report(result)
        b = serialize_solver_result_report(result)
        assert a.content_hash == b.content_hash


# ---------------------------------------------------------------------------
# serialize_result_bundle
# ---------------------------------------------------------------------------


class TestSerializeResultBundle:
    def test_returns_serialized_object(self) -> None:
        obj = serialize_result_bundle(_result_bundle())
        assert isinstance(obj, SerializedObject)

    def test_schema_name(self) -> None:
        obj = serialize_result_bundle(_result_bundle())
        assert obj.schema_name == "ResultBundle"

    def test_schema_version(self) -> None:
        obj = serialize_result_bundle(_result_bundle())
        assert obj.schema_version == SchemaVersion(1, 0, 0)

    def test_has_content_hash(self) -> None:
        obj = serialize_result_bundle(_result_bundle())
        assert obj.content_hash is not None

    def test_payload_contains_status(self) -> None:
        obj = serialize_result_bundle(_result_bundle())
        assert obj.payload["status"] == "OK"

    def test_payload_contains_messages(self) -> None:
        obj = serialize_result_bundle(_result_bundle())
        messages = obj.payload["messages"]
        assert len(messages) == 1
        assert messages[0]["text"] == "all good"

    def test_payload_contains_inner_payload(self) -> None:
        obj = serialize_result_bundle(_result_bundle())
        assert obj.payload["payload"]["answer"] == 42

    def test_deterministic(self) -> None:
        bundle = _result_bundle()
        a = serialize_result_bundle(bundle)
        b = serialize_result_bundle(bundle)
        assert a.content_hash == b.content_hash

    def test_does_not_mutate_source(self) -> None:
        bundle = _result_bundle()
        original_status = bundle.status
        original_message_count = len(bundle.messages)
        serialize_result_bundle(bundle)
        assert bundle.status == original_status
        assert len(bundle.messages) == original_message_count

    def test_empty_bundle_serializes(self) -> None:
        meta = ResultMetadata(producer="p", schema_version="1.0.0")
        bundle = ResultBundle(status=ResultStatus.OK, metadata=meta)
        obj = serialize_result_bundle(bundle)
        assert obj.payload["messages"] == []
        assert obj.payload["payload"] == {}


# ---------------------------------------------------------------------------
# serialize_validation_report
# ---------------------------------------------------------------------------


class TestSerializeValidationReport:
    def test_returns_serialized_object(self) -> None:
        obj = serialize_validation_report(_validation_report())
        assert isinstance(obj, SerializedObject)

    def test_schema_name(self) -> None:
        obj = serialize_validation_report(_validation_report())
        assert obj.schema_name == "ValidationReport"

    def test_schema_version(self) -> None:
        obj = serialize_validation_report(_validation_report())
        assert obj.schema_version == SchemaVersion(1, 0, 0)

    def test_has_content_hash(self) -> None:
        obj = serialize_validation_report(_validation_report())
        assert obj.content_hash is not None

    def test_overall_status_in_payload(self) -> None:
        obj = serialize_validation_report(_validation_report())
        assert obj.payload["overall_status"] == "OK"

    def test_checks_in_payload(self) -> None:
        obj = serialize_validation_report(_validation_report())
        checks = obj.payload["checks"]
        assert len(checks) == 1
        assert checks[0]["status"] == "OK"
        assert checks[0]["invariant"]["name"] == "global_mass"

    def test_empty_report_serializes(self) -> None:
        obj = serialize_validation_report(ValidationReport())
        assert obj.payload["overall_status"] == "NOT_EVALUATED"
        assert obj.payload["checks"] == []

    def test_deterministic(self) -> None:
        report = _validation_report()
        a = serialize_validation_report(report)
        b = serialize_validation_report(report)
        assert a.content_hash == b.content_hash

    def test_does_not_mutate_source(self) -> None:
        report = _validation_report()
        original_count = len(report.checks)
        serialize_validation_report(report)
        assert len(report.checks) == original_count

    def test_failed_status_serialized(self) -> None:
        inv = ValidationInvariant(kind=InvariantKind.ENERGY_BALANCE, name="energy", tolerance=1e-3)
        check = InvariantCheckResult(
            invariant=inv,
            residual=1.5,
            tolerance=1e-3,
            status=InvariantStatus.FAILED,
            message="Energy imbalance",
        )
        report = ValidationReport([check])
        obj = serialize_validation_report(report)
        assert obj.payload["overall_status"] == "FAILED"
        assert obj.payload["checks"][0]["message"] == "Energy imbalance"
