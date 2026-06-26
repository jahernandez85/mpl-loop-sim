"""Tests for Block 15G-A: explicit configurable residual blueprint assembly.

Covers:
  - ConfigurableResidualBlueprintKind enum
  - MassBalanceResidualBlueprint validation and translation
  - PressureDifferenceResidualBlueprint validation and translation
  - ImposedPressureResidualBlueprint validation and translation
  - ImposedMassFlowResidualBlueprint validation and translation
  - EnthalpyFlowResidualBlueprint validation and translation
  - ConfigurableResidualBlueprintSet construction
  - build_configurable_residual_blueprint_set behavior
  - build_configurable_algebraic_residuals_from_blueprints behavior
  - ConfigurableResidualBlueprintBuildResult structure
  - build_configurable_residual_blueprint_report output
  - Scenario compatibility validation
  - Boundary assertions: no topology inference, no role inference, no CoolProp,
    no PropertyBackend, no SystemState, no FluidState, no solve, no contribute,
    no file writes.

These tests do NOT:
  - Call any solver or root-finder.
  - Execute production component physics.
  - Call CoolProp, PropertyBackend, or correlations.
  - Assemble SystemState or construct FluidState.
  - Write files, use pandas, or use numpy.
  - Infer residuals from roles or topology.
"""

from __future__ import annotations

import json
import math

import pytest

from mpl_sim.network.configurable_algebraic_residuals import (
    EnthalpyFlowResidualDeclaration,
    ImposedMassFlowResidualDeclaration,
    ImposedPressureResidualDeclaration,
    MassBalanceResidualDeclaration,
    PressureDifferenceResidualDeclaration,
)
from mpl_sim.network.configurable_residual_blueprints import (
    ConfigurableResidualBlueprintBuildResult,
    ConfigurableResidualBlueprintKind,
    EnthalpyFlowResidualBlueprint,
    ImposedMassFlowResidualBlueprint,
    ImposedPressureResidualBlueprint,
    MassBalanceResidualBlueprint,
    PressureDifferenceResidualBlueprint,
    build_configurable_algebraic_residuals_from_blueprints,
    build_configurable_residual_blueprint_report,
    build_configurable_residual_blueprint_set,
)

# ===========================================================================
# ConfigurableResidualBlueprintKind
# ===========================================================================


class TestConfigurableResidualBlueprintKind:
    def test_has_mass_balance(self) -> None:
        assert ConfigurableResidualBlueprintKind.MASS_BALANCE.value == "mass_balance"

    def test_has_pressure_difference(self) -> None:
        assert ConfigurableResidualBlueprintKind.PRESSURE_DIFFERENCE.value == "pressure_difference"

    def test_has_imposed_pressure(self) -> None:
        assert ConfigurableResidualBlueprintKind.IMPOSED_PRESSURE.value == "imposed_pressure"

    def test_has_imposed_mass_flow(self) -> None:
        assert ConfigurableResidualBlueprintKind.IMPOSED_MASS_FLOW.value == "imposed_mass_flow"

    def test_has_enthalpy_flow(self) -> None:
        assert ConfigurableResidualBlueprintKind.ENTHALPY_FLOW.value == "enthalpy_flow"

    def test_exactly_five_values(self) -> None:
        assert len(list(ConfigurableResidualBlueprintKind)) == 5

    def test_values_are_strings(self) -> None:
        for kind in ConfigurableResidualBlueprintKind:
            assert isinstance(kind.value, str)


# ===========================================================================
# MassBalanceResidualBlueprint
# ===========================================================================


