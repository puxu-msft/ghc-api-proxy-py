"""Proof that the harness is what it claims, before anything is asserted on top of it.

A group like this one fails in a way the others cannot: if the binary silently talked to the real
API, or the proxy never started and the client fell back somewhere, every later test could still
pass while measuring nothing. These two check the plumbing itself.
"""

from pathlib import Path

from harness import run_claude, running_proxy
from upstream import ScriptedUpstream, anthropic_text


def test_the_client_reaches_the_model_through_the_proxy(config_dir: Path) -> None:
    """The whole path in one assertion: the binary's answer came from this test's own script.

    `MARKER` is unguessable rather than plausible on purpose. A test asserting the reply merely
    looks like an answer would pass just as well if the request had gone to the real API.
    """
    marker = "e2e-marker-7Qk2"
    upstream = ScriptedUpstream(replies=[anthropic_text(marker)])

    with running_proxy(upstream) as proxy:
        result = run_claude("say the marker", proxy=proxy, config_dir=config_dir)

    assert marker in result.stdout, result.stderr
    assert result.returncode == 0
    assert upstream.seen, "the proxy never called upstream, so the reply came from somewhere else"


def test_the_proxy_and_not_the_client_decides_what_upstream_receives(config_dir: Path) -> None:
    """The client asks for `claude-model`; upstream is asked for the id the catalog resolved.

    This is the assertion that separates a real end-to-end from a client talking to a fake: it
    inspects the body the *proxy* sent, which only exists if the proxy was in the path at all.
    """
    upstream = ScriptedUpstream(replies=[anthropic_text("ok")])

    with running_proxy(upstream) as proxy:
        run_claude("hello", proxy=proxy, config_dir=config_dir)

    assert upstream.seen
    assert upstream.seen[0].body.get("model") == "claude-model"
    assert upstream.seen[0].path.endswith("/messages")
