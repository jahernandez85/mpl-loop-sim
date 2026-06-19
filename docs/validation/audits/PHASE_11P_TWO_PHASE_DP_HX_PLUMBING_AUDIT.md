# Phase 11P Two-Phase DP HX Plumbing Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 11P adds explicit two-phase primary pressure-drop plumbing to all three
implemented HX strategies. `HXSolveRequest.dp_primary_is_two_phase=False`
preserves the existing single-phase path. When explicitly enabled, HX models
build `TwoPhaseDPInput`, forward the four Decision 011 property scalars, convert
the returned friction gradient from Pa/m to Pa by multiplying by `L_cell`
exactly once, and apply `friction_multiplier` after that conversion.

The initial focused test file did not substantiate every claimed BC path or the
complete required scalar-validation matrix. The audit expanded it from 70 to
122 tests. Stale Phase 11O documentation that still described HX injection as
deferred was also reconciled. No critical, major, or remaining minor finding
exists.

## Scope Audited

- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/epsilon_ntu.py`
- `src/mpl_sim/hx_models/lmtd.py`
- `src/mpl_sim/hx_models/segmented.py`
- `src/mpl_sim/correlations/two_phase_dp.py` documentation only
- `tests/hx_models/test_hx_two_phase_dp_plumbing.py`
- `tests/correlations/test_two_phase_dp.py` documentation only
- `docs/roadmap/PROJECT_STATUS.md`
- authoritative architecture, interface, correlation-contract, schema,
  decision-log, implementation-plan, and prior Phase 11 audit documents

No architecture document, correlation formula, registry behavior, component,
network, solver, moving-boundary, valve, manifold, or full-loop behavior was
changed. No `src/mpl_sim/correlations/init.py` exists.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-11p-two-phase-dp-hx-plumbing`
- `git status --short --branch`
  - expected Phase 11P implementation, focused tests, status, and audit paths
- `git log --oneline --decorate -10`
  - branch based on merged Phase 11O checkpoint `f8e7762`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
  - no staged changes before closeout

### Validation

- `pytest`
  - passed: `3252 passed`
- `pytest tests/correlations`
  - passed: `512 passed`
- `pytest tests/hx_models tests/components`
  - passed: `1590 passed`
- `pytest tests/hx_models/test_hx_two_phase_dp_plumbing.py -v`
  - passed: `122 passed`
- `ruff check src tests`
  - passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - passed: `133 files would be left unchanged`

Pytest emitted one non-blocking Windows warning because `.pytest_cache` could
not be written.

## Request/API Verification

- `HXSolveRequest.dp_primary_is_two_phase: bool = False` exists.
- The default preserves the established single-phase builder and output
  handling.
- The mode is caller-selected; no phase inference, correlation-class
  inspection, or registry resolution occurs.
- The mode is ignored when `dp_primary` is absent, so two-phase scalars are not
  required unnecessarily.
- When enabled with `dp_primary`, builder validation occurs before correlation
  evaluation.
- Wrong mode/correlation combinations fail clearly through the correlation
  input type contract.
- No property lookup, hidden scalar default, or `FluidState` phase inference is
  present.

## TwoPhaseDPInput Builder Verification

All three builders explicitly require:

- `G`
- `x`
- `D_h`
- `L_cell`
- `rho_l`
- `rho_v`
- `mu_l`
- `mu_v`

`G`, `D_h`, `L_cell`, densities, and viscosities must be finite and strictly
positive. Quality must be finite and in `[0, 1]`. The property values are
forwarded exactly into the immutable `property_scalars` mapping. Missing and
invalid values fail with the relevant key in the error.

No density, viscosity, diameter, quality, length, or two-phase roughness default
is introduced.

## Gradient-to-Drop Conversion

`MSHTwoPhaseFrictionGradient.value[0]` remains a positive frictional gradient in
Pa/m. Each HX path performs:

`raw_dP = raw_dP_gradient * L_cell`

exactly once. `raw_dP_primary` stores the pre-calibration pressure drop in Pa.
`dP_primary` stores `friction_multiplier * raw_dP_primary` in Pa.

The single-phase path remains unchanged. In the segmented strategy, `L_cell` is
the caller-supplied per-cell length, raw cell drops are summed in Pa, pressure
is marched with calibrated per-cell drops, and the reported calibrated total
equals the multiplier applied once to the raw total. No second length
integration or second calibration occurs.

## HX Model Path Coverage

- `EpsilonNTUModel`
  - FixedHeatRate
  - SinkInletTempAndFlow
  - FixedWallTemp
  - AmbientCoupling
- `LMTDModel`
  - FixedWallTemp
  - AmbientCoupling
  - unsupported BCs remain unsupported
- `SegmentedMarchModel`
  - FixedHeatRate
  - FixedWallTemp
  - AmbientCoupling
  - SinkInletTempAndFlow

Every supported path is exercised with `TwoPhaseDPInput` construction and an
explicit Pa/m-to-Pa assertion.

## Test Coverage

The 122 focused tests cover:

- unchanged default single-phase behavior;
- exact two-phase input type and property-scalar forwarding;
- every required missing scalar;
- zero, negative, NaN, and infinity rejection for all positive scalars;
- invalid quality values;
- explicit gradient-to-drop conversion;
- pre-calibration and calibrated result semantics;
- segmented per-cell conversion, summation, and call count;
- every supported BC path;
- no hidden defaults;
- no HX correlation-registry resolution;
- no CoolProp or `PropertyBackend`;
- clear wrong mode/correlation failures.

## Critical Searches

Searches across HX models, components, correlations, tests, and roadmap
documents found:

- no prohibited CoolProp or `PropertyBackend` implementation dependency;
- no Network or Solver dependency in HX/correlation code;
- no `CorrelationRegistry` resolution inside HX models;
- no prohibited two-phase scalar defaults;
- no gradient/drop ambiguity or duplicate length multiplication;
- no duplicate friction calibration;
- only pre-existing allowed `abs` and epsilon-NTU capacity-ratio logic;
- stale Phase 11O deferral text was corrected without changing correlation
  behavior.

## Findings

### Critical Findings

None.

### Major Findings

None remaining.

### Minor Findings

None remaining.

The initial focused-test coverage and stale-documentation findings were
resolved during the audit.

## Deferred Items

- additional two-phase DP closures, including Homogeneous/Cicchitti and
  Kim-Mudawar 2013;
- remaining two-phase HTC closures;
- counterflow and broader phase-change coupling;
- moving-boundary modeling;
- full-loop convergence acceptance.

## Phase Classification

Phase 11P is an approved checkpoint. Phase 11 remains open.

## Merge Readiness

`phase-11p-two-phase-dp-hx-plumbing` is approved for merge into `main` as a
Phase 11P checkpoint after the implementation/test and audit/status commits are
created and pushed. This audit does not authorize merging to `main`.
