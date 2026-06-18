# PROJECT_STATUS.md

Operational memory for the MPL simulation framework.
This document is not architecture. It does not redesign anything. It tracks where the project is and what to do next.

---

## 1. Current Status

| Field | Value |
|---|---|
| **Project name** | MPL Loop Simulation Library |
| **Repository** | `mpl-loop-sim` |
| **Branch** | `phase-11j-segmented-sink-coupling` |
| **Stage** | Phase 11J segmented sink coupling approved for merge as checkpoint; Phase 11 remains open |
| **Completed phase** | **Phase 10 - Pump and Accumulator** |
| **Phase 3 audit verdict** | **APPROVED FOR PHASE 4** |
| **Phase 4 audit verdict** | **APPROVED FOR PHASE 5** |
| **Phase 5A audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 6 final audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 7 final audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 8 checkpoint audit verdict** | **APPROVED FOR MERGE AS PHASE 8 CHECKPOINT - CONTINUE PHASE 8** |
| **Phase 8 final audit verdict** | **APPROVED FOR MERGE AND NEXT PHASE** |
| **Phase 8 status** | **Complete. Phase 8A, 8B, 8C, 8D, and 8E are complete.** |
| **Phase 9 final audit verdict** | **APPROVED FOR MERGE AND NEXT PHASE** |
| **Phase 9 status** | **Complete. Result primitives, schema primitives, canonical serialization, validation invariant primitives, and safe serialization adapters are complete.** |
| **Phase 10 final audit verdict** | **APPROVED FOR MERGE AND NEXT PHASE** |
| **Phase 10 status** | **Complete. Pump map/command behavior, pump power/efficiency seam, shaft-speed/inertia named seam, accumulator `VolumePressureLaw` integration, PCA closure, `V_g` state seam, network pressure-reference wiring, and pump-driven accumulator-referenced loop acceptance shape are implemented at planned V1 fidelity.** |
| **Phase 11 foundation audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11 foundation status** | **Checkpoint complete. HeatExchangerModel contract/registry, secondary BC value objects, V1 `EpsilonNTUModel` fixed-heat-rate path, and Evaporator/Condenser component wrappers are implemented and tested. Full Phase 11 physics remains in progress.** |
| **Phase 11B audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11B status** | **Checkpoint complete. `EpsilonNTUModel` now supports `SinkInletTempAndFlow` with explicit `primary_T_in`, explicit `PrimaryThermalMode`, explicit `UAComputationMode`, explicit finite-capacity `primary_cp`, injected HTC/DP correlations, and tested heating/cooling sign convention.** |
| **Phase 11C audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11C status** | **Checkpoint complete. `EvaporatorHXInput` exposes and forwards `htc_secondary`; Evaporator/Condenser wrapper tests verify sink-side HX field forwarding; `EpsilonNTUModel` rejects invalid geometry/correlation scalars and invalid HTC/DP outputs without silent fallback.** |
| **Phase 11D audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11D status** | **Checkpoint complete. `EpsilonNTUModel` now supports `FixedWallTemp` and `AmbientCoupling` with explicit primary inlet temperature, explicit wall/ambient inputs, correct heating/cooling sign convention, tested enthalpy balance, and preserved correlation/calibration boundaries.** |
| **Phase 11E audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11E status** | **Checkpoint complete. `LMTDModel` is implemented as a limited foundation supporting `FixedWallTemp` and `AmbientCoupling`; `SinkInletTempAndFlow` and `FixedHeatRate` remain explicitly unsupported in `LMTDModel`.** |
| **Phase 11F audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11F status** | **Checkpoint complete. `SegmentedMarchModel` is implemented as a limited foundation supporting only `FixedHeatRate`; segment-wise secondary coupling and local HTC/UA solving remain deferred.** |
| **Phase 11G audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11G status** | **Checkpoint complete. Cross-model family contract tests added (`test_hx_model_family_contracts.py`); import-boundary coverage extended to `lmtd.py` and `segmented.py`; no new physics added.** |
| **Phase 11H audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11H status** | **Checkpoint complete. `SegmentedMarchModel` now supports both `FixedHeatRate` and finite-capacity segmented `FixedWallTemp`, with explicit primary temperature/cp marching, per-cell injected HTC, optional per-cell injected DP, and diagnostic-only cell temperatures.** |
| **Phase 11I audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11I status** | **Checkpoint complete. `SegmentedMarchModel` now also supports finite-capacity segmented `AmbientCoupling` using prescribed `UA_ambient / n_cells`, explicit primary temperature/cp marching, no primary HTC call, optional per-cell injected DP, and diagnostic-only cell temperatures.** |
| **Phase 11J audit verdict** | **APPROVED FOR MERGE AS CHECKPOINT - CONTINUE PHASE** |
| **Phase 11J status** | **Checkpoint complete. `SegmentedMarchModel` now also supports finite-capacity co-current segmented `SinkInletTempAndFlow` with explicit primary/secondary capacities, two-sided per-cell HTC/UA, local epsilon-NTU marching, optional per-cell injected DP, and diagnostic-only primary/secondary temperatures.** |
| **Phase 11 final closeout verdict** | **APPROVED AS CHECKPOINT ONLY - PHASE 11 REMAINS OPEN** |
| **Phase 11 status** | **V1 HX model foundation now includes all four secondary BC classes in limited segmented form, but roadmap-defined correlation migrations, counterflow/phase-change segmented coupling, moving boundary, and full-loop convergence acceptance remain incomplete.** |
| **Branch status** | **Implemented and audited on `phase-11j-segmented-sink-coupling`; safe to merge into `main` as a Phase 11J checkpoint.** |
| **Current active phase** | **Phase 11 - HeatExchangerModel, Evaporator and Condenser continuation** |
| **Next immediate slice** | Continue Phase 11 with required boiling/condensation HTC and two-phase-DP migrations, counterflow or justified phase-change coupling as needed, Scenario-bound HX behavior, and full-loop convergence acceptance according to `IMPLEMENTATION_PLAN.md` |
| **Working tree before this docs task** | Phase 11J implementation present on `phase-11j-segmented-sink-coupling` in the expected six source/test files |
| **Test status** | 2770 passed, verified 2026-06-18 with `pytest`; targeted `pytest tests/hx_models tests/components` passed 1370 tests |
| **Lint status** | `ruff check src tests` clean, verified 2026-06-18. |
| **Format status** | `black --check --no-cache --verbose src tests` passed, with 124 files unchanged |

