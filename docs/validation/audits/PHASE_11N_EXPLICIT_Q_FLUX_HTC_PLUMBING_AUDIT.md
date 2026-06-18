# Phase 11N Explicit Q-Flux HTC Plumbing Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 11N adds an explicit optional `HXSolveRequest.q_flux_primary` and passes
it unchanged to primary-side `HTCInput.q_flux` in `EpsilonNTUModel`,
`LMTDModel`, and `SegmentedMarchModel`.

The correlation contract was not changed: `HTCInput.q_flux` already existed.
Provided heat flux must be finite and strictly positive. Omission remains valid
for closures that do not require heat flux, while `ShahBoilingHTC` fails
clearly if invoked without it.

An initial audit finding showed that shared HTC-input builders also forwarded
the primary heat flux to secondary HTC calls. That finding was corrected before
approval: epsilon-NTU and segmented two-sided paths now use explicit secondary
builders that set `q_flux=None`. Focused tests prove this isolation.

No heat flux is inferred from heat rate or area. No hidden default, `abs`,
clipping, property lookup, registry resolution, new correlation, two-phase DP,
moving-boundary behavior, or full-loop behavior was introduced.

No critical, major, or remaining minor finding exists.

## Scope Audited

- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/epsilon_ntu.py`
- `src/mpl_sim/hx_models/lmtd.py`
- `src/mpl_sim/hx_models/segmented.py`
- `tests/hx_models/test_hx_q_flux_plumbing.py`
- `src/mpl_sim/correlations/contract.py`
- active single-phase and two-phase HTC implementations
- component, state, port, network, solver, schema, and architecture boundaries
- authoritative roadmap, architecture, interface, correlation-contract, and
  schema documents
- Phase 11J through Phase 11M audits and the Phase 11 final closeout audit

No architecture document was modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-11n-explicit-q-flux-htc-plumbing`
- `git status --short --branch`
  - expected Phase 11N implementation/test follow-up paths only before audit
    documentation
- `git log --oneline --decorate -10`
  - Phase 11N implementation commit: `780732a`
  - branch base and `main`: `676a07c`
- `git diff --stat`
  - follow-up correction limited to `base.py`, `epsilon_ntu.py`,
    `segmented.py`, and the focused test
- `git diff --stat main...HEAD`
  - original Phase 11N commit contained four HX files, the focused test, and
    `PROJECT_STATUS.md`
- `git status --short`
  - confirmed no unrelated worktree paths
- accidental-file check
  - `src/mpl_sim/correlations/init.py` does not exist

Git emitted non-blocking warnings that the user-level ignore file could not be
read and that the focused test may be normalized from LF to CRLF.

### Required validation

- `pytest`
  - passed: `3047 passed`
- `pytest tests/correlations`
  - passed: `429 passed`
- `pytest tests/hx_models tests/components`
  - passed: `1468 passed`
- `pytest tests/hx_models/test_hx_q_flux_plumbing.py -v`
  - passed: `46 passed`
- `ruff check src tests`
  - passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - passed: `130 files would be left unchanged`

Pytest emitted one non-blocking Windows warning because `.pytest_cache` could
not be written.

## Implementation Reconstruction

- `HTCInput.q_flux: float | None` existed on `main` before Phase 11N.
- `HXSolveRequest` gained `q_flux_primary: float | None = None`.
- Request construction rejects zero, negative, NaN, and infinite supplied
  values.
- Primary HTC builders in all three implemented HX strategies pass the exact
  caller value to `HTCInput.q_flux`.
- Epsilon-NTU and segmented two-sided paths use separate secondary HTC builders
  and pass `q_flux=None`.
- LMTD supports q-flux only on its existing primary `FixedWallTemp` HTC path.
- Ambient and fixed-heat-rate no-HTC paths remain unaffected.

## Contract and Request Design

1. `HTCInput.q_flux` already existed before Phase 11N.
2. The core correlation contract was not changed.
3. `HXSolveRequest` was changed.
4. The field added was `q_flux_primary`.
5. The name clearly identifies the side and quantity.
6. It is optional, preserving non-boiling HTC requests.
7. Supplied values are validated as finite and strictly positive.
8. Omission remains valid at request construction.
9. Omitted q-flux causes `ShahBoilingHTC` to raise a clear `ValueError`.
10. `FluidState`, Ports, and `SystemState` were not changed.

## HX Model Plumbing Verification

### EpsilonNTUModel

- Primary HTC receives `request.q_flux_primary`.
- Existing no-q-flux HTC behavior remains valid.
- Shah works through `FixedWallTemp` with explicit q-flux and scalars.
- Shah without q-flux fails clearly.
- In `TWO_SIDED` mode, secondary HTC receives `q_flux=None`.
- Ambient coupling remains prescribed-UA and does not call HTC.

### LMTDModel

- `FixedWallTemp` primary HTC receives explicit q-flux.
- Shah succeeds with q-flux and fails without it.
- Ambient coupling remains prescribed-UA and no-HTC.
- Unsupported boundary conditions remain unsupported.
- No Q/A heat-flux inference exists.

### SegmentedMarchModel

