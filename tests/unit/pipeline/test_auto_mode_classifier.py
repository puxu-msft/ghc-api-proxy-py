"""Recognising an auto mode authorisation request, and answering it in a shape the client can read.

**The fixtures are traced, not invented.** `classifier_request()` reproduces the skeleton of a recorded request — `history-v3.db`, operation `req_1786636259217_269`, 2026-08-13, 710179 bytes on the wire — with the long bodies cut down. The two forensic reports behind it are cited in `.dev/docs/auto-mode-classifier/spec.md`, and between them they cover 2300 real requests and three client versions. A shape here that no recorded request has is marked where it stands.

**The parser assertions are the client's own regexes, transliterated.** `parses_as_block` and `parses_as_severity` below are `oLl` and `UGw` from `app.pretty.js` (2.1.241, lines 368407 and 368422) written in Python. That is the discriminating check in this file: a reply this proxy writes is only correct if *that* parser accepts it, and asserting on our own output shape instead would pass no matter what the client does with it. The cost of getting it wrong is not one bad answer — the client retries an unparseable reply (`p1m`, 368542), and each retry is another 710 KB.

They are a transliteration of a snapshot, so they can drift from the client. What they pin is the contract as it stood at 2.1.241; if a future version changes it, these go red for the right reason.
"""

import re
from collections.abc import Mapping
from typing import Any, cast

import httpx2
import orjson
import pytest

from app.config.schema import AutoModeDecision, InterceptAutoModeClassifierConfig, ProxyConfig
from app.model_provider import ModelDescriptor, ModelEndpoint
from app.pipeline.auto_mode_classifier import classify, verdict_text
from app.pipeline.delivery.formats.anthropic_messages_synthetic_reply import (
    auto_mode_body,
    auto_mode_sse,
)
from app.pipeline.driver import handle
from app.pipeline.request import RequestContext, WireFormat
from app.server.composition import build_chain

MONITOR_PROMPT = "You are a security monitor for autonomous AI coding agents."


def classifier_request(
    *,
    system_text: str = MONITOR_PROMPT + "\n\n## Context\n\nThe agent you are monitoring…",
    transcript_open: str = "<transcript>\n",
    stop_sequences: list[str] | None = None,
    with_claude_md: bool = True,
) -> dict[str, Any]:
    """The recorded skeleton, shortened.

    Two user turns, no assistant turn, no `tools`, no `stream` — the recorded requests have exactly this field set, and §6.5 of the traffic report contrasts it with an ordinary conversation request, which differs on every one of those.
    """
    messages: list[dict[str, Any]] = []
    if with_claude_md:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "The following is the user's CLAUDE.md configuration…"}
                ],
            }
        )
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": transcript_open},
                {"type": "text", "text": "User: do the thing\n"},
                {"type": "text", "text": "Bash rm -rf /tmp/scratch"},
                {"type": "text", "text": "</transcript>\n"},
                {"type": "text", "text": "\nErr on the side of blocking. …"},
            ],
        }
    )
    body: dict[str, Any] = {
        "model": "sonnet",
        "max_tokens": 2112,
        "system": [
            {"type": "text", "cache_control": {"type": "ephemeral"}, "text": system_text},
            {"type": "text", "text": "\n\n## Session Context\n\n- **User identity**: `xp`."},
        ],
        "messages": messages,
    }
    if stop_sequences is not None:
        body["stop_sequences"] = stop_sequences
    return body


def ordinary_request() -> dict[str, Any]:
    """What a normal Claude Code turn looks like, per §6.5 of the traffic report.

    Present so the predicates have something to *not* match. A recognition test with no negative case measures nothing.
    """
    return {
        "model": "claude-opus-5",
        "max_tokens": 128000,
        "stream": True,
        "tools": [{"name": "Read", "input_schema": {"type": "object"}}],
        "system": [{"type": "text", "text": "You are Claude Code, Anthropic's official CLI for Claude."}],
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            {"role": "user", "content": [{"type": "text", "text": "carry on"}]},
        ],
    }


