# Phase 11F Segmented HX Model Foundation Audit

## Verdict

APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE

## Summary

Phase 11F adds a limited `SegmentedMarchModel` foundation as a
`HeatExchangerModel` strategy. The model supports only `FixedHeatRate`, marches
primary enthalpy cell-by-cell over explicit `UNIFORM` discretization, records an
immutable diagnostic `SegmentedProfile`, and handles optional cell-wise primary
DP through injected `dp_primary` correlations.

This is not full Phase 11 completion. The implementation deliberately does not
add segment-wise `SinkInletTempAndFlow`, `FixedWallTemp`, `AmbientCoupling`,
local HTC/UA solving, boiling/condensation HTC migration, two-phase DP
migration, moving-boundary behavior, loop residual assembly, validation
harnesses, DOE, dynamics, control, fitting, or optimization.

## Scope Audited

Audited branch: `phase-11f-segmented-hx-model-foundation`

Files inspected:

- `src/mpl_sim/hx_models/segmented.py`
- `src/mpl_sim/hx_models/__init__.py`
- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/registry.py`
- `src/mpl_sim/discretization/primitives.py`
- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/components/evaporator.py`
- `src/mpl_sim/components/condenser.py`
- `tests/hx_models/test_segmented_march_model.py`

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
- `docs/validation/audits/PHASE_11E_LMTD_HX_MODEL_FOUNDATION_AUDIT.md`

Changed-file scope before audit docs:

- Modified: `src/mpl_sim/hx_models/__init__.py`
- Untracked implementation/test files:
  - `src/mpl_sim/hx_models/segmented.py`
  - `tests/hx_models/test_segmented_march_model.py`

No unrelated implementation files were modified. The accidental file
`src/mpl_sim/hx_models/init.py` is not present.

## Commands Executed

- `git branch --show-current`
  - `phase-11f-segmented-hx-model-foundation`
- `git status --short --branch`
  - `## phase-11f-segmented-hx-model-foundation`
  - `M src/mpl_sim/hx_models/__init__.py`
  - `?? src/mpl_sim/hx_models/segmented.py`
  - `?? tests/hx_models/test_segmented_march_model.py`
  - Git emitted local ignore permission warnings for
    `C:\Users\AndresH/.config/git/ignore`.
- `git log --oneline --decorate -8`
  - `aee1a88 (HEAD -> phase-11f-segmented-hx-model-foundation, origin/main, origin/HEAD, main) merge: phase 11e LMTD HX model foundation`
  - `f1df571 (origin/phase-11e-lmtd-hx-model-foundation, phase-11e-lmtd-hx-model-foundation) docs: audit phase 11e LMTD HX model foundation`
  - `b8bee95 feat: add LMTD heat exchanger model foundation`
  - `dd256c0 merge: phase 11d hx boundary condition expansion`
  - `9bea1fd (origin/phase-11d-hx-boundary-condition-expansion, phase-11d-hx-boundary-condition-expansion) docs: audit phase 11d hx boundary condition expansion`
  - `b6586aa feat: support fixed-wall and ambient HX boundary conditions`
  - `a3b7d6b merge: phase 11c HX wrapper input hardening`
  - `dc90603 (origin/phase-11c-hx-wrapper-and-input-hardening, phase-11c-hx-wrapper-and-input-hardening) docs: audit phase 11c HX wrapper input hardening`
- `git diff --stat`
  - `src/mpl_sim/hx_models/__init__.py | 14 ++++++++++++++`
  - Note: untracked `segmented.py` and `test_segmented_march_model.py` were not
    counted by this command.
- `git diff --stat main...HEAD`
  - No output because the branch starts at current `main`; Phase 11F changes
    were still uncommitted at audit time.
- `git status --short`
  - `M src/mpl_sim/hx_models/__init__.py`
  - `?? src/mpl_sim/hx_models/segmented.py`
  - `?? tests/hx_models/test_segmented_march_model.py`
- `pytest`
  - Passed: `2547 passed`
  - Caveat: one `.pytest_cache` permission warning.
- `pytest tests/hx_models tests/components`
  - Passed: `1147 passed`
  - Caveat: one `.pytest_cache` permission warning.
- `ruff check src tests`
  - Passed: `All checks passed!`
- `black --check --no-cache --verbose src tests`
  - Passed: `120 files would be left unchanged`

## Critical Searches

### Forbidden Architecture Dependencies

Search roots:

- `src/mpl_sim/hx_models`
- `src/mpl_sim/components`