- `FixedWallTemp` passes the same explicit q-flux once per cell.
- `SinkInletTempAndFlow` passes it once per primary HTC cell call.
- Secondary HTC receives `q_flux=None` once per cell.
- No cell-wise distribution or Q/A inference is invented.
- Ambient coupling and fixed heat rate remain no-HTC paths.

## ShahBoilingHTC Integration

- Shah is injected through epsilon-NTU, LMTD, and segmented fixed-wall paths.
- Tests provide `G`, `x`, `D_h`, `q_flux`, `rho_l`, `rho_v`, `mu_l`, `k_l`,
  `Pr_l`, and `h_fg`.
- Resulting HTC and Q are finite and positive.
- Changing mass flux changes Shah's HTC and therefore changes HX heat rate,
  proving `CorrelationOutput.value` is consumed.
- Correlation outputs and verdicts reach `HXSolveResult.verdicts`.
- Missing q-flux fails clearly.
- Missing `h_fg` or `rho_l` fails clearly; no property fallback is used.

## YanCondensationHTC Regression

- Yan remains injectable with explicit geometry/property scalars.
- Yan succeeds with q-flux omitted.
- Supplying primary q-flux does not alter Yan's result because Yan does not
  consume that field.
- Yan output verdicts remain propagated.
- When used as a secondary HTC, Yan receives `q_flux=None`.
- No property default was introduced.

## Critical Searches

### Forbidden architecture dependencies

Searched HX models, components, and correlations for `CoolProp`,
`PropertyBackend`, `mpl_sim.network`, `mpl_sim.solvers`, and
`CorrelationRegistry`.

Matches were existing registry implementation or comments/docstrings
documenting forbidden boundaries. HX models contain no forbidden import,
construction, call, or correlation-registry resolution.

### q_flux / hidden default searches

Searched for q-flux declarations and uses, heat-flux aliases, Q/A forms,
`abs` on q-flux, clipping, and min/max replacement patterns.

- no heat flux is derived from `Q`, `Q_cell`, `A_ht`, or cell area;
- no invalid value is made positive;
- no q-flux clipping or replacement exists;
- the only production `q_flux=None` assignments are explicit secondary-side
  isolation;
- `q_flux_primary=None` remains the documented optional request default;
- Shah's existing formula-level `max(alpha_cb, alpha_nb)` is unchanged.

## Audit Checklist

### Changed-file scope

Pass. Only expected HX implementation, focused tests, status, and audit files
changed. No architecture, component, network, solver, schema, result,
validation-primitive, or correlation implementation file changed. No new
correlation, two-phase DP, moving-boundary, valve, or manifold file was added.

### q_flux validation

Pass. Supplied q-flux is finite and positive; zero, negative, NaN, and both
infinities are rejected. The value is passed unchanged. There is no `abs`,
clipping, defaulting, or Q/A inference.

### HX model plumbing

Pass. Primary HTC receives q-flux in epsilon-NTU, LMTD fixed wall, segmented
fixed wall, and segmented sink paths. Segmented paths preserve one caller value
across cells. Secondary HTC is isolated. No-HTC paths are unaffected.

### Shah integration

Pass. Shah works through all three applicable primary fixed-wall paths with
explicit q-flux and scalars. Missing q-flux and missing scalar failures,
positive HTC, Q sensitivity, and verdict propagation are tested.

### Yan regression

Pass. Yan remains injectable without q-flux, remains independent of the
optional field, requires its explicit scalar inputs, and receives no primary
q-flux when used on the secondary side.

### Architecture boundaries

Pass.

- no CoolProp or `PropertyBackend` call;
- no Network or Solver import;
- no `CorrelationRegistry` resolution in HX models;
- no change to `FluidState`, `SystemState`, Ports, Solver, Network, Pump,
  Accumulator, Pipe, schema, results, or validation primitives;
- no two-phase DP, moving boundary, full-loop convergence, validation harness,
  DOE, dynamics, control, fitting, optimization, valves, or manifolds.

### Tests

Pass. Tests cover explicit passthrough, invalid request values, omission for
no-q-flux correlations, Shah success and failure, per-cell behavior,
secondary-side isolation, Shah Q sensitivity/verdict propagation, missing
scalars, and Yan regression. Assertions inspect public request/input/result
behavior rather than registry or private state.

## Findings

### Critical Findings

None.

### Major Findings

None remaining. The initial primary-to-secondary q-flux leak was corrected
before approval and is now protected by focused tests.

### Minor Findings

None.

## Deferred Items

- remaining boiling and condensation HTC closures;
- two-phase DP migration;
- counterflow and phase-change segmented coupling;
- moving-boundary modeling;
- Scenario-bound full evaporator/condenser behavior;
- full-loop residual integration and convergence acceptance;
- validation/literature harnesses;
- DOE/surrogate generation;
- dynamics, control, fitting, optimization, valves, and manifolds.

## Phase Classification

Phase 11N is a checkpoint that should be merged before continuing Phase 11. It
is not full Phase 11 completion.

## Merge Readiness

`phase-11n-explicit-q-flux-htc-plumbing` is approved for merge as a Phase 11N
checkpoint. Required validation, integration checks, regression checks,
critical searches, and architecture checks are green.
