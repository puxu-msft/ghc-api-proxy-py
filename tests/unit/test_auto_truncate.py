from app.auto_truncate.engine import truncate_messages


def test_truncate_preserves_system_and_recent_history() -> None:
    messages = [
        {"role": "system", "content": "rules"},
        *({"role": "user", "content": f"message-{index}"} for index in range(10)),
    ]
    truncated = truncate_messages(messages, keep_recent_fraction=0.3)
    assert truncated[0] == {"role": "system", "content": "rules"}
    assert [message["content"] for message in truncated[1:]] == [
        "message-7",
        "message-8",
        "message-9",
    ]