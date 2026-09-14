import pytest


@pytest.fixture(autouse=True)
def isolated_data_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep persistence tests away from the developer's XDG data directory."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path_factory.mktemp("xdg-data")))
