"""`debug models`: which models each configured provider offers, and what this proxy can do with them.

Fetched live from upstream through the server's own composition root rather than read out of a running proxy. The questions this answers — is the model on offer at all, is it disabled here, does this proxy have a driver for the endpoint it advertises — get asked when requests are being refused or the service will not start, which is exactly when there is no running instance to ask.

The renderer reads `ModelRow`, never the wire payload: one place decides what a catalog entry means, so the table and any later consumer cannot disagree about it. `--json` is the deliberate exception — it hands back the decoded payload unprojected, because the reason to ask for it is to see everything upstream said rather than the seven columns the table picked.
"""

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from rich.cells import cell_len

from app.config.schema import ProxyConfig
from app.model_provider import GithubCopilotProvider, model_type_of, resolve_endpoints
from app.model_provider.ghc_client.auth.providers import NoGitHubToken
from app.model_provider.github_copilot import DRIVEN_ENDPOINTS
from app.observability.footer import CONTROL_CHARS
from app.server.composition import build_chain, build_http_client

# The one status that means a request naming this model would be routed.
ROUTABLE = "ok"

# Marks an endpoint upstream advertises that this proxy has no driver for.
UNDRIVEN_MARK = "*"

# Marks an endpoint upstream never named, filled in from the default for the model's kind.
ASSUMED_MARK = "?"

_ENABLED_POLICY = "enabled"
_MISSING = "-"


@dataclass(frozen=True, slots=True)
class ModelRow:
    """One model, already reduced to what a report shows.

    Missing numbers are `None` rather than 0: a model that did not state its context window and one that stated zero are different answers, and only the second is a reason to look at the model.

    `assumed` says the endpoint list came from the default for the model's kind rather than from the catalog. Routing does not distinguish them, but a report that showed an assumption in the same ink as something upstream said would stop being usable as evidence about upstream.
    """

    id: str
    status: str
    vendor: str
    family: str
    endpoints: tuple[str, ...]
    undriven: frozenset[str]
    context_window: int | None
    max_output_tokens: int | None
    assumed: bool = False


@dataclass(frozen=True, slots=True)
class ProviderCatalog:
    """One provider's answer, kept whole: the rows a report shows, the payload they came from, and how much of that payload yielded no row.

    `unreadable` is carried rather than recomputed at render time so the count and the rows can never come from two different readings of the payload.
    """

    name: str
    base_url: str
    raw: Mapping[str, Any]
    rows: tuple[ModelRow, ...]
    unreadable: int = 0


@dataclass(frozen=True, slots=True)
class CatalogFailure:
    """A provider that could not be read, and why. Reported rather than raised, so one dead upstream does not hide a healthy one."""

    name: str
    reason: str


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        return {}
    return cast(Mapping[str, Any], value)


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _count(value: object) -> int | None:
    # `bool` is an `int`; a limit reported as `true` is not a number.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _printable(text: str) -> str:
    """Strip control characters from a string on its way into the report.

    Every string here is upstream text this proxy does not control, and a newline inside a model id draws a second physical line that the reader counts as another model while its remaining columns land under the wrong headings. `src/app/observability/footer.py` strips the same class for the same reason on the other display path; the pattern is shared rather than reimplemented so both cannot disagree about what a control character is.

    `--json` deliberately does not go through this: the reason to ask for the payload is to see exactly what upstream sent, control characters included.
    """
    return CONTROL_CHARS.sub("", text)