Pattern:

```text
CoolProp|PropertyBackend|mpl_sim\.network|mpl_sim\.solvers|CorrelationRegistry
```

Result: no forbidden real imports, construction, calls, or registry resolution
were found. Matches were comments/docstrings documenting forbidden dependencies
or registry separation. `SegmentedMarchModel` does not resolve
`CorrelationRegistry`.

### Hidden Physical Defaults

Search roots:

- `src/mpl_sim/hx_models`
- `src/mpl_sim/components`

Pattern:

```text
4180|A_ht\s*=\s*1\.0|area\s*=\s*1\.0|D_h\s*=\s*1e-3|rho\s*=\s*1\.0|mu\s*=\s*1e-5|cp\s*=|clip|abs\(
```

Result: no hidden physical defaults or physical-output clipping were found. The
only `abs(` match was the accepted `abs(Cr - 1.0) < 1e-9` epsilon-NTU numerical
tolerance. The only `cp` matches were component wrappers forwarding
caller-provided `primary_cp`.

### Segmented-Specific Searches

Search roots:

- `src/mpl_sim/hx_models/segmented.py`
- `src/mpl_sim/hx_models/__init__.py`
- `src/mpl_sim/correlations/contract.py`

Pattern:

```text
SegmentedMarchModel|SegmentedCellRecord|SegmentedProfile|HeatExchangerModelKind\.SEGMENTED_MARCH|UnsupportedHeatExchangerBoundaryConditionError|FixedHeatRate|SinkInletTempAndFlow|FixedWallTemp|AmbientCoupling|CorrelationRole|friction_multiplier|raw_dP_primary|zone_profile
```

Result:

- `SegmentedMarchModel` is a `HeatExchangerModel`, not a correlation.
- `SegmentedMarchModel.kind()` returns
  `HeatExchangerModelKind.SEGMENTED_MARCH`.
- `SegmentedMarchModel`, `SegmentedCellRecord`, and `SegmentedProfile` are
  exported from `mpl_sim.hx_models`.
- `CorrelationRole` contains no segmented-march role.
- `FixedHeatRate` is supported.
- `SinkInletTempAndFlow`, `FixedWallTemp`, and `AmbientCoupling` are explicitly
  rejected with `UnsupportedHeatExchangerBoundaryConditionError`.
- `zone_profile` contains the immutable diagnostic `SegmentedProfile`.
- `raw_dP_primary` is the pre-calibration sum of per-cell raw DP outputs.
- `friction_multiplier` affects DP and pressure only, not `Q` or enthalpy.

## Audit Checklist

### Model Identity and Registration

Pass.

- `SegmentedMarchModel.kind()` returns
  `HeatExchangerModelKind.SEGMENTED_MARCH`.
- `SegmentedMarchModel` is exported from `mpl_sim.hx_models`.
- `SegmentedCellRecord` and `SegmentedProfile` are intentionally exported as
  diagnostic value objects.
- The model can be registered and resolved through
  `HeatExchangerModelRegistry`.
- It remains separate from `Correlation` and `CorrelationRole`; segmented march
  is absent from `CorrelationRole`.

### FixedHeatRate Segmented Energy

Pass.

- `FixedHeatRate` is supported.
- Total `Q` is split evenly as `Q_cell = Q_total / n_cells`.
- Each cell marches enthalpy as `h_next = h_current + Q_cell / primary_mdot`.
- Final `h_out = h_in + Q_total / primary_mdot`.
- Positive, negative, and zero `Q` are tested.
- The sum of cell `Q_cell` values equals total `Q`.
- The last cell `h_out` equals the result outlet enthalpy.
- Fluid identity is preserved. Pressure is unchanged when DP is absent and
  marched consistently when DP is present.

### Discretization and Cell Count

Pass.

- The model consumes the existing `DiscretizationSpec`.
- `UNIFORM` is required.
- `LUMPED` and `MOVING_BOUNDARY` are rejected clearly.
- `n_cells > 0` is enforced by `DiscretizationSpec` and checked again at the
  model boundary.
- `n_cells = 1` is explicitly allowed and tested.
- Missing or invalid `n_cells` for `UNIFORM` is rejected by
  `DiscretizationSpec`.
- No ambiguous new discretization contract was introduced.

### DP Path and Calibration

Pass.

- `dp_primary` is optional.
- If absent, total DP remains zero, outlet pressure is unchanged, and verdicts
  are empty.