Phase 11J segmented sink coupling is approved and safe to merge as a checkpoint.
The Phase 11 final closeout assessment is checkpoint-only: Phase 11 remains open.

- `SegmentedMarchModel` now supports all four secondary BC classes in limited form: `FixedHeatRate`, finite-capacity segmented `FixedWallTemp`, finite-capacity segmented `AmbientCoupling`, and finite-capacity co-current segmented `SinkInletTempAndFlow`.
- The segmented sink path is explicitly co-current/parallel flow; both stream inlets enter cell 0. Counterflow is not claimed and remains deferred.
- The sink path requires explicit `primary_T_in`, finite positive `primary_cp`, `PrimaryThermalMode.FINITE_CAPACITY`, finite positive secondary inlet temperature/mass flow/cp, finite positive `A_ht`, both injected HTC correlations, and `UAComputationMode.TWO_SIDED`.
- Each sink cell evaluates primary HTC then secondary HTC, assembles two-sided `UA_cell`, applies co-current epsilon-NTU, and marches primary enthalpy plus diagnostic primary/secondary temperatures.
- `UAComputationMode.PRIMARY_ONLY` and `PrimaryThermalMode.CONSTANT_TEMPERATURE` are rejected clearly; no single-sided fallback or phase-change behavior is inferred.
- `SegmentedCellRecord` / `SegmentedProfile` remain immutable diagnostics. Cell primary and secondary temperatures are not stored in `FluidState`, on Ports, or in `SystemState`.
- `friction_multiplier` affects DP and pressure only; `raw_dP_primary` remains pre-calibration.
- Counterflow segmented sink coupling, phase-change segmented coupling, boiling/condensation HTC and two-phase-DP closure migrations, moving boundary, and full-loop integration remain deferred.
- Required validation passed on 2026-06-18: 2770 full tests, 1370 targeted HX/component tests, Ruff clean, and Black clean across 124 files.

Phase 11G HX model consolidation remains complete.

- New focused test file `tests/hx_models/test_hx_model_family_contracts.py` added (54 tests).
- Cross-model contracts verified: all three implemented models (`EpsilonNTUModel`, `LMTDModel`, `SegmentedMarchModel`) subclass `HeatExchangerModel`, return their correct and distinct `HeatExchangerModelKind`, and are registerable/resolvable through `HeatExchangerModelRegistry`.
- `HeatExchangerModelKind` confirmed to have exactly four declared seams: `EPSILON_NTU`, `LMTD`, `SEGMENTED_MARCH`, `MOVING_BOUNDARY`.
- No `MovingBoundaryModel` class is implemented or exported; `MOVING_BOUNDARY` remains a declared seam only.
- Unsupported BCs in `LMTDModel` (`FixedHeatRate`, `SinkInletTempAndFlow`) and `SegmentedMarchModel` (`SinkInletTempAndFlow`, `FixedWallTemp`, `AmbientCoupling`) confirmed to raise `UnsupportedHeatExchangerBoundaryConditionError`.
- `EpsilonNTUModel` `FixedHeatRate` path confirmed still supported.
- Import-boundary coverage extended to `lmtd.py` and `segmented.py` (previously `test_hx_model_architecture_boundaries.py` covered only `base.py`, `epsilon_ntu.py`, `registry.py`).
- All exports (`EpsilonNTUModel`, `LMTDModel`, `SegmentedMarchModel`, `SegmentedCellRecord`, `SegmentedProfile`) verified in `mpl_sim.hx_models.__all__`.
- No new physics was added. No `MovingBoundaryModel` was implemented. No architecture documents were modified.
- Final Phase 11 closeout is not yet supported by `IMPLEMENTATION_PLAN.md`: required HTC/DP closure migrations, meaningful segmented per-cell HTC/secondary coupling, and the converged full-loop acceptance case remain incomplete.

