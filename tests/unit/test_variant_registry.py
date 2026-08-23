from research_assistant.variants import VARIANT_REGISTRY, Variant
from research_assistant.variants.agentic.run import run as run_agentic


def test_agentic_variant_is_registered():
    assert Variant.agentic in VARIANT_REGISTRY
    assert VARIANT_REGISTRY[Variant.agentic] is run_agentic
