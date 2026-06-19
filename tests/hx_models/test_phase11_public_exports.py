"""Phase 11U: public export consistency tests.

Verifies __all__ membership for Phase 11 symbols not already covered by
per-phase test files.  Filling these gaps ensures that a symbol removed from
__all__ will break this suite rather than silently disappearing from the public
API.

Covered here (not already checked in __all__ by another test file):
  mpl_sim.hx_models:
    - FlowArrangement
    - HXSolveRequest
    - HXSolveResult

  mpl_sim.correlations:
    - MSHTwoPhaseFrictionGradient
"""

import mpl_sim.correlations as correlations_pkg
import mpl_sim.hx_models as hx_pkg
from mpl_sim.correlations import MSHTwoPhaseFrictionGradient
from mpl_sim.hx_models import FlowArrangement, HXSolveRequest, HXSolveResult


class TestHXModelsExports:
    def test_flow_arrangement_in_all(self) -> None:
        assert "FlowArrangement" in hx_pkg.__all__

    def test_flow_arrangement_identity(self) -> None:
        assert hx_pkg.FlowArrangement is FlowArrangement

    def test_hx_solve_request_in_all(self) -> None:
        assert "HXSolveRequest" in hx_pkg.__all__

    def test_hx_solve_request_identity(self) -> None:
        assert hx_pkg.HXSolveRequest is HXSolveRequest

    def test_hx_solve_result_in_all(self) -> None:
        assert "HXSolveResult" in hx_pkg.__all__

    def test_hx_solve_result_identity(self) -> None:
        assert hx_pkg.HXSolveResult is HXSolveResult

    def test_all_entries_are_accessible(self) -> None:
        for name in hx_pkg.__all__:
            assert hasattr(hx_pkg, name), f"__all__ entry {name!r} not exported"


class TestCorrelationsExports:
    def test_msh_two_phase_friction_gradient_in_all(self) -> None:
        assert "MSHTwoPhaseFrictionGradient" in correlations_pkg.__all__

    def test_msh_two_phase_friction_gradient_identity(self) -> None:
        assert correlations_pkg.MSHTwoPhaseFrictionGradient is MSHTwoPhaseFrictionGradient

    def test_all_entries_are_accessible(self) -> None:
        for name in correlations_pkg.__all__:
            assert hasattr(correlations_pkg, name), f"__all__ entry {name!r} not exported"
