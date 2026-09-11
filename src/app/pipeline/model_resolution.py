"""Model name resolution, per the rules in `config.example.yaml`.

`model_mappings` is the sole source; there are no built-in defaults.
Compatibility spellings select mapping keys, while the catalog-aware
`resolve_with_catalogs` function decides which mapping target can actually serve
the request. Unavailable targets may continue through another mapping, but a
request never silently falls back to its original name.

The lower-level discovery helpers below are retained for mapping diagnostics and
route-table explanations. Request routing uses `resolve_with_catalogs`, because
provider selection and catalog availability must be decided together.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

BRACKET_SUFFIX = re.compile(r"^(?P<base>.+)\[(?P<suffix>[^\]]+)\]$")
_MAX_ALIAS_HOPS = 8

# What separates a provider name from the model name in a qualified value or an inbound model name. `/` rather than `@`, which `split_format_suffix` already spends on the wire format, and rather than `:`, which YAML would make an operator quote.
QUALIFIER_SEPARATOR = "/"

# Where the provider serving a request came from. A closed set keeps route
# reports descriptive rather than prose-valued.
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
    default_provider: str = "",
) -> tuple[MappingProblem, ...]:
    """Every problem in `model_mappings` that needs no catalog to find.

    "Needs no catalog" is the whole selection rule, and it is the user's: the two checks that were considered and cut — is the qualified model actually in that provider's catalog, is it disabled there — both depend on a live catalog, so they answer differently at start-up than they will an hour later, and they are served by `/api/status` instead. These three answer the same at any moment. Spec §5.1, §5.1.2.

    Reported, never raised. A deployment with a typo'd qualifier still starts and still serves everything else; the ruling was explicitly against failing start-up over this. Spec §5.1.

    `default_provider` is also the provider that catches an unknown qualifier.
    """
    problems: list[MappingProblem] = []

    for key, value in mappings.items():
        provider, model, qualified = split_provider_qualifier(value, provider_names)
        if qualified and provider is None:
            head = value.partition(QUALIFIER_SEPARATOR)[0]
            configured = ", ".join(sorted(provider_names)) or "none"
            consequence = f"will be served by the default provider {default_provider!r}"
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


@dataclass(frozen=True, slots=True)
class CatalogModelResolution:
    """A mapping result that has already selected a provider and catalog id."""

    requested: str
    provider: str
    resolved: str
    target: str
    matched_key: str = ""
    hops: int = 0
    format_name: str = ""
    origin: ProviderOrigin = "default"


def _split_mapping_format(value: str) -> tuple[str, str]:
    """Remove an optional `@format` suffix from a mapping value."""
    model, separator, format_name = value.rpartition("@")
    if not separator or not model:
        return value, ""
    return model, format_name


def resolve_with_catalogs(
    requested: str,
    *,
    mappings: Mapping[str, str],
    provider_names: frozenset[str],
    available: Mapping[str, frozenset[str]],
    default_provider: str,
) -> CatalogModelResolution | None:
    """Resolve a request by trying every mapping target against provider catalogs.

    A mapping is an alias only until its target is known to be available. Bare
    targets are checked on the provider that qualified the mapping, then on the
    default provider. Qualified targets are checked only on their named provider.
    An unavailable target may itself be another alias, so the walk continues
    until a catalog hit or the hop budget is exhausted.
    """
    index = _index(mappings)
    catalog_indexes = {
        provider: {canonical(model): model for model in model_ids}
        for provider, model_ids in available.items()
    }

    def find_entry(name: str) -> tuple[str, str] | None:
        return next(
            (index[key] for key in candidate_keys(name) if key in index),
            None,
        )

    def unique(names: tuple[str | None, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        result: list[str] = []
        for name in names:
            if name and name not in seen:
                seen.add(name)
                result.append(name)
        return tuple(result)

    def catalog_id(provider: str, model: str) -> str | None:
        return catalog_indexes.get(provider, {}).get(canonical(model))

    def walk(
        current: str,
        *,
        source_provider: str | None,
        source_origin: ProviderOrigin,
        visited: frozenset[str],
        first_key: str,
        hops: int,
        inherited_format: str,
    ) -> CatalogModelResolution | None:
        if hops >= _MAX_ALIAS_HOPS:
            return None

        current_name, current_format = _split_mapping_format(current)
        entry = find_entry(current_name)
        if entry is not None:
            matched_key, value = entry
            marker = canonical(matched_key)
            if marker in visited:
                return None

            target_name, target_format = _split_mapping_format(value)
            format_name = target_format or inherited_format or current_format
            explicit, model, qualified = split_provider_qualifier(
                target_name, provider_names
            )
            if qualified:
                target_provider = explicit or default_provider
                candidates = unique((target_provider,))
                target_origin: ProviderOrigin = (
                    "qualified" if explicit is not None else "fallback"
                )
                next_name = target_name
                next_source = target_provider or None
            else:
                candidates = unique((source_provider, default_provider))
                target_origin = source_origin if source_provider else "default"
                next_name = model
                next_source = source_provider or default_provider

            for provider in candidates:
                resolved = catalog_id(provider, model)
                if resolved is not None:
                    return CatalogModelResolution(
                        requested=requested,
                        provider=provider,
                        resolved=resolved,
                        target=model,
                        matched_key=first_key or matched_key,
                        hops=hops + 1,
                        format_name=format_name,
                        origin=target_origin
                        if provider == next_source
                        else ("default" if provider == default_provider else target_origin),
                    )

            return walk(
                next_name,
                source_provider=next_source,
                source_origin=target_origin,
                visited=visited | {marker},
                first_key=first_key or matched_key,
                hops=hops + 1,
                inherited_format=format_name,
            )

        explicit, model, qualified = split_provider_qualifier(
            current_name, provider_names
        )
        if qualified:
            target_provider = explicit or default_provider
            candidates = unique((target_provider,))
            target_origin: ProviderOrigin = (
                "qualified" if explicit is not None else "fallback"
            )
        else:
            candidates = unique((source_provider, default_provider))
            target_origin = source_origin if source_provider else "default"

        for provider in candidates:
            resolved = catalog_id(provider, model)
            if resolved is not None:
                return CatalogModelResolution(
                    requested=requested,
                    provider=provider,
                    resolved=resolved,
                    target=model,
                    matched_key=first_key,
                    hops=hops,
                    format_name=inherited_format or current_format,
                    origin=target_origin
                    if provider == (explicit or source_provider)
                    else ("default" if provider == default_provider else target_origin),
                )
        return None

    explicit, bare, request_qualified = split_provider_qualifier(
        requested.strip(), provider_names
    )
    request_provider = explicit or default_provider
    request_origin: ProviderOrigin = (
        "qualified" if explicit is not None else "fallback" if request_qualified else "default"
    )

    seeds: list[tuple[str, str | None, ProviderOrigin]] = [
        (requested.strip(), request_provider, request_origin)
    ]
    if request_qualified:
        seeds.append(
            (
                f"{default_provider}{QUALIFIER_SEPARATOR}{bare}",
                default_provider,
                "fallback",
            )
        )
    else:
        seeds.append(
            (
                f"{default_provider}{QUALIFIER_SEPARATOR}{bare}",
                default_provider,
                "default",
            )
        )

    # A lookup fallback is only for a missing mapping key. Once a key exists,
    # its target and any aliases reachable from that target own the request;
    # failing that chain must not silently select another key.
    for seed, source_provider, source_origin in seeds:
        if find_entry(seed) is None:
            continue
        return walk(
            seed,
            source_provider=source_provider,
            source_origin=source_origin,
            visited=frozenset(),
            first_key="",
            hops=0,
            inherited_format="",
        )

    if not request_provider:
        return None
    resolved = catalog_id(request_provider, bare)
    if resolved is None:
        return None
    return CatalogModelResolution(
        requested=requested,
        provider=request_provider,
        resolved=resolved,
        target=bare,
        origin=request_origin,
    )
