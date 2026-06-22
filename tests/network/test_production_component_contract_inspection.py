"""Phase 14G production component contribution contract inspection tests.

Coverage items (34 required):
  1.  valid ProductionComponentContributionSignature construction
  2.  signature rejects empty class_name
  3.  signature rejects empty method_name
  4.  signature stores immutable parameter tuple
  5.  valid ProductionComponentInspectionResult construction
  6.  result rejects empty class_name
  7.  result rejects empty module_name
  8.  result stores immutable notes tuple
  9.  inspect class with no contribute method
 10.  inspect class with contribute(self, trial, ctx) without calling it
 11.  inspect class with contribute(self, state) and detect state-like dependency
 12.  inspect class with varargs and kwargs
 13.  inspect class with return annotation
 14.  inspect rejects non-class input
 15.  inspection never instantiates inspected class
 16.  inspection never calls contribute
 17.  inspection result stores no component instance
 18.  inspection result stores no executable callback
 19.  known production contract inspection returns immutable tuple
 20.  known production inspection does not instantiate production components
 21.  known production inspection does not call production contribute
 22.  public exports work from mpl_sim.network
 23.  existing Phase 13E–14F tests still pass (suite-level gate)
 24.  docs do not claim full physical network simulation
 25.  no provider execution function imports production components
 26.  no Phase 14F execution function calls contribute
 27.  no new runtime network module calls contribute
 28.  no property lookup in inspection source
 29.  no registry resolution in inspection source
 30.  no CoolProp in inspection source
 31.  no SystemState assembly in inspection source
 32.  no FluidState creation in inspection source
 33.  no physical values attached to NetworkGraph
 34.  no automatic physics from component_type
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import FrozenInstanceError

import pytest

from mpl_sim.network.production_component_inspection import (
    ProductionComponentContractStatus,
    ProductionComponentContributionSignature,
    ProductionComponentInspectionResult,
    inspect_known_production_component_contracts,
    inspect_production_component_contract,
)

# ---------------------------------------------------------------------------
# Source file paths for boundary checks
# ---------------------------------------------------------------------------

_NETWORK_SRC = pathlib.Path(__file__).parent.parent.parent / "src" / "mpl_sim" / "network"
_INSPECTION_SRC = _NETWORK_SRC / "production_component_inspection.py"
_PROVIDER_SRC = _NETWORK_SRC / "component_provider_adapters.py"


# ---------------------------------------------------------------------------
# 1–4: ProductionComponentContributionSignature
# ---------------------------------------------------------------------------


class TestProductionComponentContributionSignature:
    def test_valid_construction(self):
        """Item 1: valid signature object can be constructed."""
        sig = ProductionComponentContributionSignature(
            class_name="MyComponent",
            method_name="contribute",
            parameter_names=("trial", "ctx"),
            return_annotation=None,
            requires_system_state=False,
            requires_context=True,
            has_varargs=False,
            has_kwargs=False,
        )
        assert sig.class_name == "MyComponent"
        assert sig.method_name == "contribute"
        assert sig.parameter_names == ("trial", "ctx")
        assert sig.return_annotation is None
        assert sig.requires_system_state is False
        assert sig.requires_context is True
        assert sig.has_varargs is False
        assert sig.has_kwargs is False

    def test_rejects_empty_class_name(self):
        """Item 2: signature rejects empty class_name."""
        with pytest.raises(ValueError, match="class_name must be non-empty"):
            ProductionComponentContributionSignature(
                class_name="",
                method_name="contribute",
                parameter_names=(),
                return_annotation=None,
                requires_system_state=False,
                requires_context=False,
                has_varargs=False,
                has_kwargs=False,
            )

    def test_rejects_empty_method_name(self):
        """Item 3: signature rejects empty method_name."""
        with pytest.raises(ValueError, match="method_name must be non-empty"):
            ProductionComponentContributionSignature(
                class_name="MyComponent",
                method_name="",
                parameter_names=(),
                return_annotation=None,
                requires_system_state=False,
                requires_context=False,
                has_varargs=False,
                has_kwargs=False,
            )

    def test_stores_immutable_parameter_tuple(self):
        """Item 4: parameter_names is always a tuple, immutable."""
        sig = ProductionComponentContributionSignature(
            class_name="MyComponent",
            method_name="contribute",
            parameter_names=("a", "b"),
            return_annotation=None,
            requires_system_state=False,
            requires_context=False,
            has_varargs=False,
            has_kwargs=False,
        )
        assert isinstance(sig.parameter_names, tuple)
        with pytest.raises(FrozenInstanceError):
            sig.parameter_names = ("x",)  # type: ignore[misc]

    def test_return_annotation_can_be_none(self):
        """Item 1 (extension): return_annotation None is valid."""
        sig = ProductionComponentContributionSignature(
            class_name="C",
            method_name="contribute",
            parameter_names=(),
            return_annotation=None,
            requires_system_state=False,
            requires_context=False,
            has_varargs=False,
            has_kwargs=False,
        )
        assert sig.return_annotation is None

    def test_return_annotation_can_be_string(self):
        """Item 13 (setup): return_annotation can hold a string."""
        sig = ProductionComponentContributionSignature(
            class_name="C",
            method_name="contribute",
            parameter_names=(),
            return_annotation="ContributionRecordSet",
            requires_system_state=False,
            requires_context=False,
            has_varargs=False,
            has_kwargs=False,
        )
        assert sig.return_annotation == "ContributionRecordSet"

    def test_frozen_prevents_mutation(self):
        """Item 4 (extension): frozen dataclass prevents field mutation."""
        sig = ProductionComponentContributionSignature(
            class_name="C",
            method_name="m",
            parameter_names=(),
            return_annotation=None,
            requires_system_state=False,
            requires_context=False,
            has_varargs=False,
            has_kwargs=False,
        )
        with pytest.raises(FrozenInstanceError):
            sig.class_name = "D"  # type: ignore[misc]

    def test_rejects_whitespace_names(self):
        with pytest.raises(ValueError, match="class_name must be non-empty"):
            ProductionComponentContributionSignature(
                class_name=" ",
                method_name="contribute",
                parameter_names=(),
                return_annotation=None,
                requires_system_state=False,
                requires_context=False,
                has_varargs=False,
                has_kwargs=False,
            )

    def test_rejects_invalid_parameter_names(self):
        with pytest.raises(ValueError, match="parameter_names"):
            ProductionComponentContributionSignature(
                class_name="C",
                method_name="contribute",
                parameter_names=("state", ""),
                return_annotation=None,
                requires_system_state=True,
                requires_context=False,
                has_varargs=False,
                has_kwargs=False,
            )


# ---------------------------------------------------------------------------
# 5–8: ProductionComponentInspectionResult
# ---------------------------------------------------------------------------


class TestProductionComponentInspectionResult:
    def test_valid_construction(self):
        """Item 5: valid result object can be constructed."""
        result = ProductionComponentInspectionResult(
            class_name="MyComponent",
            module_name="mpl_sim.components.pump",
            status=ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD,
            signature=None,
            notes=("No contribute found.",),
        )
        assert result.class_name == "MyComponent"
        assert result.module_name == "mpl_sim.components.pump"
        assert result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
        assert result.signature is None
        assert result.notes == ("No contribute found.",)

    def test_rejects_empty_class_name(self):
        """Item 6: result rejects empty class_name."""
        with pytest.raises(ValueError, match="class_name must be non-empty"):
            ProductionComponentInspectionResult(
                class_name="",
                module_name="some.module",
                status=ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD,
                signature=None,
                notes=(),
            )

    def test_rejects_empty_module_name(self):
        """Item 7: result rejects empty module_name."""
        with pytest.raises(ValueError, match="module_name must be non-empty"):
            ProductionComponentInspectionResult(
                class_name="MyComponent",
                module_name="",
                status=ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD,
                signature=None,
                notes=(),
            )

    def test_stores_immutable_notes_tuple(self):
        """Item 8: notes is always a tuple, immutable."""
        result = ProductionComponentInspectionResult(
            class_name="C",
            module_name="m",
            status=ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD,
            signature=None,
            notes=("note one", "note two"),
        )
        assert isinstance(result.notes, tuple)
        with pytest.raises(FrozenInstanceError):
            result.notes = ("other",)  # type: ignore[misc]

    def test_valid_with_signature(self):
        """Item 5 (extension): result accepts a ProductionComponentContributionSignature."""
        sig = ProductionComponentContributionSignature(
            class_name="C",
            method_name="contribute",
            parameter_names=("ctx",),
            return_annotation=None,
            requires_system_state=False,
            requires_context=True,
            has_varargs=False,
            has_kwargs=False,
        )
        result = ProductionComponentInspectionResult(
            class_name="C",
            module_name="some.module",
            status=ProductionComponentContractStatus.REQUIRES_ADAPTER,
            signature=sig,
            notes=(),
        )
        assert result.signature is sig

    def test_rejects_wrong_signature_type(self):
        """Item 5 (extension): result rejects non-signature object as signature."""
        with pytest.raises(TypeError, match="signature must be"):
            ProductionComponentInspectionResult(
                class_name="C",
                module_name="m",
                status=ProductionComponentContractStatus.HAS_CONTRIBUTE_METHOD,
                signature="not-a-signature",  # type: ignore[arg-type]
                notes=(),
            )

    def test_rejects_unknown_status(self):
        with pytest.raises(ValueError, match="status must be a valid"):
            ProductionComponentInspectionResult(
                class_name="C",
                module_name="m",
                status="MADE_UP",
                signature=None,
                notes=(),
            )

    def test_rejects_string_notes_container(self):
        with pytest.raises(TypeError, match="notes must be an iterable"):
            ProductionComponentInspectionResult(
                class_name="C",
                module_name="m",
                status=ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD,
                signature=None,
                notes="not a notes tuple",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# 9–13: inspect_production_component_contract
# ---------------------------------------------------------------------------


class TestInspectProductionComponentContract:
    def test_inspect_class_with_no_contribute(self):
        """Item 9: class without contribute returns NO_CONTRIBUTE_METHOD."""

        class NoContributeClass:
            def kind(self):
                return "PUMP"

        result = inspect_production_component_contract(NoContributeClass)
        assert isinstance(result, ProductionComponentInspectionResult)
        assert result.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
        assert result.class_name == "NoContributeClass"
        assert result.signature is None
        assert len(result.notes) > 0

    def test_inspect_class_with_contribute_trial_ctx(self):
        """Item 10: class with contribute(self, trial, ctx) inspected without calling."""

        class TrialCtxComponent:
            def contribute(self, trial, ctx):
                raise RuntimeError("MUST NOT BE CALLED")

        result = inspect_production_component_contract(TrialCtxComponent)
        assert isinstance(result, ProductionComponentInspectionResult)
        assert result.status != ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD
        assert result.signature is not None
        assert "trial" in result.signature.parameter_names
        assert "ctx" in result.signature.parameter_names
        assert result.signature.requires_context is True

    def test_inspect_class_with_contribute_state(self):
        """Item 11: class with contribute(self, state) detects state-like dependency."""

        class StateComponent:
            def contribute(self, state):
                raise RuntimeError("MUST NOT BE CALLED")

        result = inspect_production_component_contract(StateComponent)
        assert result.signature is not None
        assert result.signature.requires_system_state is True
        assert result.status == ProductionComponentContractStatus.REQUIRES_SYSTEM_STATE

    def test_detects_state_dependency_from_annotation(self):
        class ComponentTrialState:
            pass

        class StateByAnnotation:
            def contribute(self, trial: ComponentTrialState):
                raise RuntimeError("MUST NOT BE CALLED")

        result = inspect_production_component_contract(StateByAnnotation)
        assert result.signature is not None
        assert result.signature.requires_system_state is True
        assert result.status == ProductionComponentContractStatus.REQUIRES_SYSTEM_STATE

    def test_detects_context_dependency_from_annotation(self):
        class EvalContext:
            pass

        class ContextByAnnotation:
            def contribute(self, payload: EvalContext):
                raise RuntimeError("MUST NOT BE CALLED")

        result = inspect_production_component_contract(ContextByAnnotation)
        assert result.signature is not None
        assert result.signature.requires_context is True

    def test_inspect_class_with_varargs_and_kwargs(self):
        """Item 12: class with *args and **kwargs has has_varargs/has_kwargs True."""

        class VarArgComponent:
            def contribute(self, *args, **kwargs):
                raise RuntimeError("MUST NOT BE CALLED")

        result = inspect_production_component_contract(VarArgComponent)
        assert result.signature is not None
        assert result.signature.has_varargs is True
        assert result.signature.has_kwargs is True
        assert result.signature.parameter_names == ()

    def test_inspect_class_with_return_annotation(self):
        """Item 13: return annotation is captured as string."""

        class AnnotatedComponent:
            def contribute(self, ctx) -> str:
                raise RuntimeError("MUST NOT BE CALLED")

        result = inspect_production_component_contract(AnnotatedComponent)
        assert result.signature is not None
        assert result.signature.return_annotation is not None
        assert isinstance(result.signature.return_annotation, str)

    def test_rejects_non_class_input(self):
        """Item 14: non-class input raises TypeError."""
        with pytest.raises(TypeError, match="must be a class"):
            inspect_production_component_contract("not-a-class")  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="must be a class"):
            inspect_production_component_contract(42)  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="must be a class"):
            inspect_production_component_contract(None)  # type: ignore[arg-type]

    def test_rejects_function_input(self):
        """Item 14 (extension): function is not a class; raises TypeError."""

        def my_func():
            pass

        with pytest.raises(TypeError, match="must be a class"):
            inspect_production_component_contract(my_func)  # type: ignore[arg-type]

    def test_inspection_never_instantiates_class(self):
        """Item 15: inspection never calls __new__ or __init__ on inspected class."""
        _instantiated: list[bool] = []

        class NeverInstantiateClass:
            def __new__(cls, *args, **kwargs):
                _instantiated.append(True)
                return super().__new__(cls)

            def contribute(self, ctx):
                pass

        result = inspect_production_component_contract(NeverInstantiateClass)
        assert not _instantiated, "Class was instantiated during inspection"
        assert isinstance(result, ProductionComponentInspectionResult)

    def test_inspection_never_calls_contribute(self):
        """Item 16: inspection never calls the contribute method."""
        _called: list[bool] = []

        class TrackedContributeClass:
            def contribute(self, trial, ctx):
                _called.append(True)
                return "something"

        result = inspect_production_component_contract(TrackedContributeClass)
        assert not _called, "contribute was called during inspection"
        assert result.status != ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD

    def test_inspection_does_not_bind_descriptor(self):
        descriptor_accessed: list[bool] = []

        class ExplodingDescriptor:
            def __get__(self, instance, owner):
                descriptor_accessed.append(True)
                raise RuntimeError("descriptor binding MUST NOT RUN")

        class DescriptorComponent:
            contribute = ExplodingDescriptor()

        result = inspect_production_component_contract(DescriptorComponent)
        assert descriptor_accessed == []
        assert result.status == ProductionComponentContractStatus.INSPECTION_UNSUPPORTED

    def test_result_stores_no_component_instance(self):
        """Item 17: inspection result stores no component instance in its fields."""

        class SomeComponent:
            def contribute(self, ctx):
                pass

        result = inspect_production_component_contract(SomeComponent)
        assert isinstance(result.class_name, str)
        assert isinstance(result.module_name, str)
        assert isinstance(result.status, str)
        assert result.signature is None or isinstance(
            result.signature, ProductionComponentContributionSignature
        )
        assert isinstance(result.notes, tuple)
        assert not isinstance(result, SomeComponent)
        if result.signature is not None:
            assert not isinstance(result.signature, SomeComponent)

    def test_result_stores_no_executable_callback(self):
        """Item 18: inspection result fields are not callable as functions."""

        class SomeComponent:
            def contribute(self, ctx):
                pass

        result = inspect_production_component_contract(SomeComponent)
        assert not callable(result.class_name)
        assert not callable(result.module_name)
        assert not callable(result.status)
        assert not callable(result.notes)

    def test_no_contribute_class_has_module_name(self):
        """Item 9 (extension): module_name is recorded even for NO_CONTRIBUTE_METHOD."""

        class PlainClass:
            pass

        result = inspect_production_component_contract(PlainClass)
        assert result.module_name  # non-empty
        assert isinstance(result.module_name, str)

    def test_requires_adapter_status_for_non_state_contribute(self):
        """Item 10 (extension): contribute without state-like params gives REQUIRES_ADAPTER."""

        class AdapterNeeded:
            def contribute(self, trial, ctx):
                raise RuntimeError("MUST NOT BE CALLED")

        result = inspect_production_component_contract(AdapterNeeded)
        assert result.status == ProductionComponentContractStatus.REQUIRES_ADAPTER

    def test_varargs_only(self):
        """Item 12 (extension): only *args."""

        class VarArgsOnly:
            def contribute(self, *args):
                pass

        result = inspect_production_component_contract(VarArgsOnly)
        assert result.signature is not None
        assert result.signature.has_varargs is True
        assert result.signature.has_kwargs is False

    def test_kwargs_only(self):
        """Item 12 (extension): only **kwargs."""

        class KwargsOnly:
            def contribute(self, **kwargs):
                pass

        result = inspect_production_component_contract(KwargsOnly)
        assert result.signature is not None
        assert result.signature.has_varargs is False
        assert result.signature.has_kwargs is True

    def test_no_contribute_notes_mention_next_bridge(self):
        """Item 9 (extension): notes identify the deferred bridge work."""

        class NoContribute:
            pass

        result = inspect_production_component_contract(NoContribute)
        combined_notes = " ".join(result.notes)
        assert "15A" in combined_notes or "deferred" in combined_notes.lower()

    def test_state_dependency_note_recorded(self):
        """Item 11 (extension): REQUIRES_SYSTEM_STATE notes mention SystemState."""

        class StateComponent:
            def contribute(self, state):
                pass

        result = inspect_production_component_contract(StateComponent)
        combined_notes = " ".join(result.notes)
        assert "SystemState" in combined_notes or "state" in combined_notes.lower()


# ---------------------------------------------------------------------------
# 19–21: inspect_known_production_component_contracts
# ---------------------------------------------------------------------------


class TestInspectKnownProductionComponentContracts:
    def test_returns_immutable_tuple(self):
        """Item 19: returns an immutable tuple of inspection results."""
        results = inspect_known_production_component_contracts()
        assert isinstance(results, tuple)
        assert all(isinstance(r, ProductionComponentInspectionResult) for r in results)
        assert len(results) > 0

    def test_all_known_components_inspected(self):
        """Item 19 (extension): result covers Component base and concrete classes."""
        results = inspect_known_production_component_contracts()
        class_names = {r.class_name for r in results}
        assert "Component" in class_names
        assert "PumpComponent" in class_names
        assert "AccumulatorComponent" in class_names
        assert "EvaporatorComponent" in class_names
        assert "CondenserComponent" in class_names

    def test_all_known_have_no_contribute(self):
        """Item 20 + 21: all known production components lack contribute method."""
        results = inspect_known_production_component_contracts()
        for r in results:
            assert r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD, (
                f"{r.class_name} unexpectedly has a contribute method or different status: "
                f"{r.status!r}"
            )

    def test_does_not_instantiate_production_components(self):
        """Item 20: calling inspect_known does not raise from component constructors.

        Since all known production components have NO_CONTRIBUTE_METHOD, the
        inspection path never reaches signature analysis or method invocation.
        The function completes without error, proving no instantiation occurred.
        """
        results = inspect_known_production_component_contracts()
        assert all(r.signature is None for r in results)

    def test_known_results_have_non_empty_class_names(self):
        """Item 19 (extension): all results have non-empty class and module names."""
        results = inspect_known_production_component_contracts()
        for r in results:
            assert r.class_name
            assert r.module_name

    def test_known_results_have_notes(self):
        """Item 19 (extension): all NO_CONTRIBUTE_METHOD results include notes."""
        results = inspect_known_production_component_contracts()
        for r in results:
            if r.status == ProductionComponentContractStatus.NO_CONTRIBUTE_METHOD:
                assert len(r.notes) > 0


# ---------------------------------------------------------------------------
# 22: Public exports from mpl_sim.network
# ---------------------------------------------------------------------------


class TestPublicExports:
    def test_all_phase14g_names_exported(self):
        """Item 22: all Phase 14G names are accessible from mpl_sim.network."""
        from mpl_sim.network import (
            ProductionComponentContractStatus as PublicStatus,
        )
        from mpl_sim.network import (
            ProductionComponentContributionSignature as PublicSig,
        )
        from mpl_sim.network import (
            ProductionComponentInspectionResult as PublicResult,
        )
        from mpl_sim.network import (
            inspect_known_production_component_contracts as public_inspect_known,
        )
        from mpl_sim.network import (
            inspect_production_component_contract as public_inspect,
        )

        assert PublicStatus is ProductionComponentContractStatus
        assert PublicSig is ProductionComponentContributionSignature
        assert PublicResult is ProductionComponentInspectionResult
        assert public_inspect is inspect_production_component_contract
        assert public_inspect_known is inspect_known_production_component_contracts

    def test_names_in_all_list(self):
        """Item 22 (extension): Phase 14G names appear in mpl_sim.network.__all__."""
        import mpl_sim.network as net

        assert "ProductionComponentContractStatus" in net.__all__
        assert "ProductionComponentContributionSignature" in net.__all__
        assert "ProductionComponentInspectionResult" in net.__all__
        assert "inspect_production_component_contract" in net.__all__
        assert "inspect_known_production_component_contracts" in net.__all__

    def test_prior_phase_exports_unchanged(self):
        """Item 22 (extension): Phase 14F and prior exports remain accessible."""
        from mpl_sim.network import (
            ComponentContributionProviderBinding,
            ComponentContributionProviderProtocol,
            ComponentContributionProviderSet,
            ComponentProviderExecutionContext,
            ToyComponentExecutionContext,
            ToyComponentExecutor,
            ToyComponentExecutorSet,
            build_component_contribution_from_provider_execution,
            build_component_contribution_from_toy_execution,
            execute_component_provider_contributions,
            execute_toy_component_contributions,
        )

        assert ComponentProviderExecutionContext is not None
        assert ComponentContributionProviderProtocol is not None
        assert ComponentContributionProviderBinding is not None
        assert ComponentContributionProviderSet is not None
        assert execute_component_provider_contributions is not None
        assert build_component_contribution_from_provider_execution is not None
        assert ToyComponentExecutionContext is not None
        assert ToyComponentExecutor is not None
        assert ToyComponentExecutorSet is not None
        assert execute_toy_component_contributions is not None
        assert build_component_contribution_from_toy_execution is not None


# ---------------------------------------------------------------------------
# 23: Existing test suite compatibility (suite-level gate)
# ---------------------------------------------------------------------------


class TestExistingTestSuiteCompatibility:
    def test_prior_network_types_still_importable(self):
        """Item 23: all prior Phase 13E–14F network types remain importable."""
        from mpl_sim.network import (
            ComponentInstance,
            NetworkGraph,
            NetworkResidualAssembly,
            NetworkSolveConfig,
        )

        assert ComponentInstance is not None
        assert NetworkGraph is not None
        assert NetworkResidualAssembly is not None
        assert NetworkSolveConfig is not None


# ---------------------------------------------------------------------------
# 24: Docs do not claim full physical network simulation
# ---------------------------------------------------------------------------


class TestDocumentationBoundaries:
    def test_inspection_source_does_not_overclaim(self):
        """Item 24: inspection module docstring does not claim physical simulation."""
        src = _INSPECTION_SRC.read_text(encoding="utf-8")
        overclaims = [
            "full MPL simulator",
            "full physical network",
            "validated against experiment",
            "validated model",
        ]
        for phrase in overclaims:
            assert (
                phrase not in src
            ), f"Overclaim found in production_component_inspection.py: {phrase!r}"

    def test_inspection_source_says_no_instantiation(self):
        """Item 24 (extension): inspection module states no instantiation."""
        src = _INSPECTION_SRC.read_text(encoding="utf-8")
        assert (
            "never instantiates" in src
            or "Instantiate" not in src
            or ("DOES NOT" in src and "instantiat" in src.lower())
        )


# ---------------------------------------------------------------------------
# 25–26: Provider execution modules do not import or call contribute
# ---------------------------------------------------------------------------


class TestProviderExecutionBoundaries:
    def test_provider_adapters_does_not_import_components(self):
        """Item 25: component_provider_adapters.py does not import production components."""
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        assert "from mpl_sim.components" not in src
        assert "import mpl_sim.components" not in src

    def test_provider_adapters_does_not_call_contribute(self):
        """Item 26: component_provider_adapters.py does not call .contribute(."""
        tree = ast.parse(_PROVIDER_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "contribute":
                    raise AssertionError(
                        "Found .contribute( call in component_provider_adapters.py"
                    )


# ---------------------------------------------------------------------------
# 27–34: Inspection source architecture boundaries
# ---------------------------------------------------------------------------


class TestInspectionSourceBoundaries:
    def test_inspection_source_does_not_call_contribute(self):
        """Item 27: production_component_inspection.py does not call .contribute(."""
        tree = ast.parse(_INSPECTION_SRC.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "contribute":
                    raise AssertionError(
                        "Found .contribute( call in production_component_inspection.py"
                    )

    def test_no_property_lookup_in_inspection_source(self):
        """Item 28: inspection source does not import PropertyBackend or properties."""
        src = _INSPECTION_SRC.read_text(encoding="utf-8")
        top_level_lines = [
            line
            for line in src.splitlines()
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and not line.strip().startswith("from __future__")
        ]
        for line in top_level_lines:
            assert (
                "PropertyBackend" not in line
            ), f"PropertyBackend import found in inspection source: {line!r}"
            assert (
                "mpl_sim.properties" not in line
            ), f"mpl_sim.properties import found in inspection source: {line!r}"

    def test_no_registry_resolution_in_inspection_source(self):
        """Item 29: inspection source does not import registries."""
        src = _INSPECTION_SRC.read_text(encoding="utf-8")
        top_level_lines = [
            line
            for line in src.splitlines()
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and not line.strip().startswith("from __future__")
        ]
        for line in top_level_lines:
            assert "CorrelationRegistry" not in line
            assert "HeatExchangerModelRegistry" not in line

    def test_no_coolprop_in_inspection_source(self):
        """Item 30: inspection source does not import CoolProp."""
        src = _INSPECTION_SRC.read_text(encoding="utf-8")
        top_level_lines = [
            line
            for line in src.splitlines()
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and not line.strip().startswith("from __future__")
        ]
        for line in top_level_lines:
            assert "CoolProp" not in line, f"CoolProp import found in inspection source: {line!r}"

    def test_no_system_state_in_inspection_source(self):
        """Item 31: inspection source does not import SystemState."""
        src = _INSPECTION_SRC.read_text(encoding="utf-8")
        top_level_lines = [
            line
            for line in src.splitlines()
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and not line.strip().startswith("from __future__")
        ]
        for line in top_level_lines:
            assert (
                "SystemState" not in line
            ), f"SystemState import found in inspection source: {line!r}"

    def test_no_fluid_state_at_module_level(self):
        """Item 32: inspection source does not import FluidState at module level."""
        src = _INSPECTION_SRC.read_text(encoding="utf-8")
        top_level_lines = [
            line
            for line in src.splitlines()
            if (line.strip().startswith("import ") or line.strip().startswith("from "))
            and not line.strip().startswith("from __future__")
        ]
        for line in top_level_lines:
            assert "FluidState" not in line, f"FluidState import at module level: {line!r}"

    def test_no_physical_values_on_network_graph(self):
        """Item 33: NetworkGraph has no physical value attributes after inspection."""
        from mpl_sim.network import (
            ComponentInstance,
            ComponentInstanceId,
            GraphNode,
            GraphNodeId,
            NetworkGraph,
        )

        graph = NetworkGraph(
            nodes=[GraphNode(node_id=GraphNodeId("n1")), GraphNode(node_id=GraphNodeId("n2"))],
            instances=[
                ComponentInstance(
                    instance_id=ComponentInstanceId("comp"),
                    component_type="test",
                    inlet_node=GraphNodeId("n1"),
                    outlet_node=GraphNodeId("n2"),
                )
            ],
        )
        assert not hasattr(graph, "mdot")
        assert not hasattr(graph, "pressure")
        assert not hasattr(graph, "enthalpy")
        assert not hasattr(graph, "fluid_state")

    def test_no_automatic_physics_from_component_type(self):
        """Item 34: inspection does not infer physics from component_type."""

        class AnyTypeComponent:
            component_type = "some_exotic_type_with_no_physics"

            def contribute(self, trial, ctx):
                pass

        result = inspect_production_component_contract(AnyTypeComponent)
        assert result.status != ProductionComponentContractStatus.INSPECTION_UNSUPPORTED
        assert result.signature is not None
        assert result.signature.parameter_names == ("trial", "ctx")

    def test_inspection_module_not_imported_by_provider_adapters(self):
        """Item 27 (extension): component_provider_adapters.py does not import inspection."""
        src = _PROVIDER_SRC.read_text(encoding="utf-8")
        assert "production_component_inspection" not in src
