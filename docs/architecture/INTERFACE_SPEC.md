# INTERFACE_SPEC.md

**The architecture-level interface and contract specification for the MPL simulation framework.**

Status: **interface specification (pre-implementation).** This document is the direct reference that future Python code must implement. It is downstream of, and subordinate to, `ARCHITECTURE_MASTER.md`; where this document refines a master concept, it does so by *specifying a contract*, never by reopening a frozen decision (`[F1]`–`[F18]`).

Companion documents (per MASTER §18): `SCHEMA_SPEC.md` (serialization bytes + version fields), `CORRELATION_CONTRACT.md` (validity-envelope format), `TEST_PLAN_V1.md` (validation-level mapping). This document is the highest-priority of the four.

Refinement notes integrated in this revision (see §17 for the amendments they imply for the master):
- **Pipe trajectory** is generalized beyond a single `Δz` without over-generalizing v1 (§5).
- **Accumulator** is specified as a *pressure-reference component* with geometry and pressure law strictly separated, extensible across PCA/HCA/bellows/spring/gas-charged (§5, §8, §11).
- **Heat-exchanger modelling** is lifted out of the correlation slot set into a distinct `HeatExchangerModel` strategy concept (§8).
- **Scenario** is decomposed into boundary conditions, commands, disturbances, environment, and operating point (§10).

---

# 1. Scope and Status

This document **specifies interfaces, not implementation.**

- It defines the **contracts** (method signatures as pseudo-signatures, input/output value shapes, invariants, and ownership) that future Python classes must satisfy.
- It contains **no executable Python, no class bodies, no algorithms.** Pseudo-signatures use a language-neutral notation (§1.2) precisely so that they are read as contracts, not code.
- It is **precise enough that implementation can proceed without reopening any architecture decision.** Where a degree of freedom is deliberately left open (e.g. caching strategy, solver internals), the document says so explicitly and names the layer that owns the choice.

A reviewer must be able to reject a non-conforming implementation by citing a contract in this document. An implementer must be able to write a conforming class from the relevant section alone.

## 1.1 Relationship to the frozen architecture

Every interface here is traceable to a master section and a frozen tag. The five **frozen interfaces** of MASTER §18 are the spine of this document:

| Frozen interface (MASTER §18) | Specified here in |
|---|---|
| Dependency DAG + forbidden directions | §2 |
| Stored-vs-derived ownership boundary | §3, §4 |
| Component contribution contract | §11 |
| Port interface (connectivity only) | §4 |
| Reproducibility Tuple schema | §15 |

A change to any signature marked **FROZEN** in this document is a redesign, not an edit, and must go through `DECISION_LOG.md`.

## 1.2 Pseudo-signature notation

```
Name { field: Type, ... }                 a value object (immutable unless stated)
interface Name { op(args) -> Return }      a behavioural contract
op(a: T, b: U) -> R                        an operation signature
T[]                                        a vector/array of T (vector-first is the default, not the exception)
T?                                         optional / may be absent (never silently defaulted)
A | B | C                                  a closed enumeration (sum type)
<<FROZEN>>                                 signature may not change without a DECISION_LOG entry
<<SEAM>>                                   declared now, implemented in a later phase; shape is fixed
```

Types named in `CamelCase` are framework concepts. Quantities use their physical names (`P`, `h`, `mdot`, `T`, `x`, …). All numeric quantities are SI unless a unit is named in `SCHEMA_SPEC.md`.

---

# 2. Interface Design Rules

These rules bind every interface in this document. They are the operational form of MASTER §1 (principles), §3 (dependencies), and §4 (ownership).

1. **No forbidden dependency directions.** Every interface is placed on exactly one DAG layer (MASTER §3) and may name only types at or below it per its dependency row. Specifically: nothing that expresses physics may reference numerics; **nothing anywhere may reference the Solver.** Forbidden directions must, wherever the type system allows, be made *unrepresentable* — a `Correlation` is never handed a `Component`; a `Component` is never handed a `Network`. Where the language cannot enforce it, the prohibition is a documented review gate.

2. **No hidden state.** An interface holds only the state its contract names. No instance caches a result between calls (`_last_dP`, `_last_Q` are forbidden). No module-level mutable state, no run-on-import behaviour, no global registries mutated after startup. A backend's *internal* property cache is permitted **only** because it is a pure function of `(P, h, identity)` and is invisible to every caller.

3. **No stored derived properties.** The only stored numbers in the framework are `P, h, mdot` per port-node and the named component internal states, all in `SystemState` (`[F3]`). `T, x, ρ, μ, k, σ, c_p, void, phase, T_sat, h_f, h_g, h_fg`, and all closure outputs (HTC, ΔP, ε) are **derived on demand, never stored on any object.** An interface that exposes a derived quantity computes it per call from `(P, h, identity)` through a backend.

4. **Configuration, not code, for swappable models.** Selecting a correlation, a property backend, a heat-exchanger model, an accumulator pressure law, a discretization mode, or a solver is a **named binding in the Reproducibility Tuple** (§15), resolved through a registry. Swapping any of them is a tuple edit. No `if model == "shah"` branch may exist in a component; no model choice may be hard-coded in a constructor.

5. **Validation-first outputs.** Every operation that produces a physical result also produces, as a first-class part of its return, the means to check it: a `ValidityVerdict` for a correlation, invariant residuals for a solve, a calibration report for a result. *A result without a residual is not a result.* No interface may return a bare number where the contract names a verdict-bearing return.

6. **Vector-first.** Property and closure query interfaces accept and return arrays; the scalar case is length-1. This is mandatory from the first definition (`[F13]`) so the Phase-5 batch and finite-difference Jacobian paths are not a later redesign.

7. **Immutability by default.** Value objects (`FluidState`, all `Geometry`, all `CorrelationInput`, `Scenario` and its parts, the Reproducibility Tuple) are immutable. Variation produces a *new* object, hence a *new* tuple — the unit a DOE iterates over (`[F8]`). Only `SystemState` is mutable, and only the Solver mutates it.

---

# 3. Core Data Interfaces

Layer 0–1 of the DAG. These are the inert-data and state primitives every physics interface reads from.

## 3.1 FluidIdentity

A **mixture-capable value object** naming *which fluid* a state describes (`[F12]`). A bare string is insufficient — identity must express a pure fluid, a defined mixture, or a custom-fluid handle so a `MixtureBackend`/`CustomFluidBackend` can be selected without changing `FluidState`.

```
FluidIdentity = PureFluid | Mixture | CustomFluid                       <<FROZEN>>

PureFluid   { name: str }                                  e.g. "R134a", "Acetone"
Mixture     { components: (str, mole_fraction)[], model: str? }
CustomFluid { handle: str }                                opaque key into a custom backend
```

- **Stored data:** only the discriminated union above. No properties, no backend reference.
- **Derived data:** none. Identity computes nothing.
- **Lifecycle:** immutable value; created once per fluid in a run, embedded in the tuple, compared by value.
- **Equality:** structural. `PureFluid("R134a") == PureFluid("R134a")`. This is the key the backend registry resolves a backend instance against (§3.4).
- **Capability:** identity carries no capability flags itself; capabilities are a property of the *backend* selected for it (§3.3).

## 3.2 FluidState

A **pure value object `(P, h, identity)`** (`[F2] [F12]`, MASTER §5). The single source of truth for every derived thermodynamic property — none of which it stores.

```
FluidState { P: float, h: float, identity: FluidIdentity }              <<FROZEN>>
```

- **Stored data:** exactly `P`, `h`, `identity`. Three fields. Nothing else, ever.
- **Derived data (computed on demand, never stored):** `T, T_sat, x, ρ, μ, k, σ, c_p, phase, h_f, h_g, h_fg`, optional first derivatives, and any electrical/dielectric property (`σ_e`, `ε_r`) a backend exposes.
- **Derivation requires a backend supplied by context, not embedded.** `FluidState` does **not** hold a `PropertyBackend` reference — that would make every state heavy and break cheap vectorization/serialization. Derived access is one of:
  - **vector-first query through context:** the inner loop and correlations receive a pure `FluidState[]` plus a backend handed in by the caller (§3.3); or
  - **an optional thin ergonomic wrapper** (`state.T`) for *user/analysis code only*, which closes over a backend. This wrapper is explicitly not for the solver inner loop.
- **Lifecycle:** ephemeral. Constructed transiently from `(P, h, identity)` when a property is needed, then discarded. **Never cached on a Port or Component** (anti-pattern §16).
- **mdot is not here.** A `FluidState` is two numbers + identity. `mdot` is a flow unknown in `SystemState` (it becomes a momentum state in dynamics).

## 3.3 PropertyBackend

