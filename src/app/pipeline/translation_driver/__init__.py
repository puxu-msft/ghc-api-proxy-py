"""Translation driver: inbound format <-> intermediate <-> upstream format.

Deliberately empty. `D-ARCH = B` puts the typed kernel at the centre and the wire shapes at the
codec boundary, and a package init that imports every codec makes that unverifiable: importing
`content` — the kernel — used to pull in both protocols and, through one of them, the existing
chain's thinking helpers.

Import the module you mean: `.content` for the block model, `.semantic` for the request, one of
`.anthropic_messages` / `.openai_responses` for a codec, `.registry` for the registry and
`default_registry`.
"""
