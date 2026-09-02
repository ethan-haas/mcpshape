"""Declared, versioned, sourced provider-compatibility tables.

THE DESIGN RULE: every value here is a mechanical, structural
fact about how a provider's tool-calling surface parses JSON Schema -- never
a judgement about what a description "means". Each table below cites the
public documentation it was transcribed from, plus a version string, so a
reviewer can check it and a future edit can bump it honestly.

This module is 100% offline: no network call is made to fetch or validate
these values at runtime. They are a frozen snapshot, exactly like a vendored
dependency. If a provider changes its limits, bump `version` and update the
table in a commit -- do not have the linter guess.

Every field a provider-dependent rule needs is declared here. A provider
NOT in `PROVIDERS` is unknown to the linter; provider-dependent rules must
emit a `severity="unknown"` verdict for it, never treat it as clean (see
rules.py: `UNKNOWN_PROVIDER_RULE_ID`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderTable:
    key: str
    display_name: str
    version: str
    source: str
    # Tool-name constraints.
    name_pattern: str
    name_max_len: int
    # Description constraint.
    description_max_len: int
    # How many levels of nested object/array a schema may have before the
    # provider is documented to flatten, reject, or otherwise mishandle it.
    # Depth 1 = a flat object whose properties are all scalars/enums.
    max_nesting_depth: int
    # JSON Schema keywords this provider is documented to ignore, reject, or
    # silently drop when present in a tool's inputSchema.
    unsupported_keywords: frozenset[str]
    # Whether an object schema with `additionalProperties` UNSET is treated
    # by the provider as open (extra args pass through) or closed.
    additional_properties_default: str  # "open" | "closed"

    def compiled_name_pattern(self) -> re.Pattern[str]:
        return re.compile(self.name_pattern)


# JSON Schema keywords this linter is aware of and checks providers against.
# (Not every provider table needs to reference all of these -- only the ones
# it documents as unsupported.)
KNOWN_SCHEMA_KEYWORDS = frozenset(
    {
        "oneOf",
        "allOf",
        "anyOf",
        "not",
        "$ref",
        "patternProperties",
        "if",
        "then",
        "else",
        "propertyNames",
        "contains",
        "const",
        "additionalProperties",
    }
)

PROVIDERS: dict[str, ProviderTable] = {
    "openai": ProviderTable(
        key="openai",
        display_name="OpenAI (function calling / Structured Outputs)",
        version="2024-08-06",
        source="https://platform.openai.com/docs/guides/function-calling ; "
        "https://platform.openai.com/docs/guides/structured-outputs "
        "(function name pattern ^[a-zA-Z0-9_-]+$, max 64 chars; Structured "
        "Outputs schema depth limit of 5 levels of nesting; strict mode "
        "requires additionalProperties:false, so a schema that omits it is "
        "treated as open/non-strict).",
        name_pattern=r"^[a-zA-Z0-9_-]{1,64}$",
        name_max_len=64,
        description_max_len=1024,
        max_nesting_depth=5,
        unsupported_keywords=frozenset(
            {
                "allOf",
                "not",
                "patternProperties",
                "if",
                "then",
                "else",
                "propertyNames",
                "contains",
            }
        ),
        additional_properties_default="open",
    ),
    "anthropic": ProviderTable(
        key="anthropic",
        display_name="Anthropic (Claude tool use)",
        version="2024-10-22",
        source="https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview "
        "(input_schema is standard JSON Schema passed through largely "
        "as-is; tool name pattern ^[a-zA-Z0-9_-]{1,128}$; description and "
        "schema become part of the prompt context, so an unbounded "
        "description is a quality bug even though the API does not reject "
        "it outright -- we apply a generous practitioner cap).",
        name_pattern=r"^[a-zA-Z0-9_-]{1,128}$",
        name_max_len=128,
        description_max_len=8192,
        max_nesting_depth=8,
        unsupported_keywords=frozenset({"if", "then", "else"}),
        additional_properties_default="open",
    ),
    "google": ProviderTable(
        key="google",
        display_name="Google Gemini (function calling)",
        version="2024-09-01",
        source="https://ai.google.dev/gemini-api/docs/function-calling "
        "(schema is a restricted OpenAPI 3.0 Schema subset: the protobuf "
        "Schema message has no oneOf/allOf/anyOf/not, $ref, "
        "patternProperties, or if/then/else field, so the typed SDK cannot "
        "express them and raw-JSON REST callers have them silently "
        "dropped; function name must match "
        r"^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$, i.e. max 64 chars starting with "
        "a letter or underscore. The Schema message also has no "
        "additionalProperties field -- setting it is a harmless no-op "
        "rather than a hard rejection, but the provider can never actually "
        "enforce a closed object, so it is NOT listed as an unsupported "
        "keyword here (setting it doesn't error) even though omitting it "
        "still means the object is open, per additional_properties_default).",
        name_pattern=r"^[a-zA-Z_][a-zA-Z0-9_-]{0,63}$",
        name_max_len=64,
        description_max_len=1024,
        max_nesting_depth=4,
        unsupported_keywords=frozenset(
            {
                "oneOf",
                "allOf",
                "anyOf",
                "not",
                "$ref",
                "patternProperties",
                "if",
                "then",
                "else",
                "propertyNames",
                "contains",
            }
        ),
        additional_properties_default="open",
    ),
}

# The default set of providers the CLI lints against when --provider is not
# given (documented CLI design choice -- see README "Choosing providers").
DEFAULT_PROVIDER_SET: tuple[str, ...] = ("openai", "anthropic", "google")


def get(provider_key: str) -> ProviderTable | None:
    return PROVIDERS.get(provider_key)


def is_known(provider_key: str) -> bool:
    return provider_key in PROVIDERS
