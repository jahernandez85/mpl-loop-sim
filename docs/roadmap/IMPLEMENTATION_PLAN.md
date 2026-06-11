# IMPLEMENTATION_PLAN.md

**The practical implementation roadmap for the first steady-state version (V1) of the MPL simulation framework.**

Status: **implementation roadmap (pre-code).** This document translates the frozen architecture and the four interface documents into a concrete, phased development sequence. It is downstream of, and subordinate to, every document it sequences and **never reopens a frozen decision**.

Source documents (all frozen, all binding):
- `ARCHITECTURE_MASTER.md` — the single source of architectural truth; decisions `[F1]`–`[F18]`.
- `INTERFACE_SPEC.md` — the five frozen contracts + `HeatExchangerModel`, `PipePath`, accumulator law/geometry split, five-part Scenario.
- `CORRELATION_CONTRACT.md` — closure contract, per-role input manifests, validity-envelope format, ML-closure admissibility.
- `SCHEMA_SPEC.md` — serialized bytes, `schema_version`, tuple/result/dataset/validation-case schemas.
- `TEST_PLAN_V1.md` — the eleven test levels, the vertical slice, the anti-pattern compliance gates.
- `DECISION_LOG.md` — Decisions 001–009.
- `ARCHITECTURE_REVIEW_LEGACY.md` — the four-verdict legacy audit and harvest order.

---

# 1. Scope and Status

This is the **implementation roadmap, not the architecture.** It answers a single question the architecture documents deliberately do not: *in what order is the code written, and what must be true before each step is allowed to begin the next?*

- **The architecture is frozen.** Decisions `[F1]`–`[F18]` and Decisions 001–009 are immutable for V1. This plan **conforms** to them; it does not argue, refine, or extend them. Where this plan and a frozen document appear to disagree, the frozen document wins and this plan is wrong.
- **The interfaces are frozen.** Every signature marked `<<FROZEN>>` in `INTERFACE_SPEC.md` / `CORRELATION_CONTRACT.md` / `SCHEMA_SPEC.md` is implemented as written. A change to one is a redesign requiring a `DECISION_LOG.md` entry, not an implementation choice.
- **This plan is mutable.** Phase ordering, intermediate deliverables, and tooling choices below may be adjusted as implementation reveals friction — *provided no adjustment violates a frozen contract or skips an acceptance gate.*
- **No code is written by this document.** It creates no implementation files, modifies no existing files. It is a sequencing and gating instrument only.

The implementation target of V1 is exactly the scope of `TEST_PLAN_V1.md` §1.1: a steady-state loop with FluidState + PropertyBackend(CoolProp), the correlation registry + calibration seam, the first components (Pipe, Pump, Accumulator), then Evaporator, Condenser, Network, and the steady Solver, validated against at least one literature case (data-permitting).

---

# 2. Implementation Principles

These bind every phase. They are the operational discipline that keeps the build conformant.

1. **Test-first implementation.** Each DAG layer's tests (`TEST_PLAN_V1.md`) pass before the layer above it is built. The harvest order *is* the test order (`TEST_PLAN_V1.md` §2.2): no layer is implemented against an untested layer below it. *A result without a residual is not a result* — invariants are test subjects from commit one.
2. **Vertical slice before full components.** The smallest end-to-end loop (`ARCHITECTURE_MASTER.md` §18) is built and green **before** any expensive component (Evaporator, Condenser). Interface friction is surfaced on trivial physics where failures are unambiguous.
3. **No architecture drift.** No phase introduces a concept absent from the closed inventory (`ARCHITECTURE_MASTER.md` §2). No abstraction is added unless two concrete cases already demand it (Principle 6). If a phase seems to need a new primitive, the phase is mis-scoped — stop and escalate, do not invent.
4. **Small commits.** Each commit lands one coherent, tested increment on an approved seam (§22). A commit that touches multiple layers or mixes a port with a new feature is too big.
5. **No legacy copy-paste.** `src/` is built from the architecture, not pasted from `legacy/`. Legacy code is consulted as a *reference* and ported equation-by-equation behind the approved interface, with globals/hacks stripped and a validity envelope added (`ARCHITECTURE_REVIEW_LEGACY.md` §0, §7.2).
6. **No direct CoolProp calls outside `properties/`.** Every property flows through `FluidState` → `PropertyBackend`. A `CoolProp` import anywhere outside `properties/` is a review failure (`[F6]`, anti-pattern §9 of MASTER §19).
7. **No state on Ports.** A Port is connectivity only (id, owner, role, peer). No `P`/`h`/`ṁ`/`FluidState`/derived property is ever stored on it (`[F10]`, `INTERFACE_SPEC.md` §4.1).
8. **No derived properties stored.** Only `(P, h, ṁ)` per port-node and named internal states are stored, in `SystemState` (`[F3]`). `T, x, ρ, μ, k, σ, c_p, void, phase` and all closure outputs (HTC, ΔP, ε) are derived on demand, never cached on any object, never serialized as primary state.

Two supporting rules, equally non-negotiable:

9. **Correlations are pure.** Stateless, no caching, no globals, no `hasattr` self-introspection, no hard-coded fluid constants. Calibration is applied *outside* the correlation, by the component, at the documented seam.
10. **The Solver depends on nothing below it, and nothing depends on the Solver.** Physics never references numerics; numerics is never referenced. The contribution contract is residual/derivative only.

---

# 3. Proposed Package Structure

A `src/`-layout Python package (`SCHEMA_SPEC.md` and `INTERFACE_SPEC.md` are language-neutral; the implementation is Python). The package tree mirrors the DAG layers so that the **import direction enforces the dependency direction** — a module may import only from modules at or below its layer. A linter/import-rule guard makes forbidden directions unrepresentable where possible.

```
src/
  mpl_sim/
    core/            # Layer 1-2-7 primitives: FluidIdentity, FluidState, Port, PortHandle,
                     #   SystemState, StateLayout, InternalStateHandle
    properties/      # Layer 0-1: PropertyBackend interface, CoolPropBackend, registry,
                     #   PropertyResult, capability flags. THE ONLY place CoolProp is imported.
    geometry/        # Layer 0: PipeGeometry+PipePath, PlateGeometry, MicrochannelGeometry,
                     #   AccumulatorGeometry — immutable flat typed family
    discretization/  # Layer 5 (numeric config): Lumped/Segmented/MovingBoundary; cell metrics
    correlations/    # Layer 3: Correlation contract, CorrelationInput role types,
                     #   CorrelationOutput, ValidityVerdict/Envelope, CorrelationRegistry, closures
    calibration/     # Layer 4: CalibrationMode/Factor/Scope/Report, resolution, application seam
    components/      # Layer 5: Component contract, Pipe, Pump, Accumulator, Evaporator,
                     #   Condenser, Valve, Junction, Reservoir + the internal 1D gradient kernel
    hx_models/       # Layer 5-internal strategy: HeatExchangerModel interface, EpsilonNTU,
                     #   LMTD, SegmentedMarch, (MovingBoundary seam), HeatExchangerModelRegistry
    network/         # Layer 6: ComponentId/PortId, connections, Junction wiring, branch groups,
                     #   topology validation, inventory accountant, SystemState assembly
    solvers/         # Layer 7: SystemState assembly driver, fixed-point + Newton, residual
                     #   assembly, FD Jacobian, convergence metadata
    schema/          # serialization: ReproducibilityTuple, Result, dataset, validation-case;
                     #   schema_version, $ref/@hash, round-trip (de)serializers
    results/         # Result object, ValidationInvariants, closure-metadata aggregation,
                     #   derived-profile reconstruction (never stored)
    validation/      # literature-case harness: Kokate/Li/Fujii fixtures, MAE, comparison metrics
tests/
  unit/  property/  correlation/  geometry/  calibration/  component/
  network/  solver/  result/  schema/  literature/  regression/  compliance/
data/
  property_tables/   # the 29 CSVs (PENDING-DATA) when recovered; content-hash pinned
docs/                # the frozen architecture + interface + this roadmap (unchanged)
examples/            # worked Scenario/tuple fixtures (Phase 12+ from PyP2PL sweeps)
```

What belongs in each — and what must **not**:

| Package | Belongs | Must NOT contain |
|---|---|---|
| `core/` | the stored-state primitives; the Port (connectivity only); the SystemState vector + handles | any property formula; any physics; any CoolProp import |
| `properties/` | `PropertyBackend`, `CoolPropBackend`, registry, capability logic | geometry, slots, topology; correlation closures (Layer 3 lives in `correlations/`) |
| `geometry/` | immutable typed scalar value objects + dimensional accessors | a mesh/segment count (`[F16]`); operating state; gravity; any `Nu`/`ΔP` computation |
| `discretization/` | mode + resolution + `cell_metrics` derived from geometry | storage of state values; assumptions made by the Solver |
| `correlations/` | pure closures, role inputs, verdicts, envelopes, registry | calibration factors; `Component`/`Geometry` objects; CoolProp; ε-NTU/LMTD (those are `hx_models/`) |
| `calibration/` | value objects + resolution + the application helper | physics; balances; any factor baked into a correlation |
| `components/` | local physics, contribution contract, the internal gradient kernel | the Network/Solver/neighbours; direct CoolProp; cached derived state |
| `hx_models/` | whole-exchanger solution strategies that *consume* correlations | port/network/solver access; registry self-resolution |
| `network/` | topology, validation, branch structure, inventory, assembly into SystemState | the Solver; correlation/geometry/FluidState internals |
| `solvers/` | assembly, iteration, Jacobian, invariants, convergence metadata | any physics/correlation/geometry/property formula |
| `schema/` | serialized shapes + versioning + round-trip | derived properties as primary state; hidden defaults |
| `results/` | minimal stored state + reports + on-demand profile reconstruction | stored `T/ρ/x` profiles |
| `validation/` | literature fixtures + comparison metrics | any change to physics to make a case pass |

---

