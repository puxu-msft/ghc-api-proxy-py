"""What the attached terminal can actually do.

Probed, not configured. A switch cannot know whether the process was started under systemd, piped into a file, or run in a CI job that sets `TERM=dumb` — and every one of those answers differs from what the operator's own terminal can do. Asking the environment gets the right answer in all of them without anybody maintaining a setting.

The three capabilities are separate on purpose. A `TERM=dumb` terminal is still a terminal: it takes plain lines and nothing else. A pipe to `tee` takes UTF-8 happily but must never see a cursor-moving escape. Collapsing them into one boolean would tie the fate of the byte-count glyph to whether a live region is possible, which are unrelated questions.
"""

import os
import sys
from dataclasses import dataclass
from typing import TextIO

# The palette, kept here because this module already owns the question of what the terminal can take. One definition means the log line and the footer cannot drift into disagreeing about what "dim" is.
RESET = "\x1b[0m"
DIM = "\x1b[2m"
RED = "\x1b[31m"
GREEN = "\x1b[32m"
YELLOW = "\x1b[33m"
MAGENTA = "\x1b[35m"
CYAN = "\x1b[36m"
WHITE = "\x1b[37m"
BOLD_RED = "\x1b[1;31m"


def paint(text: str, code: str, *, color: bool) -> str:
    """Wrap `text` in one self-contained SGR span.

    Self-contained on purpose: each span carries its own reset and none of them nest. A nested span's reset would end the enclosing one too, which is how a line ends up half-coloured in a way nobody can reproduce from reading the code.
    """
    return f"{code}{text}{RESET}" if color and text else text


def duration_colour(seconds: float) -> str:
    """Escalating severity for how long a request took, thresholds ported from `copilot-api-js`.

    A slow request is worth noticing, and the escalation is what makes it noticeable without reading the number. No dim (terminals render it as grey, which reads as "ignore me") and no magenta, which would collide with the model name.
    """
    if seconds <= 20:
        return WHITE
    if seconds <= 60:
        return YELLOW
    if seconds <= 180:
        return RED
    return BOLD_RED


def volume_colour(value: float, *, notable: float, heavy: float) -> str:
    """A severity ramp for "how much came back": quiet below `notable`, plain up to `heavy`, warm above it.

    Grey rather than absent for the small case, because most replies are small and a column that shouts on every line stops carrying information. The escalation is the point: a reply an order of magnitude bigger than usual is worth seeing without reading the number, which is the same reason `duration_colour` exists.

    Stops at yellow. Red and bold red are spoken for by failure and by a request that has run long enough to be a problem, and a large reply is neither — it is worth noticing, not worth alarm.
    """
    if value < notable:
        return DIM
    if value < heavy:
        return WHITE
    return YELLOW


def cache_hit_colour(percent: int) -> str:
    """Severity for a prompt-cache hit rate — inverted, because a high rate is the good case.

    Healthy stays quiet and a collapsing rate escalates, which is the opposite direction from duration and deliberately so: here the number getting *smaller* is what costs money.
    """
    if percent >= 80:
        return DIM
    if percent >= 40:
        return YELLOW
    if percent >= 20:
        return RED
    return BOLD_RED


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
