# OPEN_ARCHITECTURE_QUESTIONS.md

**Unresolved architectural questions to settle before consolidating ARCHITECTURE_MASTER.md**

Status: pre-consolidation review. No implementation plan, no code, no MASTER document.
Inputs treated as binding context: `ARCHITECTURE_LEVEL_1.md`, `ARCHITECTURE_LEVEL_2.md`, `ARCHITECTURE_LEVEL_3.md`, `ARCHITECTURE_REVIEW_LEGACY.md`, `DECISION_LOG.md`, `LITERATURE_CORE_ANALYSIS.md`, `TABLA_COMPONENTES.md`.
Horizon governing every recommendation: 5–10 years; steady-state now; dynamics, MPC/ROM/surrogate later as additions along prepared seams.

A note on method. Levels 1–3 are exceptionally complete, and Level 3 already *declared positions* on most of Level 2's open items. This document does **not** re-open settled physics or re-argue the dependency DAG. It does two things only:

1. **Honesty pass** — separate decisions that are genuinely mature from decisions Level 3 *asserted by fiat* but that have not been adversarially stress-tested, and from decisions that are still literally open in the Decision Log (Decision 002).
2. **Resolve the genuinely-open few** — for each, evaluate alternatives against steady-state suitability, dynamic suitability, numerics, extensibility, and complexity, and give a final recommendation that MASTER can freeze.

The bar for inclusion is the prompt's: *only questions that could significantly affect the future architecture.* Ergonomic and cosmetic choices are deliberately excluded.

---

## 1. Architecture Readiness Review

A maturity classification of every load-bearing decision, ranked by importance. Three tiers: **Mature** (freeze as-is), **Asserted-but-unratified** (Level 3 took a position; it is defensible but has not been pressure-tested and should be confirmed before MASTER), and **Genuinely open** (must be decided here — Sections 2–9 do so).

### 1.1 Mature — freeze as written (do not reopen)

Ranked by how much the rest of the architecture leans on them.

| # | Decision | Source | Why mature |
|---|---|---|---|
| 1 | One-directional dependency DAG; nothing depends on the Solver | L2 §1 | The keystone. Independently corroborated by the legacy audit (every legacy violation maps to a DAG breach). |
| 2 | (P, h) + identity canonical; everything else derived | L1 §4, Dec. 001 | Universal literature consensus (Van Gerner, Middelhuis, Truster, Kokate). Non-negotiable for saturation-dome continuity. |
| 3 | Single-source-of-truth ownership: only primary unknowns stored; T/x/ρ/μ derived | L2 §2.1 | Directly kills the #1 silent-divergence failure; legacy audit shows three independent projects that suffered exactly when they violated it. |
| 4 | Correlations are stateless, swappable, selected by name; ignorant of component/topology | L1 §8, L2 §6, L3 §7 | The project's core research seam. Legacy `MPL_Simulator` already realised it (Protocol + registry), proving buildability. |
| 5 | Calibration at the per-component correlation-output seam; scales closures never balances; resolution slot→component→global | L1 §9, L2 §7, L3 §1.1 | The conservation firewall is sound and was *independently rediscovered* in A0's `R*` design. |
| 6 | PropertyBackend is a Layer-1 citizen of FluidState, distinct from Layer-3 closure correlations | L2 §6/§10-#1, L3 §1.1 | Resolves the only latent DAG cycle. Confirmed sensible by the legacy fallback-chain design. |
| 7 | Network/Component/Solver "where/what/how" split; one pressure reference; network-level branch closure; single inventory accountant | L2 §8 | No residual ambiguity; eliminates duplicated responsibility. |
| 8 | Geometry = immutable, standalone, flat typed family, composed, shared by reference; mesh excluded | L2 §2.2/§5, L3 §5 | The "no god-object, flat family" rule is correct and well-defended. (Boundary cases resolved in §6 below.) |
| 9 | Accumulator as first-class component owning the volume↔pressure law; PCA/HCA interchangeable | L1 §6, L3 §4 | Confirmed by `MPL_Simulator` already shipping HCA+PCA behind one `set_pressure()`. |

These nine are the spine of MASTER. Nothing in this review disturbs them.

### 1.2 Asserted-but-unratified — confirm before freezing

Level 3 §1.2 took positions on these. Each is defensible, but each was decided *without* an adversarial pass, and two of them quietly **amend a Level-2 statement** without flagging it. They should be explicitly ratified (or my refinements adopted) before MASTER imports them.

| # | Decision Level 3 asserted | Risk if wrong | Where resolved here |
|---|---|---|---|
| A | Jacobian by structured finite differences in v1; AD as optional override; "components are differentiable across the saturation line" | The differentiability promise is **physically over-stated** — CoolProp (P,h) flash derivatives have kinks at x=0/x=1; AD through CoolProp is generally unavailable. Building on a promise the backend cannot keep is a latent trap. | §9 (A5 / differentiability reality) |
| B | Discretization is an explicit fidelity seam (`Lumped/Segmented/MovingBoundary`) | Low risk — correct and important. Only the *moving-boundary variable-state-count* interaction with fixed-size solver assumptions needs a guard. | §6, §9 |
| C | Junction unifies Splitter/Mixer; Reservoir is a distinct component | Low architectural risk; affects component count, not contracts. | §10 (Category B) |
| D | Scenario / Result / Reproducibility Tuple promoted to first-class concepts | Correct and cheap; ratify. The only open edge is the **linearization/sensitivity seam** they don't yet name. | §9 (A5) |

### 1.3 Genuinely open — must be decided before MASTER

These are not yet decided anywhere, or are decided *inconsistently* across documents. They are the substance of this report.

