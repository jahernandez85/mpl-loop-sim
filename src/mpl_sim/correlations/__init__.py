# Phase 3: Correlation contract, roles, registry
# Phase 10G: VolumePressureLaw (PCA) added
# Phase 11L: single-phase HTC correlations (Dittus-Boelter, Gnielinski) added
# Phase 11M: two-phase HTC correlations (ShahBoilingHTC, YanCondensationHTC) added
# MUST NOT import from components/, network/, or solvers/.

from mpl_sim.correlations.contract import (
    AnyFluid,
    Bound,
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationInput,
    CorrelationOutput,
    CorrelationRole,
    CriticalHeatFluxInput,
    EnvelopeRef,
    FlowRegimeInput,
    FlowRegimeLabel,
    FlowRegimeVerdict,
    FluidClass,
    FluidClassSpec,
    FluidFamilySpec,
    HTCInput,
    NamedFluids,
    SinglePhaseDPInput,
    SourceRef,
    ThermalSpec,
    TwoPhaseDPInput,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
    VoidFractionInput,
    VolumePressureLawInput,
)
from mpl_sim.correlations.registry import (
    CorrelationRegistry,
    create_empty_correlation_registry,
)
from mpl_sim.correlations.single_phase_dp import ChurchillFrictionGradient
from mpl_sim.correlations.single_phase_htc import DittusBoelterHTC, GnielinskiHTC
from mpl_sim.correlations.two_phase_htc import ShahBoilingHTC, YanCondensationHTC
from mpl_sim.correlations.volume_pressure_law import PcaVolumePressureLaw

__all__ = [
    "CorrelationRegistry",
    "ChurchillFrictionGradient",
    "DittusBoelterHTC",
    "GnielinskiHTC",
    "ShahBoilingHTC",
    "YanCondensationHTC",
    "PcaVolumePressureLaw",
    "create_empty_correlation_registry",
    "AnyFluid",
    "Bound",
    "BoundedQuantity",
    "ClosureMetadata",
    "Correlation",
    "CorrelationInput",
    "CorrelationOutput",
    "CorrelationRole",
    "CriticalHeatFluxInput",
    "EnvelopeRef",
    "FlowRegimeInput",
    "FlowRegimeLabel",
    "FlowRegimeVerdict",
    "FluidClass",
    "FluidClassSpec",
    "FluidFamilySpec",
    "HTCInput",
    "NamedFluids",
    "SinglePhaseDPInput",
    "SourceRef",
    "ThermalSpec",
    "TwoPhaseDPInput",
    "ValidityEnvelope",
    "ValidityStatus",
    "ValidityVerdict",
    "VoidFractionInput",
    "VolumePressureLawInput",
]