Phase 11F segmented HX model foundation checkpoint is complete and safe to merge as a checkpoint.

- New `SegmentedMarchModel` is implemented under `src/mpl_sim/hx_models/segmented.py`.
- `SegmentedMarchModel.kind()` returns `HeatExchangerModelKind.SEGMENTED_MARCH`.
- `SegmentedMarchModel` is exported from `mpl_sim.hx_models` and can be registered/resolved through `HeatExchangerModelRegistry`.
- `SegmentedCellRecord` and `SegmentedProfile` are immutable diagnostic value objects exported from `mpl_sim.hx_models`.
- Supported in this checkpoint: `FixedHeatRate`.
- Explicitly unsupported in this checkpoint: `SinkInletTempAndFlow`, `FixedWallTemp`, and `AmbientCoupling`.
- `FixedHeatRate` is split evenly over explicit `UNIFORM` `n_cells`, with per-cell `h_out = h_in + Q_cell / primary_mdot`.
- Optional primary DP is handled cell-wise through injected `dp_primary`; `raw_dP_primary` is the pre-calibration sum of raw cell DP outputs.
- `friction_multiplier` affects DP and pressure only, not heat rate or enthalpy.
- `HXSolveResult.zone_profile` carries the diagnostic `SegmentedProfile`; it is not stored in `SystemState` or attached to Ports.
- `SegmentedMarchModel` does not import CoolProp, construct or call `PropertyBackend`, import Network/Solver, or resolve `CorrelationRegistry`.
- Phase 11 remains incomplete; segment-wise secondary coupling, local HTC/UA solving, moving-boundary modeling, migrated boiling/condensation HTC and two-phase DP closures, loop residual integration, validation harnesses, DOE, dynamics, controls, fitting, and optimization remain deferred.

Phase 11E LMTD HX model foundation checkpoint remains complete and safe to merge as a checkpoint.

- New `LMTDModel` is implemented under `src/mpl_sim/hx_models/lmtd.py`.
- `LMTDModel.kind()` returns `HeatExchangerModelKind.LMTD`.
- `LMTDModel` is exported from `mpl_sim.hx_models` and can be registered/resolved through `HeatExchangerModelRegistry`.
- `LMTDModel` is a `HeatExchangerModel`, not a `Correlation`, and LMTD remains absent from `CorrelationRole`.
- Supported in this checkpoint: `FixedWallTemp` and `AmbientCoupling`.
- Explicitly unsupported in this checkpoint: `SinkInletTempAndFlow` and `FixedHeatRate`.
- `FixedWallTemp` requires explicit `primary_T_in`, explicit finite positive `A_ht`, and injected `htc_primary`.
- `FixedWallTemp` computes `Q = htc_multiplier * h_primary * A_ht * (T_wall - primary_T_in)`.
- `AmbientCoupling` computes `Q = UA_ambient * (T_ambient - primary_T_in)` without requiring `A_ht` or `htc_primary`.
- `htc_multiplier` deliberately does not affect `UA_ambient`; this boundary is tested.
- DP remains injected through `dp_primary`; `friction_multiplier` affects DP only.
- `LMTDModel` does not import CoolProp, construct or call `PropertyBackend`, import Network/Solver, or resolve `CorrelationRegistry`.
- Phase 11 remains incomplete; full two-stream LMTD solving, primary outlet-temperature iteration, LMTD correction factors, segmented march, moving boundary, migrated boiling/condensation HTC and two-phase DP closures, loop residual integration, validation harnesses, DOE, dynamics, controls, fitting, and optimization remain deferred.

Phase 11D HX boundary-condition expansion checkpoint remains complete and safe to merge as a checkpoint.

- `EpsilonNTUModel` now supports all declared `SecondaryFluidBC` variants: `FixedHeatRate`, `SinkInletTempAndFlow`, `FixedWallTemp`, and `AmbientCoupling`.
- `FixedWallTemp` requires explicit `primary_T_in`, explicit finite positive `A_ht`, and injected `htc_primary`.
- `FixedWallTemp` computes `Q = htc_multiplier * h_primary * A_ht * (T_wall - primary_T_in)`, with `Q > 0` heating the primary side and `Q < 0` cooling it.
- `FixedWallTemp` rejects invalid HTC outputs before computing UA, propagates HTC/DP verdicts, and keeps `friction_multiplier` limited to DP.
- `AmbientCoupling` requires explicit `primary_T_in` and uses `UA_ambient` and `T_ambient` directly for `Q = UA_ambient * (T_ambient - primary_T_in)`.
- `AmbientCoupling` does not require `A_ht` or `htc_primary` for energy calculation.
- `AmbientCoupling` deliberately does not apply `htc_multiplier` to `UA_ambient`; this calibration boundary is tested.
- Both new paths test heating/cooling sign convention and `h_out = h_in + Q / primary_mdot`.
- `UnsupportedHeatExchangerBoundaryConditionError` remains only as a future-proof guard for unrecognized BC objects.
- No hidden defaults were added for water cp, heat-transfer area, hydraulic diameter, density, viscosity, primary temperature, wall temperature, ambient temperature, ambient UA, HTC, or DP.
- HX models and wrappers still do not import CoolProp, construct PropertyBackend, import Network/Solver, or resolve `CorrelationRegistry`.
- Phase 11 remains incomplete; LMTD, segmented march, moving boundary, migrated HTC/DP closures, loop residual integration, validation harnesses, DOE, dynamics, controls, fitting, and optimization remain deferred.

