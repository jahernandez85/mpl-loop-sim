# Decision 001

Date: 2026-06-10

Topic:
Thermodynamic state variables

Decision:
Use P-h as internal thermodynamic representation.

Reason:
Compatible with single-phase and two-phase regions without changing state variables.

Alternatives considered:
- P-T
- P-x

Status:
Accepted

# Decision 002

Decision under review:

Should mdot be stored in Port
or in FlowState?

Current decision:
Port carries mdot.

# Decision 003

# Decision — Property backend architecture

The library must support multiple property sources, including CoolProp, REFPROP and tabulated property data from legacy files.

The FluidState object must not depend directly on CoolProp.

Instead, FluidState queries a PropertyBackend interface.

Rationale:
Some candidate fluids or mixtures may not be fully available in CoolProp, while validated tabulated data may exist in legacy implementations.

Status:
Accepted for architecture review.

---

# Decision 004

Date: 2026-06-10

Topic:
Port and SystemState ownership of primary unknowns

Decision:
Port is pure connectivity. It carries identity, owning component, role annotation, and the connected peer. It is immutable after Network assembly and stores no values.

The primary unknowns — P, h, and ṁ for each port-node, and all named component internal states — live in a solver-owned SystemState: a flat, ordered, indexable container. Port-variable handles map a port to its slots in that vector.

FluidState is transient. It is constructed from (P, h) plus identity on demand for property evaluation and is never stored or cached on a port or component.

The names PortState and FlowState are retired as storage objects. Decision 002 is closed: ṁ is associated with a port for connectivity purposes, but stored in the SystemState like every other unknown.

Rationale:
Storing primary unknowns on Port objects couples the solver to a topology walk on every residual evaluation and prevents the solver from holding multiple simultaneous state copies (trial, derivative, history, integrator stages). With a solver-owned state vector, finite-difference Jacobian columns reduce to a copy-and-bump operation, simultaneous Newton assembly is native, and the ordered introspectable state vector is the same object a linearisation or MPC/ROM seam needs. Legacy projects that stored state on port objects are identified in the architecture audit as the primary source of silent divergence and dual-source-of-truth bugs.

Consequences:
- Closes Decision 002.
- Amends the L2 §2.1 statement "Port stores the value as a solver unknown" — that statement is superseded by this decision.
- Simultaneous Newton and future dynamic integrators inherit a natural home for their unknown vector.
- Port objects become safe to share by reference across components; no mutation hazard after assembly.
- A handle or index abstraction is required at Network assembly time to map each port to its SystemState slots.

Status:
Accepted

---

# Decision 005

Date: 2026-06-10

Topic:
Correlation call signature — role-typed CorrelationInput objects

Decision:
Correlations are called with a role-typed CorrelationInput value object, not with positional scalars.

The full contract is: evaluate(CorrelationInput) → (value, ValidityVerdict).

There is one input type per correlation role, not one per formula. Roles are the set already enumerated in the architecture (e.g. SinglePhaseDPInput, TwoPhaseDPInput, HTCInput, VoidFractionInput, VolumePressureLawInput). All correlations in the same role — regardless of their formula — receive the same input type.

The Component builds the input from its FluidState(s) and the scalars it forwards from its Geometry. The correlation sees only data; it remains ignorant of component and geometry types.

CorrelationInput objects are immutable and AD-traceable structs. ValidityVerdict is the existing structured return type.

Rationale:
Positional scalar signatures degrade in readability past three arguments, are order-fragile, cause signature churn when inputs are added, and are the exact pattern the legacy PyP2PL correlation layer exhibited before breaking. A role-typed input is a written manifest of precisely what a correlation family is allowed to see, which supports scientific review, extensibility to ML/surrogate closures, and future automatic differentiation without special-casing.

Consequences:
- A small, bounded set of input value types is required — one per role. The role set is fixed by the architecture and does not grow with the correlation catalogue.
- The Component is the only layer that constructs CorrelationInput; this makes the information flow reviewable and keeps correlations decoupled from component structure.
- An ML or surrogate closure obeys the identical contract; the input object doubles as its feature vector.
- Supersedes the positional reading of L3 §3.1 and §7 without contradicting their intent.

Status:
Accepted

---

# Decision 006

Date: 2026-06-10

Topic:
FluidState definition and PropertyBackend interface

Decision:
FluidState is a pure value object: (P, h, identity). No derived property is ever stored on it. Every derived quantity — T, T_sat, x, ρ, μ, k, σ, c_p, phase, h_f, h_g, h_fg — is obtained by querying a PropertyBackend.

