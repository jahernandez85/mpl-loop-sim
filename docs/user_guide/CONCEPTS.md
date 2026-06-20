# Core Concepts

This document explains the key abstractions in `mpl-loop-sim` and how they fit together.
Audience: researchers, PhD engineers, thermal-system model developers, future maintainers.

---

## Fluid State

```python
from mpl_sim.core import FluidState, PureFluid

fluid = PureFluid(name="R134a")
state = FluidState(P=800_000.0, h=250_000.0, identity=fluid)
```

`FluidState` is an immutable triple: `(P [Pa], h [J/kg], identity)`.

**It carries no derived properties.** Saturation temperature, density, viscosity, quality — none of these are fields on `FluidState`. If a correlation needs them, the caller supplies them explicitly through `geom_scalars`.

This is an intentional architectural decision (`[F3]`): derived properties must not be stored on state objects.

---

## Secondary Boundary Conditions

A `SecondaryFluidBC` describes what the secondary side does to the primary stream.

| BC class | Meaning | Required fields |
|---|---|---|
| `FixedHeatRate(Q)` | Prescribe total heat transfer [W]; Q > 0 heats primary. | `Q` |
| `SinkInletTempAndFlow(T_in, mdot_secondary, cp_secondary)` | Finite-capacity secondary stream enters at T_in. | `T_in` [K], `mdot_secondary` [kg/s], `cp_secondary` [J/kg/K] |
| `FixedWallTemp(T_wall)` | Primary convects to/from a wall at fixed temperature. | `T_wall` [K] (requires `htc_primary`, `A_ht`, `primary_T_in`) |
| `AmbientCoupling(T_ambient, UA_ambient)` | Primary loses/gains heat to ambient. | `T_ambient` [K], `UA_ambient` [W/K] |

Sign convention: `Q > 0` always means the primary stream gains heat (evaporator direction). `Q < 0` means the primary stream rejects heat (condenser direction).

---

## HX Model Strategies

An `HeatExchangerModel` computes `Q` and `dP_primary` from a `HXSolveRequest`.

```
HXSolveRequest  ─►  HeatExchangerModel.solve()  ─►  HXSolveResult
```

Three strategies are implemented:

| Strategy | Supported BCs | Notes |
|---|---|---|
| `EpsilonNTUModel` | All four | Lumped ε-NTU; stateless; no registry. |
| `LMTDModel` | `FixedWallTemp`, `AmbientCoupling` | Limited foundation; two-stream LMTD solving deferred. |
| `SegmentedMarchModel` | All four | Cell-by-cell enthalpy march; supports co-current and counterflow (one-pass or iterated). |

`HXSolveRequest` carries the inlet state, mass flow, secondary BC, geometry, discretization, and all injected correlations. `HXSolveResult` carries Q, outlet state, dP, `ValidityVerdict` records, and (for segmented paths) a `SegmentedProfile`.

---

## Correlations

A `Correlation` is a pure function: explicit scalar inputs in, scalar outputs out.

```
CorrelationInput  ─►  Correlation.evaluate()  ─►  CorrelationOutput
```

Key design rules:
- A correlation receives one immutable, role-typed `CorrelationInput`, which may
  contain `FluidState` values and declared scalar data. It never receives a
  whole `Component`, `Geometry`, `SystemState`, network, or solver object
  (`[F4]`, `[F11]`).
- A correlation **never calls** CoolProp or `PropertyBackend` (`[F6]`).
- Calibration multipliers are **never inside** a correlation (`[F5]`); they are applied after the call, by the HX model.
- Out-of-envelope inputs return a `ValidityVerdict` with `status=EXTRAPOLATED`; they never silently clamp.

Active closures:

| Role | Symbol | Reference |
|---|---|---|
| Single-phase HTC | `DittusBoelterHTC` | Dittus & Boelter (1930) |
| Single-phase HTC | `GnielinskiHTC` | Gnielinski (1976) |
| Boiling HTC | `ShahBoilingHTC` | Shah (1982) |
| Condensation HTC | `YanCondensationHTC` | Yan, Lio & Lin (1999) |
| Single-phase DP | `ChurchillFrictionGradient` | Churchill (1977) |
| Two-phase DP | `MSHTwoPhaseFrictionGradient` | Müller-Steinhagen & Heck (1986) |
| Volume-pressure law | `PcaVolumePressureLaw` | — |

---

## Components

`EvaporatorComponent` and `CondenserComponent` are immutable wrappers holding
component identity, ports, and geometry.
They delegate physics to an injected `HeatExchangerModel`.

```python
from mpl_sim.components import EvaporatorComponent, EvaporatorScenarioBinding

# Component: holds identity, ports, and geometry; scenario physics is injected.
component = EvaporatorComponent(component_id=..., geometry=...)

# Scenario: binds BC, model, discretization, and optional correlations.
scenario = EvaporatorScenarioBinding(
    secondary_bc=FixedHeatRate(Q=1000.0),
    model=EpsilonNTUModel(),
    discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
)

result = component.evaluate_scenario(inlet_state, primary_mdot=0.05, scenario=scenario)
```

Components do not know the network or their neighbours (`[F7]`).

---

## geom_scalars

`geom_scalars` is a flat `dict[str, float]` that carries all physical scalars the caller wants to make available to correlations. It is passed as-is to `HXSolveRequest`; the HX model and correlations pick out the keys they need.

Common keys:

| Key | Meaning | Unit |
|---|---|---|
| `G` | Mass flux | kg/m²/s |
| `x` | Vapour quality | — (0 to 1) |
| `D_h` | Hydraulic diameter | m |
| `L_cell` | Cell length | m |
| `A_ht` | Heat transfer area | m² |
| `Re` | Reynolds number | — |
| `Pr` | Prandtl number | — |
| `k` | Thermal conductivity | W/m/K |
| `n` | Dittus-Boelter Pr exponent | — |
| `rho_l`, `rho_v` | Liquid/vapour density | kg/m³ |
| `mu_l`, `mu_v` | Liquid/vapour viscosity | Pa·s |

Missing required keys cause a `ValueError` with the key name in the message — no silent fallback.

---

## Segmented Counterflow Path

`SegmentedMarchModel` with `SinkInletTempAndFlow` + `FlowArrangement.COUNTERFLOW` + `CounterflowIterationConfig(enabled=True)` runs a bounded fixed-point iteration:

1. Primary marches forward cell by cell (cell 0 to n-1).
2. Secondary integrates backward from the opposite end (cell n-1 to cell 0).
3. Repeat until the secondary temperature profile converges.

`HXSolveResult` carries `converged`, `residual`, and `iteration_count`. Non-convergence returns `converged=False` and never raises silently.

Required `geom_scalars` for this path: `G`, `x`, `D_h`, `L_cell`, `A_ht`, and the HTC correlation's own scalars (e.g. `Re`, `Pr`, `k`, `n` for `DittusBoelterHTC`).

---

## What is NOT implemented

| Capability | Status |
|---|---|
| Full loop convergence | Deferred |
| Network flow-pressure solver | Deferred |
| Property lookup (CoolProp/REFPROP) in HX/component layers | Not in scope for these layers |
| Moving-boundary model | Deferred |
| Automatic phase inference | Not planned for this layer |
| Validation against experimental data | Deferred (Phase 12+ validation harness) |
| Dynamic/transient simulation | Deferred |
| Remaining boiling/condensation HTC closures | Deferred |
| Homogeneous/Cicchitti, Kim-Mudawar 2013 DP | Deferred |