# `dLl`, app.pretty.js:368404 — thinking is stripped before the decision is read, both the closed form and an unterminated tail. Case-sensitive in the original (no `i` flag), so no flags here either.
def _strip_thinking(text: str) -> str:
    return re.sub(r"<thinking>[\s\S]*$", "", re.sub(r"<thinking>[\s\S]*?</thinking>", "", text))


# ECMAScript's `\s` for a non-`u` regex: WhiteSpace plus LineTerminator. It is neither Python's default `\s` (which also takes U+001C-U+001F and U+0085) nor its ASCII one (which drops every non-ASCII space). Both substitutions were measured to disagree with the real parser, so the class is spelled out.
_ES_SPACE = r"[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"

# `re.ASCII` is what makes `\b` an ASCII word boundary and, with `IGNORECASE`, keeps the folding ASCII-only. Without it Python folds U+017F (LATIN SMALL LETTER LONG S) onto `s` and treats U+00E9 as a word character, and both were measured to flip the verdict away from the JS parser's.
_BLOCK_SCAN = re.compile(r"<block>(yes|no)\b", re.IGNORECASE | re.ASCII)
_BLOCK_READ = re.compile(r"<block>(yes|no)\b(</block>)?", re.IGNORECASE | re.ASCII)
# `\d` is ASCII in a non-`u` JS regex, so `[0-9]` rather than `\d` — Python's `\d` accepts Arabic-Indic digits, which the real parser rejects.
_SEVERITY_READ = re.compile(rf"<severity>{_ES_SPACE}*([0-9]+(?:\.[0-9]+)?){_ES_SPACE}*(</severity>)?")


def parses_as_block(text: str) -> bool | None:
    """`oLl`, app.pretty.js:368407. `None` means the client would call this unparseable and retry."""
    if len({m.group(1).lower() for m in _BLOCK_SCAN.finditer(text)}) > 1:
        return None
    found = list(_BLOCK_READ.finditer(_strip_thinking(text)))
    if not found:
        return None
    decisions = {m.group(1).lower() for m in found}
    if len(decisions) != 1:
        return None
    return "yes" in decisions


def parses_as_severity(text: str) -> float | None:
    """`UGw`, app.pretty.js:368422 — the text half of the severity read."""
    stripped = re.sub(r"<thinking>[\s\S]*?</thinking>", "", text)
    if "<thinking>" in stripped:
        return None
    found = list(_SEVERITY_READ.finditer(stripped))
    if len(found) != 1:
        return None
    return float(found[0].group(1))


def severity_of_reply(body: dict[str, Any]) -> float | None:
    """`QRl`, app.pretty.js:368418 — the whole severity read, gate included.

    `QRl` refuses a reply whose `stop_reason` is neither `stop_sequence` nor `end_turn` before it ever looks at the text. Keeping that gate in a separate assertion left the two facts — "the tag parses" and "the stop reason is acceptable" — never checked together on one reply, which is exactly the combination the client applies.
    """
    if body.get("stop_reason") not in {"stop_sequence", "end_turn"}:
        return None
    content = body.get("content")
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for block in cast(list[Any], content):
        if not isinstance(block, dict):
            continue
        entry = cast(dict[str, Any], block)
        text = entry.get("text")
        if entry.get("type") == "text" and isinstance(text, str):
            parts.append(text)
    return parses_as_severity("".join(parts))


def config(**overrides: Any) -> InterceptAutoModeClassifierConfig:
    return InterceptAutoModeClassifierConfig(**overrides)


