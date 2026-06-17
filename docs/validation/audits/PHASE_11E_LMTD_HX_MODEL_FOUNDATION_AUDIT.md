# Phase 11E LMTD HX Model Foundation Audit

## Verdict

APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE

## Summary

Phase 11E adds a limited `LMTDModel` foundation as a `HeatExchangerModel` strategy. The model supports `FixedWallTemp` and `AmbientCoupling`, explicitly rejects `SinkInletTempAndFlow` and `FixedHeatRate`, and stays separate from `CorrelationRegistry` and `CorrelationRole`.

This is not full Phase 11 completion. The implementation deliberately does not add two-stream LMTD solving, primary outlet temperature iteration, correction factors, multi-pass models, segmented march, moving boundary, migrated boiling/condensation HTC, two-phase DP, loop residual integration, validation harnesses, DOE, dynamics, control, fitting, or optimization.

## Scope Audited

Audited branch: `phase-11e-lmtd-hx-model-foundation`

Files inspected:

- `src/mpl_sim/hx_models/lmtd.py`
- `src/mpl_sim/hx_models/__init__.py`
- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/registry.py`
- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/components/evaporator.py`
- `src/mpl_sim/components/condenser.py`
- `tests/hx_models/test_lmtd_model.py`

Authoritative documents consulted:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/roadmap/ROADMAP.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/architecture/SCHEMA_SPEC.md`
- `docs/validation/audits/PHASE_11_HEAT_EXCHANGER_MODEL_FOUNDATION_AUDIT.md`
- `docs/validation/audits/PHASE_11B_SINK_SIDE_EPSILON_NTU_AUDIT.md`
- `docs/validation/audits/PHASE_11C_HX_WRAPPER_INPUT_HARDENING_AUDIT.md`
- `docs/validation/audits/PHASE_11D_HX_BOUNDARY_CONDITION_EXPANSION_AUDIT.md`

Changed-file scope before audit docs:

- Modified: `src/mpl_sim/hx_models/__init__.py`
- Untracked implementation/test files: `src/mpl_sim/hx_models/lmtd.py`, `tests/hx_models/test_lmtd_model.py`

No unrelated implementation files were modified.

## Commands Executed

- `git branch --show-current`
  - `phase-11e-lmtd-hx-model-foundation`
- `git status --short --branch`
  - `## phase-11e-lmtd-hx-model-foundation`
  - `M src/mpl_sim/hx_models/__init__.py`
  - `?? src/mpl_sim/hx_models/lmtd.py`
  - `?? tests/hx_models/test_lmtd_model.py`
  - Git emitted local ignore permission warnings for `C:\Users\AndresH/.config/git/ignore`.
- `git log --oneline --decorate -8`
  - `dd256c0 (HEAD -> phase-11e-lmtd-hx-model-foundation, origin/main, origin/HEAD, main) merge: phase 11d hx boundary condition expansion`
  - `9bea1fd (origin/phase-11d-hx-boundary-condition-expansion, phase-11d-hx-boundary-condition-expansion) docs: audit phase 11d hx boundary condition expansion`
  - `b6586aa feat: support fixed-wall and ambient HX boundary conditions`
  - `a3b7d6b merge: phase 11c HX wrapper input hardening`
  - `dc90603 (origin/phase-11c-hx-wrapper-and-input-hardening, phase-11c-hx-wrapper-and-input-hardening) docs: audit phase 11c HX wrapper input hardening`
  - `4b57c14 merge: remove presentation artifacts`
  - `f4e5b5a (origin/chore/remove-presentation-artifacts, chore/remove-presentation-artifacts) chore: remove presentation artifacts`
  - `728489e test: harden HX wrapper forwarding and input validation`
- `git diff --stat`
  - `src/mpl_sim/hx_models/__init__.py | 3 +++`
  - Note: untracked `lmtd.py` and `test_lmtd_model.py` were not counted by this command.
