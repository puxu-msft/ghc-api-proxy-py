from app.model_provider.ghc_client import (
    GhcClientConfig,
    build_identity_headers,
    build_request_headers,
)

CONFIG = GhcClientConfig(
    vscode_version="1.2.3",
    copilot_version="4.5.6",
    api_version="2025-05-01",
)


def test_identity_headers_carry_configured_versions() -> None:
    headers = build_identity_headers(CONFIG)
    assert headers["editor-version"] == "vscode/1.2.3"
    assert headers["editor-plugin-version"] == "copilot-chat/4.5.6"
    assert headers["user-agent"] == "GitHubCopilotChat/4.5.6"


def test_request_headers_include_identity_and_auth() -> None:
    headers = build_request_headers(
        "copilot-token",
        CONFIG,
        interaction_id="interaction",
        request_id="request",
    )
    assert headers["Authorization"] == "Bearer copilot-token"
    assert headers["editor-version"] == "vscode/1.2.3"
    assert headers["x-github-api-version"] == "2025-05-01"
    assert headers["x-request-id"] == "request"
    assert headers["X-Interaction-Id"] == "interaction"
    assert headers["X-Agent-Task-Id"] == "request"


def test_request_id_defaults_to_a_fresh_value_per_call() -> None:
    first = build_request_headers("t", CONFIG, interaction_id="i")
    second = build_request_headers("t", CONFIG, interaction_id="i")
    assert first["x-request-id"] != second["x-request-id"]


def test_vision_flag_is_opt_in() -> None:
    without = build_request_headers("t", CONFIG, interaction_id="i")
    with_vision = build_request_headers("t", CONFIG, interaction_id="i", vision=True)
    assert "copilot-vision-request" not in without
    assert with_vision["copilot-vision-request"] == "true"


def test_model_headers_cannot_override_protected_fields_case_insensitively() -> None:
    headers = build_request_headers(
        "copilot-token",
        CONFIG,
        interaction_id="interaction",
        model_request_headers={
            "AUTHORIZATION": "Bearer attacker",
            "x-interaction-id": "attacker",
            "Editor-Version": "vscode/0.0.0",
            "x-model-extra": "kept",
        },
    )
    # Asserting on the original casing alone would pass even without the protection.
    # Dict keys are case sensitive, so the attacker entry would simply land beside it.
    values = set(headers.values())
    assert "Bearer attacker" not in values
    assert "attacker" not in values
    assert "vscode/0.0.0" not in values

    assert headers["Authorization"] == "Bearer copilot-token"
    assert headers["X-Interaction-Id"] == "interaction"
    assert headers["editor-version"] == "vscode/1.2.3"
    assert headers["x-model-extra"] == "kept"
