"""Model name resolution, per the rules in `config.example.yaml`.

`model_mappings` is the sole source; there are no built-in defaults.

The spec's compatibility rules are matching rules, not rewriting rules.
They decide which mapping key an inbound name hits.
The date suffix is deliberately not among them; since 2026/07/16 it must be configured.

**Resolution is two passes, and it has to be.** A mapping value may name the provider that serves it (`claude-opus-4.8: A/claude-opus-5`), so the provider is not known until the chain has been walked — while the catalog that decides when the walk is over belongs to that same provider. One function cannot close that loop. So `discover_provider` walks the chain without consulting any catalog and answers only "whose is this", and `resolve_against_catalog` then answers "what is it called there". `.dev/docs/multi-provider-routing/spec.md` §2 is the normative statement of both.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

BRACKET_SUFFIX = re.compile(r"^(?P<base>.+)\[(?P<suffix>[^\]]+)\]$")
_MAX_ALIAS_HOPS = 8

# What separates a provider name from the model name in a qualified value or an inbound model name. `/` rather than `@`, which `split_format_suffix` already spends on the wire format, and rather than `:`, which YAML would make an operator quote.
QUALIFIER_SEPARATOR = "/"

# Where the provider serving a request came from. A closed set of exactly three, and that is a property worth keeping: `discover_provider` returns on the first qualifier it reads, so a chain cannot contribute a second opinion, and `/api/status` can report `origin` as an enumeration rather than as prose. Spec §2.2.
type ProviderOrigin = Literal["qualified", "fallback", "default"]


@dataclass(frozen=True, slots=True)
class ModelResolution:
    requested: str
    resolved: str
    matched_key: str = ""
    passthrough: bool = False
    hops: int = 0


@dataclass(frozen=True, slots=True)
class ProviderDiscovery:
    """Which provider serves an inbound name, and what the alias chain called it by the end.

    `provider` is filled only for `origin == "qualified"`. For `fallback` and `default` the name is the caller's to supply, because it comes from configuration this module does not read.
    """

    target: str
    provider: str = ""
    origin: ProviderOrigin = "default"
    matched_key: str = ""
    hops: int = 0
    # The mapping value the walk stopped on, when it stopped on a qualifier. Carried so an error can quote the line that is actually wrong: the key names the alias, and it is the **value** that names a provider — a message built from the key alone sends an operator to check the wrong half of the entry. Empty when no qualifier was read.
    value: str = ""


def canonical(name: str) -> str:
    """Fold the spellings the spec calls equivalent.

    Case is insensitive and `.` and `-` are interchangeable.
    `claude-opus-4-5` and `claude-opus-4.5` are therefore the same key.
    """
    return name.strip().lower().replace(".", "-")


def candidate_keys(name: str) -> tuple[str, ...]:
    """The keys an inbound name may hit, in the order the spec tries them.

    `opus[1m]` tries `opus-1m` before `opus`, so a bracket-specific mapping wins over the base one.
    """
    stripped = name.strip()
    candidates = [stripped]
    bracket = BRACKET_SUFFIX.match(stripped)
    if bracket is not None:
        base = bracket.group("base")
        candidates.append(f"{base}-{bracket.group('suffix')}")
        candidates.append(base)

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        key = canonical(candidate)
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    return tuple(ordered)


def _index(mappings: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    """Index mappings by canonical key, keeping the original key for reporting."""
    return {canonical(key): (key, value) for key, value in mappings.items()}


def split_provider_qualifier(
    value: str, provider_names: frozenset[str]
) -> tuple[str | None, str, bool]:
    """Read `A/model` into its provider and its model, if it is qualified at all.

    Returns `(provider, model, qualified)`. `qualified` says a separator was present — which is what makes the value a terminus (Spec §2.2 rules 1 and 2) — while `provider` is `None` when the name before the separator is not one this deployment configured.

    Three details, each of which was decided rather than fallen into:

    - `partition`, not `rpartition`: the **first** separator wins, so a provider name may not contain `/` while a model name may keep one. Today no Copilot model id does (measured 2026-08-26, spec §7.1), but a `vendor/model` id is common enough elsewhere that giving the model side the remainder costs nothing and reserves the possibility.
    - The provider name is matched **exactly**. `canonical` folds case and treats `.` and `-` as one character, which is right for model names and wrong for a YAML key that an operator chose.
    - Splitting happens **before** anything calls `canonical` on the value. Running it first would lower-case the provider name and turn its dots into dashes, so `model_providers` keys containing either would stop matching themselves.
    """
    head, separator, tail = value.partition(QUALIFIER_SEPARATOR)
    if not separator:
        return None, value, False
    if head in provider_names:
        return head, tail, True
    # Qualified but unrecognised. The prefix is dropped rather than kept as part of the model name: keeping it would send a string no catalog can contain to whichever provider answered, and the rejection would come back from upstream, a whole leg away from the typo that caused it.
    return None, tail, True


def discover_provider(
    requested: str,
    *,
    mappings: Mapping[str, str],
    provider_names: frozenset[str],
) -> ProviderDiscovery:
    """Walk the alias chain far enough to learn which provider serves this name.

    **No catalog is consulted here**, and that is the whole point of the pass existing. The obvious alternative — keep the existing loop, which stops as soon as a name lands in the catalog, and read qualifiers as it goes — cannot work: `fable: claude-opus-5` puts a catalog name on the chain at hop one, so the loop returns there and a qualifier written on `claude-opus-5`'s own entry is never read. The same model would then be served by different providers depending on whether the client spelled it `fable` or `claude-opus-5`, silently. Spec §9.2.

    Reading a qualifier ends the walk (Spec §2.2). That is what keeps a self-mapping like `claude-opus-5: A/claude-opus-5` — the only way to route a model whose name needs no rewriting — from being a cycle: the value is qualified, so it is a terminus and nothing follows it.
    """
    index = _index(mappings)
    current = requested.strip()
    matched_key = ""

    for hop in range(_MAX_ALIAS_HOPS):
        entry = next(
            (index[key] for key in candidate_keys(current) if key in index),
            None,
        )
        if entry is None:
            # Rule 4a: the chain simply ended. `hop` is the number of edges actually followed, which is what callers report; deriving it from the loop bound instead would say 8 for every chain, including one-hop ones.
            return ProviderDiscovery(
                target=current, origin="default", matched_key=matched_key, hops=hop
            )
        matched_key, value = entry
        provider, model, qualified = split_provider_qualifier(value, provider_names)
        if qualified:
            origin: ProviderOrigin = "qualified" if provider is not None else "fallback"
            return ProviderDiscovery(
                target=model,
                provider=provider or "",
                origin=origin,
                matched_key=matched_key,
                hops=hop + 1,
                value=value,
            )
        current = model

    # Rule 4b: the budget ran out with entries still to follow — a cycle, or a chain longer than anyone intended. The name the walk stopped on becomes the answer, and no qualifier was ever read, so this is `default` exactly like 4a. Indistinguishable from it in `origin`, which is why `inspect_mappings` looks for cycles separately. Spec §2.2.1.
    return ProviderDiscovery(
        target=current, origin="default", matched_key=matched_key, hops=_MAX_ALIAS_HOPS
    )


@dataclass(frozen=True, slots=True)
class MappingProblem:
    """Something wrong with `model_mappings` that can be seen without asking any upstream.

    `keys` names the mapping keys involved — the whole loop for a cycle, one key otherwise.
    """

    kind: Literal["unknown-provider", "empty-model", "cycle"]
    keys: tuple[str, ...]
    detail: str


def inspect_mappings(
    mappings: Mapping[str, str],
    provider_names: frozenset[str],
    *,
    fallback: str = "",
) -> tuple[MappingProblem, ...]:
    """Every problem in `model_mappings` that needs no catalog to find.

    "Needs no catalog" is the whole selection rule, and it is the user's: the two checks that were considered and cut — is the qualified model actually in that provider's catalog, is it disabled there — both depend on a live catalog, so they answer differently at start-up than they will an hour later, and they are served by `/api/status` instead. These three answer the same at any moment. Spec §5.1, §5.1.2.

    Reported, never raised. A deployment with a typo'd qualifier still starts and still serves everything else; the ruling was explicitly against failing start-up over this. Spec §5.1.

    `fallback` is the configured fallback provider's **name**, empty when there is none — not a boolean, because the wording is the point and the name is half of it. The same typo means "these keys go to B" in one deployment and "every request naming these keys will be refused" in another; an operator reading the first sentence should not have to open the configuration again to learn which provider B is. Spec §5.1.1.
    """
    problems: list[MappingProblem] = []

    for key, value in mappings.items():
        provider, model, qualified = split_provider_qualifier(value, provider_names)
        if qualified and provider is None:
            head = value.partition(QUALIFIER_SEPARATOR)[0]
            configured = ", ".join(sorted(provider_names)) or "none"
            consequence = (
                f"will be served by the fallback provider {fallback!r}"
                if fallback
                else "will be REFUSED, because no fallback_model_provider is set"
            )
            problems.append(
                MappingProblem(
                    kind="unknown-provider",
                    keys=(key,),
                    detail=(
                        f"{value!r} names provider {head!r}, which is not configured "
                        f"(configured: {configured}); requests for {key!r} {consequence}"
                    ),
                )
            )
        if not model.strip():
            problems.append(
                MappingProblem(
                    kind="empty-model",
                    keys=(key,),
                    detail=(
                        f"{value!r} carries no model name, so {key!r} can never resolve to "
                        "anything a catalog offers"
                    ),
                )
            )

    for cycle in find_alias_cycles(mappings, provider_names):
        problems.append(
            MappingProblem(
                kind="cycle",
                keys=cycle,
                detail=(
                    f"alias chain loops: {' -> '.join(cycle)} -> {cycle[0]}; requests entering it "
                    f"exhaust the {_MAX_ALIAS_HOPS}-hop budget and resolve to whichever name the "
                    "walk stopped on, silently"
                ),
            )
        )

    return tuple(problems)


def find_alias_cycles(
    mappings: Mapping[str, str], provider_names: frozenset[str]
) -> tuple[tuple[str, ...], ...]:
    """Alias chains that loop back on themselves, each reported once.

    A cycle costs the whole hop budget and then resolves to whatever name the walk happened to stop on, with no error — the symptom `discover_provider` cannot distinguish from an ordinary unmapped name, because both arrive at `origin="default"`. Spec §2.2.1 (c).

    Only **unqualified** edges can form one: a qualified value ends the walk where it is read, so `claude-opus-5: A/claude-opus-5` is a terminus rather than a self-loop. That is why this takes `provider_names` — whether an edge exists at all depends on which providers are configured. Spec §9.2.

    Each mapping key has at most one successor, so this is a functional graph and a walk needs no recursion: follow until the chain ends, meets a terminus, or revisits a node. `safe` carries the nodes already walked, which both bounds the work and de-duplicates — a three-node cycle is found from whichever of its entry points comes first and not again from the other two. Cycles are rotated to start at their lexicographically smallest member so the same loop reads the same way whichever key led to it.
    """
    index = _index(mappings)
    cycles: list[tuple[str, ...]] = []
    safe: set[str] = set()

    for key in mappings:
        # Two parallel lists: `path` holds the keys **as the operator wrote them**, `markers` holds their folded forms. Comparison needs the folded ones (`claude-opus-4.5` and `Claude-Opus-4-5` are one key); the report needs the written ones, or an operator greps the configuration for a name that is not in it.
        path: list[str] = []
        markers: list[str] = []
        on_path: set[str] = set()
        current = key
        while True:
            entry = next(
                (index[candidate] for candidate in candidate_keys(current) if candidate in index),
                None,
            )
            if entry is None:
                break
            matched_key, value = entry
            marker = canonical(matched_key)
            if marker in safe:
                break
            if marker in on_path:
                loop = path[markers.index(marker) :]
                # Rotated to start at the folded-smallest member so one loop reads the same way whichever key led into it; the rotation is chosen on the folded form and applied to the written one.
                pivot = min(range(len(loop)), key=lambda position: canonical(loop[position]))
                cycles.append(tuple(loop[pivot:] + loop[:pivot]))
                break
            on_path.add(marker)
            markers.append(marker)
            path.append(matched_key)
            _, model, qualified = split_provider_qualifier(value, provider_names)
            if qualified:
                break
            current = model
        safe |= on_path

    return tuple(cycles)


def resolve_against_catalog(
    requested: str,
    target: str,
    *,
    available: frozenset[str],
    matched_key: str = "",
    hops: int = 0,
) -> ModelResolution:
    """Turn the chain's end into a name this provider's catalog actually offers.

    `passthrough` keeps returning the **original request**, not the chain's end, which is the behaviour this module has always had.

    That is not the cosmetic choice an earlier draft of this comment claimed. `decide_route` calls `describe()` on whatever comes back, so when the original name is itself in this provider's catalog — a mapping whose target went missing, say `real-model: gone` where `real-model` is real — `passthrough=True` and a live descriptor hold **at once**, and the request goes upstream under the original name. Abandoning a broken mapping and falling back to what the client actually asked for is the intended behaviour, and is what the older comment meant by "the spec says pass through".

    Kept unchanged because it has nothing to do with providers: altering it would take requests that single-provider deployments serve today and start refusing them. `UnknownModel` carries the chain's end separately, for the other half of passthrough — where the original name is unavailable too and the request really does die. Spec §2.4.
    """
    available_index = {canonical(model): model for model in available}
    direct = available_index.get(canonical(target))
    if direct is not None:
        return ModelResolution(requested, direct, matched_key, hops=hops)
    return ModelResolution(requested, requested.strip(), matched_key, passthrough=True, hops=hops)