Phase 11C HX wrapper and input-hardening checkpoint remains complete and safe to merge as a checkpoint.

- `EvaporatorHXInput` now exposes `htc_secondary`.
- `EvaporatorComponent` forwards `htc_secondary` into `HXSolveRequest`, so `UAComputationMode.TWO_SIDED` can be exercised through the wrapper when both HTC correlations are supplied.
- Evaporator and Condenser component tests verify forwarding of `primary_T_in`, `primary_cp`, `primary_thermal_mode`, `ua_computation_mode`, `htc_primary`, `htc_secondary`, `dp_primary`, `htc_multiplier`, and `friction_multiplier` using recording/dummy HX models.
- `EpsilonNTUModel` rejects missing, non-finite, non-positive, or out-of-range required scalars where used: `G`, `D_h`, `L_cell`, `rho`, `mu`, `A_ht`, and vapor quality `x`.
- HTC outputs used for UA must be finite and strictly positive in `PRIMARY_ONLY` and `TWO_SIDED`; invalid outputs raise before UA is computed.
- DP outputs must be finite. Signed DP remains intentional: negative DP is allowed as pressure recovery, with no `abs` or clipping.
- Friction calibration still affects DP only and does not affect `Q` or enthalpy balance.
- No hidden defaults were added for heat-transfer area, hydraulic diameter, density, viscosity, mass flux, quality, water/cp, phase-change inference, or single-sided UA fallback. The explicit `roughness = 0.0` smooth-wall convention remains the only accepted default.
- HX models and wrappers still do not import CoolProp, construct PropertyBackend, import Network/Solver, or resolve `CorrelationRegistry`.
- `docs/presentations` lint/noise is unrelated to Phase 11C and should be handled later in a separate `chore/remove-presentation-artifacts` or docs cleanup branch.

Phase 11B sink-side epsilon-NTU checkpoint remains complete and safe to merge as a checkpoint.

- `SinkInletTempAndFlow` is now implemented in `EpsilonNTUModel` as a lumped counterflow epsilon-NTU heat balance.
- `PrimaryThermalMode` is explicit: `FINITE_CAPACITY` requires explicit positive `primary_cp`; `CONSTANT_TEMPERATURE` forbids `primary_cp` and represents the isothermal/phase-change limit without inference from `None`.
- `UAComputationMode` is explicit: `PRIMARY_ONLY` requires primary HTC; `TWO_SIDED` requires primary and secondary HTC and uses the series resistance formula.
- `primary_T_in`, sink-side `T_in`, sink `mdot_secondary`, sink `cp_secondary`, `primary_mdot`, and `A_ht` are explicit and validated.
- The sign convention is explicit and tested: `Q > 0` heats the primary side, `Q < 0` cools it, and `h_out = h_in + Q / primary_mdot`.
- HTC/UA calibration affects UA, NTU, epsilon, and Q; friction calibration affects `dP_primary` and not energy balance.
- Correlation verdicts from HTC and DP calls are propagated into `HXSolveResult`.
- HX models still do not import CoolProp, construct PropertyBackend, resolve `CorrelationRegistry`, import Network/Solver, or store derived properties.
- Components forward the new primary thermal and UA mode fields into `HXSolveRequest`; Phase 11C completed Evaporator secondary-HTC forwarding.

Phase 11 foundation checkpoint remains complete and safe to merge as a checkpoint.

- `HeatExchangerModelKind`, `HXSolveRequest`, `HXSolveResult`, secondary-fluid BC value objects, and `HeatExchangerModel` contract under `src/mpl_sim/hx_models/base.py`.
- Separate `HeatExchangerModelRegistry` under `src/mpl_sim/hx_models/registry.py`.
- V1 `EpsilonNTUModel` under `src/mpl_sim/hx_models/epsilon_ntu.py`, supporting `FixedHeatRate` only and explicitly rejecting unsupported BCs.
- Required HX model physical scalars are explicit and finite; no hidden `D_h`, `rho`, `mu`, `L_cell`, `G`, or `x` defaults remain.
- Optional missing `roughness` is documented and tested as a smooth-wall assumption.
- `EvaporatorComponent` and `CondenserComponent` wrappers under `src/mpl_sim/components/`, with value-free inlet/outlet ports and local delegation to injected HX models.
- HX model slots are separate from HTC/DP correlation slots.
- Components and HX models avoid Network, Solver, PropertyBackend construction, and direct CoolProp calls.
- Tests cover HX contract, registry separation, unsupported BCs, missing physical scalars, optional roughness, component boundaries, and architecture-boundary searches.

