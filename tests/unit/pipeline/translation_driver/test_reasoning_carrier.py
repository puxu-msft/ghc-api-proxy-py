import base64
import json

import pytest

from app.pipeline.translation_driver.reasoning_carrier import (
    ANTHROPIC_THINKING_SIGNATURE,
    CHAT_REASONING_CONTENT,
    PROJECT_SYNTHETIC_REASONING_SIGNATURE,
    PROJECT_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    PROJECT_SYNTHETIC_REASONING_V2_PREFIX,
    REASONING_ENCRYPTED_CONTENT_TAG,
    RESPONSES_ENCRYPTED_CONTENT,
    RESPONSES_SUMMARY_TEXT_LAYOUT,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE,
    UPSTREAM_SYNTHETIC_REASONING_SIGNATURE_PREFIX,
    CarrierRecord,
    decode_reasoning_carrier,
    encode_reasoning_carrier,
    encode_reasoning_carrier_v2,
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


def test_project_v2_producer_matches_independent_static_vector() -> None:
    signature = encode_reasoning_carrier_v2(
        [
            CarrierRecord(RESPONSES_ENCRYPTED_CONTENT, "ENC=="),
            CarrierRecord(
                RESPONSES_SUMMARY_TEXT_LAYOUT,
                {"lengths": [3, 0, 7], "extensions": [{}, {}, {}]},
            ),
        ]
    )

    assert signature == (
        "ghc-api-proxy:synthetic-reasoning:v2:"
        "eyJyZWNvcmRzIjpbeyJ0eXBlIjoib3BlbmFpLnJlc3BvbnNlcy5yZWFzb25pbmcuZW5jcnlwdGVkX2NvbnRlbnQiLCJ2YWx1ZSI6IkVOQz09In0seyJ0eXBlIjoib3BlbmFpLnJlc3BvbnNlcy5yZWFzb25pbmcuc3VtbWFyeV90ZXh0X2xheW91dCIsInZhbHVlIjp7Imxlbmd0aHMiOlszLDAsN10sImV4dGVuc2lvbnMiOlt7fSx7fSx7fV19fV19"
    )
    decoded = decode_reasoning_carrier(signature)
    assert decoded.classification == "project_v2"
    assert decoded.records == (
        CarrierRecord(RESPONSES_ENCRYPTED_CONTENT, "ENC=="),
        CarrierRecord(
            RESPONSES_SUMMARY_TEXT_LAYOUT,
            {"lengths": [3, 0, 7], "extensions": [{}, {}, {}]},
        ),
    )


def test_project_v2_unicode_bytes_match_independent_static_vector() -> None:
    signature = encode_reasoning_carrier_v2(
        [CarrierRecord(ANTHROPIC_THINKING_SIGNATURE, "CAIS-😀")]
    )
    assert signature == (
        "ghc-api-proxy:synthetic-reasoning:v2:"
        "eyJyZWNvcmRzIjpbeyJ0eXBlIjoiYW50aHJvcGljLm1lc3NhZ2VzLnRoaW5raW5nLnNpZ25hdHVyZSIsInZhbHVlIjoiQ0FJUy3wn5iAIn1dfQ"
    )


def test_project_v2_chat_origin_matches_independent_static_vector() -> None:
    signature = encode_reasoning_carrier_v2(
        [CarrierRecord(CHAT_REASONING_CONTENT, None)]
    )
    assert signature == (
        "ghc-api-proxy:synthetic-reasoning:v2:"
        "eyJyZWNvcmRzIjpbeyJ0eXBlIjoib3BlbmFpLmNoYXRfY29tcGxldGlvbnMucmVhc29uaW5nX2NvbnRlbnQiLCJ2YWx1ZSI6bnVsbH1dfQ"
    )


def test_project_v2_chat_origin_rejects_non_null_value() -> None:
    with pytest.raises(ValueError):
        encode_reasoning_carrier_v2(
            [CarrierRecord(CHAT_REASONING_CONTENT, "copied text")]
        )


def test_project_v2_preserves_present_empty_opaque_value() -> None:
    signature = encode_reasoning_carrier_v2(
        [
            CarrierRecord(RESPONSES_ENCRYPTED_CONTENT, ""),
            CarrierRecord(
                RESPONSES_SUMMARY_TEXT_LAYOUT,
                {"lengths": [], "extensions": []},
            ),
        ]
    )

    decoded = decode_reasoning_carrier(signature)
    record = decoded.record(RESPONSES_ENCRYPTED_CONTENT)
    assert record is not None
    assert record.value == ""


def test_v2_record_order_is_canonical() -> None:
    forward = encode_reasoning_carrier_v2(
        [
            CarrierRecord(RESPONSES_ENCRYPTED_CONTENT, "ENC"),
            CarrierRecord(ANTHROPIC_THINKING_SIGNATURE, "CAIS"),
        ]
    )
    reversed_input = encode_reasoning_carrier_v2(
        [
            CarrierRecord(ANTHROPIC_THINKING_SIGNATURE, "CAIS"),
            CarrierRecord(RESPONSES_ENCRYPTED_CONTENT, "ENC"),
        ]
    )
    assert forward == reversed_input


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
            "ghc-api-proxy:synthetic-reasoning:v3:anything",
            "project_unknown_version",
        ),
        (
            f"{PROJECT_SYNTHETIC_REASONING_V2_PREFIX}anything",
            "project_malformed_v2",
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


MALFORMED_V2_DOCUMENTS: list[object] = [
    {"records": []},
    {
        "records": [
            {"type": RESPONSES_ENCRYPTED_CONTENT, "value": "a"},
            {"type": RESPONSES_ENCRYPTED_CONTENT, "value": "b"},
        ]
    },
    {
        "records": [
            {
                "type": RESPONSES_SUMMARY_TEXT_LAYOUT,
                "value": {"lengths": [1], "extensions": []},
            }
        ]
    },
    {
        "records": [
            {
                "type": RESPONSES_SUMMARY_TEXT_LAYOUT,
                "value": {"lengths": [True], "extensions": [{}]},
            }
        ]
    },
]


@pytest.mark.parametrize("document", MALFORMED_V2_DOCUMENTS)
def test_malformed_v2_documents_have_one_stable_classification(document: object) -> None:
    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
    payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    decoded = decode_reasoning_carrier(f"{PROJECT_SYNTHETIC_REASONING_V2_PREFIX}{payload}")
    assert decoded.classification == "project_malformed_v2"


def test_v2_consumer_rejects_utf16_json_instead_of_autodetecting_it() -> None:
    document: object = {
        "records": [
            {
                "type": RESPONSES_SUMMARY_TEXT_LAYOUT,
                "value": {
                    "lengths": list[int](),
                    "extensions": list[dict[str, object]](),
                },
            }
        ]
    }
    raw = json.dumps(document, separators=(",", ":")).encode("utf-16le")
    payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    decoded = decode_reasoning_carrier(f"{PROJECT_SYNTHETIC_REASONING_V2_PREFIX}{payload}")
    assert decoded.classification == "project_malformed_v2"


def test_v2_producer_and_consumer_reject_non_json_nan() -> None:
    with pytest.raises(ValueError):
        encode_reasoning_carrier_v2(
            [CarrierRecord("future.provider.reasoning.detail", float("nan"))]
        )

    raw = b'{"records":[{"type":"future.provider.reasoning.detail","value":NaN}]}'
    payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    decoded = decode_reasoning_carrier(f"{PROJECT_SYNTHETIC_REASONING_V2_PREFIX}{payload}")
    assert decoded.classification == "project_malformed_v2"


def test_v2_record_type_must_be_a_dotted_namespace() -> None:
    with pytest.raises(ValueError):
        encode_reasoning_carrier_v2([CarrierRecord("x", None)])

    raw = b'{"records":[{"type":"x","value":null}]}'
    payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    decoded = decode_reasoning_carrier(f"{PROJECT_SYNTHETIC_REASONING_V2_PREFIX}{payload}")
    assert decoded.classification == "project_malformed_v2"


def test_unknown_v2_record_is_structurally_valid_but_named() -> None:
    signature = encode_reasoning_carrier_v2(
        [CarrierRecord("future.provider.reasoning.detail", {"x": 1})]
    )
    decoded = decode_reasoning_carrier(signature)
    assert decoded.classification == "project_v2"
    assert decoded.unknown_record_types == ("future.provider.reasoning.detail",)