class TestMassBalanceResidualBlueprint:
    def test_basic_construction(self) -> None:
        bp = MassBalanceResidualBlueprint(
            residual_name="mb_pump",
            incoming_component_ids=("pump",),
            outgoing_component_ids=("evaporator",),
        )
        assert bp.residual_name == "mb_pump"
        assert bp.incoming_component_ids == ("pump",)
        assert bp.outgoing_component_ids == ("evaporator",)
        assert bp.anchor_node_id is None
        assert bp.kind is ConfigurableResidualBlueprintKind.MASS_BALANCE

    def test_list_inputs_converted_to_tuple(self) -> None:
        bp = MassBalanceResidualBlueprint(
            residual_name="mb",
            incoming_component_ids=["a", "b"],
            outgoing_component_ids=["c"],
        )
        assert isinstance(bp.incoming_component_ids, tuple)
        assert isinstance(bp.outgoing_component_ids, tuple)

    def test_with_anchor_node_id(self) -> None:
        bp = MassBalanceResidualBlueprint(
            residual_name="mb_node1",
            incoming_component_ids=("acc",),
            outgoing_component_ids=(),
            anchor_node_id="n_acc_out",
        )
        assert bp.anchor_node_id == "n_acc_out"

    def test_anchor_node_id_is_metadata_only(self) -> None:
        bp_with = MassBalanceResidualBlueprint(
            residual_name="mb",
            incoming_component_ids=("pump",),
            outgoing_component_ids=("evap",),
            anchor_node_id="n1",
        )
        bp_without = MassBalanceResidualBlueprint(
            residual_name="mb",
            incoming_component_ids=("pump",),
            outgoing_component_ids=("evap",),
        )
        decl_with = bp_with._to_algebraic_declaration()
        decl_without = bp_without._to_algebraic_declaration()
        # anchor_node_id does not affect translation
        assert decl_with.incoming_unknown_names == decl_without.incoming_unknown_names
        assert decl_with.outgoing_unknown_names == decl_without.outgoing_unknown_names

    def test_empty_residual_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            MassBalanceResidualBlueprint(
                residual_name="",
                incoming_component_ids=("pump",),
                outgoing_component_ids=(),
            )

    def test_non_str_residual_name_rejected(self) -> None:
        with pytest.raises(TypeError):
            MassBalanceResidualBlueprint(
                residual_name=123,  # type: ignore[arg-type]
                incoming_component_ids=("pump",),
                outgoing_component_ids=(),
            )

    def test_empty_incoming_and_outgoing_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            MassBalanceResidualBlueprint(
                residual_name="mb",
                incoming_component_ids=(),
                outgoing_component_ids=(),
            )

    def test_empty_component_id_in_incoming_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            MassBalanceResidualBlueprint(
                residual_name="mb",
                incoming_component_ids=("",),
                outgoing_component_ids=(),
            )

    def test_non_str_component_id_in_outgoing_rejected(self) -> None:
        with pytest.raises(TypeError):
            MassBalanceResidualBlueprint(
                residual_name="mb",
                incoming_component_ids=(),
                outgoing_component_ids=(123,),  # type: ignore[arg-type]
            )

    def test_empty_anchor_node_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            MassBalanceResidualBlueprint(
                residual_name="mb",
                incoming_component_ids=("pump",),
                outgoing_component_ids=(),
                anchor_node_id="",
            )

    def test_only_incoming_allowed(self) -> None:
        bp = MassBalanceResidualBlueprint(
            residual_name="mb",
            incoming_component_ids=("pump",),
            outgoing_component_ids=(),
        )
        assert len(bp.incoming_component_ids) == 1
        assert len(bp.outgoing_component_ids) == 0

    def test_only_outgoing_allowed(self) -> None:
        bp = MassBalanceResidualBlueprint(
            residual_name="mb",
            incoming_component_ids=(),
            outgoing_component_ids=("evap",),
        )
        assert len(bp.incoming_component_ids) == 0
        assert len(bp.outgoing_component_ids) == 1

    def test_translation_to_algebraic_declaration(self) -> None:
        bp = MassBalanceResidualBlueprint(
            residual_name="mb_node",
            incoming_component_ids=("pump",),
            outgoing_component_ids=("evaporator", "condenser"),
        )
        decl = bp._to_algebraic_declaration()
        assert isinstance(decl, MassBalanceResidualDeclaration)
        assert decl.residual_name == "mb_node"
        assert decl.incoming_unknown_names == ("mdot:pump",)
        assert decl.outgoing_unknown_names == ("mdot:evaporator", "mdot:condenser")

    def test_translation_mdot_prefix(self) -> None:
        bp = MassBalanceResidualBlueprint(
            residual_name="mb",
            incoming_component_ids=("comp_a",),
            outgoing_component_ids=("comp_b",),
        )
        decl = bp._to_algebraic_declaration()
        assert all(n.startswith("mdot:") for n in decl.incoming_unknown_names)
        assert all(n.startswith("mdot:") for n in decl.outgoing_unknown_names)

    def test_is_frozen(self) -> None:
        bp = MassBalanceResidualBlueprint(
            residual_name="mb",
            incoming_component_ids=("pump",),
            outgoing_component_ids=(),
        )
        with pytest.raises((AttributeError, TypeError)):
            bp.residual_name = "other"  # type: ignore[misc]


# ===========================================================================
# PressureDifferenceResidualBlueprint
# ===========================================================================


