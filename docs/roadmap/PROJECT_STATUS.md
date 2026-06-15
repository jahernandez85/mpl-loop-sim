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
| **Stage** | Phase 6 checkpoint audited; Phase 6 remains active |
| **Completed phase** | Phase 6C - Pipe gravity pressure contribution |
| **Phase 3 audit verdict** | **APPROVED FOR PHASE 4** |
| **Phase 4 audit verdict** | **APPROVED FOR PHASE 5** |
| **Phase 5A audit verdict** | **APPROVED FOR NEXT PHASE** |
| **Phase 6 checkpoint verdict** | **APPROVED AS PHASE 6 CHECKPOINT - CONTINUE PHASE 6** |
| **Phase 6 status** | **Active; partially complete. Phase 6A, 6B, and 6C are complete, but full Phase 6 closeout is not yet supported by `IMPLEMENTATION_PLAN.md`.** |
| **Current active phase** | **Phase 6 - Pipe Component** |
| **Immediate Phase 6 slice** | **Phase 6D - pipe acceleration pressure contribution and mechanical summary scaffold** |
| **Working tree before this docs task** | Phase 6A/6B/6C implementation present |
| **Test status** | 870 passed, verified 2026-06-15 with `pytest`; pytest emitted a `.pytest_cache` permission warning |
| **Lint status** | `ruff check .` clean, verified 2026-06-15 |
| **Format status** | `black --check src tests` clean, verified 2026-06-15; 54 files would be left unchanged |

Phase 6A, Phase 6B, and Phase 6C are complete as implementation checkpoints:

- Phase 6A added component contract primitives and the Pipe skeleton.
- Phase 6B added the Pipe single-phase friction-only contribution helper using the existing `SINGLE_PHASE_DP` correlation contract.
- Phase 6C added the Pipe gravity pressure contribution helper.

The Pipe component currently includes a skeleton, single-phase friction contribution, and gravity contribution. It does not yet implement the full Phase 6 contribution contract, acceleration contribution, integrated mechanical residual/summary, calibration placement, network integration, or solver integration.

The Phase 6 audit closeout changed documentation only. No source code and no test files were modified.

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
| **Phase 6 checkpoint audit** | **Complete; approved as checkpoint, continue Phase 6** |

Closeout artifacts:

- `docs/validation/audits/PHASE_2_CLOSEOUT_SUMMARY.md`
- `docs/validation/audits/PHASE_2_COMPLETE_AUDIT.md`
- `docs/validation/audits/PHASE_2_PROPERTY_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`
- `docs/validation/audits/PHASE_4_GEOMETRY_DISCRETIZATION_AUDIT.md`
- `docs/validation/audits/PHASE_5A_CALIBRATION_PRIMITIVES_AUDIT.md`
- `docs/validation/audits/PHASE_6_PIPE_COMPONENT_CHECKPOINT_AUDIT.md`

---

## 4. Current Active Phase

**Phase 6 - Pipe Component** remains active according to `IMPLEMENTATION_PLAN.md`.

The current Phase 6 implementation is a checkpoint, not a full closeout:

- Component contract primitives are present.
- Pipe skeleton is present.
- Pipe single-phase friction-only helper is present.
- Pipe gravity pressure contribution helper is present.
- Friction and gravity are separately inspectable.
- Pipe remains local and does not know network or solver objects.

Still required before full Phase 6 closeout:

- Pipe contribution-contract behavior.
- Internal 1D gradient kernel in lumped mode.
- Acceleration pressure contribution.
- Integrated mechanical summary or momentum residual.
- Frozen-zero derivative reporting if included in the chosen Phase 6D contract slice.
- Calibration placement proving `R*` scales only friction, not gravity, acceleration, or balances.

Phase boundaries to preserve:

- Do not start Phase 7 network work yet.
- Do not implement solvers yet.
- Do not implement Pump or Accumulator components yet; they remain V1 Build Phase 10.
- Do not implement Evaporator, Condenser, `HeatExchangerModel`, or heat-exchanger components yet; they remain V1 Build Phase 11.
- Do not implement heat transfer, phase change, or two-phase behavior in Phase 6D unless explicitly scoped by the implementation plan.
- Keep calibration application narrow and only at the documented friction-gradient seam when it is introduced.

---

## 5. Next Immediate Actions

1. Review and commit the Phase 6 checkpoint audit closeout.
2. Continue Phase 6 with **Phase 6D - pipe acceleration pressure contribution and mechanical summary scaffold**.
3. Keep friction, gravity, and acceleration separately inspectable.
4. Do not implement network, solvers, pump, accumulator, evaporator, condenser, heat transfer, phase change, or two-phase behavior in the next slice.
5. Run `pytest`, `ruff check .`, and `black --check src tests` before reporting the next implementation task complete.

Recommended commit message:

```text
docs: audit phase 6 pipe checkpoint
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

None block continued Phase 6 implementation after this checkpoint audit is reviewed and committed.

| Item | What it affects | Resolution path |
|---|---|---|
| Full Phase 6 contribution contract not yet implemented | Phase 6 closeout | Continue with Phase 6D before advancing to Phase 7 |
| Acceleration contribution not yet implemented | Phase 6 closeout | Add as a separate inspectable Pipe contribution |
| Calibration application not yet wired into Pipe | Phase 6 closeout if selected for the next contract slice | Apply only to friction-gradient output, never gravity/acceleration/balances |
| Import-direction rules are not enforced by import-linter tooling | Future cross-layer expansion | Add import-linter or equivalent before higher layers expand |
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

- Phase 6 remains active.
- Phase 6A, 6B, and 6C are complete.
- Do not mark Phase 6 complete until the remaining `IMPLEMENTATION_PLAN.md` Phase 6 requirements are implemented and audited.
- Work only on the Pipe/component-contract scope unless a new task explicitly changes the phase.
- Keep Pipe local; do not add network or solver behavior.
- Preserve separation among geometry, discretization, correlations, calibration, and components.
- Keep Pump, Accumulator, Evaporator, Condenser, heat transfer, phase change, and two-phase pressure drop deferred.
- Run `pytest`, `ruff check .`, and `black --check src tests` before reporting any implementation task complete.
- Do not include `Co-Authored-By` lines unless explicitly requested.

---

## 9. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-15 |
| **Updated by** | Codex |
| **Status note** | Phase 6A/6B/6C complete; Phase 6 checkpoint audit approved; continue Phase 6 with acceleration/mechanical summary slice |

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture; for that, always go to `ARCHITECTURE_MASTER.md`.*