# 4. Development Phases Overview

Fifteen phases, Phase 0–14. Phases 0–9 build and prove the V1 vertical slice and its full component set; Phases 10–11 complete the component catalogue; Phases 12–14 add validation, DOE readiness, and release. Every phase carries: **objective**, **modules affected**, **deliverables**, **tests required**, **acceptance criteria**, **risks**, **legacy assets to consult**.

| Phase | Title | Gate it opens |
|---|---|---|
| 0 | Repository preparation and tooling | a runnable, tested, linted package skeleton |
| 1 | Core data model | the stored-vs-derived boundary exists and is tested |
| 2 | PropertyBackend (CoolProp) | every derived property is reachable through one seam |
| 3 | Correlation contract and registry | the research seam is open; first friction closure works |
| 4 | Geometry and discretization | components have immutable geometry + a fidelity axis |
| 5 | Calibration | the conservation firewall is enforceable |
| 6 | First component: Pipe | the contribution contract is proven on one component |
| 7 | Network and SystemState assembly | a topology can be validated and assembled |
| 8 | First steady solver | **the vertical slice is green end-to-end** |
| 9 | Result and schema serialization | runs are reproducible and archivable |
| 10 | Pump and Accumulator | the loop can be pressure-referenced and driven |
| 11 | HeatExchangerModel, Evaporator, Condenser | the full V1 component set exists |
| 12 | Validation harness and literature cases | the framework is checked against published data |
| 13 | DOE / surrogate readiness | datasets can be generated over scenarios |
| 14 | Documentation and release | V1 is tagged and documented |

The phase order **is** the harvest order of `ARCHITECTURE_REVIEW_LEGACY.md` §8 and the test order of `TEST_PLAN_V1.md` §2.2. The acceptance gate of each phase is the precondition of the next; a phase may not begin until its predecessor's gate is green.

## 4.1 Two phase-numbering systems — do not confuse them

There are **two distinct phase-numbering systems** in the documentation, and they must never be conflated:

- **V1 Build Phases (this document):** the fine-grained build sequence **numbered 0–14** in §4 above. This is the **authoritative implementation sequence**. For all actual coding work, "Phase N" means the V1 Build Phase N of `IMPLEMENTATION_PLAN.md`.
- **Long-Term Roadmap Milestones (coarser references elsewhere):** older, coarse milestone labels used in the architecture, correlation, schema, and test documents (`ARCHITECTURE_MASTER.md`, `CORRELATION_CONTRACT.md`, `SCHEMA_SPEC.md`, `TEST_PLAN_V1.md`), where **"Phase 5" means the DOE/surrogate research milestone** and **"Phase 6" means the dynamic-solver / MovingBoundary / dynamics milestone**.

The same token (e.g. "Phase 5", "Phase 6") therefore denotes **different work** in the two systems. **When `IMPLEMENTATION_PLAN.md` says "Phase 5" it means "V1 Build Phase 5 — Calibration", *not* the long-term DOE/surrogate milestone.** An implementation agent that cross-references documents must resolve every "Phase N" reference through the Rosetta table below before acting on it.

### Phase Rosetta table

The authoritative V1 Build Phases (0–14), and how the older/coarser Long-Term Roadmap references map onto them:

| V1 Build Phase | Title |
|---|---|
| **0** | Repository preparation and tooling |
| **1** | Core data model |
| **2** | PropertyBackend |
| **3** | Correlation contract and registry |
| **4** | Geometry and discretization |
| **5** | **Calibration** |
| **6** | Pipe component |
| **7** | Network and assembly |
| **8** | First steady solver |
| **9** | Result and schema serialization |
| **10** | Pump and Accumulator |
| **11** | HeatExchangerModel, Evaporator and Condenser |
| **12** | Validation harness and literature cases |
| **13** | DOE/surrogate readiness |
| **14** | Documentation and release |

Relationship to the older/coarser **Long-Term Roadmap** references used elsewhere:

| Long-Term Roadmap Milestone | Meaning | Realized in V1 Build Phase(s) |
|---|---|---|
| **Long-Term Roadmap Phase 5** | DOE / surrogate research milestone | V1 Build Phase 13 (DOE/surrogate readiness); schema/admissibility only in V1 |
| **Long-Term Roadmap Phase 6** | Dynamic solver / MovingBoundary / dynamics milestone | Post-V1; seams declared across the V1 Build Phases (named-but-frozen internal states, declarable `MovingBoundary`) |

> **Note.** Wherever this document writes "Phase N", it means **V1 Build Phase N** (the 0–14 column above). The Long-Term Roadmap "Phase 5 = DOE/surrogate" and "Phase 6 = dynamics" labels are *not* the same numbers and appear only in the coarser architecture/test/schema/correlation references. In particular, **`IMPLEMENTATION_PLAN.md` "Phase 5" = Calibration**, never DOE/surrogate.

---

# 5. Phase 0 — Repository Preparation and Tooling

**Objective.** Stand up a `src/`-layout Python package that is runnable, importable, testable, linted, and version-controlled, with the import-direction guard in place — *before any physics is written.* Realistic for a solo researcher: minimal, not ceremonial.

**Modules affected.** None of the physics packages yet — only project-root scaffolding and empty package `__init__` markers for the §3 tree.

**Deliverables.**
- `pyproject.toml` — package metadata, dependencies (`coolprop`, `numpy`, `scipy`, `pyyaml`/`ruamel`; dev: `pytest`, `ruff`/`flake8`, `black`, `mypy`), and the `src/` layout declaration (`tool.setuptools.packages` / equivalent). `project_version` (`SCHEMA_SPEC.md` §4) originates here.
- `src/mpl_sim/` tree per §3, each package a real importable namespace (no `sys.path` hacks — the legacy `pythonpath=["mpl"]` anti-pattern is forbidden, `ARCHITECTURE_REVIEW_LEGACY.md` §5.2).
- `tests/` tree per §3 with `pytest` discovery configured.
- Formatting/linting config (`black` + `ruff`), and an **import-rule guard** (e.g. `ruff`/`import-linter` contract) encoding the DAG: `core` may not import `solvers`; nothing may import `solvers`; only `properties` may import `coolprop`; `correlations` may not import `components`/`network`/`solvers`.
- Test runner config (`pytest`, optional `pytest-cov`).
- A CI placeholder (`.github/workflows/ci.yml` or equivalent) that runs lint + tests; it may start as a single job.
- Optional `notebooks/` directory, declared out of the import graph (notebooks consume the package, never the reverse).
- Git workflow note: small commits on feature branches off `main`, commit message convention (§22), `main` protected.

**Tests required.** A trivial smoke test (`import mpl_sim` succeeds); the import-rule guard passes on the empty tree; CI runs green.

**Acceptance criteria.** `pip install -e .` works; `pytest` collects and runs (zero or trivial tests); lint and the import guard are green in CI; no `sys.path` manipulation anywhere.

**Risks.** Over-tooling for a solo project (mitigate: keep CI to lint+test; defer release automation to Phase 14). Setting the import guard too loose to matter (mitigate: encode at least the four forbidden directions of `ARCHITECTURE_MASTER.md` §3 now).

**Legacy assets to consult.** `MPL_Simulator/pyproject.toml` as a *negative* example (`pythonpath=["mpl"]`, flat imports — do **not** reproduce). Nothing is harvested in Phase 0.

---

# 6. Phase 1 — Core Data Model

**Objective.** Implement the stored-vs-derived boundary as code: the Layer 0–2 value objects and the Layer 7 state vector, with **nothing derived stored anywhere.** This is the first of the five frozen interfaces realized.

**Modules affected.** `core/`.

**Deliverables (all `<<FROZEN>>` signatures, `INTERFACE_SPEC.md` §3, §4).**
- **`FluidIdentity`** — discriminated union `PureFluid | Mixture | CustomFluid`; structural equality; carries no properties (`INTERFACE_SPEC.md` §3.1). V1 populates `PureFluid`; `Mixture`/`CustomFluid` shapes exist but are unused.
- **`FluidState`** — pure value object `{P, h, identity}`, exactly three fields, immutable, no backend reference, no `ṁ`, no cached derived property (`INTERFACE_SPEC.md` §3.2). Derived access deferred to Phase 2 (needs a backend); the *object* exists now.
- **`Port`** — connectivity only `{id, owner, role, peer}`, immutable after assembly, holds no values (`INTERFACE_SPEC.md` §4.1).
- **`PortHandle`** — `{port, slot_P, slot_h, slot_mdot}`; the map from a Port to `SystemState` indices (`INTERFACE_SPEC.md` §4.2).
- **`SystemState`** — `{values: float[], layout: StateLayout}`; flat, ordered, mutable only by its owner (`INTERFACE_SPEC.md` §4.3).
- **`StateLayout`** — `port_handle`, `internal_handle`, ordered introspectable `names()`.
- **`InternalStateHandle`** — `{component, name, slot, slots?}`; fixed-count now, variable-count (`slots`) shape declared for MovingBoundary.

**Tests required (`TEST_PLAN_V1.md` §5.1, §7-handles, §11.1).**
- `FluidState` holds exactly three fields; no derived attribute cacheable on it; no `ṁ` field.
- `FluidIdentity` structural equality (`PureFluid("R134a") == PureFluid("R134a")`).
- `Port` carries no value/`FluidState`/derived property; is immutable after construction.
- `PortHandle` maps a port to three `SystemState` slots; `SystemState` stores only `(P,h,ṁ)` + named internal states; `StateLayout.names()` is ordered and enumerable.

**Acceptance criteria.** The stored-vs-derived boundary is enforced by the types: there is no code path that stores `T`/`ρ`/`x` on `FluidState` or any value on `Port`. `SystemState` round-trips index↔name. The introspectable ordered layout exists (the precondition for the future linearisation seam, `[F18]`).

