# PROJECT_STATUS.md

Operational memory for the MPL simulation framework.
This document is not architecture. It does not redesign anything. It tracks where the project is and what to do next.

---

## 1. Current Status

| Field | Value |
|---|---|
| **Project name** | MPL Loop Simulation Library |
| **Repository** | `mpl-loop-sim` |
| **Branch** | `phase-8-solver` |
| **Stage** | Phase 8 final audit complete; ready to merge and advance after merge |
| **Completed phase** | **Phase 8 - First Steady Solver** |
| **Phase 3 audit verdict** | **APPROVED FOR PHASE 4** |
| **Phase 4 audit verdict** | **APPROVED FOR PHASE 5** |
| **Phase 5A audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 6 final audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 7 final audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 8 checkpoint audit verdict** | **APPROVED FOR MERGE AS PHASE 8 CHECKPOINT - CONTINUE PHASE 8** |
| **Phase 8 final audit verdict** | **APPROVED FOR MERGE AND NEXT PHASE** |
| **Phase 8 status** | **Complete. Phase 8A, 8B, 8C, 8D, and 8E are complete.** |
| **Branch status** | **Implemented on `phase-8-solver`; safe to merge into `main`.** |
| **Current active phase** | **Phase 9 - Result and schema serialization, after `phase-8-solver` is merged** |
| **Next immediate slice** | Phase 9 - schema/result serialization and validation invariants |
| **Working tree before this docs task** | Phase 8A through Phase 8E implementation present |
| **Test status** | 1519 passed, verified 2026-06-16 with `pytest`; pytest emitted a `.pytest_cache` permission warning |
| **Lint status** | `ruff check .` clean, verified 2026-06-16 |
| **Format status** | `black --check src tests` clean, verified 2026-06-16; 76 files would be left unchanged |

Phase 8 is complete as a documentation-audited implementation milestone:

- Phase 8A added solver contract primitives: `SolverId`, `SolverStatus`, `SolverOptions`, `SolverReport`, and `SolverResult`.
- Phase 8B added the generic residual evaluation interface: `ResidualVector`, `ResidualEvaluation`, and `ResidualEvaluator`.
- Phase 8C added the minimal convergence-gate `SteadySolver`.
- Phase 8D added `AssembledSteadyProblem`, `ConvergenceStrategy`, `ConvergenceMetadata`, `StateUpdate`, and `StateUpdateProvider`.
- Phase 8E added the fixed-point steady iteration loop through the update interface.

The solver currently includes contract primitives, residual interface, assembled steady problem wrapper, convergence metadata with strategy reporting, update interface, and fixed-point steady iteration. The no-update path preserves residual-gate behavior.

The solver remains generic and physics-free. It does not import CoolProp, properties, correlations, calibration, components, network, geometry, or discretization. It does not own physical residuals, and it does not solve pressure or flow directly. Network and components remain solver-free.

Newton, Jacobians, finite-difference Jacobians, physical residuals, pressure solving, flow solving, schema serialization, optimization, fitting, advanced component models, transient solving, and new components remain deferred to their planned phases unless a future task explicitly changes scope.

The Phase 8 final audit closeout changed documentation only. No source code and no test files were modified during audit closeout.

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

---

## 4. Current Active Phase

After `phase-8-solver` is merged, the current active phase is:

**Phase 9 - Result and schema serialization**, according to `IMPLEMENTATION_PLAN.md`.

Phase 9 should focus on:

- Result object shape and stored/reported/derived partition;
- validation invariants, including mass imbalance, energy imbalance, pressure-closure residual, and bound checks;
- schema serialization for tuple/result artifacts;
- versioning and round-trip behavior;
- explicit model selections and no hidden defaults;
- minimal stored state only.

Phase 9 should not extend solver physics or component models as part of the handoff. It should not implement Newton, Jacobians, physical residual assembly, pressure solving, flow solving, transient solving, optimization, fitting, or new components unless a future task explicitly changes scope.

Phase boundaries to preserve:

- Do not turn Network into a solver.
- Do not make Pipe network-aware or solver-aware.
- Do not implement Pump or Accumulator components yet; they remain V1 Build Phase 10.
- Do not implement Evaporator, Condenser, `HeatExchangerModel`, or heat-exchanger components yet; they remain V1 Build Phase 11.
- Do not implement heat transfer, phase change, or two-phase pressure drop in Phase 9.
- Do not move pressure, enthalpy, mass flow, derived properties, or solver vectors onto Pipe or Port objects.
- Keep `SystemState` as the only owner of values.

