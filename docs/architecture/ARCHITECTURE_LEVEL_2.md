# ARCHITECTURE_LEVEL_2.md

**Relationships, ownership, dependencies and architectural boundaries of the MPL simulation framework**

Status: architecture definition (pre-implementation), Level 2.
Scope: how the Level 1 concepts interact. **Not** a redefinition of Component, Port, Fluid State, Geometry, Correlation, Calibration, Network or Solver — those are fixed by Level 1 and assumed accepted.
Horizon: 5–10 years; must absorb dynamics, surrogate generation, multiple fluids, multiple HX technologies, alternative accumulators, parallel branches and future control-oriented models without redesign.

This document answers a single question Level 1 deliberately left open: **once the vocabulary exists, who is allowed to know about whom, who owns what, and which way information is permitted to flow.** Getting this wrong is how a clean concept list rots into a coupled monolith over five years. Every decision below is argued to *prevent a specific future coupling*, and Sections 9–10 are deliberately adversarial about where Level 1 itself will leak.

A convention used throughout: **"depend on" means "is allowed to name, import, or hold a reference to, and to break if the other changes."** That is the relationship we are governing.

---

## 1. Dependency Philosophy

The framework is governed by one structural invariant, from which everything else follows:

> **Dependencies flow in one direction only: from inert data, through physics, toward numerics. Nothing that expresses physics may depend on anything that expresses numerics, and nothing that expresses numerics may be depended upon by anything else.**

Concretely, the eight concepts form a strict layered DAG (acyclic — no concept may depend, even transitively, on something that depends on it):

```
Layer 0 (inert):        Geometry        Property Backend
Layer 1 (state):        FluidState  ──── reads ──> Property Backend
Layer 2 (interface):    Port ── delegates ──> FluidState
Layer 3 (closure):      Correlation ── reads ──> FluidState, Geometry
Layer 4 (modifier):     Calibration  (value object; applied *at* Layer 5)
Layer 5 (physics):      Component ── owns ──> Geometry, Correlation slots, Calibration; speaks via Port
Layer 6 (topology):     Network ── holds ──> Components, Connections
Layer 7 (numerics):     Solver ── reads ──> Network (and, through it, Component contributions)
```

The single rule "lower layers never name higher layers" is the whole philosophy. Below is what that means per concept.

### Per-concept dependency contract

| Concept | MAY depend on | MUST NEVER depend on | Rationale |
|---|---|---|---|
| **Geometry** | Nothing (pure dimensional/material data) | FluidState, Port, Correlation, Calibration, Component, Network, Solver | Geometry is inert. The moment geometry knows about flow state or a correlation, it stops being a constant input and becomes a hidden model. Keeping it dependency-free is what lets it be immutable and shared (Section 5). |
| **FluidState** | The property backend only; fluid identity | Geometry, Port, Component, Correlation-as-closure, Network, Solver | FluidState is a *value* — "the fluid at a point". It cannot know *where* it is (Component/Network) or *how it is being solved* (Solver). It must not know geometry: properties of a fluid do not depend on the pipe holding it. |
| **Port** | FluidState | Component, Network, Solver, Correlation, Geometry, Calibration | A Port is an interface that carries (P, h, ṁ) and *delegates* property questions to FluidState. If a Port could name its owning Component or the Network, continuity would stop being a local assertion and become a topological back-reference — the exact coupling that kills the DAE/dynamic path. |
| **Correlation** | FluidState; a minimal *geometric-input contract* (the scalars it needs) | Component, Network, Solver, Calibration, **and the concrete Geometry/Component types** | A correlation is a pure function `(state, required scalars) → one closure number + validity verdict`. It must not know which Component called it (that is what makes it swappable) nor the topology. It depends on the *quantities* `D_h, A, roughness, …`, not on `MicrochannelEvaporator`. See Section 6. |
| **Calibration** | Nothing (named factors + mode; a value object) | Correlation internals, Component physics, Network, Solver | Calibration scales a closure *result*; it is data, not behaviour. It must never be able to reach into a correlation's formula or into a conservation equation — only multiply at the documented seam (Section 7). |
| **Component** | Geometry, FluidState (via Port), Port, Correlation slots, Calibration | Network, Solver, **neighbouring Components** | A Component expresses *local* physics. Knowledge of the topology or of a neighbour is the cardinal sin: it makes the component un-reusable and welds the loop shape into the parts. It also must not know the numerical scheme (Principle 1.3). |
| **Network** | Component, Port (connectivity) | Solver, Correlation, Geometry, FluidState internals | Network states *what must hold* (continuity, closure, one reference). It must not solve, and it must not reach down past the Component interface into correlations or geometry — those are the Component's private business. |
| **Solver** | Network (and Component contributions exposed through it) | — (nothing may depend on the Solver) | The Solver is the sink of the DAG. A new solver must require zero changes anywhere below it. If *anything* depends on the Solver, that "anything" is now solver-specific and a second solver becomes a rewrite. |

### Forbidden directions (the ones that will actually be attempted)

These are not hypothetical; they are the shortcuts a tired implementer reaches for:

