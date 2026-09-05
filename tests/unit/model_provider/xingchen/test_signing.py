import hashlib
import hmac

from app.model_provider.xingchen.signing import (
    PROTOCOL_PREFIX,
    hmac_hex,
    jwt_hmac_key,
    sign_gateway_request,
)

BODY = b'{"model":"chat-lite","messages":[{"role":"user","content":"ping"}],"stream":false}'
X_TOKEN = "prefix:header.payload.signature"
INSTALL_ID = "install-123"
TIMESTAMP = "1700000000"
NONCE = "11111111-2222-4333-8444-555555555555"
REQUEST_URI = "/superCowork/sapi/api/v1/chat/completions?tenant=t"
APP_VERSION = "2.4.1"
EXPECTED_BODY_HASH = "1f5e66073e573a0742bfdb16a8088dcb4ceaf66f428f2c9955441df391de2021"
EXPECTED_INTERMEDIATE = "28195823b1e30ec084fe2060f822ca3dfd9382e5fc03ad0b29c4452a97eb0d48"
EXPECTED_SIGNATURE = "bfd299388290771dbbab15f5b137e236e97b41c05340e6078259d1db093a0420"


def test_gateway_signature_matches_an_independent_fixed_vector() -> None:
    first_data = "/".join((PROTOCOL_PREFIX, X_TOKEN, INSTALL_ID, TIMESTAMP, NONCE))
    assert hmac_hex(jwt_hmac_key(X_TOKEN), first_data) == EXPECTED_INTERMEDIATE

    signed = sign_gateway_request(
        method="post",
        request_uri=REQUEST_URI,
        body=BODY,
        x_token=X_TOKEN,
        install_id=INSTALL_ID,
        app_version=APP_VERSION,
        timestamp=TIMESTAMP,
        nonce=NONCE,
    )

    assert len(BODY) == 82
    assert signed.body_hash == EXPECTED_BODY_HASH
    assert signed.value == EXPECTED_SIGNATURE
    assert signed.timestamp == TIMESTAMP
    assert signed.nonce == NONCE


def test_second_hmac_key_is_hex_ascii_not_decoded_digest_bytes() -> None:
    second_data = "\n".join(
        (
            PROTOCOL_PREFIX,
            "POST",
            REQUEST_URI,
            TIMESTAMP,
            NONCE,
            APP_VERSION,
            EXPECTED_BODY_HASH,
        )
    )
    decoded_key_result = hmac.new(
        bytes.fromhex(EXPECTED_INTERMEDIATE),
        second_data.encode(),
        hashlib.sha256,
    ).hexdigest()

    assert decoded_key_result != EXPECTED_SIGNATURE


def test_jwt_key_uses_the_third_segment_only_for_exactly_three_parts() -> None:
    assert jwt_hmac_key("first.second.third") == "third"
    assert jwt_hmac_key("first.second") == "first.second"
    assert jwt_hmac_key("first.second.third.fourth") == "first.second.third.fourth"
