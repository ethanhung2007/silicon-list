from silicon_list.config import Config
from silicon_list.main import build_hybrid_stages, build_legacy_providers


def provider_names(stage_providers):
    return [provider.__class__.__name__ for _, provider in stage_providers]


def stage_names(stage_providers):
    return [stage for stage, _ in stage_providers]


def test_hybrid_live_default_all_splits_stage1_and_stage2():
    config = Config(cowork_stage2=True)

    stages = build_hybrid_stages(config, "mock", "live", False, None)

    assert provider_names(stages) == [
        "GitHubSimplifyProvider",
        "CoworkProvider",
    ]
    assert stage_names(stages) == ["stage1", "stage2"]


def test_hybrid_can_disable_cowork_stage2_for_stage1_lead_pass():
    config = Config(cowork_stage2=False)

    stages = build_hybrid_stages(config, "all", "live", False, None)

    assert provider_names(stages) == [
        "GitHubSimplifyProvider",
    ]


def test_google_and_searxng_are_explicit_only():
    assert provider_names(build_hybrid_stages(Config(), "google", "live", False, None)) == ["GoogleSearchProvider"]
    assert provider_names(build_hybrid_stages(Config(), "searxng", "live", False, None)) == ["SearXNGSearchProvider"]


def test_hybrid_all_includes_google_when_configured(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "key")
    monkeypatch.setenv("GOOGLE_CSE_ID", "cse")

    stages = build_hybrid_stages(Config(cowork_stage2=False), "all", "live", False, None)

    assert provider_names(stages) == [
        "GitHubSimplifyProvider",
        "GoogleSearchProvider",
    ]


def test_legacy_preserves_live_default_github_behavior():
    stages = build_legacy_providers(Config(), "mock", "live", False, None)

    assert provider_names(stages) == ["GitHubSimplifyProvider"]
    assert stage_names(stages) == ["legacy"]
