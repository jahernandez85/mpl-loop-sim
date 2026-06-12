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
| **Stage** | Active implementation — Phase 0 complete, Phase 1 next |
| **Completed phase** | Phase 0 — Repository Preparation and Tooling |
| **Current active phase** | **Phase 1 — Core Data Model** |
| **Next phase after 1** | Phase 2 — PropertyBackend |
| **Last commit** | `bc9c78d chore: initialize python package and test tooling` |
| **Working tree** | Clean |
| **Test status** | 2 passed (smoke tests) |

---

## 2. Authoritative Documents

All eight binding documents are frozen. Do not modify them during implementation.

| Document | Purpose | Authority level |
|---|---|---|
| `docs/architecture/ARCHITECTURE_MASTER.md` | Single source of architectural truth; frozen decisions [F1]–[F18] | **Highest — overrides everything** |
| `docs/architecture/INTERFACE_SPEC.md` | Frozen contracts and signatures for every DAG layer | Binding; `<<FROZEN>>` signatures may not change without a DECISION_LOG entry |
| `docs/architecture/CORRELATION_CONTRACT.md` | Closure contract, per-role input manifests, validity-envelope format | Binding |
| `docs/architecture/SCHEMA_SPEC.md` | Serialization schemas for tuple, Result, dataset, validation case | Binding |
| `docs/validation/TEST_PLAN_V1.md` | Eleven test levels, acceptance gates, anti-pattern compliance tests | Binding test order and gate criteria |
| `docs/roadmap/IMPLEMENTATION_PLAN.md` | **Authoritative phase order (0–14) for all coding work** | Binding build sequence |
| `docs/architecture/ARCHITECTURE_FINAL_AUDIT.md` | Pre-implementation coherence audit; all findings resolved | Reference |
| `docs/decisions/DECISION_LOG.md` | Decisions 001–010; frozen for V1 | Binding governance record |

**Key authority statements:**
- `ARCHITECTURE_MASTER.md` is the single source of architectural truth. Where any other document conflicts with it, the master wins.
- `IMPLEMENTATION_PLAN.md` is the authority for phase order and build sequence. When any document says "Phase N," resolve it through the Rosetta table in `IMPLEMENTATION_PLAN.md §4.1`.
- `TEST_PLAN_V1.md` defines acceptance gates. A phase does not begin until the prior gate is green.
- `DECISION_LOG.md` is the governance record. Any change to a `<<FROZEN>>` signature requires a new entry here, not an inline edit.

---

## 3. Completed Milestones

| Milestone | Status | Commit |
|---|---|---|
| Architecture master (`ARCHITECTURE_MASTER.md`) | Done | `bacb323` |
| Interface specification (`INTERFACE_SPEC.md`) | Done | `bacb323` |
| Correlation contract (`CORRELATION_CONTRACT.md`) | Done | `bacb323` |
| Schema specification (`SCHEMA_SPEC.md`) | Done | `bacb323` |
| Implementation roadmap (`IMPLEMENTATION_PLAN.md`) | Done | `6318346` |
| Test plan (`TEST_PLAN_V1.md`) | Done | `6318346` |
| Final architecture audit (`ARCHITECTURE_FINAL_AUDIT.md`) | Done | `47acf01` |
| MAJOR-1 fix: phase-numbering Rosetta table in IMPLEMENTATION_PLAN | Done | `48024f1` |
| MAJOR-2 fix: Decision 010 recorded in DECISION_LOG | Done | `6f611d1` |
| GitHub repository initialized | Done | `dfa214d` |
| **Phase 0 — Repository Preparation and Tooling** | **Done** | `bc9c78d` |

---

## 4. Current Repository Structure