| # | Open question | Why it is genuinely open | Section |
|---|---|---|---|
| **O1** | **Where do the primary unknowns (P, h, ṁ) actually live — on the Port, or in a solver-owned state container?** | Decision 002 is *literally still "under review."* L2 §2.1 says "Port stores the value as a solver unknown." That statement is in tension with the simultaneous-Newton / DAE / dynamic path the same documents demand. This is the single highest-impact unresolved question. | **§2** |
| **O2** | **Is FluidState a pure value, or does it carry a PropertyBackend reference?** And is property access scalar-first or vector-first? | L1/L2 call FluidState "(P,h)+identity, the single source of truth" but never settle whether it *holds* its backend or is *served by* one, nor whether the query interface is array-capable — which decides the Phase-5 performance ceiling. | **§3** |
| **O3** | **Correlation call signature: positional scalars vs. role-typed input objects?** | The prompt names this explicitly. L3 said "(FluidState, declared scalars)" but never chose a *concrete shape*. The choice has real maintainability/AD/extensibility consequences. | **§5** |
| **O4** | **PropertyBackend interface shape, lifecycle, and mixture/derivative capabilities.** | Decision 003 fixes the *principle* (FluidState queries a backend) but not the *interface contract* — vectorisation, derivative provision, capability flags, mixture identity. These are architectural, not implementation. | **§4** |
| **O5** | **Does a 1D passage compute a total ΔP, or pressure gradients integrated over its discretization?** | Never decided. It determines whether lumped, segmented, and dynamic share one physics kernel — a 5-year maintainability fork. | **§7** |
| **O6** | **Precise boundary between component internal state and port/network unknowns** (esp. accumulator pressure). | Mostly covered by "named internal states," but the accumulator's `P_sys` vs `V_g` ownership is fuzzy and matters when pressure becomes a state. | **§8** |
| **O7** | **Is there a declared seam to extract a linearised state-space (A,B,C,D) for MPC/ROM/surrogate work?** | None exists. The 3-year stress test (§9) needs it; it is the same machinery as the Jacobian and should be named once. | **§9** |

---

## 2. Port vs PortState  (resolves O1 — the headline question)

**Context.** Decision 002 is open ("Should mdot be stored in Port or in FlowState?"). L2 §2.1 currently states the Port *stores* P, h, ṁ "as solver unknowns." The legacy projects (`PyP2PL.PortState`, `MPL_Simulator.Port` holding a `FluidState`) all stored state on the port object — and the legacy audit flags both as two-sources-of-truth / eager-compute violations. So the question is live and the legacy evidence is cautionary.

### Options

**Option A — Port stores pressure, enthalpy, mass flow** (the current L2 §2.1 wording).
The Port object owns mutable fields P, h, ṁ.

**Option B — Port represents only connectivity; a separate state container holds P, h, ṁ.**
Port = identity + owning component + role + connection. The triple (P, h, ṁ) for each port-node lives in a solver-owned `SystemState` vector, addressed by a stable port-variable handle.

**Option C — (refinement of B, recommended).** Port is pure connectivity; the primary unknowns live in a solver-owned, flat, indexable `SystemState` (the global unknown vector, of which port (P,h,ṁ) and component internal states are typed views). **No per-port "PortState" object exists, and nothing — port or otherwise — ever caches derived properties.** FluidState is constructed *transiently* from (P,h) only when a property is needed.

### Evaluation

| Criterion | A — state on Port | B/C — connectivity Port + solver-owned state vector |
|---|---|---|
| **Steady-state, sequential march** | Natural and simple. Each port holds current trial values. | Equally fine; the container is read/written by index. Marginally more indirection. |
| **Steady-state, simultaneous Newton** | Awkward. The solver's unknown vector `x` must be scattered into / gathered from port objects on every residual evaluation, coupling the solver to a topology walk. | Native. The state vector *is* `x`. Residual assembly reads typed views; no scatter/gather. |
| **Dynamic suitability** | Poor. ṁ and P become integrator states; you cannot cleanly hold the multiple simultaneous copies an integrator needs (trial, derivative, history, stages) on a single mutable port object. | Native. Multiple `SystemState` snapshots are just multiple arrays; the integrator owns them. |
| **Numerical implications** | FD-Jacobian columns require perturb-one-unknown-and-restore on object fields — error-prone and serial. AD requires the unknowns be a traced array, not object attributes — Option A blocks AD structurally. | FD perturbation = copy array, bump one entry. AD = trace the array. Vectorised DOE = batch the array. All trivial. |
| **Extensibility (MPC/ROM, §9)** | The unknown *layout* is implicit in the object graph; you cannot enumerate/index states in a stable order for linearisation without walking objects. | The state vector already *is* the ordered, introspectable list a linearisation/ROM seam needs (§9-A5). One mechanism serves Jacobian, integrator, and linearisation. |
| **Implementation complexity** | Lowest to write first; highest to evolve. Every later capability (Newton, dynamics, AD, ROM) pays interest. | Slightly higher up front (needs a handle/index scheme and views); flat thereafter. The cost is paid once, at assembly. |
| **Legacy evidence** | Both legacy projects chose A-like storage and both are flagged as the #1 violation to *not* carry forward. | The audit's prescription ("only P,h,ṁ stored; derive the rest; solver owns the unknowns") is literally Option C. |

### Recommendation

**Adopt Option C, and amend L2 §2.1 accordingly.**

- **Port carries connectivity only** (identity, owning component, role annotation, the connected peer). It is immutable after Network assembly.
- **The primary unknowns live in a solver-owned `SystemState`** — a flat, ordered, indexable container holding every port-node's (P, h, ṁ) and every component's named internal states. Port-variable handles map a port to its slots in that vector. This is the natural home of "the solver owns the unknowns; nothing depends on the solver."
- **`FluidState` is transient**, constructed from (P, h) + identity on demand for property evaluation, never stored, never cached on a port (§3).
- **Retire the names "PortState" and "FlowState" as storage objects.** They are exactly the legacy anti-pattern. Decision 002's phrasing ("mdot in Port vs FlowState") is resolved as: *mdot is associated-with a port for connectivity/continuity purposes, but stored-in the SystemState like every other unknown.*

