# PROJECT_STATUS.md

Operational memory for the MPL simulation framework.
This document is not architecture. It does not redesign anything. It tracks where the project is and what to do next.

---

## 1. Current Status

| Field | Value |
|---|---|
| **Project name** | MPL Loop Simulation Library |
| **Repository** | `mpl-loop-sim` |
| **Branch** | `phase-10b-pump-map-accumulator-law` |
| **Stage** | Phase 10 Pump and Accumulator final closeout complete; safe to merge and advance after merge |
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
| **Branch status** | **Implemented on `phase-10b-pump-map-accumulator-law`; safe to merge into `main`.** |
| **Current active phase** | **Phase 11 - HeatExchangerModel, Evaporator and Condenser after Phase 10 merge** |
| **Next immediate slice** | Start Phase 11 with HeatExchangerModel interface/registry strategy work, then Evaporator and Condenser according to `IMPLEMENTATION_PLAN.md` |
| **Working tree before this docs task** | Phase 10 completion implementation present on `phase-10b-pump-map-accumulator-law` |
| **Test status** | 1983 passed, verified 2026-06-16 with `pytest`; pytest emitted a `.pytest_cache` permission warning |
| **Lint status** | `ruff check .` clean, verified 2026-06-16 |
| **Format status** | `black --check src tests` clean, verified 2026-06-16; 99 files would be left unchanged |

Phase 10 is complete and safe to merge.

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
- Evaporator, Condenser, `HeatExchangerModel`, heat transfer, phase change, and two-phase pressure drop until Phase 11+ work begins.

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

---

## 4. Current Active Phase

The current active phase after merging `phase-10b-pump-map-accumulator-law` is:

**Phase 11 - HeatExchangerModel, Evaporator and Condenser**, according to `IMPLEMENTATION_PLAN.md`.

The completed Phase 10 work should be carried forward as the pressure-reference and pump-drive foundation:

- pump map and command behavior;
- pump power/efficiency seam;
- shaft-speed/inertia named-frozen seam;
- accumulator `VolumePressureLaw` slot integration;
- PCA pressure law and HCA seam decision;
- stored `V_g` / pressure-derived behavior at planned V1 fidelity;
- reference-node wiring owned by Network;
- pump-driven, accumulator-referenced loop acceptance shape.

Phase 11 should now begin with `HeatExchangerModel`, Evaporator, and Condenser only. Dynamic simulation, controls, fitting, optimization, DOE generation, literature validation, and unplanned solver behavior changes remain deferred unless a future task explicitly changes scope.

Phase boundaries to preserve:

- Do not turn Network into a solver.
- Do not make Pipe, Pump, or Accumulator network-aware or solver-aware.
- Keep Pump and Accumulator local and preserve their completed Phase 10 seams.
- Implement Evaporator, Condenser, `HeatExchangerModel`, and heat-exchanger components only inside the Phase 11 plan.
- Do not implement dynamic controls, fitting, optimization, or unplanned solver behavior in Phase 11.
- Do not move pressure, enthalpy, mass flow, derived properties, or solver vectors onto component or Port objects.
- Keep `SystemState` as the only owner of numerical values.

---

## 5. Next Immediate Actions

1. Review and commit the Phase 10 final closeout audit.
2. Merge `phase-10b-pump-map-accumulator-law` into `main`.
3. Start **Phase 11 - HeatExchangerModel, Evaporator and Condenser** after merge.
4. Preserve the completed Phase 10 boundary: Pump and Accumulator remain local and physics-light; Network owns pressure-reference wiring; law evaluation stays out of Network.
5. Preserve the Phase 9 boundary: schema/results/validation primitives remain data-only and physics-free.
6. Preserve the Phase 8 boundary: solver core remains generic and physics-free.
7. Preserve the Phase 7 boundary: Network owns topology and assembly/reference wiring only.
8. Preserve the Pipe Phase 6 boundary: local helper mechanics only, no network or solver awareness.
9. Keep dynamic controls, fitting, optimization, DOE generation, and literature validation deferred unless explicitly requested.
10. Run `pytest`, `ruff check .`, and `black --check src tests` before reporting the next implementation task complete.

Recommended commit message:

```text
docs: close out phase 10 pump and accumulator
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

None block merging the Phase 10 final closeout.

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
| Evaporator, Condenser, and HeatExchangerModel absent | Phase 11 | Implement next according to `IMPLEMENTATION_PLAN.md` |
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

- The Phase 10 Pump and Accumulator final closeout is safe to merge.
- The branch `phase-10b-pump-map-accumulator-law` is safe to merge into `main`.
- Phase 10 is complete.
- After merge, start Phase 11 heat-exchanger work according to `IMPLEMENTATION_PLAN.md`.
- Do not reopen Phase 9 unless a new task explicitly requests a Phase 9 fix.
- Keep schema/results/validation serialization data-only and physics-free.
- Keep solver core generic and physics-free.
- Keep physical residual adapters separate from solver core.
- Keep Network topology/assembly/reference wiring separate from solver behavior.
- Keep Pipe local; do not add network or solver behavior to Pipe.
- Keep Pump and Accumulator local; do not add network or solver behavior to either component.
- Preserve separation among geometry, discretization, correlations, calibration, components, network, solvers, schema, and results.
- Continue Pump and Accumulator only for focused fixes or hardening; start Phase 11 with `HeatExchangerModel`, Evaporator, and Condenser. Keep dynamic controls, fitting, optimization, DOE, literature validation, Newton/Jacobian expansion, and transient solving deferred unless explicitly requested.
- Run `pytest`, `ruff check .`, and `black --check src tests` before reporting any implementation task complete.
- Do not include `Co-Authored-By` lines unless explicitly requested.

---

## 9. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-16 |
| **Updated by** | Codex |
| **Status note** | Phase 10 Pump and Accumulator final closeout approved for merge and next phase; documentation-only audit closeout with no source/test changes |

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture; for that, always go to `ARCHITECTURE_MASTER.md`.*
