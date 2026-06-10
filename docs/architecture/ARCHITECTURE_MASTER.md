# ARCHITECTURE_MASTER.md

**The single authoritative architecture reference for the MPL simulation framework.**

Status: **frozen architecture** (pre-implementation). This document is the source of truth for all future development.
Scope: it *states* the decisions that govern the framework. It does not argue them, does not present alternatives, and does not reopen settled questions. The reasoning trail lives in `ARCHITECTURE_LEVEL_1/2/3.md`, `OPEN_ARCHITECTURE_QUESTIONS.md`, `ARCHITECTURE_REVIEW_LEGACY.md`, and `DECISION_LOG.md`; this document imports only their conclusions.
Horizon: 5–10 years. Steady-state first; dynamics, surrogate generation, and control-oriented models arrive as additions along seams that are prepared now.

How to use this document:
- A developer should be able to implement a correct new component from this document alone.
- A reviewer should be able to reject a non-conforming change by citing a section here.
- Where a contract signature is needed for code, this document points to the interface documents named in §18.
- Every frozen decision is tagged `[Fxx]` and cross-referenced to its origin in Appendix A.

---

## 1. Core Design Principles

These seven principles are **ordered**. When two conflict, the earlier governs. They are the tie-breakers for every decision below.

1. **Physical transparency before software elegance.** Every solver quantity has a name a thermal engineer recognises (P, h, ṁ, x, T_wall, …) and a defensible physical meaning. No state variable exists for numerical convenience without being documented as such.
2. **Replaceability at the model seam.** A researcher can replace one correlation, one accumulator law, or one solver without touching the solver internals, neighbouring components, or the network. Protecting this is the framework's primary structural purpose.
3. **Separation of physics from numerics.** A component declares its physical contribution (residual and/or derivative); a solver decides the numerical scheme. Neither knows the other's internals.
4. **Validation-first design.** Energy and mass balances, pressure closure, and physical-bound checks are first-class outputs, not afterthoughts. Calibration factors are explicit, named, neutral by default, and always reported. *A result without a residual is not a result.*
5. **Numerical robustness as a stated property.** Single-phase ↔ two-phase transitions, near-zero quality, and near-critical states are the normal operating regime. The state representation and solver contracts are chosen so these transitions are continuous and require no variable switching.
6. **Modularity proportional to need.** An abstraction is introduced only when at least two concrete cases demand it (or the roadmap names a third within the horizon). No plugin systems, dependency-injection containers, event buses, or speculative generality.
7. **Reproducibility.** A run is fully determined by its Reproducibility Tuple (topology + parameters + geometries + fluid + correlation selections + calibration + scenario + solver settings). No result depends on hidden global state, call order, or an un-versioned default.

---

## 2. Architectural Concepts

The framework is built from a fixed, closed inventory of concepts. **Anything not on this list does not get a class** (Principle 6). The inventory is the eight conceptual primitives of Level 1, plus five concepts formalized in Level 2/3, plus the two structural objects (`SystemState`, `Junction`) ratified during the open-questions pass.

| # | Concept | Layer | Purpose (one line) | Owner |
|---|---|---|---|---|
| 1 | **FluidState** | 1 | The thermodynamic state at a point: `(P, h, identity)`, single source of truth for all derived properties. | Transient; created on demand, never stored. |
| 2 | **PropertyBackend** | 1 | The swappable property engine (CoolProp / REFPROP / tabulated / empirical) serving FluidState. | The run (one shared instance per fluid identity). |
| 3 | **Geometry** | 0 | Immutable physical/dimensional description of a component's passages and structure. | Component, by composition (shareable by reference). |
| 4 | **Calibration** | 4 | Named multipliers (default neutral) scaling closure *outputs* at the documented seam. | Per-component correlation slot. |
| 5 | **Scenario / BoundaryConditions** | input | The operating point a Network is evaluated at, in five parts: **boundary conditions, commands, disturbances, environment, operating point** (heat loads, sink T/flow, pump/valve commands, gravity, ambient). | The Reproducibility Tuple; bound to components at solve time. |
| 6 | **ReproducibilityTuple** | input | The serializable, versioned tuple that fully determines a run. | The user/experiment layer. |
| 7 | **Port** | 2 | The connection interface declaring connectivity for (P, h, ṁ). Carries **no values**. | The Component that declares it. |
| 8 | **Correlation** | 3 | One stateless closure relation `evaluate(CorrelationInput) → (value, ValidityVerdict)`. | Instances: Correlation Registry. Selection: Component slot. |
| 9 | **Component** | 5 | Local physics of one physical element; contributes residuals and/or internal-state derivatives. | The Network, by composition. |
| 10 | **Discretization / Mesh** | 5 | The fidelity axis `Lumped \| Segmented \| MovingBoundary`; fixes the count/structure of a component's internal states. | The Component's numeric configuration. |
| 11 | **Junction** | 6 | The n-in/m-out conservation node; `Splitter`/`Mixer` are configurations of it. | The Network. |
| 12 | **Network** | 6 | The assembled topology; states continuity, loop-closure, one-reference, branch structure, global inventory. | The run. |
| 13 | **Solver** | 7 | The numerics: assemble the global system, drive to convergence (steady) or march (dynamic), emit invariants. | The run. |
| 14 | **SystemState** | 7 (numerics) | The solver-owned, flat, ordered, indexable vector holding every port-node's (P, h, ṁ) and every named internal state. | The Solver. |
| — | **Result / Solution** | output | The atomic output unit: converged state + derived profiles + invariant residuals + calibration report, paired with its tuple. | Produced by the Solver; owned by the experiment archive. |

**Not concepts (contracts/mechanisms, deliberately not runtime objects):** the Derivative/Jacobian provision (a contract on Component and Solver, §15); the Sensitivity/Linearisation seam (§16); the shared 1D segmented-passage mechanism (an internal building block reused by composition, never a public primitive); and the **HeatExchangerModel** — the heat-exchanger *solution strategy* (ε-NTU, LMTD, segmented-march, moving-boundary), a **component-internal strategy of heat-exchanger components** selected by name like a correlation slot but **distinct from a closure Correlation**: a Correlation returns one local closure value, whereas a HeatExchangerModel solves a whole exchanger by *consuming* HTC and ΔP correlations and the secondary-fluid boundary condition (§12; `INTERFACE_SPEC.md` §8). Promoting any of these to a top-level object would be the speculative generality Principle 6 forbids.

---

## 3. Dependency Rules

The framework is governed by **one structural invariant**, from which every other guard derives. This is the most important rule in the document.

> **Dependencies flow in one direction only: from inert data, through physics, toward numerics. Nothing that expresses physics may depend on anything that expresses numerics, and nothing that expresses numerics may be depended upon by anything else.** `[F1]`

The concepts form a strict, acyclic layered DAG:

