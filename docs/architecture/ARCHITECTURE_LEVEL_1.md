# ARCHITECTURE_LEVEL_1.md

**Conceptual architecture of the MPL simulation framework**

Status: architecture definition (pre-implementation)
Scope: Level 1 — concepts, responsibilities and relationships only. No code, no class design, no UML.
Horizon: must remain usable for research over 5–10 years.

This document defines *how to think* about the framework before any class is written. It is binding at the conceptual level: it fixes the vocabulary, the responsibilities, and the seams along which the system may evolve. It deliberately leaves implementation free.

A note on method: every decision below is argued from **two** directions — what the physics of mechanically pumped two-phase loops requires, and what keeps a scientific codebase alive for a decade. Where the two pull in different directions, the physics wins and the software adapts; we never adopt a pattern only because it is elegant.

---

## 1. Core Design Principles

These principles are ordered. When two conflict, the earlier one governs.

### 1.1 Physical transparency before software elegance
Every quantity that appears in the solver must have a name a thermal engineer recognises (pressure, specific enthalpy, mass flow rate, quality, wall temperature) and a defensible physical meaning. No state variable exists purely for numerical convenience without being documented as such.

- *Physics justification:* the literature is unanimous that the value of these models is in **interpreting** results (where does the subcooling appear, which branch starves, why does the accumulator set the pressure). A model you cannot interpret is not a research tool.
- *Software justification:* transparent state is debuggable state. A researcher five years from now must be able to read a residual vector and know what diverged.

### 1.2 Replaceability at the model seam
A researcher must be able to replace one evaporator model, one pressure-drop correlation, one accumulator law, or one heat-transfer correlation **without touching the solver and without touching neighbouring components**. This is the single most important structural requirement and most of Section 2–8 exists to protect it.

- *Physics justification:* the open research questions (instability mapping, HEM entrainment corrections, control-authority trade-offs) will be answered by *swapping models and comparing*, not by rewriting the framework.
- *Software justification:* the seams you can change cheaply are the only places real research happens; everything else must be stable.

### 1.3 Separation of physics from numerics
The equations a component contributes (mass/momentum/energy balance, closure relations) are stated independently of *how* they are solved (steady-state algebraic iteration vs. time integration). A component declares its contribution; a solver decides the scheme.

- *Physics justification:* the same evaporator energy balance appears in steady-state pressure-drop iteration and in dynamic ODE integration. The physics does not change; the bookkeeping does.
- *Software justification:* this is the seam that lets the steady-state-first roadmap reach dynamics (Phase 6) without a redesign — see Section 10.

### 1.4 Validation-first design
The framework is built so that *verification is cheap and continuous*, not retrofitted. Energy and mass balances, pressure closure, and physical-bound checks (0 ≤ x ≤ 1, T below critical, etc.) are first-class outputs, not afterthoughts. Calibration factors are explicit, named, defaulted to neutral, and reported.

- *Physics justification:* the whole project is justified against literature and bench data; a result without a residual is not a result.
- *Software justification:* a scientific framework without built-in invariants rots silently — the worst failure mode, because results keep coming.

### 1.5 Numerical robustness as a stated property
Single-phase ↔ two-phase transitions, near-zero quality, and near-critical states are the normal operating regime, not edge cases. The state representation and the solver contracts are chosen specifically so these transitions are continuous and do not require variable switching (Section 4).

- *Physics justification:* two-phase loops *live* on the saturation line; a representation that is fragile at x→0 or x→1 is unusable.
- *Software justification:* robustness designed in is cheaper than robustness patched in around every `if phase == ...`.

### 1.6 Modularity proportional to need (anti-over-engineering)
We introduce an abstraction only when at least two concrete cases already demand it, or the roadmap names a third within the planned horizon. We do **not** build plugin systems, dependency-injection containers, event buses, or speculative generality. A handful of well-chosen concepts (Section 2) is the entire architecture.

- *Physics justification:* the physical domain is genuinely small — a dozen component types, a handful of correlation families. It does not need a large abstraction surface.
- *Software justification:* every speculative abstraction is a maintenance liability and a barrier to the next researcher. The cheapest code to maintain is the code that was never written.

### 1.7 Reproducibility
A simulation is fully determined by: topology + component parameters + fluid + correlation choices + calibration settings + solver settings. That tuple is serialisable and is the unit of an experiment. No result depends on hidden global state, on call order, or on an un-versioned default.

