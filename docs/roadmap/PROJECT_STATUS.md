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
| **Stage** | Phase 4 closeout complete; approved for Phase 5 |
| **Completed phase** | Phase 4 - Geometry and discretization |
| **Phase 3 audit verdict** | **APPROVED FOR PHASE 4** |
| **Phase 4 audit verdict** | **APPROVED FOR PHASE 5** |
| **Current active phase** | **Phase 5 - Calibration** |
| **Immediate Phase 5 slice** | Calibration value objects and conservation-firewall shape per `IMPLEMENTATION_PLAN.md`; do not start implementation until a Phase 5 task is explicitly opened |
| **Working tree before this docs task** | Phase 4A and Phase 4B implementation present |
| **Test status** | 588 passed, verified 2026-06-13 with `pytest`; pytest emitted a `.pytest_cache` permission warning |
| **Lint status** | `ruff check .` clean, verified 2026-06-13 |
| **Format status** | `black --check src tests` clean, verified 2026-06-13; `black --check .` blocked by `.pytest_cache` permission error |

Phase 4 is complete. The audit closeout changed documentation only: no source code and no tests were modified.

Implementation should stop here for now after Phase 4 closeout. Do not start Phase 5 implementation unless a new task explicitly opens it.

Pipe component is not implemented. It remains deferred to V1 Build Phase 6. Component-tied discretization integration objects are not implemented and remain deferred until component integration requires them.

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

Phase 2 closeout artifacts:

- `docs/validation/audits/PHASE_2_CLOSEOUT_SUMMARY.md`
- `docs/validation/audits/PHASE_2_COMPLETE_AUDIT.md`
- Existing supporting audit: `docs/validation/audits/PHASE_2_PROPERTY_LAYER_AUDIT.md`

Phase 3 closeout artifact:

- `docs/validation/audits/PHASE_3_CORRELATION_LAYER_AUDIT.md`

Phase 4 closeout artifact:

- `docs/validation/audits/PHASE_4_GEOMETRY_DISCRETIZATION_AUDIT.md`

---

## 4. Current Repository Structure

```text
mpl-loop-sim/
|-- docs/
|   |-- architecture/
|   |-- decisions/
|   |-- roadmap/
|   `-- validation/
|       `-- audits/
|-- src/
|   `-- mpl_sim/
|       |-- core/
|       |-- properties/
|       |-- correlations/
|       |-- geometry/
|       |-- discretization/
|       |-- calibration/
|       |-- components/
|       |-- hx_models/
|       |-- network/
|       |-- solvers/
|       |-- schema/
|       |-- results/
|       `-- validation/
|-- tests/
|   |-- unit/
|   |-- property/
|   |-- correlation/
|   |-- geometry/
|   |-- calibration/
|   |-- component/
|   |-- network/
|   |-- solver/
|   |-- result/
|   |-- schema/
|   |-- literature/
|   |-- regression/
|   `-- compliance/
|-- pyproject.toml
`-- README.md
```

---

## 5. Phase 2 Closeout

**Phase 2 - PropertyBackend** (`src/mpl_sim/properties/`) is complete.

Scope completed:

- Phase 2A - `PropertyBackend` interface contract.
- Phase 2B - `CoolPropBackend`.
- Phase 2C - `PropertyBackendRegistry`, `BackendSelection`, and default backend-name binding.

Architectural guarantees preserved:

- `FluidState` remains pure P/h/identity.
- `FluidState` stores no derived properties.
- `FluidState` holds no `PropertyBackend` reference.
- CoolProp is confined to `properties/`.
- `core/` does not import `properties/` or CoolProp.
- P-h remains the canonical property input pair.
- `PropertyBackend` remains vector-first.
- Unsupported mixtures/custom fluids are explicit, not silently guessed.
- The property backend registry is separate from the future correlation registry.

Known deferred items:

- `TabulatedPropertyBackend`.
- REFPROP backend.
- Empirical backend.
- Mixture backend support.
- Full `ReproducibilityTuple` serialization.
- Import-linter or equivalent import-boundary enforcement before higher layers expand.
- `CoolPropBackend.valid_range()` remains a coarse envelope, not a precision domain certificate.

