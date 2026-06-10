# ARCHITECTURE_LEVEL_3.md

**Implementation-readiness architecture: objects, interfaces, responsibilities and seams of the MPL simulation framework**

Status: architecture definition (pre-implementation), Level 3 — the last document before interfaces are drawn and code is written.
Scope: *what objects must exist, what they promise, and along which seams the system is allowed to evolve.* Not redefinition of Level 1/Level 2 concepts (those are fixed and accepted); not equations, not code, not UML.
Horizon: 5–10 years — steady-state now; dynamics, surrogate generation, multiple fluids/HX/accumulator technologies, arbitrary topologies, and control-oriented models as additions along prepared seams.

This document inherits, without re-arguing:

- the **eight Level 1 concepts** (Component, Port, FluidState, Geometry, Correlation, Calibration, Network, Solver) and their responsibilities;
- the **Level 2 dependency DAG** (data → physics → numerics; nothing depends on the Solver), the **single-source-of-truth ownership map** (only P, h, ṁ stored, on Ports; T/x/ρ/μ derived by FluidState), the **three sanctioned seams** (swap a Correlation, edit the Network, swap the Solver), and the **six concepts Level 2 instructed Level 3 to formalize**: Property Backend (as a layer), Discretization/Mesh, Scenario/Boundary Conditions, Result/Solution, the Reproducibility Tuple, and the Derivative/Jacobian contract.

The single instruction Level 2 handed down governs every choice here: *draw interfaces that make the forbidden dependency directions impossible to express, and the three seams trivial to use.*

---

## 1. Final Architecture Review

A frozen-vs-uncertain classification of every prior decision, so the team knows what it is allowed to revisit and what it must build on.

### 1.1 Decisions now considered STABLE (do not reopen)

| Decision | Source | Why stable |
|---|---|---|
| Eight-concept vocabulary; physical components on a thin shared 1D-passage core | L1 §2, §3 | Validated against the literature's component taxonomy (TABLA_COMPONENTES) and the engineer-facing requirement. No new evidence contradicts it. |
| (P, h) + identity as canonical FluidState; all else derived | L1 §4, L2 §2.1 | Universal literature consensus (Van Gerner, Middelhuis, Truster, Kokate all carry P/h). Continuity across the saturation dome is non-negotiable. |
| Ports carry exactly (P, h, ṁ); non-directional continuity | L1 §5, L2 §2.1 | Minimal sufficient interface; matches the DAE/dynamic path requirement. |
| One-directional dependency DAG; nothing depends on the Solver | L2 §1 | The keystone. Every other guard derives from it. |
| Single-source-of-truth ownership (stored: P,h,ṁ + internal states; derived: everything else) | L2 §2.1 | Directly prevents the #1 silent-divergence failure mode. |
| Correlations = stateless pure functions of (FluidState, declared scalars); selected by name | L1 §8, L2 §6 | The project's core research seam; no reason to weaken it. |
| Calibration at the per-component correlation-output seam; scales closures never balances; resolution order slot → component → global | L1 §9, L2 §2.4, §7 | The conservation firewall makes validation trustworthy under calibration. Frozen. |
| Network/Component/Solver "where / what / how" split; one pressure reference; network-level branch closure; single inventory accountant | L2 §8 | Eliminates duplicated responsibility; no open question remains. |
| Property Backend is a Layer-1 citizen of FluidState, distinct from Layer-3 closure Correlations | L2 §6, §10-#1 | Resolves the only latent DAG cycle in Level 1. Frozen here. |

### 1.2 Decisions still UNCERTAIN (resolved in this document, flagged for sign-off)

These were left open by Level 2 §B ("requires further discussion before Level 3 closes"). Level 3 takes a position on each; the team confirms or overrides before coding.

1. **Derivative/Jacobian provision policy** — Level 2 named the gap but did not choose. *Resolved in §3.4 and §6:* components expose a residual/derivative contract written to be **differentiable across phase transitions**; the framework obtains the Jacobian by **structured finite differences in v1, with analytic/AD as an optional per-component override**. The contract is named now; only the FD assembler is built now.
2. **Discretization/Mesh as an explicit fidelity seam** — *Resolved in §6:* Discretization is a first-class concept owned by the component's numeric configuration, derived from Geometry, never stored in it. Modes `Lumped | Segmented | MovingBoundary` are declared in the interface from day one; only `Lumped`/`Segmented` are implemented in v1.
3. **Scenario/Boundary-Conditions and Result/Solution as first-class concepts** — *Resolved in §2, §8, §9:* both are added to the concept inventory.
4. **Splitter+Mixer vs. a single Junction; Reservoir as component vs. accumulator config** — *Resolved in §4:* a single parametrized **Junction** (n-in/m-out conservation node) with `Splitter`/`Mixer` as configurations of it; **Reservoir is a distinct component** (inventory/NPSH, no reference), removing Level 1's "where distinct from accumulator" hedge.

### 1.3 Decisions that must be FROZEN before implementation begins

These are not uncertain — they are decided — but they must be **locked** because a late change to any of them is a redesign, not an edit. The team should explicitly ratify this list as immutable for v1:

1. The **dependency DAG and its forbidden directions** (§3). This is the contract that the interfaces must make *unrepresentable to violate*.
2. The **stored-vs-derived ownership boundary** (only P, h, ṁ + named internal states are stored).
3. The **Component contribution contract** signature shape — residual *and/or* derivative, plus declared internal-state names and the differentiability promise (§3.1, §6). Adding dynamics must not change this signature.
4. The **Port interface** (P, h, ṁ; non-directional connect). Changing it later ripples through every component.
5. The **Reproducibility Tuple schema** as the serializable unit of an experiment (§8). Phase 5 batch generation depends on it being stable and versioned.

Rationale for freezing these five and no more: they are exactly the interfaces that *other* code is written against. Everything else (correlation formulae, geometry field lists, solver internals, result reporting detail) can grow without breaking callers, so it need not be frozen.

---

## 2. Final Concept Inventory

The definitive list. Level 1's eight concepts, plus the **five** Level 2 instructed us to formalize (Property Backend, Discretization/Mesh, Scenario, Result, Reproducibility Tuple), plus the **Correlation Registry** and **Junction** as the two genuinely-needed structural objects. **Thirteen concepts total — no more.** Anti-concept-explosion is itself a requirement (L1 §1.6): anything not on this list does not get a class.

The Derivative/Jacobian "concept" from Level 2 is deliberately **not** a separate object — it is a *contract on Component and Solver* (§3.4), not a thing that exists at runtime. Promoting it to an object would be the speculative generality L1 §1.6 forbids.

For each concept: **purpose / owner / lifecycle / interactions.**

