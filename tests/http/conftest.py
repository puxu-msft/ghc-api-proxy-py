import pytest


@pytest.fixture(autouse=True)
def isolated_data_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Send every XDG data lookup to a throwaway directory.

    Without this, a test that builds the app with default settings writes to the developer's own `~/.local/share/ghc-api-proxy/`: `history.enabled` defaults to true and the db path falls back to `user_data_path() / "history.db"`. That database held 8,886 rows by 2026-08-20 and was still growing, none of it from a request anyone made. It matters beyond tidiness — once forensic recording lands on the live chain, this noise would share a file with the records that file exists to keep, and whatever decides which records to retain would be weighing traffic that never happened.

    `XDG_DATA_HOME` rather than a db path threaded through each call site: `platformdirs` reads the variable at call time, so one setting also covers the pidfile, the tokenization state and the stored GitHub token. The last of those is the real prize — a test that quietly reads the developer's own credentials passes on their machine and nowhere else.

    Each group carries its own copy rather than sharing one at the root, so a group that genuinely needs the real directory can drop it instead of having it imposed.

    The directory comes from `tmp_path_factory` rather than the test's own `tmp_path`, because a test is entitled to assert exactly what its `tmp_path` holds — the pidfile test asserts precisely that, and an earlier version of this fixture broke it by leaving a directory behind there. Isolating the environment should leave no trace in the subject's own workspace.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path_factory.mktemp("xdg-data")))