---

## 5. Next Immediate Actions

1. Review and commit the Phase 8 final audit closeout.
2. Merge `phase-8-solver` into `main`.
3. Start **Phase 9 - Result and schema serialization** from `IMPLEMENTATION_PLAN.md`.
4. Keep Phase 9 focused on Result/schema/invariant work.
5. Preserve the Phase 8 boundary: solver core remains generic and physics-free.
6. Preserve the Phase 7 boundary: Network owns topology and assembly only.
7. Preserve the Pipe Phase 6 boundary: local helper mechanics only, no network or solver awareness.
8. Run `pytest`, `ruff check .`, and `black --check src tests` before reporting the next implementation task complete.

Recommended commit message:

```text
docs: close out phase 8 steady solver
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

None block merging Phase 8 or advancing to Phase 9 after this audit is reviewed and committed.

| Item | What it affects | Resolution path |
|---|---|---|
| Import-direction rules are not enforced by import-linter tooling | Future cross-layer expansion | Add import-linter or equivalent if boundary risks grow |
| Result object not yet implemented | Phase 9 | Implement in planned Result/schema phase |
| Validation invariants not yet implemented | Phase 9 | Add mass/energy/pressure/bounds invariants with Result work |
| Schema serialization not yet implemented | Phase 9 | Implement tuple/result serialization and round-trip checks |
| Physical residual assembly not yet implemented | Future solver integration | Add only when explicitly planned, keeping adapters separate from solver core |
| Newton and finite-difference Jacobian not yet implemented | Future solver strategy work | Introduce only when explicitly planned |
| Pressure solving and flow solving not yet implemented | Future loop solving work | Implement through generic residual/update contracts, not by coupling solver to components |
| Pump and Accumulator absent | Phase 10 | Implement in planned component phase |
| Evaporator, Condenser, and HeatExchangerModel absent | Phase 11 | Implement in planned heat-exchanger phase |
| Heat transfer, phase change, and two-phase pressure drop absent | Phase 11+ | Keep deferred until the planned phases |
| 29 property CSV files missing | Future `TabulatedPropertyBackend`; `sigma_e`/`eps_r` | Data recovery task; does not block CoolProp-backed V1 path |
| Literature validation data must be lifted and pinned | Literature tests | Phase 12 validation-data task |
| Content-hash canonicalization rule | Schema serialization determinism | Establish when serializers are implemented in Phase 9 |

---

## 8. Instructions for Future AI Agents

Before any coding task, read in order:

1. `docs/roadmap/PROJECT_STATUS.md`
2. `docs/roadmap/IMPLEMENTATION_PLAN.md`
3. `docs/validation/TEST_PLAN_V1.md`
4. Relevant sections of `docs/architecture/INTERFACE_SPEC.md`
5. Relevant audit/closeout documents in `docs/validation/audits/`

Rules for the next implementation session:

- Phase 8 is complete and approved for merge and next phase.
- The branch `phase-8-solver` is safe to merge into `main`.
- After merge, Phase 9 is active.
- Do not start Phase 10 components from Phase 9 work.
- Do not reopen Phase 8 unless a new task explicitly requests a Phase 8 fix.
- Keep solver core generic and physics-free.
- Keep physical residual adapters separate from solver core.
- Keep Network topology/assembly-only; do not turn it into a solver.
- Keep Pipe local; do not add network or solver behavior to Pipe.
- Preserve separation among geometry, discretization, correlations, calibration, components, network, solvers, schema, and results.
- Keep Pump, Accumulator, Evaporator, Condenser, heat transfer, phase change, two-phase pressure drop, Newton, Jacobians, and transient solving deferred unless explicitly requested.
- Run `pytest`, `ruff check .`, and `black --check src tests` before reporting any implementation task complete.
- Do not include `Co-Authored-By` lines unless explicitly requested.

---

## 9. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-16 |
| **Updated by** | Codex |
| **Status note** | Phase 8A-8E complete; Phase 8 final audit approved for merge and next phase; documentation-only closeout with no source/test changes |

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture; for that, always go to `ARCHITECTURE_MASTER.md`.*