This checkpoint changed Phase 11 source/tests and documentation only. It did not modify Pump, Accumulator, Network pressure-reference wiring, Solver behavior, schemas/results/validation primitives, property backends, calibration primitives, or frozen architecture documents.

Phase 10 remains complete and already safe to merge.

- Pump component foundation under `src/mpl_sim/components/pump.py`.
- Pump prescribed pressure-rise seam: `delta_p = delta_p_setpoint * pressure_rise_multiplier`.
- Pump performance-map behavior through `PumpPerformanceMap` and `evaluate_pump_map`.
- Pump command scope through `PumpSpeedCommand`, `PumpFlowTarget`, and target binding checks.
- Pump power/efficiency seam through explicit scalar `PumpPowerInput`.
- Pump geometry and named-frozen shaft-speed/inertia seam with `internal_state_names()` including `omega`.
- Pump hydraulic summary with raw and scaled pressure-rise reporting.
- Accumulator component foundation under `src/mpl_sim/components/accumulator.py`.
- Accumulator prescribed pressure-reference seam: `p_ref = p_setpoint`.
- Accumulator `VolumePressureLawBinding`, `evaluate_volume_pressure_law`, and `V_g` internal-state seam.
- Accumulator pressure summary with setpoint echo.
- `VOLUME_PRESSURE_LAW` correlation role and PCA volume-pressure law closure.
- HCA remains a declared seam; no numeric HCA closure was required for Phase 10 closeout because the implementation plan conditions it on feasible legacy support.
- Network-owned pressure-reference wiring through `PressureReferenceWiring`.
- Minimal pump-driven, accumulator-referenced loop acceptance shape covered by tests.
- Pump and Accumulator exports from `src/mpl_sim/components/__init__.py`.

Pump and Accumulator remain local, immutable, physics-light components. They do not call CoolProp, `PropertyBackend`, Network, Solver, physical residual assembly, dynamic simulation, fitting, or optimization. Pump does not import correlations. Accumulator imports only the correlation contract and delegates law evaluation to caller-supplied correlations. Ports remain value-free, and `SystemState` remains the owner of numerical state values.

This Phase 10 audit closeout changed documentation only. No source code and no test files were modified during audit closeout.

The following remain deferred unless explicitly planned in Phase 11 or later:

- explicit pressure-reference port-name validation hardening;
- full physical residual assembly;
- pressure/flow solving for physically converged pump/accumulator loops;
- pump shaft-speed dynamics and control laws;
- accumulator dynamic inventory integration and `dP/dt`;
- HCA numeric closure if future legacy/data support justifies it;
- NPSH checks;
- optimization and fitting;
- dynamic simulation and controls;
- full sink-side Evaporator/Condenser heat-exchanger physics, phase change, migrated HTC/DP closures, and two-phase pressure drop until Phase 11 continuation work completes.

---

## 2. Authoritative Documents

All binding architecture and roadmap documents remain frozen unless a future task explicitly authorizes changes through the decision process.

| Document | Purpose | Authority level |
|---|---|---|
| `docs/architecture/ARCHITECTURE_MASTER.md` | Single source of architectural truth; frozen decisions [F1]-[F18] | Highest |
| `docs/architecture/INTERFACE_SPEC.md` | Frozen contracts and signatures for every DAG layer | Binding |
| `docs/architecture/CORRELATION_CONTRACT.md` | Closure contract, per-role input manifests, validity-envelope format | Binding |
| `docs/architecture/SCHEMA_SPEC.md` | Serialization schemas for tuple, Result, dataset, validation case | Binding |
| `docs/validation/TEST_PLAN_V1.md` | Test levels, acceptance gates, anti-pattern compliance tests | Binding |
| `docs/roadmap/IMPLEMENTATION_PLAN.md` | Authoritative phase order for all coding work | Binding |
| `docs/architecture/ARCHITECTURE_FINAL_AUDIT.md` | Pre-implementation coherence audit | Reference |
| `docs/decisions/DECISION_LOG.md` | Frozen governance record | Binding |

Key authority statements:

- `ARCHITECTURE_MASTER.md` remains the single source of architectural truth.
- `IMPLEMENTATION_PLAN.md` is the authority for phase order and build sequence.
- `TEST_PLAN_V1.md` defines acceptance gates.
- `DECISION_LOG.md` is required for any future frozen-contract change.

---

## 3. Completed Milestones

