# Phase 5A Calibration Primitives Audit

## Verdict

**APPROVED FOR NEXT PHASE**

## Summary

Phase 5A implements a narrow calibration foundation: data-only calibration enums, scalar calibration factors, metadata-only target identifiers, immutable scalar modifiers, immutable `CalibrationSet` collections, and a separate name-keyed `CalibrationRegistry`.

The implementation keeps calibration as a separate layer and does not contaminate properties, correlations, geometry, discretization, components, network, or solvers. It contains no property lookup, thermodynamic-state storage, parameter fitting, optimization, experimental-data ingestion, component implementation, or solver behavior.

## Scope Audited

Source and configuration inspected:

- `src/mpl_sim/calibration/primitives.py`
- `src/mpl_sim/calibration/registry.py`
- `src/mpl_sim/calibration/__init__.py`
- `src/mpl_sim/core/`
- `src/mpl_sim/properties/`
- `src/mpl_sim/correlations/`
- `src/mpl_sim/geometry/`
- `src/mpl_sim/discretization/`
- `src/mpl_sim/components/__init__.py`
- `src/mpl_sim/network/__init__.py`
- `src/mpl_sim/solvers/__init__.py`
- `pyproject.toml`

Tests inspected:

- `tests/calibration/test_calibration_primitives.py`
- `tests/calibration/test_calibration_registry.py`
- Relevant import-boundary tests in `tests/correlation/`, `tests/geometry/`, and `tests/discretization/`

