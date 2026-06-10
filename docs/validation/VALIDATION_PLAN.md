# Validation Plan

## Objective

Define the verification and validation strategy for the MPL simulation library.

## Validation Levels

### Level 1 — Unit Verification

Check individual equations and utility functions.

Examples:

- Fluid property calculations.
- Quality calculation.
- Void fraction.
- Friction factor.
- Energy balance.

### Level 2 — Component Verification

Validate each component independently.

Components:

- Pipe1D
- Pump
- AccumulatorSS
- Evaporator1D
- PlateCondenser1D
- Splitter
- Mixer

### Level 3 — Loop Verification

Validate complete loop closure.

Checks:

- Conservation of mass.
- Conservation of energy.
- Pressure closure around the loop.
- Pump curve and system curve intersection.
- Physical bounds on quality and temperature.

### Level 4 — Literature Validation

Compare against published data.

Possible references:

- Kokate and Park: microchannel evaporator and P2PL.
- Van Gerner: transient MPL formulation.
- Middelhuis: multi-evaporator CO2 loop.
- Truster: dynamic/control-oriented loop.
- Li: acetone MPL experiments.

### Level 5 — Experimental Validation

Compare against future experimental bench data.

Measurements:

- Pressure drop.
- Mass flow rate.
- Inlet/outlet temperatures.
- Wall temperatures.
- Heat load.
- Condenser heat rejection.

## Acceptance Criteria

Initial targets:

- Global energy imbalance below 1%.
- Pressure closure residual below 1%.
- Outlet quality within physical bounds.
- Component pressure-drop calibration factor reported when used.
- No hidden empirical correction factors.

## Calibration Policy

Calibration is allowed but must be explicit.

Allowed modes:

- `none`
- `target`

For pressure drop:

```text
ΔP_total = R* ΔP_friction + ΔP_gravity + ΔP_acceleration