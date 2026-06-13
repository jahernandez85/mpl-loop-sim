"""Immutable geometry primitives — Phase 4A.

Geometry is a flat family of typed, immutable scalar value objects.

Architectural constraints enforced here:
- No mesh or segment count (belongs to Discretization, [F16]).
- No operating state (T, P, rho, h, mdot).
- No physics computation: no Nu, Re, friction factor, HTC, pressure drop.
- No import of CoolProp, properties, correlations, components, calibration,
  network, or solvers.

Permitted: simple dimensional derived accessors (total length, dz/dx)
derived purely from primitive scalar dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# PipePath primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipePathDerived:
    """Read-only derived scalars exposed by any PipePath via derived()."""

    L_total: float
    dz_dx_profile: float  # scalar for straight path; dimensionless elevation gradient
    sum_minor_K: float  # sum of minor-loss coefficients; 0.0 in V1


@dataclass(frozen=True)
class StraightSegment:
    """A single straight pipe run described by length, elevation change, and inclination.

    Inclination (angle from horizontal, degrees) defaults to 0.0.  The primary
    elevation datum is delta_z; dz/dx is derived geometrically, not from inclination.
    """

    length: float
    delta_z: float
    inclination: float = 0.0

    def __post_init__(self) -> None:
        if self.length <= 0:
            raise ValueError(f"StraightSegment.length must be > 0; got {self.length!r}")

    def derived(self) -> PipePathDerived:
        """Return dimensional derived scalars for this segment.

        No physics computed here — dz/dx is a pure geometric ratio.
        No fittings in V1, so sum_minor_K is always 0.0.
        """
        return PipePathDerived(
            L_total=self.length,
            dz_dx_profile=self.delta_z / self.length,
            sum_minor_K=0.0,
        )


# V1: MultiSegmentPath is a <<SEAM>>, not yet implemented.
# When added: PipePath = Union[StraightSegment, MultiSegmentPath]
PipePath = StraightSegment


# ---------------------------------------------------------------------------
# PipeGeometry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PipeGeometry:
    """Immutable geometric description of a pipe passage.

    All fields are pure physical scalars plus a trajectory descriptor.
    No mesh, no operating state, no physics outputs.
    """

    L: float  # flow length [m]
    D_h: float  # hydraulic diameter [m]
    A: float  # flow cross-sectional area [m²]
    roughness: float  # absolute wall roughness [m]
    trajectory: StraightSegment  # PipePath for V1

    def __post_init__(self) -> None:
        if self.L <= 0:
            raise ValueError(f"PipeGeometry.L must be > 0; got {self.L!r}")
        if self.D_h <= 0:
            raise ValueError(f"PipeGeometry.D_h must be > 0; got {self.D_h!r}")
        if self.A <= 0:
            raise ValueError(f"PipeGeometry.A must be > 0; got {self.A!r}")
        if self.roughness < 0:
            raise ValueError(f"PipeGeometry.roughness must be >= 0; got {self.roughness!r}")


# ---------------------------------------------------------------------------
# AccumulatorGeometry — containment only, no pressure-law parameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContainmentSpec:
    """Vessel/port geometry for the accumulator; law-agnostic.

    Describes the physical container only.  Pressure-law parameters
    (V_gas_charge, polytropic_index, spring_rate, bellows_area, …) are not
    here; they belong to the VolumePressureLaw slot.
    """

    inner_diameter: float  # vessel inner diameter [m]
    height: float  # vessel internal height [m]

    def __post_init__(self) -> None:
        if self.inner_diameter <= 0:
            raise ValueError(
                f"ContainmentSpec.inner_diameter must be > 0; got {self.inner_diameter!r}"
            )
        if self.height <= 0:
            raise ValueError(f"ContainmentSpec.height must be > 0; got {self.height!r}")


@dataclass(frozen=True)
class ThermalSpec:
    """Optional thermal sub-spec for accumulator laws that require heater or wall data (HCA)."""

    heater_power: float  # maximum heater power [W]
    wall_area: float  # effective heater/wall area [m²]

    def __post_init__(self) -> None:
        if self.heater_power < 0:
            raise ValueError(f"ThermalSpec.heater_power must be >= 0; got {self.heater_power!r}")
        if self.wall_area <= 0:
            raise ValueError(f"ThermalSpec.wall_area must be > 0; got {self.wall_area!r}")


@dataclass(frozen=True)
class AccumulatorGeometry:
    """Containment-only geometry for a pressure-reference accumulator.

    Must not contain law parameters such as V_gas_charge, charge_pressure,
    polytropic_index, spring_rate, bellows_area, gas_constant, P_set, V_g,
    or P_sys.  Those belong to the VolumePressureLaw / accumulator component.
    """

    V_total: float  # total vessel volume [m³]
    containment: ContainmentSpec
    thermal: ThermalSpec | None = None

    def __post_init__(self) -> None:
        if self.V_total <= 0:
            raise ValueError(f"AccumulatorGeometry.V_total must be > 0; got {self.V_total!r}")


# ---------------------------------------------------------------------------
# PlateGeometry — plate heat-exchanger condenser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PortDimensions:
    """Port / nozzle geometry for a plate heat exchanger."""

    diameter: float  # port diameter [m]

    def __post_init__(self) -> None:
        if self.diameter <= 0:
            raise ValueError(f"PortDimensions.diameter must be > 0; got {self.diameter!r}")


@dataclass(frozen=True)
class PlateGeometry:
    """Immutable geometry for a plate heat exchanger (condenser)."""

    N_plates: int
    chevron_angle: float  # corrugation angle from horizontal [deg]
    plate_spacing: float  # gap between plates [m]
    port_dims: PortDimensions
    A_per_plate: float  # effective flow area per plate [m²]
    sink_side: str | None = None  # optional annotation (e.g. "refrigerant" / "water")

    def __post_init__(self) -> None:
        if self.N_plates < 1:
            raise ValueError(f"PlateGeometry.N_plates must be >= 1; got {self.N_plates!r}")
        if self.plate_spacing <= 0:
            raise ValueError(f"PlateGeometry.plate_spacing must be > 0; got {self.plate_spacing!r}")
        if self.A_per_plate <= 0:
            raise ValueError(f"PlateGeometry.A_per_plate must be > 0; got {self.A_per_plate!r}")


# ---------------------------------------------------------------------------
# MicrochannelGeometry — microchannel heat-exchanger evaporator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinGeometry:
    """Fin geometry for a microchannel heat exchanger."""

    fin_pitch: float  # fins per metre [1/m]
    fin_height: float  # fin height [m]
    fin_thickness: float  # fin wall thickness [m]

    def __post_init__(self) -> None:
        if self.fin_pitch <= 0:
            raise ValueError(f"FinGeometry.fin_pitch must be > 0; got {self.fin_pitch!r}")
        if self.fin_height <= 0:
            raise ValueError(f"FinGeometry.fin_height must be > 0; got {self.fin_height!r}")
        if self.fin_thickness <= 0:
            raise ValueError(f"FinGeometry.fin_thickness must be > 0; got {self.fin_thickness!r}")


@dataclass(frozen=True)
class MicrochannelGeometry:
    """Immutable geometry for a microchannel evaporator.

    Exposes wall_mass and wall_material for the frozen dynamic
    wall-capacitance internal state (INTERFACE_SPEC §5.3).
    """

    N_channels: int
    D_h_channel: float  # hydraulic diameter of one channel [m]
    fin_geometry: FinGeometry
    A_heated: float  # total heated area [m²]
    wall_mass: float  # total wall mass [kg]
    wall_material: str  # material identifier (e.g. "aluminium")

    def __post_init__(self) -> None:
        if self.N_channels < 1:
            raise ValueError(
                f"MicrochannelGeometry.N_channels must be >= 1; got {self.N_channels!r}"
            )
        if self.D_h_channel <= 0:
            raise ValueError(
                f"MicrochannelGeometry.D_h_channel must be > 0; got {self.D_h_channel!r}"
            )
        if self.A_heated <= 0:
            raise ValueError(f"MicrochannelGeometry.A_heated must be > 0; got {self.A_heated!r}")
        if self.wall_mass <= 0:
            raise ValueError(f"MicrochannelGeometry.wall_mass must be > 0; got {self.wall_mass!r}")