The **swappable property engine** and the only thing `FluidState` derivation depends on (`[F6] [F13]`, MASTER §6). A **Layer-1 citizen, distinct from Layer-3 closure Correlations** — it reads neither geometry nor topology and lives in its own registry (§3.4), which is what breaks the only latent DAG cycle.

```
interface PropertyBackend {                                             <<FROZEN>>

  # 1. Vector-first property query. Scalar is the length-1 case.
  query(prop: PropertyName, P: float[], h: float[], identity: FluidIdentity)
        -> PropertyResult

  # 2. Optional first derivatives, behind capability flag `provides(DERIVATIVES)`.
  query_derivative(dprop: DerivativeName, P: float[], h: float[], identity: FluidIdentity)
        -> PropertyResult                                               # e.g. ∂ρ/∂P|h, ∂ρ/∂h|P

  # 3. Capability introspection. No silent guessing.
  provides(cap: Capability) -> bool
  valid_range(identity: FluidIdentity) -> RangeEnvelope
}

PropertyName   = T | T_sat | x | rho | mu | k | sigma | c_p | phase
               | h_f | h_g | h_fg | sigma_e | eps_r | ...              # closed, versioned set
Capability     = SIGMA_E | EPS_R | DERIVATIVES | <named property>
PropertyResult { value: float[], status: (OK | UNAVAILABLE | OUT_OF_RANGE)[], warning: str? }
```

- **The full derived property set** FluidState exposes must be answerable (those the backend supports).
- **No extrapolation by stealth** (`[F13]`-5): an out-of-range or unsupported query returns `UNAVAILABLE`/`OUT_OF_RANGE` with a warning and `NaN`, never a fabricated value. This is why `query` returns a status-bearing `PropertyResult`, not a bare `float[]`.
- **Capability flags** are mandatory: a caller asks `provides(SIGMA_E)` before relying on a table-only property. `σ_e`/`ε_r` exist only in the tabulated backend.
- **Mixture/custom-fluid support:** a new fluid or mixture is a **new backend behind this same interface** — extensibility identical in shape to "a new accumulator law is a new closure." `MixtureBackend`/`CustomFluidBackend` add nothing to the signature.
- **Lifecycle & ownership:** **one instance per fluid identity, owned by the run**, shared by reference across all FluidStates of that identity. Stateless with respect to the solve; an internal cache is allowed (pure function of `(P,h,identity)`). No import-time construction, no global mutable state.
- **Expected implementations:** `CoolPropBackend` (default), `RefpropBackend`, `TabulatedPropertyBackend` (CSV recovery; the only `σ_e`/`ε_r` source), `EmpiricalCorrelationBackend` (Letsou-Stiel / Latini / Brock-Bird), future `MixtureBackend`/`CustomFluidBackend`.

## 3.4 PropertyBackendRegistry

A **startup-time, name-keyed registry of backend constructors**, distinct from the `CorrelationRegistry` (§7.6). Keeping them separate is non-negotiable (`[F6]`, anti-pattern §16): the property engine has no geometry and no slots, so it must not live among slot-held closures.

```
interface PropertyBackendRegistry {                                     <<FROZEN>>
  register(name: str, constructor: () -> PropertyBackend) -> void       # startup only
  resolve(name: str) -> PropertyBackend
  instance_for(identity: FluidIdentity, name: str) -> PropertyBackend   # one shared per identity/run
}
```

- **Selection** is a `(FluidIdentity -> backend name)` binding in the Reproducibility Tuple (§15). Default = CoolProp.
- **Registration is startup-time only;** the registry owns no per-run state and is never mutated mid-solve.
- Replacing CoolProp with REFPROP or a tabulated surrogate is a tuple edit — config, not code (Rule 4).

---

# 4. Port and SystemState Interfaces

Layer 2 (connectivity) and Layer 7 (numerics). This section specifies `[F10]` and closes Decision 002/004: **Ports carry connectivity only; all unknowns live in a solver-owned vector.**

## 4.1 Port — connectivity only

```
Port {                                                                  <<FROZEN>>
  id: PortId
  owner: ComponentId           # for identity only; NOT a back-reference used to call the component
  role: (INLET | OUTLET | BRANCH | BIDIRECTIONAL)   # annotation, not a hard constraint
  peer: PortId?                # the connected port, set at Network assembly
}
```

- **A Port holds no values.** No `P`, `h`, `mdot`, no `FluidState`, no derived property. Storing any of these on a Port is the retired `PortState`/`FlowState` anti-pattern (§16).
- **Immutable after Network assembly** — therefore safe to share by reference.
- **Connecting two ports asserts, non-directionally:** equal pressure, equal enthalpy for the fluid passing, and a mass-flow balance (algebraic sum of `mdot` is zero at a node). Non-directionality is what keeps the simultaneous/DAE and dynamic formulations expressible (`[F10]`, MASTER §16).
- `role` is an *annotation* to aid readers and validators; it does not forbid reverse flow.

```
connect(a: Port, b: Port) -> Connection                                 <<FROZEN>>
```

`connect` is a Network-assembly operation (§12). It records the peer relationship and the three node assertions above; it moves no values.

## 4.2 PortHandle — the map into SystemState

A **PortHandle** is created at Network assembly and maps a Port to its slots in the `SystemState` vector. It is the only bridge between connectivity (Layer 2) and numerics (Layer 7), and it is owned by the Solver/assembly, never by the Port.

```
PortHandle {                                                            <<FROZEN>>
  port: PortId
  slot_P: index
  slot_h: index
  slot_mdot: index
}
```

- Handles turn "read this port's state" into "read these three array indices" — making finite-difference Jacobian columns a copy-and-bump and Newton assembly a native vector operation.
- Handles are created once, at assembly; they are immutable for the life of the assembled problem.

## 4.3 SystemState — the solver-owned unknown vector

```
SystemState {                                                           <<FROZEN>>
  values: float[]                       # flat, ordered, indexable
  layout: StateLayout                   # names + index ranges (introspectable)
}

interface StateLayout {
  port_handle(port: PortId) -> PortHandle
  internal_handle(component: ComponentId, state_name: str) -> InternalStateHandle
  names() -> (index -> qualified_name)  # ordered, enumerable — the precondition for §13's seam
}
```

- **Stores exactly:** every port-node's `(P, h, mdot)` and every component's named internal states (`[F3] [F15]`). Nothing else is a stored number anywhere in the framework.
- **No `PortState` storage object exists.** The names `PortState`/`FlowState` are retired (`[F10]`). The mapping from a port to its values is the `PortHandle`, not a stored object on the port.
- **Owned by the Solver.** Created at assembly, mutated only by the Solver. Nothing depends on the Solver, so nothing outside it may hold a mutable reference.
- **Steady ↔ dynamic compatibility:** in steady state, a component's internal states are present in the vector with derivative held at zero; the dynamic solver *unfreezes* them in place (no restructuring). The same flat ordered vector is what dynamic integrators (multiple snapshots), linearisation, and MPC/ROM extraction require (`[F18]`, §13.5).

## 4.4 InternalStateHandle

```
InternalStateHandle {                                                   <<FROZEN>>
  component: ComponentId
  name: str
  slot: index            # for fixed-count states
  slots: index[]?        # for variable-count (MovingBoundary) states, resolved per step
}
```

- For `Lumped`/`Segmented` components the slot count is fixed at assembly.
- For `MovingBoundary` components the count is **queryable per step, not frozen at assembly** (`[F16]`, §6.3) — `slots` is resolved against the component's current zone count each step.

---

# 5. Geometry Interfaces

Layer 0 (inert). **Immutable, standalone, flat family of typed value objects** (`[F8]`, MASTER §8). No god-object, no inheritance hierarchy; the kinds share almost no fields. A shared marker, if ever needed, is field-less and behaviour-less. **The moment a base `Geometry` grows a field, the flat family has rotted into a hierarchy** — a review red flag.

General rules for every geometry type:

- **Immutable, absolutely.** Varying a dimension produces a *new* Geometry → a *new* Reproducibility Tuple.
- **Supplies declared scalars, not itself.** A correlation receives `D_h`, `A`, `roughness`, … — never a Geometry object. This decouples a correlation from any geometry *type*.
- **May expose derived dimensional accessors** (e.g. `D_h` from primitives), but **never computes a correlation output** (no `Nu`, no `ΔP`). Dimensional algebra is allowed; physics is forbidden.
- **Stores no mesh/discretization** (`[F16]`) and no operating state (no T, no flow, no time-varying quantity).
- **Gravity is not Geometry** (`[F17]`): elevation/orientation are Geometry; the gravity vector is a Scenario input (§10).

## 5.1 PipeGeometry and the pipe trajectory (Refinement note 1)

The v1 minimal geometry remains, but `Δz` alone does not describe a real trajectory. The interface is structured so horizontal/vertical/inclined/curved/multi-segment runs, fittings, bends, collectors, and manifolds can be added **without redesigning `PipeGeometry` or any correlation that consumes it.**