class TestRecognition:
    def test_the_default_lets_every_request_through(self) -> None:
        """`passthrough` is the shipped default, so a proxy nobody configured behaves exactly as before."""
        assert classify(classifier_request(), config()) is None

    def test_the_monitor_prompt_is_recognised(self) -> None:
        verdict = classify(classifier_request(), config(decision="allow"))
        assert verdict is not None
        assert verdict.matched == "system-prompt"

    def test_the_transcript_wrapper_is_recognised_on_its_own(self) -> None:
        """The second predicate has to stand without the first, since it exists to survive a prompt rewrite."""
        request = classifier_request(system_text="Some future rewording of the monitor prompt.")
        verdict = classify(request, config(decision="allow"))
        assert verdict is not None
        assert verdict.matched == "transcript-open"

    def test_the_monitor_prompt_is_found_wherever_it_sits(self) -> None:
        """Not pinned to `system[0]`: the client puts its billing attribution in a system block too, and which one comes first has already differed between the recorded traffic and 2.1.241's source."""
        request = classifier_request(transcript_open="something else entirely\n")
        request["system"].insert(
            0, {"type": "text", "text": "x-anthropic-billing-header: cc_version=2.1.241.abc;"}
        )
        verdict = classify(request, config(decision="allow"))
        assert verdict is not None
        assert verdict.matched == "system-prompt"

    def test_an_ordinary_conversation_is_not_touched(self) -> None:
        assert classify(ordinary_request(), config(decision="allow")) is None

    def test_a_request_matching_neither_predicate_travels(self) -> None:
        """The decay path. When the client rewords both literals this returns `None`, which is the pre-feature behaviour — the bytes are spent, nothing is answered wrongly."""
        request = classifier_request(
            system_text="Some future rewording.", transcript_open="<conversation>\n"
        )
        assert classify(request, config(decision="allow")) is None

    def test_either_marker_survives_the_other_being_reworded(self) -> None:
        """Why there are two markers rather than one.

        They are literals owned by another program and each decays when that program rewords it. Keeping both means one rewording costs nothing, because the two are not rewritten together: a rewritten monitor prompt leaves the transcript wrapper alone, and vice versa.
        """
        prompt_reworded = classifier_request(system_text="Some future rewording.")
        assert classify(prompt_reworded, config(decision="allow")) is not None

        wrapper_reworded = classifier_request(transcript_open="<conversation>\n")
        assert classify(wrapper_reworded, config(decision="allow")) is not None

    def test_the_prompt_marker_is_configurable(self) -> None:
        """Why this one is a setting: it is a sentence of English prose owned by another program, so it gets reworded, and fixing that must not need a release here.

        The request below has had *both* markers reworded, so it is unrecognisable by default. Only one of the two can be repaired by configuration — which is enough, because either marker matching is enough.
        """
        request = classifier_request(
            system_text="Nouvelle formulation du moniteur.", transcript_open="<conversation>\n"
        )
        assert classify(request, config(decision="allow")) is None

        repaired = config(
            decision="allow",
            match_system_prompt_prefix="Nouvelle formulation du moniteur.",
        )
        assert classify(request, repaired) is not None

    def test_the_configured_keys_are_exactly_the_three_the_authority_names(self) -> None:
        """Ruled 2026-08-23: `<transcript>` is a structural tag rather than prose, so it does not need a knob — and a knob whose value must carry a trailing newline is one people set wrongly, silently.

        Pinned against `model_fields` rather than by asserting a `ValidationError` on the removed key. That was the first spelling and it proved nothing: `extra="forbid"` raises for *any* unknown name, so the assertion passed for typos and for the key's own former spelling alike. Two reviewers found it independently.

        The set is the discriminating form — it fails both when a removed key comes back and when a new one is added without the authority naming it.
        """
        assert set(InterceptAutoModeClassifierConfig.model_fields) == {
            "decision",
            "block_reason_str",
            "match_system_prompt_prefix",
        }

    def test_the_reason_reaches_the_reply(self) -> None:
        """`reason` is the one part of this feature the blocked person sees, so a configured one has to arrive intact."""
        verdict = classify(classifier_request(), config(decision="block"))
        assert verdict is not None
        text = verdict_text(verdict, "refused: this proxy is configured to block")
        assert "<reason>refused: this proxy is configured to block</reason>" in text


class TestProtocolSelection:
    def test_stage_one_uses_the_block_protocol(self) -> None:
        verdict = classify(
            classifier_request(stop_sequences=["</block>"]), config(decision="allow")
        )
        assert verdict is not None
        assert verdict.protocol == "block"

    def test_stage_two_carries_no_stop_sequences_and_still_uses_block(self) -> None:
        """Recorded: the 53 stage-2 samples have no `stop_sequences` at all."""
        verdict = classify(classifier_request(), config(decision="allow"))
        assert verdict is not None
        assert verdict.protocol == "block"

    def test_the_severity_variant_is_taken_from_the_stop_sequence(self) -> None:
        verdict = classify(
            classifier_request(stop_sequences=["</severity>"]), config(decision="allow")
        )
        assert verdict is not None
        assert verdict.protocol == "severity"


