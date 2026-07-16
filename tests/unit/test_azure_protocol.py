from app.protocols.azure import adapt_azure_payload


def test_azure_deployment_override_does_not_mutate_original_payload() -> None:
    original: dict[str, object] = {"model": "client-model", "messages": []}
    adapted = adapt_azure_payload(original, deployment="deployment-model")
    assert adapted.original_payload == original
    assert adapted.wire_payload["model"] == "deployment-model"
    assert original["model"] == "client-model"