Fluid identity is a mixture-capable value object, able to express a single fluid, a mixture with composition, or a custom fluid handle. A bare string is insufficient.

Property access is vector-first. The PropertyBackend interface accepts arrays of (P, h); a scalar query is the length-1 case. This is required from the first interface definition.

The PropertyBackend interface must provide:
1. Vector-first property queries: query(prop, P[], h[], identity) → value[].
2. The full derived property set FluidState exposes.
3. Optional first derivatives (∂ρ/∂P|h, ∂ρ/∂h|P, ∂T/∂…) exposed behind a capability flag.
4. Capability flags (e.g. provides(σ_e), provides(derivatives), valid_range(identity)).
5. No extrapolation by stealth — out-of-range queries return unavailable or NaN with a warning, never a fabricated value.

One backend instance is shared per fluid identity per run. The backend is long-lived, constructed from the Reproducibility Tuple, and may maintain an internal cache because it is a pure function of (P, h, identity). Backend selection is a (fluid identity → backend name) binding in the tuple. A separate backend registry — keyed by name, distinct from the correlation registry — maps backend names to constructors.

Rationale:
Storing derived properties on FluidState is the canonical drift bug documented in every legacy project. Vector-first access sets the performance ceiling for Phase-5 batch evaluations and finite-difference Jacobian columns and must be in the interface from day one to avoid a later redesign. Optional derivative provision keeps the analytic-Jacobian and dynamic compressibility paths open without requiring all backends to implement them. The capability-flag mechanism is needed because electrical conductivity and relative permittivity exist only in the legacy tabulated backend; silent fallback to a wrong value is worse than an explicit unavailable.

Consequences:
- Decision 003 (principle) is superseded by this decision, which specifies the full interface contract.
- FluidState is trivially serialisable as (P, h, identity) and trivially vectorisable for batch solves.
- Concrete backend implementations expected: CoolPropBackend (default), RefpropBackend, TabulatedPropertyBackend (CSV recovery), EmpiricalCorrelationBackend (Letsou-Stiel and related), and future MixtureBackend/CustomFluidBackend.
- Backend caching, thread-safety for parallel DOE, and vectorisation internals are implementation details deferred to Category B.

Status:
Accepted

---

# Decision 007

Date: 2026-06-10

Topic:
Geometry, Discretization boundaries, and 1D-passage pressure-gradient philosophy

Decision:
Geometry is immutable physical scalars. The gravity magnitude and vector are a Scenario input with a default of 1 g terrestrial. Elevation change Δz and orientation are Geometry. The gravitational acceleration term ρ g Δz/dx is therefore computed from a Geometry scalar and a Scenario input — not from a stored state.

Geometry may expose derived dimensional accessors (e.g. D_h computed from stored primitive dimensions). Geometry must never compute a correlation output such as Nu or ΔP.

Discretization is a small declared object {mode ∈ Lumped | Segmented | MovingBoundary, resolution parameters}, owned by the component's numeric configuration, derived from but never stored in Geometry. For MovingBoundary components the state count is queryable per step and is not frozen at Network assembly time.

All 1D passages — Pipe, and by composition Evaporator and Condenser segments — compute pressure gradients per control volume. The three contributions are: (dP/dx)_friction from the slot correlation, (dP/dx)_gravity = ρ g dz/dx from Geometry and Scenario, and (dP/dx)_acceleration = d(G²v)/dx. Total ΔP across a component is a derived output, the integral over the discretization cells. Lumped mode is the one-cell case of the identical kernel.

The calibration multiplier R* is applied to the friction gradient only. Gravity and acceleration are never calibrated.

Rationale:
Gravity as a Scenario input with Δz in Geometry means a zero-g or variable-g study (relevant for spacecraft MPLs) is a Scenario sweep, not a geometry rebuild. Gradient-based 1D-passage computation is the form used in every dynamic reference in the literature. It makes lumped, segmented, and dynamic modes share one physics kernel rather than diverging into separate code paths. The legacy MPL_Simulator gradient code is corroborating evidence. Deferring MovingBoundary state-count freezing prevents a structural retrofit when zone count changes during a dynamic simulation.

Consequences:
- Total ΔP is never a first-class computed quantity; it is always the integral of cell gradients.
- The 1D-passage mechanism is internal to the component, not a public primitive.
- Event detection (zone appearance and disappearance) in MovingBoundary mode is declared now as a first-class dynamic-solver concern, with implementation deferred to Phase 6.
- Fluid inertia for the loop momentum equation (dṁ/dt = (ΔP_pump − ΔP_loop) / I, I = L/A) is derivable from Geometry; no new state is required, but Pipe and Pump geometry must expose L and A.