```
PipeGeometry {                                                          <<FROZEN core fields>>
  L: float                 # flow length
  D_h: float               # hydraulic diameter (single D serves as D_h for round pipe)
  A: float                 # flow area
  roughness: float
  trajectory: PipePath     # replaces the bare Δz; see below
}
```

- **v1 default:** `trajectory = StraightSegment{ length: L, delta_z: Δz, inclination: θ }`. This reproduces today's behaviour exactly — a single straight run characterized by `Δz` — so v1 is **not** over-engineered.
- The correlation-facing scalars (`D_h`, `A`, `roughness`, and the per-cell `dz/dx` the gradient kernel needs) are **derived from the trajectory**, so a richer trajectory changes nothing in the correlation contract (§7) or the 1D-passage kernel (§11.3).

```
PipePath = StraightSegment | MultiSegmentPath                           <<SEAM: families beyond Straight>>

StraightSegment {
  length: float
  delta_z: float           # elevation change over the segment
  inclination: float       # angle from horizontal; 0 = horizontal, ±90° = vertical
}

# Declared shape for future extension — NOT implemented in v1, but the trajectory
# field is typed as PipePath now so adding these is additive, never a redesign:
MultiSegmentPath {
  segments: PathSegment[]              # ordered runs
}
PathSegment = StraightSegment
            | BendSegment   { radius: float, angle: float, ... }        # <<SEAM>>
            | FittingSegment{ kind: FittingKind, K_L: float, ... }      # <<SEAM>>
```

- **Contract guarantee:** `PipePath` exposes, for any trajectory, the two derived quantities the physics needs — total `L` and a per-cell `dz/dx(s)` profile — plus an optional minor-loss accumulator (`Σ K_L`) for fittings/bends. A component and its correlations consume only these derived accessors, never the trajectory's internal structure.
- **Collectors/manifolds** are *not* a single pipe; they are a **Network topology** of pipe segments joined at `Junction`s (§12), not a new geometry field. The geometry interface stays a single-passage description; multiplicity is the Network's job. (See §17 amendment.)

`PipePath.derived()` (read-only) returns: `{ L_total, dz_dx_profile, sum_minor_K }`. Geometry computing this *dimensional* algebra is permitted; it still computes no `Nu`/`ΔP`.

## 5.2 PlateGeometry

```
PlateGeometry {                                                         <<FROZEN core fields>>
  N_plates: int
  chevron_angle: float
  plate_spacing: float
  port_dims: (float, float)
  A_per_plate: float
  sink_side: SinkSideGeometry?      # secondary-fluid passage description
}
```
No single `D`; correlations consume `chevron_angle`, `plate_spacing`, `A_per_plate`, etc. Used by the plate condenser (§8, §11).

## 5.3 MicrochannelGeometry

```
MicrochannelGeometry {                                                  <<FROZEN core fields>>
  N_channels: int
  D_h_channel: float
  fin_geometry: FinGeometry
  A_heated: float
  wall_mass: float                  # exposed for the dynamic wall-capacitance term
  wall_material: MaterialRef
}
```
Exposes `wall_mass`/`wall_material` because the frozen dynamic wall-capacitance internal state needs them (`[F15]`). Used by the evaporator (§11).

## 5.4 AccumulatorGeometry (Refinement note 2 — geometry only)

The accumulator is a **pressure-reference component** (§11), and **geometry must be separated from pressure law.** `AccumulatorGeometry` is therefore a *containment* description only — it describes the vessel, never how pressure is set.

```
AccumulatorGeometry {                                                   <<FROZEN core fields>>
  V_total: float
  containment: ContainmentSpec       # vessel/port geometry; law-agnostic
  thermal: ThermalSpec?              # heater/wall data, used only by laws that need it (e.g. HCA)
}
```

- **`AccumulatorGeometry` contains no `V_gas_charge`, no spring constant, no bellows area.** Those are **parameters of a pressure law**, not geometry, and live with the law object (§11.7 / `VolumePressureLawInput` §7.5). This is the structural separation the refinement note requires: *geometry describes the vessel; the pressure-reference law describes the physics.*
- A PCA charge volume, an HCA heater duty, a bellows effective area, or a spring rate are supplied to the selected `VolumePressureLaw`, **not** stored in geometry. Swapping PCA→HCA→bellows→spring→gas-charged changes the *law binding* (Rule 4), and at most the optional `thermal`/`containment` sub-specs the law reads — never the geometry *type*.

---

# 6. Discretization Interfaces

Layer 5 (component numeric configuration). The **fidelity axis** (`[F16]`, MASTER §9): a small declared object that fixes the **count and structure** of a component's internal states. **Owned by the component's numeric configuration — not Geometry (immutable, physical), not the Solver (which sees only the resulting unknown count).**

```
Discretization = LumpedDiscretization
               | SegmentedDiscretization
               | MovingBoundaryDiscretization                           <<FROZEN enumeration>>

interface Discretization {
  mode() -> (LUMPED | SEGMENTED | MOVING_BOUNDARY)
  declared_state_count(geometry: Geometry) -> int        # how many internal-state slots this asks for
  cell_metrics(geometry: Geometry) -> CellMetrics[]      # local per-cell dims, DERIVED from geometry
}
```

- **State count is declared by the Discretization, never by Geometry, never assumed by the Solver** (`[F16]`). The Solver reads `declared_state_count` to size `SystemState`; it never guesses.
- **Geometry is used to derive local cell metrics, never the reverse.** `cell_metrics` computes per-cell length/area/`dz/dx` from the geometry (e.g. `L/N` from `PipeGeometry.L` and its `PipePath`); the mesh is never stored in geometry. The *same* Geometry object serves a lumped and a segmented run.

```
LumpedDiscretization {}                                  # 0D: one control volume
SegmentedDiscretization { N: int }                       # 1D finite-volume: N control volumes
MovingBoundaryDiscretization { max_zones: int }          # <<SEAM>>: zones appear/disappear
```

- **`LumpedDiscretization`** — one control volume; the v1 default for pipes, condenser, accumulator, reservoir, junctions, valves, pump. Lumped is the **one-cell case of the segmented kernel** (§11.3), not a separate code path.
- **`SegmentedDiscretization`** — N control volumes; per-segment states (and per-segment wall T for heated components). The meaningful steady mode for the evaporator. In steady state, per-segment states are named with zero derivative; the dynamic solver unfreezes them.
- **`MovingBoundaryDiscretization`** — declared now (`[F16]`), built in Phase 6. **State count itself changes** as zones appear/disappear.

**MovingBoundary variable state count handling (future):** `declared_state_count` is **queryable per step, not frozen at Network assembly** for this mode. The dynamic solver must support event detection (zone appearance/disappearance) as a first-class concept. The contract is shaped now: `MovingBoundaryDiscretization` exposes `current_state_count(component_state) -> int` and `events(component_state) -> ZoneEvent[]` at step time. The steady and dynamic component contribution contracts (§11) are **identical regardless of mode** — Discretization only changes how many states there are.

---

# 7. Correlation Interfaces

Layer 3 (closure). A **Correlation is a stateless pure function** selected by name (`[F4] [F11]`, MASTER §10). It is the core research seam.

## 7.1 The contract

```
interface Correlation {                                                 <<FROZEN>>
  role() -> CorrelationRole
  evaluate(input: CorrelationInput) -> CorrelationOutput
}
```

- **Correlations are pure closures.** Stateless, no caching, no globals, no `_fluid_name` hacks, no `hasattr` self-introspection (legacy violations §16).
- **A correlation does not know component, geometry *type*, network, or solver** (`[F4]`, anti-pattern §16). It receives `FluidState`(s) and declared scalar/context data via a role-typed input, and returns a value plus a verdict. It must never receive a whole `Component` or `Geometry` object.
- **The Component builds the input** from its FluidState(s) and the scalars it forwards from its Geometry. The correlation sees only data.

## 7.2 CorrelationInput — role-typed, immutable, AD-traceable

```
CorrelationInput = SinglePhaseDPInput
                 | TwoPhaseDPInput
                 | HTCInput
                 | VoidFractionInput
                 | VolumePressureLawInput
                 | ...                                                  <<FROZEN role set>>
```

- **One input type per *role*, not per *formula*** (`[F11]`): Shah, Gungor-Winterton, and Kim-Mudawar all consume `HTCInput`; Friedel and Müller-Steinhagen-Heck share `TwoPhaseDPInput`. **The role set is bounded by design and does not grow with the catalogue.**
- Every `CorrelationInput` is an **immutable, AD-traceable struct.** The same contract serves a Shah formula, an FD Jacobian column, and a future ML/surrogate closure (whose input doubles as its feature vector).
- Each role type carries: the relevant `FluidState`(s) (vector-first where applicable), the declared geometry scalars its family needs, and flow/context scalars (`G`, `q''`, `x`, `Re`, `Bond`, …). Exact fields per role are specified in `CORRELATION_CONTRACT.md`; the **types and roles** are frozen here.

