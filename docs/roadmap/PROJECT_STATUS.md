# PROJECT_STATUS.md

Operational memory for the MPL simulation framework.
This document is not architecture. It does not redesign anything. It tracks where the project is and what to do next.

---

## 1. Current Status

| Field | Value |
|---|---|
| **Project name** | MPL Loop Simulation Library |
| **Repository** | `mpl-loop-sim` |
| **Branch** | `phase-10-pump-accumulator` |
| **Stage** | Phase 10 Pump and Accumulator checkpoint audit complete; safe to merge as checkpoint; continue Phase 10 |
| **Completed phase** | **Phase 9 - Result and schema serialization** |
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
| **Phase 10 final audit verdict** | **APPROVED FOR MERGE AS PHASE 10 CHECKPOINT - CONTINUE PHASE 10** |
| **Phase 10 status** | **Checkpoint complete, full Phase 10 not complete. Pump and Accumulator foundations are implemented; detailed Phase 10 map/law/wiring work remains.** |
| **Branch status** | **Implemented on `phase-10-pump-accumulator`; safe to merge into `main` as a Phase 10 checkpoint only.** |
| **Current active phase** | **Phase 10 - Pump and Accumulator** |
| **Next immediate slice** | Continue Phase 10 with pump map/command behavior, accumulator volume-pressure law work, stored `V_g`, and reference-node wiring |
| **Working tree before this docs task** | Phase 10 checkpoint implementation present on `phase-10-pump-accumulator` |
| **Test status** | 1774 passed, verified 2026-06-16 with `pytest`; pytest emitted a `.pytest_cache` permission warning |
| **Lint status** | `ruff check .` clean, verified 2026-06-16 |
| **Format status** | `black --check src tests` clean, verified 2026-06-16; 93 files would be left unchanged |

Phase 10 currently contains a safe component-foundation checkpoint:

- Pump component foundation under `src/mpl_sim/components/pump.py`.
- Pump prescribed pressure-rise seam: `delta_p = delta_p_setpoint * pressure_rise_multiplier`.
- Pump hydraulic summary with raw and scaled pressure-rise reporting.
- Accumulator component foundation under `src/mpl_sim/components/accumulator.py`.
- Accumulator prescribed pressure-reference seam: `p_ref = p_setpoint`.
- Accumulator pressure summary with setpoint echo.
- Pump and Accumulator exports from `src/mpl_sim/components/__init__.py`.

Pump and Accumulator remain local, immutable, physics-light components. They do not call CoolProp, `PropertyBackend`, correlations, Network, Solver, physical residual assembly, dynamic simulation, fitting, or optimization. Ports remain value-free, and `SystemState` remains the owner of numerical state values.

This Phase 10 audit closeout changed documentation only. No source code and no test files were modified during audit closeout.

The following remain deferred unless explicitly planned in the next Phase 10 slice or a later phase:

- pump performance maps;
- pump shaft-speed dynamics;
- pump efficiency/power model and NPSH checks;
- accumulator stored gas volume or inventory state;
- accumulator `VolumePressureLaw` slot integration;
- PCA/HCA laws and gas-charged/spring/bellows law bindings;
- `VOLUME_PRESSURE_LAW` closures;
- network reference-node wiring;
- physical residual assembly;
- pressure/flow solving;
- optimization and fitting;
- advanced component models;
- dynamic simulation and controls;
- Evaporator, Condenser, `HeatExchangerModel`, heat transfer, phase change, and two-phase pressure drop.

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

---

## 4. Current Active Phase

The current active phase remains:

**Phase 10 - Pump and Accumulator**, according to `IMPLEMENTATION_PLAN.md`.

The completed checkpoint should be carried forward as the local component foundation. The next Phase 10 slice should focus on the remaining detailed Phase 10 acceptance scope:

- pump map or command seam required by the plan;
- pump speed/flow command binding behavior;
- accumulator `VolumePressureLaw` slot integration;
- PCA/HCA law work required by the plan;
- stored `V_g` / pressure-derived behavior at the planned V1 fidelity;
- reference-node wiring owned by Network;
- pump-driven, accumulator-referenced loop readiness through the planned contracts.

Phase 10 should not extend heat-exchanger physics or start Phase 11. It should not implement Evaporator, Condenser, heat transfer, phase change, two-phase pressure drop, transient solving, optimization, fitting, DOE generation, or literature validation unless a future task explicitly changes scope.

Phase boundaries to preserve:

- Do not turn Network into a solver.
- Do not make Pipe, Pump, or Accumulator network-aware or solver-aware.
- Keep Pump and Accumulator local until explicit network wiring work is planned.
- Do not implement Evaporator, Condenser, `HeatExchangerModel`, or heat-exchanger components yet; they remain V1 Build Phase 11.
- Do not implement heat transfer, phase change, or two-phase pressure drop in Phase 10.
- Do not move pressure, enthalpy, mass flow, derived properties, or solver vectors onto component or Port objects.
- Keep `SystemState` as the only owner of numerical values.

