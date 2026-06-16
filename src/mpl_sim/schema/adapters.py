"""Serialization adapters for solver, result, and validation objects — Phase 9D.

Thin, data-only adapters that convert existing immutable objects into
SerializedObject instances.  No physics, no solver calls, no state mutation.

Architecture constraints:
- MUST NOT call CoolProp, properties, correlations, or component methods.
- MUST NOT mutate source objects.
- MUST NOT run solver iterations.
- Imports from mpl_sim.solvers, mpl_sim.results, and mpl_sim.validation are
  permitted here because these are *adapter* modules that specifically and
  safely bridge those layers into the schema layer.
- Schema *primitives* (primitives.py, serialization.py) remain import-clean.
"""

from __future__ import annotations

from mpl_sim.results.primitives import ResultBundle, ResultMessage, ResultMetadata
from mpl_sim.schema.primitives import SchemaVersion
from mpl_sim.schema.serialization import make_serialized_object
from mpl_sim.solvers.base import ConvergenceMetadata, SolverReport, SolverResult
from mpl_sim.validation.invariants import (
    InvariantCheckResult,
    ValidationInvariant,
    ValidationReport,
)

# Canonical schema versions for the serialized forms defined in this module.
_SOLVER_REPORT_SCHEMA_VERSION = SchemaVersion(1, 0, 0)
_RESULT_BUNDLE_SCHEMA_VERSION = SchemaVersion(1, 0, 0)
_VALIDATION_REPORT_SCHEMA_VERSION = SchemaVersion(1, 0, 0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _serialize_convergence_metadata(meta: ConvergenceMetadata) -> dict:
    return {
        "strategy": meta.strategy.value,
        "tolerance": meta.tolerance,
        "max_iterations": meta.max_iterations,
        "iterations": meta.iterations,
        "converged": meta.converged,
        "final_residual_norm": meta.final_residual_norm,
        "message": meta.message,
    }


def _serialize_result_message(msg: ResultMessage) -> dict:
    return {
        "status": msg.status.value,
        "text": msg.text,
        "code": msg.code,
        "source": msg.source,
    }


def _serialize_result_metadata(meta: ResultMetadata) -> dict:
    return {
        "producer": meta.producer,
        "schema_version": meta.schema_version,
        "timestamp": meta.timestamp,
        "tags": list(meta.tags),
    }


def _serialize_validation_invariant(inv: ValidationInvariant) -> dict:
    return {
        "kind": inv.kind.value,
        "name": inv.name,
        "tolerance": inv.tolerance,
        "units": inv.units,
        "description": inv.description,
    }


def _serialize_invariant_check_result(check: InvariantCheckResult) -> dict:
    return {
        "invariant": _serialize_validation_invariant(check.invariant),
        "residual": check.residual,
        "tolerance": check.tolerance,
        "status": check.status.value,
        "message": check.message,
    }


# ---------------------------------------------------------------------------
# Public adapters
# ---------------------------------------------------------------------------


def serialize_solver_report(report: SolverReport) -> dict:
    """Convert a SolverReport to a JSON-compatible dict.

    Does not mutate the report.  Does not call physics, correlations, or
    property backends.  Enum values are converted to their string value.

    Args:
        report: the immutable SolverReport to serialize.

    Returns:
        A plain dict containing only JSON-compatible primitives.
    """
    conv_meta = None
    if report.convergence_metadata is not None:
        conv_meta = _serialize_convergence_metadata(report.convergence_metadata)
    return {
        "status": report.status.value,
        "iterations": report.iterations,
        "residual_norm": report.residual_norm,
        "message": report.message,
        "convergence_metadata": conv_meta,
    }


def serialize_solver_report_as_object(report: SolverReport) -> object:
    """Serialize a SolverReport into a SerializedObject with a content hash.

    The schema name is "SolverReport"; the schema version is 1.0.0.
    No source mutation occurs.

    Args:
        report: the immutable SolverReport to serialize.

    Returns:
        An immutable SerializedObject.
    """
    payload = serialize_solver_report(report)
    return make_serialized_object(
        schema_name="SolverReport",
        schema_version=_SOLVER_REPORT_SCHEMA_VERSION,
        payload=payload,
        include_hash=True,
    )


def serialize_solver_result_report(result: SolverResult) -> object:
    """Serialize the report metadata from a SolverResult (without SystemState values).

    Only the SolverReport inside the SolverResult is serialized.  The
    SystemState is deliberately excluded: state vector values belong to
    their own schema per SCHEMA_SPEC.md §14 and are not serialized here.

    Args:
        result: the immutable SolverResult; its state field is ignored.

    Returns:
        An immutable SerializedObject for the embedded SolverReport.
    """
    return serialize_solver_report_as_object(result.report)


def serialize_result_bundle(bundle: ResultBundle) -> object:
    """Serialize a ResultBundle into a SerializedObject with a content hash.

    The schema name is "ResultBundle"; the schema version is 1.0.0.
    No source mutation occurs.  Payload values from the bundle are passed
    through to_primitive so non-serializable values raise TypeError.

    Args:
        bundle: the immutable ResultBundle to serialize.

    Returns:
        An immutable SerializedObject.
    """
    payload: dict = {
        "status": bundle.status.value,
        "metadata": _serialize_result_metadata(bundle.metadata),
        "messages": [_serialize_result_message(m) for m in bundle.messages],
        "payload": dict(bundle.payload),
    }
    return make_serialized_object(
        schema_name="ResultBundle",
        schema_version=_RESULT_BUNDLE_SCHEMA_VERSION,
        payload=payload,
        include_hash=True,
    )


def serialize_validation_report(report: ValidationReport) -> object:
    """Serialize a ValidationReport into a SerializedObject with a content hash.

    The schema name is "ValidationReport"; the schema version is 1.0.0.
    No source mutation occurs.

    Args:
        report: the immutable ValidationReport to serialize.

    Returns:
        An immutable SerializedObject.
    """
    payload: dict = {
        "overall_status": report.overall_status.value,
        "checks": [_serialize_invariant_check_result(c) for c in report.checks],
    }
    return make_serialized_object(
        schema_name="ValidationReport",
        schema_version=_VALIDATION_REPORT_SCHEMA_VERSION,
        payload=payload,
        include_hash=True,
    )