```
mpl-loop-sim/
├── docs/
│   ├── architecture/       # ARCHITECTURE_MASTER, INTERFACE_SPEC, CORRELATION_CONTRACT,
│   │                       # SCHEMA_SPEC, ARCHITECTURE_FINAL_AUDIT, ARCHITECTURE_REVIEW_LEGACY
│   ├── decisions/          # DECISION_LOG.md (Decisions 001–010)
│   ├── roadmap/            # IMPLEMENTATION_PLAN.md, PROJECT_STATUS.md (this file)
│   └── validation/         # TEST_PLAN_V1.md, VALIDATION_PLAN.md
├── legacy/                 # A0_SS_v3_Stable, PyP2PL, MPL_Simulator — read-only reference
├── papers/                 # Literature references
├── src/
│   └── mpl_sim/            # <<< ALL implementation code lives here
│       ├── __init__.py     # version = 0.1.0.dev0
│       ├── core/           # Phase 1: FluidIdentity, FluidState, Port, SystemState
│       ├── properties/     # Phase 2: PropertyBackend, CoolPropBackend — ONLY CoolProp importer
│       ├── geometry/       # Phase 4: PipeGeometry, PlateGeometry, ...
│       ├── discretization/ # Phase 4: Lumped, Segmented, MovingBoundary
│       ├── correlations/   # Phase 3: Correlation contract, roles, registry
│       ├── calibration/    # Phase 5: CalibrationMode, CalibrationFactor, CalibrationReport
│       ├── components/     # Phase 6+: Pipe, Pump, Accumulator, Evaporator, Condenser
│       ├── hx_models/      # Phase 11: HeatExchangerModel strategies
│       ├── network/        # Phase 7: Topology, validation, assembly
│       ├── solvers/        # Phase 8: FixedPoint, Newton, FD-Jacobian
│       ├── schema/         # Phase 9: ReproducibilityTuple, Result serialization
│       ├── results/        # Phase 9: Result object, ValidationInvariants
│       └── validation/     # Phase 12: Literature harness, comparison metrics
├── tests/
│   ├── unit/               # test_smoke.py (2 passing)
│   ├── property/           # Phase 2 tests (.gitkeep)
│   ├── correlation/        # Phase 3 tests (.gitkeep)
│   ├── geometry/           # Phase 4 tests (.gitkeep)
│   ├── calibration/        # Phase 5 tests (.gitkeep)
│   ├── component/          # Phase 6+ tests (.gitkeep)
│   ├── network/            # Phase 7 tests (.gitkeep)
│   ├── solver/             # Phase 8 tests (.gitkeep)
│   ├── result/             # Phase 9 tests (.gitkeep)
│   ├── schema/             # Phase 9 tests (.gitkeep)
│   ├── literature/         # Phase 12 tests (.gitkeep)
│   ├── regression/         # regression goldens (.gitkeep)
│   └── compliance/         # anti-pattern guard tests (.gitkeep)
├── examples/               # README.md placeholder; examples added Phase 12+
├── data/
│   ├── property_tables/    # README.md; PENDING-DATA — 29 CSVs missing
│   ├── validation/         # README.md; data to be lifted from legacy/ per phase
│   └── surrogates/         # README.md; Phase 13+
├── pyproject.toml          # mpl-sim, Python >=3.10, src layout, all deps
├── .gitignore
└── README.md
```

---

## 5. Current Active Phase

**Phase 1 — Core Data Model** (`src/mpl_sim/core/`)

Objective: implement the stored-vs-derived boundary as code. All seven objects below must be implemented and tested before Phase 2 begins. No physics, no backends, no correlations.

Objects to implement (all signatures in `INTERFACE_SPEC.md §3–§4`):

| Object | Contract location | Key invariant |
|---|---|---|
| `FluidIdentity` | INTERFACE_SPEC §3.1 | Discriminated union `PureFluid \| Mixture \| CustomFluid`; structural equality |
| `FluidState` | INTERFACE_SPEC §3.2 | Exactly `{P, h, identity}` — three fields, nothing else, ever |
| `Port` | INTERFACE_SPEC §4.1 | `{id, owner, role, peer}` — no values, immutable after assembly |
| `PortHandle` | INTERFACE_SPEC §4.2 | `{port, slot_P, slot_h, slot_mdot}` — maps port → SystemState indices |
| `SystemState` | INTERFACE_SPEC §4.3 | `{values: float[], layout: StateLayout}` — solver-owned, mutable only by solver |
| `StateLayout` | INTERFACE_SPEC §4.3 | `port_handle()`, `internal_handle()`, `names()` — ordered, introspectable |
| `InternalStateHandle` | INTERFACE_SPEC §4.4 | `{component, name, slot, slots?}` — fixed-count for Lumped/Segmented |

