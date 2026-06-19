"""HeatExchangerModel contract primitives — Phase 11A/B.

Defines:
  HeatExchangerModelKind  — closed kind enumeration
  PrimaryThermalMode      — explicit primary-side thermal assumption for ε-NTU
  UAComputationMode       — explicit UA computation mode for ε-NTU
  SecondaryFluidBC family — discriminated BCs for the secondary side
  HXSolveRequest          — immutable solve request passed to a HX model
  HXSolveResult           — immutable result returned by a HX model
  HeatExchangerModel      — abstract base for all HX strategies

Architectural constraints enforced here:
  - No import of CoolProp, properties/, components/, network/, or solvers/.
  - No registry access at solve time.
  - No hidden default model selection.
  - HXSolveRequest does not construct PropertyBackend instances.
  - All objects are immutable.
  - No derived properties stored on results.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, auto
from types import MappingProxyType

from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import Correlation, CorrelationOutput
from mpl_sim.discretization.primitives import DiscretizationSpec

# ---------------------------------------------------------------------------
# HeatExchangerModelKind
# ---------------------------------------------------------------------------


class HeatExchangerModelKind(Enum):
    """Closed kind enumeration for heat-exchanger solution strategies.

    EPSILON_NTU     — lumped effectiveness-NTU method (V1 implemented)
    LMTD            — log-mean-temperature-difference method (declared seam)
    SEGMENTED_MARCH — forward march over discrete cells (declared seam)
    MOVING_BOUNDARY — moving-boundary two-phase model (declared seam)
    """

    EPSILON_NTU = auto()
    LMTD = auto()
    SEGMENTED_MARCH = auto()
    MOVING_BOUNDARY = auto()


# ---------------------------------------------------------------------------
# PrimaryThermalMode / UAComputationMode
# ---------------------------------------------------------------------------


class PrimaryThermalMode(Enum):
    """Explicit primary-side thermal assumption for ε-NTU calculations.

    FINITE_CAPACITY      — primary stream has a finite single-phase heat-capacity
                           rate; primary_cp must be supplied in HXSolveRequest.
    CONSTANT_TEMPERATURE — primary stream undergoes isothermal phase change;
                           C_primary → ∞, Cr = 0; primary_cp must be None.
    """

    FINITE_CAPACITY = auto()
    CONSTANT_TEMPERATURE = auto()


class UAComputationMode(Enum):
    """Explicit mode for computing the overall UA in ε-NTU calculations.

    TWO_SIDED    — series thermal resistance: 1/UA = 1/(h_p·A) + 1/(h_s·A);
                   htc_primary and htc_secondary must both be present.
    PRIMARY_ONLY — UA = h_primary · A_ht; secondary HTC not used for UA;
                   htc_primary must be present.
    """

    TWO_SIDED = auto()
    PRIMARY_ONLY = auto()


# ---------------------------------------------------------------------------
# SecondaryFluidBC family
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SinkInletTempAndFlow:
    """Secondary-fluid BC: known inlet temperature and mass flow.

    T_in           : secondary-fluid inlet temperature [K] — must be finite and > 0
    mdot_secondary : secondary-fluid mass flow rate [kg/s] — must be finite and > 0
    cp_secondary   : secondary-fluid specific heat [J/kg/K] — must be finite and > 0
    """

    T_in: float
    mdot_secondary: float
    cp_secondary: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.T_in) or self.T_in <= 0:
            raise ValueError(f"SinkInletTempAndFlow.T_in must be finite and > 0; got {self.T_in!r}")
        if not math.isfinite(self.mdot_secondary) or self.mdot_secondary <= 0:
            raise ValueError(
                f"SinkInletTempAndFlow.mdot_secondary must be finite and > 0; "
                f"got {self.mdot_secondary!r}"
            )
        if not math.isfinite(self.cp_secondary) or self.cp_secondary <= 0:
            raise ValueError(
                f"SinkInletTempAndFlow.cp_secondary must be finite and > 0; "
                f"got {self.cp_secondary!r}"
            )


@dataclass(frozen=True)
class FixedWallTemp:
    """Secondary-fluid BC: constant wall temperature.

    T_wall : prescribed wall temperature [K] — must be finite and > 0
    """

    T_wall: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.T_wall) or self.T_wall <= 0:
            raise ValueError(f"FixedWallTemp.T_wall must be finite and > 0; got {self.T_wall!r}")


@dataclass(frozen=True)
class FixedHeatRate:
    """Secondary-fluid BC: prescribed total heat transfer rate.

    Q : heat added to the primary fluid [W]
        Positive Q means the primary fluid gains enthalpy (evaporator sense).
        Negative Q means the primary fluid rejects heat (condenser sense).
        Must be finite.
    """

    Q: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.Q):
            raise ValueError(f"FixedHeatRate.Q must be finite; got {self.Q!r}")


@dataclass(frozen=True)
class AmbientCoupling:
    """Secondary-fluid BC: ambient heat exchange with known UA.

    T_ambient  : ambient temperature [K] — must be finite and > 0
    UA_ambient : overall heat-transfer conductance to ambient [W/K]
                 must be finite and > 0
    """

    T_ambient: float
    UA_ambient: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.T_ambient) or self.T_ambient <= 0:
            raise ValueError(
                f"AmbientCoupling.T_ambient must be finite and > 0; got {self.T_ambient!r}"
            )
        if not math.isfinite(self.UA_ambient) or self.UA_ambient <= 0:
            raise ValueError(
                f"AmbientCoupling.UA_ambient must be finite and > 0; got {self.UA_ambient!r}"
            )


SecondaryFluidBC = SinkInletTempAndFlow | FixedWallTemp | FixedHeatRate | AmbientCoupling


# ---------------------------------------------------------------------------
# HXSolveRequest
# ---------------------------------------------------------------------------


def _empty_geom_scalars() -> dict[str, float]:
    return {}


@dataclass(frozen=True)
class HXSolveRequest:
    """Immutable solve request for a HeatExchangerModel.

    The caller assembles this object from local component data and passes it to
    HeatExchangerModel.solve().  The model never resolves registries internally.

    Fields
    ------
    primary_state_in   : fluid state at the primary-side inlet (P, h, identity)
    primary_mdot       : primary-side mass flow rate [kg/s]; must be finite and > 0
    secondary_bc       : boundary condition on the secondary side
    geometry           : geometry object (PlateGeometry, MicrochannelGeometry, ...)
                         passed through to the model; the model extracts scalars as needed
    discretization     : discretization specification (LUMPED for V1)
    geom_scalars       : flat scalar bag forwarded to correlation inputs
                         (e.g. "G", "D_h", "roughness", "L_cell", "rho", "mu")
    htc_primary        : optional injected HTC correlation (primary side)
    htc_secondary      : optional injected HTC correlation (secondary side)
    dp_primary         : optional injected DP correlation (primary side)
    htc_multiplier     : calibration multiplier applied to primary HTC output; >= 0; default 1.0
    friction_multiplier: calibration multiplier applied to DP/friction output; >= 0; default 1.0
    primary_T_in           : optional precomputed primary-side inlet temperature [K]
                             required by SinkInletTempAndFlow BC; must be finite and > 0
    primary_cp             : optional precomputed primary-side specific heat [J/kg/K]
                             required when primary_thermal_mode is FINITE_CAPACITY
    primary_thermal_mode   : explicit primary-side thermal assumption for ε-NTU;
                             required for SinkInletTempAndFlow BC
    ua_computation_mode    : explicit UA computation mode for ε-NTU;
                             required for SinkInletTempAndFlow BC
    q_flux_primary         : optional explicit wall heat flux [W/m²] for the primary side;
                             required by flux-dependent boiling HTC closures
                             (e.g. ShahBoilingHTC); passed unchanged to HTCInput.q_flux;
                             must be finite and > 0 if supplied; zero, negative, NaN,
                             and infinite values are rejected; no abs(), no clipping,
                             no hidden fallback
    dp_primary_is_two_phase: when True the HX model builds TwoPhaseDPInput for dp_primary
                             and multiplies the Pa/m gradient output by L_cell to obtain
                             a pressure drop in Pa.  When False (default) the model builds
                             SinglePhaseDPInput and treats value[0] as Pa directly
                             (existing single-phase behaviour).  Ignored when dp_primary
                             is None.  No auto-detection by correlation class is performed.

    Validation
    ----------
    - primary_mdot must be finite and strictly positive.
    - htc_multiplier and friction_multiplier must be finite and >= 0.
    - primary_T_in, if supplied, must be finite and > 0.
    - primary_cp, if supplied, must be finite and > 0.
    - q_flux_primary, if supplied, must be finite and strictly positive.
    - FINITE_CAPACITY mode requires primary_cp to be explicitly supplied.
    - TWO_SIDED mode requires htc_primary and htc_secondary to be supplied.
    - PRIMARY_ONLY mode requires htc_primary to be supplied.
    - geom_scalars is converted to an immutable MappingProxyType on construction.
    """

    primary_state_in: FluidState
    primary_mdot: float
    secondary_bc: SecondaryFluidBC
    geometry: object
    discretization: DiscretizationSpec
    geom_scalars: Mapping[str, float] = field(default_factory=_empty_geom_scalars)
    htc_primary: Correlation | None = None
    htc_secondary: Correlation | None = None
    dp_primary: Correlation | None = None
    htc_multiplier: float = 1.0
    friction_multiplier: float = 1.0
    primary_T_in: float | None = None
    primary_cp: float | None = None
    primary_thermal_mode: PrimaryThermalMode | None = None
    ua_computation_mode: UAComputationMode | None = None
    q_flux_primary: float | None = None
    dp_primary_is_two_phase: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(self.primary_mdot) or self.primary_mdot <= 0:
            raise ValueError(
                f"HXSolveRequest.primary_mdot must be finite and > 0; " f"got {self.primary_mdot!r}"
            )
        if not math.isfinite(self.htc_multiplier) or self.htc_multiplier < 0:
            raise ValueError(
                f"HXSolveRequest.htc_multiplier must be finite and >= 0; "
                f"got {self.htc_multiplier!r}"
            )
        if not math.isfinite(self.friction_multiplier) or self.friction_multiplier < 0:
            raise ValueError(
                f"HXSolveRequest.friction_multiplier must be finite and >= 0; "
                f"got {self.friction_multiplier!r}"
            )
        if self.primary_T_in is not None:
            if not math.isfinite(self.primary_T_in) or self.primary_T_in <= 0:
                raise ValueError(
                    f"HXSolveRequest.primary_T_in must be finite and > 0; "
                    f"got {self.primary_T_in!r}"
                )
        if self.primary_cp is not None:
            if not math.isfinite(self.primary_cp) or self.primary_cp <= 0:
                raise ValueError(
                    f"HXSolveRequest.primary_cp must be finite and > 0; " f"got {self.primary_cp!r}"
                )
        if self.q_flux_primary is not None:
            if not math.isfinite(self.q_flux_primary) or self.q_flux_primary <= 0:
                raise ValueError(
                    f"HXSolveRequest.q_flux_primary must be finite and > 0 when supplied; "
                    f"got {self.q_flux_primary!r}. "
                    f"Zero, negative, NaN, and infinite values are not accepted. "
                    f"Supply the correct positive heat flux."
                )
        if self.primary_thermal_mode is PrimaryThermalMode.FINITE_CAPACITY:
            if self.primary_cp is None:
                raise ValueError(
                    "HXSolveRequest: primary_cp is required when primary_thermal_mode "
                    "is PrimaryThermalMode.FINITE_CAPACITY"
                )
        if self.ua_computation_mode is UAComputationMode.TWO_SIDED:
            if self.htc_primary is None:
                raise ValueError(
                    "HXSolveRequest: htc_primary is required when ua_computation_mode "
                    "is UAComputationMode.TWO_SIDED"
                )
            if self.htc_secondary is None:
                raise ValueError(
                    "HXSolveRequest: htc_secondary is required when ua_computation_mode "
                    "is UAComputationMode.TWO_SIDED"
                )
        if self.ua_computation_mode is UAComputationMode.PRIMARY_ONLY:
            if self.htc_primary is None:
                raise ValueError(
                    "HXSolveRequest: htc_primary is required when ua_computation_mode "
                    "is UAComputationMode.PRIMARY_ONLY"
                )
        if self.primary_thermal_mode is PrimaryThermalMode.CONSTANT_TEMPERATURE:
            if self.primary_cp is not None:
                raise ValueError(
                    "HXSolveRequest: primary_cp must be None when primary_thermal_mode "
                    "is PrimaryThermalMode.CONSTANT_TEMPERATURE"
                )
        if isinstance(self.secondary_bc, SinkInletTempAndFlow):
            if self.primary_T_in is None:
                raise ValueError(
                    "HXSolveRequest: primary_T_in is required when secondary_bc is "
                    "SinkInletTempAndFlow"
                )
            if self.primary_thermal_mode is None:
                raise ValueError(
                    "HXSolveRequest: primary_thermal_mode is required when secondary_bc is "
                    "SinkInletTempAndFlow"
                )
            if self.ua_computation_mode is None:
                raise ValueError(
                    "HXSolveRequest: ua_computation_mode is required when secondary_bc is "
                    "SinkInletTempAndFlow"
                )
        object.__setattr__(self, "geom_scalars", MappingProxyType(dict(self.geom_scalars)))


# ---------------------------------------------------------------------------
# HXSolveResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HXSolveResult:
    """Immutable result from HeatExchangerModel.solve().

    Fields
    ------
    primary_state_out   : fluid state at the primary-side outlet (P, h, identity)
                          computed transiently; never stored on a Port
    Q                   : total heat transferred to primary fluid [W]
                          positive = primary gains enthalpy; negative = rejects heat
    dP_primary          : pressure drop across the primary side [Pa] (calibrated)
    verdicts            : raw CorrelationOutput from every called correlation
    htc_multiplier      : HTC multiplier that was applied (for calibration traceability)
    friction_multiplier : friction/DP multiplier that was applied
    raw_dP_primary      : pre-calibration DP value [Pa] (for seam inspectability)
    zone_profile        : optional zone/cell profile (declared seam; None in V1)
    """

    primary_state_out: FluidState
    Q: float
    dP_primary: float
    verdicts: tuple[CorrelationOutput, ...]
    htc_multiplier: float = 1.0
    friction_multiplier: float = 1.0
    raw_dP_primary: float = 0.0
    zone_profile: object | None = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class UnsupportedHeatExchangerBoundaryConditionError(NotImplementedError):
    """Raised when a HeatExchangerModel receives a BC it has not implemented.

    Subclasses NotImplementedError so existing callers that catch
    NotImplementedError are unaffected, while precise callers can catch this
    specific type to distinguish unsupported-BC from other not-implemented cases.
    """


# ---------------------------------------------------------------------------
# HeatExchangerModel — abstract base
# ---------------------------------------------------------------------------


class HeatExchangerModel(ABC):
    """Abstract base for all heat-exchanger solution strategies.

    A concrete model is a stateless strategy object: it must not resolve
    registries, access Ports, Network, Solver, or SystemState, and must
    not construct PropertyBackend instances.

    Two calls with equal HXSolveRequest objects must return equivalent results.
    """

    @abstractmethod
    def kind(self) -> HeatExchangerModelKind:
        """Return the kind of this HX model."""

    @abstractmethod
    def solve(self, req: HXSolveRequest) -> HXSolveResult:
        """Solve the heat-exchanger problem described by *req*.

        Parameters
        ----------
        req : HXSolveRequest

        Returns
        -------
        HXSolveResult
        """
