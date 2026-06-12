"""PropertyBackend interface — Phase 2A.

Defines the abstract contract that all property engines must satisfy.
CoolProp, REFPROP, tabulated, and empirical backends all implement this
interface; none are implemented here.

Key architectural decisions ([F6], [F13], INTERFACE_SPEC §3.3):
- Vector-first: query() accepts and returns numpy arrays; scalar is length-1.
- Capability-flagged: a backend advertises what it provides; callers check
  provides() before relying on optional properties.
- No extrapolation by stealth: out-of-range inputs yield OUT_OF_RANGE status
  and NaN values, never a fabricated in-range result.
- CoolProp is NEVER imported in this file; that happens only in
  coolprop_backend.py (Phase 2B).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np
import numpy.typing as npt

from mpl_sim.core.fluid_identity import FluidIdentity

# ---------------------------------------------------------------------------
# PropertyName — the closed, versioned set of derivable thermodynamic
# quantities (INTERFACE_SPEC §3.3, ARCHITECTURE_MASTER §5/§6).
# ---------------------------------------------------------------------------


class PropertyName(Enum):
    """Symbolic names for every derived thermodynamic property.

    These are the quantities FluidState can supply when a PropertyBackend is
    provided.  None of them are stored on FluidState itself ([F3]).
    """

    T = "T"  # temperature                         [K]
    T_SAT = "T_sat"  # saturation temperature at P         [K]
    X = "x"  # vapour quality                      [-]  0=sat. liq, 1=sat. vap
    RHO = "rho"  # density                             [kg/m³]
    MU = "mu"  # dynamic viscosity                   [Pa·s]
    K = "k"  # thermal conductivity                [W/(m·K)]
    SIGMA = "sigma"  # surface tension                     [N/m]
    CP = "cp"  # specific heat at constant pressure  [J/(kg·K)]
    PHASE = "phase"  # phase label (see PhaseLabel)        [-]
    H_F = "h_f"  # saturated-liquid enthalpy at P      [J/kg]
    H_G = "h_g"  # saturated-vapour enthalpy at P      [J/kg]
    H_FG = "h_fg"  # latent heat  h_g - h_f              [J/kg]

    # Electrical / dielectric (table-only; CoolProp does not provide these)
    SIGMA_E = "sigma_e"  # electrical conductivity         [S/m]
    EPS_R = "eps_r"  # relative permittivity           [-]

    # First derivatives (optional, behind DERIVATIVES capability)
    DRHO_DP_H = "drho_dP_h"  # ∂ρ/∂P|h   [kg/(m³·Pa)]
    DRHO_DH_P = "drho_dh_P"  # ∂ρ/∂h|P   [kg·m³/J·m³] → [kg²/(m³·J)]


# ---------------------------------------------------------------------------
# PhaseLabel — the discrete phase descriptor returned when PropertyName.PHASE
# is queried.  The backend maps its own internal phase flag to one of these.
# ---------------------------------------------------------------------------


class PhaseLabel(Enum):
    """Thermodynamic phase of the fluid at (P, h)."""

    LIQUID = auto()
    TWO_PHASE = auto()
    VAPOR = auto()
    SUPERCRITICAL = auto()
    UNKNOWN = auto()


# ---------------------------------------------------------------------------
# BackendCapability — flags that backends advertise and callers check.
# (INTERFACE_SPEC §3.3, [F13]-4)
# ---------------------------------------------------------------------------


class BackendCapability(Enum):
    """Capabilities a PropertyBackend may advertise via provides()."""

    DERIVATIVES = auto()
    """Backend can return first derivatives (∂ρ/∂P|h, ∂ρ/∂h|P, …)."""

    SURFACE_TENSION = auto()
    """Backend can return σ (sigma) via PropertyName.SIGMA."""

    ELECTRICAL_CONDUCTIVITY = auto()
    """Backend can return σ_e (sigma_e); table-only, not in CoolProp."""

    RELATIVE_PERMITTIVITY = auto()
    """Backend can return ε_r (eps_r); table-only, not in CoolProp."""

    SATURATION_PROPERTIES = auto()
    """Backend can return h_f, h_g, h_fg, T_sat at arbitrary P."""

    VECTOR_QUERIES = auto()
    """Backend can handle array inputs of length > 1 natively (all v1 backends must)."""


# ---------------------------------------------------------------------------
# QueryStatus — per-element status codes in a PropertyResult.
# ---------------------------------------------------------------------------


class QueryStatus(Enum):
    """Element-wise outcome of a property query."""

    OK = auto()
    """Value is valid and in-range."""

    UNAVAILABLE = auto()
    """The backend does not support this property (provides() returned False)."""

    OUT_OF_RANGE = auto()
    """Input (P, h) lies outside the backend's valid range; value is NaN."""