class TestTheClientCanParseTheAnswer:
    """The load-bearing group. Each case runs this proxy's output through the client's own parser."""

    @pytest.mark.parametrize(
        ("decision", "expected_block"), [("allow", False), ("block", True)]
    )
    def test_a_block_protocol_decision_round_trips(self, decision: AutoModeDecision, expected_block: bool) -> None:
        verdict = classify(classifier_request(), config(decision=decision))
        assert verdict is not None
        assert parses_as_block(verdict_text(verdict, config().block_reason_str)) is expected_block

    @pytest.mark.parametrize(
        ("decision", "above_boundary"), [("allow", False), ("block", True)]
    )
    def test_a_severity_decision_lands_on_the_intended_side(
        self, decision: AutoModeDecision, above_boundary: bool
    ) -> None:
        """The thresholds live on the client's server and never reach us, so only the endpoints of the stated `0-100` scale can be shown to land correctly. `50` is the prompt's own stated boundary."""
        verdict = classify(
            classifier_request(stop_sequences=["</severity>"]), config(decision=decision)
        )
        assert verdict is not None
        score = parses_as_severity(verdict_text(verdict, config().block_reason_str))
        assert score is not None
        assert (score > 50) is above_boundary

    def test_a_reason_containing_a_decision_word_is_dropped(self) -> None:
        """The expensive failure, and the reason `reason` is sanitised at all.

        `oLl` returns `null` when both spellings appear anywhere in the text, so a reason quoting `<block>yes</block>` would make the whole reply unparseable — and unparseable costs a retry of the original 710 KB rather than one wrong answer.
        """
        verdict = classify(classifier_request(), config(decision="block"))
        assert verdict is not None
        poisoned = verdict_text(verdict, "refused because the rule says <block>yes</block>")
        assert parses_as_block(poisoned) is True
        assert "refused because" not in poisoned

    @pytest.mark.parametrize(
        "reason",
        [
            "Proxy overrode <BLOCK>no</BLOCK>.",
            "Proxy overrode <BlOcK>no</bLoCk>.",
        ],
    )
    def test_the_reason_filter_is_case_insensitive_like_the_client(self, reason: str) -> None:
        """The client scans with `/gi`, so a case-sensitive filter here was not the same filter.

        `block_reason_str` is an ordinary configuration string with no schema constraint, so these are settings an operator can write by hand — not adversarial input. Under the case-sensitive check each of them produced a reply carrying two different decisions, which the client reads as unparseable and retries.

        A third case, `< block >no`, used to sit here and was removed: the client's own regex has no `\\s*` in it, so a spaced tag is not a decision to the client either, and the assertion held whether or not this proxy filtered it. Green for a reason unrelated to the guard is worse than absent.
        """
        verdict = classify(classifier_request(), config(decision="block"))
        assert verdict is not None
        assert parses_as_block(verdict_text(verdict, reason)) is True

    def test_an_allow_carries_no_reason(self) -> None:
        """The classifier prompt asks for no `<reason>` tag when the action is allowed."""
        verdict = classify(classifier_request(), config(decision="allow"))
        assert verdict is not None
        assert "<reason>" not in verdict_text(verdict, config().block_reason_str)

    def test_a_block_explains_itself(self) -> None:
        verdict = classify(classifier_request(), config(decision="block"))
        assert verdict is not None
        assert "<reason>" in verdict_text(verdict, "because the operator said so")