**Risks.** Premature ergonomic wrapper on `FluidState` leaking a backend into the hot path (mitigate: defer the optional `state.T` wrapper to Phase 2 and mark it user/analysis-only). Adding an unfrozen field to `Port` for convenience (mitigate: compliance test that `Port` has exactly the four fields).

**Legacy assets to consult.** `MPL_Simulator/mpl/fluid_properties.py` `FluidState.from_Ph` constructor *shape* (P,h-anchored) — **Adapt the idea, not the eager `_compute()`** (`ARCHITECTURE_REVIEW_LEGACY.md` §5.2). `PyP2PL/.../node.py` derived-on-demand pattern as the *correct ownership reference* (§4.1). The retired `PortState`/`FlowState` names are the anti-pattern this phase exists to avoid.

---

# 7. Phase 2 — PropertyBackend

**Objective.** Make every derived thermodynamic property reachable through exactly one seam, with CoolProp as the default backend, vector-first, capability-flagged, and never extrapolating by stealth.

**Modules affected.** `properties/` (only place CoolProp is imported), and the optional ergonomic `FluidState` wrapper in `core/` that closes over a backend (user/analysis code only).

**Deliverables (`INTERFACE_SPEC.md` §3.3–§3.4, `[F6] [F13]`, Decision 006).**
- **`PropertyBackend`** interface — `query(prop, P[], h[], identity) → PropertyResult`; `query_derivative(...)` behind a `provides(DERIVATIVES)` flag; `provides(cap)`; `valid_range(identity)`.
- **`PropertyResult`** — `{value: float[], status: (OK|UNAVAILABLE|OUT_OF_RANGE)[], warning?}`. A status-bearing return, never a bare `float[]`.
- **`CoolPropBackend`** — the default; implements the full derived set CoolProp supports (`T, T_sat, x, ρ, μ, k, σ, c_p, phase, h_f, h_g, h_fg`) and its first derivatives; `provides(SIGMA_E) = false`.
- **`PropertyBackendRegistry`** — startup-time, name-keyed, distinct from the correlation registry; `instance_for(identity, name)` returns one shared instance per identity per run.
- **Capability flags** — `SIGMA_E`, `EPS_R`, `DERIVATIVES`, named properties.

**Mentions / explicit scope notes.**
- **`TabulatedPropertyBackend` is pending data** (`ARCHITECTURE_MASTER.md` §17, `ARCHITECTURE_REVIEW_LEGACY.md` §6.3). Its *interface conformance* may be stubbed and tested now; its *numerical* tests are `PENDING-DATA` until the 29 CSVs are recovered, schema-verified, versioned, and content-hash pinned. It is the **only** source of `σ_e`/`ε_r`.
- **No direct CoolProp calls outside `properties/`.** Enforced by the import guard (§5).

**Tests required (`TEST_PLAN_V1.md` §5.2–§5.7).**
- Reference agreement: `query` matches CoolProp reference values for R-134a and Acetone on a `(P,h)` grid.
- Vector-first: length-matched `value[]`/`status[]`; scalar == length-1; vector == element-wise scalar.
- Capability gate: `provides(SIGMA_E)` false for CoolProp; unsupported property → `UNAVAILABLE` + warning, never a guess.
- Out-of-range: out-of-envelope `(P,h)` → `OUT_OF_RANGE` + `NaN` + warning; never a clamped edge value.
- Purity: pure function of `(P,h,identity)`; one shared instance per identity; no import-time side effect.
- `TabulatedPropertyBackend`: interface conformance only; numerical tests written-and-skipped with a `PENDING-DATA` marker.

**Acceptance criteria.** `FluidState` derived access works end-to-end through the backend; the `x = (h − h_f)/h_fg` continuity sweep across the dome shows no discontinuity and no region-variable switch; the no-extrapolation contract holds; nothing outside `properties/` imports CoolProp.

**Risks.** Eager/expensive property construction in the hot path (mitigate: vector-first from day one; internal cache only, invisible to callers — the explicit warning of `ARCHITECTURE_REVIEW_LEGACY.md` §5.2). Property correlations (Letsou-Stiel/Latini/Brock-Bird) leaking into `FluidState` instead of an `EmpiricalCorrelationBackend` (mitigate: those are a *backend*, Layer 1, deferred to a later catalogue addition, not a `FluidState` method).

**Legacy assets to consult.** `MPL_Simulator/mpl/fluid_properties.py` — **Adapt** the CoolProp→empirical→table *fallback priority logic* and the per-property *source-tracking* idea, split into backend implementations (the highest-value property asset). `MPL_Simulator/mpl/A1_TwoPhProp.py` — the future `TabulatedPropertyBackend` (loader reusable; tables missing). `MPL_Simulator/tests/test_fluid_properties.py` — regression oracles.

---

# 8. Phase 3 — Correlation Contract and Registry

**Objective.** Open the core research seam: a stateless, role-typed, verdict-bearing closure contract and a name-keyed registry, with the **first friction correlation** registered and the **validity-envelope** machinery working.

**Modules affected.** `correlations/`.

**Deliverables (`INTERFACE_SPEC.md` §7, `CORRELATION_CONTRACT.md` §1–§8, `[F4] [F11]`, Decision 005).**
- **`Correlation`** interface — `role()`, `evaluate(CorrelationInput) → CorrelationOutput`; stateless, pure.
- **`CorrelationInput` role types** — the frozen role set: `SinglePhaseDPInput`, `TwoPhaseDPInput`, `HTCInput`, `VoidFractionInput`, `FlowRegimeInput`, `VolumePressureLawInput`, (`CriticalHeatFluxInput` declared `<<SEAM>>`). Field manifests per `CORRELATION_CONTRACT.md` §4.4. One input type per *role*, not per formula.
- **`CorrelationOutput`** — `{value: float[], verdict: ValidityVerdict, metadata: ClosureMetadata}`. Never a bare number.
- **`ValidityEnvelope`** — `{fluid_families, bounds, regime_restriction?, source, notes?}` with the frozen `Bound`/`BoundedQuantity`/`FluidFamilySpec` shapes (`CORRELATION_CONTRACT.md` §6.2).
- **`ValidityVerdict`** — `{status: (IN_ENVELOPE|EXTRAPOLATED|OUT_OF_RANGE), envelope, violated: Bound[], detail?}` with the three-state severity semantics (`CORRELATION_CONTRACT.md` §6.4).
- **`ClosureMetadata`** — `{name, version, source}` (the reproducibility anchor).
- **`CorrelationRegistry`** — startup-time `register`/`resolve`/`by_role`; rejects a closure registered without an envelope; **PropertyBackend is never in it**.
- **First friction correlation** — one `SINGLE_PHASE_DP` closure (Churchill recommended) returning a **gradient** `(dP/dx)`, never a total, with a declared envelope.

**Legacy migration discussion (sequenced, not all now).**
- **MPL correlations first.** `MPL_Simulator/mpl/correlations.py` is the richest, most architecture-aligned set (Protocol + registry already) — **Adapt** Churchill/Blassius/MSH/Kim-Mudawar/Shah/Yan/Dittus-Boelter/Gnielinski, tightening the signature to `evaluate(CorrelationInput) → (value, verdict)` and adding envelopes. The single highest-yield port. Churchill (single-phase ΔP) lands in this phase; the rest land as the components that consume them are built (Phases 6, 11).
- **PyP2PL boiling correlations later.** The five boiling HTCs (Shah, Chen, Bennett-Chen, Gungor-Winterton, Kandlikar-Balasubramanian) are **Adapt**-ed in Phase 11 (evaporator), with `_fluid_name` globals, `hasattr` introspection, and hard-coded `M = 102.0` removed — the fluid constant arriving through `FluidState`/inputs (`CORRELATION_CONTRACT.md` §11.3).
- **A0 equations later.** `alpha_boiling` (nucleate+convective ΔT fixed-point), `alpha_condensation`, and the mixture friction factor are **Adapt**-ed from their global-array housing in Phase 11.
- **Acceleration/gravity gradient helpers** (MPL `acceleration_pressure_gradient`/`gravity_pressure_gradient`) are **Component kernel terms, not registry correlations** — a compliance test asserts they are *not* registered (`CORRELATION_CONTRACT.md` §11.2).

**Tests required (`TEST_PLAN_V1.md` §3.3, §7.1–§7.9, §7.10).**
- Statelessness (equal inputs → equal outputs; no instance/global state).
- Role-typed input (correct input type; never a `Geometry`/`Component`; meaningful absent optionals).
- Output shape (always `{value[], verdict, metadata}`; vector-first; gradient not total).
- ValidityVerdict (always present; `violated` names specific bounds; in/extrapolated/out states).
- Envelope: a closure registered without an envelope is **rejected**.
- No hidden calibration (raw physics under `NONE`).
- Churchill migration test: matches its legacy output for a reference input.

**Acceptance criteria.** The first friction closure resolves by name, evaluates to a gradient + `IN_ENVELOPE` verdict for an in-range input, and `EXTRAPOLATED`/`OUT_OF_RANGE` correctly out of range. The registry rejects envelope-less closures. No correlation imports CoolProp directly or receives a component/geometry object.

**Risks.** Over-porting the whole MPL catalogue before the contract is proven on one closure (mitigate: one closure this phase; the rest follow consuming components). Bundling gravity/acceleration into a ΔP closure (mitigate: §7.9 test). Reintroducing a discontinuity at an envelope edge that the solver trips on (mitigate: §6.5 continuity caution — envelope checking *reports*, never *branches*).

**Legacy assets to consult.** `MPL_Simulator/mpl/correlations.py` (Adapt — Churchill now). `MPL_Simulator/tests/test_correlations.py` (regression oracles). `ARCHITECTURE_REVIEW_LEGACY.md` §5.3 (the violations to strip).

---

# 9. Phase 4 — Geometry and Discretization

**Objective.** Give components an immutable, flat, typed geometry family that supplies scalars (never physics) and a fidelity axis that fixes internal-state count derived from — never stored in — geometry.

