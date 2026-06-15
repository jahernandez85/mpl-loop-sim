"""Calibration package — Phase 5A: value objects and registry seams.

DAG Layer 4. Data-only calibration primitives that future components will
consume when applying modifiers to correlation outputs.

Architectural constraints:
- No import of CoolProp, properties, correlations, geometry, discretization,
  components, network, or solvers.
- No thermodynamic state stored or computed.
- No parameter estimation or optimization.
"""

from mpl_sim.calibration.primitives import (
    CalibrationFactor,
    CalibrationMode,
    CalibrationModifier,
    CalibrationModifierKind,
    CalibrationReport,
    CalibrationScope,
    CalibrationSet,
    CalibrationTarget,
    CalibrationTargetId,
    CalibrationTargetKind,
    SeamLocation,
)
from mpl_sim.calibration.registry import CalibrationRegistry

__all__ = [
    "CalibrationFactor",
    "CalibrationMode",
    "CalibrationModifier",
    "CalibrationModifierKind",
    "CalibrationRegistry",
    "CalibrationReport",
    "CalibrationScope",
    "CalibrationSet",
    "CalibrationTarget",
    "CalibrationTargetId",
    "CalibrationTargetKind",
    "SeamLocation",
]