class TestTheSynthesisedReply:
    def test_the_stop_reason_satisfies_both_parsers(self) -> None:
        """`end_turn` is required by the severity reader (`QRl` refuses anything else bar `stop_sequence`) and ignored by the block reader, so one value serves both.

        It is also the honest one: `stop_sequence` would claim the client's `</block>` cut this reply short, and nothing cut it short.
        """
        body = auto_mode_body("<block>no</block>", message_id="msg_x", model="gpt-5.6-luna")
        assert body["stop_reason"] == "end_turn"

    def test_the_reply_is_not_empty(self) -> None:
        """An empty `content` is read as `policy_refusal` by `iLl` — a different client path than the one being answered."""
        body = auto_mode_body("<block>no</block>", message_id="msg_x", model="m")
        assert body["content"][0]["text"]

    def test_usage_is_zero_because_nothing_was_spent(self) -> None:
        body = auto_mode_body("<block>no</block>", message_id="msg_x", model="m")
        assert body["usage"] == {"input_tokens": 0, "output_tokens": 0}

    def test_the_streaming_form_carries_the_same_decision(self) -> None:
        """No recorded classifier request streams; this path exists so that a client that starts doing so costs a config note rather than an incident."""
        stream = auto_mode_sse("<block>yes</block>", message_id="msg_x", model="m").decode()
        assert "event: message_start" in stream
        assert "event: message_stop" in stream
        assert "<block>yes</block>" in stream


class TestItDoesNotHijackOrdinaryRequests:
    """Every case here is a legal request an ordinary client could send, built by a reviewer against the first version of this feature — which answered all of them with a fabricated decision, invisibly, and never sent them upstream.

    That is the worst failure this feature has: not a wrong decision, but a user's real request silently replaced. The structural floor in `_has_classifier_shape` is what these pin.
    """

    def test_a_second_system_block_quoting_the_monitor_prompt_is_not_enough(self) -> None:
        """A request may legitimately quote the prompt — asking a model to explain it, for one — and the marker alone used to be sufficient."""
        request = ordinary_request()
        request["system"].append(
            {"type": "text", "text": MONITOR_PROMPT + " Explain the quoted role below."}
        )
        assert classify(request, config(decision="allow")) is None

    def test_a_transcript_opener_without_its_closer_is_not_enough(self) -> None:
        """`summarise the transcript below` has exactly this shape: a last user turn whose first block is the opener, and no wrapper around anything."""
        request: dict[str, Any] = {
            "model": "claude-opus-5",
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "<transcript>\n"},
                        {"type": "text", "text": "…and please summarise what you find."},
                    ],
                }
            ],
        }
        assert classify(request, config(decision="allow")) is None

    def test_the_monitor_prompt_does_not_fire_on_a_request_that_declares_tools(self) -> None:
        """The classifier declares none. A request carrying a toolbox is a working turn whatever its system prompt says."""
        request = classifier_request()
        request["tools"] = [{"name": "Read", "input_schema": {"type": "object"}}]
        assert classify(request, config(decision="allow")) is None

    def test_the_monitor_prompt_does_not_fire_on_a_streaming_request(self) -> None:
        request = classifier_request()
        request["stream"] = True
        assert classify(request, config(decision="allow")) is None

    def test_the_monitor_prompt_does_not_fire_when_the_conversation_has_history(self) -> None:
        """The classifier renders history into text and sends only `user` turns, so an `assistant` turn means this is a real conversation."""
        request = classifier_request()
        request["messages"].insert(
            1, {"role": "assistant", "content": [{"type": "text", "text": "sure"}]}
        )
        assert classify(request, config(decision="allow")) is None


class TestSeverityStageTwo:
    def test_the_protocol_is_read_off_the_prompt_when_no_stop_sequence_says_so(self) -> None:
        """Stage 2 carries no `stop_sequences` at all, so reading only that field called every severity stage 2 a block one — and the client, holding a severity parser, would have found `<block>no</block>` unparseable and retried the whole 710 KB.

        `OGw()` rewrites the prompt's `## Output Format` into the severity wording, which is where the tag appears in a *request*.
        """
        request = classifier_request(
            system_text=MONITOR_PROMPT
            + "\n\n## Output Format\n\nOutput <severity>N</severity> where N is an integer 0-100…"
        )
        verdict = classify(request, config(decision="allow"))
        assert verdict is not None
        assert verdict.protocol == "severity"

    def test_a_block_score_clears_every_threshold_the_client_accepts(self) -> None:
        """`nLl()` accepts any threshold in `0 <= t <= 100` and then compares `score > threshold`, so a score of `100` against a threshold of `100` is `false` — an allow, for a request configured to block.

        Getting that inversion silently is the one failure this feature must not have, so the score is deliberately outside the prompt's stated scale. `UGw` does not range-check.
        """
        verdict = classify(
            classifier_request(stop_sequences=["</severity>"]), config(decision="block")
        )
        assert verdict is not None
        score = parses_as_severity(verdict_text(verdict, config().block_reason_str))
        assert score is not None
        assert score > 100


