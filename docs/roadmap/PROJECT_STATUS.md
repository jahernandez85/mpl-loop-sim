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
| **Stage** | Phase 2 closeout complete; Phase 3 pending closeout review/commit |
| **Completed phase** | Phase 2 - PropertyBackend |
| **Current active phase** | **Phase 3 - Correlation contract and registry** |
| **Immediate Phase 3 slice** | **Phase 3A - Correlation contract primitives** |
| **Working tree before this docs task** | Phase 2C reported committed |
| **Test status** | 316 passed, verified 2026-06-12 with `python -B -m pytest -p no:cacheprovider` |
| **Lint status** | `ruff check src tests` clean, verified 2026-06-12 |
| **Format status** | `black --check src tests` clean, verified 2026-06-12 |

Phase 3 should not start until the Phase 2 complete audit and closeout summary have been reviewed and committed.

Claude is not being used further in the current session due to high session usage. Future implementation should resume with a fresh Claude session or another coding agent.

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

Phase 2 closeout artifacts:

- `docs/validation/audits/PHASE_2_CLOSEOUT_SUMMARY.md`
- `docs/validation/audits/PHASE_2_COMPLETE_AUDIT.md`
- Existing supporting audit: `docs/validation/audits/PHASE_2_PROPERTY_LAYER_AUDIT.md`

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

**Phase 3 - Correlation contract and registry** is the next implementation phase according to `IMPLEMENTATION_PLAN.md`.

Start with a narrow **Phase 3A - Correlation contract primitives** prompt only after Phase 2 closeout docs are reviewed and committed.

Phase 3A should focus on:

- Correlation roles.
- Input value objects.
- `ValidityVerdict`.
- Correlation result object.
- Registry skeleton only if aligned with `IMPLEMENTATION_PLAN.md`.

Do not implement actual correlations in the first Phase 3 prompt.

---

## 7. Next Immediate Actions

1. Review and commit Phase 2 closeout docs.
2. Begin Phase 3A with a narrow prompt focused only on correlation contract primitives.
3. Do not implement actual correlations yet.
4. Do not implement components, geometry, network, solvers, or calibration yet.
5. Add import-linter or equivalent before Phase 3 expands into correlations/components/network/solvers, or keep this as a tracked follow-up until it is implemented.

Recommended commit message:

```text
docs: close out phase 2 property layer
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

None block Phase 3A after Phase 2 closeout review and commit.

| Item | What it affects | Resolution path |
|---|---|---|
| Import-direction rules are not enforced by import-linter tooling | Future cross-layer expansion | Add import-linter or equivalent before Phase 3 expands beyond primitives |
| 29 property CSV files missing | Future `TabulatedPropertyBackend`; `sigma_e`/`eps_r` | Data recovery task; does not block CoolProp-backed V1 path |
| Literature validation data must be lifted and pinned | Literature tests | Phase 12 validation-data task |
| Per-correlation validity envelopes | Correlation admissibility | Author per correlation in Phase 3+ |
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

- Do not start Phase 3 until Phase 2 closeout docs are reviewed and committed.
- Work only on Phase 3A correlation contract primitives.
- Do not implement HTC, pressure-drop, void-fraction, or heat-exchanger correlations yet.
- Do not implement geometry, components, calibration, network, solvers, schema, results, or validation harness work yet.
- Preserve the separation between `PropertyBackendRegistry` and the future correlation registry.
- Run `pytest`, `ruff check`, and `black --check` before reporting any implementation task complete.
- Do not include `Co-Authored-By` lines unless explicitly requested by the user.

---

## 11. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-12 |
| **Updated by** | Codex |
| **Status note** | Phase 2 property layer foundation complete; approved for Phase 3 pending closeout review/commit |

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture; for that, always go to `ARCHITECTURE_MASTER.md`.*
