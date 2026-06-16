"""Accumulator component -- Phase 10D / 10H.

Defines the Accumulator component: an immutable value object that stores
AccumulatorGeometry (containment only), declares one bidirectional fluid port,
and exposes two evaluation seams:

Phase 10D:
- AccumulatorOperatingPoint: scalar input for prescribed pressure-reference law
- AccumulatorPressureSummary: result (p_ref, p_setpoint)
- AccumulatorComponent.evaluate_pressure_reference: p_ref = p_setpoint

Phase 10H:
- VolumePressureLawBinding: holds law_params (no geometry, no correlation stored)
- AccumulatorVolumePressureSummary: result (P_derived, V_g, output)
- AccumulatorComponent.internal_state_names: returns ("V_g",)
- AccumulatorComponent.evaluate_volume_pressure_law: builds VolumePressureLawInput,
  delegates to caller-supplied Correlation, returns summary

Hard constraints respected:
- No CoolProp.
- No PropertyBackend.
- Only mpl_sim.correlations.contract may be imported (not registry or any closure).
- No network / solver.
- No mutation of any object.
- No dynamic integration.
- No mass / energy balance.
- P_sys is never stored on the accumulator (architecture invariant).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.components.base import Component, ComponentId, ComponentKind
from mpl_sim.core.port import Port, PortId, PortRole
from mpl_sim.correlations.contract import (
    Correlation,
    CorrelationOutput,
    VolumePressureLawInput,
)
from mpl_sim.geometry.primitives import AccumulatorGeometry

# ---------------------------------------------------------------------------
# AccumulatorOperatingPoint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccumulatorOperatingPoint:
    """Scalar inputs for AccumulatorComponent.evaluate_pressure_reference.

    Fields:
        p_setpoint : prescribed system pressure reference [Pa]
                     must be finite and strictly positive (physical pressure)
    """

    p_setpoint: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.p_setpoint):
            raise ValueError(
                f"AccumulatorOperatingPoint.p_setpoint must be finite; " f"got {self.p_setpoint!r}"
            )
        if self.p_setpoint <= 0.0:
            raise ValueError(
                f"AccumulatorOperatingPoint.p_setpoint must be > 0 (physical pressure); "
                f"got {self.p_setpoint!r}"
            )


# ---------------------------------------------------------------------------
# AccumulatorPressureSummary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccumulatorPressureSummary:
    """Result of AccumulatorComponent.evaluate_pressure_reference.

    Fields:
        p_ref      : pressure reference returned by the accumulator [Pa]
        p_setpoint : setpoint value that was used [Pa]
    """

    p_ref: float
    p_setpoint: float


# ---------------------------------------------------------------------------
# Phase 10H -- VolumePressureLawBinding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VolumePressureLawBinding:
    """Holds law parameters for the volume-pressure law seam.

    Law parameters are scalar key/value pairs only -- no geometry objects,
    no Correlation stored here (the caller supplies the Correlation at
    evaluation time to keep the binding data-only).

    Fields:
        law_params : immutable mapping of parameter name -> float value.
                     E.g. {"charge_volume": 0.005, "charge_pressure": 1e6,
                            "polytropic_index": 1.4}
    """

    law_params: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "law_params", MappingProxyType(dict(self.law_params)))


# ---------------------------------------------------------------------------
# Phase 10H -- AccumulatorVolumePressureSummary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccumulatorVolumePressureSummary:
    """Result of AccumulatorComponent.evaluate_volume_pressure_law.

    Fields:
        P_derived : pressure derived by the law [Pa]; may be NaN if V_g invalid
        V_g       : gas volume used for evaluation [m3]
        output    : full CorrelationOutput (value, verdict, metadata)
    """

    P_derived: float
    V_g: float
    output: CorrelationOutput


# ---------------------------------------------------------------------------
# AccumulatorComponent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccumulatorComponent(Component):
    """Accumulator component -- pressure-reference and volume-pressure seams.

    An immutable component representing a pressure-reference accumulator.
    Stores containment geometry (no law parameters), declares one BIDIRECTIONAL
    fluid port, and exposes:

      evaluate_pressure_reference  -- Phase 10D prescribed-pressure law
      evaluate_volume_pressure_law -- Phase 10H PCA/HCA law seam

    P_sys is never stored on this object. The Network owns reference-node
    wiring; the Solver owns global consistency.

    Fields:
        component_id : stable identity for this component
        geometry     : AccumulatorGeometry -- containment only; law parameters
                       must NOT be stored here

    Must NOT:
        - call CoolProp, PropertyBackend
        - import mpl_sim.correlations.registry (only .contract is allowed)
        - reference Network or Solver
        - store P_sys or any dynamic inventory state
        - implement dynamic integration or mass / energy balance
        - mutate any object
    """

    component_id: ComponentId
    geometry: AccumulatorGeometry

    # ------------------------------------------------------------------
    # Component contract -- structural declarations
    # ------------------------------------------------------------------

    def kind(self) -> ComponentKind:
        """Returns ComponentKind.ACCUMULATOR."""
        return ComponentKind.ACCUMULATOR

    @property
    def fluid_port(self) -> Port:
        """Declared fluid port (BIDIRECTIONAL; peer=None before Network assembly)."""
        return Port(
            id=PortId(component_id=self.component_id.name, port_name="fluid"),
            owner=self.component_id.name,
            role=PortRole.BIDIRECTIONAL,
            peer=None,
        )

    def ports(self) -> tuple[Port, ...]:
        """Returns (fluid_port,) -- exactly one port in V1."""
        return (self.fluid_port,)

    def internal_state_names(self) -> tuple[str, ...]:
        """Named internal state: V_g (current gas volume, [m3])."""
        return ("V_g",)

    # ------------------------------------------------------------------
    # Phase 10D: prescribed pressure-reference law
    # ------------------------------------------------------------------

    def evaluate_pressure_reference(
        self,
        inp: AccumulatorOperatingPoint,
    ) -> AccumulatorPressureSummary:
        """Evaluate the prescribed pressure-reference law for this accumulator.

        Computes:
            p_ref = inp.p_setpoint

        Parameters
        ----------
        inp : AccumulatorOperatingPoint

        Returns
        -------
        AccumulatorPressureSummary
        """
        return AccumulatorPressureSummary(
            p_ref=inp.p_setpoint,
            p_setpoint=inp.p_setpoint,
        )

    # ------------------------------------------------------------------
    # Phase 10H: volume-pressure law seam
    # ------------------------------------------------------------------

    def evaluate_volume_pressure_law(
        self,
        binding: VolumePressureLawBinding,
        V_g: float,
        correlation: Correlation,
    ) -> AccumulatorVolumePressureSummary:
        """Evaluate the volume-pressure law for this accumulator.

        Builds a VolumePressureLawInput from the binding parameters and
        the caller-supplied V_g, then delegates to the supplied Correlation.
        The accumulator does not know which law is used -- the caller
        supplies any Correlation with VOLUME_PRESSURE_LAW role.

        Parameters
        ----------
        binding     : VolumePressureLawBinding holding law_params
        V_g         : current gas volume [m3]
        correlation : Correlation with VOLUME_PRESSURE_LAW role

        Returns
        -------
        AccumulatorVolumePressureSummary with P_derived, V_g, and full output
        """
        inp = VolumePressureLawInput(
            V_g=V_g,
            V_total=self.geometry.V_total,
            law_params=binding.law_params,
        )
        output = correlation.evaluate(inp)
        P_derived = output.value[0]
        return AccumulatorVolumePressureSummary(
            P_derived=P_derived,
            V_g=V_g,
            output=output,
        )