| Milestone | Status |
|---|---|
| Architecture master, interface spec, schema spec, correlation contract, test plan, implementation roadmap, final architecture audit | Complete |
| GitHub repository initialized | Complete |
| **Phase 0 - Repository Preparation and Tooling** | **Complete** |
| **Phase 1A - FluidIdentity and FluidState** | **Complete** |
| **Phase 1B - Port primitives** | **Complete** |
| **Phase 1C - SystemState and StateLayout** | **Complete** |
| **Phase 1 audit** | **Complete; approved for Phase 2** |
| **Phase 2A - PropertyBackend interface contract** | **Complete** |
| **Phase 2B - CoolPropBackend** | **Complete** |
| **Phase 2C - PropertyBackend registry and backend selection binding** | **Complete** |
| **Phase 2 property layer foundation** | **Complete** |
| **Phase 3A - Correlation contract primitives** | **Complete** |
| **Phase 3B - Correlation registry** | **Complete** |
| **Phase 3C - Churchill single-phase friction-gradient closure** | **Complete** |
| **Phase 3 correlation layer foundation** | **Complete; approved for Phase 4** |
| **Phase 4A - Immutable geometry primitives** | **Complete** |
| **Phase 4B - Discretization primitives** | **Complete** |
| **Phase 4 geometry and discretization foundation** | **Complete; approved for Phase 5** |
| **Phase 5A - Calibration primitives and registry** | **Complete** |
| **Phase 5A calibration audit** | **Complete; approved for Phase 6** |
| **Phase 6A - Component contract and Pipe skeleton** | **Complete** |
| **Phase 6B - Pipe single-phase friction-only kernel** | **Complete** |
| **Phase 6C - Pipe gravity pressure contribution** | **Complete** |
| **Phase 6D - Pipe acceleration pressure contribution** | **Complete** |
| **Phase 6E - Pipe mechanical pressure summary scaffold** | **Complete** |
| **Phase 6F - Pipe friction-only calibration placement proof** | **Complete** |
| **Phase 6 final audit** | **Complete; approved for Phase 7** |
| **Phase 7A - Network identity and topology primitives** | **Complete** |
| **Phase 7B - Connection validation and graph checks** | **Complete** |
| **Phase 7C - Network SystemState assembly** | **Complete** |
| **Phase 7 final audit** | **Complete; approved for Phase 8** |
| **Phase 8A - Solver contract primitives** | **Complete** |
| **Phase 8B - Residual evaluation interface** | **Complete** |
| **Phase 8C - Minimal convergence-gate steady solver** | **Complete** |
| **Phase 8D - Assembled steady problem wrapper, convergence metadata, and update interface** | **Complete** |
| **Phase 8E - Fixed-point steady solver loop** | **Complete** |
| **Phase 8 final audit** | **Complete; approved for merge and next phase** |
| **Phase 9 - Result and schema serialization** | **Complete** |
| **Phase 9 final audit** | **Complete; approved for merge and next phase** |
| **Phase 10 Pump and Accumulator foundation checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 10** |
| **Phase 10 Pump and Accumulator final closeout** | **Complete; approved for merge and next phase** |
| **Phase 11 HeatExchangerModel, Evaporator and Condenser foundation checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11B Sink-side epsilon-NTU checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11C HX wrapper and input hardening checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11D HX boundary-condition expansion checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11E LMTD HX model foundation checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11F segmented HX model foundation checkpoint** | **Complete; approved for merge as checkpoint, continue Phase 11** |
| **Phase 11G HX model consolidation checkpoint** | **Complete; safe to merge as Phase 11G checkpoint** |
| **Phase 11 final closeout assessment** | **Checkpoint only; Phase 11 remains open** |

Closeout artifacts:

- `docs/validation/audits/PHASE_2_CLOSEOUT_SUMMARY.md`
- `docs/validation/audits/PHASE_2_COMPLETE_AUDIT.md`
- `docs/validation/audits/PHASE_2_PROPERTY_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_4_GEOMETRY_DISCRETIZATION_AUDIT.md`
- `docs/validation/audits/PHASE_5A_CALIBRATION_PRIMITIVES_AUDIT.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_CHECKPOINT_AUDIT.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_7_NETWORK_ASSEMBLY_AUDIT.md`
- `docs/validation/audits/PHASE_8_STEADY_SOLVER_AUDIT.md`
- `docs/validation/audits/PHASE_8_STEADY_SOLVER_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_9_SCHEMA_RESULTS_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_10_PUMP_ACCUMULATOR_FINAL_AUDIT.md`
- `docs/validation/audits/PHASE_10_PUMP_ACCUMULATOR_FINAL_CLOSEOUT_AUDIT.md`
- `docs/validation/audits/PHASE_11_HEAT_EXCHANGER_MODEL_FOUNDATION_AUDIT.md`
- `docs/validation/audits/PHASE_11B_SINK_SIDE_EPSILON_NTU_AUDIT.md`
- `docs/validation/audits/PHASE_11C_HX_WRAPPER_INPUT_HARDENING_AUDIT.md`
- `docs/validation/audits/PHASE_11D_HX_BOUNDARY_CONDITION_EXPANSION_AUDIT.md`
- `docs/validation/audits/PHASE_11E_LMTD_HX_MODEL_FOUNDATION_AUDIT.md`
- `docs/validation/audits/PHASE_11F_SEGMENTED_HX_MODEL_FOUNDATION_AUDIT.md`

