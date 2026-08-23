"""Wire-format conversions that are not the pipeline's translators.

Deliberately empty of re-exports. Until 2026-08-23 this module's entire content was `from app.protocols.gemini import parse_model_with_method` — a public name for a function nothing called, on a module whose chain had already gone to `src/.archived/`. The two modules still here, `anthropic_responses` and `responses_anthropic`, are imported by their consumers directly, which is what makes it possible to see who uses them.
"""
