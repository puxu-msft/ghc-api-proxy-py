"""TLS material resolution and the count_tokens provider chain."""

from pathlib import Path
from typing import Any

import pytest

from app.config.schema import ProxyConfig
from app.pipeline.count_tokens import CountTokensUnavailable, count_tokens
from app.server.tls import (
    TLS_HANDSHAKE_BYTE,
    TlsConfigurationError,
    is_tls_handshake,
    resolve_tls_material,
    serves_plaintext,
    serves_tls,
)


def config(**tls: object) -> ProxyConfig:
    return ProxyConfig.model_validate({"server": {"tls": tls}})


# --- TLS -------------------------------------------------------------------


def test_a_client_hello_is_recognised_by_its_first_byte() -> None:
    assert is_tls_handshake(TLS_HANDSHAKE_BYTE) is True


@pytest.mark.parametrize("letter", [ord("G"), ord("P"), ord("O"), ord("H")])
def test_a_plaintext_request_is_not_mistaken_for_tls(letter: int) -> None:
    # HTTP methods begin with a letter, so the two are distinguishable on one byte.
    assert is_tls_handshake(letter) is False


def test_mode_false_serves_plaintext_only() -> None:
    assert serves_plaintext(False) is True
    assert serves_tls(False) is False


def test_mode_true_serves_tls_only() -> None:
    assert serves_plaintext(True) is False
    assert serves_tls(True) is True


def test_mode_both_serves_either() -> None:
    assert serves_plaintext("both") is True
    assert serves_tls("both") is True


def test_http_only_deployment_gets_no_material(tmp_path: Path) -> None:
    assert resolve_tls_material(config(mode=False), tls_dir=tmp_path) is None


def test_cert_without_key_is_rejected(tmp_path: Path) -> None:
    cert = tmp_path / "cert.pem"
    cert.write_text("x")
    with pytest.raises(TlsConfigurationError, match="together"):
        resolve_tls_material(config(mode=True, cert=str(cert)), tls_dir=tmp_path)


def test_a_named_file_that_does_not_exist_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(TlsConfigurationError, match="not found"):
        resolve_tls_material(
            config(mode=True, cert=str(tmp_path / "a.pem"), key=str(tmp_path / "b.pem")),
            tls_dir=tmp_path,
        )


def test_a_configured_pair_is_used_as_given(tmp_path: Path) -> None:
    cert = tmp_path / "given-cert.pem"
    key = tmp_path / "given-key.pem"
    cert.write_text("cert")
    key.write_text("key")
    material = resolve_tls_material(
        config(mode=True, cert=str(cert), key=str(key)), tls_dir=tmp_path
    )
    assert material is not None
    assert material.cert_path == cert
    assert material.generated is False


def test_omitting_both_generates_a_usable_pair(tmp_path: Path) -> None:
    material = resolve_tls_material(config(mode="both"), tls_dir=tmp_path / "tls")
    assert material is not None
    assert material.generated is True
    assert material.cert_path.read_bytes().startswith(b"-----BEGIN CERTIFICATE-----")
    assert material.key_path.read_bytes().startswith(b"-----BEGIN PRIVATE KEY-----")


def test_the_generated_key_is_not_world_readable(tmp_path: Path) -> None:
    material = resolve_tls_material(config(mode=True), tls_dir=tmp_path / "tls")
    assert material is not None
    assert material.key_path.stat().st_mode & 0o077 == 0


def test_a_generated_pair_is_reused_rather_than_regenerated(tmp_path: Path) -> None:
    # Regenerating on every start would make every client re-trust the proxy.
    tls_dir = tmp_path / "tls"
    first = resolve_tls_material(config(mode=True), tls_dir=tls_dir)
    assert first is not None
    original = first.cert_path.read_bytes()

    second = resolve_tls_material(config(mode=True), tls_dir=tls_dir)
    assert second is not None
    assert second.generated is False
    assert second.cert_path.read_bytes() == original


# --- count_tokens ----------------------------------------------------------


PAYLOAD: dict[str, Any] = {"model": "m", "messages": []}


@pytest.mark.asyncio
async def test_the_first_provider_wins_when_it_succeeds() -> None:
    async def upstream(_: Any) -> int:
        return 42

    result = await count_tokens(
        PAYLOAD,
        providers=["ghc", "local"],
        max_retries=0,
        upstream=upstream,
        local=lambda _: 7,
    )
    assert result.tokens == 42
    assert result.provider == "ghc"


@pytest.mark.asyncio
async def test_a_failing_provider_hands_over_to_the_next() -> None:
    async def upstream(_: Any) -> int:
        raise RuntimeError("upstream down")

    result = await count_tokens(
        PAYLOAD,
        providers=["ghc", "local"],
        max_retries=0,
        upstream=upstream,
        local=lambda _: 7,
    )
    assert result.tokens == 7
    assert result.provider == "local"


@pytest.mark.asyncio
async def test_retries_are_spent_within_one_provider() -> None:
    calls = {"n": 0}

    async def upstream(_: Any) -> int:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("flaky")
        return 5

    result = await count_tokens(
        PAYLOAD,
        providers=["ghc"],
        max_retries=2,
        upstream=upstream,
    )
    assert result.tokens == 5
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_order_is_taken_from_the_configuration() -> None:
    async def upstream(_: Any) -> int:
        return 42

    result = await count_tokens(
        PAYLOAD,
        providers=["local", "ghc"],
        max_retries=0,
        upstream=upstream,
        local=lambda _: 7,
    )
    assert result.provider == "local"


@pytest.mark.asyncio
async def test_an_unconfigured_provider_is_skipped_rather_than_crashing() -> None:
    result = await count_tokens(
        PAYLOAD,
        providers=["ghc", "local"],
        max_retries=1,
        upstream=None,
        local=lambda _: 7,
    )
    assert result.provider == "local"


@pytest.mark.asyncio
async def test_every_provider_failing_is_reported_with_the_attempts() -> None:
    async def upstream(_: Any) -> int:
        raise RuntimeError("down")

    def local(_: Any) -> int:
        raise ValueError("no tokenizer")

    with pytest.raises(CountTokensUnavailable) as raised:
        await count_tokens(
            PAYLOAD,
            providers=["ghc", "local"],
            max_retries=0,
            upstream=upstream,
            local=local,
        )
    assert any("ghc" in attempt for attempt in raised.value.attempts)
    assert any("local" in attempt for attempt in raised.value.attempts)
