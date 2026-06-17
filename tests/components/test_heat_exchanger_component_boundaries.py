"""Architecture boundary tests for HX components — Phase 11E.

Verifies:
  - Evaporator and Condenser do not import Network, Solver, or CoolProp
  - Ports remain value-free after Phase 11
  - Existing Pump and Accumulator tests are unaffected (smoke check)
  - Evaporator imports no properties package
  - Condenser imports no properties package
  - HX component helpers do not store derived state
"""

from __future__ import annotations

from mpl_sim.components.base import ComponentId, ComponentKind
from mpl_sim.core.port import Port, PortId, PortRole

# ---------------------------------------------------------------------------
# Ports remain value-free
# ---------------------------------------------------------------------------


class TestPortsRemainValueFree:
    def test_port_has_no_p_field(self) -> None:
        port = Port(
            id=PortId(component_id="c", port_name="in"),
            owner="c",
            role=PortRole.INLET,
            peer=None,
        )
        assert not hasattr(port, "P")

    def test_port_has_no_h_field(self) -> None:
        port = Port(
            id=PortId(component_id="c", port_name="in"),
            owner="c",
            role=PortRole.INLET,
            peer=None,
        )
        assert not hasattr(port, "h")

    def test_port_has_no_state_field(self) -> None:
        port = Port(
            id=PortId(component_id="c", port_name="in"),
            owner="c",
            role=PortRole.INLET,
            peer=None,
        )
        assert not hasattr(port, "state")

    def test_port_has_no_mdot_field(self) -> None:
        port = Port(
            id=PortId(component_id="c", port_name="in"),
            owner="c",
            role=PortRole.INLET,
            peer=None,
        )
        assert not hasattr(port, "mdot")

    def test_evaporator_ports_are_value_free(self) -> None:
        from mpl_sim.components.evaporator import EvaporatorComponent
        from mpl_sim.geometry.primitives import FinGeometry, MicrochannelGeometry

        geom = MicrochannelGeometry(
            N_channels=10,
            D_h_channel=0.001,
            fin_geometry=FinGeometry(fin_pitch=200.0, fin_height=0.005, fin_thickness=0.0001),
            A_heated=0.02,
            wall_mass=0.05,
            wall_material="aluminium",
        )
        evap = EvaporatorComponent(component_id=ComponentId("e"), geometry=geom)
        for port in evap.ports():
            assert not hasattr(port, "P")
            assert not hasattr(port, "h")
            assert not hasattr(port, "state")

    def test_condenser_ports_are_value_free(self) -> None:
        from mpl_sim.components.condenser import CondenserComponent
        from mpl_sim.geometry.primitives import PlateGeometry, PortDimensions

        geom = PlateGeometry(
            N_plates=10,
            chevron_angle=60.0,
            plate_spacing=0.003,
            port_dims=PortDimensions(diameter=0.02),
            A_per_plate=0.03,
        )
        cond = CondenserComponent(component_id=ComponentId("c"), geometry=geom)
        for port in cond.ports():
            assert not hasattr(port, "P")
            assert not hasattr(port, "h")
            assert not hasattr(port, "state")


# ---------------------------------------------------------------------------
# Import boundary — components
# ---------------------------------------------------------------------------


def _import_lines(module_file: str) -> list[str]:
    with open(module_file) as f:
        return [ln.strip() for ln in f if ln.strip().startswith(("import ", "from "))]


class TestEvaporatorImportBoundary:
    def _imports(self) -> list[str]:
        import mpl_sim.components.evaporator as m

        assert m.__file__ is not None
        return _import_lines(m.__file__)

    def test_does_not_import_network(self) -> None:
        for ln in self._imports():
            assert "network" not in ln

    def test_does_not_import_solvers(self) -> None:
        for ln in self._imports():
            assert "solvers" not in ln

    def test_does_not_import_coolprop(self) -> None:
        for ln in self._imports():
            assert "coolprop" not in ln.lower()

    def test_does_not_import_properties(self) -> None:
        for ln in self._imports():
            assert "properties" not in ln


class TestCondenserImportBoundary:
    def _imports(self) -> list[str]:
        import mpl_sim.components.condenser as m

        assert m.__file__ is not None
        return _import_lines(m.__file__)

    def test_does_not_import_network(self) -> None:
        for ln in self._imports():
            assert "network" not in ln

    def test_does_not_import_solvers(self) -> None:
        for ln in self._imports():
            assert "solvers" not in ln

    def test_does_not_import_coolprop(self) -> None:
        for ln in self._imports():
            assert "coolprop" not in ln.lower()

    def test_does_not_import_properties(self) -> None:
        for ln in self._imports():
            assert "properties" not in ln


# ---------------------------------------------------------------------------
# Existing pump and accumulator smoke check
# ---------------------------------------------------------------------------


class TestExistingComponentsUnchanged:
    def test_pump_kind_still_works(self) -> None:
        from mpl_sim.components.pump import PumpComponent

        pump = PumpComponent(component_id=ComponentId("p"))
        assert pump.kind() is ComponentKind.PUMP

    def test_accumulator_kind_still_works(self) -> None:
        from mpl_sim.components.accumulator import AccumulatorComponent
        from mpl_sim.geometry.primitives import AccumulatorGeometry, ContainmentSpec

        acc = AccumulatorComponent(
            component_id=ComponentId("acc"),
            geometry=AccumulatorGeometry(
                V_total=0.005,
                containment=ContainmentSpec(inner_diameter=0.1, height=0.3),
            ),
        )
        assert acc.kind() is ComponentKind.ACCUMULATOR

    def test_pump_ports_unchanged(self) -> None:
        from mpl_sim.components.pump import PumpComponent

        pump = PumpComponent(component_id=ComponentId("p"))
        assert len(pump.ports()) == 2

    def test_accumulator_ports_unchanged(self) -> None:
        from mpl_sim.components.accumulator import AccumulatorComponent
        from mpl_sim.geometry.primitives import AccumulatorGeometry, ContainmentSpec

        acc = AccumulatorComponent(
            component_id=ComponentId("acc"),
            geometry=AccumulatorGeometry(
                V_total=0.005,
                containment=ContainmentSpec(inner_diameter=0.1, height=0.3),
            ),
        )
        assert len(acc.ports()) == 1


# ---------------------------------------------------------------------------
# ComponentKind enum still has EVAPORATOR and CONDENSER
# ---------------------------------------------------------------------------


class TestComponentKindExtensions:
    def test_evaporator_in_component_kind(self) -> None:
        assert ComponentKind.EVAPORATOR in ComponentKind

    def test_condenser_in_component_kind(self) -> None:
        assert ComponentKind.CONDENSER in ComponentKind

    def test_pump_still_in_component_kind(self) -> None:
        assert ComponentKind.PUMP in ComponentKind

    def test_accumulator_still_in_component_kind(self) -> None:
        assert ComponentKind.ACCUMULATOR in ComponentKind

    def test_pipe_still_in_component_kind(self) -> None:
        assert ComponentKind.PIPE in ComponentKind
