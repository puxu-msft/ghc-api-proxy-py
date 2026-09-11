from pathlib import Path

import pytest

from app.observability.debug_capture import DebugCaptureRuleStore


def test_rules_are_persistent_idempotent_and_agent_aware(tmp_path: Path) -> None:
    database = tmp_path / "debug-capture-rules.sqlite3"
    store = DebugCaptureRuleStore(database)

    rule, created = store.create_rule(
        provider="sub2api",
        model_id="deepseek-v4-pro",
        session_id="session-1",
    )
    duplicate, duplicate_created = store.create_rule(
        provider=" sub2api ",
        model_id="deepseek-v4-pro",
        session_id="session-1",
    )

    assert created is True
    assert duplicate_created is False
    assert duplicate == rule
    assert store.matches(
        provider="sub2api",
        model_id="deepseek-v4-pro",
        session_id="session-1",
        agent_id="any-agent",
    )
    assert not store.matches(
        provider="sub2api",
        model_id="other-model",
        session_id="session-1",
    )
    store.close()

    reopened = DebugCaptureRuleStore(database)
    assert reopened.list_rules() == (rule,)
    assert reopened.delete_rule(rule.id)
    assert not reopened.matches(
        provider="sub2api",
        model_id="deepseek-v4-pro",
        session_id="session-1",
    )
    assert not reopened.delete_rule(rule.id)
    reopened.close()


def test_agent_specific_rule_does_not_match_another_agent(tmp_path: Path) -> None:
    store = DebugCaptureRuleStore(tmp_path / "rules.sqlite3")
    store.create_rule(
        provider="ghc",
        model_id="gpt-model",
        session_id="session-1",
        agent_id="agent-1",
    )

    assert store.matches(
        provider="ghc",
        model_id="gpt-model",
        session_id="session-1",
        agent_id="agent-1",
    )
    assert not store.matches(
        provider="ghc",
        model_id="gpt-model",
        session_id="session-1",
        agent_id="agent-2",
    )
    assert not store.matches(
        provider="ghc",
        model_id="gpt-model",
        session_id="session-1",
    )
    store.close()


def test_rule_store_rejects_empty_conditions(tmp_path: Path) -> None:
    store = DebugCaptureRuleStore(tmp_path / "rules.sqlite3")
    with pytest.raises(ValueError):
        store.create_rule(provider="", model_id="model", session_id="session")
    with pytest.raises(ValueError):
        store.create_rule(provider="provider", model_id="model", session_id=" ")
    with pytest.raises(ValueError):
        store.create_rule(
            provider="provider",
            model_id="model",
            session_id="session",
            agent_id=" ",
        )
    store.close()
