# Phase 11T Iterated Counterflow Segmented Solver Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 11T adds an explicit, bounded fixed-point iteration for segmented
counterflow `SinkInletTempAndFlow` requests. Iteration is opt-in through
`CounterflowIterationConfig`; default, co-current, and Phase 11S one-pass
counterflow behavior remain available and unchanged.

The two previous blocking findings are resolved. `max_iter` now requires a
non-boolean integer greater than or equal to one. Focused tests directly
exercise real Shah boiling, Yan condensation, and MSH two-phase pressure-drop
closures through iterated counterflow. The MSH gradient-to-drop test evaluates
the real correlation independently and verifies one multiplication by
`L_cell` per cell.

No critical or major finding remains.

## Scope Audited

- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/segmented.py`
- `src/mpl_sim/hx_models/__init__.py`
- `tests/hx_models/test_segmented_counterflow_iteration.py`
- `tests/hx_models/test_segmented_counterflow_phase_change_foundation.py`
- `docs/roadmap/PROJECT_STATUS.md`
- authoritative architecture, interface, correlation-contract, schema,
  decision-log, implementation-plan, and prior Phase 11 audit documents

No architecture, component, correlation implementation, registry, network,
solver, moving-boundary, valve, or manifold file was modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-11t-iterated-counterflow-segmented-solver`
- `git status --short --branch`
  - expected corrective files only before audit closeout
- `git log --oneline --decorate -10`
  - existing Phase 11T implementation commit: `5ff6f90`
  - branch base and `main`: `44c2c63`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
- `git diff --check`
  - clean

Git emitted non-blocking warnings that the user-level ignore file could not be
read and that Git may normalize the focused test file from LF to CRLF.

### Validation

- `pytest`
  - passed: `3548 passed`
- `pytest tests/correlations`
  - passed: `512 passed`
- `pytest tests/hx_models tests/components`
  - passed: `1886 passed`
- `pytest tests/hx_models/test_segmented_counterflow_phase_change_foundation.py -v`
  - passed: `76 passed`
- `pytest tests/hx_models/test_segmented_counterflow_iteration.py -v`
  - passed: `92 passed`
- `ruff check src tests`
  - passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - passed: `137 files would be left unchanged`

Pytest emitted a non-blocking warning because `.pytest_cache` could not be
written.

## Previous Blocking Findings and Resolution

### max_iter validation

Resolved.

`CounterflowIterationConfig.__post_init__` rejects booleans and every
non-`int` value before checking the lower bound. Runtime and focused-test
evidence confirms rejection of `True`, `False`, `1.5`, NaN, positive infinity,
negative infinity, zero, and negative integers. `max_iter=1` is accepted.
Every error identifies `max_iter`. Existing tolerance and relaxation
validation remains intact.

### Real-correlation iterated-mode coverage

Resolved.

`TestRealCorrelationIteratedMode` directly instantiates and executes:

- `ShahBoilingHTC` with explicit positive `q_flux_primary` and required
  scalars, including missing-scalar and energy-balance checks;
- `YanCondensationHTC` without q-flux, including cooling-sign,
  missing-scalar, diagnostics, and energy-balance checks;
- `MSHTwoPhaseFrictionGradient` with
  `dp_primary_is_two_phase=True` and all required explicit scalars, including
  missing-scalar and multiplier checks.

`_ConstTwoPhaseDP` remains limited to controlled algorithmic tests where a
known gradient is useful for exact arithmetic and input-forwarding assertions.
It is not the sole evidence for real MSH coverage.

### Non-circular MSH gradient-to-drop assertion

Resolved.

The focused test constructs an equivalent `TwoPhaseDPInput`, calls
`MSHTwoPhaseFrictionGradient().evaluate(...)` directly, and obtains
`expected_gradient` independently of the HX result. It then verifies:

`raw_dP_primary = expected_gradient * L_cell * n_cells`

The separate multiplier test verifies:

`dP_primary = friction_multiplier * raw_dP_primary`

This catches omitted or repeated cell-length conversion.

## Actual Implementation Summary

- `CounterflowIterationConfig` is a frozen request-level numerical config with
  `enabled`, `max_iter`, `tolerance`, and `relaxation`.
- `HXSolveRequest.counterflow_iteration` is optional and defaults to `None`.
- Enabled iteration is accepted only for segmented
  `SinkInletTempAndFlow` with explicit `FlowArrangement.COUNTERFLOW`.
- `HXSolveResult` reports `iteration_count`, `converged`, and `residual`.
- The iterated path marches primary cells forward, derives the secondary
  profile backward from the known far-end inlet, computes a profile residual,
  applies under-relaxation, and stops at tolerance or `max_iter`.

