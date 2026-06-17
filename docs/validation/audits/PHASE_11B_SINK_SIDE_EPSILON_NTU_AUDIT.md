# Phase 11B Sink-side Epsilon-NTU Audit

## Verdict

**APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE**

## Summary

The `phase-11b-hx-physics-continuation` branch adds real `SinkInletTempAndFlow` support to `EpsilonNTUModel` as a lumped counterflow epsilon-NTU calculation. The implementation uses explicit precomputed thermal scalars, explicit `PrimaryThermalMode`, explicit `UAComputationMode`, injected HTC/DP correlations, and the established sign convention:

`Q > 0` means heat is added to the primary fluid, `Q < 0` means heat is rejected by the primary fluid, and `h_out = h_in + Q / primary_mdot`.

The branch preserves the frozen architecture boundaries. `FluidState` remains pure `(P, h, identity)`, `mdot` remains outside `FluidState`, ports remain value-free, `SystemState` remains the numerical owner, HX models do not call property backends or registries, and epsilon-NTU remains a `HeatExchangerModel` strategy rather than a `CorrelationRole`.

This is still a Phase 11 checkpoint, not full Phase 11 completion. LMTD, segmented/moving-boundary models, migrated boiling/condensation HTC closures, two-phase DP closures, loop residual integration, validation harness activation, DOE, dynamics, controls, and optimization remain deferred.

## Scope Audited

Source files inspected:

- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/epsilon_ntu.py`
- `src/mpl_sim/hx_models/__init__.py`
- `src/mpl_sim/hx_models/registry.py`
- `src/mpl_sim/components/evaporator.py`
- `src/mpl_sim/components/condenser.py`
- `src/mpl_sim/components/base.py`
- `src/mpl_sim/correlations/contract.py`
- `src/mpl_sim/correlations/registry.py`
- `src/mpl_sim/core/fluid_state.py`
- `src/mpl_sim/core/port.py`
- `src/mpl_sim/core/state.py`
- `src/mpl_sim/properties/`
- `src/mpl_sim/network/`
- `src/mpl_sim/solvers/`

Tests inspected:

- `tests/hx_models/test_epsilon_ntu_sink_side.py`
- `tests/hx_models/test_epsilon_ntu_model.py`
- `tests/hx_models/test_secondary_bc.py`
- `tests/components/test_evaporator_component.py`
- `tests/components/test_condenser_component.py`
- relevant component boundary tests under `tests/components/`

Documentation consulted:

- `docs/roadmap/PROJECT_STATUS.md`
- `docs/roadmap/IMPLEMENTATION_PLAN.md`
- `docs/architecture/ARCHITECTURE_MASTER.md`
- `docs/architecture/INTERFACE_SPEC.md`
- `docs/architecture/CORRELATION_CONTRACT.md`
- `docs/validation/audits/PHASE_11_HEAT_EXCHANGER_MODEL_FOUNDATION_AUDIT.md`

## Commands Executed

- `git branch --show-current` - `phase-11b-hx-physics-continuation`
- `git status` - clean working tree on `phase-11b-hx-physics-continuation`; Git warned that `C:\Users\AndresH/.config/git/ignore` was permission-denied.
- `git log --oneline --decorate -8` - HEAD is `a723383 feat: add sink-side epsilon NTU support`; `main` and `origin/main` are at `6667d5b merge: normalize test directory layout`.
- `git diff --stat main...HEAD` - 7 files changed, 1342 insertions, 31 deletions. The diff is limited to HX model/component source and HX tests.
- `pytest` - 2301 passed, 1 Windows `.pytest_cache` permission warning.
- `ruff check .` - passed.
- `black --check src tests` - passed; 113 files would be left unchanged.
- `pytest tests/hx_models tests/components` - 901 passed, 1 Windows `.pytest_cache` permission warning.

Architecture-boundary and hidden-default searches:

- `rg -n "CoolProp" src/mpl_sim/hx_models src/mpl_sim/components` - documentation/comment references only in audited HX files; no forbidden direct CoolProp import or call.
- `rg -n "PropertyBackend" src/mpl_sim/hx_models src/mpl_sim/components` - documentation/comment references only in audited HX files; no PropertyBackend construction or dependency.
- `rg -n "mpl_sim\.network" src/mpl_sim/hx_models src/mpl_sim/components` - no matches.
- `rg -n "mpl_sim\.solvers" src/mpl_sim/hx_models src/mpl_sim/components` - no matches.
- `rg -n "CorrelationRegistry" src/mpl_sim/hx_models` - registry-separation comments only; no internal registry resolution.
- `rg -n "4180|cp *=|D_h *= *1e-3|rho *= *1\.0|mu *= *1e-5|A_ht *= *1\.0|area *= *1\.0" src/mpl_sim/hx_models src/mpl_sim/components` - only component forwarding of `primary_cp`; no dangerous hidden physical defaults.
- `rg -n "primary_cp is None|htc_secondary is None" src/mpl_sim/hx_models src/mpl_sim/components` - explicit validation checks in `HXSolveRequest`; no inference/fallback behavior.
- `rg -n "\.get\(" src/mpl_sim/hx_models src/mpl_sim/components` - one existing DP input smooth-wall default: `roughness=gs.get("roughness", 0.0)`.

## Audit Checklist

### SinkInletTempAndFlow Support

Pass. `SinkInletTempAndFlow` is now supported by `EpsilonNTUModel._solve_sink_inlet`. The model computes lumped counterflow epsilon-NTU with `UA / C_min`, the standard counterflow effectiveness equations, and `Q = epsilon * C_min * (T_secondary_in - T_primary_in)`.

The sign convention is explicit in the model docstring, implementation comments, and tests. Heating and cooling directions are both covered: warm secondary over colder primary gives `Q > 0`; hotter primary over cooler secondary gives `Q < 0`. The outlet enthalpy update remains consistent with the sign convention: `h_out = h_in + Q / primary_mdot`.

### PrimaryThermalMode

Pass. `PrimaryThermalMode` is explicit and required for `SinkInletTempAndFlow`.

- `FINITE_CAPACITY` requires explicit finite positive `primary_cp`.
- `CONSTANT_TEMPERATURE` represents the phase-change/isothermal primary-side limit with `Cr = 0`.
- `CONSTANT_TEMPERATURE` forbids `primary_cp`, so phase change is not silently inferred from `primary_cp is None`.
- Missing or invalid `primary_T_in` and `primary_cp` errors are clear and tested.

### UAComputationMode

Pass. `UAComputationMode` is explicit and required for `SinkInletTempAndFlow`.

- `TWO_SIDED` requires both primary and secondary HTC correlations.
- `PRIMARY_ONLY` requires primary HTC and intentionally computes `UA = h_primary * A_ht`.
- There is no silent fallback from two-sided to primary-only.
- UA is computed from explicit `A_ht` and injected HTC correlation outputs.
- Missing, zero, or negative `A_ht` is rejected.
- HTC calibration is applied at the HTC/UA seam before UA, NTU, epsilon, and Q are computed.

### Hidden Physical Defaults

Pass, with one already-documented optional DP convention. The audited branch does not introduce hidden defaults for:

- `cp = 4180`
- water assumption
- heat-transfer area
- primary temperature
- primary cp
- hydraulic diameter
- density or viscosity
- mass flux
- quality
- phase-change inference from `primary_cp is None`
- primary-only fallback from `htc_secondary is None`

The only `.get()` in the audited paths is the existing DP input roughness default to `0.0`, documented as a smooth-wall assumption and tested in the foundation suite. It is not part of the sink-side energy balance or UA calculation.

### Correlation/Verdict Propagation

Pass. HTC and DP correlations are injected through `HXSolveRequest`; `EpsilonNTUModel` does not resolve `CorrelationRegistry`.

Primary and secondary HTC outputs are used consistently with the selected UA mode. `PRIMARY_ONLY` consumes only primary HTC. `TWO_SIDED` consumes both primary and secondary HTC and uses the series resistance formula. DP output is handled through the existing DP path; `friction_multiplier` affects `dP_primary` and `P_out`, not energy balance. HTC/UA calibration affects UA, NTU, epsilon, and Q on the sink-side path. Correlation verdicts are propagated into `HXSolveResult.verdicts`.

### Component Wrappers

Pass for explicit thermal/UA mode forwarding. `EvaporatorHXInput` and `CondenserHXInput` expose `primary_T_in`, `primary_cp`, `primary_thermal_mode`, and `ua_computation_mode`, and both component wrappers pass those fields into `HXSolveRequest`.

Condenser also exposes and forwards `htc_secondary`. Evaporator currently exposes only `htc_primary` and `dp_primary`, so direct two-sided UA through `EvaporatorComponent` is not available yet even though the model supports it. This is a minor wrapper-completeness follow-up, not an architecture violation in this Phase 11B model checkpoint.

Components avoid storing derived temperatures, cp, UA, HTC, DP, or profiles. Components avoid PropertyBackend construction and remain Network/Solver unaware. Ports are still value-free connectivity objects.

### Layer Boundaries

Pass. The branch did not modify Solver behavior, Network behavior, Pump/Accumulator/Pipe behavior, schema/results/validation primitives, or frozen architecture documents. The source/test diff is limited to:

- `src/mpl_sim/components/condenser.py`
- `src/mpl_sim/components/evaporator.py`
- `src/mpl_sim/hx_models/base.py`
- `src/mpl_sim/hx_models/epsilon_ntu.py`
- `tests/hx_models/test_epsilon_ntu_model.py`
- `tests/hx_models/test_epsilon_ntu_sink_side.py`
- `tests/hx_models/test_secondary_bc.py`

### Tests

Pass. Tests cover both happy paths and failure paths:

- Missing `primary_T_in`, `primary_thermal_mode`, `ua_computation_mode`, `primary_cp`, `htc_primary`, `htc_secondary`, and `A_ht` failures.
- Finite/positive validation for temperatures, cp, mdot, primary mdot, calibration multipliers, and area.
- No hidden fallback behavior for phase-change mode or UA mode.
- Sign convention and `h_out = h_in + Q / mdot` numerically.
- Constant-temperature and finite-capacity epsilon-NTU formulas.
- Two-sided and primary-only UA formulas.
- HTC and friction calibration placement.
- Verdict propagation.
- Import boundaries for HX models and components.

Remaining test hardening that would be useful later: component-level sink-side wrapper tests, especially for forwarding the new mode fields through real component inputs; and explicit rejection/handling tests for non-positive HTC outputs or non-positive HTC-input scalars such as `G` and `D_h`.

## Findings

### Critical Findings

None.

### Major Findings

None.

### Minor Findings

- `EvaporatorHXInput` does not expose `htc_secondary`, so `UAComputationMode.TWO_SIDED` cannot currently be exercised through `EvaporatorComponent` even though direct `EpsilonNTUModel` use supports it. `CondenserHXInput` already forwards `htc_secondary`. This is a wrapper-completeness gap, not a model or architecture blocker for the Phase 11B checkpoint.
- Sink-side model tests are strong, but component wrapper tests have not yet been extended to exercise sink-side `primary_T_in`, `primary_cp`, `PrimaryThermalMode`, and `UAComputationMode` forwarding.
- `_build_htc_input` validates `G`, `D_h`, and `x` as finite but does not enforce positivity/range there; positive validation is currently strongest on temperatures, cp, mdot, `A_ht`, `rho`, and `mu`. Future hardening should reject physically invalid HTC input scalars and non-positive HTC outputs before computing UA.

## Deferred Items

- `FixedWallTemp` evaluation.
- `AmbientCoupling` evaluation.
- Numeric LMTD model.
- Segmented-march model.
- Moving-boundary model beyond declared seam.
- Migrated boiling and condensation HTC closures.
- Migrated two-phase DP closures.
- Full component-level sink-side acceptance tests.
- Full loop residual integration with Evaporator and Condenser.
- Physical validation/literature harness activation.
- DOE/surrogate generation.
- Dynamics and control.
- Fitting/optimization.

## Phase Classification

This branch is a **Phase 11B checkpoint that should be merged before continuing Phase 11**.

It is not full Phase 11 completion. The branch completes the sink-side epsilon-NTU model slice with explicit modes and scalar inputs, while preserving the architecture boundaries. The remaining roadmap items still require additional Phase 11 continuation work.

## Merge Readiness

`phase-11b-hx-physics-continuation` is safe to merge as a Phase 11B checkpoint.

The branch has no failing tests, no lint/format failures, no critical or major audit findings, and no observed architecture violations. Continue Phase 11 with wrapper hardening, remaining HX strategy implementations, correlation migrations, and loop integration.
