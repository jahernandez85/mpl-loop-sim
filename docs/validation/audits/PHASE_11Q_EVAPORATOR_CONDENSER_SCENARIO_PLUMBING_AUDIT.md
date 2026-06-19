# Phase 11Q Evaporator/Condenser Scenario Plumbing Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 11Q adds component-level forwarding for the existing HX request fields
`q_flux_primary` and `dp_primary_is_two_phase`. Both evaporator and condenser
input value objects preserve the established defaults and pass explicit
caller-supplied closures, scalars, calibration multipliers, and thermal inputs
to `HXSolveRequest` without phase inference, property lookup, registry
resolution, or automatic closure selection.

The initial focused tests passed but did not directly prove unchanged
`geom_scalars` forwarding or the condenser missing-two-phase-scalar failure.
The audit added those three assertions. All required validation then passed
with 3303 tests. No critical, major, or remaining minor finding exists.

## Scope Audited

- `src/mpl_sim/components/evaporator.py`
- `src/mpl_sim/components/condenser.py`
- `tests/components/test_evaporator_condenser_scenario_plumbing.py`
- `docs/roadmap/PROJECT_STATUS.md`
- authoritative architecture, interface, correlation-contract, schema,
  decision-log, implementation-plan, and Phase 11N/11O/11P audit documents

No architecture, HX model, correlation implementation, registry, network,
solver, moving-boundary, valve, manifold, or full-loop file was modified.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-11q-evaporator-condenser-scenario-plumbing`
- `git status --short --branch`
  - expected component, focused-test, and status paths only before audit closeout
- `git log --oneline --decorate -10`
  - branch based on merged Phase 11P checkpoint `0bfbf3c`
- `git diff --stat`
- `git diff --stat main...HEAD`
- `git diff --cached --stat`
  - no staged changes before closeout

### Validation

- `pytest`
  - passed: `3303 passed`
- `pytest tests/correlations`
  - passed: `512 passed`
- `pytest tests/hx_models tests/components`
  - passed: `1641 passed`
- `pytest tests/components/test_evaporator_condenser_scenario_plumbing.py -v`
  - passed: `51 passed`
- `ruff check src tests`
  - passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - passed: `134 files would be left unchanged`

Pytest emitted one non-blocking Windows warning because `.pytest_cache` could
not be written.

## Component API Verification

- `EvaporatorHXInput` and `CondenserHXInput` each define:
  - `q_flux_primary: float | None = None`
  - `dp_primary_is_two_phase: bool = False`
- Existing required arguments and ordering are unchanged.
- The defaults preserve existing single-phase/no-q-flux behavior.
- Components do not inspect `FluidState` to infer phase.
- Components do not choose Shah, Yan, MSH, or any other closure.
- Components do not resolve `CorrelationRegistry`.
- Components do not call CoolProp or `PropertyBackend`.

## Forwarding Verification

Both component wrappers forward the following directly into
`HXSolveRequest`:

- `q_flux_primary`
- `dp_primary_is_two_phase`
- `htc_primary`
- `htc_secondary`
- `dp_primary`
- `geom_scalars`
- `friction_multiplier`
- `htc_multiplier`
- all existing thermal, boundary-condition, model, geometry, and
  discretization fields

Primary q-flux is assigned only to `q_flux_primary`. Components do not build
`property_scalars`; the Phase 11P HX builders retain that responsibility.
Focused recording-model tests prove exact new-field forwarding and unchanged
geometry-scalar values.

## Scenario Coverage

### Evaporator

- Default fixed-heat-rate behavior and energy balance remain unchanged.
- Explicit `ShahBoilingHTC` evaluates when q-flux and required scalars are
  supplied.
- Shah without q-flux fails clearly with `q_flux` in the error.
- Explicit `MSHTwoPhaseFrictionGradient` evaluates when the two-phase flag and
  all required scalars are supplied.
- Missing two-phase property/length scalars fail with the missing key named.
- No Shah or MSH selection occurs automatically.

### Condenser

- Default fixed-heat-rate behavior and energy balance remain unchanged.
- Explicit `YanCondensationHTC` evaluates without q-flux.
- Explicit MSH two-phase DP evaluates when enabled with complete scalars.
- Missing condenser two-phase DP scalar `mu_v` fails clearly.
- No Yan or MSH selection occurs automatically.

## Test Coverage

The 51 focused tests cover defaults, direct request capture, exact q-flux and
two-phase-mode forwarding, unchanged geometry scalars, Shah and Yan integration,
energy balance, verdict propagation, missing q-flux, invalid q-flux, missing
two-phase scalars on both component families, explicit closure selection, and
forbidden dependency/import boundaries.

Existing component wrapper tests continue to cover the previously established
thermal, boundary-condition, correlation, and multiplier fields.

## Critical Searches

Required searches found:

- no real CoolProp or `PropertyBackend` dependency in component/HX/correlation
  implementation;
- no Network or Solver dependency in component/HX implementation;
- no `CorrelationRegistry` resolution inside components or HX models;
- no hidden production defaults for density, viscosity, diameter, quality,
  cell length, or heat flux;
- only accepted comments/docstrings, test fixture values, registry definitions,
  and pre-existing formula-level `abs`/epsilon-NTU logic.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

None remaining.

The initial focused-test evidence gaps for unchanged `geom_scalars` forwarding
and condenser missing-scalar failure were corrected during the audit.

## Deferred Items

- additional two-phase DP and HTC closures;
- counterflow and broader phase-change segmented coupling;
- moving-boundary modeling;
- Scenario binding through the full component contribution path;
- full pump/evaporator/condenser/accumulator loop convergence;
- validation harnesses, valves, and manifolds.

## Phase Classification

Phase 11Q is an approved checkpoint. Phase 11 remains open.

## Merge Readiness

`phase-11q-evaporator-condenser-scenario-plumbing` is approved for merge into
`main` as a Phase 11Q checkpoint after the implementation/test and audit/status
commits are created and pushed. This audit does not authorize merging to
`main`.