Representative role payloads (illustrative field lists; authoritative in `CORRELATION_CONTRACT.md`):

```
SinglePhaseDPInput   { state: FluidState[], G: float, D_h: float, roughness: float, L_cell: float }
TwoPhaseDPInput      { state: FluidState[], G: float, x: float[], D_h: float, L_cell: float }
HTCInput             { state: FluidState[], G: float, q_flux: float?, x: float[], D_h: float, geom_scalars: {...} }
VoidFractionInput    { state: FluidState[], x: float[] }
VolumePressureLawInput { V_g: float, V_total: float, law_params: {...}, thermal: ThermalSpec? }
```

## 7.3 CorrelationOutput

```
CorrelationOutput {                                                     <<FROZEN>>
  value: float[]                 # vector-first; the closure result (e.g. HTC, friction gradient, ε_void)
  verdict: ValidityVerdict
}
```

The output **always carries a verdict** (Rule 5). A correlation may not return a bare number.

## 7.4 ValidityVerdict

```
ValidityVerdict {                                                       <<FROZEN>>
  status: (IN_ENVELOPE | EXTRAPOLATED | OUT_OF_RANGE)
  envelope: EnvelopeRef          # fluid family, geometry range, flow-regime/quality range, Re/Bond bounds
  detail: str?
}
```

- A correlation **declares whether the call was in-envelope or extrapolated**, and the envelope it checked against.
- **The framework warns on extrapolation; it never silently clamps or extrapolates** (`[F4]`). The verdict is a transparency output surfaced into the `Result` (§14); the researcher decides acceptability but is never unaware. The envelope declaration format is specified in `CORRELATION_CONTRACT.md`.

## 7.5 Role catalogue

The enumerated, bounded role set (the slot vocabulary components draw from):

| Role | Input type | Output meaning | Calibrated? (§9) |
|---|---|---|---|
| Single-phase ΔP | `SinglePhaseDPInput` | friction gradient `(dP/dx)_fric` | `R*` on friction gradient |
| Two-phase ΔP | `TwoPhaseDPInput` | two-phase friction gradient | `R*` on friction gradient |
| Heat-transfer coefficient | `HTCInput` | HTC | HTC multiplier |
| Void fraction | `VoidFractionInput` | `ε_void` / `α` | no |
| Volume↔pressure law | `VolumePressureLawInput` | `P` from `V_g` (accumulator) | no |

> **Note (Refinement note 3):** there is **no `HeatExchangeMethodInput` role and no "heat-exchange-method" correlation slot.** ε-NTU and LMTD are *not* correlations — they are heat-exchanger **solution strategies** and are specified separately as `HeatExchangerModel` in §8. This is a deliberate departure from MASTER §10's enumerated `HeatExchangeMethodInput` and §12's "heat-exchange-method (ε-NTU/LMTD) slot" (see §17 amendment).

## 7.6 CorrelationRegistry

```
interface CorrelationRegistry {                                         <<FROZEN>>
  register(name: str, instance: Correlation) -> void     # startup only; name -> stateless instance
  resolve(name: str) -> Correlation
  by_role(role: CorrelationRole) -> (name -> Correlation)
}
```

- Holds **named, stateless instances grouped by role.** Registration is startup-time; it owns no per-run state. **Not a plugin framework, factory, or DI container** (Principle 6).
- A Component declares **slots by role**; the Reproducibility Tuple **binds a registered name to each slot** (§15). Replacing a model = rebinding the slot name (Rule 4).
- **The PropertyBackend is NOT in this registry** — separate registry (§3.4), no geometry, no slots; this avoids the DAG cycle (`[F6]`).

---

# 8. Heat Exchanger Model Interface

**This is a new top-level seam (Refinement note 3).** ε-NTU, LMTD, segmented marching, and moving-boundary HX models are **heat-exchanger solution/model strategies**, fundamentally different in kind from a Shah/Friedel/Kim-Mudawar correlation. A correlation returns *one local closure value* (an HTC, a friction gradient) for *one control volume*; a **HeatExchangerModel orchestrates a whole-exchanger heat-rate / outlet-state solution**, consuming HTC and ΔP correlations as inputs and applying secondary-fluid boundary conditions. It is therefore not a member of the `CorrelationRegistry` role set.

## 8.1 Concept and placement

- **Layer:** a **component-internal strategy**, selected per heat-exchanger component (condenser, evaporator) the same way a correlation slot is — a named binding in the tuple (Rule 4) — but resolved from a **separate `HeatExchangerModelRegistry`**, not the correlation registry.
- **It is not a correlation and not a property backend.** It does not implement `Correlation`. It has its own contract below.

```
interface HeatExchangerModel {                                          <<FROZEN>>
  kind() -> (EPSILON_NTU | LMTD | SEGMENTED_MARCH | MOVING_BOUNDARY)

  solve(req: HXSolveRequest) -> HXSolveResult
}

HXSolveRequest {
  primary_state_in: FluidState        # working fluid inlet (P, h, identity)
  primary_mdot: float
  secondary_bc: SecondaryFluidBC      # sink/source side boundary condition (§8.3)
  geometry: Geometry                  # PlateGeometry / MicrochannelGeometry — scalars only forwarded
  discretization: Discretization      # Lumped(ε-NTU/LMTD) | Segmented | MovingBoundary
  htc_primary: Correlation            # HTC correlation slot, injected by the component
  htc_secondary: Correlation?         # secondary-side HTC, if resolved
  dp_primary: Correlation             # ΔP correlation slot, injected by the component
  calibration: CalibrationBinding     # HTC/UA and friction multipliers (§9)
}

HXSolveResult {
  primary_state_out: FluidState       # derived outlet (P, h) — never stored, returned for assembly
  Q: float                            # total heat rate
  dP_primary: float                   # integrated, derived (not primary)
  zone_profile: ZoneProfile?          # zones/areas, when applicable
  verdicts: ValidityVerdict[]         # from every correlation it called
}
```

## 8.2 How it interacts with HTC and ΔP correlations

- **HeatExchangerModel consumes correlations; it does not replace them.** ε-NTU needs a `UA`, which it builds from the **HTC correlations** (primary and, when present, secondary side) and the geometry's area scalars. A segmented march calls the **HTC correlation per cell** to get the local coefficient and the **ΔP correlation per cell** for the friction gradient.
- The component **injects** the resolved HTC/ΔP correlations and calibration into the model (`htc_primary`, `dp_primary`, …). The model never resolves a registry itself and never knows which formula it received — it sees the `Correlation` contract only.
- **Calibration applies through the model at the documented seams** (§9): the HTC/UA multiplier scales the coefficient the model assembles; the friction multiplier scales the friction gradient the ΔP correlation returns. The model never scales a balance.

## 8.3 Secondary-fluid boundary conditions

```
SecondaryFluidBC = SinkInletTempAndFlow { T_in: float, mdot: float, fluid: FluidIdentity }
                 | FixedWallTemp        { T_wall: float }
                 | FixedHeatRate        { Q: float }
                 | AmbientCoupling      { T_amb: float, UA_amb: float }    # see §10 Environment
```

- The condenser's `sink T and flow` and the evaporator's `heat load / wall flux` (MASTER §12) are delivered **as a `SecondaryFluidBC`, bound from the Scenario** (§10), not stored as a component attribute.
- The model resolves the heat exchange between the primary working fluid and this secondary boundary using its `kind` strategy.

## 8.4 The four model kinds

- **`EPSILON_NTU`** — effectiveness–NTU closed-form for a `Lumped` exchanger; builds `UA` from HTC correlations + area, applies `SinkInletTempAndFlow`. The v1 condenser default.
- **`LMTD`** — log-mean-temperature-difference closed-form; an alternative `Lumped` strategy with the same request/result contract.
- **`SEGMENTED_MARCH`** — marches `Segmented` cells, calling HTC and ΔP correlations per cell, integrating `Q` and `dP`. The meaningful evaporator strategy and the high-fidelity condenser strategy.
- **`MOVING_BOUNDARY`** `<<SEAM>>` — zone-tracking model (desuperheat / two-phase / subcool) with variable zone count, built on `MovingBoundaryDiscretization` (§6). Declared now, implemented Phase 6.

## 8.5 Relationship to condenser/evaporator components

- The **Condenser** and **Evaporator** (§11) each hold a `HeatExchangerModel` slot (bound by name in the tuple) plus their HTC/ΔP correlation slots. The component forwards geometry scalars, builds the inputs, injects the correlations and calibration, calls `model.solve(...)`, and turns `HXSolveResult` into its **residual/derivative contribution** (§11) — it does not let the model touch ports, the network, or the solver.
- This keeps the swap **ε-NTU → LMTD → segmented → moving-boundary** a configuration change on the component, exactly parallel to swapping a correlation, while correctly *not* miscategorising these strategies as correlations.