**Modules affected.** `geometry/`, `discretization/`.

**Deliverables.**
- **`PipeGeometry`** `{L, D_h, A, roughness, trajectory: PipePath}` (`INTERFACE_SPEC.md` §5.1).
- **`PipePath` / `StraightSegment`** — v1 default `StraightSegment{length, delta_z, inclination}`; `PipePath.derived() → {L_total, dz_dx_profile, sum_minor_K}`. `MultiSegmentPath`/`BendSegment`/`FittingSegment` declared `<<SEAM>>`, **not implemented in V1**.
- **`PlateGeometry`** `{N_plates, chevron_angle, plate_spacing, port_dims, A_per_plate, sink_side?}`.
- **`MicrochannelGeometry`** `{N_channels, D_h_channel, fin_geometry, A_heated, wall_mass, wall_material}` — exposes wall mass/material for the frozen dynamic wall-capacitance state.
- **`AccumulatorGeometry`** `{V_total, containment, thermal?}` — **containment only; no law parameters** (`INTERFACE_SPEC.md` §5.4).
- **`LumpedDiscretization {}`** — one control volume; v1 default.
- **`SegmentedDiscretization {N}`** — N control volumes; `cell_metrics` derives `L_cell = L/N` from geometry.
- **`MovingBoundaryDiscretization {max_zones}`** — declared `<<SEAM>>`; `current_state_count`/`events` shaped, not exercised in V1.
- The `Discretization` interface: `mode()`, `declared_state_count(geometry)`, `cell_metrics(geometry)`.

**Tests required (`TEST_PLAN_V1.md` §6).**
- Immutability of every geometry type; safe sharing by reference.
- `PipePath.derived()` returns the three derived scalars; `StraightSegment` reproduces a single-`Δz` run; `dz/dx` integrates to `delta_z`.
- No geometry computes `Nu`/`ΔP`; `AccumulatorGeometry` carries no `V_gas_charge`/spring/bellows/polytropic field.
- No mesh in geometry; same geometry object serves a lumped and a segmented run.
- `LumpedDiscretization` → one cell; `SegmentedDiscretization{N}` → N cells with `L_cell = L/N`.
- `MovingBoundaryDiscretization` is declarable and serializes; V1 either rejects it with a clear message or falls back to Lumped/Segmented — never silently mis-sized.

**Acceptance criteria.** Geometry is immutable and physics-free; the fidelity switch `Lumped ↔ Segmented` touches no geometry field; the MovingBoundary seam is declared and inert.

**Risks.** Over-generalizing `PipePath` in V1 (mitigate: only `StraightSegment` is built; over-generalizing is itself an anti-pattern, `TEST_PLAN_V1.md` §6.3). A base `Geometry` growing a shared field (mitigate: flat-family compliance test; any marker is field-less). Law parameters creeping into `AccumulatorGeometry` (mitigate: §6.4/§9.6 tests).

**Legacy assets to consult.** Geometry is **Rewrite from architecture** — legacy geometry was embedded in components. Consult `MPL_Simulator/mpl` component geometry *fields* as a checklist of what scalars correlations need, not as code.

---

# 10. Phase 5 — Calibration

**Objective.** Implement the transparent calibration seam and its conservation firewall: every factor named, neutral by default, applied at one component-owned seam, always reported, never able to mask an invariant violation.

**Modules affected.** `calibration/` (value objects + resolution); the *application* helper used by `components/` (built here, exercised from Phase 6).

**Deliverables (`INTERFACE_SPEC.md` §9, `CORRELATION_CONTRACT.md` §7, `[F5] [F14]`).**
- **`CalibrationMode`** — `NONE | TARGET`. No `DATASET_FIT`.
- **`CalibrationFactor`** — `{target: (FRICTION_GRADIENT|HTC|UA), value, mode, seam: SeamLocation}`.
- **`CalibrationScope`** — `SLOT | COMPONENT | GLOBAL`.
- **`CalibrationReport`** — `{factors: CalibrationFactor[], mode}`; present even under `NONE` (empty factors).
- **Resolution** — `resolve(slot, component) → CalibrationFactor` with order **slot → component → global → neutral**.
- **Application seam** — the helper a Component calls to scale a *closure output* (friction gradient / HTC / UA) after the correlation returns, before folding into a balance. Gravity and acceleration are **never** scaled; balances are **never** scaled.

**Tests required (`TEST_PLAN_V1.md` §8).**
- `NONE`: all factors 1.0; output == raw; report present with empty factors; Result flagged `PREDICTIVE`.
- `TARGET`: non-neutral factor scales at the seam; Result flagged `CALIBRATED`; never compared as-equal to a `PREDICTIVE` run.
- Resolution order slot → component → global → neutral; the *resolved, applied* factor is reported.
- `R*` scales the friction gradient only; gravity/acceleration unchanged; a factor targeting gravity/balance/void/regime/law is rejected as malformed.
- HTC/UA multipliers scale the coefficient/conductance, never a balance.
- **Conservation firewall (the central test):** a deliberately wrong `TARGET` calibration makes the un-calibrated invariants *worse*, never falsely passing.

**Acceptance criteria.** Calibration is a value object applied outside correlations; the firewall holds (invariants computed from un-calibrated conservation); reporting is mandatory and complete.

**Risks.** A factor leaking into a correlation formula (mitigate: §7.7 + §8 tests). Calibration scaling a balance (mitigate: the firewall test). The firewall test cannot fully run until invariants exist (Phase 8/9) — *shape* it here, *activate* it at Phase 9.

**Legacy assets to consult.** `A0_SS_v3_Stable` `R*` per-region concept — **Adapt** the concept (independent rediscovery of the firewall), **Rewrite** the bisection-on-globals mechanism (`ARCHITECTURE_REVIEW_LEGACY.md` §3.3, §3.6).

---

# 11. Phase 6 — Pipe Component

**Objective.** Prove the frozen contribution contract on the simplest real component, with the internal 1D gradient kernel that all 1D passages share, in `Lumped` mode first.

**Modules affected.** `components/` (the `Component` contract base + `Pipe` + the internal gradient kernel).

**Deliverables (`INTERFACE_SPEC.md` §11, `[F8-internal-state] [F14] [F15]`).**
- **Component contract base** — `ports()`, `geometry()`, `discretization()`, `correlation_slots()`, `calibration_slots()`, `scenario_bindings()`, `internal_state_names()`, `contribute(trial, ctx) → ComponentContribution`, `result_contribution(...)`. The signature is frozen and identical across modes and steady→dynamic.
- **`Pipe` component** — `PipeGeometry`, `Lumped` default; slots for single-phase ΔP, two-phase ΔP, void fraction; optional wall-heat Scenario binding; per-segment mass/momentum (and wall T if heated) internal states named with zero derivative.
- **1D gradient kernel (internal, not public)** — per cell: `(dP/dx)_friction` from the slot correlation (the only term `R*` scales); `(dP/dx)_gravity = ρ g dz/dx` (g from Scenario, `dz/dx` from `PipePath.derived()`); `(dP/dx)_acceleration = d(G²v)/dx`. **Lumped is the one-cell integration of the identical kernel.**
- **Friction / gravity / acceleration separation** — explicit, with calibration touching only friction.
- **Lumped mode first; segmented mode after** — segmented reuses the identical kernel with `N` cells.

**Tests required (`TEST_PLAN_V1.md` §3.5, §9.2).**
- Contribution contract: Pipe consumes only handed-in trial state, never reaches outside itself, never names a neighbour, reports applied calibration.
- Physical: total ΔP = integral of the per-cell kernel; a horizontal pipe has zero gravity term; raising `delta_z` raises only the gravity term.
- Residual: momentum residual from integrated gradients; `R*` scales only friction.
- Internal-state: per-segment states named, count = Discretization, frozen derivative.
- Identical contribution signature across `Lumped`/`Segmented`.

**Acceptance criteria.** The Pipe's `contribute` integrates the gradient kernel in `Lumped` mode and returns a momentum residual + frozen-zero derivatives; the contract is proven before the Network assembles components.

**Risks.** Divergent code paths for lumped vs segmented (mitigate: one kernel, lumped = one cell). The component fetching properties directly instead of through `FluidState` in `ctx` (mitigate: §3.5 test). Premature segmented implementation before lumped is green (mitigate: lumped-first ordering).

**Legacy assets to consult.** `MPL_Simulator/mpl/pipe.py`, `PyP2PL` pipe/evaporator integration recipe — **Rewrite from reference**; the MPL gradient-decomposition code corroborates the kernel form (`ARCHITECTURE_REVIEW_LEGACY.md` §5.1, Decision 007).

---

# 12. Phase 7 — Network and Assembly

**Objective.** Assemble validated topology into a `SystemState`: connections, junctions, branch structure, the one-reference invariant, and the single inventory accountant.

**Modules affected.** `network/`, plus `core/` assembly hooks (`PortHandle`/`StateLayout` creation at assembly).

**Deliverables (`INTERFACE_SPEC.md` §12, `SCHEMA_SPEC.md` §9, `[F7]`).**
- **`ComponentId` / `PortId`** identity types.
- **`connect(a, b) → Connection`** — non-directional; records peer + the three node assertions (equal P, equal h, mass-flow balance); moves no values.
- **Junctions** — n-in/m-out conservation node; `Splitter`/`Mixer` as configurations (thin aliases deserializing to `Junction`).
- **Topology validation** — the four-check `TopologyVerdict`: no dangling ports, exactly one pressure reference, well-formed splitter↔mixer branch sets, no double-counted inventory.
- **Pressure reference** — the Network owns *which node*; exactly one; a second is a validation failure (not a numerical pathology).
- **Branch groups** — splitter↔mixer pairing; equal-ΔP branch sets summing to the trunk.
- **Inventory accountant** — the Network is the single accountant; `total_charge` first-class from V1.
- **SystemState assembly** — build the flat vector, the `StateLayout`, the `PortHandle`s and `InternalStateHandle`s from the validated topology + each component's `declared_state_count`.

