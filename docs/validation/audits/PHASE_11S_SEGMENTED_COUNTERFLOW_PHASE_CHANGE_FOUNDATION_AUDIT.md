# Phase 11S Segmented Counterflow Phase-Change Foundation Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 11S adds an explicit `FlowArrangement` API and a deliberately limited
one-pass counterflow foundation to `SegmentedMarchModel`.

The default remains the established co-current segmented sink march.
`FlowArrangement.COUNTERFLOW` places the secondary inlet at cell `n-1`,
marches the primary from cell `0` to `n-1` using the fixed secondary-inlet
temperature as the per-cell estimate, and derives a backward secondary
temperature profile afterward for diagnostics only. The implementation and
status documentation consistently state that this is not a converged
counterflow solution.

Existing explicit phase-change scalar passing, primary q-flux forwarding, and
two-phase pressure-gradient conversion remain operative. No property lookup,
phase inference, quality march, registry resolution, moving boundary, network,
solver, or full-loop behavior was introduced.

No critical or major finding exists. Two minor closeout findings were resolved:
a stale co-current docstring was corrected, and direct real-correlation Shah
and Yan counterflow tests were added.

## Scope Audited

- authoritative architecture, interface, correlation-contract, schema,
  decision-log, implementation-plan, and Phase 11N-11R audit documents
- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/segmented.py`
- `src/mpl_sim/hx_models/__init__.py`
- `tests/hx_models/test_segmented_counterflow_phase_change_foundation.py`
- existing HX-model, component, and correlation regression suites
- `docs/roadmap/PROJECT_STATUS.md`

No architecture document, component, correlation, registry, network, solver,
moving-boundary, valve, or manifold implementation was modified. The package
export file is the correct `src/mpl_sim/hx_models/__init__.py`; no accidental
`src/mpl_sim/hx_models/init.py` exists.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-11s-segmented-counterflow-phase-change-foundation`
- `git status --short --branch`
  - expected HX implementation, focused test, and status paths only before
    audit closeout
- `git log --oneline --decorate -10`
  - branch base and `main`: `b270c4e`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
- `git diff --check`
  - clean

Git emitted non-blocking warnings that the user-level ignore file could not be
read.

### Validation

- `pytest`
  - passed: `3456 passed`
- `pytest tests/correlations`
  - passed: `512 passed`
- `pytest tests/hx_models tests/components`
  - passed: `1794 passed`
- `pytest tests/hx_models/test_segmented_counterflow_phase_change_foundation.py -v`
  - passed: `76 passed`
- `ruff check src tests`
  - passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - passed: `136 files would be left unchanged`

Pytest emitted one non-blocking Windows warning because `.pytest_cache` could
not be written.

## FlowArrangement API Verification

- `FlowArrangement` defines `CO_CURRENT` and `COUNTERFLOW`.
- `HXSolveRequest.flow_arrangement` is explicit and defaults to `None`.
- `None` preserves the existing segmented co-current sink behavior.
- Explicit `CO_CURRENT` reproduces the default result and direction semantics.
- Arrangement is not inferred from component type, boundary values, phase, or
  correlation type.
- Arrangement does not select correlations or resolve a registry.
- Epsilon-NTU and LMTD behavior remains unchanged; the field is documented as
  ignored by those models.
- `SegmentedProfile.flow_arrangement` records `CO_CURRENT` or `COUNTERFLOW` for
  two-stream sink paths and remains `None` for single-stream paths.

## Counterflow One-Pass Semantics

- Primary flow marches from cell `0` to cell `n-1`.
- The secondary inlet is applied at cell `n-1`.
- Each `Q_cell` uses `bc.T_in` as the fixed secondary-temperature estimate.
- The per-cell effectiveness formula remains the documented co-current cell
  formula; this is part of the limited one-pass approximation.
- After the primary march, the secondary diagnostic profile is integrated
  backward:
  - `secondary_T_in[n-1] = bc.T_in`
  - `secondary_T_out[i] = secondary_T_in[i] - Q_cell[i] / C_secondary`
  - `secondary_T_in[i] = secondary_T_out[i+1]`