def status_of(
    *,
    disabled: bool,
    policy_state: str,
    offered: bool,
    drivable: bool,
    malformed: bool = False,
) -> str:
    """One word for why a request naming this model would not get through.

    Ordered by who can act on it: the disabled list is the operator's to edit, the policy state is theirs to accept on github.com, an offering of nothing is upstream's to change, and a missing driver is ours to write. Reporting the first of those hides nothing — clearing it re-runs this command and reveals the next.

    `no-endpoints` means no endpoint is known for this model, and it covers two ways of getting there: upstream sent an explicit empty list, or upstream said nothing and the model's `capabilities.type` has no measured default. Neither has been seen in a live catalog. They are one word because the operator's next step is the same — look at what upstream actually sent — and `--json` carries the `capabilities.type` that tells them apart. What it never means is the ordinary absent key: `resolve_endpoints` fills those in, so they do not reach here.

    `malformed` outranks the rest because it is the one answer that is not about this model. A `supported_endpoints` that arrived as a string rather than a list is a field we could not read at all, and it must not be reported as a confident claim about what upstream offers.

    An upstream policy state is prefixed rather than reported as itself, because it is the one word in this vocabulary that upstream chooses. Left bare, a state spelled `ok` would report a gated model as routable and a state spelled `disabled` would be indistinguishable from the operator's own list — the two answers with the most different fixes, collapsed by a coincidence of spelling. The prefix is also where the state is stripped of control characters, since this is the single point at which upstream text becomes a token the report repeats in its summary line as well as its table.
    """
    if malformed:
        return "malformed"
    if disabled:
        return "disabled"
    if policy_state and policy_state != _ENABLED_POLICY:
        return f"policy:{_printable(policy_state)}"
    if not offered:
        return "no-endpoints"
    if not drivable:
        return "no-driver"
    return ROUTABLE


def _wrong_shape(model: Mapping[str, Any]) -> bool:
    """Whether a field this report reads arrived as a type it cannot mean.

    Absence is not wrong shape — most of this catalog's entries legitimately omit `supported_endpoints` and `policy`. What is checked is a key that is present and holds something the reader would otherwise silently coerce into a confident wrong answer.
    """
    endpoints = model.get("supported_endpoints")
    if endpoints is not None and not isinstance(endpoints, list):
        return True
    # `capabilities.type` decides which endpoint an unstated model gets, so an unreadable one is the same class of defect as an unreadable endpoint list — and without this it would read as `no-endpoints`, losing the fact that the catalog's shape is wrong.
    capabilities: object = model.get("capabilities")
    if capabilities is not None and not isinstance(capabilities, dict):
        return True
    model_type: object = _mapping(model.get("capabilities")).get("type")
    if model_type is not None and not isinstance(model_type, str):
        return True
    policy: object = model.get("policy")
    if policy is not None and not isinstance(policy, dict):
        return True
    state: object = _mapping(model.get("policy")).get("state")
    return state is not None and not isinstance(state, str)


def build_rows(
    raw: Mapping[str, Any],
    *,
    disabled: Sequence[str] = (),
) -> tuple[tuple[ModelRow, ...], int]:
    """Project an upstream catalog payload onto the rows a report shows, and count what could not be projected at all.

    Every field is read defensively and no entry is validated as a whole. This command exists to show what a catalog nobody here controls actually contains, so it must not be the thing that fails when that catalog grows a shape we have not seen — a model with an unreadable limit still has an id, a vendor and an endpoint list worth printing.

    Tolerating a bad entry is not the same as hiding it. An entry with no readable id yields no row and cannot, so it is counted and the count is reported; an entry that has an id but whose fields arrived wrong-typed becomes a row that says `malformed` rather than one that quietly asserts something about upstream.
    """
    entries = raw.get("data")
    if not isinstance(entries, list):
        return (), 0
    blocked = frozenset(disabled)
    rows: list[ModelRow] = []
    unreadable = 0
    for entry in cast(list[object], entries):
        model = _mapping(entry)
        model_id = _text(model.get("id"))
        if not model_id:
            unreadable += 1
            continue
        capabilities = _mapping(model.get("capabilities"))
        limits = _mapping(capabilities.get("limits"))
        # The same resolution routing uses, read through the same accessor, so the two cannot drift over what `capabilities.type` says.
        resolved = resolve_endpoints(
            model.get("supported_endpoints"),
            model_type=model_type_of(model),
        )
        offered = tuple(
            sorted([endpoint.value for endpoint in resolved.known] + list(resolved.unknown))
        )
        # An endpoint we have no enum member for is by definition one we cannot drive.
        undriven = frozenset(
            [endpoint.value for endpoint in resolved.known if endpoint not in DRIVEN_ENDPOINTS]
            + list(resolved.unknown)
        )
        rows.append(
            ModelRow(
                id=model_id,
                status=status_of(
                    disabled=model_id in blocked,
                    policy_state=_text(_mapping(model.get("policy")).get("state")),
                    offered=bool(offered),
                    drivable=bool(set(offered) - undriven),
                    malformed=_wrong_shape(model),
                ),
                vendor=_text(model.get("vendor")),
                family=_text(capabilities.get("family")),
                endpoints=offered,
                undriven=undriven,
                # Filled in only counts when something actually was: an unmeasured kind yields no endpoint, and calling that `assumed` printed a legend about a standard endpoint next to an empty column.
                assumed=bool(offered) and not resolved.advertised,
                context_window=_count(limits.get("max_context_window_tokens")),
                max_output_tokens=_count(limits.get("max_output_tokens")),
            )
        )
    return tuple(sorted(rows, key=lambda row: row.id)), unreadable


