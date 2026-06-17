# Phase 11C HX Wrapper and Input Hardening Audit

## Verdict

APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE

## Summary

Phase 11C closes the approved Phase 11B follow-ups in scope. `EvaporatorHXInput` now exposes `htc_secondary`, both Evaporator and Condenser wrappers forward sink-side HX fields into `HXSolveRequest`, and `EpsilonNTUModel` now rejects invalid geometry/correlation scalars plus invalid HTC/DP outputs where those outputs are used.

This remains a Phase 11 checkpoint, not full Phase 11 completion. No LMTD strategy, segmented march, moving boundary model, validation harness, DOE, dynamics, control, fitting, optimization, or full loop HX residual integration was added.

## Scope Audited

Audited branch: `phase-11c-hx-wrapper-and-input-hardening`

Files inspected:

- `src/mpl_sim/components/evaporator.py`
- `src/mpl_sim/components/condenser.py`
- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/epsilon_ntu.py`
- `tests/components/test_evaporator_component.py`
- `tests/components/test_condenser_component.py`
- `tests/hx_models/test_hx_model_input_hardening.py`
- `tests/hx_models/test_epsilon_ntu_sink_side.py`
- `tests/hx_models/test_epsilon_ntu_model.py`
- `tests/hx_models/test_secondary_bc.py`

Branch delta against `main...HEAD` is limited to:

- `src/mpl_sim/components/evaporator.py`
- `src/mpl_sim/hx_models/epsilon_ntu.py`
- `tests/components/test_condenser_component.py`
- `tests/components/test_evaporator_component.py`
- `tests/hx_models/test_hx_model_input_hardening.py`

## Commands Executed

```text
git branch --show-current
-> phase-11c-hx-wrapper-and-input-hardening

git status --short
-> no tracked/untracked changes reported; Git emitted home-directory ignore permission warnings

git log --oneline --decorate -8
-> 728489e (HEAD -> phase-11c-hx-wrapper-and-input-hardening, origin/phase-11c-hx-wrapper-and-input-hardening) test: harden HX wrapper forwarding and input validation
-> ce6fa20 docs: add MPL library scientific presentation
-> 63b8d4f merge: phase 11b sink-side epsilon NTU support
-> dc4ab8c docs: audit phase 11b sink-side epsilon NTU
-> a723383 feat: add sink-side epsilon NTU support
-> 6667d5b merge: normalize test directory layout
-> 3ce3aba chore: normalize test directory layout
-> 87ae985 merge: phase 11 heat exchanger foundation checkpoint

git diff --stat main...HEAD
-> 5 files changed, 817 insertions(+), 10 deletions(-)

pytest
-> 2363 passed, 1 .pytest_cache permission warning

pytest tests/hx_models tests/components
-> 963 passed, 1 .pytest_cache permission warning

ruff check src tests
-> All checks passed

black --check src tests
-> timed out after 120s and again after 300s in this environment