class TestPressureDifferenceResidualBlueprint:
    def test_basic_construction(self) -> None:
        bp = PressureDifferenceResidualBlueprint(
            residual_name="dp_pump",
            inlet_node_id="n_acc_out",
            outlet_node_id="n_pump_out",
            delta_p=-50000.0,
        )
        assert bp.residual_name == "dp_pump"
        assert bp.inlet_node_id == "n_acc_out"
        assert bp.outlet_node_id == "n_pump_out"
        assert bp.delta_p == -50000.0
        assert bp.kind is ConfigurableResidualBlueprintKind.PRESSURE_DIFFERENCE

    def test_delta_p_stored_as_float(self) -> None:
        bp = PressureDifferenceResidualBlueprint(
            residual_name="dp",
            inlet_node_id="n1",
            outlet_node_id="n2",
            delta_p=1000,
        )
        assert isinstance(bp.delta_p, float)
        assert bp.delta_p == 1000.0

    def test_empty_residual_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            PressureDifferenceResidualBlueprint(
                residual_name="",
                inlet_node_id="n1",
                outlet_node_id="n2",
                delta_p=0.0,
            )

    def test_empty_inlet_node_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            PressureDifferenceResidualBlueprint(
                residual_name="dp",
                inlet_node_id="",
                outlet_node_id="n2",
                delta_p=0.0,
            )

    def test_empty_outlet_node_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            PressureDifferenceResidualBlueprint(
                residual_name="dp",
                inlet_node_id="n1",
                outlet_node_id="",
                delta_p=0.0,
            )

    def test_nan_delta_p_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            PressureDifferenceResidualBlueprint(
                residual_name="dp",
                inlet_node_id="n1",
                outlet_node_id="n2",
                delta_p=math.nan,
            )

    def test_inf_delta_p_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            PressureDifferenceResidualBlueprint(
                residual_name="dp",
                inlet_node_id="n1",
                outlet_node_id="n2",
                delta_p=math.inf,
            )

    def test_bool_delta_p_rejected(self) -> None:
        with pytest.raises(TypeError, match="not bool"):
            PressureDifferenceResidualBlueprint(
                residual_name="dp",
                inlet_node_id="n1",
                outlet_node_id="n2",
                delta_p=True,  # type: ignore[arg-type]
            )

    def test_non_numeric_delta_p_rejected(self) -> None:
        with pytest.raises(TypeError):
            PressureDifferenceResidualBlueprint(
                residual_name="dp",
                inlet_node_id="n1",
                outlet_node_id="n2",
                delta_p="1000",  # type: ignore[arg-type]
            )

    def test_translation_to_algebraic_declaration(self) -> None:
        bp = PressureDifferenceResidualBlueprint(
            residual_name="dp_pump",
            inlet_node_id="n_acc_out",
            outlet_node_id="n_pump_out",
            delta_p=-50000.0,
        )
        decl = bp._to_algebraic_declaration()
        assert isinstance(decl, PressureDifferenceResidualDeclaration)
        assert decl.residual_name == "dp_pump"
        assert decl.inlet_pressure_unknown == "P:n_acc_out"
        assert decl.outlet_pressure_unknown == "P:n_pump_out"
        assert decl.delta_p == -50000.0

    def test_translation_p_prefix(self) -> None:
        bp = PressureDifferenceResidualBlueprint(
            residual_name="dp",
            inlet_node_id="node_a",
            outlet_node_id="node_b",
            delta_p=0.0,
        )
        decl = bp._to_algebraic_declaration()
        assert decl.inlet_pressure_unknown.startswith("P:")
        assert decl.outlet_pressure_unknown.startswith("P:")

    def test_is_frozen(self) -> None:
        bp = PressureDifferenceResidualBlueprint(
            residual_name="dp",
            inlet_node_id="n1",
            outlet_node_id="n2",
            delta_p=0.0,
        )
        with pytest.raises((AttributeError, TypeError)):
            bp.delta_p = 999.0  # type: ignore[misc]


# ===========================================================================
# ImposedPressureResidualBlueprint
# ===========================================================================


class TestImposedPressureResidualBlueprint:
    def test_basic_construction(self) -> None:
        bp = ImposedPressureResidualBlueprint(
            residual_name="p_ref",
            node_id="n_acc_out",
            pressure=100_000.0,
        )
        assert bp.residual_name == "p_ref"
        assert bp.node_id == "n_acc_out"
        assert bp.pressure == 100_000.0
        assert bp.kind is ConfigurableResidualBlueprintKind.IMPOSED_PRESSURE

    def test_pressure_stored_as_float(self) -> None:
        bp = ImposedPressureResidualBlueprint(
            residual_name="p_ref",
            node_id="n1",
            pressure=100000,
        )
        assert isinstance(bp.pressure, float)

    def test_empty_residual_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            ImposedPressureResidualBlueprint(
                residual_name="",
                node_id="n1",
                pressure=1e5,
            )

    def test_empty_node_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            ImposedPressureResidualBlueprint(
                residual_name="p_ref",
                node_id="",
                pressure=1e5,
            )

    def test_nan_pressure_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            ImposedPressureResidualBlueprint(
                residual_name="p_ref",
                node_id="n1",
                pressure=math.nan,
            )

    def test_inf_pressure_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            ImposedPressureResidualBlueprint(
                residual_name="p_ref",
                node_id="n1",
                pressure=math.inf,
            )

    def test_bool_pressure_rejected(self) -> None:
        with pytest.raises(TypeError, match="not bool"):
            ImposedPressureResidualBlueprint(
                residual_name="p_ref",
                node_id="n1",
                pressure=True,  # type: ignore[arg-type]
            )

    def test_non_numeric_pressure_rejected(self) -> None:
        with pytest.raises(TypeError):
            ImposedPressureResidualBlueprint(
                residual_name="p_ref",
                node_id="n1",
                pressure="1e5",  # type: ignore[arg-type]
            )

    def test_translation_to_algebraic_declaration(self) -> None:
        bp = ImposedPressureResidualBlueprint(
            residual_name="p_ref",
            node_id="n_acc_out",
            pressure=100_000.0,
        )
        decl = bp._to_algebraic_declaration()
        assert isinstance(decl, ImposedPressureResidualDeclaration)
        assert decl.residual_name == "p_ref"
        assert decl.pressure_unknown == "P:n_acc_out"
        assert decl.imposed_value == 100_000.0

    def test_translation_p_prefix(self) -> None:
        bp = ImposedPressureResidualBlueprint(
            residual_name="p_ref",
            node_id="some_node",
            pressure=0.0,
        )
        decl = bp._to_algebraic_declaration()
        assert decl.pressure_unknown.startswith("P:")
        assert decl.pressure_unknown == "P:some_node"

    def test_is_frozen(self) -> None:
        bp = ImposedPressureResidualBlueprint(
            residual_name="p_ref",
            node_id="n1",
            pressure=1e5,
        )
        with pytest.raises((AttributeError, TypeError)):
            bp.pressure = 0.0  # type: ignore[misc]