# ---------------------------------------------------------------------------
# PropertyResult — the status-bearing return from query().
# (INTERFACE_SPEC §3.3: "never a bare float[]")
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PropertyResult:
    """Return value from PropertyBackend.query().

    Attributes
    ----------
    values:
        Computed property values, one per input point.  Elements that are
        UNAVAILABLE or OUT_OF_RANGE carry NaN.
    status:
        Per-element status code.  Always the same length as *values*.
    warning:
        Optional human-readable description of any non-OK conditions.
    """

    values: npt.NDArray[np.float64]
    status: tuple[QueryStatus, ...]
    warning: str | None = None

    def __post_init__(self) -> None:
        if len(self.values) != len(self.status):
            raise ValueError(
                f"PropertyResult: values length {len(self.values)} != "
                f"status length {len(self.status)}"
            )

    @classmethod
    def unavailable(cls, n: int, warning: str | None = None) -> PropertyResult:
        """Factory: *n* UNAVAILABLE elements, all NaN."""
        return cls(
            values=np.full(n, np.nan),
            status=tuple(QueryStatus.UNAVAILABLE for _ in range(n)),
            warning=warning,
        )

    @classmethod
    def out_of_range(cls, n: int, warning: str | None = None) -> PropertyResult:
        """Factory: *n* OUT_OF_RANGE elements, all NaN."""
        return cls(
            values=np.full(n, np.nan),
            status=tuple(QueryStatus.OUT_OF_RANGE for _ in range(n)),
            warning=warning,
        )

    @classmethod
    def ok(cls, values: npt.NDArray[np.float64]) -> PropertyResult:
        """Factory: all elements OK."""
        return cls(
            values=values,
            status=tuple(QueryStatus.OK for _ in range(len(values))),
        )


# ---------------------------------------------------------------------------
# ValidRange — optional range envelope that backends may expose.
# (INTERFACE_SPEC §3.3: valid_range(identity) -> RangeEnvelope)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidRange:
    """Pressure–enthalpy envelope within which a backend's data are reliable.

    Values are inclusive bounds in SI units (Pa, J/kg).
    A value of None means "unbounded / unknown in that direction".
    """

    P_min: float | None = None  # [Pa]
    P_max: float | None = None  # [Pa]
    h_min: float | None = None  # [J/kg]
    h_max: float | None = None  # [J/kg]


# ---------------------------------------------------------------------------
# PropertyBackend — the abstract interface every property engine implements.
# (INTERFACE_SPEC §3.3, [F6], [F13])
# ---------------------------------------------------------------------------


class PropertyBackend(ABC):
    """Abstract contract for a thermodynamic property engine.

    All methods are vector-first: P and h are 1-D numpy arrays; the scalar
    case is length-1.  Subclasses must not break this contract.

    No physics is implemented here.  This class is purely structural.
    """

    # ------------------------------------------------------------------
    # Primary query
    # ------------------------------------------------------------------

    @abstractmethod
    def query(
        self,
        prop: PropertyName,
        P: npt.NDArray[np.float64],
        h: npt.NDArray[np.float64],
        identity: FluidIdentity,
    ) -> PropertyResult:
        """Return the requested property at each (P[i], h[i]) point.

        Parameters
        ----------
        prop:
            Which thermodynamic quantity to compute.
        P:
            Pressure array [Pa], length n.
        h:
            Specific-enthalpy array [J/kg], length n.
        identity:
            Which fluid to evaluate.

        Returns
        -------
        PropertyResult
            *values* and *status* of length n.
            Elements that fall outside the valid range carry status
            OUT_OF_RANGE and value NaN.
            Unsupported properties carry status UNAVAILABLE and value NaN.
        """

    # ------------------------------------------------------------------
    # Optional derivative query (behind DERIVATIVES capability)
    # ------------------------------------------------------------------

    @abstractmethod
    def query_derivative(
        self,
        prop: PropertyName,
        P: npt.NDArray[np.float64],
        h: npt.NDArray[np.float64],
        identity: FluidIdentity,
    ) -> PropertyResult:
        """Return the first derivative of *prop* at each (P, h) point.

        Only meaningful when provides(BackendCapability.DERIVATIVES) is True.
        Backends that do not support derivatives must return UNAVAILABLE for
        every element rather than raising.

        Supported derivative names are a subset of PropertyName:
        DRHO_DP_H and DRHO_DH_P.
        """

    # ------------------------------------------------------------------
    # Capability introspection
    # ------------------------------------------------------------------

    @abstractmethod
    def provides(self, cap: BackendCapability) -> bool:
        """Return True if this backend supports *cap*.

        Callers must check this before relying on optional properties.
        A backend that returns False for a capability must return
        UNAVAILABLE (not raise) when that property is queried.
        """

    # ------------------------------------------------------------------
    # Range introspection
    # ------------------------------------------------------------------

    @abstractmethod
    def valid_range(self, identity: FluidIdentity) -> ValidRange:
        """Return the (P, h) envelope within which this backend is reliable.

        Points outside this envelope will receive OUT_OF_RANGE status from
        query().  The envelope is fluid-specific.
        """
