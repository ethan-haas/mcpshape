"""Acceptance gate 4: provider tables are testable, sourced, and fail-safe.

Every table carries a version and a cited source. A provider key not in
the table must yield `unknown`, never silently "clean" -- the fail-unsafe
direction this design exists to avoid.
"""
from __future__ import annotations

from mcpshape import fixtures, providers, rules


def test_every_provider_table_has_a_version_and_source():
    assert len(providers.PROVIDERS) >= 3, "spec requires at least 3 real providers"
    for key, table in providers.PROVIDERS.items():
        assert table.version, f"{key} table missing a version string"
        assert table.source, f"{key} table missing a cited source"
        assert table.source.startswith("http"), f"{key} table source should cite a URL: {table.source!r}"


def test_unknown_provider_yields_unknown_not_clean():
    manifest = fixtures.valid_manifest()  # a manifest that is clean for KNOWN providers
    assert not providers.is_known("some-made-up-provider-xyz")

    tables = {"some-made-up-provider-xyz": providers.get("some-made-up-provider-xyz")}
    findings = rules.lint(manifest["tools"], "/tools", tables)

    assert findings, "an unknown provider must not be silently treated as clean"
    assert all(f["severity"] == "unknown" for f in findings)
    assert all(f["rule_id"] == rules.RULE_UNKNOWN_PROVIDER for f in findings)
    assert len(findings) == len(manifest["tools"]), "expect one unknown-provider finding per tool"


def test_known_providers_are_named_in_spec():
    for expected in ("openai", "anthropic", "google"):
        assert expected in providers.PROVIDERS
