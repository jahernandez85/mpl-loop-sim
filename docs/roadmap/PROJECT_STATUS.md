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
| **Stage** | Phase 8 checkpoint audit complete; continue Phase 8 |
| **Completed phase** | **Phase 8 checkpoint - Solver contract primitives, residual interface, and minimal convergence-gate steady solver** |
| **Phase 3 audit verdict** | **APPROVED FOR PHASE 4** |
| **Phase 4 audit verdict** | **APPROVED FOR PHASE 5** |
| **Phase 5A audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 6 checkpoint verdict** | **APPROVED AS PHASE 6 CHECKPOINT - CONTINUE PHASE 6** |
| **Phase 6 final audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 6 status** | **Complete for Pipe component closeout scope. Phase 6A, 6B, 6C, 6D, 6E, and 6F are complete.** |
| **Phase 7 final audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 7 status** | **Complete for Network and Assembly closeout scope. Phase 7A, 7B, and 7C are complete.** |
| **Phase 8 audit verdict** | **APPROVED FOR MERGE AS PHASE 8 CHECKPOINT — CONTINUE PHASE 8** |
| **Phase 8 status** | **Partially complete and safe to merge as a checkpoint. Phase 8A, 8B, and 8C are complete; Phase 8 remains active.** |
| **Branch status** | **Implemented on `phase-8-solver`; safe to merge into `main` as a checkpoint, not as full Phase 8 closeout.** |
| **Current active phase** | **Phase 8 - First Steady Solver** |
| **Next immediate slice** | Phase 8D - assembled steady problem wrapper, fixed-point pressure iteration/update interface, and convergence metadata with strategy reporting |
| **Working tree before this docs task** | Phase 8A through Phase 8C implementation present |
| **Test status** | 1361 passed, verified 2026-06-16 with `pytest`; pytest emitted a `.pytest_cache` permission warning |
| **Lint status** | `ruff check .` clean, verified 2026-06-16 |
| **Format status** | `black --check src tests` clean, verified 2026-06-16; 71 files would be left unchanged |

Phase 6 is complete as a documentation-audited implementation milestone:

- Phase 6A added component contract primitives and the Pipe skeleton.
- Phase 6B added the Pipe single-phase friction-only contribution helper using the existing `SINGLE_PHASE_DP` correlation contract.
- Phase 6C added the Pipe gravity pressure contribution helper.
- Phase 6D added the Pipe acceleration pressure contribution helper.
- Phase 6E added the local Pipe mechanical pressure summary scaffold.
- Phase 6F proved calibration placement: `R*` / `friction_multiplier` scales only friction, not gravity, acceleration, or the total directly.

The Pipe component currently includes skeleton, single-phase friction, gravity, acceleration, mechanical pressure summary, and friction-only calibration placement. It remains local and is not a network.

Phase 7 is complete as a documentation-audited implementation milestone:

- Phase 7A added Network identity and topology primitives.
- Phase 7B added connection validation and graph checks.
- Phase 7C added deterministic `SystemState` assembly through `StateLayout`, port handles, optional internal handles, and connected-port peer mapping.

The Network currently includes topology primitives, validation/graph checks, and `SystemState` assembly. It remains solver-free and physics-free.

Phase 8 is partially complete as a documentation-audited checkpoint:

- Phase 8A added solver contract primitives: `SolverId`, `SolverStatus`, `SolverOptions`, `SolverReport`, and `SolverResult`.
- Phase 8B added the generic residual evaluation interface: `ResidualVector`, `ResidualEvaluation`, and `ResidualEvaluator`.
- Phase 8C added a minimal convergence-gate `SteadySolver`.

The current solver evaluates the residual at the initial `SystemState` once. If residual norm is within tolerance it returns `CONVERGED`; otherwise it returns `FAILED`. It does not implement state update logic, fixed-point pressure iteration, Newton, Jacobians, physical residual assembly, pressure solving, flow solving, or validation invariants.

The solver remains generic and physics-free. It does not import CoolProp, properties, correlations, calibration, components, network, geometry, or discretization. Network and components do not import solvers.

Newton, Jacobians, physical residuals, pressure solving, flow solving, schema serialization, optimization, fitting, advanced component models, transient solving, and new components remain deferred unless a later audit explicitly changes that status. Pump, accumulator, evaporator, condenser, and heat-exchanger components remain deferred to their planned later phases.

The Phase 8 checkpoint audit closeout changed documentation only. No source code and no test files were modified during audit closeout.

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
| **Phase 6 checkpoint audit** | **Complete; approved as checkpoint, continue Phase 6** |
| **Phase 6 final audit** | **Complete; approved for Phase 7** |
| **Phase 7A - Network identity and topology primitives** | **Complete** |
| **Phase 7B - Connection validation and graph checks** | **Complete** |
| **Phase 7C - Network SystemState assembly** | **Complete** |
| **Phase 7 final audit** | **Complete; approved for Phase 8** |
| **Phase 8A - Solver contract primitives** | **Complete** |
| **Phase 8B - Residual evaluation interface** | **Complete** |
| **Phase 8C - Minimal convergence-gate steady solver** | **Complete** |
| **Phase 8 checkpoint audit** | **Complete; approved for merge as checkpoint, continue Phase 8** |

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

