# Phase 11O Two-Phase DP Migration Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

Phase 11O migrates `MSHTwoPhaseFrictionGradient` under
`CorrelationRole.TWO_PHASE_DP`. The closure returns one positive frictional
pressure-loss gradient in Pa/m for positive mass flux.

The previously blocking frozen-contract issue is resolved by Decision 011.
`TwoPhaseDPInput` has no direct `rho_l`, `rho_v`, `mu_l`, or `mu_v` fields. It
instead carries an immutable, caller-supplied `property_scalars` mapping with
an empty default. The MSH closure requires and validates the four property
keys without property lookup or hidden defaults.

All required validation passes. No critical, major, or minor finding remains.

## Scope Audited

- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/correlations/two_phase_dp.py`
- `src/mpl_sim/correlations/__init__.py`
- `tests/correlations/test_two_phase_dp.py`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/decisions/DECISION_LOG.md`
- `docs/roadmap/PROJECT_STATUS.md`
- existing correlation registry and HX/component integration boundaries

No unrelated source, HX, network, solver, moving-boundary, valve, manifold, or
full-loop change is present. No accidental
`src/mpl_sim/correlations/init.py` exists.

## Commands Executed

### Git inspection

- `git branch --show-current`
  - `phase-11o-two-phase-dp-migration`
- `git status --short --branch`
  - five expected unstaged correction files before audit closeout
- `git diff --stat`
  - correction scope limited to contract, MSH implementation, focused tests,
    correlation contract, and Decision 011
- `git diff --cached --stat`
  - no staged changes before closeout
- `git diff --stat main...HEAD`
  - pre-existing Phase 11O implementation commit retained
- `git log --oneline --decorate -10`
  - implementation commit `a6d9bfc`

### Required validation

- `pytest`
  - passed: `3130 passed`
- `pytest tests/correlations`
  - passed: `512 passed`
- `pytest tests/correlations/test_two_phase_dp.py -v`
  - passed: `83 passed`
- `pytest tests/hx_models tests/components`
  - passed: `1468 passed`
- `ruff check src tests`
  - passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - passed: `132 files would be left unchanged`

Pytest emitted one non-blocking Windows warning because `.pytest_cache` could
not be written. Test collection and execution completed successfully.

## Previous Blocking Findings and Resolution

### Smooth-wall behavior

Resolved. The migrated MSH/PyP2PL variant uses the smooth-wall Churchill
friction factor. Roughness is not a `TwoPhaseDPInput` field or formula
parameter. Documentation and focused tests state and protect this semantic.

### Re < 1 behavior

Resolved. `Re_lo < 1` or `Re_vo < 1` yields an `EXTRAPOLATED` verdict with the
specific violated Reynolds bound in metadata. `Re = 1` remains in-envelope.
Full PyP2PL equivalence is claimed only for `Re >= 1`.

### L_cell semantics

Resolved. `CorrelationOutput.value[0]` is a pressure gradient in Pa/m.
`L_cell` is not consumed, and no gradient-to-drop conversion occurs in the
correlation. Focused tests prove output independence from `L_cell`.

### Fluid-family validity scope

Resolved. The envelope declares
`FluidClassSpec(FluidClass.REFRIGERANT)` and does not use `AnyFluid()`.

### TwoPhaseDPInput property scalar mapping

Resolved. `TwoPhaseDPInput` contains `property_scalars: Mapping[str, float]`
and no direct liquid/vapor density or viscosity fields. Construction copies
the mapping into a `MappingProxyType`; the default is an empty mapping.

## Decision 011 and Contract Update

Decision 011 explicitly authorizes the `TwoPhaseDPInput.property_scalars`
mapping and amends the frozen field manifest in
`CORRELATION_CONTRACT.md` section 4.4.

The binding rules require caller-supplied formula-specific scalars, no
property lookup, no hidden defaults, clear validation of missing or invalid
keys, no automatic closure selection, and explicit HX builder/plumbing before
integration. Existing `L_cell` gradient semantics remain unchanged.

## Correlation Implementation Verification

`MSHTwoPhaseFrictionGradient` implements the existing `Correlation` contract,
reports the `TWO_PHASE_DP` role, and returns exactly one value with verdict and
metadata.

`_require_scalar()` validates key presence, finiteness, and strict positivity.
Missing, zero, negative, NaN, and infinite `rho_l`, `rho_v`, `mu_l`, or `mu_v`
values fail clearly.

The implementation has no CoolProp or `PropertyBackend` dependency, property
lookup, quality clamp, density/viscosity/diameter/length default, automatic
closure selection, or registry resolution.

Focused numerical tests compare against an independent MSH calculation at
multiple qualities and conditions rather than comparing the implementation to
itself.

## Output Semantics

`CorrelationOutput.value[0]` is the positive frictional pressure-loss gradient
in Pa/m for positive mass flux. Gravity and acceleration are excluded.
Multiplication by cell length belongs downstream in the component/HX layer.

## HX Seam Status

Two-phase DP HX injection remains intentionally deferred. Current HX DP
builders construct `SinglePhaseDPInput` and consume DP output as a pressure
drop. Integration requires:

1. an explicit `TwoPhaseDPInput` builder;
2. explicit population of required `property_scalars`;
3. explicit gradient-to-drop multiplication by `L_cell`.

No HX registry resolution or partial integration was added.

## Critical Searches

Searches across correlations, HX models, components, tests, architecture,
decisions, and roadmap documents found:

- no prohibited CoolProp or `PropertyBackend` implementation dependency;
- no correlation dependency on network or solvers;
- no `CorrelationRegistry` resolution inside HX models;
- no hidden density, viscosity, diameter, quality, roughness, or length
  defaults;
- no quality clipping or hidden gradient/drop conversion;
- only documented/accepted min/max and signed-flow uses outside this closure;
- no direct `TwoPhaseDPInput.rho_l`, `rho_v`, `mu_l`, or `mu_v` fields.

Matches for forbidden dependency names were comments/docstrings documenting
the boundary or existing registry definitions, not prohibited calls.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

None.

## Deferred Items

- explicit two-phase DP HX builder and gradient-to-drop conversion;
- remaining two-phase DP closures, including Homogeneous/Cicchitti and
  Kim-Mudawar 2013;
- remaining Phase 11 counterflow/phase-change coupling;
- moving-boundary and full-loop convergence work.

## Phase Classification

Phase 11O is an approved checkpoint. Phase 11 remains open.

## Merge Readiness

`phase-11o-two-phase-dp-migration` is approved for merge into `main` as a
Phase 11O checkpoint after the two closeout commits are created and pushed.