### Group A — Value objects (inert, immutable, Layer 0–1)

**FluidState** — *Purpose:* the thermodynamic state of the fluid at a point, anchored on (P, h) + identity; single source of truth for all derived properties. *Owner:* created transiently by whoever holds a Port's (P,h); not owned long-term. *Lifecycle:* ephemeral — constructed on demand from (P,h), discarded; never cached on a Port or Component. *Interactions:* reads the **Property Backend**; consumed by **Correlations** and by **Component** balances.

**PropertyBackend** — *Purpose:* the swappable property engine (CoolProp / REFPROP / tabulated surrogate) that answers property queries for a FluidState. *Owner:* the simulation configuration (one backend instance per fluid, shared). *Lifecycle:* constructed once per run from the Reproducibility Tuple; long-lived; stateless w.r.t. the solve. *Interactions:* serves **FluidState** only. Reads neither Geometry nor topology. **This is the resolution of Level 2's latent DAG cycle: PropertyBackend is Layer 1, never a Layer-3 closure Correlation.**

**Geometry** — *Purpose:* the fixed dimensional/material description of a component's passages and structure, as a flat typed family (`PipeGeometry`, `PlateGeometry`, `MicrochannelGeometry`, `AccumulatorGeometry`, …). *Owner:* the **Component**, by composition (read-only reference; shareable across components). *Lifecycle:* immutable for the whole run; a varied dimension produces a *new* Geometry and a *new* tuple. *Interactions:* supplies **declared scalars** (not itself) to Correlations and to the component's balance. Excludes operating state, physics, and the mesh.

**Calibration** — *Purpose:* named multipliers (default neutral = 1) that scale closure *outputs* at the documented seam, with a mode (`none`/`target`). *Owner:* the per-component correlation slot, resolving slot → component → global. *Lifecycle:* fixed per run; part of the tuple; reported in every Result. *Interactions:* applied *by the Component* between a Correlation's raw output and its use in a balance. Touches nothing else.

