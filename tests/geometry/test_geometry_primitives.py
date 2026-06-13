"""Phase 4A — immutable geometry primitive tests.

Validates:
- StraightSegment construction, immutability, derived accessors, validation.
- PipeGeometry construction, immutability, field purity, validation.
- AccumulatorGeometry construction, immutability, validation, no law parameters.
- PlateGeometry and MicrochannelGeometry basic construction.
- Import purity: geometry must not pull in CoolProp or higher-layer packages.
"""

from __future__ import annotations

import dataclasses

import pytest

from mpl_sim.geometry import (
    AccumulatorGeometry,
    ContainmentSpec,
    FinGeometry,
    MicrochannelGeometry,
    PipeGeometry,
    PipePathDerived,
    PlateGeometry,
    PortDimensions,
    StraightSegment,
    ThermalSpec,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def straight_seg() -> StraightSegment:
    return StraightSegment(length=5.0, delta_z=1.0, inclination=11.31)


@pytest.fixture()
def pipe_geom(straight_seg: StraightSegment) -> PipeGeometry:
    return PipeGeometry(
        L=5.0,
        D_h=0.01,
        A=7.854e-5,
        roughness=1.5e-5,
        trajectory=straight_seg,
    )


@pytest.fixture()
def containment() -> ContainmentSpec:
    return ContainmentSpec(inner_diameter=0.15, height=0.40)


@pytest.fixture()
def acc_geom(containment: ContainmentSpec) -> AccumulatorGeometry:
    return AccumulatorGeometry(V_total=0.005, containment=containment)


# ---------------------------------------------------------------------------
# StraightSegment
# ---------------------------------------------------------------------------


class TestStraightSegment:
    def test_construction(self, straight_seg: StraightSegment) -> None:
        assert straight_seg.length == 5.0
        assert straight_seg.delta_z == 1.0
        assert straight_seg.inclination == pytest.approx(11.31)

    def test_immutable(self, straight_seg: StraightSegment) -> None:
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            straight_seg.length = 99.0  # type: ignore[misc]

    def test_derived_is_pipe_path_derived(self, straight_seg: StraightSegment) -> None:
        assert isinstance(straight_seg.derived(), PipePathDerived)

    def test_derived_total_length_equals_length(self, straight_seg: StraightSegment) -> None:
        assert straight_seg.derived().L_total == straight_seg.length

    def test_derived_dz_dx_consistent_with_delta_z_over_length(
        self, straight_seg: StraightSegment
    ) -> None:
        d = straight_seg.derived()
        assert d.dz_dx_profile == pytest.approx(straight_seg.delta_z / straight_seg.length)

    def test_dz_dx_zero_for_horizontal(self) -> None:
        seg = StraightSegment(length=3.0, delta_z=0.0)
        assert seg.derived().dz_dx_profile == 0.0

    def test_sum_minor_k_defaults_zero(self, straight_seg: StraightSegment) -> None:
        assert straight_seg.derived().sum_minor_K == 0.0

    def test_default_inclination_is_zero(self) -> None:
        seg = StraightSegment(length=2.0, delta_z=0.0)
        assert seg.inclination == 0.0

    def test_rejects_zero_length(self) -> None:
        with pytest.raises(ValueError, match="length"):
            StraightSegment(length=0.0, delta_z=0.0)

    def test_rejects_negative_length(self) -> None:
        with pytest.raises(ValueError, match="length"):
            StraightSegment(length=-1.0, delta_z=0.0)

    def test_negative_delta_z_allowed(self) -> None:
        seg = StraightSegment(length=5.0, delta_z=-2.0)
        assert seg.derived().dz_dx_profile == pytest.approx(-0.4)


# ---------------------------------------------------------------------------
# PipeGeometry
# ---------------------------------------------------------------------------

_PIPE_FORBIDDEN_ATTRS = [
    # discretization / mesh
    "N",
    "mesh",
    "cells",
    "n_cells",
    "n_segments",
    # operating state / flow quantities
    "pressure",
    "enthalpy",
    "mdot",
    "m_dot",
    "mass_flow",
    "rho",
    "density",
    "mu",
    "viscosity",
    # physics outputs
    "Re",
    "reynolds",
    "reynolds_number",
    "f",
    "friction_factor",
    "dP",
    "delta_P",
    "pressure_drop",
    "HTC",
    "htc",
    "heat_transfer_coefficient",
    "Nu",
    "nusselt",
    "nusselt_number",
]


class TestPipeGeometry:
    def test_construction(self, pipe_geom: PipeGeometry) -> None:
        assert pipe_geom.L == 5.0
        assert pipe_geom.D_h == 0.01
        assert pipe_geom.A == pytest.approx(7.854e-5)
        assert pipe_geom.roughness == pytest.approx(1.5e-5)

    def test_immutable(self, pipe_geom: PipeGeometry) -> None:
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            pipe_geom.L = 99.0  # type: ignore[misc]

    def test_stores_only_physical_fields_and_path(self, pipe_geom: PipeGeometry) -> None:
        field_names = {f.name for f in dataclasses.fields(pipe_geom)}
        assert field_names == {"L", "D_h", "A", "roughness", "trajectory"}

    def test_trajectory_is_straight_segment(self, pipe_geom: PipeGeometry) -> None:
        assert isinstance(pipe_geom.trajectory, StraightSegment)

    def test_rejects_non_positive_L(self) -> None:
        seg = StraightSegment(length=1.0, delta_z=0.0)
        with pytest.raises(ValueError, match="L"):
            PipeGeometry(L=0.0, D_h=0.01, A=1e-4, roughness=0.0, trajectory=seg)
        with pytest.raises(ValueError, match="L"):
            PipeGeometry(L=-1.0, D_h=0.01, A=1e-4, roughness=0.0, trajectory=seg)

    def test_rejects_non_positive_D_h(self) -> None:
        seg = StraightSegment(length=1.0, delta_z=0.0)
        with pytest.raises(ValueError, match="D_h"):
            PipeGeometry(L=1.0, D_h=0.0, A=1e-4, roughness=0.0, trajectory=seg)
        with pytest.raises(ValueError, match="D_h"):
            PipeGeometry(L=1.0, D_h=-0.01, A=1e-4, roughness=0.0, trajectory=seg)

    def test_rejects_non_positive_area(self) -> None:
        seg = StraightSegment(length=1.0, delta_z=0.0)
        with pytest.raises(ValueError, match="A"):
            PipeGeometry(L=1.0, D_h=0.01, A=0.0, roughness=0.0, trajectory=seg)
        with pytest.raises(ValueError, match="A"):
            PipeGeometry(L=1.0, D_h=0.01, A=-1e-4, roughness=0.0, trajectory=seg)

    def test_rejects_negative_roughness(self) -> None:
        seg = StraightSegment(length=1.0, delta_z=0.0)
        with pytest.raises(ValueError, match="roughness"):
            PipeGeometry(L=1.0, D_h=0.01, A=1e-4, roughness=-0.001, trajectory=seg)

    def test_allows_zero_roughness(self) -> None:
        seg = StraightSegment(length=1.0, delta_z=0.0)
        g = PipeGeometry(L=1.0, D_h=0.01, A=1e-4, roughness=0.0, trajectory=seg)
        assert g.roughness == 0.0

    def test_does_not_expose_forbidden_attributes(self, pipe_geom: PipeGeometry) -> None:
        for attr in _PIPE_FORBIDDEN_ATTRS:
            assert not hasattr(pipe_geom, attr), f"PipeGeometry must not expose '{attr}'"


# ---------------------------------------------------------------------------
# AccumulatorGeometry
# ---------------------------------------------------------------------------

_ACC_FORBIDDEN_LAW_PARAMS = [
    "V_gas_charge",
    "charge_pressure",
    "polytropic_index",
    "spring_rate",
    "bellows_area",
    "gas_constant",
    "P_set",
    "V_g",
    "P_sys",
]


class TestAccumulatorGeometry:
    def test_construction(self, acc_geom: AccumulatorGeometry) -> None:
        assert acc_geom.V_total == pytest.approx(0.005)
        assert isinstance(acc_geom.containment, ContainmentSpec)

    def test_thermal_defaults_to_none(self, acc_geom: AccumulatorGeometry) -> None:
        assert acc_geom.thermal is None

    def test_construction_with_thermal(self, containment: ContainmentSpec) -> None:
        thermal = ThermalSpec(heater_power=200.0, wall_area=0.05)
        g = AccumulatorGeometry(V_total=0.005, containment=containment, thermal=thermal)
        assert g.thermal is not None
        assert g.thermal.heater_power == 200.0
        assert g.thermal.wall_area == pytest.approx(0.05)

    def test_immutable(self, acc_geom: AccumulatorGeometry) -> None:
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            acc_geom.V_total = 999.0  # type: ignore[misc]

    def test_rejects_zero_V_total(self, containment: ContainmentSpec) -> None:
        with pytest.raises(ValueError, match="V_total"):
            AccumulatorGeometry(V_total=0.0, containment=containment)

    def test_rejects_negative_V_total(self, containment: ContainmentSpec) -> None:
        with pytest.raises(ValueError, match="V_total"):
            AccumulatorGeometry(V_total=-0.001, containment=containment)

    def test_does_not_expose_law_parameters(self, acc_geom: AccumulatorGeometry) -> None:
        for attr in _ACC_FORBIDDEN_LAW_PARAMS:
            assert not hasattr(
                acc_geom, attr
            ), f"AccumulatorGeometry must not expose law parameter '{attr}'"

    def test_containment_spec_immutable(self, containment: ContainmentSpec) -> None:
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            containment.inner_diameter = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PlateGeometry (minimal construction test)
# ---------------------------------------------------------------------------


class TestPlateGeometry:
    def test_construction(self) -> None:
        port = PortDimensions(diameter=0.05)
        g = PlateGeometry(
            N_plates=40,
            chevron_angle=60.0,
            plate_spacing=0.003,
            port_dims=port,
            A_per_plate=0.02,
        )
        assert g.N_plates == 40
        assert g.chevron_angle == 60.0
        assert g.plate_spacing == pytest.approx(0.003)
        assert g.A_per_plate == pytest.approx(0.02)
        assert g.sink_side is None

    def test_immutable(self) -> None:
        port = PortDimensions(diameter=0.05)
        g = PlateGeometry(
            N_plates=40,
            chevron_angle=60.0,
            plate_spacing=0.003,
            port_dims=port,
            A_per_plate=0.02,
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            g.N_plates = 1  # type: ignore[misc]

    def test_rejects_invalid_fields(self) -> None:
        port = PortDimensions(diameter=0.05)
        with pytest.raises(ValueError, match="N_plates"):
            PlateGeometry(
                N_plates=0,
                chevron_angle=60.0,
                plate_spacing=0.003,
                port_dims=port,
                A_per_plate=0.02,
            )
        with pytest.raises(ValueError, match="plate_spacing"):
            PlateGeometry(
                N_plates=40,
                chevron_angle=60.0,
                plate_spacing=0.0,
                port_dims=port,
                A_per_plate=0.02,
            )


# ---------------------------------------------------------------------------
# MicrochannelGeometry (minimal construction test)
# ---------------------------------------------------------------------------


class TestMicrochannelGeometry:
    def test_construction(self) -> None:
        fin = FinGeometry(fin_pitch=800.0, fin_height=0.001, fin_thickness=0.0001)
        g = MicrochannelGeometry(
            N_channels=100,
            D_h_channel=0.001,
            fin_geometry=fin,
            A_heated=0.05,
            wall_mass=0.3,
            wall_material="aluminium",
        )
        assert g.N_channels == 100
        assert g.D_h_channel == pytest.approx(0.001)
        assert g.wall_mass == pytest.approx(0.3)
        assert g.wall_material == "aluminium"

    def test_immutable(self) -> None:
        fin = FinGeometry(fin_pitch=800.0, fin_height=0.001, fin_thickness=0.0001)
        g = MicrochannelGeometry(
            N_channels=100,
            D_h_channel=0.001,
            fin_geometry=fin,
            A_heated=0.05,
            wall_mass=0.3,
            wall_material="aluminium",
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            g.N_channels = 1  # type: ignore[misc]

    def test_rejects_invalid_fields(self) -> None:
        fin = FinGeometry(fin_pitch=800.0, fin_height=0.001, fin_thickness=0.0001)
        with pytest.raises(ValueError, match="D_h_channel"):
            MicrochannelGeometry(
                N_channels=100,
                D_h_channel=0.0,
                fin_geometry=fin,
                A_heated=0.05,
                wall_mass=0.3,
                wall_material="aluminium",
            )


# ---------------------------------------------------------------------------
# Import purity
# ---------------------------------------------------------------------------


class TestImportPurity:
    def test_geometry_primitives_does_not_import_coolprop(self) -> None:
        import mpl_sim.geometry.primitives as prim_mod

        assert prim_mod.__file__ is not None
        with open(prim_mod.__file__) as fh:
            lines = fh.readlines()
        import_lines = [ln for ln in lines if ln.strip().startswith(("import ", "from "))]
        for ln in import_lines:
            assert (
                "CoolProp" not in ln and "coolprop" not in ln.lower()
            ), f"geometry/primitives.py must not import CoolProp: {ln.rstrip()!r}"

    def test_geometry_primitives_does_not_import_forbidden_packages(self) -> None:
        import mpl_sim.geometry.primitives as prim_mod

        assert prim_mod.__file__ is not None
        with open(prim_mod.__file__) as fh:
            lines = fh.readlines()
        import_lines = [ln for ln in lines if ln.strip().startswith(("import ", "from "))]

        forbidden = [
            "mpl_sim.properties",
            "mpl_sim.correlations",
            "mpl_sim.components",
            "mpl_sim.calibration",
            "mpl_sim.network",
            "mpl_sim.solvers",
        ]
        for ln in import_lines:
            for pkg in forbidden:
                assert (
                    pkg not in ln
                ), f"geometry/primitives.py must not import '{pkg}': {ln.rstrip()!r}"