---

# 9. Calibration Interfaces

Layer 4 (modifier value object, applied at Layer 5). Reconciles models with experiment **transparently** (`[F5]`, MASTER §11): every correction named, neutral by default, applied at one seam, always reported.

## 9.1 CalibrationMode

```
CalibrationMode = NONE | TARGET                                         <<FROZEN>>
```

- **`NONE`** — all factors = 1; pure predictive physics; the default and honest baseline.
- **`TARGET`** — factors chosen to meet a stated experimental target. A Result produced under `TARGET` is **flagged calibrated, not predictive** (§14), and is never compared as-equal to a `NONE` run.
- **Dataset-fitting (least-squares over many points) is NOT a calibration mode** — it is identification/surrogate territory (Phase 5) and must route its results back as ordinary explicit factors at this same seam, never as a parallel hidden mechanism.

## 9.2 CalibrationFactor

```
CalibrationFactor {                                                     <<FROZEN>>
  target: CalibrationTarget       # FRICTION_GRADIENT | HTC | UA
  value: float                    # 1.0 == neutral
  mode: CalibrationMode
  seam: SeamLocation              # the documented point of application (which slot, which component)
}

CalibrationTarget = FRICTION_GRADIENT | HTC | UA                        <<FROZEN>>
```

- **Pressure-drop calibration applies ONLY to the friction gradient** (`[F14]`): `R*` multiplies `(dP/dx)_friction`. Gravity and acceleration are physics and are **never** scaled.
- **Heat-transfer calibration applies to HTC or UA** at the analogous output seam.
- A factor is a value object; it scales a **closure output**, never a balance (the conservation firewall, §9.5).

## 9.3 CalibrationScope and resolution

```
CalibrationScope = SLOT | COMPONENT | GLOBAL                            <<FROZEN>>
```

Resolution order is **slot → component → global**, falling back to neutral:

```
resolve(slot: SlotId, component: ComponentId) -> CalibrationFactor
   # per-slot factor if present, else per-component, else global, else neutral (value = 1, mode = NONE)
```

- **Owned at the per-component correlation slot.** The Network/Solver own only *aggregation and reporting*, never the physics (`[F5]`).
- Calibration is **applied by the Component, at the seam between a correlation's (or HX model's) raw output and its use in a balance** — never inside a correlation, never on a conservation equation.

## 9.4 CalibrationReport

```
CalibrationReport {                                                     <<FROZEN>>
  factors: CalibrationFactor[]    # every non-neutral factor: target, value, mode, seam
  mode: CalibrationMode           # the run's overall mode
}
```

- **Calibration must always be reported.** Every non-neutral factor, its value, its mode, and its seam location are inputs in the tuple (§15) and outputs in **every** Result (§14). *A factor that is not reported cannot exist.*

## 9.5 The conservation firewall (specified as invariants)

1. **Correlations stay pure** — they return physics; calibration scales afterward.
2. **Conservation is never scaled** — calibration multiplies closures (`ΔP_friction`, HTC, UA), never balances (mass/energy continuity).
3. **Calibration cannot mask an invariant violation** — energy/mass balances (§14) are computed from *un-calibrated* conservation, so a wrong calibration shows up as a *worse* data match, never as a *false-passing* balance.

---

# 10. Scenario and Boundary-Condition Interfaces

**Scenario is specified precisely (Refinement note 4).** It is the operating point a Network is evaluated at (`[F17]`, MASTER §15) and the **primary DOE axis** for Phase 5. It is decomposed into five role-typed parts so that DOE, surrogate generation, dynamic simulation, and future MPC each draw from the part they need.

## 10.1 Scenario structure

```
Scenario {                                                              <<FROZEN structure>>
  boundary_conditions: BoundaryCondition[]
  commands:            Command[]
  disturbances:        Disturbance[]                # <<SEAM: time-varying; v1 may be empty/constant>>
  environment:         Environment
  operating_point:     OperatingPoint
}
```

All five parts are **immutable** and bound to components/network at solve time (§10.5). Sweeping any field without rebuilding the loop is the definition of a Scenario input (the membership test, §10.4).

## 10.2 The five parts

```
BoundaryCondition = EvaporatorHeatLoad   { Q: float | wall_flux: float, target: ComponentId }
                  | CondenserSink        { T_in: float, mdot: float, fluid: FluidIdentity, target: ComponentId }
                  | FixedInletState      { P: float?, h: float?, target: PortId }
                  | AccumulatorPressureSetpoint { P_set: float, target: ComponentId }   # the reference value

Command = PumpSpeedCommand   { omega: float, target: ComponentId }
        | PumpFlowTarget     { mdot: float, target: ComponentId }
        | ValveOpeningCommand{ fraction: float, target: ComponentId }

Disturbance = TimeVarying { signal: Signal, applies_to: BoundaryCondition | Command }   # <<SEAM>>

Environment {
  gravity: Vector3            # default 1 g terrestrial; zero-g / variable-g is a Scenario sweep [F17]
  T_ambient: float?
  ambient_loss: AmbientLossSpec?     # UA_amb / heat-loss condition for exposed components
}

OperatingPoint {
  # the named steady operating-point specification this run targets:
  # e.g. design heat load, nominal charge, target subcooling — the DOE coordinate label
  label: str?
  coordinates: { name -> float }
}
```

Mapping to the master's named examples (MASTER §10 task list): **evaporator heat load** → `EvaporatorHeatLoad` (BC); **condenser sink inlet temperature and flow** → `CondenserSink` (BC); **pump speed command** → `PumpSpeedCommand` (Command); **valve opening command** → `ValveOpeningCommand` (Command); **gravity vector** → `Environment.gravity`; **ambient heat loss** → `Environment.ambient_loss`; **accumulator pressure setpoint** → `AccumulatorPressureSetpoint` (BC, the reference value).

## 10.3 Why the decomposition (DOE / surrogate / dynamic / MPC)

- **DOE & surrogate datasets (Phase 5):** the sweep iterates over `boundary_conditions` / `commands` / `operating_point` against a *fixed* Network and *fixed* Components. The `(Scenario in tuple) → (invariants + outputs in Result)` mapping is exactly the input/output pairing a surrogate trains on (§14, §15).
- **Dynamic simulation:** `Disturbance` is the seam for time-varying inputs; v1 leaves it empty or constant, dynamics activates it. A `Command` becomes a time-varying input under a disturbance without changing the Scenario shape.
- **Future MPC:** `commands` is precisely the manipulated-variable vector; `boundary_conditions`/`disturbances` are the measured/unmeasured disturbance vector; `OperatingPoint` is the linearisation set-point. The Sensitivity/Linearisation seam (§13.5) draws its **input vector from the Scenario** and its **output vector from the Result**.

## 10.4 Division of responsibility (what belongs where)

| Belongs to | What | Membership test |
|---|---|---|
| **Scenario** | heat loads, sink T/flow, pump/valve commands, gravity, ambient, accumulator `P_set`, operating-point label | "If I sweep this in Phase 5 without rebuilding the loop, it is Scenario." |
| **Component** | Geometry, fixed parameters (η, Cv, channel count), slot selections, calibration factors, Discretization mode, internal-state names, the pressure-reference **law** | "If changing this changes one part without re-wiring, it is Component." |
| **Network** | which components exist, how Ports connect, branch topology, which node is the reference, inventory accounting | "If changing this changes the P&ID, it is Network." |
| **Solver settings** | solver type, tolerances, iteration limits, FD step | "If changing this changes only the numerics, not the physics, it is Solver settings." |

- **Gravity is Scenario, not Geometry** (`[F17]`). **Fluid choice is tuple-level identity** selecting the backend, not Scenario. **`P_set` value is Scenario; the pressure *law* is Component; *which node* is the reference is Network** — the three-way split of the pressure reference (§11.7, §12).

## 10.5 Binding

```
bind(scenario: Scenario, network: Network) -> ScenarioBinding           <<FROZEN>>
```

`bind` resolves each Scenario part's `target` to the component/port it applies to, producing an immutable binding the Solver reads. A BC/Command targeting a non-existent component is a binding-time error, not a silent no-op.

---

# 11. Component Interface

Layer 5 (physics). The common contribution contract (`[F8-internal-state] [F14] [F15]`, MASTER §12). **The signature is frozen and identical across `Lumped → Segmented → MovingBoundary` and across steady → dynamic** — Discretization sets the state count, the solver decides the scheme, the contract does not change.

## 11.1 The contribution contract (FROZEN)