Authoritative documents inspected:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_4_GEOMETRY_DISCRETIZATION_AUDIT.md`

## Audit Checklist

### Calibration Layer Boundaries

`calibration/` is a separate package. Static inspection shows it imports only Python standard-library modules and its own calibration primitives/registry. It does not import CoolProp, properties, correlations, geometry, discretization, components, network, solvers, or `PropertyBackend`.

The calibration package does not call property backends, correlations, or thermodynamic property functions. It does not compute thermodynamic properties, store thermodynamic state, mutate existing objects, implement components, implement solvers, or create network coupling.

### Calibration Primitives

`CalibrationMode`, `CalibrationTarget`, and `CalibrationScope` are explicit enums matching the expected Phase 5A vocabulary. `CalibrationMode` contains `NONE` and `TARGET`, with no dataset-fitting mode. `CalibrationTarget` contains only `FRICTION_GRADIENT`, `HTC`, and `UA`, preserving the firewall that calibration applies to closure outputs rather than balances, gravity, acceleration, void fraction, flow regime, or pressure laws.

`SeamLocation`, `CalibrationFactor`, `CalibrationReport`, `CalibrationTargetId`, and `CalibrationModifier` are frozen dataclasses. `CalibrationSet` is effectively immutable through `__slots__`, tuple storage, and blocked attribute mutation. Identifiers reject empty names. Scalar factors, scales, and offsets reject NaN and infinity through finite-value validation.

`CalibrationModifier` supports scalar-only multiplier, offset, and affine forms. `apply_to_scalar()` is a generic arithmetic transform independent of physical models; it does not know about components, correlations, geometry, properties, balances, or state.

No parameter fitting, optimization, dataset ingestion, or experimental calibration-data handling is implemented.

### Interface-Spec Calibration Types

The interface-spec types are present:

- `CalibrationMode`
- `CalibrationTarget`
- `CalibrationScope`
- `SeamLocation`
- `CalibrationFactor`
- `CalibrationReport`

`SeamLocation` is a pure identifier composed of strings and `CalibrationScope`; it does not import or depend on component classes. `CalibrationFactor` is scalar-only and validated. `CalibrationReport` is data-only, defensively converts its factor sequence to a tuple, and remains presentable as empty under `NONE`.

These types do not create premature component coupling. They identify future seams by value rather than by object references.

### CalibrationSet

`CalibrationSet` snapshots input iterables into a tuple and validates that every element is a `CalibrationModifier`. Later mutation of the source list cannot mutate the set. Iteration and `modifiers_for(target)` preserve deterministic insertion order, and empty-set behavior is explicit through `CalibrationSet.empty()`, `is_empty`, length zero, and empty tuple query results.

`modifiers_for(target)` uses `CalibrationTargetId` equality and requires no component, correlation, property, geometry, discretization, network, or solver imports.

### CalibrationRegistry

`CalibrationRegistry` is separate from `PropertyBackendRegistry` and `CorrelationRegistry`. It registers named `CalibrationSet` objects only, rejects empty names, rejects duplicate names, rejects non-`CalibrationSet` values, raises `KeyError` for unknown names, and lists names in deterministic sorted order.

The registry does not auto-register physical calibration logic, default factors, component-coupled resolution, or application behavior. It imports only `CalibrationSet`.

### Import Boundaries

Static inspection and tests show:

- `calibration/` does not import CoolProp.
- `calibration/` does not import properties, correlations, geometry, discretization, components, network, or solvers.
- `correlations/` remains free of calibration imports.
- `geometry/` and `discretization/` remain free of calibration imports.
- Components, network, and solvers remain absent except for placeholder `__init__.py` files.

Import-boundary tooling is still documented as a follow-up in `pyproject.toml`; current enforcement is through targeted tests, static inspection, and review.

### Tests

Phase 5A tests meaningfully cover:

- enum/role values;
- construction;
- validation;
- immutability;
- source-collection isolation;
- NaN/infinity rejection;
- generic scalar application behavior;
- `CalibrationSet` ordering and query behavior;
- registry construction, duplicate-name rejection, unknown-name rejection, invalid-value rejection, and deterministic names;
- calibration import-boundary purity in a fresh Python subprocess;
- full suite passing.

No important missing Phase 5A test blocks the next phase. Later tests for `resolve(slot, component)`, component application seams, reporting through `Result`, and the conservation firewall require component/result/solver infrastructure and are correctly deferred.

### Architecture Consistency

Phase 5A is consistent with the frozen architecture:

- Calibration remains a seam/layer, not fitting.
- Calibration does not implement optimization.
- Calibration does not modify correlations directly.
- Calibration does not modify geometry.
- Calibration does not modify property backends.
- Calibration application to component outputs remains deferred.
- Pipe component remains V1 Build Phase 6.
- Conservation firewall activation remains later, when invariants and results exist.
- Components remain absent.

Acceptable deferred items, not blockers:

- `resolve(slot, component) -> CalibrationFactor` resolution logic.
- The application seam helper used by components after correlation evaluation.
- Conservation firewall activation.
- Experimental calibration-data ingestion.
- Parameter fitting/optimization.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

- Import-direction rules are still enforced by targeted tests, static inspection, and review rather than import-linter or equivalent tooling. This is not a Phase 6 blocker, but it should remain tracked as cross-layer imports increase.

## Next Phase Readiness

The project is ready to continue to the next planned V1 Build Phase in `docs/roadmap/IMPLEMENTATION_PLAN.md`: **Phase 6 - Pipe Component**.

There is no additional Phase 5 substep in the authoritative implementation plan before Phase 6. The items not built in Phase 5A, including component-coupled resolution, application helpers, result reporting, and conservation-firewall activation, are intentionally deferred until components/results/solvers exist.

Phase 6 should remain scoped to the Pipe component and its required component contract/kernel work. It should not start network, solvers, optimization, parameter fitting, DOE/surrogates, or unrelated components.

## Recommended Follow-ups

- Keep calibration application deferred until components exist.
- Apply calibration only after raw correlation/HX-model output and before component balance consumption.
- Do not implement fitting or optimization yet.
- Keep calibration separate from correlations, properties, geometry, and discretization.
- Track import-linter or equivalent if import-boundary risks grow.

## Verification

Verified on 2026-06-15.

Commands run:

```text
pytest
ruff check .
black --check src tests
```

Results:

- `pytest`: 696 passed, with one pytest cache warning because Windows denied access to `.pytest_cache`.
- `ruff check .`: passed.
- `black --check src tests`: passed; 47 files would be left unchanged.

`black --check .` was not needed for this closeout because the requested meaningful formatting check is `black --check src tests`; prior closeouts already documented the Windows `.pytest_cache` traversal issue for whole-repository Black checks.

## Files Inspected

Documents:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_4_GEOMETRY_DISCRETIZATION_AUDIT.md`

Source and configuration:

- `src/mpl_sim/calibration/primitives.py`
- `src/mpl_sim/calibration/registry.py`
- `src/mpl_sim/calibration/__init__.py`
- `src/mpl_sim/core/`
- `src/mpl_sim/properties/`
- `src/mpl_sim/correlations/`
- `src/mpl_sim/geometry/`
- `src/mpl_sim/discretization/`
- `src/mpl_sim/components/__init__.py`
- `src/mpl_sim/network/__init__.py`
- `src/mpl_sim/solvers/__init__.py`
- `pyproject.toml`

Tests:

- `tests/calibration/test_calibration_primitives.py`
- `tests/calibration/test_calibration_registry.py`
- Relevant import-boundary tests in `tests/correlation/`, `tests/geometry/`, and `tests/discretization/`
