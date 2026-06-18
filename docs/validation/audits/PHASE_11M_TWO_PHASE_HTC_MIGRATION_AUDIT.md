# Phase 11M Two-Phase HTC Migration Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 11M migrates `ShahBoilingHTC` and `YanCondensationHTC` from the legacy
MPL correlation catalogue into the active correlation contract. Both are
stateless `Correlation` implementations using `CorrelationRole.HTC`, explicit
scalar inputs, one-element `CorrelationOutput.value`, declared validity
behavior, and closure metadata.

The formulas and branch conditions match
`legacy/MPL_Simulator/mpl/correlations.py`. Legacy state/property coupling and
quality clamping were intentionally removed. No CoolProp, `PropertyBackend`,
hidden fluid default, automatic closure selection, HX registry resolution,
two-phase DP, or moving-boundary work was introduced.

The audit corrected one inaccurate pre-audit claim: existing HX builders
already forward the complete `geom_scalars` mapping. Therefore
`YanCondensationHTC` is directly injectable when callers provide its required
scalars. `ShahBoilingHTC` HX injection remains deferred because the builders do
not populate `HTCInput.q_flux`. Focused tests now prove both facts and pin
independent Shah branch values.

No critical, major, or remaining minor finding exists.

## Scope Audited

- `src/mpl_sim/correlations/two_phase_htc.py`
- `src/mpl_sim/correlations/__init__.py`
- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/correlations/single_phase_htc.py`
- `tests/correlations/test_two_phase_htc.py`
- HX input builders and component forwarding boundaries
- authoritative architecture, interface, correlation-contract, schema,
  roadmap, and project-status documents
- Phase 11J, 11K, 11L, and final-closeout audits
- relevant MPL, PyP2PL, and A0 legacy references

No architecture document was modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-11m-two-phase-htc-migration-foundation`
- `git status --short --branch`
  - expected Phase 11M implementation, export, test, and status paths only
- `git log --oneline --decorate -10`
  - pre-commit `HEAD`, `main`, and `origin/main`: `fc1733c`
- `git diff --stat`
  - tracked changes initially limited to `PROJECT_STATUS.md` and package exports
- `git diff --stat main...HEAD`
  - no output because the branch began at current `main`
- `git status --short`
  - confirmed the same expected paths
- accidental-file check
  - `src/mpl_sim/correlations/init.py` does not exist

Git emitted non-blocking warnings that the user-level ignore file could not be
read.

### Required validation

- `pytest`
  - passed: `3001 passed`
- `pytest tests/correlations`
  - passed: `429 passed`
- `pytest tests/correlations/test_two_phase_htc.py -v`
  - passed: `97 passed`
- `pytest tests/hx_models tests/components`
  - passed: `1422 passed`
- `ruff check src tests`
  - passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - passed: `129 files would be left unchanged`

Pytest emitted one non-blocking Windows warning because `.pytest_cache` could
not be written.

## Legacy Traceability

### ShahBoilingHTC

The legacy class exists and defines:

- liquid-only Dittus-Boelter baseline at total mass flux;
- convection number, boiling number, and liquid Froude number;
- the same Froude split for `N`;
- `alpha_cb = 1.8 * alpha_l / N^0.8`;
- the same four `N`/`Bo` nucleate-boiling branches;
- `max(alpha_cb, alpha_nb)` as the correlation's physical selection logic.

The migrated implementation preserves those equations and constants. It
replaces legacy `state.x`, saturation-property attributes, endpoint clamping,
and the latent-heat fallback with explicit validated inputs.

### YanCondensationHTC

The legacy class exists and defines:

```text
G_eq = G * (1 - x + x * sqrt(rho_l/rho_v))
Re_eq = G_eq * D_h / mu_l
h = 4.118 * Re_eq^0.4 * Pr_l^(1/3) * k_l / D_h
```

The migrated implementation preserves the formula and replaces legacy state
property access and quality clamping with explicit validated inputs.

### Deferred legacy closures

- Chen remains deferred because the PyP2PL implementation performs CoolProp
  lookup and fallback behavior inside the closure.
- Gungor-Winterton remains deferred because the legacy implementation embeds
  an R-134a molar-mass default.
- Bennett-Chen, Kandlikar, Kim-Mudawar, other boiling/condensation closures,
  A0 global/property-coupled formulas, and two-phase DP remain deferred.

## Correlation Implementation Verification

### ShahBoilingHTC

- Implements `Correlation`; role is `HTC`.
- Returns `(h,)` in W/m²/K with verdict and metadata.
- Requires explicit `G`, `x`, `D_h`, `q_flux`, `rho_l`, `rho_v`, `mu_l`,
  `k_l`, `Pr_l`, and `h_fg`.
- Rejects missing, non-finite, zero, or negative required physical inputs.
- Enforces `0 < x < 1`; no quality clamp or `abs`.
- Uses formula-level `max(alpha_cb, alpha_nb)`, not output sanitization.
- Representative independent values:
  - `x=0.3`: `5786.6507 W/m²/K`
  - `x=0.8`: `24168.5615 W/m²/K`
