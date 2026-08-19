"""What the attached terminal can actually do.

Probed, not configured. A switch cannot know whether the process was started under systemd, piped into a file, or run in a CI job that sets `TERM=dumb` — and every one of those answers differs from what the operator's own terminal can do. Asking the environment gets the right answer in all of them without anybody maintaining a setting.

The three capabilities are separate on purpose. A `TERM=dumb` terminal is still a terminal: it takes plain lines and nothing else. A pipe to `tee` takes UTF-8 happily but must never see a cursor-moving escape. Collapsing them into one boolean would tie the fate of the byte-count glyph to whether a live region is possible, which are unrelated questions.
"""

import os
import sys
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True, slots=True)
class TerminalCapabilities:
    """What may be sent to this stream.

    `live` gates the footer, because a live region rewrites lines that were already emitted, and anything reading the output as a byte stream — a log file, a CI collector, a pipe — gets a mess of escapes instead of the log it asked for.

    `color` and `unicode` gate decoration only. They are answered separately from `live` because a destination can accept one and not the others.
    """

    live: bool
    color: bool
    unicode: bool

    @property
    def plain(self) -> bool:
        """True when nothing beyond 7-bit text may be emitted."""
        return not (self.live or self.color or self.unicode)


def _is_tty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        # A closed or substituted stream answers neither yes nor no. Treat it as not a terminal: the cost of being wrong that way is plain output, and the cost of being wrong the other way is escape sequences in someone's log.
        return False


def _supports_unicode(stream: TextIO, probe: str) -> bool:
    """Whether `probe` survives this stream's encoding.

    Asked by encoding rather than by name: a terminal is capable of whatever its encoding can carry, and guessing from `TERM` or the platform gets legacy code pages wrong in both directions. `errors` matters too — a stream that replaces unencodable characters would not raise, and the glyph would silently arrive as `?`.
    """
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return False
    try:
        probe.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def detect_terminal(stream: TextIO | None = None, environ: dict[str, str] | None = None, *, probe: str = "↓") -> TerminalCapabilities:
    """Ask the stream and the environment what may be sent.

    `NO_COLOR` and `TERM=dumb` are honoured because they are the two conventions a user actually has to hand; `CI` is honoured because a CI job is a terminal that nobody is watching, and a live region there produces a log full of cursor movements for no reader.
    """
    target = stream if stream is not None else sys.stderr
    env = environ if environ is not None else dict(os.environ)

    tty = _is_tty(target)
    term = env.get("TERM", "")
    dumb = term == "dumb" or (tty and not term)
    interactive = tty and not dumb and not env.get("CI")

    return TerminalCapabilities(
        live=interactive,
        # `NO_COLOR` is about colour alone, so it must not take the footer down with it. The convention is "present **and non-empty**": `NO_COLOR=` is how a caller unsets an inherited value in a shell that cannot delete it, and reading that as "disable colour" does the opposite of what was asked.
        color=interactive and not env.get("NO_COLOR"),
        # Independent of `live`: a file or a pipe still renders UTF-8 correctly, and there is no reason to degrade the byte-count glyph just because the footer cannot run.
        unicode=_supports_unicode(target, probe),
    )
