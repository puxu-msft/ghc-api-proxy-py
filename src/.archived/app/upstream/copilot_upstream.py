"""`CopilotUpstream` — the adapter that put `GhcApiClient` into the shape of `UpstreamTarget`.

Cut out of `app/upstream/copilot.py` on 2026-08-23 and landed here under a name that never existed upstream of the cut, the same way `app/tokenization/gemini_estimator.py` did.

Only one thing in that file is measurably live: `GitHubTokenSourceAdapter`, built by `app/server/composition.py`. An earlier version of this docstring claimed the two header builders were live as well; a review checked and they are not. `build_copilot_identity_headers` has no caller anywhere, and `build_copilot_headers` has one test and no production caller — the live paths call the layer beneath them (`build_request_headers`, `build_identity_headers`) directly. They stayed in `src/app/` rather than coming here because nobody has ruled on them; registered in `deferred.md` §22之五.

`UpstreamTarget` is the protocol in `app/upstream/base.py` *in this directory* — so this class adapted the live library to an already-archived interface, and nothing in `src/` or `tests/` ever instantiated it. The live provider reaches `GhcApiClient` directly through `app/model_provider/github_copilot.py`.

It went because it was the only caller of `GhcApiClient.send_responses_headers`, which was in turn the only caller of `app/model_provider/ghc_client/transport.py` — the one place in the tree recording that a bare `h2.exceptions.ProtocolError` reaches callers unwrapped. That guard read as though it protected the live path. It did not, and while it sat there the live body path went without the same knowledge until 2026-08-23. See `.dev/docs/upstream/retry-and-continuation/deferred.md` §22之三.
"""



class CopilotUpstream:
    """Exposes `GhcApiClient` in the shape of `UpstreamTarget`.

    `UpstreamTarget` names protocol families; the library names endpoints.
    This class is the single translation point between the two.
    """

    def __init__(
        self,
        clients: SDKClients,
        token_manager: CopilotTokenManager,
        settings: AppSettings,
        *,
        interaction_id: str,
    ) -> None:
        self._client = GhcApiClient(
            clients.openai,
            clients.anthropic,
            token_manager,
            ghc_config_from_settings(settings),
            interaction_id=interaction_id,
        )

    async def send_openai(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx2.Response:
        return await self._client.send_chat_completions(payload, stream=stream)

    async def send_anthropic(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        return await self._client.send_anthropic_messages(
            payload,
            stream=stream,
            extra_headers=extra_headers,
        )

    async def send_anthropic_count_tokens(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
        return await self._client.send_anthropic_count_tokens(payload)

    async def send_responses(
        self,
        payload: Mapping[str, Any],
        *,
        stream: bool = False,
    ) -> httpx2.Response:
        return await self._client.send_responses(payload, stream=stream)

    async def send_responses_headers(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
        return await self._client.send_responses_headers(payload)

    async def send_embeddings(
        self,
        payload: Mapping[str, Any],
    ) -> httpx2.Response:
        return await self._client.send_embeddings(payload)