---

## 4. Current Active Phase

**Phase 8 - First Steady Solver** remains the current active phase according to `IMPLEMENTATION_PLAN.md`.

Phase 8 completed checkpoint scope:

- solver contract primitives;
- residual evaluation interface;
- minimal convergence-gate steady solver.

Phase 8 remaining objective:

- close the first vertical slice with a steady solver;
- assemble residuals from component contributions and Network continuity/closure conditions;
- drive the assembled system over `SystemState`;
- keep Network responsible for topology and assembly, not numerical solving;
- keep Pipe as a local component that does not name the Network, neighbours, or Solver.
- add fixed-point pressure iteration / update behavior;
- add an assembled steady problem wrapper;
- add convergence metadata with a strategy field;
- add finite-difference Jacobian and Newton only after the assembled residual path is stable, as required for full Phase 8 closeout.

Phase boundaries to preserve:

- Do not turn Network into a solver.
- Do not make Pipe network-aware or solver-aware.
- Do not implement Pump or Accumulator components yet; they remain V1 Build Phase 10.
- Do not implement Evaporator, Condenser, `HeatExchangerModel`, or heat-exchanger components yet; they remain V1 Build Phase 11.
- Do not implement heat transfer, phase change, or two-phase pressure drop in Phase 8.
- Do not move pressure, enthalpy, mass flow, derived properties, or solver vectors onto Pipe or Port objects.
- Keep `SystemState` as the only owner of values.

---

## 5. Next Immediate Actions

1. Review and commit the Phase 8 checkpoint audit closeout.
2. Continue **Phase 8 - First Steady Solver** from `IMPLEMENTATION_PLAN.md`.
3. Implement Phase 8D: assembled steady problem wrapper, fixed-point pressure iteration / update interface, and convergence metadata with strategy reporting.
4. Keep Phase 8 focused on solver residual assembly and numerical iteration over `SystemState`.
5. Preserve the Phase 7 boundary: Network owns topology and assembly only.
6. Preserve the Pipe Phase 6 boundary: local helper mechanics only, no network or solver awareness.
7. Run `pytest`, `ruff check .`, and `black --check src tests` before reporting the next implementation task complete.

Recommended commit message:

```text
docs: audit phase 8 steady solver checkpoint
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

None block merging this Phase 8 checkpoint or continuing Phase 8 after this audit is reviewed and committed.

| Item | What it affects | Resolution path |
|---|---|---|
| Import-direction rules are not enforced by import-linter tooling | Future cross-layer expansion | Add import-linter or equivalent before higher layers expand further |
| Solver residual assembly not yet implemented | Phase 8 | Implement in the first steady solver without changing Network into a solver |
| Fixed-point pressure iteration not yet implemented | Phase 8 closeout | Add after the assembled steady problem/update interface is defined |
| Simultaneous Newton and finite-difference Jacobian not yet implemented | Phase 8 closeout | Add after fixed-point/residual assembly path is stable |
| `ConvergenceMetadata.strategy` not yet represented | Phase 8 closeout | Extend convergence reporting without coupling solver to physics |
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

- Phase 8 is active.
- Phase 8A, 8B, and 8C are complete and approved for merge as a checkpoint.
- Phase 8 is not fully closed out.
- Phase 7 is complete and approved for the next phase.
- Do not reopen Phase 7 unless a new task explicitly requests a Phase 7 fix.
- Work only on first steady solver scope unless a new task explicitly changes the phase.
- Continue with the next Phase 8 implementation slice: assembled steady problem wrapper, fixed-point pressure iteration / update interface, and convergence metadata with strategy reporting.
- Keep Network topology/assembly-only; do not turn it into a solver.
- Keep Pipe local; do not add network or solver behavior to Pipe.
- Preserve separation among geometry, discretization, correlations, calibration, components, network, and solvers.
- Keep Pump, Accumulator, Evaporator, Condenser, heat transfer, phase change, and two-phase pressure drop deferred.
- Run `pytest`, `ruff check .`, and `black --check src tests` before reporting any implementation task complete.
- Do not include `Co-Authored-By` lines unless explicitly requested.

---

## 9. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-16 |
| **Updated by** | Codex |
| **Status note** | Phase 8A-8C complete; Phase 8 checkpoint audit approved for merge and continued Phase 8 work; documentation-only closeout with no source/test changes |

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture; for that, always go to `ARCHITECTURE_MASTER.md`.*