- If present, DP is handled cell-wise.
- `dp_primary` is called exactly once per cell.
- Each DP call receives the current cell inlet `FluidState`.
- Required DP input scalars `rho`, `mu`, `G`, `D_h`, and `L_cell` are explicit
  and validated as finite and positive.
- Non-finite DP outputs are rejected.
- Signed DP behavior is preserved; negative DP is allowed as pressure recovery.
- `raw_dP_primary` is the sum of raw pre-calibration DP outputs.
- `friction_multiplier` is applied once to total raw DP, equivalently to each
  cell for pressure marching, without double calibration.
- `friction_multiplier` affects DP and pressure only, not `Q` or enthalpy.
- DP verdicts are propagated for every DP call.
- The cell profile distinguishes `raw_dP_cell` and calibrated `dP_cell`.

### zone_profile / Cell Profile

Pass.

- `SegmentedProfile` is immutable.
- `SegmentedCellRecord` is immutable.
- `HXSolveResult.zone_profile` contains the segmented diagnostic profile.
- It is diagnostic only and is not stored in `SystemState` or attached to
  Ports.
- It contains cell index, `Q_cell`, `h_in`, `h_out`, `raw_dP_cell`, `dP_cell`,
  `P_in`, and `P_out`.
- The number of cell records equals `n_cells`.

### Unsupported BC Behavior

Pass.

- `SinkInletTempAndFlow` raises
  `UnsupportedHeatExchangerBoundaryConditionError`.
- `FixedWallTemp` raises `UnsupportedHeatExchangerBoundaryConditionError`.
- `AmbientCoupling` raises `UnsupportedHeatExchangerBoundaryConditionError`.
- Error messages are clear and state that the feature is deferred.
- The implementation avoids fake secondary coupling and fake local UA solving.

### Hidden Physical Defaults

Pass.

Confirmed absent in the audited Phase 11F source:

- water `cp = 4180`;
- default heat-transfer area;
- default hydraulic diameter;
- default density;
- default viscosity;
- default mass flux;
- default quality;
- default cell count unless explicit in `DiscretizationSpec`;
- default local HTC;
- default local DP affecting energy;
- clipping or absolute-value fixing of physical outputs.

The existing `roughness = 0.0` smooth-wall convention in DP input construction
remains unchanged and tested in prior HX hardening work.

### Architecture Boundaries

Pass.

- No CoolProp imports/calls in `hx_models/` or component wrappers.
- No `PropertyBackend` construction/calls in `hx_models/` or component wrappers.
- No Network/Solver imports in `hx_models/` or components.
- No `CorrelationRegistry` resolution inside `SegmentedMarchModel`.
- No architecture documents changed.
- No changes to Solver, Network, Pump, Accumulator, Pipe,
  schema/results/validation primitives.
- No segment-wise secondary coupling, local HTC/UA solving, moving boundary,
  validation harness, DOE, dynamics, control, fitting, or optimization added.

### Tests

Pass.

Tests cover:

- model identity, export, and registry behavior;
- absence of segmented march from `CorrelationRole`;
- positive, negative, and zero `FixedHeatRate`;
- `n_cells = 1` and `n_cells > 1`;
- `LUMPED` and `MOVING_BOUNDARY` rejection;
- DP absent and DP present paths;
- cell-wise DP call count and cell-inlet state propagation;
- DP verdict propagation;
- raw vs calibrated DP;
- negative DP pressure recovery;
- DP not affecting enthalpy;
- `friction_multiplier` not affecting energy;
- unsupported `SinkInletTempAndFlow`, `FixedWallTemp`, and `AmbientCoupling`;
- architecture import boundaries;
- prior Phase 11B/11C/11D/11E guarantees via full and targeted suites.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

None.

## Deferred Items

- Segment-wise `SinkInletTempAndFlow`.
- Segment-wise `FixedWallTemp`.
- Segment-wise `AmbientCoupling`.
- Local HTC/UA solving per segment.
- Boiling/condensation HTC closure migrations.
- Two-phase DP closure migrations.
- Moving-boundary HX model.
- Full loop residual assembly for evaporator/condenser behavior.
- Validation/literature harnesses.
- DOE/surrogate generation.
- Dynamics, control, fitting, and optimization.

## Phase Classification

Phase 11F checkpoint that should be merged before continuing Phase 11.

This is not full Phase 11 completion.

## Merge Readiness

Approved for merge as a checkpoint. The branch has no critical or major
findings, required validation is green, and the implementation stays within the
requested Phase 11F scope.
