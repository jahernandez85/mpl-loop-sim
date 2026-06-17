"""Tests for EvaporatorComponent — Phase 11C.

Verifies:
  - Evaporator has exactly inlet and outlet ports
  - No values on ports
  - ComponentKind is EVAPORATOR
  - Component is local and imports no Network/Solver/CoolProp
  - evaluate_heat_exchanger calls the injected HX model
  - evaluate_heat_exchanger passes injected correlations to model via request
  - evaluate_heat_exchanger passes calibration multipliers
  - FixedHeatRate raises outlet enthalpy by Q / mdot
  - No derived state is stored on the component
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId, ComponentKind
from mpl_sim.components.evaporator import EvaporatorComponent, EvaporatorHXInput
from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.core.port import PortRole
from mpl_sim.correlations.contract import (
    AnyFluid,
    Bound,
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationInput,
    CorrelationOutput,
    CorrelationRole,
    EnvelopeRef,
    SourceRef,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import FinGeometry, MicrochannelGeometry
from mpl_sim.hx_models.base import (
    FixedHeatRate,
    HeatExchangerModel,
    HeatExchangerModelKind,
    HXSolveRequest,
    HXSolveResult,
)

# ---------------------------------------------------------------------------
# Minimal fake HX model
# ---------------------------------------------------------------------------


class _RecordingModel(HeatExchangerModel):
    """Records calls and returns a canned result via EpsilonNTUModel-like logic."""

    def __init__(self) -> None:
        self.call_count = 0
        self.last_req: HXSolveRequest | None = None

    def kind(self) -> HeatExchangerModelKind:
        return HeatExchangerModelKind.EPSILON_NTU

    def solve(self, req: HXSolveRequest) -> HXSolveResult:
        self.call_count += 1
        self.last_req = req
        bc = req.secondary_bc
        assert isinstance(bc, FixedHeatRate)
        h_out = req.primary_state_in.h + bc.Q / req.primary_mdot
        state_out = FluidState(
            P=req.primary_state_in.P, h=h_out, identity=req.primary_state_in.identity
        )
        return HXSolveResult(
            primary_state_out=state_out,
            Q=bc.Q,
            dP_primary=0.0,
            verdicts=(),
        )


# ---------------------------------------------------------------------------
# Minimal fake correlations
# ---------------------------------------------------------------------------

_MINIMAL_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test"),
)


class _FakeHTCCorr(Correlation):
    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(100.0,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef("fake_htc", "0"),
                violated=(),
            ),
            metadata=ClosureMetadata("fake_htc", "0", SourceRef("test")),
        )


class _FakeDPCorr(Correlation):
    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(500.0,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef("fake_dp", "0"),
                violated=(),
            ),
            metadata=ClosureMetadata("fake_dp", "0", SourceRef("test")),
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=1e6, h=250e3, identity=_IDENTITY)
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)
_FIN = FinGeometry(fin_pitch=500.0, fin_height=0.008, fin_thickness=0.0001)
_GEOM = MicrochannelGeometry(
    N_channels=40,
    D_h_channel=0.0008,
    fin_geometry=_FIN,
    A_heated=0.05,
    wall_mass=0.15,
    wall_material="aluminium",
)
_COMP_ID = ComponentId("evap1")


def _make_evaporator() -> EvaporatorComponent:
    return EvaporatorComponent(component_id=_COMP_ID, geometry=_GEOM)


def _make_input(
    Q: float = 1000.0,
    mdot: float = 0.05,
    model: HeatExchangerModel | None = None,
    htc_primary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
) -> EvaporatorHXInput:
    return EvaporatorHXInput(
        primary_state_in=_STATE_IN,
        primary_mdot=mdot,
        secondary_bc=FixedHeatRate(Q=Q),
        model=model or _RecordingModel(),
        discretization=_DISC,
        geom_scalars={"rho": 1200.0, "mu": 2e-4},
        htc_primary=htc_primary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
    )


# ---------------------------------------------------------------------------
# Port structure
# ---------------------------------------------------------------------------


class TestEvaporatorPorts:
    def test_has_exactly_two_ports(self) -> None:
        evap = _make_evaporator()
        assert len(evap.ports()) == 2

    def test_inlet_role_is_inlet(self) -> None:
        evap = _make_evaporator()
        assert evap.inlet.role is PortRole.INLET

    def test_outlet_role_is_outlet(self) -> None:
        evap = _make_evaporator()
        assert evap.outlet.role is PortRole.OUTLET

    def test_inlet_peer_is_none(self) -> None:
        evap = _make_evaporator()
        assert evap.inlet.peer is None

    def test_outlet_peer_is_none(self) -> None:
        evap = _make_evaporator()
        assert evap.outlet.peer is None

    def test_ports_tuple_matches_properties(self) -> None:
        evap = _make_evaporator()
        ports = evap.ports()
        assert ports[0].id == evap.inlet.id
        assert ports[1].id == evap.outlet.id


# ---------------------------------------------------------------------------
# ComponentKind
# ---------------------------------------------------------------------------


class TestEvaporatorKind:
    def test_kind_is_evaporator(self) -> None:
        evap = _make_evaporator()
        assert evap.kind() is ComponentKind.EVAPORATOR


# ---------------------------------------------------------------------------
# Internal state names
# ---------------------------------------------------------------------------


class TestEvaporatorInternalState:
    def test_internal_state_names_is_tuple(self) -> None:
        evap = _make_evaporator()
        assert isinstance(evap.internal_state_names(), tuple)

    def test_t_wall_is_declared(self) -> None:
        evap = _make_evaporator()
        assert "T_wall" in evap.internal_state_names()


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestEvaporatorImmutability:
    def test_component_is_frozen(self) -> None:
        evap = _make_evaporator()
        with pytest.raises((AttributeError, TypeError)):
            evap.component_id = ComponentId("other")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# evaluate_heat_exchanger — model is called
# ---------------------------------------------------------------------------


class TestEvaluateHXModelCalled:
    def test_model_is_called(self) -> None:
        evap = _make_evaporator()
        rec_model = _RecordingModel()
        inp = _make_input(model=rec_model)
        evap.evaluate_heat_exchanger(inp)
        assert rec_model.call_count == 1

    def test_model_receives_correct_geometry(self) -> None:
        evap = _make_evaporator()
        rec_model = _RecordingModel()
        inp = _make_input(model=rec_model)
        evap.evaluate_heat_exchanger(inp)
        assert rec_model.last_req is not None
        assert rec_model.last_req.geometry is _GEOM

    def test_model_receives_correct_state_in(self) -> None:
        evap = _make_evaporator()
        rec_model = _RecordingModel()
        inp = _make_input(model=rec_model)
        evap.evaluate_heat_exchanger(inp)
        assert rec_model.last_req is not None
        assert rec_model.last_req.primary_state_in is _STATE_IN

    def test_model_receives_correlations(self) -> None:
        evap = _make_evaporator()
        rec_model = _RecordingModel()
        htc = _FakeHTCCorr()
        dp = _FakeDPCorr()
        inp = _make_input(model=rec_model, htc_primary=htc, dp_primary=dp)
        evap.evaluate_heat_exchanger(inp)
        assert rec_model.last_req is not None
        assert rec_model.last_req.htc_primary is htc
        assert rec_model.last_req.dp_primary is dp

    def test_model_receives_calibration_multipliers(self) -> None:
        evap = _make_evaporator()
        rec_model = _RecordingModel()
        inp = _make_input(model=rec_model, htc_multiplier=1.2, friction_multiplier=0.8)
        evap.evaluate_heat_exchanger(inp)
        assert rec_model.last_req is not None
        assert math.isclose(rec_model.last_req.htc_multiplier, 1.2)
        assert math.isclose(rec_model.last_req.friction_multiplier, 0.8)

    def test_result_is_hx_solve_result(self) -> None:
        evap = _make_evaporator()
        result = evap.evaluate_heat_exchanger(_make_input())
        assert isinstance(result, HXSolveResult)


# ---------------------------------------------------------------------------
# Energy balance through helper
# ---------------------------------------------------------------------------


class TestEvaluateHXEnergyBalance:
    def test_h_out_equals_h_in_plus_q_over_mdot(self) -> None:
        from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

        evap = _make_evaporator()
        Q, mdot = 2000.0, 0.05
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
            secondary_bc=FixedHeatRate(Q=Q),
            model=EpsilonNTUModel(),
            discretization=_DISC,
            geom_scalars={"rho": 1200.0, "mu": 2e-4},
        )
        result = evap.evaluate_heat_exchanger(inp)
        expected = _STATE_IN.h + Q / mdot
        assert math.isclose(result.primary_state_out.h, expected, rel_tol=1e-12)

    def test_primary_state_out_not_on_port(self) -> None:
        from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

        evap = _make_evaporator()
        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=500.0),
            model=EpsilonNTUModel(),
            discretization=_DISC,
        )
        evap.evaluate_heat_exchanger(inp)
        for port in evap.ports():
            assert not hasattr(port, "state")
            assert not hasattr(port, "h")
            assert not hasattr(port, "P")


# ---------------------------------------------------------------------------
# No derived state stored on component
# ---------------------------------------------------------------------------


class TestNoStoredDerivedState:
    def test_component_has_no_q_attribute(self) -> None:
        evap = _make_evaporator()
        assert not hasattr(evap, "Q")

    def test_component_has_no_dp_attribute(self) -> None:
        evap = _make_evaporator()
        assert not hasattr(evap, "dP")

    def test_component_has_no_h_out_attribute(self) -> None:
        evap = _make_evaporator()
        assert not hasattr(evap, "h_out")

    def test_evaluate_does_not_mutate_component(self) -> None:
        evap = _make_evaporator()
        cid_before = evap.component_id
        geom_before = evap.geometry
        evap.evaluate_heat_exchanger(_make_input())
        assert evap.component_id is cid_before
        assert evap.geometry is geom_before


# ---------------------------------------------------------------------------
# Import boundary
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
