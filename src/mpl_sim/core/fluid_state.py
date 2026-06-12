"""FluidState — canonical thermodynamic state (P, h, identity).

Exactly three fields: P [Pa], h [J/kg], identity.
No derived properties (T, x, rho, mu, k, sigma, cp, phase, h_f, h_g, h_fg) are stored.
No mdot — mass flow is a SystemState unknown, not a fluid-state quantity.
No PropertyBackend reference — derivation is wired in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass

from mpl_sim.core.fluid_identity import FluidIdentity


@dataclass(frozen=True)
class FluidState:
    """Immutable thermodynamic state anchored at (P, h, identity).

    P        : pressure                [Pa]
    h        : specific enthalpy       [J/kg]
    identity : which fluid this is
    """

    P: float
    h: float
    identity: FluidIdentity