- *Physics justification:* surrogate-model generation (Phase 5) produces thousands of runs that must be exactly attributable to inputs.
- *Software justification:* reproducibility is what makes a 5-year-old result still trustworthy.

---

## 2. Fundamental Concepts

Eight concepts form the whole vocabulary. Everything else is a specialisation or a utility. For each: definition, responsibilities, what belongs inside, what does not.

### 2.1 Component
**Definition.** A physical element of the loop that conserves and/or transports mass, momentum and energy: pump, pipe, evaporator, condenser, accumulator, valve, splitter, mixer, reservoir.

**Responsibilities.**
- Own its **geometry** and **parameters**.
- Own its **internal states** (e.g. wall temperature, gas volume) when it has any.
- Given the states at its ports and its internal states, produce its **physical contribution**: the residual equations (steady-state) and/or the time derivatives of its internal states (dynamic).
- Request closure quantities (HTC, pressure drop, void fraction) from **correlations** it holds, without knowing the correlations' internal formulae.

**Belongs inside.** Conservation logic for *this element*; geometry; parameters; internal state definitions; choice of which correlation slots it exposes.

**Does NOT belong inside.** Knowledge of the network topology or of neighbouring components; the numerical scheme (Newton step, time integrator); fluid-property formulae (those come from the fluid model via the state); the specific algebra of a correlation; global mass-inventory accounting.

### 2.2 Port
**Definition.** The named connection interface through which a component exchanges fluid with another component. A connection is two ports declared equal.

**Responsibilities.**
- Carry the **interface variables** that define the fluid crossing the boundary (Section 5).
- Define a connection point so that the network can enforce continuity (equal pressure, equal enthalpy, mass-flow balance) across a junction.

**Belongs inside.** The minimal set of interface variables and a notion of identity/connectivity.

**Does NOT belong inside.** Any physics (a port does not compute pressure drop); any property calculation; storage of history.

### 2.3 Fluid State
**Definition.** The complete thermodynamic state of the working fluid at a point, anchored on two **primary independent variables** plus the fluid identity, from which all other properties are derived.

**Responsibilities.**
- Hold the primary variables (recommended: pressure **P** and specific enthalpy **h** — Section 4).
- Provide *derived* properties on demand: T, T_sat, quality x, ρ, μ, σ, k, c_p, phase.
- Be the **single source of truth** for properties, delegating to the property backend (CoolProp/REFPROP) or a tabulated surrogate.

**Belongs inside.** Primary variables; fluid identity; access to derived properties; phase identification.

**Does NOT belong inside.** Conservation equations; geometry; any notion of *where* in the loop it is; the choice of solver. A Fluid State is a value, not an actor.

### 2.4 Geometry
**Definition.** The fixed physical description of a component's flow passages and solid structure: lengths, diameters/hydraulic diameters, flow areas, number of channels, wall thickness and material, heat-transfer areas, roughness, elevation change.

**Responsibilities.**
- Provide the dimensional inputs that correlations and conservation laws need.
- Be inert: geometry does not compute physics, it supplies parameters to those who do.

**Belongs inside.** Dimensions, areas, counts, material thermophysical constants, orientation/elevation.

**Does NOT belong inside.** Operating state; correlations; any time-varying quantity. Geometry is constant for a given simulation.

### 2.5 Correlation
**Definition.** A swappable empirical or semi-empirical closure relation: heat-transfer coefficient, two-phase pressure-drop multiplier/friction factor, void fraction, and (as a special family) the property model itself.

**Responsibilities.**
- Given a fluid state and the relevant geometry/flow quantities, return a single physical closure quantity (e.g. α, ΔP, ε_void).
- Declare its validity envelope (fluid, geometry range, flow regime) for transparency.

**Belongs inside.** One formula family and its parameters; its applicability range.

**Does NOT belong inside.** Conservation equations; knowledge of which component is calling it; calibration bookkeeping (calibration multiplies the *result* at a defined seam — Section 9); solver concerns.

### 2.6 Calibration
**Definition.** The explicit, named set of multipliers/parameters that scale model outputs (principally pressure drop and heat transfer) to match experiment, together with a declared **mode**.