**Tests required (`TEST_PLAN_V1.md` §10).**
- `connect` records a non-directional peer; direction not stored.
- No values on ports (re-asserted at network level).
- `validate()` passes with exactly one reference, fails with zero or two; fails on a dangling port with a clear message.
- Well-formed branch group validates; branches share ΔP, sum to trunk; adding a branch is a topology edit only.
- Splitter/Mixer deserialize to canonical `Junction`.
- Single inventory accountant; no component competes.
- (Loop-closure-as-Network-condition is asserted at the Solver phase, §10.8.)

**Acceptance criteria.** A trivial two-component topology (fixed-inlet source → Pipe → fixed-outlet/reference) validates and assembles into a correctly-sized `SystemState` with handles mapping every port and internal state.

**Risks.** Topology baked into the solver (the legacy anti-pattern, all three projects — mitigate: the Network exists *before* the Solver, this phase precedes Phase 8). Out-of-band reference wiring (mitigate: the reference is a Network fact, not a component side-call).

**Legacy assets to consult.** All three legacy "loops" are **Rewrite** (a Python list is not a Network, `ARCHITECTURE_REVIEW_LEGACY.md` §4.2, §5.2). Consult `MPL_Simulator/mpl/loop.py` `build_standard_loop` only as a *negative* example of hard-wired topology.

---

# 13. Phase 8 — First Steady Solver

**Objective.** Close the vertical slice: drive the assembled system to convergence, emit invariants and convergence metadata, depending on nothing below. **This phase makes the vertical slice green end-to-end.**

**Modules affected.** `solvers/`.

**Deliverables (`INTERFACE_SPEC.md` §13, `ARCHITECTURE_MASTER.md` §14, `[F1] [F7] [F18]`).**
- **Fixed-point pressure iteration** — iterate global pressure/flow, march local enthalpy; the robust default for the single-loop slice.
- **Simultaneous Newton option** — first-class, on the full residual vector; the legacy `(R1 = ΔP_pump − ΣΔP, R2 = P_sys − P_acc)` shape behind a real Network. Inherited later by the dynamic path.
- **Residual assembly** — scatter trial values to components via handles (`ComponentTrialState`), gather `ComponentContribution`, add Network continuity/closure conditions, over `SystemState`. No component fetches from the network.
- **Finite-difference Jacobian seam** — the Solver obtains the Jacobian itself by structured FD (copy-the-array-and-bump); components are not required to provide derivatives, only to be differentiable. Optional analytic/AD override accepted but **AD through the property layer is not promised**.
- **Convergence metadata** — `ConvergenceMetadata {iterations, final_residual_norm, converged, strategy}` on every solve.
- **Non-convergence reporting** — `converged: false` with honest final residual; the partial state is not raised-and-discarded.

**Tests required (`TEST_PLAN_V1.md` §11, §4).**
- `SystemState` owned/mutated only by the Solver; stores exactly `(P,h,ṁ)` + named states.
- Residual assembly via handles; assembled residual = contributions + Network conditions.
- Fixed-point converges the single loop to tolerance.
- Simultaneous Newton converges the **same** loop to the **same** state.
- FD Jacobian by copy-and-bump; residual continuity across a quality transition (differentiability).
- Convergence metadata emitted converged-or-not; non-converged state persisted honestly.
- Solver isolation: never calls a correlation/geometry/property formula; works for any valid Network (swap two-component for three-component, no solver change).
- **The vertical slice (§4 of TEST_PLAN):** all seven layer tests green; loop invariants within targets (energy imbalance < 1%, pressure-closure < 1%, `0 ≤ x ≤ 1`).

**Acceptance criteria.** The minimal loop converges under both strategies to the same state; invariants are computed from un-calibrated conservation and within target; the Solver depends on nothing below it. This is the proof that the frozen interfaces compose end-to-end.

**Risks.** Solver–physics entanglement (mitigate: §11.9 isolation test). Convergence failure on near-saturation states (mitigate: (P,h) continuity + FD; fixed-point as the robust starting point; honest non-convergence reporting rather than masking). A non-smooth correlation branch tripping Newton (mitigate: §7.6 continuity + §11.5 differentiability test).

**Legacy assets to consult.** `MPL_Simulator/mpl/loop.py` `LoopSolver` Newton residual *shape* — **Adapt** the simultaneous-Newton strategy and the two-residual form; **Rewrite** the topology/import/out-of-band-accumulator coupling (`ARCHITECTURE_REVIEW_LEGACY.md` §5.3, §5.6). `A0` two-pass momentum corrector as a numerical pattern (§3.3).

---

# 14. Phase 9 — Result and Schema Serialization

**Objective.** Make runs reproducible and archivable: the minimal-stored Result with mandatory invariants, and the versioned round-tripping tuple/result serialization.

**Modules affected.** `results/`, `schema/`.

**Deliverables (`INTERFACE_SPEC.md` §14, `SCHEMA_SPEC.md` §2, §4, §14–§16).**
- **`Result`** — stored: `converged_port_values {PortId → (P,h,ṁ)}`, `converged_internal_states {(ComponentId, name) → float[]}`, `tuple_ref`. Nothing else stored.
- **`ValidationInvariants`** — `energy_imbalance`, `mass_imbalance`, `pressure_closure_residual`, `bound_checks` (`0 ≤ x ≤ 1`, `T < T_crit`), all from un-calibrated conservation. A Result missing any is malformed.
- **Closure metadata** — aggregated from every correlation/HX-model that contributed (name, version, source).
- **Validity warnings** — every non-`IN_ENVELOPE` verdict surfaced into `Result.validity_warnings`.
- **Calibration report** — present even under `NONE` (empty factors); predictive-vs-calibrated flag mandatory.
- **Derived profiles** — reconstructed on demand from stored `(P,h)` through `FluidState`; never stored (the one sanctioned `post_processing_cache` exception is explicitly marked and regenerable).
- **Tuple serialization** — `ReproducibilityTuple` with all fields of `SCHEMA_SPEC.md` §4; `schema_version` (first field), `project_version`, `metadata`.
- **Result serialization** — `#kind: Result`, `schema_version`, `tuple_ref` (by-value or `@hash`).
- **`schema_version`** — every top-level artifact carries it; semantic versioning rules.
- **`tuple_ref`** — content-hash recommended for archival; embed for self-contained results.
- **Content-hash placeholder** — the canonicalization rule (which normalized serialization is hashed, which algorithm) is fixed at first serializer authoring and recorded in the artifact metadata. A placeholder/stub hash is acceptable in V1 provided the rule is documented and the field is populated.

**Tests required (`TEST_PLAN_V1.md` §3.8, §12).**
- Minimal stored state; no stored derived properties; the sanctioned cache marked and regenerable.
- `tuple_ref` required; by-value or content-hash; archival result embeds its tuple.
- Energy/mass imbalance and pressure-closure residual present and within target; bound checks recorded with worst value + location.
- Validity warnings surfaced; predictive/calibrated flag mandatory.
- Schema: every artifact carries `schema_version`; round-trip deserialize→serialize byte-stable under the canonicalization rule; unresolvable `$ref` is a hard error; every model selection present and canonical; no hidden defaults (resolved values written explicitly, e.g. gravity = 1 g).
- Reproducibility round-trip: serialize tuple → re-instantiate → re-solve → converged state reproduces to tolerance.

**Acceptance criteria.** A run produces a well-formed minimal Result with all mandatory invariants/reports; the tuple+result round-trip and reproduce the solve to tolerance. The Phase-5 conservation-firewall test now fully activates (invariants exist).

**Risks.** A `T`/`ρ` profile sneaking into stored state (mitigate: §2.4 serialization-firewall test). Hidden defaults (mitigate: explicit-value writing test). Canonicalization left undefined, breaking archival hashes later (mitigate: document the rule now, even with a placeholder algorithm).

**Legacy assets to consult.** `PyP2PL/.../results.py` and `MPL_Simulator` `LoopResult` as *reference shapes* for a Result object — **Adapt** the field inventory, enforce minimal-stored.

---

# 15. Phase 10 — Pump and Accumulator

**Objective.** Make the loop drivable and pressure-referenced: a Pump with a simple performance map, and the Accumulator as the first-class pressure-reference component with a swappable volume↔pressure law.

**Modules affected.** `components/` (Pump, Accumulator), `correlations/` (the `VOLUME_PRESSURE_LAW` role closures), `network/` (reference-node wiring).

**Deliverables (`INTERFACE_SPEC.md` §11.4, §11.7, `CORRELATION_CONTRACT.md` §9, `[F9] [F15]`, Decision 008).**
- **`Pump` component** — `[in]`/`[out]`; minimal geometry exposing `L, A` for loop inertia; shaft speed / inertia `I` named-but-frozen; performance/efficiency-map slot; binds `PumpSpeedCommand` (ω) or `PumpFlowTarget` (ṁ).
- **Simple pump map** — `ΔP_pump` vs `ṁ` at commanded ω; pump power derivable. Contributes ΔP to the loop momentum balance.
- **`Accumulator` component** — `AccumulatorGeometry` (containment only); one `VolumePressureLaw` slot; stores **`V_g`**, derives `P` (never stored).
- **PCA law** — `VOLUME_PRESSURE_LAW` closure: `(V_g, V_total, charge_volume, polytropic_index) → P` via the polytropic gas relation; monotonic `P(V_g)`.
- **HCA law from legacy if feasible** — heater-driven saturation-temperature reference using the `thermal` sub-spec; **Adapt** the MPL `AccumulatorHCA` `set_pressure`/`dP_dT` law. (Gas-charged/spring/bellows declared interchangeable `<<SEAM>>`; only the slot acceptance is tested in V1.)
- **`V_g` stored, P derived** — `P_sys` is a `SystemState` unknown constrained by the law, never stored on the accumulator.
- **Accumulator pressure-reference role** — the Network wires *which node*; the law owns the *value*; the Solver owns global consistency; `P_set` arrives from Scenario (`AccumulatorPressureSetpoint`).