- **Correlation → Component** ("the Shah correlation checks if it's in an evaporator"). Forbidden. Breaks swappability, the project's entire research value.
- **Component → Network** ("the splitter asks the network for the other branch's flow"). Forbidden. Branch closure is a *network/solver* condition (Section 8); the component supplies only its local balance.
- **Component → Solver** ("the evaporator knows it is being Newton-iterated / picks a timestep"). Forbidden. Kills the dynamic-solver path (Section 9).
- **Geometry → Correlation** ("the plate geometry computes its own Nu"). Forbidden. Geometry is inert; a geometry that computes physics is a god-object and a maintenance sink.
- **FluidState → Geometry** ("the state knows the channel it's in"). Forbidden. Properties are local to the fluid, not the passage.
- **Anything → Solver.** Forbidden, universally.

The payoff: research happens at exactly two seams — swapping a **Correlation** and editing the **Network** topology — and a *third* engineering seam, swapping the **Solver**. The DAG guarantees each of those three is touchable without disturbing the others.

---

## 2. Ownership Analysis

Dependency answers "who may know whom". Ownership answers "who is the single source of truth for a value, and who is merely allowed to read it". Duplicated ownership is the silent-divergence failure mode (Level 1 Risk #1), so every quantity gets exactly one owner.

### 2.1 Fluid properties

| Quantity | Owner (source of truth) | Stored or derived | Who may read |
|---|---|---|---|
| **pressure P** | **Port** stores the value as a solver unknown; **FluidState** is the canonical interpreter of (P,·) | Stored on Port | Everyone, through the Port/FluidState |
| **enthalpy h** | **Port** stores the value; **FluidState** is the canonical interpreter of (·,h) | Stored on Port | Through the Port/FluidState |
| **mass flow ṁ** | **Port** (a flow/transport variable, *not* part of the thermodynamic state of a point) | Stored on Port | Network (continuity), Component (balances) |
| **temperature T** | **FluidState**, computed from (P,h) | **Derived, never stored** | Anyone, on demand |
| **quality x** | **FluidState**, `x = (h − h_f)/h_fg` | Derived, never stored | Anyone, on demand |
| **density ρ** | **FluidState** | Derived, never stored | Correlations, mass storage (dynamics) |
| **viscosity μ** (and k, σ, c_p, void, phase) | **FluidState** | Derived, never stored | Correlations |

**Ownership rule:** the *only* stored thermodynamic numbers in the whole framework are **P and h on Ports** (plus ṁ as the flow variable, and Component internal states). **Everything a thermal engineer reads off a plot — T, x, ρ, μ — is owned by FluidState and computed on demand.** This is non-negotiable: the moment T or ρ is cached on a Port or Component beside (P,h), it can drift, and the drift is invisible until a balance silently violates. FluidState is the single property authority; Port is the single carrier of the primary variables.

A subtlety worth fixing now: **ṁ is owned by the Port but is *not* part of FluidState.** FluidState is (P,h)+identity — two numbers. The Port carries three numbers. This keeps "the thermodynamic state of the fluid" and "how much of it is moving" cleanly separated, which matters when dynamics makes ṁ a momentum state but leaves (P,h) as the energy state.

### 2.2 Geometry

**Who owns geometry?** Evaluating the three options against the four geometry kinds that actually occur:

- **Option A — Geometry embedded inside components.** Simplest to write. But: (1) it duplicates dimensional logic across components that share a passage shape (heated pipe and evaporator both have a circular channel); (2) it makes geometry impossible to validate or reuse on its own; (3) it forces a correlation that wants `D_h` to reach *into the component*, dragging the component type into the correlation's view — a Section 1 violation. **Rejected.**
- **Option B — Geometry as a standalone concept, held by the component by composition.** Geometry is its own immutable value; the Component owns a *reference* to it; correlations receive the dimensional scalars they need. Reusable, independently testable, decoupled. **Preferred.**
- **Option C — Shared geometry objects across components.** A special case of B: because geometry is immutable, two components *may* point at the same geometry object safely. Useful (e.g. ten identical parallel microchannel evaporators), but must be *allowed*, never *required*. Forcing sharing introduces aliasing surprises. **Adopt as an allowance under B, not as the default.**

**Discussion across the four kinds:**

- **Pipe geometry** — length, hydraulic diameter, flow area, roughness, elevation change. The minimal case; clearly a standalone value.
- **Plate condenser geometry** — plate count, chevron angle, port dimensions, per-plate area, sink-side description. Structurally unrelated to pipe geometry; it exposes *different scalars* to *different correlations* (Yan/Shah condensation want chevron angle and plate spacing, not a single `D`).
- **Microchannel geometry** — channel count, per-channel hydraulic diameter, fin/wall geometry, heated area. Different again.
- **Accumulator geometry** — total volume, gas charge volume (PCA), heater/thermal-control description (HCA). Barely "flow geometry" at all — it is a *containment* geometry.

These four share almost no fields. That is the decisive observation: **there is no universal Geometry god-object, and trying to build one would be exactly the speculative abstraction Principle 1.6 forbids.** Geometry is a **flat family of distinct, typed value objects** — `PipeGeometry`, `PlateGeometry`, `MicrochannelGeometry`, `AccumulatorGeometry` — each exposing precisely the scalars its component's correlations consume, and nothing more.

**Recommendation:** Geometry is **standalone (Option B), immutable, a flat typed family, owned by the Component by composition, and safely shareable by reference (Option C as an allowance).** No inheritance hierarchy, no base "Geometry" with optional fields.

### 2.3 Correlations

**Who owns correlations?**

- **Components own the *selection*** — i.e. each component holds named **slots** ("a boiling-HTC correlation", "a two-phase-ΔP correlation") and decides *which* slots its hardware exposes. The component owns the binding.
- **Correlations themselves are stateless and ownerless as instances** — they are pure functions, so a single registry can hand the same `Shah-boiling` object to every evaporator. The component owns *which name* fills the slot; the registry owns *the catalogue of names*.
- **Geometry must NOT own correlations** — geometry is inert (Section 1).
- **Solver must NOT own correlations** — the solver must work for any valid network and must not know a single formula (Level 1 Risk #2).
- **Network must NOT own correlations** — the network knows topology, not closures.

**Recommendation:** **Components own correlation *slots and selection*; a Correlation Registry owns the *catalogue*; correlations own *no state*.** Selection is configuration, recorded in the reproducibility tuple — never a code edit (Section 6).

### 2.4 Calibration

**Who owns calibration?** Evaluating the four scopes:

- **Global** — one mode/factor for the whole loop. Necessary as the *default policy* and the honest baseline (`none`). Insufficient alone: the evaporator's friction factor and a pipe's are physically different corrections.
- **Per network** — a calibration set attached to one assembled loop. Useful as a reporting/aggregation level, but the *physics* of a calibration is not network-wide.
- **Per component** — a factor attached to a specific component. This is where the *physical* correction lives (Level 1 §9 already concedes this).
- **Per correlation (slot)** — the finest seam: a factor on *this* component's *two-phase-ΔP* output specifically.

**Recommendation:** Calibration is **owned at the per-component correlation slot**, with a **resolution order** that makes the global mode the default and never a parallel mechanism:

> **slot-level factor → component-level factor → global policy (`none`/`target`, default = neutral).**

The factor is *applied* by the Component at the correlation-output seam (Section 7); the global `mode` is a default the configuration resolves; the Network/Solver **aggregate and report** every factor that was non-neutral. Network and Solver never own the calibration *physics* — they own its *reporting*. This gives the v1 simplicity of a global `none`/`target` while making per-component granularity a configuration choice rather than a future redesign.

---

## 3. Data Flow Philosophy

Information moves through the framework in **one assembly pass and one solve loop**, and the reproducibility tuple is the contract between them. Tracing a complete steady-state workflow:

**Stage 0 — User / Experiment configuration.**
*Created:* the **reproducibility tuple** = topology + component parameters + geometries + fluid identity + correlation selections + calibration settings + **scenario/boundary conditions** (heat loads, sink temperature, pump command — see Section 10, this is a concept Level 1 under-names) + solver settings.
*Consumed:* nothing. *Transformed:* user-friendly inputs (subcooling, superheat, °C) are converted **immediately** to canonical (P,h) on entry, so everything downstream sees one representation.

**Stage 1 — Network assembly.**
*Created:* the connection graph; the continuity/closure conditions; the validation verdict (no dangling ports, exactly one pressure reference, branches well-formed).
*Consumed:* components and their declared ports. *Transformed:* a bag of components becomes a *topology with stated invariants* — but **no values are computed**. The Network produces *equations and unknowns*, not a solution.

**Stage 2 — Solver assembly.**
*Created:* the global unknown vector (Port P,h,ṁ across the network + component internal states) and the global residual structure.
*Consumed:* the Network's unknowns/equations and each Component's *contribution contract*. *Transformed:* local contributions + network conditions become one global system. The Solver owns this object; nobody below it sees it.

**Stage 3 — Iteration (the inner loop).** Per trial state, for each Component:
*Consumed:* the (P,h,ṁ) at its ports → a FluidState per port → derived properties on demand.
*Created:* closure numbers, by calling its **Correlations** (which read FluidState + the geometric scalars from its **Geometry**), then applying **Calibration** at the output seam.
*Transformed:* closures + internal states → the component's **residual** (steady) or **derivative** (dynamic). The Solver collects these, checks the global residual + invariants, and updates the trial state. Pressure closure and branch split are enforced *here, globally* — never by a component.

**Stage 4 — Results.**
*Created:* the converged port states; the derived **profiles** (P, h, x, T along the loop, recomputed from FluidState); the **invariant residuals** (energy/mass imbalance, pressure-closure residual, physical-bound checks); and the **calibration report** (every non-neutral factor and its seam).
*Consumed:* the converged unknowns. *Transformed:* raw (P,h) into the engineer-facing, validation-bearing **Result** — which, paired with its reproducibility tuple, is the atomic unit of an experiment for Phase 5.

The shape to notice: **values are created only in Stage 3, and only inside components, and only from data that flows *up* the DAG.** Stages 0–2 move structure, not numbers; Stage 4 moves numbers back out as derived, never-stored views.

---

## 4. State Flow Analysis

Thermodynamic information propagates by **different mechanisms for different variables**, and conflating them is a classic modelling bug.

**How pressure moves.** Pressure is propagated by **momentum/ΔP relations within components** and tied together by a **network-level closure**: the algebraic sum of pressure changes around any closed path is zero. There is exactly **one reference**, set by the accumulator; every other pressure is referred to it. Pressure is therefore *globally coupled* — it cannot be marched component-by-component without a closure correction, which is precisely why loop closure is a Solver/Network responsibility, not a component's (Section 8).

**How enthalpy moves.** Enthalpy is **advected with mass flow** and updated by each component's **energy balance** (`Q = ṁ(h_out − h_in)`), with **equal-enthalpy continuity** at connections. In steady state with a known flow direction, enthalpy propagates *sequentially and locally* — far more local than pressure. This asymmetry (pressure global, enthalpy local) is the reason fixed-point pressure iteration works: iterate the *global* pressure/flow, march the *local* enthalpy.

**How derived properties are obtained.** They are **never propagated.** At any point, T, x, ρ, μ are recomputed from the local (P,h) FluidState. There is no "density field" travelling through the network — only (P,h) travels, and density is a question asked of it locally. This is the single-source-of-truth rule expressed as a flow statement.

**Steady-state vs. future dynamic:**

- *Steady-state:* all storage derivatives are zero. Pressure is an algebraic global closure; enthalpy is algebraic advection; the accumulator sets a fixed reference. The state is found by root-finding.
- *Dynamic:* the same variables, now with storage. Enthalpy gains `∂(ρh)/∂t` (fluid inventory) and wall capacitance `C_w dT_w/dt`; **pressure becomes a true state** coupled through accumulator compressibility (`dP/dt ∝ (n P / V_g)·ṁ_a/ρ_l`), so the global pressure coupling that was an algebraic closure becomes a *dynamic* coupling. Crucially, **the variables do not change** — (P,h) is already what the dynamic energy equation stores, and ρ is already derived. Dynamics *unfreezes derivatives*; it does not introduce a new state representation. The propagation *mechanism* changes (integration vs. root-finding); the *information carried* does not.

---

## 5. Geometry Strategy

This section is load-bearing because geometry is where physics, correlations and discretization are most likely to bleed into each other.

**What Geometry should represent.** The **fixed physical description** of a component's flow passages and solid structure, expressed as exactly the dimensional and material scalars its correlations and conservation laws consume: lengths, (hydraulic) diameters, flow areas, channel/plate counts, heat-transfer areas, wall thickness, material thermophysical constants, roughness, orientation/elevation, containment volumes.

**What Geometry must NEVER represent (the boundaries that will be tested):**
- **Operating state** — no pressure, temperature, flow, quality, void. Geometry is constant for a run.
- **Correlations or physics** — geometry supplies numbers; it never computes Nu, ΔP or void.
- **Time-varying quantities** — none, ever.
- **The mesh / discretization.** *This is the critical and easily-missed boundary.* The number of finite volumes, the moving-boundary zone count, the segmentation policy — these are **numerical fidelity choices**, not physical facts. They are *derived from* geometry (a 1 m pipe divided into 20 segments yields per-segment lengths) but they are **owned by the component's discretization configuration, not stored in Geometry.** Putting the mesh in Geometry would (a) make the immutable, shareable geometry object carry a solver concern, and (b) make a steady-lumped-vs-dynamic-1D switch a *geometry* edit instead of a *fidelity* edit. Keep them separate (this is flagged again as a missing Level 1 concept in Section 10).

**Reusable?** Yes — and reusability is *why* it is immutable. Ten identical parallel evaporators share one geometry object.

**Mutable or immutable?** **Immutable.** A geometry mutated mid-run breaks reproducibility and aliasing safety. If a study varies a diameter, it produces a *new* geometry and hence a *new* reproducibility tuple — exactly what Phase 5 DOE needs.

**How geometry interacts with components.** By **composition**: the component holds a read-only reference and exposes, to its correlations, the specific scalars they declared they need.

**How geometry interacts with correlations.** **One-way, read-only, scalar-level.** The correlation does not receive "the Geometry object" (that would couple it to a concrete type); it receives the quantities it declared — `D_h`, `A`, `roughness`, `chevron_angle`. This keeps a friction correlation usable for a pipe *and* an evaporator channel because both can supply `D_h` and `roughness`.

**Across the examples:**
- **Circular tube** — `{L, D, A, roughness, Δz}`. Single `D` serves as `D_h`.
- **Annular tube** — `{L, D_in, D_out, A, roughness, Δz}`; `D_h = D_out − D_in`. Same correlation family, different geometry type supplying `D_h` differently.
- **Plate heat exchanger** — `{N_plates, chevron_angle, plate_spacing, port_dims, A_per_plate, sink-side}`. No single `D`; exposes plate-specific scalars to condensation correlations.
- **Microchannel evaporator** — `{N_channels, D_h,channel, fin_geometry, A_heated, wall_mass/material}`. Exposes channel count and wall thermal mass (the latter matters for the *dynamic* wall-capacitance term, named now, frozen in steady state).
- **Accumulator** — `{V_total, V_gas_charge (PCA), heater/thermal description (HCA)}`. A containment geometry, not a flow geometry; it still feeds the generic volume↔pressure law.

**Recommended philosophy:** *Geometry is an immutable, standalone, flat family of typed value objects, owned by composition, shared by reference, that supplies declared scalars read-only to correlations and conservation laws — and that explicitly excludes operating state, physics, and the mesh.* The mesh/discretization is a separate fidelity concept living with the component's numerical configuration.

---

## 6. Correlation Architecture

**How correlations are selected.** By **name, from a registry, at configuration time.** A component declares slots; the configuration binds a registered name to each slot; the binding is recorded in the reproducibility tuple. No selection logic lives in code paths that a researcher would have to edit.

**How correlations are replaced.** By **rebinding the slot name** — a configuration change, recorded and reproducible. Replacing Shah with Kim–Mudawar in an evaporator touches the configuration, not the evaporator, not the solver, not neighbouring components. This *is* the replaceability of Principle 1.2, made operational.

**How correlations declare validity ranges.** Each correlation **declares its envelope** (fluid family, geometry range, flow-regime/quality range, Reynolds/Bond bounds). On evaluation it returns its number **and a validity verdict**. The framework **warns on extrapolation; it never silently clamps or extrapolates.** Validity is a *transparency* output, not a correctness guarantee — the researcher decides whether an out-of-envelope use is acceptable, but is never allowed to be unaware of it.

**How correlations interact with geometry.** They receive **declared scalars**, not geometry objects (Section 5). A correlation states "I need `D_h`, `A`, `G` (mass flux)"; the component supplies them. This is the seam that decouples a correlation from any specific geometry *type*.

**How correlations interact with fluid states.** They receive a **FluidState** and read whatever derived properties they need (`ρ_l, ρ_v, μ_l, μ_v, σ, h_fg, …`). They never store the state and never mutate it.

**Should a correlation know…**
- **Component type?** **No.** The whole point is that the correlation does not know whether an evaporator or a heated pipe called it. Coupling here destroys swappability.
- **Geometry type?** **No — it knows geometric *scalars*, not geometry *types*.** It depends on `D_h`, never on `MicrochannelGeometry`.
- **Network topology?** **Absolutely not.** A closure relation has no business knowing how many branches exist.

**Recommendation:** A correlation is a **stateless pure function `(FluidState, declared scalars) → (closure value, validity verdict)`**, selected and replaced by name through a lightweight registry, decoupled from component identity, geometry type, and topology. Calibration is applied to its *output* by the caller, never inside it (Section 7) — so the correlation stays pure physics.

**One important clarification that Level 1 leaves ambiguous (resolved here):** the **property model** (CoolProp/REFPROP/tabulated surrogate) is described in Level 1 as "a correlation family too". Architecturally it is **not** the same kind of object as a closure correlation: it does **not** read geometry, it is **not** held in per-component slots, and it sits at **Layer 1** as the backend of FluidState, not at Layer 3. Both are "named and swappable", but they live in different layers and obey different contracts. Level 2 separates them: **closure Correlations** (HTC, ΔP, void) are Component-slot citizens; the **Property Backend** is a FluidState citizen. Conflating them would force FluidState to depend on the geometry-aware correlation layer — a DAG violation. (See Section 10, finding #1.)

---

## 7. Calibration Architecture

**What gets calibrated, and how.**
- **Pressure-drop calibration** — a multiplier `R*` on the **frictional term only**, per the validation plan: `ΔP_total = R*·ΔP_friction + ΔP_gravity + ΔP_acceleration`. Gravity and acceleration are physics and are **never** scaled. `R*` multiplies the *output* of the ΔP correlation, at the seam, before it enters the momentum balance.
- **Heat-transfer calibration** — an analogous multiplier on the HTC (or on UA), applied at the same kind of output seam, before it enters the energy balance.

**Where calibration lives.** At the **seam between a correlation's raw output and its use in a component's balance**, owned by the **per-component correlation slot**, defaulting through the resolution order of Section 2.4 (`slot → component → global none/target`). This placement has three consequences that are each a design requirement:

1. **Correlations stay pure.** They return physics; calibration scales it afterward. A reader of a correlation never sees a fudge factor.
2. **Conservation is never scaled.** Calibration multiplies *closures* (ΔP_friction, HTC), never *balances* (mass/energy continuity). This is the firewall that makes the next point possible.
3. **Calibration cannot mask an invariant violation.** Because energy and mass balances are computed from un-calibrated conservation, a wrong calibration shows up as a *worse* match to data, never as a *false-passing* energy balance. Calibration can move the operating point; it can never make `Σṁ ≠ 0` look like zero.

**Global vs component vs correlation calibration — recommendation.** Adopt **global `none`/`target` as the default policy and honest baseline**, with the **factor seam addressable per component and per correlation slot** so finer calibration is configuration, not redesign. Dataset-fitting (least-squares over many points) is **not calibration** — it is identification/surrogate territory (Phase 5) and must **route its results back as ordinary explicit factors at this same seam**, never as a parallel hidden mechanism.

**How calibration interacts with validation.** Tightly, and by design:
- Every non-neutral factor, its value, its mode, and its **seam location** are **inputs** in the reproducibility tuple and **outputs** in every Result. The validation acceptance criterion "no hidden empirical correction factors" is enforced structurally: a factor that is not reported cannot exist, because the Result always emits the full factor set.
- A Result produced under `target` mode is **flagged as calibrated, not predictive.** Validation distinguishes a *predictive* claim (`none`) from a *reconciled* one (`target`); the two are never compared as if equal.
- The conservation firewall (point 3 above) means the validation invariants remain a *trustworthy* check even on a calibrated run — which is what lets calibration coexist with validation-first design rather than undermining it.

---

## 8. Network Architecture

The goal is zero duplicated responsibility across Network, Component, Solver. The clean division is **"where / what / how"**:

| Owner | Owns | One-word role |
|---|---|---|
| **Network** | The connection graph; continuity conditions at connections; loop-closure conditions; the **uniqueness** of the pressure reference; branch structure (splitter↔mixer pairing, equal-ΔP branch sets); global mass-inventory accounting; topology validation | **Where** (structure & what-must-hold) |
| **Component** | Its geometry, parameters, internal states, correlation slots, calibration; its **local** balance; the **value/law** of any reference it sets (e.g. accumulator pressure law) | **What** (local physics & values) |
| **Solver** | Assembly of contributions; the numerical scheme; convergence/integration; production of residuals & invariants | **How** (numerics) |

**Branch handling.** Parallel branches between a common splitter and mixer are closed by a **network-level condition**: all parallel branches share the **same ΔP**, and branch flows **sum to the trunk flow**. The Network *states* this set of equations; the Solver *enforces* it; the Splitter/Mixer supply only mass/energy conservation; the branches supply only their resistances. **No component knows another branch exists.** Adding a branch is a topology edit — never a solver or component edit. This is the guard against Level 1 Risk #6 (topology baked into the solver).

**Loop closure.** "Sum of pressure changes around any closed path = 0" is a **Network condition** the **Solver** satisfies. No single component "closes the loop"; closure is emergent and global. This is the embodiment of the pressure-is-global / enthalpy-is-local asymmetry of Section 4.

**Pressure-reference management.** The Network's topology validator enforces **exactly one** pressure reference. The **Accumulator component** owns the *law and value* that sets the reference (PCA polytropic / HCA saturation, behind one generic volume↔pressure interface); the **Network** owns *which node* is the reference and wires it; the **Solver** owns *making the rest of the field consistent* with it. Three owners, three non-overlapping responsibilities — the anti-duplication objective met exactly.

**Accumulator interaction.** The accumulator is a first-class Component (so its dynamic derivative law activates without structural change — Section 9), but its *reference role* is a Network wiring fact. The split is: **Component = the pressure-setting law; Network = the wiring and the one-reference invariant; Solver = global consistency.** A second accumulator is therefore caught by topology validation, not discovered as a numerical pathology.

A boundary to state explicitly (Section 10, finding): **Reservoir and Accumulator must not both claim inventory/reference ownership.** The **Accumulator sets the pressure reference**; the **Reservoir holds liquid inventory and guarantees NPSH but sets no reference.** Global mass-inventory accounting is the **Network's** single responsibility, reading each component's stored mass; no component double-counts it.

---

## 9. Dynamic Readiness Review

**Decisions that already support dynamics (keep):**
1. **(P,h) primary state** — already the variable the dynamic energy equation stores; density derived. Dynamics adds equations, not a representation.
2. **Internal states named even when frozen** — wall capacitance, gas/liquid volumes, fluid inventory, moving-boundary positions are named now (Section 6 of Level 1 lists them per component), derivatives held at zero. Unfreezing is activation, not invention.
3. **Component contract = residual *and/or* derivative** — same contract, different solver.
4. **Solver behind a stable interface** — the dynamic solver is an *additional* sink on the DAG, touching nothing below it.
5. **Non-directional ports** — the simultaneous/DAE formulation dynamics needs is already expressible; inlet/outlet is annotation, not constraint.
6. **Accumulator as a real component** — the "brain" needs only its derivative law activated.

**Decisions that may create future problems (address now, build later):**

- **A. The mesh/discretization seam is unowned (highest concern).** Steady-state components are described at mixed fidelity (condenser "lumped 0D or multi-segment", accumulator 0D, evaporator 1D). The dynamic models need **1D finite-volume** (evaporator/pipe) and **moving-boundary** (condenser) structures whose *state count changes*. If discretization is not an explicit, declared fidelity axis from day one (Section 5), the moving-boundary condenser is a **state-structure retrofit**, not an activation. *Recommendation:* introduce **discretization/mesh as an explicit component-fidelity concept now** (lumped ↔ segmented ↔ moving-boundary as a declared mode), even if only the lumped/segmented modes are implemented in v1. Prepare the seam; defer the mechanism.

- **B. No Jacobian/derivative-provision contract.** Simultaneous Newton (offered as a steady-state alternative) and *implicit* dynamic integrators (needed for stiff two-phase problems) both require a **Jacobian**. The current contract returns residuals/derivatives only — it is silent on how sensitivities are produced (finite-difference, analytic, or automatic differentiation). If this is left implicit, the first stiff problem forces an awkward bolt-on. *Recommendation:* decide the **derivative-provision policy** (most likely: components return residuals; the framework obtains the Jacobian by AD or structured finite differences) as a named Level 3 contract, and ensure component contributions are written so AD is possible (no hidden non-differentiable branches at phase transitions — which (P,h) already helps with).

- **C. Pressure changes character (algebraic → state) at the accumulator.** In steady state the reference pressure is an algebraic boundary; in dynamics system pressure is a *state* coupled to *every* component through compressibility. The "named-but-frozen state" device covers the accumulator's own `V_g`, but the **global coupling pattern** changes. This is manageable because pressure is already treated as globally coupled (Section 4), but Level 3 must not assume the steady-state *sequential* pressure march generalizes — the dynamic path is inherently simultaneous. *Recommendation:* keep the simultaneous/DAE formulation a first-class steady-state option (not only fixed-point), so the dynamic solver inherits a tested simultaneous assembly.

- **D. "Global mass inventory when required" is too tentative.** In dynamics, inventory redistribution between condenser, accumulator and reservoir is a *primary* phenomenon, not an occasional add-on. *Recommendation:* make **global mass inventory a first-class Network quantity from v1** (even if steady-state only checks total charge), so the dynamic inventory equations attach to an existing accountant rather than introducing one.

**Verdict:** the Level 1 architecture is *structurally* dynamic-ready on state representation, contracts, and solver decoupling. The four gaps above are **seam-preparation gaps, not redesign gaps** — each is addressable now by *declaring a seam* (mesh fidelity, Jacobian policy, simultaneous assembly, inventory accountant) without building the dynamic mechanism.

---

## 10. Architecture Consistency Audit

A deliberately critical pass over Level 1.

**Hidden inconsistencies:**

1. **Property model: backend or correlation? (most important).** Level 1 calls the property model "a correlation family" (§2.5, §8) yet also makes it the backend FluidState "delegates to" (§2.3). These are incompatible layers: a closure Correlation reads geometry and lives in component slots; the property backend reads neither geometry nor topology and lives under FluidState. **Resolution (Section 6):** treat the **Property Backend as a Layer-1 citizen of FluidState**, distinct from Layer-3 closure Correlations. Both are "named and swappable", but they are not the same concept. Left unresolved, FluidState would have to depend on the geometry-aware correlation layer — a DAG cycle.

2. **Reservoir vs. Accumulator inventory/reference overlap.** Both are described as managing inventory and (the accumulator) the reference. Without an explicit rule this duplicates ownership of mass inventory and risks two pressure references. **Resolution (Section 8):** Accumulator sets the *one* pressure reference; Reservoir holds inventory/NPSH and sets *no* reference; the Network is the *single* inventory accountant.

3. **Calibration: "global mode" vs "per-component seam".** Level 1 §9 simultaneously adopts a global `none`/`target` and asserts the seam is per-correlation. **Resolution (Section 2.4/7):** a resolution order (`slot → component → global`) makes these one mechanism, not two.

4. **ṁ: state or not?** Ports "store P,h,ṁ" while FluidState is "(P,h)". Mostly consistent but worth stating outright (done in Section 2.1): the Port carries three numbers; FluidState reads two; ṁ is a flow variable, never part of the thermodynamic state.

**Future bottlenecks:**

- **Property-backend call cost in the inner loop.** Thousands of CoolProp/REFPROP calls per iteration × thousands of Phase-5 runs is a real performance wall. Level 1 names the tabulated surrogate as the guard — *keep it a first-class, early capability*, not a late optimization, because surrogate generation (Phase 5) depends on it.
- **Jacobian assembly (Section 9-B).** The contract's silence on sensitivities is the most likely numerical bottleneck for both simultaneous-Newton steady state and stiff dynamics.
- **State-structure changes at moving-boundary (Section 9-A).** The condenser's variable zone count is the most likely dynamic bottleneck.

**Likely sources of technical debt:**
- A **Geometry god-object** if the flat-family discipline (Section 5) slips into an inheritance hierarchy with optional fields.
- **Correlations receiving whole Component/Geometry objects** instead of declared scalars — re-coupling the layer the architecture worked to separate.
- **Calibration drifting toward conservation terms** if the "scale closures, never balances" firewall is not enforced in code review.

**Unnecessary abstractions / things to question (be critical):**
- **Splitter and Mixer as two distinct components** may be premature dualization of one **Junction** concept (n-in/m-out conservation node). Worth deciding in Level 3 whether they are two components or one parametrized junction — the literature's "matrix-based branch distribution" treats them uniformly.
- **Reservoir "where distinct from accumulator"** is conditionally-existing, which is a smell. Either it is a distinct component (inventory/NPSH, no reference) or it is an accumulator configuration. Section 8 picks the former; Level 1's hedging should be removed.
- The **shared 1D segmented-passage mechanism** is justified (two+ consumers) and should stay *internal* — but it must not quietly become a public abstract primitive (the Option-B trap Level 1 already rejects).

**Missing concepts (the most actionable output of this audit):**
1. **Discretization / Mesh** — a fidelity axis (lumped ↔ segmented ↔ moving-boundary), owned by the component's numeric configuration, *derived from* but *not stored in* Geometry. Absent from Level 1's eight concepts yet present in the roadmap ("geometry and mesh objects"). **Add it as an explicit seam now.**
2. **Scenario / Boundary Conditions** — heat loads, sink temperature/flow, pump command, ambient. These are neither geometry, nor state, nor correlation; they are the *operating point* a run is evaluated at, and they are the **primary DOE input axis for Phase 5**. Level 1 folds them into "component inputs", but a surrogate dataset needs them as a first-class, varied, recorded concept. **Name it.**
3. **Result / Solution** — the output object (profiles + invariant residuals + calibration report), paired with its reproducibility tuple as the atomic experiment unit. Level 1 carefully defines the *input* tuple but never names the *output*. Phase 5 cannot batch what it cannot name. **Name it.**
4. **Property Backend as a layer** distinct from closure Correlation (finding #1).
5. **Derivative/Jacobian provision contract** (Section 9-B).
6. **Reproducibility tuple / Experiment configuration** as an explicit concept — referenced throughout Level 1 but never made first-class; it is the natural home for fluid, correlation selections, calibration, scenario and solver settings, and the key to reproducible surrogate generation.

None of these six contradicts Level 1; each fills a gap that would otherwise be improvised inconsistently across the codebase.

---

## 11. Final Recommendations

Ranked within each tier by importance (most important first).

### A. Approved — adopt as Level 2 decisions, carry into Level 3

1. **The one-directional dependency DAG** (Section 1): data → physics → numerics; nothing depends on the Solver; no concept depends on a higher layer. *This is the most important decision in the document — every other guard derives from it.*
2. **Single-source-of-truth ownership** (Section 2.1): only P, h (and ṁ) are stored, on Ports; all of T, x, ρ, μ are derived by FluidState and never stored.
3. **Three research/engineering seams and only three:** swap a Correlation (config), edit the Network (topology), swap the Solver (engineering). Everything else is stable.
4. **Geometry = immutable, standalone, flat typed family, composed, shareable; mesh excluded** (Section 5).
5. **Correlations = stateless pure functions of (FluidState, declared scalars); selected/replaced by name; ignorant of component, geometry type, and topology** (Section 6).
6. **Calibration at the per-component correlation-output seam, scaling closures never balances, with the conservation firewall and full reporting** (Section 7).
7. **Network/Component/Solver "where / what / how" split**, with one pressure reference, network-level branch closure, and a single inventory accountant (Section 8).

### B. Requires further discussion before Level 3 closes

1. **Property Backend vs. closure Correlation** — confirm the two-layer separation (Section 6 / 10-#1). *High importance: it is a latent DAG cycle.*
2. **Derivative/Jacobian provision policy** (AD vs. structured FD vs. analytic) and the requirement that component contributions be differentiable across phase transitions (Section 9-B). *High importance for both Newton steady state and stiff dynamics.*
3. **Discretization/Mesh as an explicit component-fidelity seam**, including the lumped↔segmented↔moving-boundary modes (Sections 5, 9-A, 10-#1). *High importance for the dynamic path.*
4. **Scenario / Boundary-Condition concept** and **Result/Solution concept** as first-class citizens (Section 10-#2,3). *High importance for Phase 5; cheap to add now, expensive to retrofit.*
5. **Calibration resolution order** (`slot → component → global`) — confirm as the reconciliation of Level 1's global-mode vs. per-component-seam tension (Section 2.4).
6. **Splitter+Mixer vs. a single Junction concept; Reservoir as a real component vs. an accumulator configuration** (Section 10). *Medium importance; affects component count, not architecture.*

### C. Postponed — prepare the seam, defer the mechanism

1. **Dynamic mechanisms:** time integrator, moving-boundary equations, wall-conduction networks, dynamic inventory redistribution (Phase 6). Seams: named internal states, derivative contract, mesh fidelity, inventory accountant, simultaneous assembly — all prepared now.
2. **Surrogate/identification tooling and dataset-fitting** (Phase 5), routing its outputs back through the explicit calibration seam.
3. **Control-oriented linearization / reduced-order / MPC state-space generation** (Phase 7).
4. **Simultaneous-Newton steady solver** as a drop-in alternative to fixed-point — built behind the existing component contract when needed.

### Handoff to ARCHITECTURE_LEVEL_3

Level 3 (implementation strategy, interfaces, class organization) inherits from this document: a **fixed dependency DAG** it must not violate; a **clear ownership map** per quantity; **three sanctioned seams**; and a **short, ranked list of concepts to formally add** before interfaces are drawn — Property Backend (as a layer), Discretization/Mesh, Scenario/Boundary Conditions, Result/Solution, the Reproducibility tuple, and the Derivative/Jacobian contract. The single instruction to Level 3 is: *draw interfaces that make the forbidden dependency directions impossible to express, and the three seams trivial to use.*
