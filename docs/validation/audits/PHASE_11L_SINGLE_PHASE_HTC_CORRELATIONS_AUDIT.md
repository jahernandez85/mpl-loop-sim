# Phase 11L Single-Phase HTC Correlations Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 11L migrates `DittusBoelterHTC` and `GnielinskiHTC` into the active
correlation package. Both are stateless `Correlation` implementations with
`CorrelationRole.HTC`, explicit scalar inputs, declared validity envelopes,
vector-first `CorrelationOutput` values, per-call verdicts, and closure
metadata.

The formulas, envelope reporting, package exports, registry compatibility, and
explicit `HXSolveRequest` injection paths are correct. No property lookup,
CoolProp call, `PropertyBackend` dependency, hidden physical default,
automatic closure selection, or HX-model registry resolution was introduced.

No critical, major, or remaining minor finding was identified. This is a Phase
11L checkpoint, not full Phase 11 completion.

## Scope Audited

- `src/mpl_sim/correlations/single_phase_htc.py`
- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/correlations/single_phase_dp.py`
- `src/mpl_sim/correlations/__init__.py`
- `tests/correlations/test_single_phase_htc.py`
- HX-model and component closure-consumption boundaries
- authoritative roadmap, architecture, interface, correlation-contract, and
  schema documents
- Phase 11H through Phase 11K audits and the Phase 11 final closeout audit

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-11l-single-phase-htc-correlations`
- `git status --short --branch`
  - expected Phase 11L implementation, test, export, and status paths only
- `git log --oneline --decorate -10`
  - pre-commit `HEAD`, `main`, and `origin/main`: `11b6b12`
- `git diff --stat`
  - tracked changes were limited to `PROJECT_STATUS.md` and the correlation
    package export; the implementation and focused test were initially
    untracked
- `git diff --stat main...HEAD`
  - no output because the branch began at current `main`
- `git status --short`
  - confirmed the same expected Phase 11L paths

Git emitted non-blocking warnings that the user-level ignore file under
`C:\Users\AndresH\.config\git\ignore` could not be read.

### Required validation

- `pytest`
  - passed: `2904 passed`
- `pytest tests/correlations`
  - passed: `332 passed`
- `pytest tests/correlations/test_single_phase_htc.py -v`
  - passed: `82 passed`
- `pytest tests/hx_models tests/components`
  - passed: `1422 passed`
- `ruff check src tests`
  - passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - passed: `127 files would be left unchanged`

Pytest emitted one non-blocking Windows warning because `.pytest_cache` could
not be written.

## Correlation Implementation Verification

### DittusBoelterHTC

- Implements `Correlation` and returns one HTC value in
  `CorrelationOutput.value[0]`.
- Uses `CorrelationRole.HTC`.
- Implements `Nu = 0.023 Re^0.8 Pr^n` and `h = Nu k / D_h`.
- Requires explicit finite positive `Re`, `Pr`, `k`, `n`, and `D_h`.
- Supports explicit `n=0.4` and `n=0.3` paths without inferring heating,
  cooling, temperature direction, or phase.
- Declares and checks `Re >= 10000`, `Pr in [0.6, 160]`, and
  `D_h >= 1e-6 m`.
- Returns honest formula extrapolation with `EXTRAPOLATED` outside the
  envelope and never clamps inputs.

### GnielinskiHTC

- Implements `Correlation` and returns one HTC value in
  `CorrelationOutput.value[0]`.
- Uses `CorrelationRole.HTC`.
- Implements the specified Petukhov friction factor and Gnielinski Nusselt
  formula, followed by `h = Nu k / D_h`.
- Requires explicit finite positive `Re`, `Pr`, `k`, and `D_h`.
- Declares and checks `Re in [3000, 5e6]`, `Pr in [0.5, 2000]`, and
  `D_h >= 1e-6 m`.
- Outside the declared envelope, returns the raw mathematically evaluable
  formula result with `EXTRAPOLATED`; it does not force a positive HTC or clamp
  the input. HX models retain their existing rejection of non-positive HTC
  outputs.

## Critical Searches

### Forbidden architecture dependencies

Searched `src/mpl_sim/correlations`, `src/mpl_sim/hx_models`, and
`src/mpl_sim/components` for:

```text
CoolProp
PropertyBackend
mpl_sim.network
mpl_sim.solvers
CorrelationRegistry
```

Matches were package registry implementation or comments/docstrings describing
forbidden dependencies. The new HTC module contains no forbidden import or
call. HX models contain no `CorrelationRegistry` resolution.

### Hidden physical defaults

Searched the same roots for the requested physical constants, scalar
assignments, `clip`, and `abs(` patterns.

