"""Geometry package — immutable typed scalar geometry primitives.

DAG layer 2.  Geometry is a flat family of value objects.

Architectural constraints:
- No mesh or segment count (belongs to Discretization, [F16]).
- No operating state (T, P, rho, h, mdot).
- No physics computation (Nu, Re, friction factor, HTC, pressure drop).
- No import of CoolProp, properties, correlations, components, calibration,
  network, or solvers.
"""

from mpl_sim.geometry.primitives import (
    AccumulatorGeometry,
    ContainmentSpec,
    FinGeometry,
    MicrochannelGeometry,
    PipeGeometry,
    PipePath,
    PipePathDerived,
    PlateGeometry,
    PortDimensions,
    StraightSegment,
    ThermalSpec,
)

__all__ = [
    "AccumulatorGeometry",
    "ContainmentSpec",
    "FinGeometry",
    "MicrochannelGeometry",
    "PipeGeometry",
    "PipePath",
    "PipePathDerived",
    "PlateGeometry",
    "PortDimensions",
    "StraightSegment",
    "ThermalSpec",
]