- `git diff --stat main...HEAD`
  - No output because the branch starts at current `main`; Phase 11E changes were still uncommitted at audit time.
- `pytest`
  - Passed: `2490 passed`
  - Caveat: one `.pytest_cache` permission warning.
- `pytest tests/hx_models tests/components`
  - Passed: `1090 passed`
  - Caveat: one `.pytest_cache` permission warning.
- `ruff check src tests`
  - Passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - Passed: `118 files would be left unchanged`

## Critical Searches

### Forbidden Architecture Dependencies

Search roots:

- `src/mpl_sim/hx_models`
- `src/mpl_sim/components`

Pattern:

```text
CoolProp|PropertyBackend|mpl_sim\.network|mpl_sim\.solvers|CorrelationRegistry
```

Result: no forbidden real imports, construction, calls, or registry resolution were found. Matches were comments/docstrings documenting forbidden dependencies or registry separation. `LMTDModel` does not resolve `CorrelationRegistry`.

### Hidden Physical Defaults

Search roots:

- `src/mpl_sim/hx_models`
- `src/mpl_sim/components`

Pattern:

```text
4180|A_ht\s*=\s*1\.0|area\s*=\s*1\.0|D_h\s*=\s*1e-3|rho\s*=\s*1\.0|mu\s*=\s*1e-5|cp\s*=|clip|abs\(
```

Result: no hidden physical defaults or physical-output clipping were found. The only `abs(` match was the accepted `abs(Cr - 1.0) < 1e-9` epsilon-NTU numerical tolerance. The only `cp` matches were component wrappers forwarding caller-provided `primary_cp`.

### LMTD-Specific Searches

Search roots:

- `src/mpl_sim/hx_models/lmtd.py`
- `src/mpl_sim/hx_models/__init__.py`
- `src/mpl_sim/correlations/contract.py`

Pattern:

```text
LMTDModel|HeatExchangerModelKind\.LMTD|UnsupportedHeatExchangerBoundaryConditionError|SinkInletTempAndFlow|FixedHeatRate|FixedWallTemp|AmbientCoupling|htc_multiplier|UA_ambient|CorrelationRole
```

Result:

- `LMTDModel` is a `HeatExchangerModel`, not a correlation.
- `HeatExchangerModelKind.LMTD` is returned by `LMTDModel.kind()`.
- `LMTDModel` is exported from `mpl_sim.hx_models`.
- `CorrelationRole` contains no LMTD role.
- `FixedWallTemp` and `AmbientCoupling` are present as supported implementation paths.
- `SinkInletTempAndFlow` and `FixedHeatRate` are explicitly rejected with `UnsupportedHeatExchangerBoundaryConditionError`.
- `htc_multiplier` is applied only to the `FixedWallTemp` HTC/UA seam.
- `htc_multiplier` does not scale `UA_ambient`.

## Audit Checklist

### LMTDModel Identity and Registration

Pass.

- `LMTDModel.kind()` returns `HeatExchangerModelKind.LMTD`.
- `LMTDModel` is exported from `mpl_sim.hx_models`.
- `LMTDModel` can be registered and resolved through `HeatExchangerModelRegistry`.
- It is separate from `Correlation` and `CorrelationRole`; LMTD is absent from `CorrelationRole`.

### FixedWallTemp Support

Pass.

- `FixedWallTemp` is supported by `LMTDModel`.
- It requires explicit `primary_T_in`.
- It requires explicit finite positive `A_ht`.
- It requires injected `htc_primary`.
- It rejects missing, non-finite, zero, or negative HTC output before computing UA.
- The formula is equivalent to `UA = htc_multiplier * h_primary * A_ht`, `Q = UA * (T_wall - primary_T_in)`, and `h_out = h_in + Q / primary_mdot`.
- Heating, cooling, and zero-Q cases are tested.
- `htc_multiplier` scales Q.
- `friction_multiplier` affects DP only.
- HTC and DP verdicts are propagated.

### AmbientCoupling Support

