"""CoolPropBackend — CoolProp 7.x wrapper implementing PropertyBackend.

This is the ONLY module in the mpl_sim package that may import CoolProp.
([F6], ARCHITECTURE_MASTER §3, IMPLEMENTATION_PLAN §21-6)
"""

from __future__ import annotations

import CoolProp.CoolProp as CP
import numpy as np
import numpy.typing as npt

from mpl_sim.core.fluid_identity import FluidIdentity, PureFluid
from mpl_sim.properties.backend import (
    BackendCapability,
    PhaseLabel,
    PropertyBackend,
    PropertyName,
    PropertyResult,
    QueryStatus,
    ValidRange,
)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_CAPABILITIES: frozenset[BackendCapability] = frozenset(
    {
        BackendCapability.VECTOR_QUERIES,
        BackendCapability.SATURATION_PROPERTIES,
        BackendCapability.SURFACE_TENSION,
    }
)

# CoolProp integer phase codes → PhaseLabel
_IPHASE_TO_LABEL: dict[int, PhaseLabel] = {
    0: PhaseLabel.LIQUID,  # iphase_liquid
    1: PhaseLabel.SUPERCRITICAL,  # iphase_supercritical
    2: PhaseLabel.SUPERCRITICAL,  # iphase_supercritical_gas
    3: PhaseLabel.SUPERCRITICAL,  # iphase_supercritical_liquid
    5: PhaseLabel.VAPOR,  # iphase_gas
    6: PhaseLabel.TWO_PHASE,  # iphase_twophase
}

# Properties evaluated on the saturation curve (use PQ_INPUTS, ignore h)
_SAT_PROPS: frozenset[PropertyName] = frozenset(
    {
        PropertyName.H_F,
        PropertyName.H_G,
        PropertyName.H_FG,
        PropertyName.T_SAT,
        PropertyName.SIGMA,
    }
)

# Properties CoolProp cannot provide at all
_UNSUPPORTED_PROPS: frozenset[PropertyName] = frozenset(
    {
        PropertyName.SIGMA_E,
        PropertyName.EPS_R,
    }
)


# ---------------------------------------------------------------------------
# CoolPropBackend
# ---------------------------------------------------------------------------