---

## 4. Current Active Phase

The current active phase after merging the `phase-11f-segmented-hx-model-foundation` checkpoint is:

**Phase 11 - HeatExchangerModel, Evaporator and Condenser continuation**, according to `IMPLEMENTATION_PLAN.md`.

The completed Phase 10 work should be carried forward as the pressure-reference and pump-drive foundation:

- pump map and command behavior;
- pump power/efficiency seam;
- shaft-speed/inertia named-frozen seam;
- accumulator `VolumePressureLaw` slot integration;
- PCA pressure law and HCA seam decision;
- stored `V_g` / pressure-derived behavior at planned V1 fidelity;
- reference-node wiring owned by Network;
- pump-driven, accumulator-referenced loop acceptance shape.

Phase 11 should continue from the completed Phase 11F checkpoint. The contract/registry, fixed-heat-rate V1 path, component wrappers, sink-side epsilon-NTU model path, wrapper sink-side forwarding, input/output hardening, fixed-wall-temperature path, ambient-coupling path, limited LMTD foundation for fixed-wall/ambient conditions, and limited segmented-march foundation for `FixedHeatRate` are present; the remaining Phase 11 work is physical HX continuation and integration, not a new architecture pass. Dynamic simulation, controls, fitting, optimization, DOE generation, literature validation, and unplanned solver behavior changes remain deferred unless a future task explicitly changes scope.

Phase boundaries to preserve:

- Do not turn Network into a solver.
- Do not make Pipe, Pump, or Accumulator network-aware or solver-aware.
- Keep Pump and Accumulator local and preserve their completed Phase 10 seams.
- Continue Evaporator, Condenser, `HeatExchangerModel`, and heat-exchanger component work only inside the Phase 11 plan.
- Do not implement dynamic controls, fitting, optimization, or unplanned solver behavior in Phase 11.
- Do not move pressure, enthalpy, mass flow, derived properties, or solver vectors onto component or Port objects.
- Keep `SystemState` as the only owner of numerical values.

---

## 5. Next Immediate Actions

1. Merge `phase-11g-hx-model-consolidation` into `main` as a Phase 11G checkpoint.
2. Continue **Phase 11 - HeatExchangerModel, Evaporator and Condenser** after merge.
3. Migrate the roadmap-required boiling/condensation HTC and two-phase-DP closures.
4. Complete meaningful segmented local HTC/secondary coupling and the full-loop convergence acceptance case.
5. Repeat the Phase 11 final closeout audit before starting Phase 12.
6. Preserve frozen architecture boundaries while completing the remaining work.
7. Preserve the Phase 8 boundary: solver core remains generic and physics-free.
8. Preserve the Phase 7 boundary: Network owns topology and assembly/reference wiring only.
9. Preserve the Pipe Phase 6 boundary: local helper mechanics only, no network or solver awareness.
10. Keep dynamic controls, fitting, optimization, DOE generation, and literature validation deferred unless explicitly requested.
11. Run `pytest`, scoped lint appropriate to the branch, and `black --check src tests` before reporting the next implementation task complete. For Phase 11F specifically, `ruff check src tests` was used because the required audit scope was source and tests.

Recommended commit message:

```text
test: consolidate HX model family contracts
```

---

## 6. Non-Negotiable Implementation Rules

These rules are operational forms of the frozen decisions. Violating any is a review failure.

| Rule | Source |
|---|---|
| Do not modify frozen architecture docs during coding | `IMPLEMENTATION_PLAN.md` |
| Do not introduce new architecture concepts | `ARCHITECTURE_MASTER.md` |
| Do not copy legacy code directly into `src/` | `IMPLEMENTATION_PLAN.md` |
| Do not call CoolProp outside `properties/` | [F6] |
| Do not store derived properties anywhere | [F3] |
| Do not put values on Port | [F10] |
| Do not make Solver depend on physics | [F1] |
| Do not put mesh/segment count in Geometry | [F16] |
| Do not put accumulator law parameters in AccumulatorGeometry | [F9] |
| Do not weaken a test to make code pass | `IMPLEMENTATION_PLAN.md` |
| Calibration must not be inside a correlation | [F5] |
| A correlation must not receive a Component or Geometry object | [F4] |
| Network must never know the Solver | [F1] |
| Components must never know their Network or neighbours | [F7] |

---

## 7. Current Known Blockers and Deferred Work

None block merging the Phase 11F segmented HX model foundation checkpoint.