**Scenario / BoundaryConditions** *(formalized per L2 §10-#2)* — *Purpose:* the **operating point** at which a Network is evaluated: heat loads, sink temperature/flow, pump command, ambient. Neither geometry, nor state, nor correlation. *Owner:* the Reproducibility Tuple (it is an input axis), applied to components as boundary inputs at solve time. *Lifecycle:* one Scenario per run; **the primary varied axis for Phase-5 DOE**. *Interactions:* read by the **Solver** as the boundary inputs that close the otherwise-underdetermined system; bound to specific components (which evaporator gets which Q, which condenser sees which sink).

**ReproducibilityTuple / ExperimentConfiguration** *(formalized per L2 §10-#6)* — *Purpose:* the serializable, versioned tuple that fully determines a run = topology + component parameters + geometries + fluid identity + correlation selections + calibration + scenario + solver settings. *Owner:* the user/experiment layer; it is the atomic *input* unit of an experiment. *Lifecycle:* authored once, immutable, versioned, archived alongside its Result. *Interactions:* consumed by Network assembly, Solver, and the PropertyBackend selection; emitted (by reference) inside every Result. **No run may depend on anything outside this tuple** (L1 §1.7).

### Group B — Interface and physics objects (Layer 2–5)

**Port** — *Purpose:* the connection interface carrying exactly (P, h, ṁ); delegates property questions to FluidState. *Owner:* the **Component** that declares it. *Lifecycle:* lives with its component; its (P,h,ṁ) values are solver unknowns. *Interactions:* connected to other Ports by the Network (non-directional equality of P, h; mass balance of ṁ).

**Correlation** — *Purpose:* one stateless closure relation `(FluidState, declared scalars) → (value, validity verdict)`: HTC, two-phase ΔP, void fraction. *Owner:* instances owned by the **Correlation Registry**; *selection* owned by the Component's slot. *Lifecycle:* registered at startup, immutable, shared by reference across all components. *Interactions:* reads FluidState + scalars; ignorant of component, geometry type, topology, solver, and calibration.

**Component** — *Purpose:* local physics of one physical element; produces residuals (steady) and/or internal-state derivatives (dynamic) from its port states + internal states. *Owner:* the **Network**, by composition. *Lifecycle:* constructed from the tuple; holds geometry, parameters, internal-state *names*, correlation slots, calibration, and a Discretization. *Interactions:* speaks only via its Ports and its Correlations; never names a neighbour, the Network, or the Solver.

**Discretization / Mesh** *(formalized per L2 §9-A, §10-#1)* — *Purpose:* the **fidelity axis** of a component: `Lumped | Segmented | MovingBoundary`. Determines the *count and structure* of a component's internal states. *Owner:* the **Component's numeric configuration** (not Geometry, not Solver). *Lifecycle:* fixed per run; *derived from* Geometry (a 1 m pipe at 20 segments → per-segment lengths) but **never stored in Geometry**. *Interactions:* tells the Component how many internal states/residuals it contributes; the Solver sees only the resulting unknown count. Switching lumped↔segmented is a *fidelity edit*, not a geometry or solver edit. **This is the single most important new seam for the dynamic path.**

### Group C — Structural and numerical objects (Layer 6–7)

**Junction** *(resolves L2 §10 Splitter/Mixer question)* — *Purpose:* the n-in/m-out conservation node (mass + energy balance, equal pressure at the node). `Splitter` and `Mixer` are *configurations/aliases* of one Junction, not two classes. *Owner:* the Network. *Lifecycle:* per run. *Interactions:* supplies only conservation; branch *resistances* come from the branches, branch *closure* (equal ΔP) is a Network condition.

**Network** — *Purpose:* the assembled topology; states continuity, loop-closure, the one-reference invariant, branch structure, and global mass inventory. *Owner:* the experiment/run. *Lifecycle:* assembled from the tuple, validated, then handed to a Solver. *Interactions:* holds Components + Connections; exposes unknowns/equations to the Solver; never solves, never reaches past the Component interface.

**Solver** — *Purpose:* the numerics — assemble the global system, drive to convergence (steady) or march in time (dynamic), produce residuals + invariants. *Owner:* the run (chosen from the tuple's solver settings). *Lifecycle:* per run; the sink of the DAG. *Interactions:* reads Network + Component contributions; **nothing depends on it**. A new Solver requires zero changes below it.

**Result / Solution** *(formalized per L2 §10-#3)* — *Purpose:* the output object: converged port states, derived profiles (P, h, x, T along the loop), invariant residuals (energy/mass/pressure-closure, physical-bound checks), and the calibration report — paired with its Reproducibility Tuple. *Owner:* produced by the Solver, owned by the experiment archive. *Lifecycle:* immutable once produced; **the atomic unit Phase 5 batches over**. *Interactions:* consumes converged unknowns; derives everything else through FluidState (never stores T/x/ρ redundantly).

> **Why exactly thirteen.** Eight (L1) + Property Backend, Discretization, Scenario, Result, Reproducibility Tuple (L2's five) = thirteen, with Correlation Registry and Junction folded in as the registry-of-correlations and the unification-of-splitter/mixer rather than as net-new ideas. The Derivative/Jacobian and the "shared 1D passage" remain **contracts/mechanisms, not concepts** — they get interfaces, not their own top-level objects. This is the bar from L1 §1.6 held firm.

---

## 3. Interface Philosophy

For the five load-bearing interfaces: what each **must provide**, must **consume**, and must **never access**. No code — these are contracts.

### 3.1 Component

- **Must provide:** its declared **Ports**; its declared **internal-state names** (even when frozen at zero — the dynamic-readiness device, L1 §10); on request, its **contribution** = the residual equations (steady) and/or the time-derivatives of its internal states (dynamic), evaluated at a *given* trial state; its **correlation slot declarations** (which closures it needs, by role); the **calibration factors actually applied** (for reporting); and its **declared scalar requirements** passed through to correlations.
- **Must consume:** the (P, h, ṁ) at its Ports (as a trial state handed in by the Solver); its own Geometry, parameters, Discretization, internal states, and the Scenario inputs bound to it (e.g. its heat load).
- **Must never access:** the Network topology or any neighbouring Component; the Solver or its numerical scheme (no Newton-awareness, no timestep); a Correlation's internal formula; the PropertyBackend directly (it goes through FluidState); global mass-inventory accounting (that is the Network's).

**Contract shape (the frozen signature, §1.3):** "Given a trial state at my Ports and my internal states, return my residual vector and/or my internal-state derivatives, written so they are continuous and differentiable across the saturation line." That last clause is the §3.4 differentiability promise, stated as part of the Component contract from day one.

### 3.2 Correlation

- **Must provide:** exactly one closure number (α, ΔP, ε_void, …) **plus a validity verdict** (in-envelope / extrapolated, with the envelope it checked against).
- **Must consume:** a **FluidState** and the **declared scalars** it announced it needs (`D_h`, `A`, `G`, `roughness`, `chevron_angle`, …) — scalars, never a Geometry object.
- **Must never access:** which Component called it (the basis of swappability); the Geometry *type*; the Network; the Solver; the Calibration (calibration scales its *output*, applied by the caller); any mutable or stored state — it is a pure function and stores nothing.

### 3.3 PropertyBackend

- **Must provide:** thermophysical properties for a given (P, h, identity) — T, T_sat, x, ρ, μ, σ, k, c_p, phase, and the saturation anchors (h_f, h_g, h_fg) FluidState needs to compute quality.
- **Must consume:** (P, h) and the fluid identity, nothing more.
- **Must never access:** Geometry, Port, Component, Network, Solver, or a closure Correlation. It sits *below* FluidState and is the only thing FluidState depends on. This containment is what keeps it swappable (CoolProp → REFPROP → tabulated surrogate) without touching physics — and is decisive for Phase-5 performance (the tabulated surrogate is a first-class early capability, L2 §10).

### 3.4 Solver

- **Must provide:** a converged state (or an integrated trajectory); residuals, iteration counts, convergence status; and the **validation invariants** (energy/mass imbalance, pressure-closure residual, physical-bound checks) as first-class outputs feeding the Result.
- **Must consume:** the Network's unknowns + equations and each Component's contribution contract; the Scenario's boundary inputs; the solver settings from the tuple. To build a Jacobian (for simultaneous-Newton steady state or implicit dynamics) it consumes **sensitivities** — and here is the resolved policy: **the Solver obtains the Jacobian itself, by structured finite differences over the Component contract in v1**, optionally accepting an analytic/AD Jacobian a Component *may* provide as an override. Components are *not* required to provide derivatives of their residuals — only to be *differentiable* (no hidden non-smooth branches at phase transitions, which (P,h) already buys).
- **Must never access:** any physics, correlation, geometry, or property formula. It must work for *any* valid Network. This is the universal forbidden direction: **nothing depends on the Solver, and the Solver depends on no physics detail.**

### 3.5 Network

- **Must provide:** the full set of unknowns (Port P,h,ṁ + component internal states) and the equations that must hold (per-component contributions assembled by reference, plus continuity, loop-closure, one-reference, branch equal-ΔP, global mass inventory); a **topology validation verdict** (no dangling ports, exactly one pressure reference, well-formed splitter↔mixer branch sets, no double-counted inventory).
- **Must consume:** Components and their declared Ports/connections from the tuple.
- **Must never access:** the Solver; a Correlation; a Geometry; FluidState internals. It states *what must hold*, never *how to make it hold*, and never reaches past the Component interface.

> The unifying rule across all five: **each interface exposes the minimum that its consumers up the DAG need, and accepts only what flows up to it.** An interface that makes a forbidden direction *inexpressible* (e.g. a Correlation that is handed scalars and a FluidState, never a Component) is the design goal — the compiler/type system should refuse the coupling, not a code reviewer.

---

## 4. Component Architecture

For each component: required **ports / parameters / internal states / geometry / correlation slots / calibration locations.** Internal states named even when frozen in steady state (the dynamic seam). No equations.

Notation: ports as `[in]`, `[out]`, `[branch_i]`; internal states tagged **(frozen v1)** if named-but-zero-derivative until Phase 6.

### Pump
- **Ports:** `[in]`, `[out]`.
- **Parameters:** efficiency η (or efficiency map), reference speed, displacement (if positive-displacement).
- **Internal states:** none (steady). **(frozen v1)** shaft speed / loop fluid inertia I.
- **Geometry:** minimal — a reference for the performance map.
- **Correlation slots:** pump performance/efficiency map (ΔP vs flow at speed).
- **Calibration:** none typical (efficiency is a parameter, not a calibrated closure). Slot exists but defaults neutral.
- **Scenario binding:** commanded speed ω or target ṁ comes from the Scenario.

### Pipe
- **Ports:** `[in]`, `[out]`.
- **Parameters:** optional wall-heat flag/value.
- **Internal states:** none (steady, lumped). **(frozen v1)** per-segment fluid mass/momentum and (if heated) wall temperature — **count set by Discretization**, not Geometry.
- **Geometry:** `PipeGeometry {L, D_h, A, roughness, Δz}`.
- **Correlation slots:** single-phase friction; two-phase friction; void fraction (when needed).
- **Calibration:** R* on the frictional ΔP output, per-slot.
- **Discretization:** `Lumped` (v1 default) or `Segmented`; this is where the shared 1D-passage mechanism is reused by composition.

### Evaporator
- **Ports:** `[in]`, `[out]`.
- **Parameters:** channel count, heated-area parameters.
- **Internal states:** flow regime (algebraic, steady). **(frozen v1)** wall thermal capacitance per segment, fluid inventory — **count set by Discretization**.
- **Geometry:** `MicrochannelGeometry {N_channels, D_h,channel, fin_geometry, A_heated, wall_mass/material}`.
- **Correlation slots:** boiling HTC (Shah / Gungor–Winterton / Kim–Mudawar); two-phase ΔP. **The most correlation-sensitive component — replaceability here is the whole point.**
- **Calibration:** HTC multiplier and ΔP_friction multiplier, per-slot.
- **Discretization:** `Segmented` is the meaningful steady mode; `MovingBoundary` declared for Phase 6.
- **Scenario binding:** heat load Q (or wall flux).

### Condenser
- **Ports:** `[in]` (two-phase), `[out]` (subcooled).
- **Parameters:** plate/area parameters, sink-side description.
- **Internal states:** effective areas per zone (steady). **(frozen v1)** moving-boundary interface positions (two-phase/liquid).
- **Geometry:** `PlateGeometry {N_plates, chevron_angle, plate_spacing, port_dims, A_per_plate, sink-side}`.
- **Correlation slots:** condensation HTC (Shah / Yan); ΔP; and a **heat-exchange method** slot (ε-NTU / LMTD) — treated as a selectable closure, not hard-wired.
- **Calibration:** HTC/UA multiplier; ΔP_friction multiplier.
- **Discretization:** `Lumped` or `Segmented` (v1); `MovingBoundary` is the named Phase-6 seam.
- **Scenario binding:** sink temperature and sink flow.

### Accumulator
- **Ports:** one liquid `[port]` (mass exchange with the loop); it also wires the pressure-reference node.
- **Parameters:** total volume; gas charge (PCA); heater/thermal description (HCA).
- **Internal states:** liquid/gas split consistent with P_set (steady). **(frozen v1)** gas volume V_g, liquid volume V_l.
- **Geometry:** `AccumulatorGeometry {V_total, V_gas_charge (PCA), heater/thermal (HCA)}` — a *containment* geometry.
- **Correlation slots:** one **generic volume↔pressure law** slot, filled by a polytropic (PCA) or saturation-under-thermal-control (HCA) implementation — **so PCA and HCA are interchangeable behind one interface** (L1 §6).
- **Calibration:** none typical.
- **Network role:** **owns the pressure-setting law and value**; the Network owns *which node* is the reference and the *one-reference* invariant; the Solver owns global consistency (L2 §8).
- **Scenario binding:** P_set (steady) / control input (dynamic).

### Valve
- **Ports:** `[in]`, `[out]`.
- **Parameters:** reference area / Cv.
- **Internal states:** none (steady). **(frozen v1)** position over time.
- **Geometry:** minimal (reference area / Cv).
- **Correlation slots:** loss coefficient K_L vs. opening.
- **Calibration:** optional multiplier on the loss output.
- **Scenario binding:** opening fraction.

### Junction (Splitter / Mixer unified — resolves L2 §10)
- **Ports:** one `[trunk]` + N `[branch_i]` (Splitter: 1-in/N-out; Mixer: N-in/1-out; the class is one n-in/m-out node, configured by port counts).
- **Parameters:** branch count; orientation (split/mix) as configuration.
- **Internal states:** none (negligible storage).
- **Geometry:** minimal.
- **Correlation slots:** **none intrinsic** — branch resistances belong to the branches; junction supplies only mass + energy conservation and equal node pressure.
- **Calibration:** none.
- **Network role:** branch **equal-ΔP closure is a Network condition**; the Junction never knows another branch exists.

> **Decision:** one `Junction` with `Splitter`/`Mixer` as configurations, not two classes. Rationale: identical conservation contract, the literature's matrix-based branch distribution treats them uniformly (LITERATURE §4), and it shrinks the component count. Public-facing names `Splitter`/`Mixer` may remain as thin factory aliases for engineer readability.

### Reservoir (distinct component — removes L1's "where distinct from accumulator" hedge)
- **Ports:** liquid `[in]`, `[out]`.
- **Parameters:** volume.
- **Internal states:** inventory consistent with total charge (steady). **(frozen v1)** liquid level / interface height.
- **Geometry:** containment volume.
- **Correlation slots:** none.
- **Calibration:** none.
- **Network role:** **holds liquid inventory and guarantees NPSH; sets NO pressure reference.** The Accumulator sets the reference; the Network is the single inventory accountant. This firewall (L2 §8, §10-#2) prevents the duplicated-ownership smell.

---

## 5. Geometry Architecture

**Recommended family:** a **flat family of immutable, typed value objects** — `PipeGeometry`, `PlateGeometry`, `MicrochannelGeometry`, `AccumulatorGeometry` — each exposing exactly the scalars its component's correlations and balances consume, and nothing more. (Decided in L2 §2.2/§5; Level 3 ratifies and operationalizes.)

**Per-kind evaluation:**

- **PipeGeometry** `{L, D_h, A, roughness, Δz}` — the minimal flow geometry; single `D` serves as `D_h`. An annular variant supplies `D_h` differently but reuses the same friction-correlation family — proof that correlations bind to *scalars*, not types.
- **PlateGeometry** `{N_plates, chevron_angle, plate_spacing, port_dims, A_per_plate, sink-side}` — structurally unrelated to pipe; exposes chevron/spacing scalars that condensation correlations (Yan/Shah) want; **no single `D`**.
- **MicrochannelGeometry** `{N_channels, D_h,channel, fin_geometry, A_heated, wall_mass/material}` — exposes channel count and **wall thermal mass** (named now, used by the frozen dynamic wall-capacitance term).
- **AccumulatorGeometry** `{V_total, V_gas_charge, heater/thermal}` — a *containment* geometry, barely "flow" geometry; still feeds the generic volume↔pressure law.

**Composition:** Geometry is held by the Component **by composition** as a read-only reference. The Component, not the Geometry, decides which scalars to forward to each correlation.

**Reuse:** allowed and encouraged via **sharing by reference** — ten identical parallel evaporators point at one Geometry object. Sharing is *permitted*, never *required* (forced sharing creates aliasing surprises).

**Immutability:** **absolute.** A mutated geometry breaks reproducibility and aliasing safety. Varying a dimension produces a *new* Geometry → a *new* Reproducibility Tuple → exactly the unit Phase-5 DOE iterates over.

**Ownership:** Component-by-composition (Option B), with reference-sharing (Option C) as an allowance. **No god-object, no base `Geometry` with optional fields.**

**Should inheritance exist?** **No.** The four kinds share almost no fields; a common base would be a near-empty interface or a bag of optionals — both are the speculative abstraction L1 §1.6 forbids. If a shared *marker* is ever needed (e.g. "is a Geometry" for type-bounding), it is an empty tag interface carrying **no fields and no behaviour**, never a fields-bearing base. The discipline to defend in code review: **the moment a base Geometry grows a field, the flat family has rotted into a hierarchy.**

**Explicit exclusion (the boundary that will be tested):** Geometry **never** holds operating state, physics, time-varying quantities, or **the mesh**. The mesh is a *numerical fidelity choice derived from* geometry, owned by Discretization (§6) — putting it in Geometry would make a steady-lumped↔dynamic-1D switch a *geometry* edit and would burden the immutable shareable object with a solver concern.

---

## 6. Discretization Architecture

**This section is critical** — it is the seam Level 2 flagged as the single highest dynamic-readiness concern (L2 §9-A), and the one Level 1 omitted entirely.

**Concept:** Discretization is the **fidelity axis** of a component — the declared mode that fixes the *count and structure* of its internal states and residuals. Three modes, declared in the interface from day one:

- **Lumped (0D).** One control volume; parameters averaged across the component. State count minimal. The v1 default for pipes, condenser, accumulator, reservoir, junctions, valves, pump.
- **Segmented (1D finite-volume).** N control volumes along the flow; per-segment states (and, for heated components, per-segment wall temperature). State count = f(N). The meaningful steady mode for the evaporator (spatial resolution of quality/HTC) and an option for heated pipes and condenser.
- **MovingBoundary.** Zones whose *boundaries move* (two-phase ↔ liquid interface in the condenser); **the state count itself changes as zones appear/disappear.** Declared now, implemented in Phase 6.

**Ownership.** The **Component's numeric configuration** owns its Discretization. *Not* Geometry (which is immutable and physical), *not* the Solver (which must work for any valid network and only sees the resulting unknown count). The Component reports "I contribute K internal states and M residuals"; Discretization is what sets K and M.

**Lifecycle.** Fixed per run, chosen from the Reproducibility Tuple. **Derived from Geometry** (segment lengths = L/N from `PipeGeometry.L`) but **never stored in Geometry**. Switching `Lumped`↔`Segmented` is a *fidelity edit* — it changes neither the Geometry nor the Solver, only how many unknowns the Component declares.

**Interaction with Geometry.** One-way, read-only: Discretization reads geometric scalars (length, area) to compute per-segment quantities. Geometry never knows it has been discretized — the same Geometry object serves a lumped and a segmented run.

**Interaction with Components.** Discretization is the bridge between "how much physics detail" and "how many unknowns". The Component's contribution contract (§3.1) is **identical regardless of mode** — it always returns "my residuals and/or my derivatives for my current internal states"; Discretization merely sets how many there are. This is what makes the contract frozen-stable across the lumped→segmented→moving-boundary progression.

**How future dynamic models use this.** This is the payoff. In steady state, a `Segmented` evaporator's per-segment wall temperatures are **named internal states with zero derivative**. The dynamic solver does not restructure the component — it *unfreezes* those derivatives (L1 §10, L2 §9). The `MovingBoundary` condenser is the one genuinely harder case (variable state count); declaring the mode *now*, even unimplemented, means Phase 6 *activates a declared mode* rather than *retrofitting a state structure into a component that never anticipated one*. **Prepare the seam, defer the mechanism** (L1 §1.6) — built now: `Lumped`, `Segmented`; declared now, built Phase 6: `MovingBoundary`.

> The one rule to enforce in review: **state count belongs to Discretization, never to Geometry, never assumed by the Solver.** Violating it is how the moving-boundary condenser becomes a redesign instead of an activation.

---

## 7. Correlation Registry Architecture

**Registration.** A lightweight **Correlation Registry** holds a catalogue of named, stateless correlation instances, grouped by **role** (boiling-HTC, condensation-HTC, single-phase-friction, two-phase-ΔP, void-fraction, volume↔pressure-law, heat-exchange-method). Registration is a startup-time act: a name → instance binding. The registry owns the *catalogue*; it owns no per-run state. (L2 §2.3, §6.)

**Selection.** A Component declares **slots by role** ("I need a boiling-HTC and a two-phase-ΔP"). The Reproducibility Tuple binds a registered *name* to each slot. Selection is **configuration, recorded in the tuple — never a code edit.** The component knows it needs an HTC; it never knows whether Shah or Kim–Mudawar fills the slot.

**Replacement.** Replacing a model = **rebinding the slot name** in the tuple. Swapping Shah → Kim–Mudawar in an evaporator touches the configuration only — not the evaporator, not the solver, not neighbours. *This operationalizes Principle 1.2, the project's core research seam.*

**Validity checking.** Each correlation **declares its envelope** (fluid family, geometry range, flow-regime/quality range, Re/Bond bounds) and, on each evaluation, returns its number **plus a validity verdict**. The framework **warns on extrapolation; it never silently clamps or extrapolates.** Validity is a transparency output (the researcher decides if out-of-envelope use is acceptable, but is never unaware of it), surfaced into the Result.

**Worked seam 1 — replace a pressure-drop model.** Researcher edits the tuple: `evaporator.two_phase_dP_slot = "Friedel"` → `"MüllerSteinhagenHeck"`. Re-run. Nothing in the evaporator, solver, network, or neighbouring components changes. The new model's validity envelope is checked against the run's regime; any extrapolation is flagged in the Result. The calibration seam (R* on ΔP_friction) is unaffected — it still multiplies whatever the slot now returns.

**Worked seam 2 — replace an HTC model.** Researcher edits the tuple: `evaporator.boiling_HTC_slot = "Shah"` → `"GungorWinterton"`. Re-run. Same isolation. The component asked for "a boiling-HTC"; the registry now hands it a different pure function with the same `(FluidState, scalars) → (value, verdict)` contract. The HTC calibration multiplier applies identically.

> **Deliberately lightweight.** This is a *registry of named pure functions*, not a heavyweight factory framework, plugin system, or dependency-injection container (L1 §1.6, L2 §6). The whole mechanism is: a name→function catalogue + per-slot name bindings in the tuple + a validity verdict on each call. **The PropertyBackend is NOT in this registry** — it is a Layer-1 FluidState citizen with a different contract (no geometry, no slots), kept separate to avoid the DAG cycle (L2 §6, §10-#1).

---

## 8. Configuration Philosophy

A simulation is described **entirely** by the **Reproducibility Tuple** (L1 §1.7): `topology + component parameters + geometries + fluid identity + correlation selections + calibration + scenario + solver settings`. This is the serializable, versioned unit of an experiment. **No run depends on anything outside it** — no global state, no call order, no un-versioned default.

The decisive question Level 3 must settle is the **division of responsibility** across Scenario / Network / Component. The rule:

| Belongs to | What | Test for membership |
|---|---|---|
| **Scenario / BoundaryConditions** | The **operating point**: heat loads, sink temperature/flow, pump command/speed, ambient, accumulator P_set. The things you *vary in a DOE while the hardware stays fixed*. | "If I sweep this in Phase 5 without rebuilding the loop, it is Scenario." |
| **Network** | The **structure**: which components exist, how their Ports connect, branch topology, which node is the pressure reference, global inventory accounting. The things that define *what loop this is*. | "If changing this changes the P&ID, it is Network." |
| **Component** | The **local identity**: its Geometry, fixed parameters (η, Cv, channel count), correlation slot *selections*, calibration factors, Discretization mode, internal-state names. The things intrinsic to *that piece of hardware*. | "If changing this changes one part without re-wiring, it is Component." |

**Worked allocations (to remove ambiguity before coding):**

- *Heat load on the evaporator* → **Scenario** (operating point), bound to the evaporator component. Not a component parameter — the same evaporator runs at many loads.
- *Sink temperature on the condenser* → **Scenario**, bound to the condenser.
- *Pump speed* → **Scenario**; the pump's efficiency map → **Component**.
- *Which boiling-HTC correlation* → **Component** slot selection (recorded in the tuple).
- *Calibration R\* on evaporator ΔP* → **Component** (per-slot calibration).
- *Number of parallel evaporator branches* → **Network** (topology).
- *Which node is the pressure reference* → **Network** (the one-reference invariant); the *law* that sets the reference value → **Component** (the accumulator's volume↔pressure slot).
- *Solver type / tolerances / steady-vs-dynamic* → **solver settings** in the tuple (neither Scenario nor Network nor Component — they are numerics).
- *Fluid choice* → tuple-level **fluid identity**, which selects the PropertyBackend.

**The boundary that matters for Phase 5:** Scenario is the **primary DOE axis**. Keeping it cleanly separate from Component parameters and Network topology is what lets a surrogate dataset sweep operating points (thousands of Scenarios) against a *fixed* Network and *fixed* Components — and attribute every Result to an exact tuple. Folding Scenario into "component inputs" (as L1 did) would make Phase 5 improvise this separation inconsistently. Naming it now is cheap; retrofitting it is expensive (L2 §10-#2).

---

## 9. Result Philosophy

The **Result / Solution** object is the atomic output unit, paired with its Reproducibility Tuple. Its design is governed by the same single-source-of-truth rule as everything else: **store the minimum; derive the rest; never let a derived quantity become a second source of truth.**

**What is STORED (the irreducible converged state):**
- The converged **Port (P, h, ṁ)** across the network.
- The converged **component internal states** (wall temperatures, gas/liquid volumes, etc. — whatever each Discretization declared).
- A **reference to the Reproducibility Tuple** that produced it (by value or content-hash, so the Result is self-describing and archivable).

**What is DERIVED on demand (never stored redundantly):**
- The **profiles**: P, h, x, T, ρ along the loop — recomputed from the stored (P,h) through FluidState. There is no stored "temperature field" that can drift from (P,h).
- Component-level derived outputs (heat rejected, outlet quality, subcooling, pump power).

**What is REPORTED (first-class, always present):**
- The **validation invariants** — global energy imbalance, mass imbalance, pressure-closure residual, and physical-bound checks (0 ≤ x ≤ 1, T < T_crit) — computed from *un-calibrated conservation*, so calibration can never make a violated balance look satisfied (the conservation firewall, L2 §7).
- The **calibration report** — every non-neutral factor, its value, its mode (`none`/`target`), and its seam location. A factor that is not reported cannot exist (the validation acceptance criterion "no hidden empirical correction factors" enforced structurally).
- The **validity verdicts** from every correlation evaluated outside its envelope (extrapolation warnings).
- **Convergence metadata** — iterations, final residual, status.
- A **predictive-vs-reconciled flag** — a Result produced under `target` is flagged as calibrated, never compared as-equal to a `none` predictive run (L2 §7).

**Validation information that must ALWAYS be included** (per VALIDATION_PLAN acceptance criteria): energy imbalance < 1% check, pressure-closure residual < 1% check, quality-bounds check, and the calibration-factor report. These are not optional fields — a Result without them is malformed. This is L1 §1.4 (validation-first) made structural: *a result without a residual is not a result.*

**Future DOE / surrogate considerations (Phase 5):**
- The Result must be **batchable and serializable** — Phase 5 produces thousands, each (Tuple, Result) pair fully attributable. This is why the tuple reference is stored *in* the Result.
- The stored state must be **minimal** (storage cost × thousands of runs is real); profiles are derived on read, not persisted, unless explicitly requested.
- The Result schema, like the tuple schema, should be **versioned** so a 5-year-old surrogate dataset remains interpretable.
- The clean **(Scenario in tuple) → (invariants + outputs in Result)** mapping is exactly the input/output pairing a surrogate model trains on. The architecture hands Phase 5 its training rows for free.

---

## 10. Extensibility Audit

The 5-year test. For each future addition: **what changes** (the seam) and **what stays untouched** (everything else). If "stays untouched" is large and "changes" is local, the architecture earned its modularity.

### New evaporator technology
- **Changes:** add one new `Component` (its balance + its declared geometry type + its slot declarations) and, if its passage shape is new, one new `Geometry` type in the flat family. Optionally a new boiling-HTC correlation in the registry.
- **Untouched:** Solver, Network, Port, FluidState, PropertyBackend, Calibration mechanism, Result, every other component, the dependency DAG. The new evaporator is just another physical component speaking the same contribution contract.

### New accumulator model
- **Changes:** **nothing structural** — add a new implementation of the **volume↔pressure law** slot and register it. PCA, HCA, and any future accumulator are interchangeable behind that one slot (L1 §6).
- **Untouched:** the Accumulator component shell, the Network's one-reference wiring, the Solver, everything else. This is the cleanest seam in the architecture: a "new accumulator" is a *new closure*, not a new component.

### New pressure-drop correlation
- **Changes:** register one new pure function with its validity envelope. Rebind the slot in any tuple that wants it.
- **Untouched:** every component, the solver, the network, calibration (R* still multiplies the new output), and all other correlations. This is §7's worked seam 1 — **configuration, not code.**

### New dynamic solver
- **Changes:** add one new `Solver` implementation behind the existing component contribution contract. It asks components for d(state)/dt and integrates.
- **Untouched:** **every component, every correlation, every geometry, the network, the ports.** Components contribute residuals *and/or* derivatives; the new solver consumes the derivative side. Because nothing depends on the Solver (DAG sink), a new solver is a pure addition. The named-but-frozen internal states (§4, §6) activate without restructuring. *This is the entire reason steady-state-first does not paint us into a corner* (L1 §10).

### Machine-learning closure model
- **Changes:** register an ML model **as a Correlation** — it obeys the identical `(FluidState, declared scalars) → (value, validity verdict)` contract. Bind it to a slot. Its "validity envelope" becomes its training-domain bounds; out-of-domain use is flagged like any extrapolation. If it is a *property* surrogate instead of a *closure*, it registers as a **PropertyBackend** (a tabulated/learned backend) at Layer 1, not as a slot correlation.
- **Untouched:** components, solver, network. The ML model is physics-shaped data behind a pure-function contract; the framework cannot tell it apart from Shah. Dataset-fitting that *produced* the model is Phase-5 identification territory and routes its results back as ordinary explicit factors/closures — never a parallel hidden mechanism (L2 §7).

> **The pattern across all five:** every realistic future addition lands on **exactly one of the three sanctioned seams** — swap a Correlation (config), add/edit a Component+Geometry (a new physical part), or swap the Solver (engineering) — plus the registry for new closures/backends. The Solver, the DAG, the Port interface, the ownership map, and the component contract are touched by **none** of them. That invariance *is* the 5–10 year design lifetime.

---

## 11. Anti-Patterns

Architectural mistakes future developers will be tempted into, each tied to the guard that forbids it. The first four are from the prompt; the rest are the additional traps this architecture specifically exposes.

1. **Geometry owning physics.** A `PlateGeometry` that computes its own Nu, or a Geometry that holds a correlation. *Why it's fatal:* a god-object and a maintenance sink; couples inert data to closures. *Guard:* Geometry supplies declared scalars only; it is Layer 0, depends on nothing, computes nothing (§5, L2 §1).

2. **Components knowing topology.** A junction asking the network for "the other branch's flow"; an evaporator referencing its downstream condenser. *Why it's fatal:* welds the loop shape into the parts; destroys reuse; makes adding a branch a component rewrite. *Guard:* Component may never name Network or a neighbour; branch closure is a Network condition (§3.1, §4, L2 §8).

3. **Calibration hidden inside correlations.** A fudge factor baked into the Shah formula instead of applied at the output seam. *Why it's fatal:* makes old results untrustworthy; violates the validation criterion; lets calibration mask a balance violation. *Guard:* correlations are pure (return physics); calibration multiplies the *output* at the documented seam, scales closures never balances, and is always reported (§7, L2 §7).

4. **Duplicated state ownership.** Caching T or ρ on a Port/Component beside (P,h); two components both claiming the loop's inventory; two pressure references. *Why it's fatal:* silent divergence — results keep coming while a balance is quietly violated. *Guard:* only P,h,ṁ + internal states are stored; everything else derived by FluidState; the Network is the single inventory accountant; the topology validator enforces exactly one reference (§2, §4, L2 §2.1, §8).

5. **Solver–physics entanglement.** A component that "knows" it is Newton-iterated, hard-codes a timestep, or stores a Jacobian assumption. *Why it's fatal:* the second solver becomes a rewrite; the dynamic path dies. *Guard:* the contribution contract is residual/derivative only; the Solver owns all numerics and obtains the Jacobian itself; nothing depends on the Solver (§3.1, §3.4, L2 §1).

6. **Correlations welded into components.** Hard-coded `if regime == annular: shah()` inside the evaporator. *Why it's fatal:* kills the swappability that is the project's research value. *Guard:* correlations are named slots filled from the registry by configuration (§7).

7. **The mesh living in Geometry.** Storing segment count or zone count in the immutable Geometry object. *Why it's fatal:* makes a fidelity switch a geometry edit, and burdens the shareable immutable object with a solver concern; turns the moving-boundary condenser into a retrofit. *Guard:* state count is owned by Discretization, derived from but never stored in Geometry (§6, L2 §9-A).

8. **Geometry hierarchy creep.** A base `Geometry` class that grows fields, sprouting optionals to cover all four kinds. *Why it's fatal:* the flat family rots into a fat hierarchy — the speculative abstraction L1 §1.6 forbids. *Guard:* flat typed family; any shared marker is field-less; "a base Geometry field" is a review red flag (§5).

9. **PropertyBackend treated as a slot Correlation.** Putting CoolProp in the per-component correlation registry. *Why it's fatal:* forces FluidState to depend on the geometry-aware Layer-3 correlation layer — a DAG cycle. *Guard:* PropertyBackend is a Layer-1 FluidState citizen, separate registry, no geometry, no slots (§2, §7, L2 §6).

10. **Scenario folded into component parameters.** Treating heat load or sink temperature as a fixed component attribute. *Why it's fatal:* Phase-5 DOE then has no clean axis to sweep; the surrogate dataset's input/output split is improvised. *Guard:* Scenario is a first-class concept and the primary DOE axis, bound-to but separate-from components (§8).

11. **Result as a bag of stored numbers.** Persisting T/x/ρ profiles as stored fields beside (P,h). *Why it's fatal:* recreates the duplicated-source bug in the output, and the stored profile can contradict the stored state. *Guard:* Result stores minimal converged state + tuple reference; profiles and invariants are derived/computed, never a second truth (§9).

12. **Speculative generality.** A plugin system, event bus, DI container, or the abstract-primitive component model — added "for flexibility." *Why it's fatal:* a permanent translation tax on every future researcher with no physical payoff. *Guard:* abstraction only when two concrete cases demand it; thirteen concepts and no more; physical-component vocabulary kept public (L1 §1.6, §3B).

---

## 12. Readiness Assessment

**Verdict: the architecture is mature enough to begin implementation of Phases 1–4 (steady-state), provided the five freezes of §1.3 are ratified and the four interface-defining documents below are produced.** The four dynamic-readiness gaps Level 2 raised are all resolved here as *declared seams* (Discretization §6, Jacobian policy §3.4, simultaneous assembly kept as an option §3.4/§3.5, inventory accountant §4) — none is a redesign blocker for v1.

**There are no architectural blockers.** The remaining work is *interface specification*, not *architecture*. Specifically, before the first component is coded, produce these **minimal remaining documents** (the only gate between Level 3 and code):

1. **INTERFACE_SPEC.md** — the precise method signatures (still language-agnostic or in the chosen language's interface form) for the five frozen contracts: Component contribution, Port connect, Correlation evaluate, PropertyBackend query, Solver/Network assembly. This is where §3's prose becomes signatures. *Highest priority — it is the thing all code is written against.*
2. **SCHEMA_SPEC.md** — the serialization schema (and version field) for the **Reproducibility Tuple** and the **Result**. Phase 5 depends on these being stable and versioned from run #1.
3. **CORRELATION_CONTRACT.md** — the validity-envelope declaration format and the validity-verdict return shape, so the first correlation and the registry agree.
4. **TEST_PLAN_V1.md** — the mapping from VALIDATION_PLAN's five levels to concrete first-implementation checks (unit: friction factor, quality; component: each of the §4 components; loop: closure + invariants; literature: Kokate R134a as the first end-to-end target). This makes validation-first real from the first commit.

**Not required before coding** (prepare-the-seam, defer-the-mechanism): the dynamic integrator, moving-boundary equations, the AD Jacobian path, the surrogate/identification tooling, and the simultaneous-Newton steady solver. Their seams are declared; their mechanisms wait for their phases.

**Recommended first vertical slice** (to validate the architecture against reality early): implement FluidState + PropertyBackend (CoolProp) → Port → one friction Correlation + registry → `Pipe` (Lumped) → a trivial two-component Network → fixed-point steady Solver → Result with invariants. This exercises every layer of the DAG end-to-end on the simplest possible loop, surfacing any interface friction before the expensive components are built. Then add Pump, Accumulator, Evaporator, Condenser, Junction against the now-proven contracts (Phase 2 order in the roadmap).

---

## 13. Recommendations for ARCHITECTURE_MASTER.md

The consolidated, implementation-facing document. Its job is to be the **single source of architectural truth** a developer reads once and refers to forever — so it must be *shorter and more decisive* than the three Levels combined, importing conclusions and discarding the deliberation that produced them.

**Guiding principle for the consolidation:** Levels 1–3 are a *reasoning trail* (they argue *why*). MASTER is a *reference* (it states *what*, with a one-line *why* and a pointer to the Level for the full argument). Import **decisions and contracts**, not debates.

### Proposed structure

**Chapter 0 — Purpose & Status.** One page. What the framework is, the 5–10 year horizon, the steady-state-first/dynamics-later stance. *From:* README + L1 preamble.

**Chapter 1 — Design Principles (the seven, condensed).** The ordered principles as a numbered list with one sentence each, no dual-justification prose. *Import from L1 §1, compressed ~4:1.* These are the tie-breakers; they must be in MASTER.

**Chapter 2 — The Dependency DAG & Forbidden Directions.** The layered diagram, the per-concept dependency table, and the forbidden-direction list. *Import from L2 §1 nearly verbatim — it is already reference-shaped.* **This is the most important chapter; it leads because every contract derives from it.**

**Chapter 3 — Concept Inventory (the thirteen).** The purpose/owner/lifecycle/interactions table for all thirteen concepts. *Import from L3 §2.* This replaces L1 §2's eight-concept prose with the final thirteen.

**Chapter 4 — Ownership & State.** The single-source-of-truth map (stored vs derived), the calibration resolution order, the inventory-accountant rule. *Import from L2 §2 + L3 §9's stored/derived split.*

**Chapter 5 — Interface Contracts.** The five contracts (Component, Correlation, PropertyBackend, Solver, Network): provides / consumes / never-accesses. *Import from L3 §3.* This chapter is the bridge to INTERFACE_SPEC.md and should explicitly point to it for signatures.

**Chapter 6 — Component Reference.** The per-component table (ports/params/states/geometry/slots/calibration) for the nine physical components. *Import from L3 §4*, with the Junction-unification and Reservoir-as-component decisions baked in (drop L1's hedges).

**Chapter 7 — Geometry & Discretization.** The flat-family geometry rule and the three-mode discretization seam, kept together because their boundary (mesh ≠ geometry) is the most-tested one. *Import from L3 §5 + §6.*

**Chapter 8 — Correlations & Calibration.** The registry mechanism, selection/replacement by name, validity verdicts, and the calibration seam + conservation firewall. *Import from L3 §7 + L2 §7.*

**Chapter 9 — Configuration, Scenario & Result.** The Reproducibility Tuple as the unit of an experiment; the Scenario/Network/Component division; the Result schema and mandatory validation fields. *Import from L3 §8 + §9.* This chapter is the contract Phase 5 builds on.

**Chapter 10 — Solver & Dynamic Readiness.** The where/what/how split, the steady strategies, the Jacobian policy, and the prepared dynamic seams (named states, derivative contract, discretization, inventory, simultaneous assembly). *Import from L1 §7 + L2 §8, §9 + L3 §3.4*, stated as *prepared seams*, not future plans.

**Chapter 11 — Anti-Patterns.** The twelve anti-patterns with their guards. *Import from L3 §11 verbatim* — this is the code-review checklist and belongs in MASTER as-is.

**Chapter 12 — Implementation Gate.** The five frozen decisions, the four required interface documents, and the recommended first vertical slice. *Import from L3 §1.3 + §12.* This is the chapter that says "you may now write code, here, in this order."

**Appendix A — Decision Provenance.** A table mapping each MASTER decision to its originating Level/section, so the reasoning trail remains recoverable without cluttering the reference. This is how MASTER stays short while keeping Levels 1–3 as the archived *why*.

### Level-of-detail guidance

- **MASTER states decisions; it does not argue them.** Every place L1/L2/L3 wrote "Option A vs B vs C → recommendation", MASTER imports only the recommendation + a one-line reason + a provenance pointer.
- **Import rule of thumb:** *from L1* → principles and vocabulary (Ch 1, 3); *from L2* → the DAG, ownership, and forbidden directions (Ch 2, 4); *from L3* → the concrete contracts, component tables, the new seams (Discretization, Scenario, Result), the anti-patterns, and the implementation gate (Ch 5–12). L3 is the largest contributor because it is the most concrete.
- **What to leave behind in the Levels** (do not import): the dual physics/software justifications, the option-by-option evaluations, the adversarial consistency audits, and the "uncertain vs frozen" deliberation. Those did their job; MASTER inherits their *conclusions*.

The test of a good MASTER: a developer who has never read Levels 1–3 can implement a correct new component from MASTER alone, and a reviewer can reject a bad PR by citing a MASTER chapter. If both hold, the team is ready to build.

---

*End of ARCHITECTURE_LEVEL_3.md — the architecture is ready for the four interface documents of §12, after which implementation of Phases 1–4 may begin.*
