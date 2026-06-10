# Legacy Code

This folder contains previous development attempts used only as technical reference.

The code in this folder is not part of the active library.

## Contents

- `A0_SS_v3_Stable/`: monolithic 1D steady-state simulator with axial marching, pressure-drop decomposition and R* calibration.
- `PyP2PL/`: previous component-based P2PL library attempt.
- `MPL_Simulator/`: previous MPL library attempt with fluid properties, correlations and loop components.

## Reuse Policy

Legacy code may be inspected for:
- equations
- validation cases
- numerical strategies
- correlation implementations
- example inputs

Legacy code should not be copied directly into `src/` without review and refactoring.