Status:
Accepted

---

# Decision 008

Date: 2026-06-10

Topic:
Component internal state membership

Decision:
A quantity is component internal state if and only if the component stores it and will provide its time-derivative in dynamic mode.

Quantities that a component can recompute from port unknowns, Geometry, and correlations are not state.

Component internal state includes: wall temperatures (per cell), fluid mass per cell (the ∂ρ/∂t storage term), vapor and liquid inventories where tracked separately, gas volume V_g in the accumulator, moving-boundary interface positions in the condenser, and actuator states such as valve position and pump shaft speed (frozen in v1).

The following are never component state: port pressure P, port enthalpy h, port mass flow ṁ (all are SystemState unknowns per Decision 004), derived properties T, x, ρ (computed by FluidState), and correlation outputs such as HTC and ΔP (recomputed each evaluation).

The accumulator owns the volume-pressure law. Its stored state is V_g. System pressure P_sys is a SystemState unknown constrained by the accumulator's law; in dynamics the accumulator derives dP/dt from dV_g/dt. The accumulator does not own P_sys as a stored field.

Rationale:
Caching correlation outputs (_last_dP, _last_Q) is identified in the legacy audit as a repeated source of stale-result bugs. The accumulator's role as the pressure-setting component creates a temptation to store P_sys on it, but doing so would violate single-source-of-truth ownership (Decision 001 consequence) and make the dynamic DAE index ambiguous. Storing V_g and deriving P preserves the single-source-of-truth rule even for the component whose function is to anchor the loop pressure.

Consequences:
- The steady-state solver freezes internal-state derivatives at zero; no new solver mechanism is needed.
- In dynamics, each component exposes its state names, count, and time-derivative residual. The SystemState (Decision 004) is extended to include named internal states alongside port unknowns.
- State count for MovingBoundary components is per-step (Decision 007), requiring the dynamic solver to handle variable state-count components.

Status:
Accepted

---

# Decision 009

Date: 2026-06-10

Topic:
Sensitivity and Linearisation seam

Decision:
Structured finite differences are the primary sensitivity mechanism. Analytic property derivatives are used where the PropertyBackend provides them (Decision 006, capability flag). Automatic differentiation through the property layer is not promised; CoolProp and REFPROP are compiled external libraries for which AD is generally unavailable. The architecture keeps the AD seam open but does not build on it.

Property derivatives at the saturation boundary are discontinuous in slope even though properties themselves are continuous in (P, h). Smoothed or regularised property derivatives near saturation are the recommended technique for gradient-based control and optimisation applications.

A single Sensitivity/Linearisation seam is declared. This seam unifies three uses that require the same underlying machinery: the Newton Jacobian, the dynamic implicit-integration Jacobian, and the linearised state-space (A, B, C, D) extraction for MPC/ROM/surrogate work. The contract is: given the assembled system and a SystemState operating point, perturb the SystemState and Scenario inputs, re-evaluate residuals and outputs, and assemble sensitivities. The ordered, introspectable SystemState (Decision 004) is the precondition that makes this seam stable and enumerable. The Scenario provides the input vector; the Result quantities provide the output vector.

Rationale:
All three uses of sensitivity information — Newton solve, implicit dynamic integration, and linearisation for MPC/ROM — require iterating over the same ordered state vector and re-evaluating the same residual assembly. Declaring them as one seam now prevents three divergent implementations from accumulating. The FD-primary stance is honest about what the property layer can deliver; committing to AD in ARCHITECTURE_MASTER.md when CoolProp cannot support it would create a latent design trap. The (P, h) representation buys continuity across the saturation dome, not smoothness of derivatives.

Consequences:
- ARCHITECTURE_MASTER.md must not state that AD is a promised path. It may note that AD is aspirational if framework-side arithmetic is made traceable in the future.
- The Sensitivity/Linearisation seam is declared as an interface now; its implementation is deferred (Category B) and is not required for v1 steady-state operation.
- The simultaneous/DAE assembler required for Newton (Decision 004 consequence) is also the assembler the dynamic solver and the linearisation seam inherit — one shared residual assembly, not three.
- The steady-state solution is the consistent initial condition for the dynamic DAE; this requires the steady and dynamic solvers to share one residual assembly.

Status:
Accepted