async def collect_catalogs(
    config: ProxyConfig,
    only: str | None = None,
) -> tuple[tuple[ProviderCatalog, ...], tuple[CatalogFailure, ...]]:
    """Fetch every configured provider's catalog, or just the named one.

    Assembled by `build_chain` rather than by wiring a client here, so what this prints is what the server would see: the same token chain, the same per-provider base URL and token file, the same catalog request. A report built from a second, simpler client could disagree with the running service about which models exist, which would make it worse than no report at all.

    A provider that fails is recorded and the loop continues. `Exception` is caught broadly and deliberately: the failure modes here run from an absent token to a TLS error inside a proxy's transport, nothing about them is a bug in this command, and the caller reports every one of them and exits non-zero.
    """
    catalogs: list[ProviderCatalog] = []
    failures: list[CatalogFailure] = []
    http_client = build_http_client(config)
    try:
        chain = build_chain(config, http_client=http_client)
        names = [only] if only is not None else sorted(chain.providers.names)
        for name in names:
            provider = chain.providers.get(name)
            if not isinstance(provider, GithubCopilotProvider):
                failures.append(CatalogFailure(name, "provider type publishes no catalog"))
                continue
            try:
                await provider.refresh_catalog()
            except Exception as error:
                failures.append(CatalogFailure(name, describe_failure(error)))
                continue
            rows, unreadable = build_rows(
                provider.raw_catalog,
                disabled=config.model_providers[name].disabled_models,
            )
            catalogs.append(
                ProviderCatalog(
                    name=name,
                    base_url=provider.base_url,
                    raw=provider.raw_catalog,
                    rows=rows,
                    unreadable=unreadable,
                )
            )
    finally:
        await http_client.aclose()
    return tuple(catalogs), tuple(failures)


def describe_failure(error: BaseException) -> str:
    """Say what went wrong, and for the one cause the operator fixes themselves, say how."""
    if isinstance(error, NoGitHubToken):
        return f"{error} — run `ghc-api-proxy auth`"
    return str(error) or type(error).__name__


def _number(value: int | None) -> str:
    return _MISSING if value is None else str(value)


def _endpoint_cell(row: ModelRow) -> str:
    """The endpoint list, with each entry marked for why it is not plain.

    `*` and `?` are mutually exclusive in practice — an assumed endpoint is always one we drive — but both are applied rather than chosen between, so a future default we cannot drive would still say both things.
    """
    parts = [
        f"{endpoint}{UNDRIVEN_MARK}" if endpoint in row.undriven else endpoint
        for endpoint in row.endpoints
    ]
    if row.assumed:
        parts = [f"{part}{ASSUMED_MARK}" for part in parts]
    return ", ".join(parts) or _MISSING


def _cells(row: ModelRow) -> tuple[str, ...]:
    return tuple(
        _printable(cell)
        for cell in (
            row.id,
            row.status,
            row.vendor or _MISSING,
            row.family or _MISSING,
            _number(row.context_window),
            _number(row.max_output_tokens),
            _endpoint_cell(row),
        )
    )


_HEADERS = ("ID", "STATUS", "VENDOR", "FAMILY", "CONTEXT", "OUT", "ENDPOINTS")
_RIGHT_ALIGNED = frozenset({4, 5})


def _pad(cell: str, width: int, *, right: bool) -> str:
    """Pad to a width measured in terminal cells rather than code points.

    A CJK or emoji character occupies two columns, so `str.ljust` under-pads it by one per character and the columns after it step left. `rich.cells` is already in the dependency tree and is what the footer measures with.
    """
    filler = " " * max(0, width - cell_len(cell))
    return filler + cell if right else cell + filler