Pass.

- `AmbientCoupling` is supported by `LMTDModel`.
- It requires explicit `primary_T_in`.
- It uses `UA_ambient` and `T_ambient` directly.
- It does not require `A_ht` for energy calculation.
- It does not require `htc_primary` for energy calculation.
- The formula is equivalent to `Q = UA_ambient * (T_ambient - primary_T_in)` and `h_out = h_in + Q / primary_mdot`.
- `htc_multiplier` leaves `UA_ambient` and Q unchanged, and this is tested.
- DP works if `dp_primary` is supplied.
- Empty verdicts are allowed when no correlation is called.

### Unsupported BC Behavior

Pass.

- `SinkInletTempAndFlow` raises `UnsupportedHeatExchangerBoundaryConditionError`.
- `FixedHeatRate` raises `UnsupportedHeatExchangerBoundaryConditionError`.
- Error messages name `LMTDModel` and explain why the path is deferred or unnecessary.
- The unsupported behavior avoids fake outlet-temperature closure and avoids treating prescribed heat rate as LMTD physics.

### DP Path and Calibration

Pass.

- DP is handled only through the injected `dp_primary` path.
- Non-finite DP outputs are rejected.
- Signed DP behavior is preserved; no `abs()` or clipping forces DP positive.
- `friction_multiplier` applies only to DP and outlet pressure, not energy.

### Hidden Physical Defaults

Pass.

Confirmed absent in the audited Phase 11E source:

- water `cp = 4180`;
- default heat-transfer area;
- default hydraulic diameter;
- default density;
- default viscosity;
- default primary temperature;
- default wall temperature;
- default ambient temperature;
- default ambient UA;
- default HTC;
- default DP affecting energy;
- clipping or absolute-value fixing of physical outputs.

The existing `roughness = 0.0` smooth-wall convention in DP input construction remains unchanged and is not part of the Phase 11E energy calculation.

### Architecture Boundaries

Pass.

- No CoolProp imports/calls in `hx_models/` or component wrappers.
- No `PropertyBackend` construction/calls in `hx_models/` or component wrappers.
- No Network/Solver imports in `hx_models/` or components.
- No `CorrelationRegistry` resolution inside `LMTDModel`.
- No architecture documents changed.
- No changes to Solver, Network, Pump, Accumulator, Pipe, schema/results/validation primitives.
- No segmented march, moving boundary, validation harness, DOE, dynamics, control, fitting, or optimization added.

### Tests

Pass.

Tests cover:

- model identity, export, and registry behavior;
- FixedWallTemp heating, cooling, zero-Q, enthalpy balance, required inputs, invalid HTC outputs, HTC calibration, DP path, DP verdicts, and friction calibration;
- AmbientCoupling heating, cooling, zero-Q, enthalpy balance, no-area/no-HTC energy path, no `htc_multiplier` effect on `UA_ambient`, DP path, DP verdicts, and empty-verdict no-correlation path;
- unsupported `SinkInletTempAndFlow` and `FixedHeatRate` behavior;
- LMTD import boundaries and absence from `CorrelationRole`;
- prior Phase 11B/11C/11D guarantees via the full and targeted test suites.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

None.

## Deferred Items

- Full two-stream LMTD solving for `SinkInletTempAndFlow`.
- Primary outlet temperature iteration.
- LMTD correction factors and multi-pass exchanger models.
- Segmented march and moving-boundary HX strategies.
- Migrated boiling/condensation HTC closures.
- Migrated two-phase DP closures.
- Full loop residual integration for evaporator/condenser behavior.
- Validation/literature harnesses.
- DOE/surrogate generation.
- Dynamics, control, fitting, and optimization.

## Phase Classification

Phase 11E checkpoint that should be merged before continuing Phase 11.

This is not full Phase 11 completion.

## Merge Readiness

Approved for merge as a checkpoint. The branch has no critical or major findings, required validation is green, and the implementation stays within the requested Phase 11E scope.