---

## 6. Current Active Phase

**Phase 5 - Calibration** is the next implementation phase according to `IMPLEMENTATION_PLAN.md`.

Phase 4 is closed:

- Phase 4A immutable geometry primitives are complete.
- Phase 4B discretization primitives are complete.
- Phase 4 audit verdict is **APPROVED FOR PHASE 5**.
- No source code or test files were modified during the Phase 4 audit closeout.

Implementation should stop here for now after the Phase 4 closeout document is reviewed and committed. Do not begin Phase 5 implementation unless a new task explicitly opens it.

Phase boundaries to preserve:

- Do not implement the Pipe component yet; Pipe remains V1 Build Phase 6.
- Do not implement Pump or Accumulator components yet; they remain V1 Build Phase 10.
- Do not implement Evaporator or Condenser components yet; they remain V1 Build Phase 11.
- Do not implement solvers or network work yet.
- Do not add new real correlations unless a later consuming component phase requires them.
- Keep component-coupled discretization integration objects deferred until component integration requires them.

---

## 7. Next Immediate Actions

1. Review and commit the Phase 4 audit closeout.
2. Stop implementation here until a new task explicitly opens Phase 5.
3. When Phase 5 starts, implement Calibration only per `IMPLEMENTATION_PLAN.md`.
4. Keep Pipe component work deferred to Phase 6.
5. Keep Pump and Accumulator component work deferred to Phase 10.
6. Keep Evaporator and Condenser component work deferred to Phase 11.
7. Keep component-coupled discretization integration objects deferred until component integration requires them.
8. Add import-linter or equivalent before higher-layer cross-package imports expand, or keep this as a tracked follow-up until it is implemented.

Recommended commit message:

```text
docs: close out phase 4 geometry and discretization
```

---

## 8. Non-Negotiable Implementation Rules

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

## 9. Current Known Blockers and Deferred Work

None block Phase 5 after Phase 4 closeout review and commit.

| Item | What it affects | Resolution path |
|---|---|---|
| Import-direction rules are not enforced by import-linter tooling | Future cross-layer expansion | Add import-linter or equivalent before higher layers expand |
| 29 property CSV files missing | Future `TabulatedPropertyBackend`; `sigma_e`/`eps_r` | Data recovery task; does not block CoolProp-backed V1 path |
| Literature validation data must be lifted and pinned | Literature tests | Phase 12 validation-data task |
| Registry-name vs `ClosureMetadata.name` canonicalization | Future correlation catalogue growth | Document or enforce before the catalogue expands |
| Per-correlation validity envelopes | Correlation admissibility | Author per additional correlation when consuming components require it |
| Content-hash canonicalization rule | Schema serialization determinism | Establish when serializers are implemented in Phase 9 |

---

## 10. Instructions for Future AI Agents

Before any coding task, read in order:

1. `docs/roadmap/PROJECT_STATUS.md`
2. `docs/roadmap/IMPLEMENTATION_PLAN.md`
3. `docs/validation/TEST_PLAN_V1.md`
4. Relevant sections of `docs/architecture/INTERFACE_SPEC.md`
5. Relevant audit/closeout documents in `docs/validation/audits/`

Rules for the next implementation session:

- Phase 4 is complete and approved for Phase 5.
- Work only on Phase 5 calibration when a new task explicitly opens that phase.
- Do not implement components in Phase 5.
- Do not implement Pipe until Phase 6.
- Do not implement Pump or Accumulator components until Phase 10.
- Do not implement Evaporator or Condenser until Phase 11.
- Preserve the separation between geometry, discretization, correlations, calibration, and components.
- Keep component-coupled discretization integration objects deferred until component integration requires them.
- Preserve the separation between `PropertyBackendRegistry` and `CorrelationRegistry`.
- Run `pytest`, `ruff check`, and `black --check` before reporting any implementation task complete.
- Do not include `Co-Authored-By` lines unless explicitly requested by the user.

---

## 11. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-13 |
| **Updated by** | Codex |
| **Status note** | Phase 4 geometry and discretization foundation complete; approved for Phase 5 calibration |

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture; for that, always go to `ARCHITECTURE_MASTER.md`.*