```
Layer 0 (inert):        Geometry        PropertyBackend
Layer 1 (state):        FluidState  ──── reads ──> PropertyBackend
Layer 2 (interface):    Port  (connectivity only — carries no values)
Layer 3 (closure):      Correlation ── reads ──> FluidState, declared scalars
Layer 4 (modifier):     Calibration  (value object; applied at Layer 5)
Layer 5 (physics):      Component ── owns ──> Geometry, Correlation slots, Calibration,
                                              Discretization; speaks via Port
Layer 6 (topology):     Network ── holds ──> Components, Junctions, Connections
Layer 7 (numerics):     Solver ── reads ──> Network; owns ──> SystemState
```

### Per-concept dependency contract

| Concept | MAY depend on | MUST NEVER depend on |
|---|---|---|
| **Geometry** | Nothing | Everything above it |
| **PropertyBackend** | Fluid identity only | Geometry, Port, Component, Correlation, Network, Solver |
| **FluidState** | PropertyBackend; identity | Geometry, Port, Component, Correlation, Network, Solver |
| **Port** | (declares connectivity; references its owning component for identity only) | Values, FluidState, Correlation, Network, Solver |
| **Correlation** | FluidState; declared scalars (via CorrelationInput) | Component, Geometry *type*, Network, Solver, Calibration |
| **Calibration** | Nothing (value object) | Correlation internals, Component physics, Network, Solver |
| **Component** | Geometry, Port, Correlation slots, Calibration, Discretization, its Scenario inputs | Network, Solver, **neighbouring Components** |
| **Discretization** | Geometry scalars (read-only) | Solver, Network |
| **Network** | Component, Port, Junction (connectivity) | Solver, Correlation, Geometry, FluidState internals |
| **Solver** | Network, Component contributions, SystemState | — (nothing depends on the Solver) |

### Forbidden directions (enforced in review; ideally made unrepresentable by the interfaces)