class TestTheParserOracleMatchesEcmascript:
    """The transliterated parsers are only worth anything if they disagree with the real one nowhere.

    Each case is a string a reviewer ran through both the real JS parser and this file's Python one, back when they disagreed. Python's defaults are the culprit in every one: Unicode word boundaries, Unicode case folding, Unicode `\\d`, and a `\\s` that is not ECMAScript's.
    """

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            # U+00E9 is not an ASCII word character, so `\b` holds after `yes` -- JS reads a decision here.
            ("<block>yes\u00e9", True),
            # Python's Unicode case folding maps U+017F onto `s`; ECMAScript's non-`u` canonicalisation does not, so `ye` + U+017F is not `yes` and nothing parses.
            ("<block>ye\u017f</block>", None),
        ],
    )
    def test_block_parsing_follows_ascii_rules(self, text: str, expected: bool | None) -> None:
        assert parses_as_block(text) is expected

    @pytest.mark.parametrize(
        "text",
        [
            # Arabic-Indic digit U+0661: Python's `\d` accepts it, ECMAScript's does not.
            "<severity>\u0661</severity>",
            # U+001C is in Python's default `\s` and not in ECMAScript's.
            "<severity>\u001c0</severity>",
        ],
    )
    def test_severity_parsing_rejects_what_ecmascript_rejects(self, text: str) -> None:
        assert parses_as_severity(text) is None


class ExplodingProvider:
    """A provider that fails the test if anything asks it to call upstream.

    Recording what was sent and asserting the list is empty proves the same thing, but one step later and one step weaker: a `send` that happened for a reason the assertion did not anticipate still shows up as an empty list if the payload never reached `sent`. Raising here means the failure is attributed to the call itself.
    """

    name = "ghc"

    def __init__(self, *, endpoint: ModelEndpoint = ModelEndpoint.ANTHROPIC_MESSAGES) -> None:
        self._endpoint = endpoint

    @property
    def available_ids(self) -> frozenset[str]:
        return frozenset({"claude-model"})
    @property
    def raw_catalog(self) -> Mapping[str, Any]:
        return {}


    # Reporting-only members of the provider protocol, here so this stub satisfies it. Nothing on this test's path reads them; `/api/status` does.
    @property
    def disabled_ids(self) -> frozenset[str]:
        return frozenset()

    @property
    def base_url(self) -> str:
        return "https://stub.invalid"

    @property
    def catalog_refreshed_at(self) -> str:
        return "2026-08-27T00:00:00+00:00"

    def describe(self, model_id: str) -> ModelDescriptor | None:
        if model_id != "claude-model":
            return None
        return ModelDescriptor(id=model_id, endpoints=frozenset({self._endpoint}))

    async def refresh_catalog(self) -> bool:
        return False

    async def send(self, *args: Any, **kwargs: Any) -> httpx2.Response:
        raise AssertionError("upstream was called for a request that should have been answered locally")

    async def count_tokens(self, *args: Any, **kwargs: Any) -> httpx2.Response:
        raise AssertionError("upstream was asked to count a locally answered request")


def chain_with(
    decision: AutoModeDecision,
    *,
    endpoint: ModelEndpoint = ModelEndpoint.ANTHROPIC_MESSAGES,
    block_reason_str: str | None = None,
) -> Any:
    intercept: dict[str, Any] = {"decision": decision}
    if block_reason_str is not None:
        intercept["block_reason_str"] = block_reason_str
    config = ProxyConfig.model_validate(
        {
            "default_model_provider": "ghc",
            "model_providers": {"ghc": {"type": "github_copilot"}},
            "hook_fix_anthropic_request": {"intercept_auto_mode_classifier": intercept},
        }
    )
    # Constructing the chain opens no connection, so the client needs no teardown here.
    return build_chain(
        config,
        http_client=httpx2.AsyncClient(),
        providers={"ghc": ExplodingProvider(endpoint=endpoint)},
    )


