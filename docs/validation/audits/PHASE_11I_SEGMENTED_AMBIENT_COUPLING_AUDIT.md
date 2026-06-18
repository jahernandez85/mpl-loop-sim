# Phase 11I Segmented Ambient Coupling Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 11I extends `SegmentedMarchModel` with finite-capacity segmented
`AmbientCoupling` while preserving `FixedHeatRate` and finite-capacity
segmented `FixedWallTemp`.

The ambient path divides prescribed `UA_ambient` uniformly over the explicit
cell count and marches primary enthalpy and diagnostic temperature cell by
cell. It does not require or call `htc_primary`, does not apply
`htc_multiplier` to prescribed ambient UA, and retains optional cell-wise
injected primary DP.

No critical or major findings were identified. Two stale descriptions were
corrected during finalization: the Phase 11F test-module overview still listed
wall and ambient coupling as unsupported, and the cell-record field
documentation did not state that ambient records also carry
`htc_primary=None`.

This is a Phase 11I checkpoint, not full Phase 11 completion.

## Scope Audited

Implementation and tests:

- `src/mpl_sim/hx_models/segmented.py`
- `tests/hx_models/test_segmented_ambient_coupling.py`
- `tests/hx_models/test_segmented_march_model.py`
- `tests/hx_models/test_segmented_wall_htc_coupling.py`
- `tests/hx_models/test_hx_model_family_contracts.py`

Architecture and state contracts:

- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/core/fluid_state.py`
- `src/mpl_sim/core/state.py`
- `src/mpl_sim/correlations/contract.py`

Authoritative documents:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/architecture/SCHEMA_SPEC.md`
- Phase 11 foundation through Phase 11H audits
- `docs/validation/audits/PHASE_11_FINAL_CLOSEOUT_AUDIT.md`