def _table(rows: Sequence[tuple[str, ...]]) -> list[str]:
    """Lay the cells out in columns.

    The last column is never padded, so nothing carries trailing whitespace into a paste.
    """
    widths = [
        max(cell_len(header), max((cell_len(row[index]) for row in rows), default=0))
        for index, header in enumerate(_HEADERS)
    ]
    last = len(_HEADERS) - 1

    def line(cells: Sequence[str]) -> str:
        parts = [
            cell if index == last else _pad(cell, widths[index], right=index in _RIGHT_ALIGNED)
            for index, cell in enumerate(cells)
        ]
        return "  ".join(parts)

    return [line(_HEADERS), *(line(cells) for cells in rows)]


def _summary(catalog: ProviderCatalog) -> str:
    """`40 models, 37 routable, 2 disabled, 1 policy:unconfigured`.

    The breakdown is counted from the statuses themselves rather than from a fixed list, so a policy state upstream invents tomorrow is reported by name instead of being folded into an "other".

    Entries that produced no row at all are named too. Dropping them silently would let a catalog of eight entries report "4 models" in a tone indistinguishable from a catalog that really held four — in a command whose entire job is to say what upstream sent.
    """
    rows = catalog.rows
    total = len(rows)
    routable = sum(1 for row in rows if row.status == ROUTABLE)
    blocked = Counter(row.status for row in rows if row.status != ROUTABLE)
    # Always plural. A singular branch buys "1 model" at the cost of a second spelling for every count in the line, and `1 models` costs the reader nothing.
    parts = [f"{total} models", f"{routable} routable"]
    parts.extend(f"{count} {status}" for status, count in sorted(blocked.items()))
    summary = ", ".join(parts)
    if catalog.unreadable:
        summary += f" ({catalog.unreadable} unreadable entries skipped)"
    return summary


def render_text(catalogs: Sequence[ProviderCatalog]) -> str:
    """The default report: one block per provider."""
    blocks: list[str] = []
    for catalog in catalogs:
        lines = [
            f"{_printable(catalog.name)}  {_printable(catalog.base_url)}",
            _summary(catalog),
        ]
        if catalog.rows:
            lines.append("")
            lines.extend(_table([_cells(row) for row in catalog.rows]))
        else:
            lines.append("upstream offered no models")
        legend = [
            (any(row.undriven for row in catalog.rows), f"{UNDRIVEN_MARK} advertised by upstream, no driver in this proxy"),
            (any(row.assumed for row in catalog.rows), f"{ASSUMED_MARK} not named by upstream; the standard endpoint for this model type"),
        ]
        marks = [text for applies, text in legend if applies]
        if marks:
            lines.append("")
            lines.extend(marks)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_json(catalogs: Sequence[ProviderCatalog], *, keyed: bool = True) -> str:
    """Every provider's decoded payload, complete and unprojected.

    Not the upstream bytes: the response was parsed to JSON before it reached here, so whitespace, escape spelling and any duplicate object key are already gone. What survives is every field of the decoded catalog, which is what distinguishes this from the table — the table shows seven columns, this shows everything upstream said.

    `keyed` reflects what was asked for, not how many providers happen to be configured. The wrapper is dropped only when it also leaves exactly one payload to return — two catalogs cannot be one document, so a `keyed=False` that arrived alongside several of them keeps the names rather than picking a winner. Without `--provider` the caller asked about the deployment and the answer has to say which upstream each payload came from; with it they named one, and wrapping that single answer in a key they already typed only makes it something to unwrap again.
    """
    if not keyed and len(catalogs) == 1:
        return json.dumps(dict(catalogs[0].raw), indent=2, ensure_ascii=False)
    return json.dumps(
        {catalog.name: dict(catalog.raw) for catalog in catalogs},
        indent=2,
        ensure_ascii=False,
    )


__all__ = [
    "ASSUMED_MARK",
    "ROUTABLE",
    "UNDRIVEN_MARK",
    "CatalogFailure",
    "ModelRow",
    "ProviderCatalog",
    "build_rows",
    "collect_catalogs",
    "describe_failure",
    "render_json",
    "render_text",
    "status_of",
]
