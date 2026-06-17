"""hx_models package — Phase 11: HeatExchangerModel strategies.

Exports:
  Kind enumeration:
    HeatExchangerModelKind

  Secondary-fluid BCs:
    SinkInletTempAndFlow, FixedWallTemp, FixedHeatRate, AmbientCoupling
    SecondaryFluidBC  (union type alias)

  Request / result:
    HXSolveRequest, HXSolveResult

  Abstract base:
    HeatExchangerModel

  Registry:
    HeatExchangerModelRegistry, create_empty_hx_model_registry

  Concrete strategies:
    EpsilonNTUModel
    LMTDModel
    SegmentedMarchModel

  Cell-profile value objects (SegmentedMarchModel):
    SegmentedCellRecord
    SegmentedProfile

Architectural constraints:
  - MUST NOT import from network/ or solvers/.
  - MUST NOT import CoolProp.
  - MUST NOT import properties/.
  - MUST NOT import components/.
"""

from mpl_sim.hx_models.base import (
    AmbientCoupling,
    FixedHeatRate,
    FixedWallTemp,
    HeatExchangerModel,
    HeatExchangerModelKind,
    HXSolveRequest,
    HXSolveResult,
    SecondaryFluidBC,
    SinkInletTempAndFlow,
    UnsupportedHeatExchangerBoundaryConditionError,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel
from mpl_sim.hx_models.lmtd import LMTDModel
from mpl_sim.hx_models.registry import (
    HeatExchangerModelRegistry,
    create_empty_hx_model_registry,
)
from mpl_sim.hx_models.segmented import (
    SegmentedCellRecord,
    SegmentedMarchModel,
    SegmentedProfile,
)

__all__ = [
    # Kind
    "HeatExchangerModelKind",
    # Secondary BCs
    "SinkInletTempAndFlow",
    "FixedWallTemp",
    "FixedHeatRate",
    "AmbientCoupling",
    "SecondaryFluidBC",
    # Request / result
    "HXSolveRequest",
    "HXSolveResult",
    # Abstract base
    "HeatExchangerModel",
    # Exceptions
    "UnsupportedHeatExchangerBoundaryConditionError",
    # Registry
    "HeatExchangerModelRegistry",
    "create_empty_hx_model_registry",
    # Concrete strategies
    "EpsilonNTUModel",
    "LMTDModel",
    "SegmentedMarchModel",
    # Cell-profile value objects
    "SegmentedCellRecord",
    "SegmentedProfile",
]