The pre-audit working tree contained only the five expected Phase 11I
implementation/test paths. No unrelated changes or architecture-document
changes were present.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-11i-segmented-ambient-coupling`
- `git status --short --branch`
  - Modified: `src/mpl_sim/hx_models/segmented.py`
  - Modified: `tests/hx_models/test_hx_model_family_contracts.py`
  - Modified: `tests/hx_models/test_segmented_march_model.py`
  - Modified: `tests/hx_models/test_segmented_wall_htc_coupling.py`
  - Untracked: `tests/hx_models/test_segmented_ambient_coupling.py`
- `git log --oneline --decorate -10`
  - Pre-commit HEAD: `8c976f1 merge: phase 11h segmented wall HTC coupling`
  - `main`, `origin/main`, and the Phase 11I branch began at that commit.
- `git diff --stat`
  - Four tracked implementation/test files changed; the untracked focused
    ambient test was not included in Git's statistic.
- `git diff --stat main...HEAD`
  - No output because Phase 11I was uncommitted and the branch began at current
    `main`.
- `git status --short`
  - Confirmed the same five expected implementation/test paths.

Git emitted non-blocking warnings that the user-level ignore file under
`C:\Users\AndresH\.config\git\ignore` could not be read. Repository inspection
was unaffected.

### Required validation

- `pytest`
  - Passed: `2711 passed`
  - One non-blocking Windows `.pytest_cache` permission warning.
- `pytest tests/hx_models tests/components`
  - Passed: `1311 passed`
  - One non-blocking Windows `.pytest_cache` permission warning.
- `ruff check src tests`
  - Passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - Passed: `123 files would be left unchanged`.

## Critical Searches

### Forbidden architecture dependencies

Patterns searched under `src/mpl_sim/hx_models` and
`src/mpl_sim/components`:

```text
CoolProp
PropertyBackend
mpl_sim.network
mpl_sim.solvers
CorrelationRegistry
```

No forbidden import, construction, call, or registry resolution was found.
Matches were comments and docstrings documenting the boundaries or registry
separation. `SegmentedMarchModel` consumes correlations only through
`HXSolveRequest`.

### Hidden physical defaults

Patterns searched:

```text
4180
A_ht *= *1.0
area *= *1.0
D_h *= *1e-3
rho *= *1.0
mu *= *1e-5
cp *=
clip
abs(
```

No hidden physical defaults, clipping, or sign-forcing `abs()` calls were
found. The sole `abs(` match was the accepted epsilon-NTU numerical tolerance
`abs(Cr - 1.0) < 1e-9`. Component `primary_cp` matches only forward explicit
caller values. The previously audited optional `roughness=0.0` smooth-wall DP
convention is unchanged.

### Segmented ambient-coupling searches

Targeted searches confirmed:

- `AmbientCoupling` routes to `_solve_ambient_coupling`.
- `SinkInletTempAndFlow` remains unsupported and deferred.
- `PrimaryThermalMode.FINITE_CAPACITY` is required.
- `PrimaryThermalMode.CONSTANT_TEMPERATURE` is rejected as deferred.
- `primary_T_in` and `primary_cp` are explicit.
- `UA_cell = UA_ambient / n_cells`.
- `T_in` and `T_out` occur only in diagnostic cell records/profile.
- `htc_primary` is not used by the ambient path.
- `htc_multiplier` does not affect ambient UA or energy.
- `friction_multiplier` affects DP and pressure only.
- `raw_dP_primary` remains pre-calibration.
- segmented march remains absent from `CorrelationRole`.

## Audit Checklist

### AmbientCoupling segmented support

Pass.

- `AmbientCoupling` is supported by `SegmentedMarchModel`.
- Each cell performs the required finite-capacity explicit march:

  ```text
  UA_cell = UA_ambient / n_cells
  Q_cell = UA_cell * (T_ambient - T_cell_in)
  h_cell_out = h_cell_in + Q_cell / primary_mdot
  T_cell_out = T_cell_in + Q_cell / (primary_mdot * primary_cp)
  ```

- Result `Q` is the sum of cell heat rates.
- Result outlet enthalpy and pressure equal the final cell outputs.
- Heating, cooling, zero-temperature-difference, one-cell, and multi-cell
  behavior are tested.

### Required explicit inputs

Pass.

- Explicit finite positive `primary_T_in` is required.
- Explicit finite positive `primary_cp` is required.
- `PrimaryThermalMode.FINITE_CAPACITY` is required.
- `CONSTANT_TEMPERATURE` is rejected with a phase-change-deferred message.
- `AmbientCoupling` requires finite positive `UA_ambient` and finite positive
  `T_ambient`; invalid construction is tested.
- Primary mass flow and cell count remain explicit and validated by their
  existing value-object contracts.
- No defaults were introduced for cp, ambient temperature, UA, mass flow,
  density, viscosity, or cell count.

### HTC path / prescribed UA behavior

Pass.

- `htc_primary` is neither required nor called, including when supplied.
- No HTC verdicts are produced.
- Every ambient cell record has `htc_primary=None`.
- `htc_multiplier` does not affect `UA_cell`, cell or total heat rate,
  enthalpy, or temperature.
- This is consistent with treating `UA_ambient` as prescribed conductance and
  is covered by focused tests.

### DP path

Pass.

- Existing `FixedHeatRate` and `FixedWallTemp` DP tests remain green.
- Optional `dp_primary` is called once per ambient cell with the current cell
  inlet `FluidState`.
- DP verdicts are propagated in deterministic cell order.
- `friction_multiplier` affects only calibrated cell DP, total DP, and
  pressure; energy results are unchanged.
- `raw_dP_primary` is the sum of pre-calibration cell outputs.
- Signed DP and pressure recovery are preserved.
- Non-finite DP output is rejected.

### Profile diagnostics

Pass.

- `SegmentedCellRecord` and `SegmentedProfile` are frozen dataclasses.
- `zone_profile` contains exactly `n_cells` records.
- Records contain `cell_index`, `Q_cell`, `h_in`, `h_out`,
  `raw_dP_cell`, `dP_cell`, `P_in`, `P_out`, `T_in`, `T_out`,
  `htc_primary`, and `UA_cell`.
- Ambient records carry `htc_primary=None`.
- Temperatures are diagnostic only; no temperature is stored on
  `FluidState`, `Port`, or `SystemState`.

### Unsupported/deferred behavior

Pass.

- `SinkInletTempAndFlow` remains unsupported with a clear deferred message.
- No fake segmented sink-side coupling was added.
- Constant-temperature/phase-change segmented ambient coupling remains
  deferred.
- Moving-boundary behavior remains deferred.

### Architecture boundaries

Pass.

- No CoolProp import or call.
- No `PropertyBackend` construction or call.
- No Network or Solver import.
- No `CorrelationRegistry` resolution in `SegmentedMarchModel`.
- No architecture documents changed.
- No changes to Solver, Network, Pump, Accumulator, Pipe, schema, results,
  validation primitives, core state contracts, or correlation roles.
- No moving-boundary model, closure migration, full-loop residual assembly,
  literature harness, DOE, dynamics, control, fitting, or optimization.

### Tests

Pass.

- Happy paths and failure paths are covered.
- Heating, cooling, and zero-difference cases are covered.
- Missing and invalid explicit inputs are covered.
- No-HTC-call, no-HTC-verdict, and `htc_multiplier` no-effect behavior are
  covered.
- DP call count, current-cell inlet state, verdict propagation, signed DP,
  non-finite output, and multiplier placement are covered.
- Profile count, immutability, diagnostic fields, and final-cell consistency
  are covered.
- Deferred `SinkInletTempAndFlow` behavior is covered.
- Full and targeted suites preserve Phase 11B-11H guarantees.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

None remaining.

Two stale documentation descriptions were corrected before final validation:

- the Phase 11F segmented test overview no longer claims that
  `FixedWallTemp` and `AmbientCoupling` are unsupported;
- `SegmentedCellRecord.htc_primary` documentation now states that it is also
  `None` for `AmbientCoupling`.

## Deferred Items

- Segmented `SinkInletTempAndFlow`.
- Phase-change/constant-temperature segmented wall and ambient coupling.
- Boiling and condensation HTC closure migrations.
- Two-phase DP closure migrations.
- Moving-boundary HX model.
- Scenario-bound full evaporator/condenser behavior.
- Full-loop residual integration and convergence acceptance.
- Validation/literature harnesses.
- DOE/surrogate generation.
- Dynamics, control, fitting, and optimization.

## Phase Classification

Phase 11I is a checkpoint that should be merged before continuing Phase 11.

It is not full Phase 11 completion. The authoritative implementation plan and
final closeout audit still require correlation migrations, broader physical
coupling, and full-loop convergence evidence.

## Merge Readiness

Approved for merge as a checkpoint. Required tests, lint, formatting,
critical searches, and architecture checks are green, with no critical,
major, or remaining minor findings.