- Independent tests also pin both `N > 1` boiling-number branches, the
  intermediate-`N` branch, low-`N` branch, and low-Froude path.

### YanCondensationHTC

- Implements `Correlation`; role is `HTC`.
- Returns `(h,)` in W/m²/K with verdict and metadata.
- Requires explicit `G`, `x`, `D_h`, `rho_l`, `rho_v`, `mu_l`, `k_l`, and
  `Pr_l`.
- Rejects missing, non-finite, zero, or negative required physical inputs.
- Accepts `0 <= x <= 1`; interior quality is `IN_ENVELOPE`, while endpoints
  are evaluable and `EXTRAPOLATED`.
- Representative independent values:
  - `x=0.5`: `7550.31 W/m²/K`
  - `x=0.2`: `5742.41 W/m²/K`

## Critical Searches

### Forbidden architecture dependencies

Searched correlations, HX models, and components for `CoolProp`,
`PropertyBackend`, `mpl_sim.network`, `mpl_sim.solvers`, and
`CorrelationRegistry`.

Matches were registry implementation or comments/docstrings documenting
forbidden dependencies. The new module has no forbidden import or call. HX
models do not resolve `CorrelationRegistry`.

### Hidden defaults / clamping

Searched the requested roots for physical fallback constants and assignments,
`molar`, surface-tension defaults, `clip`, `minimum`, `maximum`, `min`, `max`,
and `abs`.

No hidden default, property replacement, quality clamp, or sign forcing exists
in the new correlations. Allowed matches were Shah's formula-level maximum,
pre-existing epsilon-NTU capacity-rate math, the accepted epsilon-NTU numerical
tolerance, and pre-existing signed-flow handling in Churchill DP.

## Audit Checklist

### Changed-file scope

Pass. Only the Phase 11M source, export, focused test, status, and audit paths
changed. No HX source or architecture document changed. No accidental
`correlations/init.py` exists.

### Legacy traceability

Pass. Both named legacy classes exist and their formulas were faithfully
migrated. Legacy property access and clamping were removed. Deferred closures
are correctly classified.

### Correlation contract compliance

Pass. Both closures use the existing role and input/output contract, return one
HTC value, carry verdict and metadata, and fail invalid inputs consistently.

### ShahBoilingHTC

Pass. Required inputs, strict quality domain, formula branches, formula-level
maximum, independent numerical values, and invalid-input behavior are tested.

### YanCondensationHTC

Pass. Required inputs, endpoint verdicts, independent numerical values,
invalid-input behavior, and direct HX consumption are tested.

### HX injection status

Pass with corrected classification.

- HX models still receive closures only through `HXSolveRequest`.
- Builders forward the complete `geom_scalars` mapping without defaults.
- Yan is injectable now when required scalars are supplied.
- Shah remains deferred because `HTCInput.q_flux` is not populated.
- Future Shah integration should add explicit heat-flux plumbing; no hidden
  default is acceptable.

### Exports and registry

Pass. Both classes are package exports and resolve through existing
`CorrelationRegistry` patterns. HX models remain registry-free. No automatic
selection was added.

### Architecture boundaries

Pass.

- no CoolProp or `PropertyBackend` call;
- no Network or Solver import;
- no HX registry resolution;
- no change to `FluidState`, `SystemState`, Ports, Solver, Network, Pump,
  Accumulator, Pipe, schema, results, or validation primitives;
- no two-phase DP, moving boundary, full-loop integration, validation harness,
  DOE, dynamics, control, fitting, optimization, valves, or manifolds.

### Tests

Pass. Tests independently verify representative formulas and Shah branch
results, invalid and endpoint quality cases, missing explicit inputs, exports,
registry behavior, architecture boundaries, Yan HX injection, and the precise
Shah `q_flux` deferral. The full suite preserves prior behavior.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

None remaining. During audit finalization, the blanket claim that both closures
were blocked by missing property-scalar forwarding was corrected. Tests were
strengthened to prove actual branch selection and closure-specific HX status.

## Deferred Items

- explicit HX `q_flux` plumbing for Shah boiling injection;
- remaining boiling and condensation HTC closures;
- two-phase DP migration;
- counterflow and phase-change segmented coupling;
- moving-boundary modeling;
- Scenario-bound full HX behavior and full-loop convergence acceptance;
- validation/literature harnesses;
- DOE/surrogate generation;
- dynamics, control, fitting, optimization, valves, and manifolds.

## Phase Classification

Phase 11M is a checkpoint that should be merged before continuing Phase 11. It
is not full Phase 11 completion.

## Merge Readiness

`phase-11m-two-phase-htc-migration-foundation` is approved for merge as a
checkpoint. Required validation, formula checks, critical searches, and
architecture checks are green, with no critical, major, or remaining minor
finding.