```
interface Component {                                                   <<FROZEN>>

  # --- declarations (static structure) ---
  ports() -> Port[]
  geometry() -> Geometry
  discretization() -> Discretization
  correlation_slots() -> SlotDeclaration[]          # roles I need, by name
  hx_model_slot() -> SlotDeclaration?               # only heat-exchanger components (§8)
  calibration_slots() -> CalibrationSlot[]
  scenario_bindings() -> ScenarioBindingDecl[]      # what Scenario inputs I accept
  internal_state_names() -> str[]                   # named even when frozen [F15]

  # --- contribution (the frozen kernel) ---
  # "Given a trial state at my Ports and my internal states, return my residual vector
  #  and/or my internal-state derivatives, continuous & differentiable across the saturation line."
  contribute(trial: ComponentTrialState, ctx: EvalContext) -> ComponentContribution

  # --- result projection ---
  result_contribution(converged: ComponentTrialState, ctx: EvalContext) -> ComponentResult
}

ComponentTrialState {
  port_values: { PortId -> (P, h, mdot) }    # handed in by the Solver via SystemState — never fetched
  internal_states: { str -> float[] }        # this component's named states, current trial values
}

EvalContext {
  backend: PropertyBackend                   # supplied by context; FluidState derives through it
  scenario: ScenarioBinding                  # the inputs bound to me
  calibration: CalibrationBinding            # my resolved factors
  correlations: { role -> Correlation }      # my resolved slots
  hx_model: HeatExchangerModel?              # my resolved HX strategy, if any
}

ComponentContribution {
  residuals: float[]                         # my local balance residuals at this trial
  derivatives: float[]?                      # d(internal_state)/dt; zero (frozen) in steady state
}
```

- **A Component must provide:** its declared Ports; its internal-state names (even when frozen); its contribution; its slot declarations; the calibration factors actually applied (into the report); and the declared scalars it forwards to correlations.
- **A Component must consume:** the `(P, h, mdot)` at its Ports (handed in via `ComponentTrialState`, **never** fetched from the network), its Geometry, parameters, Discretization, internal states, and the Scenario inputs bound to it.
- **A Component must never access:** the Network or a neighbour; the Solver or its scheme; a correlation's formula; the `PropertyBackend` directly other than through `FluidState` derivation in `ctx`; global inventory accounting (anti-patterns §16).

## 11.2 Internal-state membership (FROZEN rule)

> **A quantity is component internal state iff the component stores it and will provide its time-derivative in dynamics. Everything recomputable from port unknowns + geometry + correlations is NOT state** (`[F15]`).

Internal state: wall temperature(s) per cell; fluid/liquid/vapor inventory per cell; accumulator gas volume `V_g`; condenser moving-boundary positions (variable count); actuator states (valve position, pump shaft speed — frozen v1). **Not state:** port `P, h, mdot` (SystemState); derived `T, x, ρ` (FluidState); correlation outputs (recomputed each call); system pressure `P_sys` (a SystemState unknown).

## 11.3 The 1D-passage kernel (gradient form, FROZEN)

All 1D passages (Pipe; Evaporator/Condenser segments by composition) **compute pressure gradients per control volume** (`[F14]`); the Discretization integrates them; **total ΔP is a derived output, not the primary object.** Per cell:

- `(dP/dx)_friction` from the slot correlation — **the only term `R*` scales**;
- `(dP/dx)_gravity = ρ g dz/dx` — `g` from `Scenario.Environment.gravity`, `dz/dx` from `Geometry` (`PipePath.derived()`, §5.1);
- `(dP/dx)_acceleration = d(G²v)/dx`.

`Lumped` is the **one-cell integration of the identical kernel** — lumped, segmented, and dynamic share one physics kernel. The shared 1D mechanism stays **internal** to the component; it is never a public primitive.

## 11.4 Component reference table

Notation: ports `[in]`/`[out]`/`[branch_i]`; **(frozen v1)** = named-but-zero-derivative until Phase 6.

| Component | Ports | Geometry | Internal states | Correlation slots | HX model slot | Calibration | Scenario binding |
|---|---|---|---|---|---|---|---|
| **Pump** | `[in]`,`[out]` | minimal (perf-map ref); exposes `L, A` for inertia | **(frozen)** shaft speed / loop inertia `I` | pump performance/efficiency map | — | none typical | `PumpSpeedCommand` ω or `PumpFlowTarget` ṁ |
| **Pipe** | `[in]`,`[out]` | `PipeGeometry` (+ `PipePath`) | **(frozen)** per-seg mass/momentum, wall T if heated (count = Discretization) | single-phase ΔP; two-phase ΔP; void fraction | — | `R*` on friction gradient | optional wall heat (BC) |
| **Evaporator** | `[in]`,`[out]` | `MicrochannelGeometry` | flow regime (algebraic); **(frozen)** wall capacitance/seg, fluid inventory | boiling HTC; two-phase ΔP | **yes** (`SEGMENTED_MARCH` default) | HTC ×, `R*` on friction | `EvaporatorHeatLoad` Q / wall flux |
| **Condenser** | `[in]` (2φ),`[out]` (subcooled) | `PlateGeometry` | effective areas/zone; **(frozen)** moving-boundary positions | condensation HTC; ΔP | **yes** (`EPSILON_NTU` default; LMTD/segmented/MB selectable) | HTC/UA ×, `R*` on friction | `CondenserSink` T and flow |
| **Accumulator** | one liquid `[port]`; wires reference node | `AccumulatorGeometry` (containment only) | liquid/gas split; **(frozen)** `V_g` (P derived) | one **VolumePressureLaw** slot (PCA/HCA/bellows/spring/gas-charged) | — | none typical | `AccumulatorPressureSetpoint` `P_set` / control input |
| **Valve** | `[in]`,`[out]` | minimal (Cv) | **(frozen)** position | loss coefficient `K_L` vs opening | — | optional × on loss | `ValveOpeningCommand` fraction |
| **Junction** | `[trunk]` + N `[branch_i]` | minimal | none (negligible storage) | none intrinsic | — | none | — |
| **Reservoir** | `[in]`,`[out]` | containment volume | inventory; **(frozen)** liquid level | none | — | none | — |

Two component-shape decisions are baked in: **`Junction` is one n-in/m-out conservation node** (`Splitter`/`Mixer` are configurations, optional thin aliases); **`Reservoir` holds inventory and guarantees NPSH but sets no pressure reference** (the Accumulator sets the reference; the Network is the single inventory accountant).

## 11.5 Heat-exchanger components (Evaporator, Condenser)

The Evaporator and Condenser additionally hold a **`HeatExchangerModel` slot** (§8). Their `contribute` builds the `HXSolveRequest` (forwarding geometry scalars, injecting resolved HTC/ΔP correlations and calibration, attaching the `SecondaryFluidBC` from the Scenario), calls `model.solve(...)`, and converts `HXSolveResult` into residuals/derivatives. The component never lets the model touch ports, network, or solver, and never miscategorises the model as a correlation.

## 11.6 Accumulator — the pressure-reference component (Refinement note 2)

The Accumulator is specified as a **pressure-reference component**, with **geometry and pressure law strictly separated**:

- **It is a first-class Component** that *sets a pressure reference.* It owns the **pressure-setting law and value**; the **Network owns which node is the reference and the one-reference invariant**; the **Solver owns global consistency** (`[F7]`, the three-way split).
- **Geometry ≠ pressure law.** `AccumulatorGeometry` (§5.4) describes containment only. The **pressure-reference law is a swappable slot** filled by a `VolumePressureLaw` (a closure consuming `VolumePressureLawInput`, §7.5). Different technologies — **PCA, HCA, bellows, spring-loaded, gas-charged** — are **different law bindings**, selected by name in the tuple (Rule 4), **without redesigning the component.**
- **Stored internal state is `V_g`** (gas/displaced volume); **`P` is derived** from the law, never stored (`[F15]`). In dynamics the accumulator derives `dP/dt` from `dV_g/dt`. It does **not** own `P_sys` as a stored field.
- The `P_set` value comes from the Scenario (`AccumulatorPressureSetpoint`); the law maps `(V_g, V_total, law_params, thermal?)` → `P`.

```
VolumePressureLaw : Correlation   with role = VOLUME_PRESSURE_LAW       # bound by name
   evaluate(VolumePressureLawInput) -> CorrelationOutput   # value = P from V_g
```

Law parameters (PCA charge volume & polytropic index, HCA heater duty & saturation reference, bellows effective area & rate, spring constant & preload, gas-charge pressure) live in `law_params` / `thermal`, **never in geometry.**

---

# 12. Network Interface

Layer 6 (topology). States **what must hold**, never **how to make it hold** (`[F7]`, MASTER §13).

