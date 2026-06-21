"""Network residual evaluation foundation — Phase 13G.

Evaluates declared network residuals from an explicit value map and explicit
residual callback functions.  Builds on Phase 13F (declaration assembly) and
Phase 13C (ResidualEvaluation / ResidualVector).

What this module DOES
---------------------
- Accepts a NetworkResidualAssembly (Phase 13F declarations).
- Accepts an explicit NetworkUnknownValues map (unknown name → float).
- Accepts explicit NetworkResidualEvaluator callbacks, one per declared residual.
- Accepts explicit residual scales, one per declared residual.
- Evaluates each callback with the supplied unknown values.
- Validates all inputs strictly.
- Returns NetworkResidualEvaluationResult containing:
  - original assembly;
  - unknown values;
  - tuple of ResidualEvaluation (Phase 13C) in assembly declaration order;
  - ResidualVector (Phase 13C);
  - scaled values tuple;
  - max_abs_scaled (L-infinity norm);
  - l2_scaled (Euclidean norm).

Architecture boundaries (MUST NOT)
-----------------------------------
- MUST NOT solve the network.
- MUST NOT iterate residuals to find a zero.
- MUST NOT mutate the assembly, value map, or evaluators.
- MUST NOT execute component physics.
- MUST NOT look up fluid properties.
- MUST NOT attach physical state to graph nodes.
- MUST NOT import mpl_sim.solvers, mpl_sim.components, mpl_sim.properties,
  mpl_sim.calibration, mpl_sim.hx_models, or CoolProp.
- MUST NOT import or invoke CorrelationRegistry or HeatExchangerModelRegistry.
- MUST NOT import mpl_sim.closed_loop solver modules; only residuals.py value
  types (ResidualSpec, ResidualEvaluation, ResidualVector) are used.
- MUST NOT expose a solve() method on any evaluation type.

Exported names
--------------
NetworkUnknownValues            — immutable map from unknown name to float
NetworkResidualEvaluator        — frozen (name, callback) pair for one residual
NetworkResidualEvaluationResult — full evaluation result with vector and norms
evaluate_network_residuals      — main evaluation entry point
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mpl_sim.closed_loop.residuals import ResidualEvaluation, ResidualSpec, ResidualVector
from mpl_sim.network.residual_assembly import NetworkResidualAssembly

# ---------------------------------------------------------------------------
# NetworkUnknownValues
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkUnknownValues:
    """Immutable map from declared unknown name to numeric value.

    Accepts a plain dict or any Mapping[str, float].  Stored internally as a
    MappingProxyType so the contents cannot be mutated after construction.

    Fields
    ------
    values : MappingProxyType[str, float]
        Read-only view of the unknown name → float map.

    Validation (at construction)
    ----------------------------
    - All keys must be non-empty strings.
    - All values must be finite, non-bool numeric (int or float).

    Note
    ----
    Assembly-level validation (keys match declarations exactly, no extras or
    missing entries) is performed by evaluate_network_residuals, not here.
    NetworkUnknownValues may be constructed before an assembly is known.
    """

    values: MappingProxyType

    def __post_init__(self) -> None:
        raw = self.values
        if not hasattr(raw, "items"):
            raise TypeError(
                "NetworkUnknownValues.values must be a Mapping[str, float]; "
                f"got {type(raw).__name__!r}"
            )
        try:
            converted: MappingProxyType = MappingProxyType(dict(raw))
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "NetworkUnknownValues.values could not be converted to a mapping"
            ) from exc
        object.__setattr__(self, "values", converted)
        proxy: MappingProxyType = self.values
        for name, val in proxy.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError(
                    "NetworkUnknownValues: all keys must be non-empty strings; " f"got {name!r}"
                )
            if isinstance(val, bool):
                raise ValueError(
                    f"NetworkUnknownValues: value for {name!r} must not be bool; " f"got {val!r}"
                )
            if not isinstance(val, (int, float)):
                raise TypeError(
                    f"NetworkUnknownValues: value for {name!r} must be numeric; "
                    f"got {type(val).__name__!r}"
                )
            if not math.isfinite(float(val)):
                raise ValueError(
                    f"NetworkUnknownValues: value for {name!r} must be finite; " f"got {val!r}"
                )


# ---------------------------------------------------------------------------
# NetworkResidualEvaluator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkResidualEvaluator:
    """Frozen wrapper around a residual declaration name and its evaluation callback.

    One evaluator is required per declared residual in the assembly.

    Fields
    ------
    name     : non-empty string matching a NetworkResidualDeclaration name
    callback : callable(values: Mapping[str, float]) -> float

    The callback receives the full unknown-value mapping and returns the raw
    residual value in the declared unit.  It may perform any pure computation;
    it must not trigger property lookup, component execution, or network
    solving.

    Validation
    ----------
    - name must be a non-empty string.
    - callback must be callable.
    - Callback return validation (finite, non-bool numeric) is deferred to
      evaluate_network_residuals so that callback exceptions propagate naturally.
    """

    name: str
    callback: Callable[[Mapping[str, float]], float]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                "NetworkResidualEvaluator.name must be a non-empty string; " f"got {self.name!r}"
            )
        if not callable(self.callback):
            raise TypeError(
                "NetworkResidualEvaluator.callback must be callable; "
                f"got {type(self.callback).__name__!r}"
            )


# ---------------------------------------------------------------------------
# NetworkResidualEvaluationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkResidualEvaluationResult:
    """Immutable result of evaluating network residuals against explicit callbacks.

    Contains the original inputs and all computed outputs for full auditability.
    Nothing is mutated; no solve() method is provided.

    Fields
    ------
    assembly        : original NetworkResidualAssembly (Phase 13F)
    unknown_values  : NetworkUnknownValues supplied to the evaluation
    evaluations     : tuple of ResidualEvaluation (Phase 13C) in assembly order
    residual_vector : ResidualVector (Phase 13C) built from evaluations
    scaled_values   : tuple of scaled residuals (value / scale) in assembly order
    max_abs_scaled  : float — L-infinity norm of scaled residuals
    l2_scaled       : float — Euclidean (L2) norm of scaled residuals
    """

    assembly: NetworkResidualAssembly
    unknown_values: NetworkUnknownValues
    evaluations: tuple[ResidualEvaluation, ...]
    residual_vector: ResidualVector
    scaled_values: tuple[float, ...]
    max_abs_scaled: float
    l2_scaled: float

    def __post_init__(self) -> None:
        if not isinstance(self.assembly, NetworkResidualAssembly):
            raise TypeError(
                "NetworkResidualEvaluationResult.assembly must be a "
                f"NetworkResidualAssembly; got {type(self.assembly).__name__!r}"
            )
        if not isinstance(self.unknown_values, NetworkUnknownValues):
            raise TypeError(
                "NetworkResidualEvaluationResult.unknown_values must be a "
                f"NetworkUnknownValues; got {type(self.unknown_values).__name__!r}"
            )
        if not isinstance(self.evaluations, tuple):
            object.__setattr__(self, "evaluations", tuple(self.evaluations))
        if not isinstance(self.residual_vector, ResidualVector):
            raise TypeError(
                "NetworkResidualEvaluationResult.residual_vector must be a "
                f"ResidualVector; got {type(self.residual_vector).__name__!r}"
            )
        if not isinstance(self.scaled_values, tuple):
            object.__setattr__(self, "scaled_values", tuple(self.scaled_values))


# ---------------------------------------------------------------------------
# evaluate_network_residuals
# ---------------------------------------------------------------------------


def evaluate_network_residuals(
    assembly: object,
    unknown_values: object,
    evaluators: object,
    scales: object,
) -> NetworkResidualEvaluationResult:
    """Evaluate declared network residuals from explicit values and callbacks.

    Parameters
    ----------
    assembly
        NetworkResidualAssembly from Phase 13F.  Provides unknown and residual
        declaration names, units, and insertion order.  Must not be mutated.
    unknown_values
        NetworkUnknownValues mapping each declared unknown name to its trial
        numeric value.  Keys must match assembly unknown declarations exactly
        (no extra keys, no missing keys).
    evaluators
        Sequence of NetworkResidualEvaluator.  One evaluator per declared
        residual.  Names must match assembly residual declarations exactly
        (no extras, no missing, no duplicates).
    scales
        Mapping[str, float] from residual declaration name to characteristic
        scale.  Keys must match assembly residual declarations exactly.
        Values must be finite, strictly positive, non-bool.

    Returns
    -------
    NetworkResidualEvaluationResult
        Contains the original inputs, a ResidualEvaluation tuple in assembly
        declaration order, a ResidualVector, scaled norms, and l2 norm.

    Raises
    ------
    TypeError
        If assembly, unknown_values, or any evaluator has the wrong type.
        If evaluators is a Mapping (must be a Sequence).
        If any scale value is not numeric.
    ValueError
        If unknown value keys do not match assembly unknown declarations.
        If evaluator names do not match assembly residual declarations.
        If scale keys do not match assembly residual declarations.
        If any scale value is zero, negative, nan, inf, or bool.
        If any callback returns bool, non-numeric, or non-finite.

    Notes
    -----
    - Callback exceptions propagate without being swallowed.
    - Residual declaration order from the assembly is always preserved.
    - This function MUST NOT solve the network, iterate toward a zero, or
      execute component physics.  It is a pure evaluation layer.
    """
    # --- validate assembly ---
    if not isinstance(assembly, NetworkResidualAssembly):
        raise TypeError(
            "evaluate_network_residuals: assembly must be a NetworkResidualAssembly; "
            f"got {type(assembly).__name__!r}"
        )

    # --- validate unknown_values ---
    if not isinstance(unknown_values, NetworkUnknownValues):
        raise TypeError(
            "evaluate_network_residuals: unknown_values must be a NetworkUnknownValues; "
            f"got {type(unknown_values).__name__!r}"
        )
    declared_unknown_names: set[str] = set(assembly.unknowns.names())
    provided_unknown_names: set[str] = set(unknown_values.values.keys())
    missing_unknowns = declared_unknown_names - provided_unknown_names
    if missing_unknowns:
        raise ValueError(
            "evaluate_network_residuals: unknown_values missing for declared unknowns: "
            f"{sorted(missing_unknowns)!r}"
        )
    extra_unknowns = provided_unknown_names - declared_unknown_names
    if extra_unknowns:
        raise ValueError(
            "evaluate_network_residuals: unknown_values contain names not in assembly "
            f"declarations: {sorted(extra_unknowns)!r}"
        )

    # --- validate evaluators ---
    if isinstance(evaluators, Mapping):
        raise TypeError(
            "evaluate_network_residuals: evaluators must be a Sequence of "
            "NetworkResidualEvaluator, not a Mapping"
        )
    try:
        evaluator_list: list[NetworkResidualEvaluator] = list(evaluators)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(
            "evaluate_network_residuals: evaluators must be iterable; "
            f"got {type(evaluators).__name__!r}"
        ) from exc

    for i, ev in enumerate(evaluator_list):
        if not isinstance(ev, NetworkResidualEvaluator):
            raise TypeError(
                f"evaluate_network_residuals: evaluators[{i}] must be a "
                f"NetworkResidualEvaluator; got {type(ev).__name__!r}"
            )

    seen_ev: set[str] = set()
    for ev in evaluator_list:
        if ev.name in seen_ev:
            raise ValueError(f"evaluate_network_residuals: duplicate evaluator name {ev.name!r}")
        seen_ev.add(ev.name)

    declared_residual_names: set[str] = set(assembly.residuals.names())
    provided_evaluator_names: set[str] = {ev.name for ev in evaluator_list}
    missing_evaluators = declared_residual_names - provided_evaluator_names
    if missing_evaluators:
        raise ValueError(
            "evaluate_network_residuals: evaluators missing for declared residuals: "
            f"{sorted(missing_evaluators)!r}"
        )
    extra_evaluators = provided_evaluator_names - declared_residual_names
    if extra_evaluators:
        raise ValueError(
            "evaluate_network_residuals: evaluators contain names not in assembly "
            f"residual declarations: {sorted(extra_evaluators)!r}"
        )

    # --- validate scales ---
    if not hasattr(scales, "keys") or not hasattr(scales, "__getitem__"):
        raise TypeError(
            "evaluate_network_residuals: scales must be a Mapping[str, float]; "
            f"got {type(scales).__name__!r}"
        )
    scale_keys: set[str] = set(scales.keys())  # type: ignore[union-attr]
    missing_scales = declared_residual_names - scale_keys
    if missing_scales:
        raise ValueError(
            "evaluate_network_residuals: scales missing for declared residuals: "
            f"{sorted(missing_scales)!r}"
        )
    extra_scales = scale_keys - declared_residual_names
    if extra_scales:
        raise ValueError(
            "evaluate_network_residuals: scales contain names not in assembly "
            f"residual declarations: {sorted(extra_scales)!r}"
        )
    for res_name in assembly.residuals.names():
        scale_val = scales[res_name]  # type: ignore[index]
        if isinstance(scale_val, bool):
            raise ValueError(
                f"evaluate_network_residuals: scale for {res_name!r} must not be "
                f"bool; got {scale_val!r}"
            )
        if not isinstance(scale_val, (int, float)):
            raise TypeError(
                f"evaluate_network_residuals: scale for {res_name!r} must be "
                f"numeric; got {type(scale_val).__name__!r}"
            )
        fscale = float(scale_val)
        if not math.isfinite(fscale):
            raise ValueError(
                f"evaluate_network_residuals: scale for {res_name!r} must be "
                f"finite; got {scale_val!r}"
            )
        if fscale <= 0.0:
            raise ValueError(
                f"evaluate_network_residuals: scale for {res_name!r} must be "
                f"> 0; got {scale_val!r}"
            )

    # --- build evaluator lookup ---
    evaluator_by_name: dict[str, NetworkResidualEvaluator] = {ev.name: ev for ev in evaluator_list}

    # --- evaluate each residual in assembly declaration order ---
    values_proxy: MappingProxyType = unknown_values.values
    evaluations: list[ResidualEvaluation] = []

    for res_decl in assembly.residuals.residuals:
        evaluator = evaluator_by_name[res_decl.name]
        # Callback exceptions propagate without being swallowed.
        raw_value = evaluator.callback(values_proxy)

        if isinstance(raw_value, bool):
            raise ValueError(
                f"evaluate_network_residuals: callback for {res_decl.name!r} "
                f"returned bool; got {raw_value!r}"
            )
        if not isinstance(raw_value, (int, float)):
            raise TypeError(
                f"evaluate_network_residuals: callback for {res_decl.name!r} "
                f"returned non-numeric; got {type(raw_value).__name__!r}"
            )
        if not math.isfinite(float(raw_value)):
            raise ValueError(
                f"evaluate_network_residuals: callback for {res_decl.name!r} "
                f"returned non-finite; got {raw_value!r}"
            )

        scale = float(scales[res_decl.name])  # type: ignore[index]
        spec = ResidualSpec(name=res_decl.name, unit=res_decl.unit, scale=scale)
        ev_obj = ResidualEvaluation(spec=spec, value=float(raw_value))
        evaluations.append(ev_obj)

    # --- build residual vector and compute norms ---
    residual_vector = ResidualVector(evaluations=tuple(evaluations))
    scaled_vals: tuple[float, ...] = residual_vector.scaled_values()
    max_abs: float = residual_vector.max_abs_scaled()
    l2: float = residual_vector.l2_scaled()

    return NetworkResidualEvaluationResult(
        assembly=assembly,
        unknown_values=unknown_values,
        evaluations=tuple(evaluations),
        residual_vector=residual_vector,
        scaled_values=scaled_vals,
        max_abs_scaled=max_abs,
        l2_scaled=l2,
    )