black --check --no-cache --verbose src tests
-> All done; 114 files would be left unchanged
```

`ruff check src tests` was used instead of `ruff check .` because the Phase 11C request explicitly scoped linting away from `docs/presentations/generate_mpl_presentation.py`, which is unrelated presentation-experiment lint noise. That artifact should be handled later in a separate `chore/remove-presentation-artifacts` or docs cleanup branch.

Architecture/default searches were run with PowerShell `Select-String` equivalents for:

- `CoolProp`
- `PropertyBackend`
- `mpl_sim.network`
- `mpl_sim.solvers`
- `CorrelationRegistry`
- hidden default patterns such as `4180`, `A_ht = 1.0`, `D_h = 1e-3`, `rho = 1.0`, `mu = 1e-5`
- `abs(` and `clip`

Search results found only boundary-documentation mentions for CoolProp/PropertyBackend, no network/solver imports in HX targets, no `CorrelationRegistry` resolution in `EpsilonNTUModel`, no hidden physical-default patterns in the scoped source files, and only the accepted `abs(Cr - 1.0) < 1e-9` numerical tolerance.

## Audit Checklist

### Evaporator Wrapper Completeness

Pass.

- `EvaporatorHXInput` exposes `htc_secondary`.
- `EvaporatorComponent.evaluate_heat_exchanger()` forwards `htc_secondary` into `HXSolveRequest`.
- `UAComputationMode.TWO_SIDED` can now be exercised through `EvaporatorComponent` when both HTC correlations are supplied.
- The wrapper delegates to the injected HX model and does not resolve correlations internally.

### Component Forwarding Tests

Pass.

Both Evaporator and Condenser component tests verify forwarding of:

- `primary_T_in`
- `primary_cp`
- `primary_thermal_mode`
- `ua_computation_mode`
- `htc_primary`
- `htc_secondary`
- `dp_primary`
- `htc_multiplier`
- `friction_multiplier`

The tests use recording/dummy HX models and fake correlations. They test wrapper forwarding, not real heat-transfer numerics.

### HX Input Hardening

Pass.

`EpsilonNTUModel` rejects missing or non-finite required scalars through `_require_scalar()` where used. Positive-domain checks are enforced for `G`, `D_h`, `L_cell`, `rho`, `mu`, and `A_ht`. Vapor quality `x` is required and checked as `0 <= x <= 1` when building HTC inputs.

Missing-scalar coverage exists across `test_epsilon_ntu_model.py` and `test_epsilon_ntu_sink_side.py`; non-finite and non-positive/out-of-range coverage exists in `test_hx_model_input_hardening.py`.

### HTC/UA Output Hardening

Pass.

HTC outputs used in UA are required to be finite and strictly positive before UA is computed. Invalid primary HTC outputs are rejected in `PRIMARY_ONLY` and `TWO_SIDED`; invalid secondary HTC outputs are rejected in `TWO_SIDED`.

There is no clipping, `abs`, replacement, or silent fallback for HTC outputs. `PRIMARY_ONLY` requires valid primary HTC. `TWO_SIDED` requires valid primary and secondary HTC.

### DP Output Handling

Pass.

Non-finite DP outputs are rejected in both `FixedHeatRate` and `SinkInletTempAndFlow` paths. Signed DP is documented and tested: positive `dP_primary` decreases pressure, while negative DP is allowed intentionally as pressure recovery. The implementation does not apply `abs` or clipping to DP.

Friction calibration multiplies DP only and does not affect `Q` or enthalpy balance.

### Hidden Physical Defaults

Pass.

No new hidden defaults were found for:

- `cp = 4180`
- water assumptions
- heat-transfer area
- hydraulic diameter
- density
- viscosity
- mass flux
- quality
- phase-change inference from `primary_cp is None`
- single-sided UA fallback from missing `htc_secondary`

The only accepted convention remains `roughness = 0.0` as an explicit smooth-wall default, and it is documented/tested.

### Architecture Boundaries

Pass.

- No CoolProp imports/calls in `hx_models/` or component wrappers.
- No `PropertyBackend` construction/calls in `hx_models/` or component wrappers.
- No Network/Solver imports in `hx_models/` or HX wrappers.
- No `CorrelationRegistry` resolution inside `EpsilonNTUModel`.
- Branch diff does not modify Solver, Network, Pump, Accumulator, Pipe, schema/results/validation primitives, or architecture documents.
- No LMTD, segmented march, moving boundary, validation harness, DOE, dynamics, control, fitting, or optimization was added.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

None.

## Deferred Items

- Full Phase 11 physical HX continuation remains deferred: FixedWallTemp/AmbientCoupling decisions, additional HX strategies such as LMTD/segmented models, migrated HTC/DP closures, and loop residual integration.
- Presentation artifacts under `docs/presentations/` are outside Phase 11C scope and should be handled in a separate `chore/remove-presentation-artifacts` or docs cleanup branch.
- The exact `black --check src tests` command timed out in this environment, but `black --check --no-cache --verbose src tests` completed successfully with all 114 files unchanged.

## Phase Classification

Phase 11C checkpoint that should be merged before continuing Phase 11.

This is not full Phase 11 completion.

## Merge Readiness

Ready to merge as a Phase 11C checkpoint.

Required test/lint evidence is green for `pytest`, scoped HX/component tests, `ruff check src tests`, and no-cache Black formatting. The branch stays within its intended source/test scope and closes the Phase 11B follow-up items without introducing architecture-boundary violations.