**Tests required (`TEST_PLAN_V1.md` §9.1, §9.5).**
- Pump: ΔP follows the map at commanded ω/ṁ; inertia `I = L/A` named-frozen; command targeting a non-existent pump is a binding error.
- Accumulator PCA: monotonic `P(V_g)`, agreement with MPL legacy PCA values; HCA agreement with MPL legacy HCA values.
- Stores `V_g`; `P_sys` **not** stored on the accumulator.
- Geometry↔law separation: `AccumulatorGeometry` carries no `V_gas_charge`/spring/bellows/polytropic; all law params travel in `law_params`/`thermal`.
- Reference wiring: accumulator sets the reference at its node; `P_set` from Scenario.

**Acceptance criteria.** A pump-driven, accumulator-referenced single loop converges; the law derives `P` from stored `V_g`; geometry and law are strictly separated.

**Risks.** Storing `P_sys` on the accumulator (the legacy temptation — mitigate: §9.5 test). Out-of-band `accumulator.set_pressure()` solver coupling (the MPL anti-pattern — mitigate: reference is Network wiring + a `VOLUME_PRESSURE_LAW` closure, not a side-call). Law parameters in geometry (mitigate: separation test).

**Legacy assets to consult.** `MPL_Simulator/mpl/accumulator.py` (`AccumulatorHCA`/`AccumulatorPCA`, `dP_dT`, `effective_compressibility`, `fluid_inventory`) — **Adapt** as the `VOLUME_PRESSURE_LAW` closures; the frozen `V_g`/`V_l` states carry into Phase 6/dynamics unchanged (`ARCHITECTURE_REVIEW_LEGACY.md` §5.3). `MPL_Simulator/mpl/pump.py` — **Rewrite from reference**.

---

# 16. Phase 11 — HeatExchangerModel, Evaporator and Condenser

**Objective.** Complete the V1 component set: the distinct `HeatExchangerModel` strategy concept and the two heat exchangers that consume it, with their HTC/ΔP correlation slots and secondary-fluid boundary conditions.

**Modules affected.** `hx_models/`, `components/` (Evaporator, Condenser), `correlations/` (boiling/condensation HTCs, two-phase ΔP — the PyP2PL + A0 ports).

**Deliverables (`INTERFACE_SPEC.md` §8, §11.4, `CORRELATION_CONTRACT.md` §3.4, `TEST_PLAN_V1.md` §9.3–§9.4, §9.9).**
- **`HeatExchangerModelRegistry`** — separate from the correlation registry; resolves HX strategies by name.
- **`HeatExchangerModel`** interface — `kind()`, `solve(HXSolveRequest) → HXSolveResult`; consumes injected HTC/ΔP correlations + calibration + a `SecondaryFluidBC`; never touches ports/network/solver.
- **`EpsilonNTU` model** — builds `UA` from HTC correlations + area; the v1 condenser default (Lumped).
- **`SegmentedMarch` model** — marches `Segmented` cells, calling HTC/ΔP correlations per cell; the meaningful evaporator strategy. (`LMTD` Lumped alternative built alongside; `MOVING_BOUNDARY` declared `<<SEAM>>`.)
- **Plate condenser** — `PlateGeometry`; condensation-HTC + ΔP slots; `EPSILON_NTU` default; inlet two-phase → outlet subcooled; binds `CondenserSink {T_in, mdot, fluid}`.
- **Microchannel evaporator** — `MicrochannelGeometry`; `SEGMENTED_MARCH` default; boiling-HTC + two-phase-ΔP slots; wall T = `T_sat + q″/α` per segment; binds `EvaporatorHeatLoad`.
- **Secondary-fluid boundary conditions** — `SinkInletTempAndFlow | FixedWallTemp | FixedHeatRate | AmbientCoupling`, bound from Scenario, never a stored component attribute. The condenser sink fluid is a first-class `FluidRef` with its own backend.
- **HTC and DP correlation slots** — the PyP2PL five boiling HTCs and A0 `alpha_boiling`/`alpha_condensation`/mixture-friction are **Adapt**-ed here (globals/hacks stripped, envelopes added); MPL Shah/Kim-Mudawar/Yan/MSH already ported in Phase 3 are bound.

**Tests required (`TEST_PLAN_V1.md` §9.3, §9.4, §9.9, §7.10).**
- HX model is a *separate concept*: ε-NTU/LMTD/segmented resolved from `HeatExchangerModelRegistry`, never the correlation registry.
- Model consumes correlations: builds `UA` from injected HTC + area; calls HTC/ΔP per cell for segmented; never resolves a registry itself.
- Secondary BC bound from Scenario.
- Calibration through the model at documented seams (HTC/UA, friction), never a balance.
- `HXSolveResult` returns derived `primary_state_out`, total `Q`, integrated `dP_primary`, and every called correlation's verdict.
- Evaporator: heat load raises outlet enthalpy/quality per energy balance; outlet quality in `[0,1]`; `Q` matches the BC.
- Condenser: heat rejected matches the sink BC; two-phase → subcooled; energy balance closes.
- Boiling/condensation correlation migration tests (PyP2PL/A0 with hacks removed).

**Acceptance criteria.** A full loop (pump → evaporator → condenser → accumulator) converges with the HX models consuming correlations and secondary BCs from Scenario; ε-NTU↔LMTD↔segmented swap is a tuple edit; the model is never miscategorised as a correlation.

**Risks.** Re-introducing ε-NTU/LMTD as a correlation role (the §17-A3 amendment forbids it — mitigate: §9.9 separate-registry test). PyP2PL correlation hacks surviving the port (`_fluid_name`, `M = 102.0` — mitigate: §7.10 migration tests). Solver convergence on the two-phase evaporator (mitigate: segmented-march + (P,h) continuity; fixed-point fallback).

**Legacy assets to consult.** `MPL_Simulator/mpl/condenser.py` (ε-NTU zone march) — **Adapt** behind the Component + HX-model contract. `PyP2PL` evaporator integration recipe + five boiling HTCs — **Adapt** correlations, **Rewrite** component. `A0` `alpha_boiling`/`alpha_condensation`/mixture friction — **Adapt** equations from global housing.

---

# 17. Phase 12 — Validation Harness and Literature Cases

**Objective.** Check the framework against published data, using the validation-case schema, with clear handling of data that is not yet digitized.

**Modules affected.** `validation/`, `schema/` (validation-case file), `tests/literature/`.

**Deliverables (`SCHEMA_SPEC.md` §18, `TEST_PLAN_V1.md` §3.10, `ARCHITECTURE_REVIEW_LEGACY.md` §7.3).**
- **Validation case schema usage** — inputs, measured quantities, uncertainty, expected outputs, comparison metrics (MAE per Kokate Eq. 17).
- **Kokate 2024** R-134a — HTC-vs-q″, ΔP-vs-q″, HTC-vs-G; the named first end-to-end target. Digitized data from PyP2PL `validation.py` (**Reuse** data, **Adapt** MAE).
- **Li 2021 Acetone** — evaporator-component energy balance (Mode A) and loop-level (Mode B); from MPL `validation_li2021.py` (**Reuse**). A second fluid/source.
- **Fujii 2004** — High/Medium/Low node profiles + per-region ΔP, from A0 annex comments (**Reuse** as a fixture, **Discard** the code). A third, geometry-resolved case.
- **PyP2PL sweeps** — the four worked example sweeps as the first Scenario/Result fixtures.
- **Pending-data handling** — each case whose digitized data is not yet sourced/pinned is marked `PENDING-DATA`: the test is *written and skipped* with a marker citing the blocker, so sourcing the data flips it from skipped to active without authoring new tests.

**Tests required.** For each case with data present: agreement within the case's `comparison_metrics` tolerance against the reported uncertainty band. For each `PENDING-DATA` case: the skip marker is present and the harness loads the case schema.

**Acceptance criteria.** At least one literature case is **active** (data present) and passing within tolerance, OR all are `PENDING-DATA` with the harness proven on the case schema and the data blocker documented — consistent with the V1 Definition of Done (§24).

**Risks.** Validation data not digitized (mitigate: `PENDING-DATA` markers; Kokate data already digitized in PyP2PL is the most likely active case). Silently weakening a tolerance to pass (forbidden — §21; if a case fails, the report says so). Changing physics to make a case pass (forbidden — the test is wrong before the architecture is).

**Legacy assets to consult.** `PyP2PL/utils/validation.py` (Kokate digitized + MAE — Reuse/Adapt). `MPL_Simulator/validation/validation_li2021.py` (Li Acetone — Reuse). `A0` Fujii annex (Reuse as data).

---

# 18. Phase 13 — DOE and Surrogate Readiness

**Objective.** Make datasets generable over scenarios against a fixed network, with failed runs recorded and results filterable by validity — **without implementing any ML.**

**Modules affected.** `schema/` (DOE dataset file), `validation/`/`results/` (filtering helpers), `tests/`.

**Deliverables (`SCHEMA_SPEC.md` §17, `INTERFACE_SPEC.md` §10.3, `TEST_PLAN_V1.md` §1.3).**
- **DOE dataset schema** — a collection of tuple/result references over a fixed network and varied scenarios; `parent_tuple` lineage so a dataset is "base + the one field each point varied."
- **Scenario sweeps** — iterate `boundary_conditions`/`commands`/`operating_point` against a fixed Network and fixed Components; the `(Scenario → Result)` mapping is the surrogate training pair.
- **Failed-run recording** — a non-converged solve still produces a valid serialized Result with honest invariants; the DOE records and analyzes failed points, never hides them.
- **Result filtering by validity** — filter a dataset by `convergence.converged`, by invariant tolerance, and by `validity_warnings` (in-envelope vs extrapolated).
- **Not implementing ML yet** — only the dataset *schema* and the `CUSTOM_CLOSURE` admissibility *contract* are exercised; no real surrogate is trained. The `CUSTOM_CLOSURE` seam and ML-closure traceability fields are declared, empty in V1.