- Diagnostic secondary temperatures do not feed back into `Q_cell`.
- No nonlinear iteration, convergence tolerance, or hidden solve loop exists.
- Implementation, tests, and status text do not claim full counterflow
  convergence.

## Co-current / Default Behavior

- Existing segmented behavior remains unchanged by default.
- Explicit `CO_CURRENT` matches default heat rate, outlet enthalpy, pressure
  drop, profile size, and inlet direction.
- FixedHeatRate, FixedWallTemp, AmbientCoupling, and SinkInletTempAndFlow
  regression paths pass.
- The counterflow branch is entered only for an explicit `COUNTERFLOW` request
  with `SinkInletTempAndFlow`.

## Phase-Change Scalar Passing

- No CoolProp or `PropertyBackend` lookup exists in HX models.
- No saturation-temperature, latent-heat, quality, or phase inference exists.
- No quality marching, clipping, interpolation, or hidden physical default was
  added.
- `geom_scalars` remains the explicit path for `x`, `h_fg`, `rho_l`, `rho_v`,
  `mu_l`, `mu_v`, `k_l`, `Pr_l`, `G`, `D_h`, and `L_cell`.
- `q_flux_primary` reaches primary HTC only; secondary HTC receives `None`.
- `dp_primary_is_two_phase=True` builds `TwoPhaseDPInput`.
- Missing required inputs fail with clear `ValueError` messages.
- Direct tests verify Shah boiling HTC, Yan condensation HTC, and MSH
  two-phase DP in the segmented counterflow path with explicit inputs.

## Unit and Sign Semantics

- Positive `Q` increases primary enthalpy and temperature and decreases the
  secondary diagnostic temperature.
- Negative `Q` produces the opposite secondary temperature change.
- Primary energy balance remains `h_out = h_in + Q / mdot`.
- MSH output remains a friction gradient in Pa/m.
- The segmented HX multiplies by explicit per-cell `L_cell` exactly once and
  applies the friction multiplier once.
- `SegmentedCellRecord` field documentation identifies temperature, heat-rate,
  enthalpy, pressure, HTC, UA, capacity-rate, effectiveness, and NTU units.

## Test Coverage

The 76 focused tests cover default and explicit co-current equivalence,
counterflow acceptance and direction, fixed-estimate one-pass behavior,
diagnostic-only backward integration, profile metadata, sign and energy
semantics, q-flux side isolation, Shah, Yan, MSH, two-phase scalar forwarding,
gradient-to-drop conversion, missing inputs, forbidden dependencies, package
exports, accidental-file absence, and representative Phase 11N-11R
regressions.

## Critical Searches

Required searches found:

- no prohibited CoolProp or `PropertyBackend` implementation dependency;
- no Network or Solver dependency in HX models or components;
- no `CorrelationRegistry` resolution in HX models or components;
- no hidden production defaults for heat capacity, density, viscosity,
  hydraulic diameter, quality, cell length, heat flux, saturation temperature,
  or latent heat;
- no quality clipping or hidden counterflow iteration;
- no `per_cell_geom_scalars`, `cell_geom_scalars`, `primary_T_sat`,
  `primary_h_fg`, or `primary_x` request fields;
- no accidental `init.py`.

Matches were boundary comments/docstrings, explicit test fixture values, or
pre-existing accepted formula-level uses.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

Resolved during audit:

1. The co-current helper docstring still said counterflow was deferred. It now
   distinguishes the implemented one-pass foundation from the still-deferred
   fully coupled solve.
2. The focused tests used real Shah and Yan closures in segmented paths but did
   not directly exercise both through `COUNTERFLOW`. Two direct tests were
   added.

## Deferred Items

- fully coupled iterated counterflow solution;
- per-cell geometry/property scalar variation;
- moving-boundary modeling;
- remaining two-phase HTC and DP closures;
- frozen component `contribute(trial, ctx)` integration;
- full-loop convergence acceptance;
- validation harnesses and later valves/manifolds.

## Phase Classification

Phase 11S is an approved Phase 11 checkpoint. Phase 11 remains open.

## Merge Readiness

`phase-11s-segmented-counterflow-phase-change-foundation` is approved for merge
into `main` as a Phase 11S checkpoint after the two closeout commits are
created and pushed. This audit does not authorize or perform the merge.
