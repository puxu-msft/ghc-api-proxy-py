from dataclasses import dataclass
from hashlib import sha256
from hmac import new as hmac_new

PROTOCOL_PREFIX = "superagent-auth-v1"
SIGN_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class GatewaySignature:
    value: str
    timestamp: str
    nonce: str
    body_hash: str


def jwt_hmac_key(x_token: str) -> str:
    parts = x_token.split(".")
    return parts[2] if len(parts) == 3 else x_token


def hmac_hex(key: str, data: str) -> str:
    return hmac_new(key.encode(), data.encode(), sha256).hexdigest()


def sign_gateway_request(
    *,
    method: str,
    request_uri: str,
    body: bytes,
    x_token: str,
    install_id: str,
    app_version: str,
    timestamp: str,
    nonce: str,
) -> GatewaySignature:
    body_hash = sha256(body).hexdigest()
    intermediate = hmac_hex(
        jwt_hmac_key(x_token),
        "/".join((PROTOCOL_PREFIX, x_token, install_id, timestamp, nonce)),
    )
    signature = hmac_hex(
        intermediate,
        "\n".join(
            (
                PROTOCOL_PREFIX,
                method.upper(),
                request_uri,
                timestamp,
                nonce,
                app_version,
                body_hash,
            )
        ),
    )
    return GatewaySignature(
        value=signature,
        timestamp=timestamp,
        nonce=nonce,
        body_hash=body_hash,
    )