---

## 5. Next Immediate Actions

1. Review and commit the Phase 10 checkpoint audit closeout.
2. Merge `phase-10-pump-accumulator` into `main` only as a Phase 10 checkpoint.
3. Continue **Phase 10 - Pump and Accumulator** after merge.
4. Add the remaining detailed Phase 10 pump map/command and accumulator volume-pressure/reference wiring work in focused slices.
5. Preserve the checkpoint boundary: Pump and Accumulator foundations remain local and physics-light.
6. Preserve the Phase 9 boundary: schema/results/validation primitives remain data-only and physics-free.
7. Preserve the Phase 8 boundary: solver core remains generic and physics-free.
8. Preserve the Phase 7 boundary: Network owns topology and assembly/reference wiring only.
9. Preserve the Pipe Phase 6 boundary: local helper mechanics only, no network or solver awareness.
10. Run `pytest`, `ruff check .`, and `black --check src tests` before reporting the next implementation task complete.

Recommended commit message:

```text
docs: audit phase 10 pump and accumulator checkpoint
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

None block merging the Phase 10 checkpoint. Full Phase 10 closeout is blocked by the remaining detailed Phase 10 scope.

| Item | What it affects | Resolution path |
|---|---|---|
| Pump performance map and command binding not yet implemented | Full Phase 10 closeout | Continue Phase 10 with planned pump map/command seam |
| Pump shaft-speed/inertia named state not yet represented at planned V1 fidelity | Full Phase 10 closeout | Add only in the planned Phase 10 component-contract shape; keep dynamics deferred |
| Accumulator `VolumePressureLaw` slot not yet integrated | Full Phase 10 closeout | Continue Phase 10 with law slot separated from geometry |
| PCA/HCA law closures and numerical tests not yet implemented | Full Phase 10 closeout | Continue Phase 10 under `VOLUME_PRESSURE_LAW`; keep law params out of geometry |
| Stored accumulator `V_g` / derived-pressure law behavior not yet implemented | Full Phase 10 closeout | Add according to `INTERFACE_SPEC.md`; never store `P_sys` on the component |
| Network reference-node wiring not yet implemented | Full Phase 10 closeout | Add in Network, not as accumulator-side solver coupling |
| Import-direction rules are not enforced by import-linter tooling | Future cross-layer expansion | Add import-linter or equivalent if boundary risks grow |
| Full physical minimal `Result` artifact not yet implemented | Future schema/result integration | Add when later loop artifacts can produce physical run results |
| Physical invariant calculations not yet implemented | Future validation/residual integration | Keep primitives data-only until physical balances are explicitly planned |
| Full `ReproducibilityTuple` serialization not yet implemented | Future schema/result integration | Build on Phase 9 canonical primitives when physical tuple inputs are ready |
| Component serialization not yet implemented | Future schema integration | Add only safe serializers; avoid component-internal coupling |
| Physical residual assembly not yet implemented | Future solver integration | Add only when explicitly planned, keeping adapters separate from solver core |
| Newton and finite-difference Jacobian not yet implemented | Future solver strategy work | Introduce only when explicitly planned |
| Pressure solving and flow solving not yet implemented | Future loop solving work | Implement through generic residual/update contracts, not by coupling solver to components |
| Evaporator, Condenser, and HeatExchangerModel absent | Phase 11 | Implement only after full Phase 10 closeout |
| Heat transfer, phase change, and two-phase pressure drop absent | Phase 11+ | Keep deferred until the planned phases |
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

- The Phase 10 Pump and Accumulator foundation checkpoint is safe to merge.
- The branch `phase-10-pump-accumulator` is safe to merge into `main` as a checkpoint only.
- Phase 10 is not fully complete.
- Do not start Phase 11 heat-exchanger work from this checkpoint.
- Do not reopen Phase 9 unless a new task explicitly requests a Phase 9 fix.
- Keep schema/results/validation serialization data-only and physics-free.
- Keep solver core generic and physics-free.
- Keep physical residual adapters separate from solver core.
- Keep Network topology/assembly/reference wiring separate from solver behavior.
- Keep Pipe local; do not add network or solver behavior to Pipe.
- Keep Pump and Accumulator local; do not add network or solver behavior to either component.
- Preserve separation among geometry, discretization, correlations, calibration, components, network, solvers, schema, and results.
- Continue Pump and Accumulator work only within the Phase 10 plan; keep Evaporator, Condenser, heat transfer, phase change, two-phase pressure drop, Newton, Jacobians, and transient solving deferred unless explicitly requested.
- Run `pytest`, `ruff check .`, and `black --check src tests` before reporting any implementation task complete.
- Do not include `Co-Authored-By` lines unless explicitly requested.

---

## 9. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-16 |
| **Updated by** | Codex |
| **Status note** | Phase 10 Pump and Accumulator foundation checkpoint approved for merge as checkpoint; continue Phase 10; documentation-only audit closeout with no source/test changes |

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture; for that, always go to `ARCHITECTURE_MASTER.md`.*