## API and Default Behavior

- Iteration is explicit and opt-in.
- `flow_arrangement=None` preserves established behavior.
- Explicit `CO_CURRENT` remains equivalent to the default sink path.
- `COUNTERFLOW` without enabled iteration preserves the Phase 11S one-pass
  approximation.
- Epsilon-NTU and LMTD behavior remains unchanged.
- Iteration defaults are documented as numerical controls, not physical
  assumptions.

## Iteration Configuration

- `max_iter`: non-boolean `int >= 1`
- `tolerance`: finite and strictly positive
- `relaxation`: finite and in `(0, 1]`
- config object: immutable frozen dataclass
- no physical scalar defaults, closure selection, or phase inference

## Iterated Counterflow Algorithm

- limited to segmented `SinkInletTempAndFlow` counterflow
- primary direction remains cell `0` to `n-1`
- secondary inlet remains at cell `n-1`
- each iteration uses the current per-cell secondary-temperature estimate
- secondary profile is integrated backward from the known inlet
- residual is the maximum absolute profile change in kelvin
- relaxation is applied to the profile update
- iteration is bounded by `max_iter`
- no network, global-loop, property, moving-boundary, quality-marching, or
  saturation-inference coupling exists

## Non-Convergence Behavior

Non-convergence returns a normal result with `converged=False`, the performed
iteration count, and the final residual. It is not silently treated as success.
Focused tests force non-convergence with low `max_iter`.

## Diagnostics and Result Schema

Iterated results expose:

- counterflow arrangement through `SegmentedProfile`;
- per-cell heat rates and primary/secondary temperature diagnostics;
- primary and secondary HTC values;
- iteration count;
- convergence flag;
- final profile residual in kelvin.

Non-iterated results preserve defaults of `iteration_count=0`,
`converged=None`, and `residual=None`.

## Phase-Change / DP Plumbing Regression

- primary q-flux reaches primary HTC only;
- real Shah boiling works with explicit q-flux and scalars;
- real Yan condensation works without q-flux;
- real MSH two-phase pressure gradient works with explicit property scalars;
- Pa/m is converted to Pa using `L_cell` exactly once;
- `friction_multiplier` is applied exactly once;
- missing required scalars fail clearly;
- no hidden defaults, property lookup, phase inference, or quality marching.

## Unit and Sign Semantics

- primary balance remains `h_out = h_in + Q / mdot`;
- positive Q heats the primary and cools the secondary;
- negative Q cools the primary and heats the secondary;
- profile residual is in kelvin;
- MSH output remains Pa/m before the explicit cell-length conversion.

## Test Coverage

The 92 focused Phase 11T tests cover default/co-current/one-pass preservation,
strict config validation, opt-in dispatch, per-cell profile feedback,
convergence, explicit non-convergence, relaxation, secondary direction and
backward integration, diagnostics, q-flux side isolation, real Shah/Yan/MSH
integration, exact MSH gradient conversion, missing inputs, architecture
boundaries, and Phase 11S regressions.

## Critical Searches

Required searches found:

- no prohibited CoolProp or `PropertyBackend` implementation dependency;
- no Network or Solver dependency in HX models or components;
- no `CorrelationRegistry` resolution in HX models or components;
- no hidden physical defaults or automatic closure selection;
- no silent non-convergence or full-loop convergence claim;
- `_ConstTwoPhaseDP` confined to controlled fake-correlation tests;
- direct real Shah, Yan, MSH, and `TwoPhaseDPInput` usage in the focused suite.

Matches for dependency names were comments or docstrings documenting
architectural boundaries.

## Findings

### Critical Findings

None.

### Major Findings

None. All previous blocking findings are resolved.

### Minor Findings

Resolved during final audit: corrected a test docstring to state that the
non-circular MSH assertion passes only when `L_cell` is applied exactly once.

## Deferred Items

- moving-boundary modeling;
- full-loop convergence acceptance;
- per-cell geometry/property scalar variation;
- quality marching and phase inference;
- remaining two-phase HTC and DP closures;
- frozen component contribution integration;
- validation harnesses and later valves/manifolds.

## Phase Classification

Phase 11T is an approved Phase 11 checkpoint. Phase 11 remains open.

## Merge Readiness

`phase-11t-iterated-counterflow-segmented-solver` is approved for merge into
`main` as a Phase 11T checkpoint after the corrective and audit commits are
created and pushed. This audit does not authorize or perform the merge.