```
interface Network {                                                     <<FROZEN>>
  components() -> Component[]
  connections() -> Connection[]
  junctions() -> Junction[]
  pressure_reference() -> ComponentId          # exactly one (the Accumulator); see invariant below
  branch_groups() -> BranchGroup[]             # splitter↔mixer pairings, equal-ΔP branch sets
  inventory() -> InventoryAccount              # the single global mass accountant
  validate() -> TopologyVerdict
}
```

**Network owns (Where):** the connection graph; continuity & loop-closure conditions; **uniqueness** of the pressure reference; branch structure; **global mass-inventory accounting** (single accountant, first-class from v1); topology validation.

**Network must NEVER do:**
- compute physics, call a correlation, or read FluidState internals;
- own a numerical scheme or touch the Solver;
- let a Component see a neighbour or another branch's flow (branch closure is a Network condition, not a component query);
- set a pressure *law/value* (that is the Accumulator's) — it owns only *which node* and the one-reference invariant.

**TopologyVerdict** (validation, `[F7]`): no dangling ports; **exactly one pressure reference** (a second accumulator is caught here, not as a numerical pathology); well-formed splitter↔mixer branch sets; no double-counted inventory.

- **Loop closure** — "Σ pressure changes around any closed path = 0" — is a Network condition the Solver satisfies; no single component closes the loop. This embodies pressure-global / enthalpy-local asymmetry.
- **Branch handling** — parallel branches between a common splitter and mixer share the **same ΔP**, flows summing to the trunk. The Network states it; the Solver enforces it; the Junction supplies only conservation; branches supply only resistances. **Adding a branch is a topology edit, never a solver or component edit.** (Collectors/manifolds from §5.1 are realized here, as pipe segments joined at Junctions.)

---

# 13. Solver Interface

Layer 7 (numerics), the **sink of the DAG**. Reads the Network and Component contributions, owns `SystemState`, drives to satisfaction (`[F1] [F7]`, MASTER §14). **Nothing depends on the Solver.**

## 13.1 SteadyStateSolver

```
interface SteadyStateSolver {                                           <<FROZEN>>
  assemble(network: Network, scenario: ScenarioBinding) -> AssembledProblem
  solve(problem: AssembledProblem, settings: SolverSettings) -> Result
}

AssembledProblem {
  state: SystemState                  # solver-owned; the unknown vector x
  residual(x: SystemState) -> float[] # assembled from all Component contributions + Network conditions
}
```

- **Local/global split:** each Component computes its own contribution from its port + internal states (§11); the Solver assembles all contributions + all Network continuity/closure conditions into one global system over `SystemState` and drives it to convergence.
- **Two steady strategies, both behind the same component contract:**
  - **Fixed-point pressure iteration** — robust start for single loops (iterate global pressure/flow, march local enthalpy);
  - **Simultaneous Newton–Raphson** on the full residual — kept a **first-class option** (the dynamic path is inherently simultaneous and inherits this assembler). The legacy `(R1 = ΔP_pump − ΣΔP, R2 = P_sys − P_acc)` residual shape is the proven basis.

## 13.2 Residual assembly and SystemState ownership

- The Solver **owns `SystemState`** and is the only mutator. It scatters trial values to each component via `ComponentTrialState` (using `PortHandle`/`InternalStateHandle`) and gathers `ComponentContribution` back — **no component fetches from the network.**
- **One shared residual assembly** serves steady Newton, the dynamic DAE, and the linearisation seam (`[F18]`); the steady solution is the consistent initial condition for the DAE.

## 13.3 The Jacobian / sensitivity seam

- **Structured finite differences are primary** (`[F18]`): the Solver obtains the Jacobian itself by perturbing `SystemState` over the component contract — a copy-and-bump on the array.
- **Analytic/AD derivatives are optional:** a Component *may* provide an analytic Jacobian as an override, and a backend *may* provide property derivatives behind a capability flag (§3.3). Components are **not required to provide derivatives** — only to be *differentiable* (no hidden non-smooth branches at phase transitions; `(P, h)` buys continuity, not smoothness).
- **AD is not promised.** CoolProp/REFPROP are compiled externals; the AD seam is kept open but **the architecture does not build on it** and this spec states no AD path.

## 13.4 Convergence metadata and invariants

```
ConvergenceMetadata { iterations: int, final_residual_norm: float, converged: bool, strategy: str }
```

**Validation invariants are first-class Solver outputs** feeding the Result (§14): global energy imbalance, mass imbalance, pressure-closure residual, physical-bound checks (`0 ≤ x ≤ 1`, `T < T_crit`) — **all computed from un-calibrated conservation** (§9.5).

The Solver **must never access** any physics, correlation, geometry, or property formula; it must work for *any* valid Network.

## 13.5 DynamicSolver and the Linearisation seam (SEAM)

```
interface DynamicSolver { ... }                                         <<SEAM: Phase 6>>
interface SensitivitySeam {                                             <<SEAM>>
  # given an assembled problem at a SystemState operating point, perturb SystemState
  # and Scenario inputs, re-evaluate residuals and Result outputs, assemble sensitivities.
  linearize(problem: AssembledProblem, op: SystemState, inputs: Scenario)
      -> StateSpace   # (A, B, C, D) for MPC/ROM/surrogate
}
```

The DynamicSolver is an **additional DAG sink** touching nothing below it. The single Sensitivity/Linearisation seam unifies the Newton Jacobian, the implicit-dynamic Jacobian, and `(A,B,C,D)` extraction (`[F18]`): the ordered introspectable `SystemState` is the precondition, the **Scenario provides the input vector**, the **Result provides the output vector**.

---

# 14. Result Interface

Output unit, paired with its tuple, under the same single-source-of-truth rule (MASTER §15).

```
Result {                                                                <<FROZEN>>
  # --- stored (irreducible) ---
  converged_port_values: { PortId -> (P, h, mdot) }
  converged_internal_states: { (ComponentId, str) -> float[] }
  tuple_ref: TupleRef                  # by value or content-hash into the Reproducibility Tuple

  # --- derived on demand (NEVER stored redundantly) ---
  profiles() -> Profiles               # P, h, x, T, ρ along the loop, recomputed via FluidState
  heat_rejected() -> float
  outlet_quality() -> float
  subcooling() -> float
  pump_power() -> float

  # --- reported (first-class, ALWAYS present) ---
  invariants: ValidationInvariants     # energy/mass imbalance, pressure-closure residual, bound checks
  calibration_report: CalibrationReport
  validity_warnings: ValidityVerdict[] # any out-of-envelope correlation/HX call
  convergence: ConvergenceMetadata
  predictive_or_calibrated: (PREDICTIVE | CALIBRATED)   # from CalibrationMode
}

ValidationInvariants {
  energy_imbalance: float
  mass_imbalance: float
  pressure_closure_residual: float
  bound_checks: BoundCheck[]           # 0 ≤ x ≤ 1, T < T_crit, ...
}
```

- **Stored = minimal:** only converged `(P, h, mdot)`, converged internal states, and a tuple reference. **Profiles/T/x/ρ are derived** (recomputed from stored `(P, h)` through FluidState) — never persisted beside `(P, h)` (anti-pattern §16).
- **A Result without** energy-imbalance, mass-imbalance, pressure-closure, quality-bounds, and calibration-report fields is **malformed** (Rule 5).
- **Predictive vs calibrated flag** is mandatory: a `CALIBRATED` result is never compared as-equal to a `PREDICTIVE` one.
- The schema is **versioned and minimal** (`SCHEMA_SPEC.md`) so a 5-year-old surrogate dataset stays interpretable; the `(Scenario in tuple) → (invariants + outputs in Result)` mapping is the surrogate training pair.

---

# 15. Reproducibility Tuple Interface

The serialized input unit (`[F1]` Principle 7, MASTER §15). **A run is fully determined by it; no result depends on anything outside it.** Serializable, **versioned**, immutable.

```
ReproducibilityTuple {                                                  <<FROZEN structure>>
  topology:             TopologySpec          # components + connections + junctions + branch structure
  component_parameters: { ComponentId -> ParamSet }
  geometries:           { ComponentId -> Geometry }      # immutable typed value objects (§5)
  fluid:                { FluidIdentity -> backend_name } # identity + backend selection (§3)
  correlation_selections: { (ComponentId, role) -> correlation_name }
  hx_model_selections:  { ComponentId -> hx_model_name }   # heat-exchanger strategy (§8)
  accumulator_law_selections: { ComponentId -> volume_pressure_law_name }   # PCA/HCA/bellows/... (§11.6)
  calibration:          CalibrationReport      # factors: target, value, mode, seam (§9)
  scenario:             Scenario               # the five-part operating point (§10)
  solver_settings:      SolverSettings
  schema_version:       str                    # versioned; SCHEMA_SPEC.md owns the bytes
}
```

- **Includes every selection seam:** backend per fluid, correlation per slot, **HX model per heat-exchanger component**, **accumulator pressure law per accumulator** — so swapping any model is a tuple edit (Rule 4). (The `hx_model_selections` and `accumulator_law_selections` fields are additions implied by Refinement notes 2 & 3 — see §17.)
- **Geometry and Scenario are immutable** (§5, §10); varying either yields a new tuple — the DOE unit.
- **`schema_version`** is mandatory; serialization bytes and migration are owned by `SCHEMA_SPEC.md`, not here.
- A `Result` references its tuple by value or content-hash (§14); the pair is the atomic reproducible record.

---

# 16. Interface Anti-Patterns

Each ties to the guard that forbids it (MASTER §19, extended for this spec).

1. **State on Port objects** — storing/caching `(P, h, mdot)` or derived properties on a Port. *Guard:* Port is connectivity only (§4.1); SystemState holds unknowns; `PortState`/`FlowState` are retired.
2. **Stored derived properties** — caching `T`/`ρ`/`x` beside `(P, h)`, or a Result persisting profiles. *Guard:* only `P, h, mdot` + internal states stored (§3.2, §14); FluidState derives the rest.
3. **Hidden state / cached closures** — `_last_dP`, `_last_Q`, module globals, run-on-import. *Guard:* Rule 2; correlations and components are stateless (§7, §11).
4. **Correlation knowing component/geometry-type/topology/solver** — `if in_evaporator`, `hasattr(self, ...)`, `_fluid_name` globals, hard-coded `M=102`. *Guard:* role-typed input, pure closure (§7.1).
5. **Correlation receiving a whole Component/Geometry/State object** — instead of `FluidState` + declared scalars. *Guard:* the Component builds a role-typed `CorrelationInput` (§7.2).
6. **Miscategorising ε-NTU/LMTD as a correlation** — putting a heat-exchanger solution strategy in the correlation role set/registry. *Guard:* `HeatExchangerModel` is a separate concept with its own registry (§8).
7. **Calibration hidden inside a correlation or scaling a balance** — a fudge factor in a formula, or `R*` on gravity/continuity. *Guard:* calibration is an explicit value object applied at the output seam, friction-gradient/HTC/UA only, always reported (§9).
8. **Accumulator geometry carrying the pressure law** — `V_gas_charge`/spring rate/bellows area stored in geometry; or the accumulator storing `P_sys`. *Guard:* geometry = containment only; law is a swappable slot; stored state is `V_g`, `P` derived (§5.4, §11.6).
9. **Mesh in Geometry** — segment/zone count in the immutable Geometry. *Guard:* state count owned by Discretization, derived from but never stored in Geometry (§5, §6).
10. **Geometry hierarchy creep** — a base `Geometry` growing fields/optionals; a single `Δz` hard-wired so trajectories can't extend. *Guard:* flat typed family; `PipePath` typed for extension (§5.1).
11. **Geometry computing physics** — Geometry returning `Nu`/`ΔP`. *Guard:* dimensional accessors allowed, correlation outputs forbidden (§5).
12. **PropertyBackend in the correlation registry** — CoolProp as a slot correlation. *Guard:* Layer-1 citizen, separate registry, no geometry/slots (§3.3, §3.4).
13. **Scenario folded into component parameters** — heat load / sink T / gravity as fixed component attributes. *Guard:* Scenario is first-class, five-part, the primary DOE axis, bound-to but separate-from components (§10).
14. **Component reaching outside itself** — naming the Network, a neighbour, another branch's flow, or the Solver/its scheme. *Guard:* `contribute` consumes only handed-in trial state + its own slots (§11.1); branch closure is a Network condition (§12).
15. **Solver reached into out-of-band** — anything depending on the Solver; a component picking a timestep or knowing it is Newton-iterated; the solver calling `accumulator.set_pressure()` directly. *Guard:* nothing depends on the Solver; the reference is Network wiring; the contract is residual/derivative only (§11, §12, §13).
16. **Result as a bag of stored numbers** — persisting invariants-free or profile-laden results. *Guard:* minimal stored state + mandatory reported invariants/calibration (§14).
17. **Promising AD through the property layer** — building a gradient path on AD through CoolProp. *Guard:* FD-primary, analytic-where-available, AD-not-promised (§13.3).
18. **Speculative generality** — plugin system, event bus, DI container, abstract-primitive component, or over-generalizing the pipe trajectory / accumulator law beyond two concrete cases. *Guard:* abstraction only when two concrete cases demand it; v1 trajectory is a single `StraightSegment`, extension seams declared but unbuilt (§5.1, Principle 6).

---

# 17. Required Architecture Master Amendments

> **Status: APPLIED — reconciled into `ARCHITECTURE_MASTER.md`.** Amendments A1–A6 below have been applied to the master (§2, §8, §10, §12, §15, §18) and recorded in `DECISION_LOG.md` Decision 010. They are retained here as the traceability record of what changed; **do not re-apply them.** "§17 amendment" cross-references in `CORRELATION_CONTRACT.md` and `SCHEMA_SPEC.md` should be read as "reconciled in the master."

The following amendments to `ARCHITECTURE_MASTER.md` were **required to keep the master consistent with this interface review.** Each is a clarification or correction implied by the four refinement notes — none reopens a frozen decision; they refine how a frozen decision is expressed.

**A1 — Pipe geometry / trajectory (Refinement note 1).**
- §8 (`PipeGeometry {L, D_h, A, roughness, Δz}`) and §2 concept table: amend so the elevation descriptor is a **`PipePath`/trajectory field** of which a single straight `Δz` segment is the v1 default, not the only representable form. Add a sentence that horizontal/vertical/inclined/curved/multi-segment runs, bends, and fittings are additive `PipePath` families, and that **collectors and manifolds are Network topologies of pipe segments at Junctions, not a geometry field.** No change to "Geometry computes no physics."

**A2 — Accumulator as pressure-reference component; geometry ≠ law (Refinement note 2).**
- §8 `AccumulatorGeometry {V_total, V_gas_charge (PCA), heater/thermal (HCA)}`: amend to **`AccumulatorGeometry {V_total, containment, thermal?}` (containment only)** and **move `V_gas_charge` and all law parameters out of geometry into the `VolumePressureLaw` slot.** State explicitly that geometry and pressure law are separated and that **PCA, HCA, bellows, spring-loaded, and gas-charged** are interchangeable law bindings.
- §12 Accumulator row and §4.2 / `[F9]`: reword "the accumulator owns the volume↔pressure law" to "the accumulator is a **pressure-reference component**; its **geometry (containment) and pressure-reference law are separate**, the law is a swappable slot supporting PCA/HCA/bellows/spring/gas-charged."

**A3 — Heat-exchanger model is not a correlation role (Refinement note 3).**
- §10 enumerated role set: **remove `HeatExchangeMethodInput`** from the `CorrelationInput` role list.
- §12 Condenser row "heat-exchange-method (ε-NTU/LMTD) slot": reword to a **`HeatExchangerModel` slot** (a separate solution-strategy concept, §8 of this spec), distinct from HTC and ΔP correlation slots. Add `HeatExchangerModel` to the §2 concept inventory (or note it as a component-internal strategy, not a top-level primitive) and note that ε-NTU / LMTD / segmented-march / moving-boundary are its kinds.
- Optionally add a §2 "Not concepts" clarification distinguishing a *closure correlation* (one local value) from a *heat-exchanger model* (whole-exchanger solution consuming correlations).

**A4 — Scenario decomposition (Refinement note 4).**
- §2 concept #5 and §15: amend the Scenario definition to the **five-part structure** — `boundary_conditions`, `commands`, `disturbances`, `environment`, `operating_point` — and state that this decomposition is what DOE, surrogate generation, dynamic simulation, and future MPC each draw from. Keep gravity under `Environment`, `P_set` under `boundary_conditions`, pump/valve commands under `commands`.

**A5 — Reproducibility Tuple selection fields.**
- §15 tuple definition: add the two selection fields this spec introduces — **`hx_model_selections`** (per heat-exchanger component) and **`accumulator_law_selections`** (per accumulator) — alongside `correlation_selections`, so every swappable model is a named tuple binding.

**A6 — §18 cross-reference.**
- §18 (interface documents): note that `INTERFACE_SPEC.md` additionally specifies the **`HeatExchangerModel`** seam and the **Scenario five-part decomposition**, which were refinements integrated during interface specification, and that the master sections above should be reconciled to them.

---

*End of INTERFACE_SPEC.md — the interface and contract reference for the MPL simulation framework. Subordinate to ARCHITECTURE_MASTER.md; frozen contracts are tagged `<<FROZEN>>`, future seams `<<SEAM>>`. The amendments in §17 have been applied to the master and recorded in `DECISION_LOG.md` Decision 010. Next companions: SCHEMA_SPEC.md, CORRELATION_CONTRACT.md, TEST_PLAN_V1.md.*
