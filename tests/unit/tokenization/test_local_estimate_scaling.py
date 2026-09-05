from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config.loading import load_proxy_config
from app.config.schema import CountTokensConfig
from app.tokenization.scaling import scale_local_estimate


def test_multiplier_defaults_to_identity() -> None:
    config = CountTokensConfig()
    assert config.local_estimate_multiplier == 1.0
    assert scale_local_estimate(12345, config.local_estimate_multiplier) == 12345


@pytest.mark.parametrize("value", [True, False, 0, -1, 0.9, float("inf"), float("nan"), "NaN", "invalid"])
def test_multiplier_rejects_invalid_configuration(value: object) -> None:
    with pytest.raises(ValidationError):
        CountTokensConfig.model_validate({"local_estimate_multiplier": value})


@pytest.mark.parametrize(
    ("tokens", "multiplier", "expected"),
    [(100, 1.1, 110), (101, 1.1, 112), (1, 1.01, 2), (0, 1.5, 0), (10**30, 1.1, 11 * 10**29)],
)
def test_multiplier_rounds_the_decimal_product_up(tokens: int, multiplier: float, expected: int) -> None:
    assert scale_local_estimate(tokens, multiplier) == expected


def test_file_and_environment_load_the_count_scoped_multiplier(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "inbound:\n  anthropic_count_tokens:\n    local_estimate_multiplier: 1.2\n",
        encoding="utf-8",
    )
    from_file = load_proxy_config(config_path=config_path, bundled={}, environ={})
    assert from_file.inbound.anthropic_count_tokens.local_estimate_multiplier == 1.2
    from_environment = load_proxy_config(
        config_path=config_path,
        bundled={},
        environ={"GHC_API_PROXY_INBOUND__ANTHROPIC_COUNT_TOKENS__LOCAL_ESTIMATE_MULTIPLIER": "1.3"},
    )
    assert from_environment.inbound.anthropic_count_tokens.local_estimate_multiplier == 1.3