No hidden HTC input default, clipping, or sign forcing was found. The matches
were explicit formula/envelope constants, the pre-existing signed-mass-flux
Churchill handling, and the accepted epsilon-NTU `Cr` numerical tolerance.

### Closure-specific searches

Targeted searches confirmed:

- both class names are exported;
- both roles are `CorrelationRole.HTC`;
- outputs use `CorrelationOutput`;
- `Re`, `Pr`, `k`, `D_h`, and Dittus-Boelter `n` are explicit;
- envelope bounds and `IN_ENVELOPE`/`EXTRAPOLATED` verdicts are present;
- no CoolProp, `PropertyBackend`, replacement default, clipping, or sign
  forcing is present.

## Audit Checklist

### Changed-file scope

Pass.

- Only expected Phase 11L implementation, test, export, status, and audit paths
  changed.
- No HX model source file changed.
- No architecture document changed.
- `PROJECT_STATUS.md` records the Phase 11L verdict and keeps Phase 11 open.
- `src/mpl_sim/correlations/init.py` does not exist.

### Correlation contract compliance

Pass. Both classes implement the existing contract, use the existing HTC role,
return a one-element value tuple with verdict and metadata, reject invalid
required inputs clearly, and report envelope excursions consistently with
existing project style.

### DittusBoelterHTC

Pass. The formula and explicit exponent paths are independently checked.
Missing `n` fails. Invalid inputs fail. Envelope excursions, including positive
`D_h < 1e-6 m`, are flagged without replacement or clamping.

### GnielinskiHTC

Pass. The friction-factor, Nusselt, and HTC calculations are independently
checked. Invalid inputs fail. Envelope excursions are flagged without
replacement or clamping.

### Domain/envelope handling

Pass. The requested Re, Pr, and hydraulic-diameter bounds are declared and
tested. `D_h = 1e-6 m` is accepted at the boundary; smaller positive values are
evaluated and flagged `EXTRAPOLATED`. No `abs`, clipping, or sign forcing is
used in either HTC formula.

### Exports and registry

Pass. Both correlations are package exports and can be registered/resolved
through the existing `CorrelationRegistry`. HX models remain registry-free and
no automatic closure selection was introduced.

### HX integration

Pass.

- Both production correlations can be injected into `EpsilonNTUModel`.
- Tests independently calculate the raw HTC and prove it determines fixed-wall
  heat rate through `CorrelationOutput.value[0]`.
- Both can be injected into segmented `FixedWallTemp`.
- Both can be injected on either side of segmented
  `SinkInletTempAndFlow`.
- Verdict counts prove per-cell calls occur through the explicit request.
- No hidden defaults or registry resolution are required.

### Architecture boundaries

Pass.

- no CoolProp import/call;
- no `PropertyBackend` construction/call;
- no Network or Solver import;
- no `CorrelationRegistry` resolution inside HX models;
- no architecture-document changes;
- no change to `FluidState`, `SystemState`, Ports, Solver, Network, Pump,
  Accumulator, Pipe, schema, results, or validation primitives;
- no moving-boundary, boiling HTC, condensation HTC, or two-phase DP work;
- no validation harness, full-loop integration, DOE, dynamics, control,
  fitting, optimization, valve, or manifold work.

### Tests

Pass. Tests independently verify both numerical formulas, invalid and
out-of-envelope behavior, the explicit Dittus-Boelter exponent, package
exports, registry behavior, forbidden imports, no clamping, and production
correlation injection into the required HX paths. The full suite preserves
Phase 11B-11K behavior.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

None remaining. During finalization, the focused tests were strengthened to
cover the positive sub-envelope hydraulic-diameter path, package exports,
AST-based forbidden-import inspection, exact fixed-wall Q consumption, and
per-cell verdict counts. Stale Phase 11K branch fields in `PROJECT_STATUS.md`
were corrected.

## Deferred Items

- boiling HTC migration;
- condensation HTC migration;
- two-phase DP migration;
- counterflow and phase-change segmented coupling;
- moving-boundary modeling;
- Scenario-bound full HX behavior and full-loop convergence acceptance;
- validation/literature harnesses;
- DOE/surrogate generation;
- dynamics, control, fitting, and optimization;
- valves and manifolds.

## Phase Classification

Phase 11L is a checkpoint that should be merged before continuing Phase 11.
It is not full Phase 11 completion.

## Merge Readiness

`phase-11l-single-phase-htc-correlations` is approved for merge as a
checkpoint. Required validation, critical searches, formula checks, and
architecture checks are green, with no critical, major, or remaining minor
finding.