- **Correlation → Component** (a correlation checking "am I in an evaporator"). Breaks swappability.
- **Component → Network** (a junction asking for another branch's flow). Branch closure is a Network condition.
- **Component → Solver** (a component aware it is Newton-iterated, or picking a timestep). Kills the dynamic-solver path.
- **Geometry → Correlation / Geometry computes physics.** Geometry is inert; it supplies scalars, never Nu or ΔP.
- **FluidState → Geometry.** Properties are local to the fluid, not the passage.
- **Anything → Solver.** Universally forbidden.

The payoff is **exactly three sanctioned seams**: swap a **Correlation** (configuration), edit the **Network** topology, swap the **Solver** (engineering). The DAG guarantees each is touchable without disturbing the others.

---

## 4. Ownership Rules

Dependency answers "who may know whom". Ownership answers "who is the single source of truth". **Every quantity has exactly one owner.** Duplicated ownership is the #1 silent-divergence failure mode.

### 4.1 The stored-vs-derived boundary `[F3]`

> **The only stored numbers in the framework are P, h, ṁ (per port-node) and the named component internal states — all held in the solver-owned `SystemState`. Everything a thermal engineer reads off a plot — T, x, ρ, μ, σ, k, c_p, void, phase — is owned by FluidState and computed on demand, never stored.**

| Quantity | Owner | Stored / Derived |
|---|---|---|
| pressure P, enthalpy h, mass flow ṁ | **SystemState** (solver-owned) | Stored (primary unknowns) |
| component internal states (wall T, V_g, inventories, …) | **SystemState** | Stored (named per Discretization) |
| temperature T, quality x, density ρ, μ, k, σ, c_p, void, phase, T_sat, h_f/h_g/h_fg | **FluidState** (via PropertyBackend) | **Derived, never stored** |
| closure outputs (HTC, ΔP, ε_void) | recomputed each evaluation | **Never stored** (no `_last_dP` caching) |

The moment T or ρ is cached beside (P, h), it can drift, and the drift is invisible until a balance silently violates. This is non-negotiable.

### 4.2 Other ownership rules

- **Geometry** is owned by the Component by composition, immutable, and may be shared by reference; the Component decides which scalars to forward to each correlation.
- **Correlation selection** is owned by the Component's slot; **correlation instances** are owned (stateless) by the Correlation Registry.
- **Calibration** is owned at the per-component correlation slot, resolving **slot → component → global (`none`/`target`, default neutral)**. The Network/Solver own only its *aggregation and reporting*, never its physics. `[F5]`
- **Global mass inventory** has a single accountant: the **Network**. No component double-counts it.
- **Pressure reference**: the **Accumulator is a pressure-reference component** whose **geometry (containment) and pressure-reference law are separate**, the law a swappable slot supporting PCA/HCA/bellows/spring/gas-charged. It owns the pressure-setting *law and value*; the **Network** owns *which node* is the reference and the one-reference invariant; the **Solver** owns *global consistency*. The **Reservoir holds inventory/NPSH and sets no reference.** `[F7]`

---

## 5. FluidState Architecture

`[F2] [F12]`

**FluidState is a pure value object: `(P, h, identity)`.** No derived property is ever stored on it. Every derived quantity — T, T_sat, x, ρ, μ, k, σ, c_p, phase, and the saturation anchors h_f/h_g/h_fg — is obtained by querying the PropertyBackend.

- **Why (P, h):** continuous and single-valued across subcooled, saturated, and superheated regions; `x = (h − h_f)/h_fg` is continuous through 0 and 1; no region-dependent variable switching. It is the variable the energy balance already carries and the variable the dynamic energy equation stores, so dynamics adds equations, not a new representation. This is the universal literature consensus.
- **Identity is a mixture-capable value object** — able to express a single fluid, a mixture with composition, or a custom-fluid handle. A bare string is insufficient; this is the seam that lets a `MixtureBackend`/`CustomFluidBackend` be selected without changing FluidState.
- **ṁ is not in FluidState.** FluidState is two numbers + identity. ṁ is a flow variable in the SystemState. This matters in dynamics, where ṁ is a momentum state while (P, h) is the energy state.
- **Lifecycle:** ephemeral. Constructed transiently from (P, h) when a property is needed, then discarded. Never cached on a Port or Component.
- **Access is vector-first.** The inner loop and correlations receive a pure FluidState plus access to a backend supplied by context — not a backend embedded in every state. The pure form keeps Phase-5 batches and finite-difference Jacobian columns cheap and serialization trivial. An optional thin ergonomic wrapper may exist for user/analysis code only.

---

## 6. PropertyBackend Architecture

`[F6] [F13]`

The PropertyBackend is a **Layer-1 citizen of FluidState, distinct from Layer-3 closure Correlations.** It reads neither geometry nor topology, lives in its own registry, and is the only thing FluidState depends on. This separation resolves the only latent DAG cycle in the architecture: a closure Correlation is geometry-aware and slot-held; the property engine is neither.

### Interface contract (frozen from day one)

The PropertyBackend interface must provide:

1. **Vector-first property queries:** `query(prop, P[], h[], identity) → value[]`. A scalar is the length-1 case. *This sets the Phase-5 and Jacobian performance ceiling and must be in the interface from the first definition.*
2. **The full derived property set** FluidState exposes (T, T_sat, x, ρ, μ, k, σ, c_p, phase, h_f, h_g, h_fg).
3. **Optional first derivatives** (`∂ρ/∂P|h`, `∂ρ/∂h|P`, `∂T/∂…`) behind a **capability flag** — needed for the analytic-Jacobian path and the dynamic accumulator compressibility term. Declared now; only CoolProp's first derivatives need fill it initially.
4. **Capability flags** — e.g. `provides(σ_e)`, `provides(derivatives)`, `valid_range(identity)`. A backend asked for a property it lacks returns an explicit "unavailable," never a silent guess.
5. **No extrapolation by stealth** — out-of-range queries return unavailable/NaN with a warning, never a fabricated value.

### Ownership, lifecycle, selection

- **One backend instance per fluid identity, owned by the run**, shared by reference across all FluidStates of that fluid. Stateless with respect to the solve (internal caches are permitted because the contract is a pure function of (P, h, identity)). No import-time construction, no global mutable state.
- **A separate backend registry**, keyed by name, distinct from the Correlation Registry. Registration is startup-time.
- **Selection** is a `(fluid identity → backend name)` binding in the Reproducibility Tuple. Default backend = CoolProp. Replacing it with REFPROP or a tabulated surrogate is a tuple edit — config, not code.
- **Expected implementations:** `CoolPropBackend` (default), `RefpropBackend`, `TabulatedPropertyBackend` (the legacy CSV path — strategic, see §17), `EmpiricalCorrelationBackend` (Letsou-Stiel / Latini / Brock-Bird), and future `MixtureBackend`/`CustomFluidBackend`. A custom fluid or mixture is a new backend behind the same interface — extensibility identical in shape to "a new accumulator is a new closure."

---

## 7. Port and SystemState Architecture

`[F10]` (This section supersedes the Level 2 §2.1 statement that "the Port stores the value as a solver unknown," and closes Decision 002.)

### Port — connectivity only

A **Port carries connectivity, not values.** It holds identity, its owning component, a role annotation (inlet/outlet as *annotation*, not a hard constraint), and the connected peer. It is **immutable after Network assembly** and therefore safe to share by reference.

Connecting two ports asserts, **non-directionally**: equal pressure, equal enthalpy (for the fluid passing), and a mass-flow balance (at junctions the algebraic sum of ṁ is zero). Non-directionality keeps the DAE/simultaneous and dynamic formulations expressible.

### SystemState — the solver-owned unknown vector

The primary unknowns live in a **solver-owned `SystemState`**: a flat, ordered, indexable container holding every port-node's (P, h, ṁ) and every component's named internal states. **Port-variable handles**, created at Network assembly, map each port to its slots in that vector.

This is the natural home of "the solver owns the unknowns; nothing depends on the solver," and it is what makes the numerical seams fall out of one object:

- **Finite-difference Jacobian columns** reduce to copy-the-array-and-bump-one-entry.
- **Simultaneous Newton assembly** is native — the state vector *is* `x`; no scatter/gather into port objects.
- **Dynamic integrators** hold multiple simultaneous snapshots (trial, derivative, history, stages) as multiple arrays.
- **Linearisation / MPC / ROM** get the ordered, introspectable state list they require for free (§16).

The names `PortState` and `FlowState` are **retired as storage objects** — they are precisely the legacy two-sources-of-truth anti-pattern.

---

## 8. Geometry Architecture

`[F8]`

**Geometry is an immutable, standalone, flat family of typed value objects**, owned by the Component by composition, shareable by reference. There is **no god-object and no inheritance hierarchy** — the kinds share almost no fields, so a common base would be a near-empty interface or a bag of optionals (the speculative abstraction Principle 6 forbids). If a shared marker is ever needed, it is a field-less, behaviour-less tag. **The moment a base Geometry grows a field, the flat family has rotted into a hierarchy** — a review red flag.

The family (each exposing exactly the scalars its component's correlations consume):

- **`PipeGeometry`** `{L, D_h, A, roughness, trajectory}` — minimal flow geometry; single `D` serves as `D_h`. The elevation descriptor is a **`PipePath` trajectory** field, of which a single straight `Δz` segment is the v1 default — *not* the only representable form. Horizontal/vertical/inclined/curved/multi-segment runs, bends, and fittings are additive `PipePath` families that change no correlation contract; the passage forwards only derived scalars (`D_h`, `A`, `roughness`, per-cell `dz/dx`, `Σ K_L`). **Collectors and manifolds are Network topologies of pipe segments joined at Junctions, never a geometry field.**
- **`PlateGeometry`** `{N_plates, chevron_angle, plate_spacing, port_dims, A_per_plate, sink-side}` — no single `D`.
- **`MicrochannelGeometry`** `{N_channels, D_h,channel, fin_geometry, A_heated, wall_mass/material}` — exposes wall thermal mass (used by the frozen dynamic wall-capacitance term).
- **`AccumulatorGeometry`** `{V_total, containment, thermal?}` — a *containment* geometry only. **Geometry and pressure law are separated:** `V_gas_charge` and all law parameters (charge volume, heater duty, bellows area, spring rate, gas-charge pressure) live in the swappable `VolumePressureLaw` slot (§12), never in geometry. **PCA, HCA, bellows, spring-loaded, and gas-charged** are interchangeable law bindings selected in the tuple.

Rules:

- **Immutable, absolutely.** Varying a dimension produces a *new* Geometry → a *new* Reproducibility Tuple — exactly the unit Phase-5 DOE iterates over.
- **Supplies declared scalars, not itself.** Correlations receive `D_h`, `A`, `roughness`, `chevron_angle`, … — scalars, never a Geometry object. This decouples a correlation from any geometry *type*.
- **Derived dimensional accessors are allowed** (e.g. an annulus exposing `D_h = D_out − D_in` as a read-only accessor over stored primitives). Geometry computing *its own dimensional algebra* is permitted; Geometry computing a *correlation* (Nu, ΔP) is forbidden.
- **Excludes, always:** operating state, physics, time-varying quantities, and **the mesh** (§9). `[F7-geometry]`
- **Gravity is not Geometry.** Δz and orientation are Geometry; the **gravity magnitude/vector is a Scenario input** (default 1 g terrestrial). This makes a zero-g or variable-g spacecraft study a Scenario sweep, not a geometry rebuild. `[F17]`

---

## 9. Discretization Architecture

`[F16]` — the single most important new seam for the dynamic path; the one Level 1 omitted.

**Discretization is the fidelity axis of a component** — a small declared object `{mode, resolution}` that fixes the *count and structure* of the component's internal states and residuals. Three modes, declared in the interface from day one:

- **`Lumped` (0D).** One control volume; the v1 default for pipes, condenser, accumulator, reservoir, junctions, valves, pump.
- **`Segmented` (1D finite-volume).** N control volumes along the flow; per-segment states (and per-segment wall temperature for heated components). The meaningful steady mode for the evaporator.
- **`MovingBoundary`.** Zones whose boundaries move (two-phase ↔ liquid interface in the condenser); **the state count itself changes as zones appear/disappear.** Declared now, implemented in Phase 6.

Rules:

- **Owned by the Component's numeric configuration** — *not* Geometry (immutable, physical), *not* the Solver (which sees only the resulting unknown count).
- **Derived from Geometry, never stored in it.** Segment lengths = `L/N` from `PipeGeometry.L`; the same Geometry object serves a lumped and a segmented run. Putting the mesh in Geometry would make a fidelity switch a geometry edit and burden the immutable shareable object with a solver concern. **State count belongs to Discretization, never to Geometry, never assumed by the Solver.**
- **The component contribution contract is identical regardless of mode** — it always returns "my residuals and/or derivatives for my current internal states"; Discretization merely sets how many there are. This is what keeps the contract frozen-stable across the `Lumped → Segmented → MovingBoundary` progression.
- **MovingBoundary state count is queryable per step, not frozen at Network assembly.** The dynamic solver must support event detection (zone appearance/disappearance) as a first-class concept — declared now, built in Phase 6.

In steady state, a `Segmented` component's per-segment states are named with zero derivative; the dynamic solver *unfreezes* them rather than restructuring the component. Declaring `MovingBoundary` now — even unimplemented — means Phase 6 *activates a declared mode* rather than retrofitting a state structure.

---

## 10. Correlation Architecture

`[F4] [F11]`

A **Correlation is a stateless pure function** selected by name. It is the project's core research seam (Principle 2), kept deliberately lightweight.

### Contract

```
evaluate(CorrelationInput) → (value, ValidityVerdict)
```

- **Role-typed input.** Correlations receive a **role-typed `CorrelationInput` value object**, not positional scalars. There is **one input type per correlation role, not per formula**: Shah, Gungor-Winterton, and Kim-Mudawar all consume the same `HTCInput`; Friedel and Müller-Steinhagen-Heck share `TwoPhaseDPInput`. Roles are the enumerated slot set: `SinglePhaseDPInput`, `TwoPhaseDPInput`, `HTCInput`, `VoidFractionInput`, `VolumePressureLawInput`, … The role set is bounded by design and does not grow with the catalogue. **ε-NTU and LMTD are *not* correlation roles** — they are heat-exchanger *solution strategies* and belong to the separate `HeatExchangerModel` concept (§2, §12; `INTERFACE_SPEC.md` §8), not a `CorrelationInput` role.
- **The Component builds the input** from its FluidState(s) and the scalars it forwards from its Geometry. The correlation sees only data; it remains ignorant of component and geometry *type*, network topology, solver, and calibration.
- **`CorrelationInput` is an immutable, AD-traceable struct.** The same contract serves a Shah formula, a structured-FD Jacobian column, and a future ML/surrogate closure (whose input doubles as its feature vector) without special-casing.
- **A correlation returns a `ValidityVerdict`** alongside its value, declaring whether the call was in-envelope or extrapolated (and the envelope it checked against — fluid family, geometry range, flow-regime/quality range, Re/Bond bounds). **The framework warns on extrapolation; it never silently clamps or extrapolates.** Validity is a transparency output surfaced into the Result; the researcher decides acceptability but is never unaware.

### Registry, selection, replacement

- A lightweight **Correlation Registry** holds named, stateless instances grouped by role. Registration is startup-time (name → instance); it owns no per-run state. It is *not* a plugin framework, factory, or DI container.
- A Component declares **slots by role** ("I need a boiling-HTC and a two-phase-ΔP"). The Reproducibility Tuple **binds a registered name to each slot**.
- **Replacing a model = rebinding the slot name** in the tuple. Swapping Shah → Kim-Mudawar in an evaporator touches the configuration only — not the evaporator, solver, network, or neighbours. This operationalizes Principle 2.
- **The PropertyBackend is NOT in this registry** — it is a Layer-1 FluidState citizen with a different contract (no geometry, no slots), kept separate to avoid the DAG cycle (§6).

---

## 11. Calibration Architecture

`[F5] [F14]`

Calibration lets researchers reconcile models with experiment **transparently**: every correction is named, neutral by default, applied at one seam, and reported. No hidden empirical factors.

### What gets calibrated, and where

- **Pressure drop:** a multiplier `R*` on the **friction term only**, per `ΔP_total = R*·ΔP_friction + ΔP_gravity + ΔP_acceleration`. In gradient form (§12), `R*` multiplies the **friction gradient** `(dP/dx)_friction`. Gravity and acceleration are physics and are **never** scaled.
- **Heat transfer:** an analogous multiplier on the HTC (or UA), at the same kind of output seam.

Calibration is applied **by the Component, at the seam between a correlation's raw output and its use in a balance.** It is owned per-component correlation slot and resolves **slot → component → global (`none`/`target`, default neutral)**.

### The conservation firewall (three consequences, each a requirement)

1. **Correlations stay pure** — they return physics; calibration scales afterward. A reader of a correlation never sees a fudge factor.
2. **Conservation is never scaled** — calibration multiplies *closures* (ΔP_friction, HTC), never *balances* (mass/energy continuity).
3. **Calibration cannot mask an invariant violation** — because energy and mass balances are computed from *un-calibrated* conservation, a wrong calibration shows up as a *worse* match to data, never as a *false-passing* balance. Calibration can move the operating point; it can never make `Σṁ ≠ 0` look like zero.

### Modes and reporting

- **`none`** — all factors = 1; pure predictive physics; the default and honest baseline.
- **`target`** — factors chosen to meet a stated experimental target. A Result produced under `target` is **flagged as calibrated, not predictive**, and is never compared as-equal to a `none` run.
- Every non-neutral factor, its value, its mode, and its **seam location** are inputs in the tuple and outputs in every Result. *A factor that is not reported cannot exist.*
- **Dataset-fitting (least-squares over many points) is not calibration** — it is identification/surrogate territory (Phase 5), and must route its results back as ordinary explicit factors at this same seam, never as a parallel hidden mechanism.

---

## 12. Component Architecture

`[F8-internal-state] [F15]` — Internal states are named from day one, frozen (zero derivative) in steady state, unfrozen in dynamics.

### The contribution contract (frozen signature — §17)

> "Given a trial state at my Ports and my internal states, return my residual vector and/or my internal-state derivatives, written so they are continuous and differentiable across the saturation line."

A Component **must provide:** its declared Ports; its declared internal-state names (even when frozen); its contribution (residual and/or derivative) at a given trial state; its correlation slot declarations; the calibration factors actually applied; and the declared scalars it forwards to correlations.
A Component **must consume:** the (P, h, ṁ) at its Ports (handed in by the Solver via SystemState), its Geometry, parameters, Discretization, internal states, and the Scenario inputs bound to it.
A Component **must never access:** the Network or a neighbour; the Solver or its scheme; a correlation's formula; the PropertyBackend directly (it goes through FluidState); global inventory accounting.

### Internal-state membership test `[F15]`

> **A quantity is component internal state iff the component stores it and will provide its time-derivative in dynamics. Everything a component can recompute from port unknowns + geometry + correlations is NOT state.**

| Is internal state | Is NOT internal state |
|---|---|
| wall temperature(s) per cell | port P, h, ṁ (SystemState unknowns) |
| fluid mass / liquid & vapor inventory per cell | derived T, x, ρ (FluidState) |
| accumulator gas volume V_g | correlation outputs (HTC, ΔP) — recomputed each call |
| condenser moving-boundary positions (variable count) | system pressure P_sys (a SystemState unknown) |
| actuator states (valve position, pump shaft speed) — frozen v1 | — |

### 1D-passage philosophy (gradient form) `[F14]`

All 1D passages (Pipe, and by composition Evaporator/heated-Pipe/Condenser segments) **compute pressure gradients per control volume**; the Discretization integrates them; **total ΔP is a derived output, not the primary computational object.** Per cell:

- `(dP/dx)_friction` from the slot correlation (the only term `R*` scales);
- `(dP/dx)_gravity = ρ g dz/dx` (g from Scenario, dz from Geometry);
- `(dP/dx)_acceleration = d(G²v)/dx`.

Lumped mode is the **one-cell integration of the identical kernel**, so lumped, segmented, and dynamic share one physics kernel instead of diverging into separate code paths. The shared 1D mechanism stays *internal*, never a public primitive.

### Component reference table

Notation: ports `[in]`/`[out]`/`[branch_i]`; **(frozen v1)** = named-but-zero-derivative until Phase 6.

| Component | Ports | Geometry | Internal states | Correlation slots | Calibration | Scenario binding |
|---|---|---|---|---|---|---|
| **Pump** | `[in]`,`[out]` | minimal (perf-map ref); exposes L, A for inertia | **(frozen)** shaft speed / loop inertia I | pump performance/efficiency map | none typical | commanded ω or target ṁ |
| **Pipe** | `[in]`,`[out]` | `PipeGeometry` | **(frozen)** per-segment mass/momentum, wall T if heated (count = Discretization) | single-phase friction; two-phase friction; void fraction | R* on friction gradient | optional wall heat |
| **Evaporator** | `[in]`,`[out]` | `MicrochannelGeometry` | flow regime (algebraic); **(frozen)** wall capacitance/seg, fluid inventory | **boiling HTC**; two-phase ΔP (most correlation-sensitive) | HTC ×, ΔP_friction × | heat load Q / wall flux |
| **Condenser** | `[in]` (2φ),`[out]` (subcooled) | `PlateGeometry` | effective areas/zone; **(frozen)** moving-boundary positions | condensation HTC; ΔP — **plus a separate `HeatExchangerModel` slot** (ε-NTU/LMTD/segmented/moving-boundary), *not* a correlation | HTC/UA ×, ΔP_friction × | sink T and flow |
| **Accumulator** | one liquid `[port]`; wires reference node | `AccumulatorGeometry` (containment only) | liquid/gas split; **(frozen)** **V_g** (P derived) | one **volume↔pressure law** slot (PCA/HCA/bellows/spring/gas-charged) | none typical | P_set / control input |
| **Valve** | `[in]`,`[out]` | minimal (Cv) | **(frozen)** position | loss coefficient K_L vs opening | optional × on loss | opening fraction |
| **Junction** | `[trunk]` + N `[branch_i]` | minimal | none (negligible storage) | none intrinsic | none | — |
| **Reservoir** | `[in]`,`[out]` | containment volume | inventory; **(frozen)** liquid level | none | none | — |

Two component-shape decisions are baked in (Level 1 hedges removed):

- **`Junction` is one n-in/m-out conservation node**; `Splitter` (1-in/N-out) and `Mixer` (N-in/1-out) are configurations of it, optionally exposed as thin factory aliases for readability. It supplies only mass + energy conservation and equal node pressure; **it never knows another branch exists.**
- **`Accumulator` is the pressure-reference component**, and its **geometry (containment) is separate from its pressure-reference law** — a swappable slot. PCA, HCA, bellows, spring-loaded, and gas-charged are interchangeable law bindings selected in the tuple: a new accumulator technology is a new law, not a redesigned component. It stores **V_g** and derives P.
- **`Reservoir` is a distinct component** that holds liquid inventory and guarantees NPSH but **sets no pressure reference.** The Accumulator sets the reference; the Network is the single inventory accountant.

---

## 13. Network Architecture

`[F7]`

The Network states **what must hold**, never **how to make it hold**. Responsibilities split cleanly across Network / Component / Solver as **where / what / how**:

| Owner | Owns | Role |
|---|---|---|
| **Network** | connection graph; continuity conditions; loop-closure conditions; **uniqueness** of the pressure reference; branch structure (splitter↔mixer pairing, equal-ΔP branch sets); global mass-inventory accounting; topology validation | **Where** |
| **Component** | geometry, parameters, internal states, slots, calibration; its local balance; the *law/value* of any reference it sets | **What** |
| **Solver** | assembly of contributions; numerical scheme; convergence/integration; residuals & invariants | **How** |

- **Loop closure** — "the sum of pressure changes around any closed path = 0" — is a Network condition the Solver satisfies. No single component closes the loop; closure is emergent and global. This embodies the **pressure-is-global / enthalpy-is-local** asymmetry: pressure is globally coupled and needs a closure correction; enthalpy is advected with mass flow and propagates locally. Fixed-point iteration exploits this (iterate global pressure/flow, march local enthalpy).
- **Branch handling** — parallel branches between a common splitter and mixer share the **same ΔP**, with branch flows summing to the trunk. The Network states it; the Solver enforces it; the Junction supplies only conservation; the branches supply only their resistances. **Adding a branch is a topology edit, never a solver or component edit.**
- **Pressure-reference management** — the topology validator enforces **exactly one** reference. The Accumulator owns the law/value; the Network owns which node and the one-reference invariant; the Solver owns global consistency. A second accumulator is caught by topology validation, not discovered as a numerical pathology.
- **Global mass inventory is a first-class Network quantity from v1** (steady checks total charge; dynamics attaches redistribution equations to the existing accountant).
- **Topology validation verdict:** no dangling ports, exactly one pressure reference, well-formed splitter↔mixer branch sets, no double-counted inventory.

---

## 14. Solver Architecture

`[F1] [F7]`

The Solver is the **sink of the DAG**: it reads the Network and Component contributions, owns the SystemState, and drives the system to satisfaction. **Nothing depends on the Solver; a new solver requires zero changes below it.**

- **Local/global split.** Each Component computes its own contribution from its port states + internal states (it never reaches outside itself). The Solver assembles all contributions + all Network continuity/closure conditions into one global system over the SystemState and drives it to convergence (steady) or marches it in time (dynamic).
- **Steady-state strategies, both behind the same component contract:**
  - **Fixed-point pressure iteration** — robust starting point for single loops.
  - **Simultaneous Newton–Raphson** on the full residual vector — kept a **first-class option, not only fixed-point**, because the dynamic path is inherently simultaneous and inherits a tested simultaneous assembler. The legacy `(R1 = ΔP_pump − ΣΔP, R2 = P_sys − P_acc)` residual shape is the proven basis.
- **The Solver obtains the Jacobian itself** — by structured finite differences over the Component contract in v1, optionally accepting an analytic/AD Jacobian a Component may provide as an override. Components are *not* required to provide residual derivatives — only to be *differentiable* (no hidden non-smooth branches at phase transitions, which (P, h) already helps with).
- **Validation invariants are first-class Solver outputs** feeding the Result: global energy imbalance, mass imbalance, pressure-closure residual, and physical-bound checks (0 ≤ x ≤ 1, T < T_crit), all computed from un-calibrated conservation.
- **Must never access** any physics, correlation, geometry, or property formula. It must work for *any* valid Network.

---

## 15. Configuration, Scenario and Result

A simulation is described **entirely** by the **Reproducibility Tuple** (Principle 7): `topology + component parameters + geometries + fluid identity + correlation selections + heat-exchanger-model selections + accumulator-law selections + calibration + scenario + solver settings`. It is serializable, **versioned**, and immutable; no run depends on anything outside it. The `hx_model_selections` (per heat-exchanger component) and `accumulator_law_selections` (per accumulator) bindings make every swappable model a named tuple entry, exactly as `correlation_selections` does for closure slots.

### Scenario structure

**Scenario is decomposed into five role-typed parts**, so DOE, surrogate generation, dynamic simulation, and future MPC each draw from the part they need:

- **Boundary conditions** — evaporator heat load, condenser sink inlet T and flow, fixed inlet states, the accumulator pressure setpoint (the reference *value*).
- **Commands** — pump speed or flow target, valve opening.
- **Disturbances** — time-varying inputs (declared now, constant/empty in v1; activated by dynamics and consumed by future MPC).
- **Environment** — gravity vector (default 1 g), ambient temperature, ambient heat-loss condition.
- **Operating point** — the named steady operating-point specification (the DOE coordinate label) the run targets.

Gravity stays under Environment; `P_set` is a boundary condition; pump/valve commands are Commands; the pressure-reference *law* is Component while *which node* is the reference is Network (§4.2, §13). The `(Scenario → Result)` mapping is the surrogate training pair, and the Scenario provides the input vector for the Sensitivity/Linearisation seam (§16).

### Division of responsibility

| Belongs to | What | Membership test |
|---|---|---|
| **Scenario / BoundaryConditions** | heat loads, sink T/flow, pump command/speed, **gravity**, ambient, accumulator P_set | "If I sweep this in Phase 5 without rebuilding the loop, it is Scenario." |
| **Network** | which components exist, how Ports connect, branch topology, which node is the reference, inventory accounting | "If changing this changes the P&ID, it is Network." |
| **Component** | Geometry, fixed parameters (η, Cv, channel count), slot selections, calibration factors, Discretization mode, internal-state names | "If changing this changes one part without re-wiring, it is Component." |

Scenario is the **primary DOE axis** for Phase 5: keeping it cleanly separate lets a surrogate dataset sweep thousands of operating points against a *fixed* Network and *fixed* Components, with every Result attributable to an exact tuple. Solver type/tolerances are solver settings; fluid choice is tuple-level identity selecting the PropertyBackend.

### Result / Solution

The **Result** is the atomic output unit, paired with its tuple, governed by the same single-source-of-truth rule.

- **Stored (irreducible):** converged Port (P, h, ṁ); converged component internal states; a reference (by value or content-hash) to the Reproducibility Tuple.
- **Derived on demand (never stored redundantly):** profiles of P, h, x, T, ρ along the loop (recomputed from stored (P, h) through FluidState); heat rejected, outlet quality, subcooling, pump power.
- **Reported (first-class, always present):** the validation invariants (energy/mass imbalance, pressure-closure residual, physical-bound checks); the calibration report (every non-neutral factor, value, mode, seam); validity verdicts for any out-of-envelope correlation; convergence metadata; and the predictive-vs-reconciled flag.

A Result **without** energy-imbalance, pressure-closure, quality-bounds, and calibration-report fields is **malformed**. The Result schema is **versioned and minimal** so a 5-year-old surrogate dataset remains interpretable, and the `(Scenario in tuple) → (invariants + outputs in Result)` mapping is exactly the input/output pairing a surrogate model trains on.

---

## 16. Dynamic Readiness Strategy

The architecture is **structurally dynamic-ready**; the dynamic mechanisms are deferred but their seams are prepared now (Principle 6 applied to the future).

### Decisions that already carry into dynamics (keep)

1. **(P, h) primary state** — already the variable the dynamic energy equation stores; density derived.
2. **Internal states named even when frozen** — wall capacitance, gas/liquid volumes, fluid inventory, moving-boundary positions are named now, derivatives held at zero; unfreezing is activation, not invention.
3. **Component contract = residual and/or derivative** — same contract, different solver.
4. **Solver behind a stable interface** — the dynamic solver is an additional DAG sink touching nothing below it.
5. **Non-directional ports** — the simultaneous/DAE formulation is already expressible.
6. **Accumulator as a real component** — the "brain" needs only its derivative law activated. It stores **V_g** and derives P (`dP/dt` from `dV_g/dt`), preserving single-source-of-truth even for the pressure-anchoring component.
7. **SystemState** — a flat ordered state vector is precisely what dynamic integration and state-space extraction need.

### Prepared seams (declared now, built in their phases)

- **Discretization fidelity axis** (§9) — `MovingBoundary` declared now, with per-step queryable state count and event detection as first-class dynamic-solver concerns.
- **Simultaneous/DAE assembly** kept a first-class steady option, so the dynamic solver inherits a tested assembler; **the steady solution is the consistent initial condition for the DAE**, so steady and dynamic solvers share one residual assembly.
- **Global mass inventory** as a first-class Network quantity from v1.
- **Fluid inertia** for loop momentum (`dṁ/dt = (ΔP_pump − ΔP_loop)/I`, `I = L/A`) is derivable from Geometry; Pipe/Pump geometry exposes L and A. No new state.

### Sensitivity and Linearisation seam `[F18]`

- **Structured finite differences are the primary sensitivity mechanism** (v1 and likely beyond). **Analytic property derivatives** are used where the backend provides them (§6, capability flag). **Smoothed/regularised property derivatives near saturation** are the recommended technique for gradient-based control — because (P, h) buys *continuity* across the dome, **not smoothness**: property slopes have kinks at x = 0 and x = 1.
- **Automatic differentiation through the property layer is not promised.** CoolProp/REFPROP are compiled external libraries for which AD is generally unavailable. The AD seam is kept open but **the architecture does not build on it**, and this document does not state AD as a promised path.
- **A single Sensitivity/Linearisation seam** unifies three uses that share one machinery — the Newton Jacobian, the implicit-dynamic Jacobian, and the linearised `(A, B, C, D)` extraction for MPC/ROM/surrogate work. The contract: *given the assembled system and a SystemState operating point, perturb the SystemState and Scenario inputs, re-evaluate residuals and outputs, and assemble sensitivities.* The ordered, introspectable SystemState is the precondition; the Scenario provides the input vector; the Result quantities provide the output vector.

**What is explicitly NOT built now:** the time integrator, moving-boundary equations, wall-conduction networks, dynamic inventory redistribution, the AD path, and the surrogate/identification tooling. Their seams are declared; their mechanisms wait for their phases.

---

## 17. Legacy Migration Decisions

`src/` is built from this architecture, not ported from legacy. Legacy code is judged only by what it can contribute, under four verdicts — **Reuse** (cosmetic change only), **Adapt** (sound physics, re-housed behind an approved interface), **Rewrite** (idea needed, implementation violates the DAG too deeply to port), **Discard**.

### Project verdicts

- **`A0_SS_v3_Stable`** — architecturally unusable (module-level globals, runs on import), but the **richest source of validated physics**: HEM closures, the mixture friction factor, the nucleate+convective boiling ΔT fixed-point, condensation HTCs, the `R*` per-region calibration concept (independent rediscovery of the calibration firewall), the two-pass momentum corrector, and embedded **Fujii (2004) validation data**. *Discard the structure; Adapt the equations and the R\* concept; Reuse the validation data.*
- **`PyP2PL`** — the most complete component-based attempt and the **best Kokate (2024) R-134a validation asset** (digitised data + MAE Eq. 17 + four worked sweeps). But its FluidState is T-anchored (violates Decision 001), its solver is a Kokate control-law march with no loop closure, and its correlations carry globals/hacks. *Adapt the five boiling correlations + MSH/Churchill ΔP + validation; Rewrite the solver and FluidState; keep the component decomposition as reference only.*
- **`MPL_Simulator`** — **the primary harvest target**, having independently converged on much of the approved architecture: (P, h)-anchored FluidState, a CoolProp→empirical→tabulated fallback chain, a Protocol-based correlation registry, HCA+PCA behind one `set_pressure()`, and a simultaneous Newton solve on (ṁ, P_sys). *Adapt aggressively; Rewrite the ownership leaks* (Port stores derived state; eager FluidState construction; flat imports; out-of-band `accumulator.set_pressure()`; single-loop topology).

### Strategic property asset

The **fluid-property fallback chain** plus the `A1_TwoPhProp` tabulated mechanism is the most strategically reusable asset — it is the **only legacy source of electrical conductivity (σ_e) and relative permittivity (ε_r)**, which CoolProp does not expose, and it covers 29 fluids. It becomes the `TabulatedPropertyBackend`.

> **⚠ Critical data-availability finding.** The 29 CSV property tables the loader expects are **not present anywhere in `legacy/`** — only the loader code survives. The sole CSVs in the tree are PyP2PL sweep *outputs*, not property tables. The `TabulatedPropertyBackend` is therefore structurally portable but **functionally empty until the original CSVs are located/regenerated and versioned** under the package. This is a data task, not a code task.

### Harvest order

1. **FluidState + PropertyBackend split** (Adapt MPL `fluid_properties.py` + `A1_TwoPhProp.py`); locate the 29 CSVs in parallel.
2. **Correlation Registry** (Adapt MPL `correlations.py`; fold in PyP2PL's five boiling correlations and A0's boiling/condensation/friction). Tighten to the `CorrelationInput` contract; add validity envelopes.
3. **Calibration seam** (Adapt A0's `R*` as the per-slot friction/HTC multiplier).
4. **Component contract + first components** (Rewrite from references: Pipe → Pump → Accumulator (MPL HCA/PCA) → Evaporator (PyP2PL recipe) → Condenser (MPL ε-NTU)). Name internal states; attach Discretization.
5. **Network + simultaneous Solver** (Adapt MPL's Newton residual shape behind a real Network; Accumulator as reference node).
6. **Validation harness** wired from commit one: Kokate (2024) R-134a, Li et al. (2021) Acetone, Fujii et al. (2004), plus PyP2PL example sweeps as the first Scenario/Result fixtures.

### Recurring violations to guard against during the port

Stored derived state on Port/State objects; per-component property-engine construction or direct CoolProp calls; topology baked into the solver; the solver reaching into components out-of-band; correlations receiving whole component/state objects or carrying globals/hacks; run-on-import / module-level state. Each maps to a forbidden DAG direction (§3) and an anti-pattern (§19).

---

## 18. Implementation Gate

The architecture is mature enough to begin **Phases 1–4 (steady-state)**. The remaining work before code is **interface specification, not architecture.**

### The five frozen interfaces (a late change to any is a redesign, not an edit)

1. The **dependency DAG and its forbidden directions** (§3) — the interfaces must make forbidden directions unrepresentable.
2. The **stored-vs-derived ownership boundary** (only P, h, ṁ + named internal states are stored, in SystemState).
3. The **Component contribution contract** signature (residual and/or derivative + declared internal-state names + the differentiability promise). Adding dynamics must not change it.
4. The **Port interface** (connectivity only; non-directional connect; handles into SystemState).
5. The **Reproducibility Tuple schema** (serializable, versioned) — Phase 5 batch generation depends on it.

### The four interface documents to produce next (the only gate between here and code)

1. **`INTERFACE_SPEC.md`** — precise signatures for the five frozen contracts: Component contribution, Port connect, Correlation evaluate (`evaluate(CorrelationInput) → (value, ValidityVerdict)`), PropertyBackend query (vector-first + capability flags), Solver/Network assembly over SystemState. It additionally specifies the **`HeatExchangerModel` seam** (heat-exchanger solution strategies, separate from correlations), the **`PipePath` trajectory** generalization of `PipeGeometry`, the **accumulator geometry↔law separation**, and the **five-part Scenario decomposition** — refinements integrated during interface specification and reconciled into §2, §8, §10, §12, and §15 above. *Highest priority.*
2. **`SCHEMA_SPEC.md`** — serialization schema and version field for the Reproducibility Tuple and the Result.
3. **`CORRELATION_CONTRACT.md`** — the validity-envelope declaration format and the `ValidityVerdict` return shape; the per-role `CorrelationInput` types.
4. **`TEST_PLAN_V1.md`** — the mapping from the validation plan's levels to concrete checks (unit: friction factor, quality; component: each §12 component; loop: closure + invariants; literature: Kokate R-134a as the first end-to-end target).

### Recommended first vertical slice

`FluidState + PropertyBackend (CoolProp) → Port → one friction Correlation + registry → Pipe (Lumped) → a trivial two-component Network → fixed-point steady Solver → Result with invariants.` This exercises every DAG layer end-to-end on the simplest loop, surfacing interface friction before the expensive components are built. Then add Pump, Accumulator, Evaporator, Condenser, Junction against the now-proven contracts.

---

## 19. Anti-Patterns (the code-review checklist)

Each is tied to the guard that forbids it.

1. **Geometry owning physics** — a Geometry computing Nu or holding a correlation. *Guard:* Geometry supplies declared scalars only; Layer 0; computes nothing (§8).
2. **Components knowing topology** — a junction asking for another branch's flow; an evaporator referencing its condenser. *Guard:* a Component may never name the Network or a neighbour; branch closure is a Network condition (§3, §12, §13).
3. **Calibration hidden inside correlations** — a fudge factor baked into a formula. *Guard:* correlations are pure; calibration scales the *output* at the seam, scales closures never balances, always reported (§11).
4. **Duplicated state ownership** — caching T or ρ beside (P, h); two components claiming inventory; two pressure references. *Guard:* only P, h, ṁ + internal states stored, in SystemState; FluidState derives the rest; one inventory accountant; one reference (§4, §7).
5. **Solver–physics entanglement** — a component aware it is Newton-iterated, hard-coding a timestep, or storing a Jacobian assumption. *Guard:* the contract is residual/derivative only; the Solver owns numerics and builds the Jacobian itself; nothing depends on the Solver (§12, §14).
6. **Correlations welded into components** — hard-coded `if regime == annular: shah()`. *Guard:* named slots filled from the registry by configuration (§10).
7. **The mesh living in Geometry** — segment/zone count stored in the immutable Geometry. *Guard:* state count owned by Discretization, derived from but never stored in Geometry (§9).
8. **Geometry hierarchy creep** — a base `Geometry` growing fields/optionals. *Guard:* flat typed family; any shared marker is field-less (§8).
9. **PropertyBackend as a slot Correlation** — putting CoolProp in the per-component correlation registry. *Guard:* PropertyBackend is a Layer-1 FluidState citizen, separate registry, no geometry, no slots (§6).
10. **Scenario folded into component parameters** — treating heat load or sink T as a fixed component attribute. *Guard:* Scenario is first-class and the primary DOE axis, bound-to but separate-from components (§15).
11. **Result as a bag of stored numbers** — persisting T/x/ρ profiles beside (P, h). *Guard:* Result stores minimal converged state + tuple reference; profiles/invariants derived (§15).
12. **Speculative generality** — a plugin system, event bus, DI container, or abstract-primitive component model. *Guard:* abstraction only when two concrete cases demand it; the fixed concept inventory; physical-component vocabulary kept public (Principle 6, §2).
13. **State on Port objects** — storing or caching (P, h, ṁ) or derived properties on a Port. *Guard:* Port is connectivity only; SystemState holds the unknowns; the names PortState/FlowState are retired (§7).
14. **Promising AD through the property layer** — building a gradient-based path on AD through CoolProp. *Guard:* FD-primary, analytic-where-available, AD-not-promised; smoothed derivatives near saturation (§16).

---

## 20. Approved Decisions Summary

The frozen decision set. Spine decisions (F1–F9) are mature foundations; F10–F18 were ratified during the open-questions pass and recorded as Decisions 004–009. **These are immutable for v1.**

| Tag | Decision | Section |
|---|---|---|
| **F1** | One-directional dependency DAG and its forbidden directions; nothing depends on the Solver. | §3 |
| **F2** | (P, h) + identity canonical; everything else derived. | §5 |
| **F3** | Single-source-of-truth: only primary unknowns + named internal states stored; T/x/ρ/μ derived. | §4 |
| **F4** | Correlations stateless, swappable, selected by name; ignorant of component/geometry-type/topology. | §10 |
| **F5** | Calibration at the per-component correlation-output seam; scales closures never balances; resolution slot → component → global; conservation firewall. | §11 |
| **F6** | PropertyBackend is a Layer-1 FluidState citizen, separate from closure correlations. | §6 |
| **F7** | Network/Component/Solver where/what/how split; one pressure reference; network-level branch closure; single inventory accountant. | §13 |
| **F8** | Geometry = immutable, flat typed family, composed, shareable; mesh excluded. | §8 |
| **F9** | Accumulator as first-class **pressure-reference component**; geometry (containment) separate from the swappable volume↔pressure law; PCA/HCA/bellows/spring/gas-charged interchangeable. | §12 |
| **F10** | Port = connectivity; SystemState (solver-owned) stores P, h, ṁ + internal states; no cached derived properties anywhere. *(Decision 004; closes Decision 002.)* | §7 |
| **F11** | Correlation contract = `evaluate(CorrelationInput) → (value, ValidityVerdict)`, one input type per role, built by the component. *(Decision 005.)* | §10 |
| **F12** | FluidState = pure `(P, h, mixture-capable identity)`; properties served vector-first by the backend; never stored on the state. *(Decision 006.)* | §5 |
| **F13** | PropertyBackend interface: vector-first queries + optional derivatives + capability flags + per-identity selection; one shared instance per fluid per run; separate registry. *(Decision 006.)* | §6 |
| **F14** | All 1D passages contribute per-cell gradients/residuals over their Discretization; total ΔP is a derived output; R* multiplies the friction gradient only. *(Decision 007.)* | §12 |
| **F15** | Component internal state = stored quantities whose derivatives dynamics will provide; port (P, h, ṁ) and derived properties are never component state; the accumulator stores V_g and derives P. *(Decision 008.)* | §12 |
| **F16** | Discretization = `{mode ∈ Lumped\|Segmented\|MovingBoundary, resolution}`, owned by the component numeric config, derived-from but never stored-in Geometry; MovingBoundary state count is queryable per step. *(Decision 007.)* | §9 |
| **F17** | Gravity is a Scenario input (default 1 g); Δz/orientation are Geometry. *(Decision 007.)* | §8 |
| **F18** | Sensitivity stance: structured FD primary; analytic property derivatives where available; AD not promised. One Sensitivity/Linearisation seam serves Jacobian, implicit dynamic integration, and MPC/ROM/surrogate extraction. *(Decision 009.)* | §16 |

**Deliberately left unfrozen** (where the research happens — freezing them would defeat the architecture's purpose): the concrete solver choice, the concrete PropertyBackend per fluid, the correlation catalogue contents, the Discretization resolution and mode per component, the topology, backend caching/threading internals, Result serialization bytes, and whether/when an AD path is ever added.

---

## Appendix A — Decision Provenance

| MASTER element | Originating source |
|---|---|
| §1 Principles | L1 §1 (condensed) |
| §2 Concept inventory | L1 §2; L3 §2; + SystemState (Decision 004), Junction (L3 §4) |
| §3 Dependency rules | L2 §1 |
| §4 Ownership | L2 §2; L3 §9; Decisions 004, 008 |
| §5 FluidState | L1 §4; Decision 001, 006 |
| §6 PropertyBackend | L2 §6/§10-#1; L3 §2; Decision 003, 006 |
| §7 Port / SystemState | L2 §2.1 (amended); OAQ §2; Decision 002 (closed), 004 |
| §8 Geometry | L2 §2.2/§5; L3 §5; Decision 007 |
| §9 Discretization | L2 §9-A/§10-#1; L3 §6; Decision 007 |
| §10 Correlation | L1 §8; L2 §6; L3 §7; Decision 005 |
| §11 Calibration | L1 §9; L2 §7; L3 §8; Decision 005 |
| §12 Component | L1 §6; L3 §4; OAQ §7, §8; Decision 007, 008 |
| §13 Network | L2 §8; L3 §4 |
| §14 Solver | L1 §7; L2 §8, §9; L3 §3.4 |
| §15 Configuration/Scenario/Result | L2 §10-#2,3,6; L3 §8, §9 |
| §16 Dynamic readiness | L1 §10; L2 §9; L3 §6; OAQ §9; Decision 009 |
| §17 Legacy migration | ARCHITECTURE_REVIEW_LEGACY §1–8 |
| §18 Implementation gate | L3 §1.3, §12 |
| §19 Anti-patterns | L3 §11; + §7, §16 additions |
| §20 Decision summary | OAQ §11; DECISION_LOG Decisions 001–009 |

---

*End of ARCHITECTURE_MASTER.md — the single source of architectural truth for the MPL simulation framework. Decisions F1–F18 are frozen for v1. The next artifacts are the four interface documents of §18, after which implementation of Phases 1–4 may begin.*