Phase 1 acceptance gate (`TEST_PLAN_V1.md §18.1` Gate 1 partial):
- `FluidState` holds exactly three fields; no derived attribute cacheable on it.
- `FluidIdentity` structural equality works.
- `Port` carries no value; is immutable after construction.
- `PortHandle` maps a port to three `SystemState` slots.
- `SystemState` round-trips index ↔ name.
- `StateLayout.names()` is ordered and enumerable.

---

## 6. Next Immediate Actions

Phase 0 is complete and committed. Proceed in this order:

1. **Verify environment is clean** before starting:
   ```
   git status          # should be clean
   pytest tests/       # should pass 2 tests
   ruff check src/ tests/
   black --check src/ tests/
   ```

2. **Start Phase 1 — FluidIdentity and FluidState** (write tests first):
   - Create `tests/unit/test_fluid_identity.py` and `tests/unit/test_fluid_state.py`.
   - Implement `src/mpl_sim/core/fluid_identity.py` and `src/mpl_sim/core/fluid_state.py`.
   - Assert `FluidState` has exactly three fields; no derived attribute; no `mdot`.

3. **Continue Phase 1 — Port, PortHandle, SystemState, StateLayout, InternalStateHandle**:
   - Implement in `src/mpl_sim/core/`.
   - Tests in `tests/unit/`.
   - Recommended split into two commits per IMPLEMENTATION_PLAN §22:
     - `core: add fluid identity, fluid state, and port primitives`
     - `core: add system state vector and handles`

4. **Do not implement PropertyBackend** until Phase 1 core primitives are complete and green.

5. **Do not implement any physics** — Phase 1 is value objects only.

---

## 7. Non-Negotiable Implementation Rules

These rules are operational forms of the frozen decisions. Violating any is a review failure.

| Rule | Source |
|---|---|
| Do not modify frozen architecture docs during coding | IMPLEMENTATION_PLAN §21-2 |
| Do not introduce new architecture concepts | ARCHITECTURE_MASTER §2, Principle 6 |
| Do not copy legacy code directly into `src/` | IMPLEMENTATION_PLAN §21-4 |
| Do not call CoolProp outside `properties/` | [F6]; anti-pattern MASTER §19-9 |
| Do not store derived properties (T, x, ρ, …) anywhere | [F3]; anti-pattern MASTER §19-4 |
| Do not put values on Port | [F10]; anti-pattern MASTER §19-13 |
| Do not make Solver depend on physics | [F1]; anti-pattern MASTER §19-5 |
| Do not put mesh (segment count) in Geometry | [F16]; anti-pattern MASTER §19-7 |
| Do not put accumulator law parameters in AccumulatorGeometry | [F9]; anti-pattern MASTER §19-8 |
| Do not weaken a test to make code pass | IMPLEMENTATION_PLAN §21-11 |
| Calibration must not be inside a correlation | [F5]; anti-pattern MASTER §19-3 |
| A correlation must not receive a Component or Geometry object | [F4]; anti-pattern MASTER §19-6 |
| Network must never know the Solver | [F1] |
| Components must never know their Network or neighbours | [F7]; anti-pattern MASTER §19-2 |
| `P_sys` must not be stored on the Accumulator | [F15], Decision 008 |
| ε-NTU/LMTD are HeatExchangerModel strategies, not Correlation roles | Decision 010 |

---

## 8. Current Known Blockers

None of these block Phase 1.