This reconciles Decision 002, removes the only Level-2 statement that fights the dynamic path, and makes the Jacobian/AD/ROM seams (§9) fall out of one object rather than three. It costs one indexing abstraction at assembly time — the cheapest possible insurance for the 5-year horizon.

> **MASTER action:** rewrite L2 §2.1's "Port stores the value" as "Port declares connectivity; the SystemState (solver-owned) stores P, h, ṁ and internal states." Add `SystemState` to the concept inventory as a numerics-layer object (it is the Solver's, so it does not expand the physics surface).

---

## 3. FluidState Ownership  (resolves O2)

### What belongs inside FluidState — stored vs. derived

| Quantity | Verdict | Rationale |
|---|---|---|
| **pressure P** | **Stored** (primary) | One of the two thermodynamic anchors. |
| **enthalpy h** | **Stored** (primary) | The second anchor; the variable the energy balance and the dynamic energy equation both carry. |
| **fluid identity** | **Stored** (primary) | Required to interpret (P,h). **Must be richer than a string** — see mixtures below. |
| **temperature T** | **Derived** | `T(P,h)` from the backend; storing it is the canonical drift bug. |
| **quality x** | **Derived** | `x = (h−h_f)/h_fg`; continuous through 0/1 — the whole reason for (P,h). |
| **density ρ** | **Derived** | Needed by correlations and (dynamics) mass storage; always recomputed. |
| **viscosity μ** (and k, σ, c_p, void, phase, T_sat, h_f/h_g/h_fg) | **Derived** | Transport/closure properties; served by the backend on demand. |
| **property backend reference** | **Not owned by value — injected/served** (see below) | Decides whether FluidState is a pure value or a smart object. |

**Mass flow ṁ is *not* in FluidState.** It is a flow variable in the `SystemState` (§2). FluidState is two numbers + identity. This separation matters in dynamics, where ṁ is a momentum state while (P,h) is the energy state.

### The one genuinely open sub-question: value vs. backend-carrying, and scalar vs. vector access

Two coherent designs:

- **3a — Pure value.** FluidState = `(P, h, identity)`. Properties are obtained via `backend.query(state, prop)` or `backend.T(state)`. The caller holds the backend. Cleanest DAG; trivially serialisable; vectorises and AD-traces naturally (a FluidState is just two arrays + an identity).
- **3b — Smart value.** FluidState = `(P, h, identity, backend-handle)`, so `state.T()` works directly. More ergonomic at call sites; but every transient state object now carries a reference, and the temptation to memoise on it (the legacy eager-compute trap) returns.

**Recommendation: 3a for the solver/inner-loop and correlation path; an optional thin ergonomic wrapper for user/analysis code.**

