"""Components package -- Phase 11D: Evaporator and Condenser foundations added.

Exports:
  Component contract primitives:
    ComponentId, ComponentKind, ComponentPort, Component

  Pipe (with Phase 6B friction, Phase 6C gravity, Phase 6D acceleration,
        Phase 6E mechanical summary):
    Pipe, PipeSinglePhaseFrictionInput, PipeFrictionResult,
    PipeGravityInput, PipeGravityResult,
    PipeAccelerationInput, PipeAccelerationResult,
    PipeMechanicalPressureInput, PipeMechanicalPressureSummary

  Pump (Phase 10A/10B/10F):
    PumpComponent, PumpGeometry,
    PumpOperatingPoint, PumpHydraulicSummary,
    PumpMapPoint, PumpPerformanceMap,
    PumpSpeedCommand, PumpFlowTarget,
    PumpPowerInput, PumpPowerSummary

  Accumulator (Phase 10C/10D/10H):
    AccumulatorComponent, AccumulatorOperatingPoint, AccumulatorPressureSummary,
    VolumePressureLawBinding, AccumulatorVolumePressureSummary

  Evaporator (Phase 11C):
    EvaporatorComponent, EvaporatorHXInput

  Condenser (Phase 11D):
    CondenserComponent, CondenserHXInput

Architectural constraints:
  - MUST NOT import from network/ or solvers/.
  - MUST NOT import CoolProp.
  - MUST NOT import properties/.
"""

from mpl_sim.components.accumulator import (
    AccumulatorComponent,
    AccumulatorOperatingPoint,
    AccumulatorPressureSummary,
    AccumulatorVolumePressureSummary,
    VolumePressureLawBinding,
)
from mpl_sim.components.base import (
    Component,
    ComponentId,
    ComponentKind,
    ComponentPort,
)
from mpl_sim.components.condenser import CondenserComponent, CondenserHXInput
from mpl_sim.components.evaporator import EvaporatorComponent, EvaporatorHXInput
from mpl_sim.components.pipe import (
    Pipe,
    PipeAccelerationInput,
    PipeAccelerationResult,
    PipeFrictionResult,
    PipeGravityInput,
    PipeGravityResult,
    PipeMechanicalPressureInput,
    PipeMechanicalPressureSummary,
    PipeSinglePhaseFrictionInput,
)
from mpl_sim.components.pump import (
    PumpComponent,
    PumpFlowTarget,
    PumpGeometry,
    PumpHydraulicSummary,
    PumpMapPoint,
    PumpOperatingPoint,
    PumpPerformanceMap,
    PumpPowerInput,
    PumpPowerSummary,
    PumpSpeedCommand,
)

__all__ = [
    # Identity primitives
    "ComponentId",
    "ComponentKind",
    # Port declaration
    "ComponentPort",
    # Abstract base
    "Component",
    # Pipe + Phase 6B friction types
    "Pipe",
    "PipeSinglePhaseFrictionInput",
    "PipeFrictionResult",
    # Pipe Phase 6C gravity types
    "PipeGravityInput",
    "PipeGravityResult",
    # Pipe Phase 6D acceleration types
    "PipeAccelerationInput",
    "PipeAccelerationResult",
    # Pipe Phase 6E mechanical summary types
    "PipeMechanicalPressureInput",
    "PipeMechanicalPressureSummary",
    # Pump Phase 10A/10B/10F
    "PumpComponent",
    "PumpGeometry",
    "PumpOperatingPoint",
    "PumpHydraulicSummary",
    "PumpMapPoint",
    "PumpPerformanceMap",
    "PumpSpeedCommand",
    "PumpFlowTarget",
    "PumpPowerInput",
    "PumpPowerSummary",
    # Accumulator Phase 10C/10D/10H
    "AccumulatorComponent",
    "AccumulatorOperatingPoint",
    "AccumulatorPressureSummary",
    "VolumePressureLawBinding",
    "AccumulatorVolumePressureSummary",
    # Evaporator Phase 11C
    "EvaporatorComponent",
    "EvaporatorHXInput",
    # Condenser Phase 11D
    "CondenserComponent",
    "CondenserHXInput",
]