# ===========================================================================
# ImposedMassFlowResidualBlueprint
# ===========================================================================


class TestImposedMassFlowResidualBlueprint:
    def test_basic_construction(self) -> None:
        bp = ImposedMassFlowResidualBlueprint(
            residual_name="mdot_pump",
            component_id="pump",
            mass_flow=0.1,
        )
        assert bp.residual_name == "mdot_pump"
        assert bp.component_id == "pump"
        assert bp.mass_flow == 0.1
        assert bp.kind is ConfigurableResidualBlueprintKind.IMPOSED_MASS_FLOW

    def test_mass_flow_stored_as_float(self) -> None:
        bp = ImposedMassFlowResidualBlueprint(
            residual_name="mdot",
            component_id="c",
            mass_flow=1,
        )
        assert isinstance(bp.mass_flow, float)

    def test_empty_residual_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            ImposedMassFlowResidualBlueprint(
                residual_name="",
                component_id="pump",
                mass_flow=0.1,
            )

    def test_empty_component_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            ImposedMassFlowResidualBlueprint(
                residual_name="mdot",
                component_id="",
                mass_flow=0.1,
            )

    def test_nan_mass_flow_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            ImposedMassFlowResidualBlueprint(
                residual_name="mdot",
                component_id="pump",
                mass_flow=math.nan,
            )

    def test_inf_mass_flow_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be finite"):
            ImposedMassFlowResidualBlueprint(
                residual_name="mdot",
                component_id="pump",
                mass_flow=-math.inf,
            )

    def test_bool_mass_flow_rejected(self) -> None:
        with pytest.raises(TypeError, match="not bool"):
            ImposedMassFlowResidualBlueprint(
                residual_name="mdot",
                component_id="pump",
                mass_flow=False,  # type: ignore[arg-type]
            )

    def test_non_numeric_mass_flow_rejected(self) -> None:
        with pytest.raises(TypeError):
            ImposedMassFlowResidualBlueprint(
                residual_name="mdot",
                component_id="pump",
                mass_flow="0.1",  # type: ignore[arg-type]
            )

    def test_translation_to_algebraic_declaration(self) -> None:
        bp = ImposedMassFlowResidualBlueprint(
            residual_name="mdot_pump",
            component_id="pump",
            mass_flow=0.1,
        )
        decl = bp._to_algebraic_declaration()
        assert isinstance(decl, ImposedMassFlowResidualDeclaration)
        assert decl.residual_name == "mdot_pump"
        assert decl.mass_flow_unknown == "mdot:pump"
        assert decl.imposed_value == 0.1

    def test_translation_mdot_prefix(self) -> None:
        bp = ImposedMassFlowResidualBlueprint(
            residual_name="mdot_acc",
            component_id="accumulator",
            mass_flow=0.05,
        )
        decl = bp._to_algebraic_declaration()
        assert decl.mass_flow_unknown.startswith("mdot:")
        assert decl.mass_flow_unknown == "mdot:accumulator"

    def test_is_frozen(self) -> None:
        bp = ImposedMassFlowResidualBlueprint(
            residual_name="mdot",
            component_id="pump",
            mass_flow=0.1,
        )
        with pytest.raises((AttributeError, TypeError)):
            bp.mass_flow = 99.0  # type: ignore[misc]


# ===========================================================================
# EnthalpyFlowResidualBlueprint
# ===========================================================================