- The inner loop and correlations receive a **pure** FluidState plus access to a backend (the backend is supplied by the component/registry context, not embedded in every state). This keeps Phase-5 batches and FD-Jacobian columns cheap and AD-friendly, and keeps FluidState serialisable as exactly `(P, h, identity)`.
- **Property access is vector-first.** The backend query interface accepts arrays of (P,h); a scalar is the length-1 case. This is the architectural decision that sets the Phase-5 performance ceiling (L2 §10's "thousands of CoolProp calls" wall) and the FD-Jacobian cost; it must be in the interface from day one (see §4).
- **Responsibilities of FluidState:** hold the two anchors + identity; define *which* derived properties exist; delegate every derived value to the backend; never store a derived value; never know geometry, location, or solver.

### Fluid identity must be mixture-capable

The project requirement (§4 of the prompt) includes "future custom mixtures." A bare fluid-name string cannot express a mixture. **Make identity a small value object** capable of `(fluid)` or `(fluids, composition)` or `(custom-fluid-handle)`. This is the seam that lets a `MixtureBackend` or `CustomFluidBackend` be selected by identity without changing FluidState. Cheap now; a retrofit later.

> **MASTER action:** record FluidState as a pure `(P, h, identity)` value; properties served by a vector-first backend; identity is a mixture-capable value object; no property is ever stored on it.

---

## 4. PropertyBackend Architecture  (resolves O4 — a stated critical requirement)

Decision 003 fixes the principle: FluidState must not depend on CoolProp directly; it queries a `PropertyBackend`. The framework must support CoolProp, REFPROP, tabulated databases, future custom fluids, and future custom mixtures. What is **open** is the *interface contract*, the *lifecycle*, and the *capabilities* — and those are architectural because callers (FluidState, the Jacobian assembler, the dynamic compressibility term) are written against them.

### Backend ownership

- **One backend instance per fluid identity, owned by the run** (constructed from the Reproducibility Tuple). Shared by reference across all FluidStates of that fluid. Stateless with respect to the solve (internal caches are permitted *because* the contract is a pure function of (P,h,identity)).
- **Future multi-fluid runs:** selection is *per fluid identity*, so a single run could in principle bind R134a→CoolProp and a custom mixture→TabulatedBackend simultaneously. Design the registry keyed by identity, not globally, to keep that door open.

### Backend lifecycle

Constructed once per fluid per run; long-lived; disposed with the run. No import-time construction, no global mutable state (the explicit A0 anti-pattern). Internal memoisation of recent (P,h) flashes is allowed and encouraged (it is invisible behind the pure contract) — but is a *Category-B* implementation detail, not an architectural promise.

### Backend registration

A **separate registry** from the correlation registry (they are different layers — L2 §6). A backend registry maps a backend *name* → constructor. This mirrors the correlation registry's lightweight name→instance pattern; it is **not** a plugin framework. Registration is startup-time.

### Backend selection

By a `(fluid identity → backend name)` binding recorded in the Reproducibility Tuple. Default backend = CoolProp. Replacing CoolProp with REFPROP or a tabulated surrogate is a tuple edit — the same "config not code" seam as correlations.

### The interface contract — what must be in it from day one

This is the architectural core. The `PropertyBackend` interface must promise:

1. **Vector-first property queries:** `query(prop, P[], h[], identity) → value[]`. Scalar = length-1. (Sets the Phase-5 and Jacobian performance ceiling — §3.)
2. **The full derived set** FluidState exposes: T, T_sat, x, ρ, μ, k, σ, c_p, phase, and the saturation anchors h_f/h_g/h_fg.
3. **Optional first derivatives** — `∂ρ/∂P|h`, `∂ρ/∂h|P`, `∂T/∂…`, exposed behind a capability flag. Needed for the analytic-Jacobian path and for the dynamic accumulator compressibility term (`dP/dt ∝ (nP/V_g)…`). Declaring the method now (even if only CoolProp's first derivatives fill it) prevents a later bolt-on. **This is the seam that keeps the AD/analytic option alive — see §9-A5 for the differentiability caveat.**
4. **Capability flags** — e.g. `provides(σ_e)`, `provides(ε_r)`, `provides(derivatives)`, `valid_range(identity)`. The tabulated backend is the *only* legacy source of electrical conductivity / relative permittivity (legacy audit §6); a capability flag lets a component discover, rather than assume, that a property exists. A backend asked for a property it lacks returns an explicit "unavailable," never a silent guess.
5. **No extrapolation by stealth** — out-of-range tabulated queries return unavailable/NaN with a warning, never a fabricated number (inherits the correlation validity-verdict philosophy).

### Recommended architecture

A thin `PropertyBackend` interface (vector-first queries + optional derivatives + capability flags + range reporting); a small **separate** backend registry keyed by name; selection by `(fluid identity → backend)` binding in the tuple; one shared, long-lived, internally-cacheable instance per fluid per run. Concrete implementations behind the one interface: `CoolPropBackend` (default), `RefpropBackend`, `TabulatedPropertyBackend` (the legacy CSV path — strategic for σ_e/ε_r and the 29-fluid breadth, *pending CSV recovery* per legacy audit §6.3), `EmpiricalCorrelationBackend` (Letsou-Stiel/Latini/Brock-Bird, re-housed out of the legacy FluidState), and a future `MixtureBackend`/`CustomFluidBackend`. Custom fluids and mixtures are *new backend implementations behind the same interface* — the cleanest possible extensibility, identical in shape to "a new accumulator is a new closure."

> **What is Category B (defer):** caching/memoisation policy, thread-safety for parallel DOE, vectorisation internals, and CSV recovery. The *interface* is architectural and must be frozen; the *implementation* is not.

---

## 5. Correlation Signature Philosophy  (resolves O3)

The prompt asks how correlations should receive information. L3 said "(FluidState, declared scalars)" but never chose a concrete shape, and the legacy code shows the failure mode of getting this wrong (positional scalars + `_fluid_name` globals + `hasattr` self-introspection in PyP2PL; whole-`state`-object passing in `MPL_Simulator`).

### Options

**Option A — positional scalars:** `correlation(fluid_state, scalar_1, scalar_2, …)`.

**Option B — role-typed input objects:** `correlation(input)` where `input` is one of a small set of value objects grouped *by correlation role*: `SinglePhaseDPInput`, `TwoPhaseDPInput`, `HTCInput`, `VoidFractionInput`, `VolumePressureLawInput`, … each carrying named fields (the FluidState(s) it needs + the declared geometric/flow scalars `D_h, A, G, roughness, chevron_angle, q''`).

**Option C — pass the whole component/geometry** (the `MPL_Simulator` near-miss). **Rejected up front**: it recouples the correlation to a concrete geometry/component *type*, the exact dependency the DAG forbids (L2 §6).

### Evaluation (A vs B)

| Criterion | A — positional scalars | B — role-typed input objects |
|---|---|---|
| **Readability** | Degrades fast past ~3 args; `f(state, 0.004, 1.2e-5, 350.0)` is unreadable and order-fragile. | High — `HTCInput(state=…, D_h=…, G=…, q_flux=…)` is self-documenting at the call site. |
| **Maintainability** | Adding one input changes *every* correlation signature in that role. | Adding a field is additive; correlations that don't use it are untouched. |
| **Scientific transparency** | Medium — the scalars are visible but unlabelled; reviewers must consult the signature to know what physics is consumed. | High — the input *type* is a written manifest of exactly what a correlation family is allowed to see. A reviewer reads `TwoPhaseDPInput` and knows the closure's entire information diet. |
| **Future extensibility (AD, ML closures)** | Poor — positional scalars are hard to trace coherently; an ML closure must reverse-engineer the arg list. | High — the input object is a struct of traced scalars (AD-friendly); an ML closure (L3 §10) obeys the identical `Input → (value, verdict)` contract; the input doubles as the feature vector. |
| **Decoupling from geometry type** | Preserved (scalars, not objects). | Preserved (the input carries scalars, not a Geometry). The input *is* the concrete realisation of L3's "declared scalars." |
| **Concept-count cost (L1 §1.6)** | Zero new types. | A handful of small value objects — *one per correlation role*, which the architecture already enumerates (L3 §7). Bounded by design; not concept-creep. |
| **Risk** | Order bugs; signature churn; the legacy hacks reappear. | Over-proliferation *if* inputs are made per-correlation instead of per-role. Mitigate by the rule below. |

### Recommendation

**Adopt Option B — role-typed `CorrelationInput` value objects — as the concrete realisation of L3's "(FluidState, declared scalars)."** The return type stays `(value, validity verdict)`.

Guardrails that keep B from becoming concept-creep:
- **One input type per correlation *role***, not per formula. Shah, Gungor-Winterton, and Kim-Mudawar all consume the same `HTCInput`; Friedel and MSH share `TwoPhaseDPInput`. The role set is exactly L3 §7's slot roles — already enumerated, already bounded.
- **The Component builds the input** from its FluidState(s) + the scalars it forwards from its Geometry. This keeps the correlation ignorant of component and geometry *type* (the input is just data) while making the information flow explicit and reviewable.
- **Inputs are immutable, AD-traceable structs.** This is what makes the same contract serve a Shah formula, a structured-FD Jacobian column, and a future ML/property surrogate without special-casing.

This supersedes the positional reading of L3 §3.1/§7 without contradicting its intent — "declared scalars" becomes "a declared, role-typed input object." It is the long-term-maintainable, transparent, AD-ready choice, at the cost of a half-dozen small value types.

> **MASTER action:** state the correlation contract as `evaluate(CorrelationInput) → (value, ValidityVerdict)`, with one `*Input` type per correlation role, built by the component.

---

## 6. Geometry vs Discretization

This was strongly resolved by L2 §5 and L3 §5–6 (geometry = immutable physical scalars; mesh = fidelity, owned by the component's numeric config, *derived from but never stored in* Geometry). I do not reopen it. I only **resolve the boundary cases** the prior documents left implicit, because they are exactly where the two concepts will bleed in code.

### Ownership table (final)

| Quantity | Belongs to | Note |
|---|---|---|
| diameter, hydraulic diameter | **Geometry** | The primary scalar correlations bind to. |
| plate dimensions (chevron angle, spacing, port dims, N_plates) | **Geometry** (`PlateGeometry`) | No single `D`; exposes plate scalars. |
| microchannel dimensions (N_channels, per-channel D_h, fin geometry) | **Geometry** (`MicrochannelGeometry`) | — |
| roughness | **Geometry** | Inert physical fact. |
| flow area, heated area | **Geometry** | — |
| wall thickness, wall mass, material c_p/ρ/k | **Geometry** | Feeds the *frozen* dynamic wall-capacitance term; physical, fixed. |
| **elevation change Δz** | **Geometry** (default) | Fixed for a fixed loop. **Edge case below.** |
| **orientation relative to gravity** | **Geometry** (default) | **Edge case below — relevant to space MPLs.** |
| lumped vs segmented vs moving-boundary mode | **Discretization** | The fidelity axis. |
| number of cells N | **Discretization** | Derived per-cell lengths come from Geometry.L / N. |
| moving-boundary zone count | **Discretization** | *Variable* state count — the one hard case (§9). |

### Two boundary cases worth fixing now

1. **Elevation / orientation vs. gravity.** For a fixed terrestrial loop these are Geometry. But MPLs are frequently *spacecraft* systems, and a maneuvering or variable-g study makes the gravity vector an *operating-point* quantity, not a fixed one. **Recommendation:** Δz and orientation live in Geometry by default (the common case), but the **gravity magnitude/vector is a Scenario input** with a neutral default of 1 g. This keeps `ΔP_gravity = ρ g Δz` with Δz from Geometry and g from Scenario — so a zero-g or transient-g study is a Scenario sweep, not a geometry rebuild. Cheap seam; high relevance to the actual domain.

2. **"Hydraulic diameter" as a derived vs stored geometric scalar.** Some geometries store `D` and *derive* `D_h` (annulus: `D_out − D_in`). **Recommendation:** Geometry may expose `D_h` as a computed *read-only accessor* over its stored primitives — this is geometry computing *its own dimensional algebra*, which is allowed (it is not physics, not state, not a closure). The forbidden line is geometry computing a *correlation* (Nu, ΔP). Keep that distinction explicit in review.

### Recommendation

Ratify L2/L3 unchanged, **plus**: gravity is a Scenario input (default 1 g) while Δz/orientation are Geometry; geometry may expose derived dimensional accessors (e.g. `D_h`) but never physics. Discretization stays a small declared object `{mode, resolution params}` owned by the component's numeric configuration.

---

## 7. Pipe Architecture  (resolves O5)

The prompt's substantive open question for Pipe is the last one: **total pressure drop vs. pressure gradients.** Everything else (geometry by composition; discretization by component numeric config; friction/HTC via slots; gravity & acceleration as physics never calibrated) is settled by the general rules. The gradient question is genuinely open and is a 5-year fork.

### Total ΔP vs. gradients

**Option A — Pipe computes a total ΔP** across the whole component: `ΔP_total = R*·ΔP_friction + ΔP_gravity + ΔP_acceleration`, lumped.

**Option B — Pipe works internally with pressure gradients per cell** (`dP/dx = (dP/dx)_friction + (dP/dx)_gravity + (dP/dx)_acceleration`), integrated over the discretization; the total ΔP is an *output* (the integral), not the primary computational object.

| Criterion | A — total ΔP | B — gradients integrated over discretization |
|---|---|---|
| **Lumped steady** | Direct. | The 1-cell integral — identical result, negligible overhead. |
| **Segmented steady** | Must be re-derived per segment anyway, so a "total" pipe secretly re-implements a per-cell loop. | Native: the per-cell gradient *is* the kernel; the discretization integrates it. |
| **Dynamic** | The dynamic momentum/energy equations are written *per control volume* in gradient form (every paper in `LITERATURE_CORE_ANALYSIS`: Van Gerner, Middelhuis, Truster). A total-ΔP component cannot supply per-CV terms without restructuring. | The per-cell gradient kernel is exactly what the dynamic per-CV equation needs; dynamics *unfreezes* the same cells. |
| **Calibration firewall** | R* multiplies the friction term — fine, but at component granularity only. | R* multiplies the *friction gradient* term — same firewall, finer locality, and physically correct (friction varies along a boiling channel). |
| **Acceleration term** | Bolt-on `ΔP_acc` over the whole length. | Naturally `d(G²v)/dx` per cell — the physically right form, and the one legacy `MPL_Simulator` already computes as a gradient. |
| **Code duplication** | A "total" path and a "segmented" path diverge and drift. | One kernel serves lumped, segmented, and dynamic — the shared 1D-passage mechanism L1 §3 already mandates. |

### Recommendation

**Adopt Option B: all 1D passages (Pipe, and by composition Evaporator/heated-Pipe/Condenser segments) compute pressure *gradients* per control volume; the discretization integrates them; total ΔP is a derived output.** Concretely:

- **Geometry ownership:** by composition (`PipeGeometry`), immutable.
- **Discretization ownership:** the component's numeric config; `Lumped` = 1-cell integration of the identical kernel.
- **Pressure-drop:** per-cell `(dP/dx)_friction` (from the slot correlation) + `(dP/dx)_gravity` (`ρ g dz/dx`, Scenario-g per §6) + `(dP/dx)_acceleration` (`d(G²v)/dx`). Calibration R* multiplies the friction gradient only.
- **Heat-transfer:** per-cell `q''` → local HTC (slot) → wall coupling; lumped = single cell.
- **Gravity & acceleration:** physics, never calibrated (the firewall).
- **Total vs gradient:** **gradient internally, total as output.** This is the choice that makes lumped/segmented/dynamic one kernel and is corroborated by every dynamic reference in the literature and by the surviving legacy gradient code.

> **MASTER action:** state the 1D-passage contract as "contributes per-cell residuals/gradients over its Discretization; total ΔP is derived." This is also the cleanest place to note that the shared 1D mechanism stays *internal* (L1 §3), not a public primitive.

---

## 8. Component State Philosophy  (resolves O6)

The general rule is settled (internal states named from day one, frozen in steady state, unfrozen in dynamics — L1 §10). What is open is the **precise membership test** and one fuzzy case (accumulator pressure).

### Membership test

> **A quantity is component internal state iff the component *stores* it and will provide its time-derivative in dynamics. Everything a component can *recompute* from port unknowns + geometry + correlations is NOT state.**

| Candidate | Component state? | Rationale |
|---|---|---|
| **wall temperature(s)** | **Yes** (per cell, count set by Discretization) | Stored; `C_w dT_w/dt` in dynamics. Frozen in steady. |
| **liquid inventory / fluid mass per cell** | **Yes** | The `∂ρ/∂t` storage term; frozen in steady, primary in dynamics. |
| **vapor inventory** | **Yes** (where tracked separately, e.g. accumulator/condenser zones) | — |
| **gas volume V_g / liquid volume V_l (accumulator)** | **Yes** | The accumulator's true stored states; `dV_g/dt` drives `dP/dt`. |
| **moving-boundary interface positions (condenser)** | **Yes** (variable count — §9) | Stored zone boundaries; the hard dynamic case. |
| **valve position / pump shaft speed (actuator states)** | **Yes** (frozen v1) | Stored actuator dynamics; driven by Scenario commands. |
| **pressure P at a port** | **No** | A port/`SystemState` unknown (§2), globally coupled, set by the network closure — not owned by any single component. |
| **enthalpy h, mass flow ṁ at ports** | **No** | `SystemState` unknowns. |
| **temperature T, quality x, density ρ (derived)** | **No** | Derived by FluidState; never stored (the firewall). |
| **correlation outputs (HTC, ΔP)** | **No** | Recomputed each evaluation; storing them is the legacy `_last_dP/_last_Q` wrinkle the audit flags. |

### The one fuzzy case: accumulator pressure

The accumulator is the "brain" that *sets* the reference pressure, so it is tempting to call `P_sys` its state. **It is not.** Resolution:

- **Stored internal state of the accumulator = V_g (and/or V_l, or gas pressure of the captive gas).**
- **System pressure P_sys is a `SystemState` unknown** that the accumulator's volume↔pressure *law* constrains (steady: `P_sys = P_acc(V_g)`; dynamic: `dP/dt = (nP/V_g)(ṁ_a/ρ_l)` derived from `dV_g/dt`).
- So in dynamics the **stored state is V_g; P is derived** from it through the law. This keeps the single-source-of-truth rule intact even for the one component whose entire job is "owning the pressure," and it matches the L2 §8 split (Component owns the *law*; Network owns *which node*; Solver owns *global consistency*).

### Recommendation

Adopt the membership test verbatim; record that **port (P,h,ṁ) and all derived properties are never component state**, and that **the accumulator stores V_g and derives P** — closing the only ambiguity. Internal-state *names and counts* come from Discretization; the steady solver freezes their derivatives at zero.

---

## 9. Dynamic Readiness Stress Test  (resolves O7; extends L2 §9)

L2 §9 already did a strong dynamic-readiness pass (mesh seam, Jacobian gap, simultaneous assembly, inventory accountant). I do not repeat it. I stress-test specifically against the **3-year MPC / ROM / surrogate** scenario the prompt names, and surface the residual risks that the prior documents *under-stated*.

### Decisions that remain safe under the 3-year scenario (keep)

The (P,h) state, named-frozen internal states, residual/derivative contract, solver-as-DAG-sink, and the §2 `SystemState` ownership all carry directly into dynamics and into linearisation. The §2 recommendation in particular *enables* MPC/ROM, because a flat ordered state vector is precisely what a state-space extraction needs.

### Residual risks the prior documents understate

**A5 — Differentiability is over-promised; and there is no linearisation seam.** *(highest concern)*
L3 §3.4 asserts components are "differentiable across the saturation line" and offers AD as an option. Two physical realities qualify this:
- CoolProp/REFPROP (P,h) flash **derivatives have kinks** at x=0 and x=1 (property slopes are discontinuous across the phase boundary even though properties themselves are continuous). (P,h) buys *continuity*, not *smoothness*.
- **AD through CoolProp is generally unavailable** (it is a compiled external library). So the "AD override" is aspirational for the property path, even if framework-side arithmetic is AD-able.

*Recommendation:*
- Commit to **structured finite differences as the primary sensitivity mechanism** (v1 and likely beyond), with **optional analytic property derivatives from the backend** (§4-item-3) where the backend provides them, and **smoothed/regularised property derivatives near saturation** as the technique for gradient-based MPC. Do **not** write MASTER as if AD is a promised path; write it as "FD now; analytic-where-available; AD is not guaranteed by the property layer."
- **Name a single Sensitivity/Linearisation seam now**, because the Jacobian (for Newton + implicit dynamics), the linearised `(A,B,C,D)` (for MPC/ROM), and the surrogate's input/output gradients are *the same machinery*: given the assembled system, perturb the `SystemState`/Scenario, re-evaluate residuals/outputs, assemble sensitivities. Declaring one contract — "the assembled system can report its ordered states, its inputs (Scenario), its outputs (Result quantities), and its residual/derivative at a point" — serves all three. The §2 `SystemState` makes the state ordering stable and introspectable, which is the precondition. This seam is currently **missing** from all three Levels and is the main thing the 3-year scenario needs that is not yet declared.

**A — Moving-boundary variable state count vs. fixed-size assumptions.** *(structural hazard)*
The condenser's MovingBoundary mode changes its *state count* as zones appear/disappear. If `Network`/`Solver`/`SystemState` interfaces assume a state count fixed at assembly, this becomes a retrofit. *Recommendation:* the `SystemState` size for a MovingBoundary component must be **queryable per step, not frozen at assembly**, and the dynamic solver must support **event detection** (zone appearance/disappearance) as a first-class concept — declared now, implemented in Phase 6. Everywhere else, fixed count is fine.

**C — Pressure changes character (algebraic → state) and the DAE index.** When pressure becomes a state coupled through accumulator compressibility, the system is a **DAE** (algebraic junction/quasi-steady-ΔP equations + differential storage equations), almost certainly index-1. *Recommendation:* (i) keep the **simultaneous/DAE assembly a first-class steady-state option**, not only fixed-point, so the dynamic solver inherits a tested simultaneous assembler (this is L2 §9-C, reaffirmed and made a §2 consequence); (ii) the **steady solution is the consistent initial condition** for the DAE — so the steady and dynamic solvers must share one residual assembly. The §2 `SystemState` + the A5 sensitivity seam make this natural.

**D — Inventory redistribution is a primary dynamic phenomenon.** Reaffirm L2 §9-D: make **global mass inventory a first-class Network quantity from v1** (steady checks total charge; dynamics attaches redistribution equations to the existing accountant). Low risk if done now.

**Fluid inertia parameter for loop momentum.** The dynamic pump/loop momentum `dṁ/dt = (ΔP_pump − ΔP_loop)/I`, `I = L/A` (`TABLA_COMPONENTES` Pump §2) needs an inertia parameter. *Recommendation:* it is derivable from Geometry (L/A) — no new state, just ensure Pipe/Pump geometry exposes the L and A needed. Trivial; name it.

### Verdict

The architecture is **structurally dynamic-ready** on state representation, contracts, and solver decoupling — *and is strengthened* by the §2 state-vector recommendation. The two things the 3-year MPC/ROM scenario needs that are **not yet declared** are: (1) an honest differentiability stance (FD-primary, AD-not-promised), and (2) a single **Sensitivity/Linearisation seam** unifying Jacobian + state-space + surrogate gradients. Both are *declare-the-seam-now* items, not build-now mechanisms.

---

## 10. Final Open Questions — Categories A / B / C

### Category A — must be resolved before ARCHITECTURE_MASTER.md

These change the contracts MASTER is meant to freeze. Each has a recommendation above; what is required is **ratification**.

| ID | Question | Recommendation (from above) | Why it blocks MASTER |
|---|---|---|---|
| **A1** | Port vs PortState — where do unknowns live? (O1, Dec. 002) | **Port = connectivity; solver-owned `SystemState` holds P,h,ṁ + internal states; no cached derived props.** Amends L2 §2.1. | MASTER freezes the Port interface (L3 §1.3-#4) and the stored-vs-derived boundary (#2). Both are wrong-as-written until this is settled. |
| **A2** | Correlation signature shape (O3) | **Role-typed `CorrelationInput` value objects** (one per role), built by the component. | MASTER freezes the Correlation contract (L3 §1.3-#3 implies it). The signature shape must be fixed before INTERFACE_SPEC. |
| **A3** | FluidState: pure value + vector-first backend access (O2) | **Pure `(P,h,identity)` value; vector-first backend queries; mixture-capable identity.** | Sets the Phase-5 performance ceiling and the serialisation unit; both are MASTER-frozen contracts. |
| **A4** | PropertyBackend interface (O4, Dec. 003) | **Vector-first queries + optional derivatives + capability flags + per-identity selection.** Interface frozen; implementations deferred. | Decision 003 is "accepted for architecture review" but the *interface* is unspecified; MASTER's Ch. 5 needs it. |
| **A5** | 1D-passage: gradient vs total ΔP (O5) | **Per-cell gradients integrated over Discretization; total ΔP derived.** | Determines the shared 1D-passage contract MASTER documents (Ch. 7) and the calibration locality. |
| **A6** | Differentiability stance + unified Sensitivity/Linearisation seam (O7) | **FD-primary, analytic-where-available, AD-not-promised; declare one sensitivity seam serving Jacobian + state-space + surrogate.** | MASTER's dynamic-readiness chapter (Ch. 10) currently over-promises AD and omits the linearisation seam the 3-year roadmap needs. |

**Rationale for Category A:** every item alters a contract listed in L3 §1.3 as "must be frozen." Freezing the wrong version is a redesign, not an edit — exactly what the freeze discipline exists to prevent.

### Category B — may be postponed to implementation

Decided in principle; details are implementation, not architecture.

| Item | Why deferrable |
|---|---|
| Junction unification (Splitter/Mixer) and Reservoir-as-component (L3 §1.2-#4) | Affects component count, not contracts. Public aliases keep it cosmetic. |
| PropertyBackend caching/memoisation, thread-safety, vectorisation internals | Hidden behind the pure contract (A4); changeable without breaking callers. |
| Tabulated-CSV recovery (legacy audit §6.3) | A data task; the backend interface is portable without it. |
| Which concrete correlations are ported first; their validity envelopes | Registry contents; config, not architecture. |
| Solver tolerances, damping, event-detection algorithm for moving boundary | Numerics internals; the Solver owns them. |
| Result serialisation format details (beyond "versioned, minimal, tuple-referenced") | Schema detail; the *shape* is frozen (A3/§3), the *bytes* are not. |
| Calibration concrete values and per-slot wiring | Config in the tuple. |

### Category C — should intentionally remain flexible

Freezing these would *cost* future research value.

| Item | Why keep flexible |
|---|---|
| Concrete solver choice (fixed-point vs simultaneous Newton vs future dynamic) | The whole point of the DAG sink: a new solver is a pure addition. Never freeze to one. |
| Concrete PropertyBackend per fluid (CoolProp/REFPROP/tabulated/custom) | Selection is a per-identity tuple binding; locking it defeats the swap seam and the mixture requirement. |
| Correlation catalogue contents | The research seam itself; must stay open by design. |
| Discretization resolution N and mode per component | Fidelity is a per-run choice; the lumped↔segmented↔moving-boundary axis must stay free. |
| Topology (number of branches, evaporators, loop shape) | A Network/tuple edit by definition; never baked in. |
| If/when an AD path is ever added | Aspirational; keep the seam (A6) but never promise the mechanism. |

---

## 11. Architecture Freeze Recommendation

**Verdict: the architecture is ready to be frozen into ARCHITECTURE_MASTER.md *conditionally* — after a single short ratification pass over the six Category-A items.** It is **not** ready to freeze *as currently written*, because (a) Decision 002 is literally still open, (b) L2 §2.1 contains a statement (Port stores the unknowns) that fights the dynamic path, and (c) L3 over-promises differentiability and omits the linearisation seam. None of these is a research blocker — each has a firm recommendation above — so the "blocker" is sign-off, not investigation. If the team accepts the six recommendations as-is, MASTER can be written immediately, incorporating them.

### Blockers (resolve = ratify, all decidable today)

1. **A1 — ratify Port-as-connectivity + solver-owned `SystemState`** (closes Decision 002; amends L2 §2.1). *This is the one with the widest ripple and should be ratified first.*
2. **A2 — ratify role-typed `CorrelationInput` objects.**
3. **A3 — ratify FluidState as a pure value with vector-first backend access and mixture-capable identity.**
4. **A4 — ratify the PropertyBackend interface shape** (vector-first + optional derivatives + capability flags + per-identity selection).
5. **A5 — ratify gradient-based 1D-passage** (total ΔP derived).
6. **A6 — ratify the differentiability stance and the unified Sensitivity/Linearisation seam.**

### Exactly which decisions to freeze and record in MASTER

Once A1–A6 are ratified, MASTER should freeze the following (and *only* the following — everything else stays editable):

**Spine (already mature — §1.1):**
- F1. The one-directional dependency DAG and its forbidden directions (L2 §1).
- F2. (P, h) + identity canonical; everything else derived (Dec. 001).
- F3. Single-source-of-truth ownership: only primary unknowns + named internal states stored.
- F4. Correlations stateless, swappable, selected by name, ignorant of component/topology.
- F5. Calibration at the per-component correlation-output seam; scales closures never balances; resolution slot→component→global.
- F6. PropertyBackend as a Layer-1 FluidState citizen, separate from closure correlations (Dec. 003 principle).
- F7. Network/Component/Solver where/what/how split; one pressure reference; network-level branch closure; single inventory accountant.
- F8. Geometry = immutable flat typed family, composed, shared by reference; mesh excluded.
- F9. Accumulator as first-class component owning the volume↔pressure law (PCA/HCA interchangeable).

**Newly ratified (this document — §2–§9):**
- F10. **Port = connectivity; `SystemState` (solver-owned) stores P, h, ṁ + internal states; no cached derived properties anywhere.** (A1)
- F11. **Correlation contract = `evaluate(CorrelationInput) → (value, ValidityVerdict)`, one input type per role.** (A2)
- F12. **FluidState = pure `(P, h, mixture-capable identity)`; properties served vector-first by the backend; never stored on the state.** (A3)
- F13. **PropertyBackend interface: vector-first queries + optional derivatives + capability flags + per-identity selection; one shared instance per fluid per run; separate registry.** (A4)
- F14. **All 1D passages contribute per-cell gradients/residuals over their Discretization; total ΔP is a derived output; R\* multiplies the friction gradient only.** (A5)
- F15. **Component internal state = stored quantities whose derivatives dynamics will provide; port (P,h,ṁ) and derived properties are never component state; the accumulator stores V_g and derives P.** (§8)
- F16. **Discretization = `{mode ∈ Lumped|Segmented|MovingBoundary, resolution}`, owned by the component numeric config, derived-from but never stored-in Geometry; MovingBoundary state count is queryable per step, not frozen at assembly.** (§6, §9)
- F17. **Gravity is a Scenario input (default 1 g); Δz/orientation are Geometry.** (§6)
- F18. **Sensitivity stance: structured FD primary; analytic property derivatives where the backend provides them; AD not promised. One declared Sensitivity/Linearisation seam serves Jacobian, dynamic implicit integration, and MPC/ROM/surrogate state-space extraction.** (A6, §9)

**Deliberately left unfrozen** (Categories B and C): concrete solver, concrete backends, correlation catalogue, discretization resolution, topology, caching, serialisation bytes, AD mechanism. These are where 5 years of research happens; freezing them would defeat the architecture's purpose.

### Sequencing

The cleanest path: hold one ratification review on A1–A6 (this document is its agenda), record the outcomes as Decisions 004–009 in `DECISION_LOG.md` (Decision 002 is closed by A1), then write ARCHITECTURE_MASTER.md importing F1–F18 as its frozen-decision set. MASTER then proceeds to the four interface documents L3 §12 names (INTERFACE_SPEC, SCHEMA_SPEC, CORRELATION_CONTRACT, TEST_PLAN_V1), now written against the *correct* contracts rather than the ones that would have needed a redesign.

---

*End of OPEN_ARCHITECTURE_QUESTIONS.md — review and resolution only. No MASTER document was created, no implementation plan proposed, and no code written. The recommendation is: ratify the six Category-A items (F10–F18), then ARCHITECTURE_MASTER.md may be written.*
