# PROJECT_STATUS.md

Operational memory for the MPL simulation framework.
This document is not architecture. It does not redesign anything. It tracks where the project is and what to do next.

---

## 1. Current Status

| Field | Value |
|---|---|
| **Project name** | MPL Loop Simulation Library |
| **Repository** | `mpl-loop-sim` |
| **Branch** | `main` |
| **Stage** | Phase 6 final audit complete; ready for Phase 7 |
| **Completed phase** | **Phase 6 - Pipe Component** |
| **Phase 3 audit verdict** | **APPROVED FOR PHASE 4** |
| **Phase 4 audit verdict** | **APPROVED FOR PHASE 5** |
| **Phase 5A audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 6 checkpoint verdict** | **APPROVED AS PHASE 6 CHECKPOINT - CONTINUE PHASE 6** |
| **Phase 6 final audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 6 status** | **Complete for Pipe component closeout scope. Phase 6A, 6B, 6C, 6D, 6E, and 6F are complete.** |
| **Current active phase** | **Phase 7 - Network and Assembly** |
| **Next immediate slice** | Begin Phase 7 topology validation and `SystemState` assembly without making Pipe network-aware or solver-aware |
| **Working tree before this docs task** | Phase 6A through Phase 6F implementation present |
| **Test status** | 1083 passed, verified 2026-06-15 with `pytest`; pytest emitted a `.pytest_cache` permission warning |
| **Lint status** | `ruff check .` clean, verified 2026-06-15 |
| **Format status** | `black --check src tests` clean, verified 2026-06-15; 57 files would be left unchanged |

Phase 6 is complete as a documentation-audited implementation milestone:

- Phase 6A added component contract primitives and the Pipe skeleton.
- Phase 6B added the Pipe single-phase friction-only contribution helper using the existing `SINGLE_PHASE_DP` correlation contract.
- Phase 6C added the Pipe gravity pressure contribution helper.
- Phase 6D added the Pipe acceleration pressure contribution helper.
- Phase 6E added the local Pipe mechanical pressure summary scaffold.
- Phase 6F proved calibration placement: `R*` / `friction_multiplier` scales only friction, not gravity, acceleration, or the total directly.

The Pipe component currently includes skeleton, single-phase friction, gravity, acceleration, mechanical pressure summary, and friction-only calibration placement. It remains local and is not a network.

Heat transfer, phase change, two-phase pressure drop, network assembly, and solvers remain deferred. Pump, accumulator, evaporator, condenser, and heat-exchanger components remain deferred to their planned later phases.

The Phase 6 final audit closeout changed documentation only. No source code and no test files were modified.

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

Closeout artifacts:

- `docs/validation/audits/PHASE_2_CLOSEOUT_SUMMARY.md`
- `docs/validation/audits/PHASE_2_COMPLETE_AUDIT.md`
- `docs/validation/audits/PHASE_2_PROPERTY_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_4_GEOMETRY_DISCRETIZATION_AUDIT.md`
- `docs/validation/audits/PHASE_5A_CALIBRATION_PRIMITIVES_AUDIT.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_CHECKPOINT_AUDIT.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_FINAL_AUDIT.md`

---

## 4. Current Active Phase

**Phase 7 - Network and Assembly** is now the current active phase according to `IMPLEMENTATION_PLAN.md`.

Phase 7 objective:

- assemble validated topology into `SystemState`;
- implement connections, junctions, branch structure, one-reference invariant, and inventory-accounting shape as planned;
- keep the Network responsible for topology and assembly;
- keep Pipe as a local component that does not name the Network, neighbours, or Solver.

Phase boundaries to preserve:

- Do not implement solvers yet; Phase 8 owns the first steady solver.
- Do not implement Pump or Accumulator components yet; they remain V1 Build Phase 10.
- Do not implement Evaporator, Condenser, `HeatExchangerModel`, or heat-exchanger components yet; they remain V1 Build Phase 11.
- Do not implement heat transfer, phase change, or two-phase pressure drop in Phase 7.
- Do not move pressure, enthalpy, mass flow, derived properties, or solver vectors onto Pipe or Port objects.
- Keep calibration registry resolution out of Pipe until component slots and network assembly require it.

---

## 5. Next Immediate Actions

1. Review and commit the Phase 6 final audit closeout.
2. Start **Phase 7 - Network and Assembly** from `IMPLEMENTATION_PLAN.md`.
3. Keep Phase 7 focused on topology validation and `SystemState` assembly.
4. Preserve the Pipe Phase 6 boundary: local helper mechanics only, no network or solver awareness.
5. Run `pytest`, `ruff check .`, and `black --check src tests` before reporting the next implementation task complete.

Recommended commit message:

```text
docs: close out phase 6 pipe component
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

None block starting Phase 7 after this final audit is reviewed and committed.

| Item | What it affects | Resolution path |
|---|---|---|
| Import-direction rules are not enforced by import-linter tooling | Future cross-layer expansion | Add import-linter or equivalent before higher layers expand further |
| Network and topology assembly not yet implemented | Phase 7 | Implement according to `IMPLEMENTATION_PLAN.md` without changing Pipe into a network-aware object |
| Solver residual assembly not yet implemented | Phase 8 | Implement after Phase 7 Network assembly is green |
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

- Phase 7 is active.
- Phase 6 is complete and approved for the next phase.
- Do not reopen Phase 6 unless a new task explicitly requests a Phase 6 fix.
- Work only on Network and assembly scope unless a new task explicitly changes the phase.
- Keep Pipe local; do not add network or solver behavior to Pipe.
- Preserve separation among geometry, discretization, correlations, calibration, components, network, and solvers.
- Keep Pump, Accumulator, Evaporator, Condenser, heat transfer, phase change, and two-phase pressure drop deferred.
- Run `pytest`, `ruff check .`, and `black --check src tests` before reporting any implementation task complete.
- Do not include `Co-Authored-By` lines unless explicitly requested.

---

## 9. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-15 |
| **Updated by** | Codex |
| **Status note** | Phase 6A-6F complete; Phase 6 final audit approved for Phase 7; documentation-only closeout with no source/test changes |

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture; for that, always go to `ARCHITECTURE_MASTER.md`.*