**Responsibilities.**
- Hold calibration factors with neutral defaults (factor = 1, mode = `none`).
- Apply at a single, documented seam (between a correlation's raw output and its use in a balance).
- Be reported in every result so no correction is ever hidden.

**Belongs inside.** Named factors; mode (`none`/`target`, see Section 9); the rule for where they apply.

**Does NOT belong inside.** The physics being calibrated (a calibration scales a correlation; it is not itself a correlation); silent global fudge factors.

### 2.7 Network
**Definition.** The topology: the set of components and the connections between their ports, including parallel branches and junctions. The Network is the *assembled loop*.

**Responsibilities.**
- Hold components and their connectivity.
- Define the continuity conditions at every connection and the closure conditions of the loop (the loop must close on pressure; mass must balance at junctions; the accumulator sets the reference pressure).
- Expose, to the solver, the full set of unknowns and equations without itself solving them.
- Account for **global mass inventory** when required (total charge distributed across components).

**Belongs inside.** Component registry; connection graph; continuity/closure conditions; topology validation (no dangling ports, exactly one pressure reference).

**Does NOT belong inside.** The numerical algorithm; per-component physics; correlation choices. The Network describes *what must hold*, not *how to make it hold*.

### 2.8 Solver
**Definition.** The numerical engine that takes a Network's unknowns and equations and finds the state that satisfies them — algebraically (steady state) or by time integration (dynamic).

**Responsibilities.**
- Assemble the global system from component contributions and network conditions.
- Drive it to convergence (steady) or march it in time (dynamic).
- Report residuals, iteration counts, convergence status, and the validation invariants.

**Belongs inside.** The numerical scheme (Newton–Raphson, fixed-point pressure iteration, RK/implicit integrator), the assembly of contributions, convergence control.

**Does NOT belong inside.** Any physics (it must work for any valid Network), any correlation, any geometry. A new solver must require **zero** changes to components.

---

## 3. Component Philosophy

The question: should the framework be built from **physical components** (Pipe, Evaporator, Condenser, Pump, Accumulator, Valve, Splitter, Mixer) or from **abstract distributed primitives** (FlowComponent1D, DistributedComponent, ThermalComponent)?

### Option A — Physical components
A class per recognisable piece of hardware.

- **Advantages.** Maps one-to-one to how engineers describe a loop and to how the literature reports models; topology construction reads like a P&ID; each component carries exactly the parameters and correlation slots its hardware needs; easy to validate against a paper that models "a microchannel evaporator". Newcomers are productive immediately because the vocabulary is the domain's.
- **Disadvantages.** Risk of duplicated conservation logic across components that are internally similar (an evaporator and a heated pipe share a 1D fluid balance); risk of a fat hierarchy if every hardware variant becomes a subclass.

### Option B — Abstract distributed components
A small set of mathematical primitives; physical devices are configurations of them.

- **Advantages.** Conservation logic written once; in principle any device is a parameterised distributed element; elegant from a numerics standpoint.
- **Disadvantages.** The model no longer speaks the engineer's language — "configure a DistributedComponent with a boiling source term" is a translation barrier for every future researcher; validation against a specific paper's evaporator becomes indirect; the abstraction tends to leak (accumulators, pumps and junctions do not fit a 1D distributed mould and need escapes anyway); high risk of the over-engineering Principle 1.6 forbids.

### Recommendation — Physical components on top of a thin shared physics core
Adopt **Option A as the public, user-facing vocabulary**, and capture the genuinely shared mathematics (the 1D segmented fluid balance) as an **internal, non-public mechanism that physical components reuse by composition**, not as the interface users see.

Concretely:
- The world is built from **Pipe, Evaporator, Condenser, Pump, Accumulator, Valve, Splitter, Mixer, Reservoir**. This is what topology, validation, and results speak.
- The shared "1D finite-volume / segmented fluid passage with friction and an optional heat source" is real (Principle: don't duplicate), but it is a *building block the heated/transport components use internally*, not a primitive users assemble. Evaporator = that passage + a wall energy balance + boiling correlations; heated Pipe = that passage with zero source.
- Point-like elements (Pump, Valve, Splitter, Mixer, Accumulator, lumped Condenser) do **not** force themselves into the distributed mould; they are their own physical components with their own simple balances.

This gives the engineer's vocabulary and validation directness of Option A while avoiding the copy-paste that Option B was trying to cure — and it refuses the abstract-primitive interface that would cost every future user a translation step. The shared core is justified only because at least two components (evaporator, condenser, heated pipe) genuinely need it; that is the bar from Principle 1.6.

---

## 4. Fluid State Philosophy

### Candidate independent-variable pairs
- **P–T:** intuitive, excellent in single phase. **Fails on the saturation line:** inside the two-phase dome P and T are not independent, so (P,T) cannot resolve quality. Requires variable switching at phase boundaries — exactly the fragility Principle 1.5 forbids.
- **P–x:** natural inside the dome, undefined in single phase. Same switching problem, mirror image.
- **P–ρ:** continuous across phases and natural for compressible/dynamic mass storage; but ρ is a poor primary for energy bookkeeping and less directly tied to the energy balance the components write; near-incompressible liquid makes P–ρ ill-conditioned (huge dP for tiny dρ).
- **P–h (pressure–specific enthalpy):** continuous and single-valued across subcooled, saturated and superheated regions; the energy balance is *written in h*, so it is the variable the components naturally carry; quality, T, ρ, properties all derive cleanly from (P,h); robust at x→0 and x→1.

### Why P–h
- **Single-phase regions.** (P,h) fully determines the state; T and all properties follow from the backend.
- **Two-phase regions.** (P,h) is single-valued where (P,T) collapses; quality is `x = (h − h_f)/h_fg`, continuous through 0 and 1. No region-dependent variable switch — one representation spans the whole operating envelope.
- **Numerical robustness.** No discontinuity or branch at the saturation line; the same residual equations hold everywhere; this is precisely why the literature reports P–h (and the related P,h,ṁ state vector) as the consensus choice for two-phase loop simulation.
- **Compatibility with future dynamics.** The dynamic energy equation is naturally an enthalpy-storage equation (∂(ρh)/∂t …); carrying h now means the dynamic extension stores the variable it already uses. Density needed for mass storage is a *derived* property of (P,h), so moving to dynamics adds equations, not a new state representation.

### Recommendation
**Internal primary representation: (P, h) plus fluid identity.** All other properties (T, T_sat, x, ρ, μ, σ, k, c_p, phase) are **derived**, served by the Fluid State via the property backend. User-facing inputs may be given in friendlier terms (e.g. subcooling, superheat, T) but are converted to (P,h) immediately on entry, so the canonical internal state is uniform. The mass flow rate ṁ travels alongside (P,h) on ports but is a flow variable, not part of the thermodynamic state of a point.

---

## 5. Port Philosophy

### What a port carries
A port describes the fluid crossing a component boundary. The minimal, sufficient set is:

- **Pressure P** — needed for momentum closure and as the thermodynamic anchor.
- **Specific enthalpy h** — needed for energy closure and as the second thermodynamic anchor.
- **Mass flow rate ṁ** — the flow/transport variable; what is conserved at junctions.

These three are the *stored* (carried) port variables. They mirror the consensus interface (P, h, ṁ) and are sufficient to (a) define the thermodynamic state of the crossing fluid via Section 4 and (b) enforce all continuity and conservation conditions at connections.

### What is stored vs. derived
- **Stored on the port:** P, h, ṁ. Nothing else.
- **Derived on demand (never stored on the port):** temperature T, quality x, density ρ, void fraction, all transport properties. These follow from (P,h) through the Fluid State. Storing them on the port would create a second source of truth that can drift out of sync with (P,h) — a classic and silent bug. The port exposes them only by delegating to the Fluid State.

### Continuity at a connection
Connecting two ports asserts: equal pressure, equal enthalpy (for the fluid passing), and a mass-flow balance (ṁ out of one equals ṁ into the next; at junctions the algebraic sum is zero). Directionality (inlet/outlet) is a convenience for sequential steady-state assembly; the underlying continuity is non-directional, which keeps the door open for DAE-style simultaneous solution and for the dynamic phase. Ports therefore should support a non-directional notion of connection, with inlet/outlet as an annotation rather than a hard constraint.

---

## 6. Component Responsibilities

For each component: purpose, inputs, outputs, internal states, relation to geometry, relation to correlations, dynamic relevance. No code.

### Pump
- **Purpose.** Impart pressure rise; set the loop's flow.
- **Inputs.** Inlet (P,h); commanded speed ω or target ṁ.
- **Outputs.** Outlet (P,h); power.
- **Internal states.** None in steady state (efficiency is a parameter). Dynamic: shaft speed / fluid inertia of the loop.
- **Geometry.** Minimal — a reference for the performance map; displacement if positive-displacement.
- **Correlations.** Pump performance/efficiency map (ΔP vs flow at speed).
- **Dynamic relevance.** Low thermally, but it sets the mechanical time constant for flow excursions (Ledinegg-type). The inertia term is the dynamic seam.

### Pipe
- **Purpose.** Transport with frictional (and gravitational) pressure drop; optionally a heated/cooled passage.
- **Inputs.** Inlet (P,h,ṁ); optional wall heat.
- **Outputs.** Outlet (P,h).
- **Internal states.** None in steady state. Dynamic: distributed fluid mass/momentum (and wall temperature if heated).
- **Geometry.** Length, hydraulic diameter, area, roughness, elevation.
- **Correlations.** Single- and two-phase friction (Darcy–Weisbach/Haaland; Friedel / Müller-Steinhagen–Heck for two-phase); void fraction when needed.
- **Dynamic relevance.** Moderate — transport delay and fluid inertia influence stability.

### Evaporator
- **Purpose.** Add heat; produce vapour/quality; the loop's primary heat source.
- **Inputs.** Inlet (P,h,ṁ); heat load Q (or wall flux).
- **Outputs.** Outlet (P,h,x); wall temperature.
- **Internal states.** Steady: flow regime (algebraic). Dynamic: wall thermal capacitance, fluid inventory.
- **Geometry.** Channel count/dimensions, heated area, wall mass/material — central to both balances.
- **Correlations.** Boiling HTC (Shah, Gungor–Winterton, Kim–Mudawar); two-phase ΔP. The most correlation-sensitive component; replaceability here is the point.
- **Dynamic relevance.** Critical — wall capacitance governs temperature overshoot under pulsed loads; built on the shared 1D segmented passage so spatial resolution is available.

### Condenser
- **Purpose.** Reject heat; return subcooled liquid.
- **Inputs.** Two-phase inlet (P,h,ṁ); sink temperature and flow.
- **Outputs.** Outlet (P,h) (subcooling); heat rejected.
- **Internal states.** Steady: effective areas per zone. Dynamic: moving-boundary positions (two-phase/liquid interface).
- **Geometry.** Plate/area geometry, sink-side description.
- **Correlations.** Condensation HTC (Shah, Yan); ΔP; ε-NTU/LMTD as the heat-exchange method.
- **Dynamic relevance.** High — condenser flooding/expansion changes the liquid volume returned to the accumulator; the moving-boundary form is the dynamic seam.

### Accumulator
- **Purpose.** Set the loop reference pressure and absorb mass-inventory changes — the system "brain".
- **Inputs.** Steady: target/reference pressure P_set. Dynamic: net mass exchange with the loop; control input (heater power for HCA, gas pressure for PCA).
- **Outputs.** Reference pressure node; for dynamics, instantaneous system pressure.
- **Internal states.** Steady: liquid/gas split consistent with P_set. Dynamic: gas volume V_g, liquid volume V_l.
- **Geometry.** Total volume; gas charge (PCA); heater/thermal description (HCA).
- **Correlations.** Polytropic gas law (PCA); saturation relation under thermal control (HCA). Both expressed through one generic *volume↔pressure* law so PCA and HCA are interchangeable behind the same interface.
- **Dynamic relevance.** Highest — regulates pressure and absorbs transients; its stiffness and placement drive instability behaviour.

### Valve
- **Purpose.** Local pressure loss; tunable resistance for stability.
- **Inputs.** Inlet (P,h,ṁ); opening fraction.
- **Outputs.** Outlet P.
- **Internal states.** None (steady). Dynamic: position over time.
- **Geometry.** Reference area / Cv.
- **Correlations.** Loss coefficient K_L vs. opening.
- **Dynamic relevance.** High for stability — used to add stiffness to mitigate pressure-drop oscillations.

### Splitter
- **Purpose.** Divide flow into parallel branches.
- **Inputs.** Inlet (P,h,ṁ).
- **Outputs.** Per-branch (P,h,ṁ); branch split follows from equal pressure-drop closure across parallel branches.
- **Internal states.** None (negligible storage).
- **Geometry.** Minimal.
- **Correlations.** None intrinsic; branch resistances come from the branches themselves.
- **Dynamic relevance.** Low — enforces conservation/convergence between branches.

### Mixer
- **Purpose.** Recombine branch flows.
- **Inputs.** Per-branch (P,h,ṁ).
- **Outputs.** Combined (P,h,ṁ) by mass and energy balance.
- **Internal states.** None.
- **Geometry.** Minimal.
- **Correlations.** None intrinsic.
- **Dynamic relevance.** Low — conservation node.

### Reservoir (where distinct from accumulator)
- **Purpose.** Hold liquid inventory; guarantee pump suction (NPSH).
- **Inputs/Outputs.** Liquid in/out; level.
- **Internal states.** Steady: inventory consistent with total charge. Dynamic: liquid level/interface.
- **Geometry.** Volume.
- **Dynamic relevance.** Moderate — ensures NPSH during transients.

---

## 7. Solver Philosophy

### Global vs. local
- **Local (in the component).** Each component computes its own contribution from the state at its ports and its internal states: its residual equations (steady) and its internal-state derivatives (dynamic). It never reaches outside itself.
- **Global (in the solver).** The unknowns are the port variables (P, h, ṁ) across the network plus components' internal states. The solver assembles all component contributions and all network continuity/closure conditions into one system and drives it to satisfaction. **Loop closure is a global condition, not a component's job.**

This split is the embodiment of Principle 1.3: components express physics, the solver expresses numerics, and neither knows the other's internals.

### Network closure strategy
- The loop must **close on pressure**: the sum of pressure changes around any closed path is zero, equivalently the pump head matches total loop resistance at the operating point.
- Exactly one **pressure reference** is set by the accumulator; the topology validator enforces "exactly one reference".
- **Mass continuity** holds at every junction; **energy continuity** holds at every connection.
- Two acceptable steady-state strategies, both compatible with this architecture: (a) **fixed-point pressure iteration** — assume reference pressure / branch splits, march the states, correct until the loop residual vanishes; (b) **simultaneous Newton–Raphson** on the full residual vector. Start with the more robust fixed-point/sequential approach for single loops; allow the simultaneous approach as a drop-in alternative because the component contract (residuals, not solving) supports both with zero component changes.

### Parallel branches
Parallel branches are closed by the condition that **all branches between a common splitter and mixer share the same pressure drop**, with the branch mass flows summing to the trunk flow. This is a network-level set of equations the solver owns; the splitter/mixer only supply conservation, the branches only supply their resistances. Adding a branch is a topology edit, never a solver edit.

### Future extension toward dynamic simulation
The same local/global split carries directly into dynamics:
- Components already separate *algebraic closure* (HTC, ΔP, void) from *state evolution*. In steady state the time derivatives are set to zero; in dynamics the solver integrates them.
- The dynamic solver is a **new solver behind the same component contract**: it asks each component for d(internal state)/dt instead of for an algebraic residual, and integrates (explicit RK for non-stiff, implicit for stiff). Components do not change.
- This is why steady-state-first does not paint us into a corner — see Section 10.

---

## 8. Correlation Strategy

### Families
- **Heat-transfer coefficient (HTC):** boiling (Shah, Gungor–Winterton, Kim–Mudawar), condensation (Shah, Yan).
- **Pressure-drop:** single-phase friction (Colebrook/Haaland); two-phase (Friedel, Müller-Steinhagen–Heck, Kim–Mudawar, McAdams).
- **Void fraction:** homogeneous and slip models.
- **Property model:** treated as a correlation family too — CoolProp/REFPROP as the truth, with an optional tabulated surrogate for speed.

### Integration without coupling to components
- A correlation is a **named, swappable closure** that takes a Fluid State plus the geometric/flow quantities it needs and returns one physical number. It does not know which component called it.
- A component **holds slots** ("a boiling-HTC correlation", "a two-phase-ΔP correlation") and calls them at the point its balance needs a closure. The component knows it needs an HTC; it does not know whether that HTC is Shah or Kim–Mudawar.
- Selecting or replacing a correlation is a **configuration choice**, recorded in the reproducibility tuple (Principle 1.7), not a code change. This is the literature's "correlation manager / strategy" recommendation, kept deliberately lightweight: a registry of named correlations, not a heavyweight factory framework (Principle 1.6).
- Each correlation **declares its validity envelope**; the framework warns (not silently extrapolates) when used outside it — a transparency requirement, not a correctness guarantee.

### Where calibration meets correlations
Calibration (Section 9) applies at the **seam between a correlation's raw output and its use in the balance** — a single multiplier on ΔP or α. This keeps correlations pure (they return physics) and makes every correction explicit and located in one place.

---

## 9. Calibration Strategy

### Requirements
The framework must let researchers reconcile models with experiment **transparently**: every correction is named, defaulted to neutral, and reported alongside results. No hidden empirical factors (an explicit acceptance criterion in the validation plan).

### What gets calibrated
- **Pressure drop:** a multiplier R\* on the frictional component, per the validation plan's
  `ΔP_total = R*·ΔP_friction + ΔP_gravity + ΔP_acceleration`.
  Gravity and acceleration terms are physics and are **not** scaled; only the empirical friction term is.
- **Heat transfer:** an analogous multiplier on the HTC (or on UA), applied at the same kind of seam.

### Explicit parameters, transparency, reproducibility
- Calibration factors are first-class, named inputs with default = 1 (neutral). They live in the reproducibility tuple and are emitted in every result.
- They apply at one documented seam (Section 8), so a reader can always see exactly what was scaled and by how much.

### Evaluation of the proposed `none` / `target` philosophy
- **`none`** — all factors = 1; pure predictive physics. Essential as the honest baseline and the default. Correct and sufficient for what it is.
- **`target`** — factors chosen so the model meets a specified experimental target (e.g. measured loop ΔP). Useful and legitimate *provided* the target, the resulting factor, and the seam are all reported.

**Is `none`/`target` sufficient?** For the steady-state scope (Phases 1–4) and for honest single-point reconciliation, **yes** — it is the minimum that satisfies transparency and reproducibility, and it should be implemented exactly as proposed. But it has two foreseeable gaps to acknowledge now (not necessarily build now):

1. **Granularity.** A single mode for the whole loop is coarse. Calibration is physically *per-component* (the evaporator's friction may need a different factor than a pipe's). The architecture should allow a calibration factor to attach **per component / per correlation**, with `none`/`target` as the global default behaviour. This is a scoping choice, not new machinery — the seam already exists per correlation.
2. **Fitting vs. setting.** `target` as a *single* factor that hits *one* target is fine. Calibrating against a **dataset** (least-squares over many points) is a different activity — that is surrogate/identification territory (Phase 5), and it should reuse the same explicit-factor seam rather than introducing a parallel hidden mechanism.

**Recommendation:** adopt `none`/`target` as specified for v1, with the factor seam designed to be addressable per-component so the granularity extension later is configuration, not redesign. Keep dataset-fitting out of the calibration concept and route it through the (later) identification tooling, writing its results back as ordinary explicit factors.

---

## 10. Dynamic Extension Strategy

The first version is steady-state (Phases 1–4); dynamics arrive in Phase 6. The architecture must absorb that without redesign. The following design choices, all made *now*, are what make it possible:

1. **State representation already dynamic-ready.** Choosing (P,h) as the primary variables (Section 4) means the variable the dynamic energy equation stores is the variable already carried. Density for mass storage is derived, so dynamics adds equations, not a new representation.

2. **Internal states declared even when frozen.** Components that *will* store mass/energy dynamically (evaporator wall, accumulator gas volume, condenser boundaries, pipe inventory) **name those internal states from day one**, even though steady state holds their derivatives at zero. The dynamic step then "unfreezes" derivatives; it does not invent new state.

3. **Components contribute derivatives, not solutions.** The component contract is "given the state, return your residual *and/or* your d(state)/dt" — never "solve yourself". Steady-state uses the residual with derivatives = 0; dynamics asks for the derivatives and integrates. Same contract, different solver.

4. **Solver behind a stable interface.** The dynamic solver is an *additional* solver, not a modification of the existing one. Because closure and continuity are network-level conditions and physics is local, swapping the steady solver for an integrator touches neither components nor network description (Section 7).

5. **Non-directional ports.** Keeping continuity non-directional (Section 5) means the simultaneous/DAE formulation dynamics needs is already expressible; we are not locked into a one-way sequential assembly.

6. **Accumulator as a real component.** Because the accumulator is a first-class component that already owns gas/liquid volumes and sets the pressure reference, the single most important dynamic element (the "brain") needs only its derivative law activated, not a structural change.

What we explicitly **do not** do now: build the integrator, write moving-boundary equations, or add wall-conduction networks. We only ensure the *seams* exist (state names, derivative contract, solver interface) so those are additions, not surgery. This is Principle 1.6 applied to the future: prepare the seam, defer the mechanism.

---

## 11. Risks and Failure Modes

Architectural mistakes most likely to make this project hard to maintain over five years, and the guard already built into the design:

1. **Two sources of truth for fluid properties.** Storing T or ρ on ports/components beside (P,h) lets them drift apart silently. *Guard:* properties are always derived from the canonical (P,h) Fluid State; ports store only P,h,ṁ (Sections 4–5).

2. **Solver–physics entanglement.** If a component "knows" it is being Newton-iterated, or hard-codes a time step, no new solver can be added. *Guard:* the component contract is residual/derivative only; the solver is the sole owner of numerics (Sections 2.8, 7).

3. **Correlations welded into components.** Hard-coded Shah inside the evaporator kills the very replaceability that is the project's research value. *Guard:* correlations are named, swappable closures held in component slots (Section 8).

4. **Over-abstraction / speculative generality.** A plugin system, an event bus, a deep abstract hierarchy, or the abstract-primitive component model (Section 3B) would impose a permanent translation tax on every future researcher and a maintenance burden with no physical payoff. *Guard:* Principle 1.6 — abstraction only when two concrete cases demand it; physical-component vocabulary kept public.

5. **Hidden calibration.** Any un-reported correction factor makes old results untrustworthy and is explicitly forbidden by the validation plan. *Guard:* calibration is named, neutral-by-default, single-seam, and always reported (Section 9).

6. **Topology assumptions baked into the solver.** Assuming "one loop, no parallel branches" anywhere in the solver makes multi-evaporator support a rewrite. *Guard:* parallel-branch closure is a network-level condition; adding a branch is a topology edit (Section 7).

7. **Retrofitting dynamics.** If internal states and the derivative contract are not present from the start, Phase 6 becomes a redesign. *Guard:* internal states named now, derivatives frozen not absent (Section 10).

8. **Irreproducible runs.** Results depending on call order, mutable globals, or un-versioned defaults cannot anchor a surrogate dataset. *Guard:* the reproducibility tuple fully determines a run (Principle 1.7).

9. **Property-backend lock-in / cost.** Tying physics directly to one library (or paying its call cost in every inner loop) hurts both portability and the thousands-of-runs Phase 5. *Guard:* property model is itself a swappable family with an optional tabulated surrogate behind the Fluid State (Section 8).

10. **Validation as an afterthought.** Bolting balance checks on later means they are skipped under deadline. *Guard:* energy/mass/pressure-closure residuals and physical-bound checks are first-class solver outputs (Principle 1.4).

---

## 12. Recommended Architecture

The framework is **a Network of physical Components connected through Ports, whose canonical fluid description is a (P,h) Fluid State, closed by a Solver that is fully decoupled from the physics, with empirical closures supplied as swappable Correlations and every correction made explicit through Calibration.**

In one paragraph per relationship:

- **Components are physical and speak the engineer's language** — Pump, Pipe, Evaporator, Condenser, Accumulator, Valve, Splitter, Mixer, Reservoir. Internally, the heated/transport components reuse one shared 1D segmented-passage mechanism by composition; point-like components keep their own simple balances. No abstract-primitive interface is imposed on users.

- **Ports carry exactly (P, h, ṁ)** and nothing derived; connections assert equal pressure, equal enthalpy, and mass balance, non-directionally.

- **Fluid State is (P, h) + fluid identity**, the single source of truth, with every other property derived through a swappable property backend. This is what makes the single-phase ↔ two-phase transition continuous and what makes dynamics a future addition rather than a rewrite.

- **Correlations are named, swappable closures** held in component slots; replacing one is configuration, not code. Each declares its validity envelope.

- **Calibration is explicit, neutral-by-default, single-seam, always reported.** `none`/`target` is adopted for v1, with the factor seam addressable per-component so finer calibration is later configuration, not redesign.

- **The Network owns topology and the closure/continuity conditions** (loop closes on pressure; one accumulator-set reference; parallel branches share ΔP); it states what must hold without solving it.

- **The Solver owns all numerics.** Steady state first (fixed-point pressure iteration, then optionally simultaneous Newton); dynamics later as an additional solver behind the identical component contract — components contribute residuals and/or derivatives, never solutions.

- **Validation and reproducibility are structural,** not optional: invariant residuals are first-class outputs, and a run is fully determined by topology + parameters + fluid + correlation choices + calibration + solver settings.

This architecture is deliberately small. It introduces eight concepts and one shared internal mechanism, and no more. It earns its modularity at exactly the seams where research happens — the model replaceability of Principle 1.2 — and refuses it everywhere else. It is designed today, in steady state, so that the dynamic, control-oriented and surrogate phases on the roadmap are *additions along prepared seams*, not redesigns. That is the property that lets it stay useful for the next 5–10 years.