class TestTheShortCircuitIsWiredIn:
    """Recognition proves a predicate works. This proves `handle()` consults it on the path a request actually takes.

    The distinction has cost this project before: a guard can be correct, tested, and stranded on a chain nothing calls any more.
    """

    async def test_a_recognised_request_never_reaches_upstream(self) -> None:
        context = RequestContext(
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            requested_model="claude-model",
            payload=classifier_request(),
        )

        handled = await handle(chain_with("allow"), context)

        assert handled.synthesized is True
        assert handled.response is not None
        body = orjson.loads(handled.response.read())
        assert parses_as_block(body["content"][0]["text"]) is False

    async def test_the_same_request_is_forwarded_when_the_feature_is_off(self) -> None:
        """The negative that gives the test above its meaning: with the default config this request goes upstream, and `ExplodingProvider` is what says so.

        The driver catches what a provider raises and hands it back on the outcome rather than letting it escape, so this reads the outcome. `pytest.raises` here passed for the wrong reason once — nothing propagated, and an assertion that the call *did not* happen would have looked identical.
        """
        context = RequestContext(
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            requested_model="claude-model",
            payload=classifier_request(),
        )

        handled = await handle(chain_with("passthrough"), context)

        assert handled.synthesized is False
        assert isinstance(handled.outcome.error, AssertionError)
        assert "upstream was called" in str(handled.outcome.error)

    async def test_a_severity_run_is_answered_in_the_severity_protocol(self) -> None:
        """The only regression guard on the protocol bug, and it has to go through `handle()` to be one.

        Every other severity case stops at `classify` + `verdict_text`. This one builds the shape that was actually mishandled — a severity run with **no** `stop_sequences`, which is what stage 2 sends — and reads the synthesised reply the way the client does, `stop_reason` gate included.
        """
        payload = classifier_request(
            system_text=MONITOR_PROMPT
            + "\n\n## Output Format\n\nOutput <severity>N</severity> where N is an integer 0-100…"
        )
        context = RequestContext(
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            requested_model="claude-model",
            payload=payload,
        )

        handled = await handle(chain_with("block"), context)

        assert handled.synthesized is True
        assert handled.response is not None
        score = severity_of_reply(orjson.loads(handled.response.read()))
        assert score is not None
        assert score > 100

    async def test_the_configured_reason_reaches_the_synthesised_reply(self) -> None:
        """The wiring, not the formatter.

        `verdict_text` taking a reason and putting it in `<reason>` was already covered — by calling it directly, which is exactly what hides this: nothing proved `handle()` reads the reason *from the configuration*. A reviewer replaced that lookup with a hardcoded string and the whole file stayed green.

        So this asserts on a value that only exists in the config object, and would not appear in the reply by any other route.
        """
        marker = "refused by the operator, and this exact sentence proves the lookup happened"
        chain = chain_with("block", block_reason_str=marker)
        context = RequestContext(
            inbound_format=WireFormat.ANTHROPIC_MESSAGES,
            requested_model="claude-model",
            payload=classifier_request(),
        )

        handled = await handle(chain, context)

        assert handled.response is not None
        body = orjson.loads(handled.response.read())
        text = body["content"][0]["text"]
        assert parses_as_block(text) is True
        assert f"<reason>{marker}</reason>" in text

    async def test_a_chat_completions_request_is_never_answered_as_anthropic(self) -> None:
        """The endpoint boundary. Without it, a legal Chat Completions body whose content parts happened to match the markers came back as an Anthropic Message on `/chat/completions` — a protocol its caller has no reason to read — and the real request never reached upstream.

        The markers describe a body, not an endpoint. Which endpoint a request arrived on is something the route already knows, and that is what decides here.
        """
        payload = classifier_request()
        payload["stream"] = False
        context = RequestContext(
            inbound_format=WireFormat.OPENAI_CHAT_COMPLETIONS,
            requested_model="claude-model",
            payload=payload,
        )

        handled = await handle(
            chain_with("allow", endpoint=ModelEndpoint.OPENAI_CHAT_COMPLETIONS), context
        )

        assert handled.synthesized is False
        assert isinstance(handled.outcome.error, AssertionError)