| Item | What it affects | Resolution path |
|---|---|---|
| Explicit pressure-reference port-name validation not separately enforced | Minor network validation hardening | Add a focused validation test/check if pressure-reference port identity becomes semantically important |
| Import-direction rules are not enforced by import-linter tooling | Future cross-layer expansion | Add import-linter or equivalent if boundary risks grow |
| Full physical minimal `Result` artifact not yet implemented | Future schema/result integration | Add when later loop artifacts can produce physical run results |
| Physical invariant calculations not yet implemented | Future validation/residual integration | Keep primitives data-only until physical balances are explicitly planned |
| Full `ReproducibilityTuple` serialization not yet implemented | Future schema/result integration | Build on Phase 9 canonical primitives when physical tuple inputs are ready |
| Component serialization not yet implemented | Future schema integration | Add only safe serializers; avoid component-internal coupling |
| Physical residual assembly not yet implemented | Future solver integration | Add only when explicitly planned, keeping adapters separate from solver core |
| Newton and finite-difference Jacobian not yet implemented | Future solver strategy work | Introduce only when explicitly planned |
| Pressure solving and flow solving not yet implemented | Future loop solving work | Implement through generic residual/update contracts, not by coupling solver to components |
| Full two-stream LMTD and full segmented-march strategies not implemented | Phase 11 continuation | Build on the Phase 11E `LMTDModel` foundation and Phase 11F `SegmentedMarchModel` foundation; implement as `HeatExchangerModel` strategies, not correlations |
| Presentation artifact lint/noise remains on this branch lineage | Docs cleanup | Handle `docs/presentations` separately in `chore/remove-presentation-artifacts` or a docs cleanup branch |
| Boiling/condensation HTC and two-phase DP closure migrations not implemented | Phase 11 continuation | Port under the correlation contract with envelopes and no globals/hacks |
| Full loop residual integration with Evaporator and Condenser not implemented | Phase 11 continuation | Integrate through component/local residual adapters while keeping Solver physics-free |
| Heat transfer, phase change, and two-phase pressure drop incomplete | Phase 11+ | Continue in planned Phase 11 slices; do not fake Phase 12 validation |
| 29 property CSV files missing | Future `TabulatedPropertyBackend`; `sigma_e`/`eps_r` | Data recovery task; does not block CoolProp-backed V1 path |
| Literature validation data must be lifted and pinned | Literature tests | Phase 12 validation-data task |
| Full artifact metadata for content-hash canonicalization rule | Future tuple/result artifacts | Phase 9 implements sorted-key compact JSON + SHA-256; record the rule in full artifact metadata when those artifacts are added |

---

## 8. Instructions for Future AI Agents

Before any coding task, read in order:

1. `docs/roadmap/PROJECT_STATUS.md`
2. `docs/roadmap/IMPLEMENTATION_PLAN.md`
3. `docs/validation/TEST_PLAN_V1.md`
4. Relevant sections of `docs/architecture/INTERFACE_SPEC.md`
5. Relevant audit/closeout documents in `docs/validation/audits/`

Rules for the next implementation session:

- The Phase 11F segmented HX model foundation checkpoint is safe to merge.
- The branch `phase-11f-segmented-hx-model-foundation` is safe to merge into `main` as a checkpoint.
- Phase 10 is complete.
- Phase 11 is not complete; continue Phase 11 heat-exchanger work according to `IMPLEMENTATION_PLAN.md`.
- `FixedHeatRate`, `SinkInletTempAndFlow`, `FixedWallTemp`, and `AmbientCoupling` are implemented in `EpsilonNTUModel`; Phase 11C completed wrapper sink-side forwarding and input/output hardening; Phase 11D completed fixed-wall and ambient boundary-condition support; Phase 11E added limited `LMTDModel` support for `FixedWallTemp` and `AmbientCoupling` while keeping `SinkInletTempAndFlow` and `FixedHeatRate` explicitly unsupported in `LMTDModel`; Phase 11F added limited `SegmentedMarchModel` support for `FixedHeatRate` while keeping segment-wise secondary coupling and local HTC/UA solving deferred. Continue with full HX strategies, correlation migrations, and loop integration.
- Do not reopen Phase 9 unless a new task explicitly requests a Phase 9 fix.
- Keep schema/results/validation serialization data-only and physics-free.
- Keep solver core generic and physics-free.
- Keep physical residual adapters separate from solver core.
- Keep Network topology/assembly/reference wiring separate from solver behavior.
- Keep Pipe local; do not add network or solver behavior to Pipe.
- Keep Pump and Accumulator local; do not add network or solver behavior to either component.
- Preserve separation among geometry, discretization, correlations, calibration, components, network, solvers, schema, and results.
- Continue Pump and Accumulator only for focused fixes or hardening; continue Phase 11 from the Phase 11F HX checkpoint. Keep dynamic controls, fitting, optimization, DOE, literature validation, Newton/Jacobian expansion, and transient solving deferred unless explicitly requested.
- Run `pytest`, appropriate scoped lint, and `black --check src tests` before reporting any implementation task complete. Keep scoped audit commands tied to the requested branch surface.
- Do not include `Co-Authored-By` lines unless explicitly requested.

---

## 9. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-17 |
| **Updated by** | Codex |
| **Status note** | Phase 11G approved for merge as checkpoint; Phase 11 final closeout is checkpoint-only and Phase 11 remains open |

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture; for that, always go to `ARCHITECTURE_MASTER.md`.*