**Tests required.** DOE dataset round-trips; a sweep generates N tuples from a base with `parent_tuple` set; a deliberately non-converging point is recorded with `converged: false`; validity-filtering returns the expected subset; the `CUSTOM_CLOSURE` admissibility contract (declared role + envelope + traceability) is testable with a stub.

**Acceptance criteria.** A multi-point scenario sweep over a fixed loop produces a filterable dataset of tuple/result pairs, with failed points recorded honestly. No ML code exists.

**Risks.** Building ML before the dataset substrate is solid (mitigate: explicitly out of scope — Phase 5/"later"). Hiding failed runs (forbidden — `SCHEMA_SPEC.md` §20-14 anti-pattern). Dataset bloat from stored derived properties (mitigate: minimal-stored Result).

**Legacy assets to consult.** `PyP2PL/utils/parametric.py` sweep helpers (**Adapt** under results tooling). The four PyP2PL example sweeps as the first dataset fixtures.

---

# 19. Phase 14 — Documentation and Release

**Objective.** Tag V1 with documentation a new contributor (human or agent) can build from, and a compliance checklist that proves conformance.

**Modules affected.** `docs/` (new contributor-facing docs; the frozen architecture docs are unchanged), `README`, `examples/`.

**Deliverables.**
- **README update** — what the framework is, the V1 scope, install, run the vertical slice and one literature case.
- **Examples** — the worked vertical-slice loop and the full loop, as runnable tuple/scenario fixtures with golden Results.
- **Developer guide** — how to add a correlation (register + envelope), add a component (contribution contract), add a backend; the package-structure map (§3); the import-direction guard.
- **Known limitations** — V1 is steady-state only; `TabulatedPropertyBackend` is `PENDING-DATA`; MovingBoundary/dynamics/AD/ML are declared seams, not built; which literature cases are active vs pending.
- **Architecture compliance checklist** — the anti-pattern checklist (`ARCHITECTURE_MASTER.md` §19, `CORRELATION_CONTRACT.md` §13, `SCHEMA_SPEC.md` §20) as a sign-off list, mapped to the automated compliance tests and review gates that enforce each.
- **Internal release tag** — `v1.0.0` (or the agreed `project_version`), with `schema_version` `1.0.0` frozen for archival.

**Tests required.** Examples run green; golden Results match; the compliance checklist's automated items all pass in CI; docs links resolve.

**Acceptance criteria.** A new contributor can install, run the slice, run a literature case, and add a correlation from the docs alone; the compliance checklist is fully green or has documented, justified exceptions.

**Risks.** Documentation drifting from code (mitigate: examples are tested, not prose-only). Releasing with silent compliance gaps (mitigate: the checklist gates the tag).

**Legacy assets to consult.** None — this phase produces new documentation.

---

# 20. Legacy Harvest Plan

Built from the architecture, harvested in the §8 order of `ARCHITECTURE_REVIEW_LEGACY.md`. Verdicts: **Reuse** (cosmetic change only), **Adapt** (sound physics re-housed behind an approved interface), **Rewrite** (idea needed, implementation too DAG-violating to port), **Discard**.

| Legacy source | What to harvest | Where it goes | Verdict | When (phase) | Tests required |
|---|---|---|---|---|---|
| **A0_SS_v3_Stable** | module structure, globals, run-on-import | — | **Discard** | never | — |
| A0 | HEM closures (void, ρ_mix, actual quality, homogeneous velocity), mixture friction factor | `correlations/` | **Adapt** | 11 | equation reproduces legacy value, hacks stripped |
| A0 | `alpha_boiling` (nucleate+convective ΔT fixed-point) | `correlations/` (HTC) | **Adapt** | 11 | §7.10 migration test |
| A0 | `alpha_condensation` (Chen / Shah-1979) | `correlations/` (HTC) | **Adapt** | 11 | §7.10 migration test |
| A0 | `R*` per-region calibration *concept* | `calibration/` | **Adapt** (concept) / **Rewrite** (bisection-on-globals) | 5 | conservation firewall test |
| A0 | two-pass momentum corrector | `solvers/` (numerical pattern) | **Adapt** | 8 | Newton/fixed-point convergence |
| A0 | Fujii (2004) validation data (annex) | `validation/` fixtures | **Reuse** (data) | 12 | literature-case agreement |
| A0 | `EOS_liq/vap_properties`, plotting, hard-coded BCs | — | **Discard** (superseded) | never | — |
| **PyP2PL** | five boiling HTCs (Shah, Chen, Bennett-Chen, Gungor-Winterton, Kandlikar-Balasubramanian) | `correlations/` (HTC) | **Adapt** | 11 | §7.10 — `_fluid_name`/`hasattr`/`M=102.0` removed |
| PyP2PL | MSH + homogeneous accel + Churchill ΔP | `correlations/` (ΔP) | **Adapt** | 3 (Churchill), 11 (MSH) | gradient-not-total; legacy value |
| PyP2PL | plate / single-phase ΔP | `correlations/` (ΔP) | **Adapt** | 11 | legacy value |
| PyP2PL | evaporator integration recipe | `components/` (reference) | **Rewrite** | 11 | contribution-contract tests |
| PyP2PL | component decomposition (pump/evaporator/condenser/...) | `components/` (reference only) | **Rewrite** | 6,10,11 | per-component §9 tests |
| PyP2PL | `node.py` derived-on-demand pattern | `core/`/`results/` (ownership reference) | **Adapt** | 1,9 | no-stored-derived tests |
| PyP2PL | Kokate (2024) digitized data + MAE Eq. 17 | `validation/` | **Reuse** (data) / **Adapt** (MAE) | 12 | Kokate agreement |
| PyP2PL | four example sweeps + CSV/PNG outputs | `examples/`, DOE fixtures | **Reuse** (scenarios) | 12,13 | DOE round-trip |
| PyP2PL | T-anchored `FluidProperties`/`FluidState`; Kokate control-law solver; list-as-loop | — | **Discard** (violates Decision 001 / no closure / no Network) | never | — |
| PyP2PL | `SatState` field list | — (checklist) | reference only | 2 | what FluidState must expose |
| **MPL_Simulator** | `fluid_properties.py` (P,h FluidState + fallback chain + source tracking) | `core/` + `properties/` (split) | **Adapt** (primary asset) | 1,2 | §5 FluidState/backend tests |
| MPL | `A1_TwoPhProp.py` table loader (σ_e, ε_r) | `properties/` `TabulatedPropertyBackend` | **Adapt** | 2 (iface) / later (data) | interface conformance; numerical `PENDING-DATA` |
| MPL | `correlations.py` (Shah, Kim-Mudawar 12/13, Yan, Dittus-Boelter, Gnielinski, Shah-London, Blasius, Churchill, Homogeneous, MSH) | `correlations/` | **Adapt** (highest-yield port) | 3,11 | §7.10 migration tests |
| MPL | `accumulator.py` (HCA + PCA, dP_dT, compressibility, inventory) | `correlations/` (`VOLUME_PRESSURE_LAW`) + `components/` | **Adapt** | 10 | §9.5 accumulator tests |
| MPL | `condenser.py` (ε-NTU zone march, counter-flow two-pass) | `hx_models/` + `components/` | **Adapt** | 11 | §9.4, §9.9 tests |
| MPL | `loop.py` Newton residual shape `(R1, R2)` | `solvers/` | **Adapt** (strategy) / **Rewrite** (topology/imports/coupling) | 8 | §11.4 Newton agreement |
| MPL | `base.py` Port-holds-FluidState; `pipe.py`/`pump.py`/`evaporator.py` | `components/`/`core/` (reference) | **Rewrite** | 1,6,10,11 | no-state-on-port; contract tests |
| MPL | Li (2021) Acetone validation | `validation/` | **Reuse** (data) / **Adapt** (harness) | 12 | Li agreement |
| MPL | `tests/*` (both projects) | `tests/` (oracles) | **Reuse** | per-phase | regression fixtures |
| MPL | `Simple_test_v1.py`, `.spyproject/`, `.docx`, `sys.path` hacks | — | **Discard** | never | — |
| **(all)** | the 29 property CSVs | `data/property_tables/` | **Reuse — once located** | data task | `PENDING-DATA` until recovered + pinned |

> **Critical data finding (carried forward):** the 29 CSV property tables the loader expects are **not in `legacy/`** (`ARCHITECTURE_REVIEW_LEGACY.md` §6.3). Locating/regenerating, schema-verifying, versioning, and content-hash-pinning them is a **data task** that gates `TabulatedPropertyBackend` numerical correctness and the only source of `σ_e`/`ε_r` — run in parallel, blocking nothing else.

---

# 21. Development Rules for AI Agents

These bind every AI agent (Claude Code, Codex, or future) and every human contributor working on `src/`. They are the operational form of the frozen architecture and the anti-pattern checklists.

