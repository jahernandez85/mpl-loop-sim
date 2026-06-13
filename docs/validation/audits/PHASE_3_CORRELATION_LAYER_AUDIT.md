# Phase 3 Correlation Layer Audit

## Verdict

**APPROVED FOR PHASE 4**

## Summary

Phase 3A implemented the correlation contract primitives: the frozen role set, role-typed correlation inputs, validity envelopes, verdicts, closure metadata, correlation output, and the abstract `Correlation` interface.

Phase 3B implemented a correlation registry that is separate from the property backend registry, enforces unique names, rejects unknown names clearly, filters by role, and rejects correlations without usable validity envelopes.

Phase 3C implemented `ChurchillFrictionGradient` as the first `SINGLE_PHASE_DP` closure. It returns friction pressure gradient in Pa/m using the Darcy friction factor convention, does not integrate over pipe length, does not include gravity or acceleration, does not include calibration, and does not call CoolProp or the property layer.

The previous Phase 3 audit found one required minor fix: frozen correlation-facing value objects still had mutable nested dictionary payloads. That fix has been applied. `HTCInput.geom_scalars`, `VolumePressureLawInput.law_params`, and `FlowRegimeVerdict.transition_coords` are now exposed as immutable mapping views over defensive copies, and tests prove both mutation resistance and source-dict isolation.

## Scope Audited

- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/correlations/registry.py`
- `src/mpl_sim/correlations/single_phase_dp.py`
- `src/mpl_sim/correlations/__init__.py`
- `tests/correlation/test_correlation_contract.py`
- `tests/correlation/test_correlation_registry.py`
- `tests/correlation/test_single_phase_dp.py`

Supporting context was checked against:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/TEST_PLAN_V1.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/validation/audits/PHASE_2_COMPLETE_AUDIT.md`
- `docs/validation/audits/PHASE_2_CLOSEOUT_SUMMARY.md`

## Audit Checklist

1. **Correlation contract primitives**

   The implemented role set matches the frozen contract: `SINGLE_PHASE_DP`, `TWO_PHASE_DP`, `HTC`, `VOID_FRACTION`, `FLOW_REGIME`, `CRITICAL_HEAT_FLUX`, `VOLUME_PRESSURE_LAW`, and `CUSTOM_CLOSURE`. Role-typed input objects exist with one input type per role, not one input type per formula. Inputs are data-only and do not receive Component, Geometry, Network, Solver, Calibration, or PropertyBackend objects. `CorrelationOutput` carries value, verdict, and metadata; no contract path returns a bare float. `ValidityEnvelope`, `Bound`, `FluidFamilySpec`, `ValidityVerdict`, and `ClosureMetadata` are explicit and frozen. `CriticalHeatFluxInput` remains a declared seam only.

2. **Correlation registry**

   `CorrelationRegistry` is separate from `PropertyBackendRegistry`. It imports only correlation-layer contract primitives, enforces unique names, rejects unknown names with an explicit `KeyError`, resolves by name, filters by role, and rejects correlations with missing, empty-fluid, or empty-bound envelopes. It does not auto-register formulas.

3. **Churchill single-phase friction-gradient closure**

   `ChurchillFrictionGradient` implements `Correlation`, reports role `SINGLE_PHASE_DP`, exposes a non-empty `ValidityEnvelope`, evaluates `SinglePhaseDPInput`, and returns `CorrelationOutput`. It returns friction pressure gradient in Pa/m, does not multiply by `L_cell`, does not include gravity, acceleration, calibration, components, geometry objects, CoolProp, or property imports. The implementation documents and uses the Darcy friction factor convention, and the pressure-gradient expression is dimensionally consistent: `f_D * G^2 / (2 * rho * D_h)`.

4. **Nested payload immutability**

   The previous minor finding is resolved. The relevant mapping payloads are defensively copied and wrapped in `MappingProxyType`. Tests verify direct mutation raises `TypeError`, later mutation of the source dictionary does not propagate, and read access still works.

5. **Import boundaries**

   The correlation package does not import CoolProp, properties, components, geometry, calibration, network, or solvers. `core/` remains independent from properties and correlations. `properties/` does not import correlations. The import boundaries are covered by targeted tests and static inspection.

6. **Test coverage**

   Tests meaningfully cover the role set, immutable/data-only inputs, nested payload immutability, forbidden imports, registry behavior, envelope-required registration, output contract, Churchill gradient-not-total behavior, laminar reference behavior, turbulent plausibility, monotonicity with mass flux and roughness, invalid input behavior, and out-of-envelope verdicts.

7. **Architecture consistency**

   Phase 3 remains consistent with Decision 005, Decision 006, Decision 007, Decision 010, and `IMPLEMENTATION_PLAN.md` Phase 3. Derived properties reach correlations as scalar inputs supplied by callers, not by backend queries inside correlations. Churchill returns only the friction gradient. The correlation registry remains separate from property and heat-exchanger model registries. The catalogue remains intentionally narrow: Churchill is the only real formula implemented in Phase 3.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

- Import-direction rules are still mostly enforced by targeted tests and review rather than import-linter or equivalent tooling. This is not a Phase 4 blocker, but should be addressed before cross-layer imports expand.
- Registry-name versus `ClosureMetadata.name` canonicalization should be documented or enforced before the correlation catalogue grows.
- No additional real correlations beyond Churchill have been implemented. This is intentional and consistent with the Phase 3 scope.

## Phase 4 Readiness

The project is ready to begin **Phase 4 - Geometry and discretization**.

Phase 4 should start narrowly with immutable geometry primitives and the declared geometry/discretization seams: `PipeGeometry`, `PipePath`, `StraightSegment`, containment-only `AccumulatorGeometry`, and discretization primitives. Phase 4 should not implement components.

## Recommended Follow-ups

- Add import-linter or equivalent before cross-layer imports expand.
- Keep Phase 4 focused on geometry and discretization only.
- Do not implement the Pipe component yet; Pipe remains Phase 6.
- Preserve the separation between geometry, discretization, correlations, and components.
- Keep actual additional correlations deferred until consuming components require them.

## Verification

Commands run:

```text
python -B -m pytest -p no:cacheprovider
ruff check .
black --check .
black --check src tests
```

Results:

- `python -B -m pytest -p no:cacheprovider`: 502 passed.
- `ruff check .`: passed.
- `black --check .`: blocked by a Windows `PermissionError` while traversing `.pytest_cache`.
- `black --check src tests`: passed; 36 files would be left unchanged.

## Files Inspected

Source files:

- `src/mpl_sim/core/`
- `src/mpl_sim/properties/`
- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/correlations/registry.py`
- `src/mpl_sim/correlations/single_phase_dp.py`
- `src/mpl_sim/correlations/__init__.py`
- `pyproject.toml`

Test files:

- `tests/unit/`
- `tests/property/`
- `tests/correlation/test_correlation_contract.py`
- `tests/correlation/test_correlation_registry.py`
- `tests/correlation/test_single_phase_dp.py`

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
- `docs/validation/audits/PHASE_2_COMPLETE_AUDIT.md`
- `docs/validation/audits/PHASE_2_CLOSEOUT_SUMMARY.md`
