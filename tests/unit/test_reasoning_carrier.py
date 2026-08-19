import base64
import json

import pytest

from app.pipeline.translation_driver.reasoning_carrier import (
    PROJECT_SYNTHETIC_REASONING_SIGNATURE,
    PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    REASONING_ENCRYPTED_CONTENT_TAG,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    decode_reasoning_carrier,
    encode_reasoning_carrier,
)


def test_project_v1_canonical_encode_decode_round_trip() -> None:
    signature = encode_reasoning_carrier("opaque-😀")

    assert signature == (
        "ghc-api-proxy:synthetic-reasoning:v1:"
        "eyJ0YWciOiJvcGVuYWkucmVzcG9uc2VzLnJlYXNvbmluZy5lbmNyeXB0ZWRfY29udGVudCIs"
        "ImVuY3J5cHRlZF9jb250ZW50Ijoib3BhcXVlLfCfmIAifQ"
    )
    assert "=" not in signature.removeprefix(PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX)
    assert decode_reasoning_carrier(signature).encrypted_content == "opaque-😀"


def test_project_v1_consumer_accepts_semantic_json_variants() -> None:
    document = {
        "encrypted_content": "ENC==",
        "tag": REASONING_ENCRYPTED_CONTENT_TAG,
    }
    payload = base64.urlsafe_b64encode(
        json.dumps(document, indent=2).encode()
    ).decode().rstrip("=")

    decoded = decode_reasoning_carrier(
        f"{PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX}{payload}"
    )

    assert decoded.classification == "project_v1"
    assert decoded.encrypted_content == "ENC=="


def test_project_and_upstream_bare_carriers_preserve_summary_only_shape() -> None:
    assert decode_reasoning_carrier(
        PROJECT_SYNTHETIC_REASONING_SIGNATURE
    ).classification == "project_bare_v1"
    assert decode_reasoning_carrier(
        UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX
    ).classification == "upstream_bare_v1"
    assert decode_reasoning_carrier(
        UPSTREAM_SYNTHETIC_REASONING_SIGNATURE
    ).classification == "upstream_legacy_bare"


@pytest.mark.parametrize(
    ("encrypted_content", "payload"),
    [
        ("ENC==", "RU5DPT0"),
        ("opaque-😀", "b3BhcXVlLfCfmIA"),
    ],
)
def test_decodes_copilot_api_js_v1_main_path(
    encrypted_content: str,
    payload: str,
) -> None:
    decoded = decode_reasoning_carrier(
        f"{UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX}{payload}"
    )

    assert decoded.classification == "upstream_v1"
    assert decoded.encrypted_content == encrypted_content


@pytest.mark.parametrize(
    ("signature", "classification"),
    [
        (
            "ghc-api-proxy:synthetic-reasoning:v2:anything",
            "project_unknown_version",
        ),
        (
            f"{PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX}!!!",
            "project_malformed_v1",
        ),
        (
            f"{UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX}!!!",
            "upstream_malformed_v1",
        ),
        ("CAIS-foreign", "foreign"),
    ],
)
def test_unknown_malformed_and_foreign_have_minimal_stable_outcomes(
    signature: str,
    classification: str,
) -> None:
    decoded = decode_reasoning_carrier(signature)

    assert decoded.classification == classification
    assert decoded.encrypted_content is None
