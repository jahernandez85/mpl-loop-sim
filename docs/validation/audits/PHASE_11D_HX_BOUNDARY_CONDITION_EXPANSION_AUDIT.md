# Phase 11D HX Boundary Condition Expansion Audit

## Verdict

APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE

## Summary

Phase 11D is a successful checkpoint. The branch adds real `EpsilonNTUModel`
support for `FixedWallTemp` and `AmbientCoupling` without adding LMTD,
segmented march, moving-boundary models, validation harnesses, DOE, dynamics,
control, fitting, optimization, or loop integration.

No critical, major, or minor findings were found. The implementation remains
inside the intended HX model boundary, uses injected correlations only, avoids
hidden physical defaults, and preserves the tested Phase 11B/11C behavior.

## Scope Audited

Audited branch: `phase-11d-hx-boundary-condition-expansion`

Files inspected:

- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/epsilon_ntu.py`
- `src/mpl_sim/hx_models/__init__.py`
- `src/mpl_sim/components/evaporator.py`
- `src/mpl_sim/components/condenser.py`
- `tests/hx_models/test_epsilon_ntu_fixed_wall_temp.py`
- `tests/hx_models/test_epsilon_ntu_ambient_coupling.py`
- `tests/hx_models/test_epsilon_ntu_model.py`
- `tests/hx_models/test_epsilon_ntu_sink_side.py`
- `tests/hx_models/test_hx_model_input_hardening.py`

Changed-file scope before audit docs:

- `src/mpl_sim/hx_models/epsilon_ntu.py`
- `tests/hx_models/test_epsilon_ntu_ambient_coupling.py`
- `tests/hx_models/test_epsilon_ntu_fixed_wall_temp.py`
- `tests/hx_models/test_epsilon_ntu_model.py`

No unrelated roadmap areas were modified by the Phase 11D implementation.

## Commands Executed

- `git branch --show-current`:
  - `phase-11d-hx-boundary-condition-expansion`
- `git status --short --branch`:
  - `## phase-11d-hx-boundary-condition-expansion...origin/phase-11d-hx-boundary-condition-expansion`
  - Git emitted a local config ignore permission warning for `C:\Users\AndresH/.config/git/ignore`; this did not affect repository status.
- `git log --oneline --decorate -8`:
  - `b6586aa (HEAD -> phase-11d-hx-boundary-condition-expansion, origin/phase-11d-hx-boundary-condition-expansion) feat: support fixed-wall and ambient HX boundary conditions`
  - `a3b7d6b (origin/main, origin/HEAD, main) merge: phase 11c HX wrapper input hardening`
  - `dc90603 (origin/phase-11c-hx-wrapper-and-input-hardening, phase-11c-hx-wrapper-and-input-hardening) docs: audit phase 11c HX wrapper input hardening`
  - `4b57c14 merge: remove presentation artifacts`
  - `f4e5b5a (origin/chore/remove-presentation-artifacts, chore/remove-presentation-artifacts) chore: remove presentation artifacts`
  - `728489e test: harden HX wrapper forwarding and input validation`
  - `ce6fa20 docs: add MPL library scientific presentation`
  - `63b8d4f merge: phase 11b sink-side epsilon NTU support`
- `git diff --stat main...HEAD`:
  - 4 files changed, 957 insertions, 54 deletions
  - Changes limited to `epsilon_ntu.py` and HX model tests.
- `pytest`:
  - Passed: `2418 passed`
  - Caveat: pytest emitted one `.pytest_cache` permission warning.
- `pytest tests/hx_models tests/components`:
  - Passed: `1018 passed`
  - Caveat: pytest emitted one `.pytest_cache` permission warning.