class CoolPropBackend(PropertyBackend):
    """PropertyBackend backed by CoolProp 7.x HEOS equations of state.

    Only PureFluid identities are supported.  Mixture and CustomFluid return
    UNAVAILABLE rather than raising.  Derivatives are not implemented and
    return UNAVAILABLE.
    """

    # ------------------------------------------------------------------
    # Capability flags
    # ------------------------------------------------------------------

    def provides(self, cap: BackendCapability) -> bool:
        return cap in _CAPABILITIES

    # ------------------------------------------------------------------
    # Valid range
    # ------------------------------------------------------------------

    def valid_range(self, identity: FluidIdentity) -> ValidRange:
        # Coarse CoolProp-derived envelope; not a precision thermodynamic domain certificate.
        if not isinstance(identity, PureFluid):
            return ValidRange()
        try:
            st = CP.AbstractState("HEOS", identity.name)
            T_min = float(st.Tmin())
            T_max = float(st.Tmax())
            P_max = float(st.pmax())
            # Triple-point pressure requires a prior state update on some builds
            st.update(CP.QT_INPUTS, 0.0, T_min)
            P_min = float(st.keyed_output(CP.iP_triple))
            h_min = float(st.hmass())  # saturated liquid at T_min
            # h_max: superheated vapour at atmospheric pressure, maximum T
            st.update(CP.PT_INPUTS, 101325.0, T_max)
            h_max = float(st.hmass())
            return ValidRange(P_min=P_min, P_max=P_max, h_min=h_min, h_max=h_max)
        except Exception:
            return ValidRange()

    # ------------------------------------------------------------------
    # Primary query
    # ------------------------------------------------------------------

    def query(
        self,
        prop: PropertyName,
        P: npt.NDArray[np.float64],
        h: npt.NDArray[np.float64],
        identity: FluidIdentity,
    ) -> PropertyResult:
        if len(P) != len(h):
            raise ValueError(
                f"P and h must have the same length; got len(P)={len(P)}, len(h)={len(h)}"
            )
        n = len(P)

        if not isinstance(identity, PureFluid):
            return PropertyResult.unavailable(
                n,
                warning="CoolPropBackend supports PureFluid only; got Mixture or CustomFluid",
            )

        if prop in _UNSUPPORTED_PROPS:
            return PropertyResult.unavailable(
                n, warning=f"{prop.name} is not available from CoolProp"
            )

        if prop in _SAT_PROPS:
            return self._query_saturation(prop, P, n, identity.name)

        return self._query_state(prop, P, h, n, identity.name)

    # ------------------------------------------------------------------
    # Derivative query — not implemented, returns UNAVAILABLE
    # ------------------------------------------------------------------

    def query_derivative(
        self,
        prop: PropertyName,
        P: npt.NDArray[np.float64],
        h: npt.NDArray[np.float64],
        identity: FluidIdentity,
    ) -> PropertyResult:
        return PropertyResult.unavailable(
            len(P), warning="CoolPropBackend does not support derivatives"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query_state(
        self,
        prop: PropertyName,
        P: npt.NDArray[np.float64],
        h: npt.NDArray[np.float64],
        n: int,
        fluid_name: str,
    ) -> PropertyResult:
        """Evaluate *prop* at each (h[i], P[i]) via HmassP_INPUTS."""
        values = np.empty(n, dtype=np.float64)
        statuses: list[QueryStatus] = [QueryStatus.OK] * n
        warnings: list[str] = []

        try:
            st = CP.AbstractState("HEOS", fluid_name)
        except Exception as exc:
            return PropertyResult.unavailable(n, warning=f"CoolProp init error: {exc}")

        for i in range(n):
            try:
                st.update(CP.HmassP_INPUTS, float(h[i]), float(P[i]))
                val, status = _eval_state_prop(st, prop)
                values[i] = val
                statuses[i] = status
            except Exception:
                values[i] = np.nan
                statuses[i] = QueryStatus.OUT_OF_RANGE
                warnings.append(f"point {i}: P={P[i]:.3g} h={h[i]:.3g}")

        warning = "Out of range: " + "; ".join(warnings) if warnings else None
        return PropertyResult(values=values, status=tuple(statuses), warning=warning)

    def _query_saturation(
        self,
        prop: PropertyName,
        P: npt.NDArray[np.float64],
        n: int,
        fluid_name: str,
    ) -> PropertyResult:
        """Evaluate saturation-curve property at each P[i] via PQ_INPUTS."""
        values = np.empty(n, dtype=np.float64)
        statuses: list[QueryStatus] = [QueryStatus.OK] * n
        warnings: list[str] = []

        try:
            st = CP.AbstractState("HEOS", fluid_name)
        except Exception as exc:
            return PropertyResult.unavailable(n, warning=f"CoolProp init error: {exc}")

        for i in range(n):
            try:
                values[i] = _eval_sat_prop(st, prop, float(P[i]))
            except Exception:
                values[i] = np.nan
                statuses[i] = QueryStatus.OUT_OF_RANGE
                warnings.append(f"point {i}: P={P[i]:.3g}")

        warning = "Out of saturation range: " + "; ".join(warnings) if warnings else None
        return PropertyResult(values=values, status=tuple(statuses), warning=warning)


# ---------------------------------------------------------------------------
# Point-level evaluation helpers (module-private)
# ---------------------------------------------------------------------------


def _eval_state_prop(st: CP.AbstractState, prop: PropertyName) -> tuple[float, QueryStatus]:
    """Extract one property value from an already-updated AbstractState."""
    if prop == PropertyName.T:
        return float(st.T()), QueryStatus.OK
    if prop == PropertyName.RHO:
        return float(st.rhomass()), QueryStatus.OK
    if prop == PropertyName.MU:
        return float(st.viscosity()), QueryStatus.OK
    if prop == PropertyName.K:
        return float(st.conductivity()), QueryStatus.OK
    if prop == PropertyName.CP:
        return float(st.cpmass()), QueryStatus.OK
    if prop == PropertyName.X:
        q = float(st.Q())
        if q < 0.0:  # CoolProp sentinel: -1 for single-phase states
            return np.nan, QueryStatus.UNAVAILABLE
        return q, QueryStatus.OK
    if prop == PropertyName.PHASE:
        label = _IPHASE_TO_LABEL.get(st.phase(), PhaseLabel.UNKNOWN)
        return float(label.value), QueryStatus.OK
    return np.nan, QueryStatus.UNAVAILABLE


def _eval_sat_prop(st: CP.AbstractState, prop: PropertyName, P: float) -> float:
    """Evaluate a saturation-curve property at pressure *P*."""
    if prop == PropertyName.SIGMA:
        st.update(CP.PQ_INPUTS, P, 0.0)
        return float(st.surface_tension())
    if prop == PropertyName.T_SAT:
        st.update(CP.PQ_INPUTS, P, 0.0)
        return float(st.T())
    if prop == PropertyName.H_F:
        st.update(CP.PQ_INPUTS, P, 0.0)
        return float(st.hmass())
    if prop == PropertyName.H_G:
        st.update(CP.PQ_INPUTS, P, 1.0)
        return float(st.hmass())
    if prop == PropertyName.H_FG:
        st.update(CP.PQ_INPUTS, P, 0.0)
        h_f = float(st.hmass())
        st.update(CP.PQ_INPUTS, P, 1.0)
        return float(st.hmass()) - h_f
    raise ValueError(f"_eval_sat_prop: {prop!r} is not a saturation property")