class TestEnthalpyFlowResidualBlueprint:
    def test_basic_construction(self) -> None:
        bp = EnthalpyFlowResidualBlueprint(
            residual_name="hflow_evap",
            heat_rate_unknown="q_evap",
            mass_flow_component_id="evaporator",
            h_in_unknown="h_in_evap",
            h_out_unknown="h_out_evap",
        )
        assert bp.residual_name == "hflow_evap"
        assert bp.heat_rate_unknown == "q_evap"
        assert bp.mass_flow_component_id == "evaporator"
        assert bp.h_in_unknown == "h_in_evap"
        assert bp.h_out_unknown == "h_out_evap"
        assert bp.kind is ConfigurableResidualBlueprintKind.ENTHALPY_FLOW

    def test_empty_residual_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            EnthalpyFlowResidualBlueprint(
                residual_name="",
                heat_rate_unknown="q",
                mass_flow_component_id="evap",
                h_in_unknown="h_in",
                h_out_unknown="h_out",
            )

    def test_empty_heat_rate_unknown_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            EnthalpyFlowResidualBlueprint(
                residual_name="hflow",
                heat_rate_unknown="",
                mass_flow_component_id="evap",
                h_in_unknown="h_in",
                h_out_unknown="h_out",
            )

    def test_empty_mass_flow_component_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            EnthalpyFlowResidualBlueprint(
                residual_name="hflow",
                heat_rate_unknown="q",
                mass_flow_component_id="",
                h_in_unknown="h_in",
                h_out_unknown="h_out",
            )

    def test_empty_h_in_unknown_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            EnthalpyFlowResidualBlueprint(
                residual_name="hflow",
                heat_rate_unknown="q",
                mass_flow_component_id="evap",
                h_in_unknown="",
                h_out_unknown="h_out",
            )

    def test_empty_h_out_unknown_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty"):
            EnthalpyFlowResidualBlueprint(
                residual_name="hflow",
                heat_rate_unknown="q",
                mass_flow_component_id="evap",
                h_in_unknown="h_in",
                h_out_unknown="",
            )

    def test_translation_to_algebraic_declaration(self) -> None:
        bp = EnthalpyFlowResidualBlueprint(
            residual_name="hflow_evap",
            heat_rate_unknown="q_evap",
            mass_flow_component_id="evaporator",
            h_in_unknown="h_in_evap",
            h_out_unknown="h_out_evap",
        )
        decl = bp._to_algebraic_declaration()
        assert isinstance(decl, EnthalpyFlowResidualDeclaration)
        assert decl.residual_name == "hflow_evap"
        assert decl.q_unknown == "q_evap"
        assert decl.mdot_unknown == "mdot:evaporator"
        assert decl.h_in_unknown == "h_in_evap"
        assert decl.h_out_unknown == "h_out_evap"

    def test_translation_mdot_prefix_for_component(self) -> None:
        bp = EnthalpyFlowResidualBlueprint(
            residual_name="hflow",
            heat_rate_unknown="q",
            mass_flow_component_id="comp_x",
            h_in_unknown="h_in",
            h_out_unknown="h_out",
        )
        decl = bp._to_algebraic_declaration()
        assert decl.mdot_unknown == "mdot:comp_x"

    def test_is_frozen(self) -> None:
        bp = EnthalpyFlowResidualBlueprint(
            residual_name="hflow",
            heat_rate_unknown="q",
            mass_flow_component_id="evap",
            h_in_unknown="h_in",
            h_out_unknown="h_out",
        )
        with pytest.raises((AttributeError, TypeError)):
            bp.residual_name = "other"  # type: ignore[misc]


# ===========================================================================
# ConfigurableResidualBlueprintSet
# ===========================================================================


class TestConfigurableResidualBlueprintSet:
    def _make_mass_balance(self, name: str = "mb") -> MassBalanceResidualBlueprint:
        return MassBalanceResidualBlueprint(
            residual_name=name,
            incoming_component_ids=("pump",),
            outgoing_component_ids=("evap",),
        )

    def _make_imposed_pressure(self, name: str = "p_ref") -> ImposedPressureResidualBlueprint:
        return ImposedPressureResidualBlueprint(
            residual_name=name,
            node_id="n1",
            pressure=1e5,
        )

    def test_build_basic_set(self) -> None:
        bp1 = self._make_mass_balance("mb1")
        bp2 = self._make_imposed_pressure("p_ref")
        bpset = build_configurable_residual_blueprint_set([bp1, bp2])
        assert bpset.blueprint_count == 2
        assert bpset.residual_names == ("mb1", "p_ref")
        assert bpset.blueprints == (bp1, bp2)

    def test_preserves_order(self) -> None:
        bps = [
            self._make_imposed_pressure("p_ref"),
            self._make_mass_balance("mb"),
            ImposedMassFlowResidualBlueprint("mdot_p", "pump", 0.1),
        ]
        bpset = build_configurable_residual_blueprint_set(bps)
        assert bpset.residual_names == ("p_ref", "mb", "mdot_p")

    def test_duplicate_residual_names_rejected(self) -> None:
        bp1 = self._make_mass_balance("same")
        bp2 = self._make_imposed_pressure("same")
        with pytest.raises(ValueError, match="duplicate"):
            build_configurable_residual_blueprint_set([bp1, bp2])

    def test_empty_set_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            build_configurable_residual_blueprint_set([])

    def test_non_blueprint_type_rejected(self) -> None:
        with pytest.raises(TypeError):
            build_configurable_residual_blueprint_set(["not_a_blueprint"])  # type: ignore[list-item]

    def test_tuple_input_accepted(self) -> None:
        bp = self._make_mass_balance()
        bpset = build_configurable_residual_blueprint_set((bp,))
        assert bpset.blueprint_count == 1

    def test_bpset_is_frozen(self) -> None:
        bp = self._make_mass_balance()
        bpset = build_configurable_residual_blueprint_set([bp])
        with pytest.raises((AttributeError, TypeError)):
            bpset.blueprints = ()  # type: ignore[misc]

    def test_bpset_blueprints_is_tuple(self) -> None:
        bp = self._make_mass_balance()
        bpset = build_configurable_residual_blueprint_set([bp])
        assert isinstance(bpset.blueprints, tuple)

    def test_source_list_mutation_does_not_affect_set(self) -> None:
        bp1 = self._make_mass_balance("mb1")
        bp2 = self._make_imposed_pressure("p_ref")
        source = [bp1, bp2]
        bpset = build_configurable_residual_blueprint_set(source)
        source.clear()
        assert bpset.blueprint_count == 2


