"""The Gemini input estimator, lifted out of the live `app/tokenization/estimators.py`.

Not a whole file that moved: the rest of that module — the Anthropic and Responses estimators, `preload_tokenizer`, the shared `_TOKENIZER_NAME` — is live and stayed. What came here is `estimate_gemini_input` with its two private helpers and the `app.models.gemini` import that only it needed, cut out on 2026-08-23 when the rest of the old Gemini implementation was archived. So there is no original path under `app/tokenization/` that this file corresponds to, and its name is new.

Why it was in the live tree at all: the old chain's `countTokens` answered locally rather than asking upstream — `routes/gemini.py` called this directly and returned `{"totalTokens": n}` without a network round trip. That is a real design decision and the reason this is worth keeping rather than deleting: the new chain's Gemini `countTokens` route exists and answers 501, and whoever implements it has to decide the same question. `.dev/docs/server-layout/deferred.md` §D-A points here.

It had no caller anywhere by the time it was archived — the chain that used it went to `src/.archived/` on 2026-08-22, and `app.tokenization.__init__` was re-exporting a function nothing imported.

Like the rest of this archive, it is not importable as it stands: `app.models.gemini` now lives beside it under `src/.archived/`, not on the path.
"""

from typing import Any

import tiktoken

from app.models.gemini import CountTokensRequest, GenerateContentRequest
from app.wire_json import dumps

# The live module's own constant, copied rather than imported: this file is not on the path, so an import would only look like a live dependency without being one.
_TOKENIZER_NAME = "o200k_base"


def _gemini_request(request: CountTokensRequest | GenerateContentRequest) -> GenerateContentRequest:
    if isinstance(request, GenerateContentRequest):
        return request
    if request.generate_content_request is not None:
        return request.generate_content_request
    return GenerateContentRequest(contents=request.contents or [])


def estimate_gemini_input(request: CountTokensRequest | GenerateContentRequest) -> int:
    payload = _gemini_request(request)
    values: list[str] = []
    if payload.system_instruction is not None:
        values.extend(_gemini_part_values(payload.system_instruction.parts))
    for content in payload.contents:
        if content.role:
            values.append(content.role)
        values.extend(_gemini_part_values(content.parts))
    if payload.tools:
        values.append(
            dumps(
                [
                    tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for tool in payload.tools
                ]
            ).decode()
        )
    encoding = tiktoken.get_encoding(_TOKENIZER_NAME)
    return max(len(encoding.encode("\n".join(values))), 1)


def _gemini_part_values(parts: list[Any]) -> list[str]:
    values: list[str] = []
    for part in parts:
        if part.text is not None:
            values.append(part.text)
        elif part.function_call is not None:
            values.append(dumps(part.function_call).decode())
        elif part.function_response is not None:
            values.append(dumps(part.function_response).decode())
        elif part.inline_data is not None:
            values.append(dumps(part.inline_data).decode())
    return values