1. **Always read `ARCHITECTURE_MASTER.md` before implementation**, plus the interface document(s) governing the layer you are touching. Implement signatures exactly as frozen.
2. **Never modify architecture or interface documents during coding** unless explicitly asked. A perceived need to change a frozen contract is escalated as a `DECISION_LOG.md` proposal, not edited inline.
3. **Do not introduce new abstractions without approval.** The concept inventory is closed (`ARCHITECTURE_MASTER.md` §2). No new top-level class, plugin system, DI container, event bus, or speculative base type. If two concrete cases do not already demand it, it does not exist.
4. **Do not copy legacy code directly into `src/`.** Port equation-by-equation behind the approved interface; strip globals/hacks; add a validity envelope. A pasted block from `legacy/` is a review failure.
5. **Prefer small patches.** One coherent, tested increment per commit, on one approved seam.
6. **Run tests after each phase** (and after each commit). The layer below must be green before the layer above is built. No layer is implemented against an untested layer.
7. **Do not bypass PropertyBackend.** No CoolProp (or any property engine) import or call outside `properties/`. All properties flow through `FluidState`.
8. **Do not store derived properties.** Only `(P, h, ṁ)` + named internal states are stored, in `SystemState`. No `T`/`ρ`/`x` cached on any object or serialized as primary state.
9. **Do not put values on Port.** Port is connectivity only. Values live in `SystemState`, mapped by `PortHandle`.
10. **Do not make Solver depend on physics.** The contribution contract is residual/derivative only; the Solver builds its own Jacobian; nothing depends on the Solver.
11. **Do not silently fix tests by weakening them.** A failing test is fixed by fixing the code or by a deliberate, documented baseline update — never by loosening a tolerance, deleting an assertion, or skipping without a cited blocker. If a test contradicts the architecture, the test is wrong; if the code contradicts the test, the code is wrong; you do not get to make the disagreement disappear.

Supporting prohibitions (each maps to a named anti-pattern): no calibration inside a correlation; no correlation receiving a `Component`/`Geometry` object; no topology baked into the solver; no out-of-band reference wiring; no `_last_dP`/`_last_Q` caching; no run-on-import/module-level mutable state; no mesh in geometry; no law parameters in geometry; no AD-through-CoolProp promise.

---

# 22. Recommended Commit Strategy

Commit milestones, roughly one coherent increment each, in phase order. Branch off `main`; small commits; tests green before merge.

```
docs:        complete architecture and validation framework          (done: bacb323)
docs:        add implementation roadmap                              (this document)
chore:       initialize python package and test tooling              (Phase 0)
core:        add fluid identity, fluid state, and port primitives    (Phase 1)
core:        add system state vector and handles                     (Phase 1)
properties:  add property backend interface and registry             (Phase 2)
properties:  add CoolProp backend                                    (Phase 2)
correlations: add correlation contract, input roles, and verdict     (Phase 3)
correlations: add registry and first friction closure (Churchill)    (Phase 3)
geometry:    add immutable geometry family and PipePath              (Phase 4)
discretization: add lumped/segmented modes and cell metrics          (Phase 4)
calibration: add calibration value objects and conservation firewall (Phase 5)
components:  add component contribution contract and 1D kernel        (Phase 6)
components:  add pipe component (lumped)                              (Phase 6)
network:     add topology, validation, and state assembly            (Phase 7)
solvers:     add fixed-point steady solver                           (Phase 8)
solvers:     add simultaneous Newton option and FD Jacobian          (Phase 8)
results:     add result, invariants, and minimal-stored reporting    (Phase 9)
schema:      add tuple and result serialization with versioning      (Phase 9)
components:  add pump component and simple map                       (Phase 10)
components:  add accumulator and PCA/HCA volume-pressure laws        (Phase 10)
hx_models:   add heat-exchanger model interface and epsilon-NTU      (Phase 11)
hx_models:   add segmented-march model                               (Phase 11)
components:  add condenser (plate) and evaporator (microchannel)     (Phase 11)
correlations: add boiling/condensation HTC closures (PyP2PL/A0)      (Phase 11)
validation:  add literature harness and Kokate/Li/Fujii cases        (Phase 12)
schema:      add DOE dataset schema and scenario sweeps              (Phase 13)
docs:        add developer guide, examples, and compliance checklist (Phase 14)
release:     tag v1.0.0 (schema_version 1.0.0)                       (Phase 14)
```

Commit messages end with the project's co-author trailer. A commit that spans multiple layers or mixes a legacy port with a new feature is split.

---

# 23. Risks and Mitigation

| Risk | Where it bites | Mitigation |
|---|---|---|
| **Over-engineering before the vertical slice** | Phases 1–8 | Build the smallest end-to-end loop first (§4, Principle 2); no expensive component until the slice is green; no abstraction without two concrete cases. |
| **Legacy copy-paste** | every port | No paste rule (§21-4); port equation-by-equation behind the interface; migration tests prove the *equation* reproduces, not the *housing*. |
| **Architecture drift** | every phase | Closed concept inventory; import-direction guard; the anti-pattern compliance tests as CI gates; escalate, never edit, a frozen contract. |
| **CoolProp near saturation** | Phases 2, 8, 11 | (P,h) bought *continuity* not *smoothness*; expect slope kinks at x=0/1; smoothed derivatives recommended for gradient paths; FD-primary; honest `OUT_OF_RANGE` rather than fabricated values. |
| **Solver convergence issues** | Phases 8, 11 | Fixed-point as the robust default; Newton as the cross-check; FD Jacobian; (P,h) continuity + differentiable closures; honest non-convergence reporting, never masked. |
| **Missing property tables** | `TabulatedPropertyBackend`, σ_e/ε_r | `PENDING-DATA` markers; interface conformance tested with a stub; the data task runs in parallel and blocks nothing else. |
| **Validation data not digitized** | Phase 12 | `PENDING-DATA` skip markers citing the blocker; Kokate data (already digitized in PyP2PL) is the most likely active case; the harness is proven on the schema regardless. |
| **Too many documents vs not enough code** | the whole project | This roadmap exists to convert frozen docs into code; the architecture phase is *closed* (the gate of `ARCHITECTURE_MASTER.md` §18 is passed); Phase 0 starts code now; no further architecture documents are produced for V1. |

---

# 24. Definition of Done for V1

V1 is complete when **all** of the following hold:

1. **One working steady loop** converges end-to-end (pump → evaporator → condenser → accumulator-referenced) under both fixed-point and simultaneous-Newton strategies, to the same converged state within tolerance.
2. **`CoolPropBackend`** serves every derived property through the single property seam; no CoolProp call exists outside `properties/`.
3. **Components present:** Pipe, Pump, Accumulator, Evaporator, Condenser (plus Valve, Junction, Reservoir at V1 fidelity), each satisfying the contribution contract.
4. **At least one pressure-drop correlation** (the friction closure, e.g. Churchill + a two-phase ΔP) is registered with a validity envelope and returns a gradient.
5. **At least one HTC correlation** (boiling and/or condensation) is registered with an envelope and consumed by an HX model.
6. **Result invariants** — energy imbalance, mass imbalance, pressure-closure residual, and bound checks — are first-class, computed from un-calibrated conservation, and within target (energy < 1%, pressure-closure < 1%, `0 ≤ x ≤ 1`).
7. **Schema serialization** — the Reproducibility Tuple and Result round-trip, carry `schema_version`, store only minimal state, and reproduce the solve to tolerance.
8. **At least one literature validation case active or pending with a clear data status** — Kokate 2024 (or Li 2021 / Fujii 2004) is either passing within tolerance or `PENDING-DATA` with the blocker documented and the harness proven on the case schema.
9. **The conservation firewall holds** — a wrong calibration worsens the un-calibrated invariants, never falsely passes.
10. **The compliance checklist is green** — the anti-pattern tests pass; no stored derived state, no value on a Port, no correlation impurity, no solver–physics entanglement, no architecture drift.

Explicitly **not** required for V1 (declared seams, built later): the dynamic solver, MovingBoundary zone evolution, the linearisation/MPC/ROM extraction, real surrogate/ML closures, REFPROP/Mixture/Custom backends, bellows/spring/gas-charged accumulator laws, and `TabulatedPropertyBackend` numerical correctness (gated on the missing CSVs).

---

# 25. Immediate Next Actions

The concrete actions to take after this document, in order:

1. **Execute Phase 0.** Create `pyproject.toml`, the `src/mpl_sim/` package tree (§3), the `tests/` tree, lint/format config, the import-direction guard encoding the four forbidden DAG directions, and the CI placeholder. Commit `chore: initialize python package and test tooling`.
2. **Pin the CoolProp reference values.** Generate a small reference grid (R-134a, Acetone) of `(P,h) → T,ρ,x,h_f,h_g,h_fg` from CoolProp directly, to serve as the Phase-2 backend-agreement oracle — stored as a test fixture, not in `src/`.
3. **Implement Phase 1 core data model** test-first: `FluidIdentity`, `FluidState`, `Port`, `PortHandle`, `SystemState`, `StateLayout`, `InternalStateHandle`, with the stored-vs-derived boundary tests green.
4. **Implement Phase 2 PropertyBackend** test-first: the interface, `CoolPropBackend`, `PropertyBackendRegistry`, `PropertyResult`, capability flags; wire the optional ergonomic `FluidState` wrapper (analysis-only).
5. **Implement Phase 3 correlation contract + registry** with Churchill as the first `SINGLE_PHASE_DP` closure (Adapt from MPL `correlations.py`), including its `ValidityEnvelope`.
6. **Start the property-CSV recovery data task in parallel** — locate/regenerate the 29 tables, verify the column schema against the `A1_TwoPhProp` loader, version and content-hash pin them. This blocks only `TabulatedPropertyBackend` numerical tests.
7. **Implement Phases 4–6** (geometry/discretization, calibration value objects + firewall shape, Pipe + the 1D gradient kernel in Lumped mode) test-first.
8. **Build the vertical slice (Phases 7–8):** trivial two-component Network → fixed-point Solver → converged `SystemState`, and make the seven-layer slice test green (`TEST_PLAN_V1.md` §4) — the milestone that proves the frozen interfaces compose.
9. **Implement Phase 9** (Result + schema) and **activate the conservation-firewall test** now that invariants exist; establish the first golden Result for the slice.
10. **Proceed to Phases 10–14** in order — Pump/Accumulator, HX models + Evaporator/Condenser, the literature harness (digitize/pin Kokate first), DOE readiness, then documentation and the `v1.0.0` tag — each gated by its predecessor's green acceptance criteria.

---

*End of IMPLEMENTATION_PLAN.md — the practical, phased build sequence for MPL V1. It conforms strictly to the frozen architecture and the four interface documents; it reopens no decision. Phase 0 begins now.*