| Blocker | What it blocks | Resolution path |
|---|---|---|
| **29 property CSV files missing** from `legacy/` | `TabulatedPropertyBackend` numerical tests; `σ_e`/`ε_r` | Data recovery task; mark tests `PENDING-DATA`; does not block V1 CoolProp path |
| **Literature validation data must be lifted and pinned** | Literature test pass/fail (`tests/literature/`) | Transcription from `legacy/` into `data/validation/`; data exists, just needs lifting |
| **Per-correlation ValidityEnvelope bounds** | Each correlation's admissibility into the registry | Literature task per correlation; done when each correlation is authored in Phase 3+ |
| **Content-hash canonicalization rule** | Schema serialization determinism | Fixed at first serializer authoring in Phase 9; tests assert determinism, not algorithm |

---

## 9. Legacy Assets — Harvest Summary

Read from `legacy/` only. Never paste code directly into `src/`. Port equations one at a time behind the approved interface.

| Legacy project | What to harvest | Verdict | When |
|---|---|---|---|
| `A0_SS_v3_Stable` | HEM closures, mixture friction, `alpha_boiling`, `alpha_condensation`, `R*` concept, Fujii (2004) data | Adapt equations / Reuse data / Discard structure | Phase 5, 11, 12 |
| `PyP2PL` | Five boiling HTCs, MSH/Churchill ΔP, Kokate (2024) digitized data, sweep fixtures | Adapt correlations / Reuse data | Phase 3, 11, 12 |
| `MPL_Simulator` | `fluid_properties.py` (P,h FluidState + fallback chain), `A1_TwoPhProp.py` (table loader), `correlations.py`, `accumulator.py`, `condenser.py`, Newton residual shape | Adapt (primary harvest target) / Rewrite ownership leaks | Phase 1–2, 3, 10, 11, 8 |

---

## 10. Instructions for Future AI Agents

**Before any coding task, read in order:**

1. `docs/roadmap/PROJECT_STATUS.md` — this file (current state)
2. `docs/roadmap/IMPLEMENTATION_PLAN.md §5–§6` (or the section for the target phase)
3. `docs/validation/TEST_PLAN_V1.md` — tests and gates for the target phase
4. The relevant `INTERFACE_SPEC.md` section(s) for the layer being implemented

**Rules for every coding session:**

- Work only on the current phase. Do not implement layers above the current one.
- Read the frozen interface signatures from `INTERFACE_SPEC.md`. Implement them exactly — do not invent or simplify.
- Write tests first (test-driven). The layer below must be green before the layer above is built.
- Keep each commit to one coherent increment on one approved seam (IMPLEMENTATION_PLAN §21-5).
- Run `pytest`, `ruff check`, and `black --check` before reporting a task complete.
- Report: which files were created or modified; which commands were run; what the test results were.
- Never silently skip a failing test. A failing test means fixing the code, not loosening the assertion.
- If a required change would alter a `<<FROZEN>>` contract: stop, report the conflict, do not proceed without a `DECISION_LOG.md` entry.
- If uncertain whether a concept belongs in the architecture: check `ARCHITECTURE_MASTER.md §2` (the closed inventory). If the concept is not there, it does not exist in V1.

**Commit message convention** (from IMPLEMENTATION_PLAN §22):
```
<layer-prefix>: <short description>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```
Layer prefixes: `core:`, `properties:`, `correlations:`, `geometry:`, `discretization:`, `calibration:`, `components:`, `hx_models:`, `network:`, `solvers:`, `schema:`, `results:`, `validation:`, `chore:`, `docs:`.

---

## 11. Last Updated

| Field | Value |
|---|---|
| **Date** | 2026-06-12 |
| **Commit at time of writing** | `bc9c78d` (Phase 0 complete) |
| **Updated by** | AI assistant (Claude Sonnet 4.6) |

---

*This document must be updated at the start of each new phase and whenever a milestone is completed. It is not a source of truth for architecture — for that, always go to `ARCHITECTURE_MASTER.md`.*