# ===========================================================================
# build_configurable_algebraic_residuals_from_blueprints
# ===========================================================================


class TestBuildBlueprintsFunction:
    def _make_simple_blueprints(self) -> list:
        return [
            ImposedPressureResidualBlueprint("p_ref", "n_acc_out", 1e5),
            ImposedMassFlowResidualBlueprint("mdot_pump", "pump", 0.1),
        ]

    def test_basic_build(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert isinstance(result, ConfigurableResidualBlueprintBuildResult)
        assert result.blueprint_count == 2

    def test_accepts_blueprint_set(self) -> None:
        bps = self._make_simple_blueprints()
        bpset = build_configurable_residual_blueprint_set(bps)
        result = build_configurable_algebraic_residuals_from_blueprints(bpset)
        assert result.blueprint_count == 2

    def test_accepts_list(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.blueprint_count == 2

    def test_accepts_tuple(self) -> None:
        bps = tuple(self._make_simple_blueprints())
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.blueprint_count == 2

    def test_empty_list_rejected(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            build_configurable_algebraic_residuals_from_blueprints([])

    def test_duplicate_names_rejected(self) -> None:
        bp1 = ImposedPressureResidualBlueprint("same", "n1", 1e5)
        bp2 = ImposedMassFlowResidualBlueprint("same", "pump", 0.1)
        with pytest.raises(ValueError, match="duplicate"):
            build_configurable_algebraic_residuals_from_blueprints([bp1, bp2])

    def test_non_blueprint_element_rejected(self) -> None:
        with pytest.raises(TypeError):
            build_configurable_algebraic_residuals_from_blueprints(["not_a_blueprint"])  # type: ignore[list-item]

    def test_blueprint_names_ordered(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.blueprint_names == ("p_ref", "mdot_pump")

    def test_blueprint_kinds_ordered(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.blueprint_kinds == (
            ConfigurableResidualBlueprintKind.IMPOSED_PRESSURE.value,
            ConfigurableResidualBlueprintKind.IMPOSED_MASS_FLOW.value,
        )

    def test_algebraic_residual_set_has_correct_residuals(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        rs = result.algebraic_residual_set
        assert rs.residual_names == ("p_ref", "mdot_pump")

    def test_required_unknown_names_deduplicated(self) -> None:
        bps = [
            MassBalanceResidualBlueprint("mb", ("pump",), ("pump",)),
        ]
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        # "mdot:pump" appears in both incoming and outgoing but should deduplicate
        assert result.required_unknown_names.count("mdot:pump") == 1

    def test_required_unknown_names_ordered_by_declaration(self) -> None:
        bps = [
            ImposedPressureResidualBlueprint("p_ref", "n_acc_out", 1e5),
            ImposedMassFlowResidualBlueprint("mdot_pump", "pump", 0.1),
        ]
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.required_unknown_names == ("P:n_acc_out", "mdot:pump")

    def test_no_solve_is_true(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.no_solve is True

    def test_residuals_inferred_from_roles_is_false(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.residuals_inferred_from_roles is False

    def test_residuals_inferred_from_topology_is_false(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.residuals_inferred_from_topology is False

    def test_closures_inferred_from_roles_is_false(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.closures_inferred_from_roles is False

    def test_production_components_executed_is_false(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.production_components_executed is False

    def test_result_is_frozen(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        with pytest.raises((AttributeError, TypeError)):
            result.no_solve = False  # type: ignore[misc]

    def test_scenario_not_checked_when_none(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.scenario_compatibility_checked is False
        assert result.scenario_is_compatible is False
        assert result.missing_unknowns == ()

    def test_no_evaluation_during_build(self) -> None:
        # Build completes without requiring evaluation; algebraic_residual_set has
        # declarations but they have not been evaluated.
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert len(result.algebraic_residual_set.declarations) == 2

    def test_translation_produces_correct_declaration_types(self) -> None:
        bps = [
            MassBalanceResidualBlueprint("mb", ("pump",), ("evap",)),
            PressureDifferenceResidualBlueprint("dp", "n1", "n2", 1000.0),
            ImposedPressureResidualBlueprint("p_ref", "n_acc_out", 1e5),
            ImposedMassFlowResidualBlueprint("mdot_pump", "pump", 0.1),
            EnthalpyFlowResidualBlueprint("hflow", "q", "evap", "h_in", "h_out"),
        ]
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        decls = result.algebraic_residual_set.declarations
        assert isinstance(decls[0], MassBalanceResidualDeclaration)
        assert isinstance(decls[1], PressureDifferenceResidualDeclaration)
        assert isinstance(decls[2], ImposedPressureResidualDeclaration)
        assert isinstance(decls[3], ImposedMassFlowResidualDeclaration)
        assert isinstance(decls[4], EnthalpyFlowResidualDeclaration)

    def test_limitations_are_non_empty_tuple(self) -> None:
        bps = self._make_simple_blueprints()
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert isinstance(result.limitations, tuple)
        assert len(result.limitations) > 0


# ===========================================================================
# Scenario compatibility
# ===========================================================================


class _FakeScenarioBuildResult:
    """Minimal duck-type for scenario build result with unknown_names."""

    def __init__(self, unknown_names: tuple[str, ...]) -> None:
        self.unknown_names = unknown_names


class TestScenarioCompatibility:
    def test_compatible_when_all_unknowns_present(self) -> None:
        bps = [
            ImposedPressureResidualBlueprint("p_ref", "n1", 1e5),
            ImposedMassFlowResidualBlueprint("mdot_pump", "pump", 0.1),
        ]
        sbr = _FakeScenarioBuildResult(("P:n1", "mdot:pump", "P:n2"))
        result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        assert result.scenario_compatibility_checked is True
        assert result.scenario_is_compatible is True
        assert result.missing_unknowns == ()

    def test_incompatible_when_unknown_missing(self) -> None:
        bps = [
            ImposedPressureResidualBlueprint("p_ref", "n1", 1e5),
            ImposedMassFlowResidualBlueprint("mdot_pump", "pump", 0.1),
        ]
        # Only P:n1 is present; mdot:pump is missing
        sbr = _FakeScenarioBuildResult(("P:n1",))
        result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        assert result.scenario_compatibility_checked is True
        assert result.scenario_is_compatible is False
        assert "mdot:pump" in result.missing_unknowns

    def test_missing_mdot_reported_deterministically(self) -> None:
        bps = [
            ImposedMassFlowResidualBlueprint("mdot_b", "comp_b", 0.1),
            ImposedMassFlowResidualBlueprint("mdot_a", "comp_a", 0.2),
        ]
        sbr = _FakeScenarioBuildResult(())
        result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        # Sorted deterministically
        assert result.missing_unknowns == ("mdot:comp_a", "mdot:comp_b")

    def test_missing_p_node_reported_deterministically(self) -> None:
        bps = [
            ImposedPressureResidualBlueprint("p_b", "node_b", 2e5),
            ImposedPressureResidualBlueprint("p_a", "node_a", 1e5),
        ]
        sbr = _FakeScenarioBuildResult(())
        result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        assert result.missing_unknowns == ("P:node_a", "P:node_b")

    def test_not_checked_when_no_scenario(self) -> None:
        bps = [ImposedPressureResidualBlueprint("p_ref", "n1", 1e5)]
        result = build_configurable_algebraic_residuals_from_blueprints(bps)
        assert result.scenario_compatibility_checked is False

    def test_invalid_scenario_build_result_rejected(self) -> None:
        bps = [ImposedPressureResidualBlueprint("p_ref", "n1", 1e5)]
        with pytest.raises(TypeError, match="unknown_names"):
            build_configurable_algebraic_residuals_from_blueprints(
                bps, scenario_build_result="not_a_build_result"
            )

    def test_role_change_does_not_affect_blueprint_translation(self) -> None:
        # Blueprint explicitly references component/node IDs; roles are irrelevant
        bps = [ImposedMassFlowResidualBlueprint("mdot_pump", "pump", 0.1)]
        sbr = _FakeScenarioBuildResult(("mdot:pump", "P:n1"))
        result = build_configurable_algebraic_residuals_from_blueprints(
            bps, scenario_build_result=sbr
        )
        decl = result.algebraic_residual_set.declarations[0]
        # Translation is purely from component_id; no role involved
        assert decl.mass_flow_unknown == "mdot:pump"
        assert result.scenario_is_compatible is True

    def test_no_residuals_generated_without_blueprints(self) -> None:
        # Empty blueprint list is rejected; no auto-generation happens
        with pytest.raises(ValueError, match="must not be empty"):
            build_configurable_algebraic_residuals_from_blueprints([])


# ===========================================================================
# build_configurable_residual_blueprint_report
# ===========================================================================


class TestBlueprintReport:
    def _make_result(self) -> ConfigurableResidualBlueprintBuildResult:
        bps = [
            ImposedPressureResidualBlueprint("p_ref", "n_acc_out", 1e5),
            ImposedMassFlowResidualBlueprint("mdot_pump", "pump", 0.1),
        ]
        return build_configurable_algebraic_residuals_from_blueprints(bps)

    def test_returns_dict(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert isinstance(report, dict)

    def test_is_json_serializable(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        json_str = json.dumps(report)
        parsed = json.loads(json_str)
        assert parsed["no_solve"] is True

    def test_no_solve_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert report["no_solve"] is True

    def test_no_inference_flags_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert report["residuals_inferred_from_roles"] is False
        assert report["residuals_inferred_from_topology"] is False
        assert report["closures_inferred_from_roles"] is False
        assert report["production_components_executed"] is False

    def test_blueprint_count_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert report["blueprint_count"] == 2

    def test_blueprint_names_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert report["blueprint_names"] == ["p_ref", "mdot_pump"]

    def test_blueprint_kinds_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert report["blueprint_kinds"] == ["imposed_pressure", "imposed_mass_flow"]

    def test_residual_names_generated_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert report["residual_names_generated"] == ["p_ref", "mdot_pump"]

    def test_required_unknown_names_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert "P:n_acc_out" in report["required_unknown_names"]
        assert "mdot:pump" in report["required_unknown_names"]

    def test_scenario_compatibility_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        compat = report["scenario_compatibility"]
        assert isinstance(compat, dict)
        assert "checked" in compat
        assert "is_compatible" in compat
        assert "missing_unknowns" in compat

    def test_scenario_not_checked_reflected_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        compat = report["scenario_compatibility"]
        assert compat["checked"] is False
        assert compat["is_compatible"] is None

    def test_limitations_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert isinstance(report["limitations"], list)
        assert len(report["limitations"]) > 0

    def test_status_in_report(self) -> None:
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert report["status"] == "configurable_residual_blueprint_build"

    def test_wrong_type_rejected(self) -> None:
        with pytest.raises(TypeError):
            build_configurable_residual_blueprint_report("not_a_build_result")  # type: ignore[arg-type]

    def test_no_file_writes(self) -> None:
        # Report function returns a dict; no side effects, no file access
        result = self._make_result()
        report = build_configurable_residual_blueprint_report(result)
        assert isinstance(report, dict)


# ===========================================================================
# Boundary assertions — module-level
# ===========================================================================


class TestBlueprintModuleBoundaries:
    """Module-level boundary checks for configurable_residual_blueprints."""

    def _import_lines(self) -> list[str]:
        import re

        import mpl_sim.network.configurable_residual_blueprints as mod

        src_path = getattr(mod, "__file__", "")
        if not src_path:
            return []
        with open(src_path) as f:
            text = f.read()
        return [ln for ln in text.splitlines() if re.match(r"^\s*(import|from)\s+", ln)]

    def _executable_lines(self) -> list[str]:
        import mpl_sim.network.configurable_residual_blueprints as mod

        src_path = getattr(mod, "__file__", "")
        if not src_path:
            return []
        lines: list[str] = []
        in_docstring = False
        docstring_char = None
        with open(src_path) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                for dq in ('"""', "'''"):
                    if dq in line:
                        count = line.count(dq)
                        if in_docstring and docstring_char == dq:
                            in_docstring = count % 2 == 0
                            docstring_char = None if not in_docstring else dq
                        elif not in_docstring and count % 2 == 1:
                            in_docstring = True
                            docstring_char = dq
                        break
                if in_docstring:
                    continue
                lines.append(line)
        return lines

    def test_no_coolprop_import(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "CoolProp")
        for ln in self._import_lines():
            assert "CoolProp" not in ln, f"CoolProp found in import: {ln!r}"

    def test_no_property_backend_import(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "PropertyBackend")
        for ln in self._import_lines():
            assert "PropertyBackend" not in ln, f"PropertyBackend found in import: {ln!r}"

    def test_no_correlation_registry_import(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "CorrelationRegistry")
        for ln in self._import_lines():
            assert "CorrelationRegistry" not in ln

    def test_no_hx_model_import(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "hx_models")
        for ln in self._import_lines():
            assert "hx_models" not in ln

    def test_no_components_import(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "components")
        for ln in self._import_lines():
            assert "mpl_sim.components" not in ln

    def test_no_system_state(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "SystemState")
        for ln in self._import_lines():
            assert "SystemState" not in ln

    def test_no_fluid_state(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "FluidState")
        for ln in self._import_lines():
            assert "FluidState" not in ln

    def test_no_contribute_call(self) -> None:
        for ln in self._executable_lines():
            assert ".contribute(" not in ln, f"contribute call found: {ln!r}"

    def test_no_define_contribute(self) -> None:
        for ln in self._executable_lines():
            assert "def contribute" not in ln, f"contribute defined: {ln!r}"

    def test_no_solve_network(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "NetworkGraph")
        for ln in self._executable_lines():
            assert "solve(network" not in ln, f"solve(network found: {ln!r}"

    def test_no_network_graph_solve(self) -> None:
        import mpl_sim.network.configurable_residual_blueprints as mod

        assert not hasattr(mod, "NetworkGraph")
        for ln in self._executable_lines():
            assert "NetworkGraph.solve" not in ln

    def test_no_least_squares(self) -> None:
        for ln in self._executable_lines():
            assert "least_squares" not in ln
            assert "lstsq" not in ln
            assert "fsolve" not in ln

    def test_no_role_based_dispatch(self) -> None:
        for ln in self._executable_lines():
            assert "component_type" not in ln, f"component_type found: {ln!r}"

    def test_no_file_writes(self) -> None:
        for ln in self._executable_lines():
            assert "write_text" not in ln
            assert "to_csv" not in ln
            assert "to_json" not in ln