- `ruff check src tests`:
  - Passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`:
  - Passed: `116 files would be left unchanged`
  - No timeout occurred.

## Critical Searches

### Forbidden architecture dependencies

Search roots:

- `src/mpl_sim/hx_models`
- `src/mpl_sim/components`

Patterns:

- `CoolProp`
- `PropertyBackend`
- `mpl_sim.network`
- `mpl_sim.solvers`
- `CorrelationRegistry`

Result: no forbidden real imports, construction, registry resolution, or calls
were found. Matches were comments/docstrings documenting forbidden dependencies
or separation constraints. `EpsilonNTUModel` does not resolve
`CorrelationRegistry`.

### Hidden physical defaults

Search roots:

- `src/mpl_sim/hx_models`
- `src/mpl_sim/components`

Patterns:

- `4180`
- `A_ht *= *1.0`
- `area *= *1.0`
- `D_h *= *1e-3`
- `rho *= *1.0`
- `mu *= *1e-5`
- `cp *=`
- `clip`
- `abs(`

Result: no hidden physical defaults or clipping were found.

The only `cp` matches were component wrappers forwarding caller-provided
`primary_cp`. The only `abs(` match was the accepted
`abs(Cr - 1.0) < 1e-9` counterflow numerical tolerance.

### Phase 11D-specific searches

Search root:

- `src/mpl_sim/hx_models/epsilon_ntu.py`

Patterns:

- `FixedWallTemp`
- `AmbientCoupling`
- `htc_multiplier`
- `UA_ambient`
- `UnsupportedHeatExchangerBoundaryConditionError`

Result: all expected terms are present in real implementation paths.

- `FixedWallTemp` uses explicit `primary_T_in`, explicit finite positive
  `A_ht`, and injected `htc_primary`.
- `FixedWallTemp` computes `UA = htc_multiplier * h_primary * A_ht` and
  `Q = UA * (T_wall - primary_T_in)`.
- `AmbientCoupling` computes `Q = UA_ambient * (T_ambient - primary_T_in)`.
- `AmbientCoupling` does not require `A_ht` or `htc_primary` for energy.
- `AmbientCoupling` does not apply `htc_multiplier` to `UA_ambient`.
- `UnsupportedHeatExchangerBoundaryConditionError` remains as a future-proof
  guard for unrecognized BC objects.

## Audit Checklist

### FixedWallTemp support

- Is `FixedWallTemp` now actually supported by `EpsilonNTUModel`? Yes.
- Does it require explicit `primary_T_in`? Yes.
- Does it require explicit finite positive `A_ht`? Yes.
- Does it require injected `htc_primary`? Yes.
- Does it reject invalid HTC outputs before computing UA? Yes.
- Is the heat-rate formula equivalent to `UA = h_primary * A_ht` and
  `Q = UA * (T_wall - primary_T_in)`? Yes, with the documented
  `htc_multiplier` applied at the HTC/UA seam.
- Is the sign convention tested for heating and cooling? Yes.
- Is `h_out = h_in + Q / primary_mdot` tested? Yes.
- Does `htc_multiplier` scale UA and Q? Yes.
- Does `friction_multiplier` affect DP only? Yes.
- Are HTC/DP verdicts propagated? Yes.

### AmbientCoupling support

- Is `AmbientCoupling` now actually supported by `EpsilonNTUModel`? Yes.
- Does it require explicit `primary_T_in`? Yes.
- Does it use `AmbientCoupling.UA_ambient` and `T_ambient` directly? Yes.
- Does it avoid requiring `A_ht` for energy calculation? Yes.
- Does it avoid requiring `htc_primary` for energy calculation? Yes.
- Is the heat-rate formula equivalent to
  `Q = UA_ambient * (T_ambient - primary_T_in)`? Yes.
- Does `htc_multiplier` leave `UA_ambient` and Q unchanged? Yes.
- Is that calibration decision tested? Yes.
- Does DP still work if `dp_primary` is supplied? Yes.
- Are DP verdicts propagated if DP is called? Yes.
- Are empty verdicts allowed when no correlation is called? Yes.
- Is the sign convention tested for heating and cooling? Yes.
- Is `h_out = h_in + Q / primary_mdot` tested? Yes.

### Unsupported BC behavior

All declared `SecondaryFluidBC` variants are now supported by
`EpsilonNTUModel`:

- `FixedHeatRate`
- `SinkInletTempAndFlow`
- `FixedWallTemp`
- `AmbientCoupling`

`UnsupportedHeatExchangerBoundaryConditionError` remains only as a
future-proof guard for unrecognized BC objects. Tests were updated so they no
longer incorrectly expect `FixedWallTemp` or `AmbientCoupling` to be
unsupported.

### Correlation and calibration boundaries

- Correlations are still injected through `HXSolveRequest`.
- `EpsilonNTUModel` does not resolve correlations internally.
- `htc_multiplier` is applied to HTC/UA seams and is tracked for fixed heat
  rate; it is not used to alter prescribed conservation balances.
- `friction_multiplier` is applied only to DP.
- `AmbientCoupling` deliberately avoids applying `htc_multiplier` to
  `UA_ambient`; this is tested.

### Hidden physical defaults

Confirmed absent:

- water `cp = 4180`
- default heat-transfer area
- default hydraulic diameter
- default density
- default viscosity
- default primary temperature
- default wall temperature
- default ambient temperature
- default ambient UA
- silent HTC default
- silent DP default that affects energy
- clipping or absolute-value fixing of physical outputs

The existing `roughness = 0.0` smooth-wall convention remains unchanged and
tested.

### Architecture boundaries

Confirmed:

- no CoolProp imports/calls in `hx_models/` or component wrappers;
- no `PropertyBackend` construction/calls;
- no Network/Solver imports in `hx_models/` or HX wrappers;
- no `CorrelationRegistry` resolution inside `EpsilonNTUModel`;
- no changes to Solver, Network, Pump, Accumulator, Pipe, schema/results, or
  validation primitives;
- no architecture docs changed;
- no LMTD, segmented march, moving boundary, validation harness, DOE,
  dynamics, control, fitting, or optimization added.

### Tests

Tests cover:

- happy paths and failure paths;
- heating and cooling sign convention;
- missing/invalid required inputs;
- invalid HTC outputs for `FixedWallTemp`;
- DP path and DP verdict propagation;
- `AmbientCoupling` not requiring HTC or area;
- `htc_multiplier` not affecting `UA_ambient`;
- preservation of previous Phase 11B/11C guarantees.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

None.

## Deferred Items

The following remain deferred for later Phase 11 continuation or later phases:

- LMTD strategy;
- segmented march strategy;
- moving-boundary strategy;
- migrated boiling/condensation HTC and two-phase DP closures;
- loop residual integration for evaporator/condenser behavior;
- validation harnesses, DOE, dynamics, controls, fitting, and optimization.

## Phase Classification

This is a Phase 11D checkpoint that should be merged before continuing Phase
11. It is not full Phase 11 completion.

## Merge Readiness

Approved for merge as a checkpoint.

Recommended commit message:

```text
docs: audit phase 11d hx boundary condition expansion
```
