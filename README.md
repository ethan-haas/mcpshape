# mcpshape

Will your MCP server's tools actually work when a model calls them?

`mcpshape` lints an MCP server's `tools/list` output against **declared,
versioned, sourced provider compatibility tables** for OpenAI, Anthropic,
and Google Gemini tool-calling. It catches the failure mode where a tool
schema is perfectly valid JSON Schema and still gets silently degraded by
the provider that calls it: a constraint gets dropped, a description gets
truncated, a nested object gets flattened -- nothing errors, and the model
starts calling your tool with arguments you never intended to allow.

It is non-interactive, exits non-zero on findings, and is meant to run as a
CI gate on every commit to your MCP server.

## What this is not

The official [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector)
is an interactive debugging UI: you point it at a running server, drive it
by hand, and read the results yourself, one server at a time. It is the
right tool for exploring a server during development, and mcpshape does not
try to replace it.

`mcpshape` is the other shape: **non-interactive, opinionated, CI-shaped.**
No UI, no server has to be running, no human has to drive it. It reads a
JSON tool manifest, checks it against structural rules and provider tables,
and exits non-zero if anything is wrong -- so it belongs in a GitHub Action,
not in your hands. It also carries the provider-compatibility tables the
Inspector does not: things like "does this provider's function-calling
surface support `oneOf`" or "what's the tool-name length cap for Gemini."
The Inspector was never trying to answer those questions; that gap is what
mcpshape fills.

## The design rule: no natural-language recognition, anywhere

Every check in `mcpshape` is a mechanical, structural fact about JSON Schema:
a regex against a name, a length comparison, a nesting-depth count, a set
membership test against a declared keyword table. `mcpshape` never judges
whether a tool's description "matches" what the tool does, or reads meaning
into free text. That is a semantic judgment, and every prior project in
this family that tried it (a legal-citation grounding checker, a clinical
trial eligibility matcher, a PII redaction guard) died slowly to a finite
recognizer chasing unbounded phrasing. Tool schemas are typed and closed.
Keep the linter that way.

Length caps, nesting-depth caps, and keyword support are **declared,
versioned tables per provider**, each with a cited source. A provider
outside the table -- or, in a future version, a keyword outside a table's
declared vocabulary -- yields an explicit `unknown` verdict. It is never
guessed at and never silently treated as clean.

## Before / after

Before -- a schema that looks fine and passes every JSON Schema validator,
but silently misbehaves once wired to a real provider:

```json
{
  "tools": [
    {
      "name": "Update Inventory Item!",
      "description": "...(2400 characters, truncated by several providers before the model ever sees the constraint that mattered)...",
      "inputSchema": {
        "type": "object",
        "properties": {
          "item_id": { "type": "string" },
          "patch": {
            "type": "object",
            "properties": { "sku": { "type": "string" } }
          }
        },
        "required": ["item_id", "sku"]
      }
    }
  ]
}
```

```console
$ mcpshape tools.json --provider openai
mcpshape: 1 tool(s) checked against [openai] -- 4 finding(s): 4 error, 0 unknown.

tool_name                   rule_id                     json_pointer                            message
--------------------------------------------------------------------------------------------------------------
Update Inventory Item!      name-pattern                /tools/0/name                           tool name does not match OpenAI...'s required pattern '^[a-zA-Z0-9_-]{1,64}$' (table v2024-08-06)
Update Inventory Item!      description-too-long        /tools/0/description                    description is 2400 chars, exceeding OpenAI...'s cap of 1024 (table v2024-08-06)
Update Inventory Item!      required-missing-property   /tools/0/inputSchema/required/1          'sku' is listed in required but absent from properties -- this schema can never be satisfied
Update Inventory Item!      additional-properties-open  /tools/0/inputSchema/properties/patch    object schema does not set 'additionalProperties'...the model may pass arguments this schema never declared
$ echo $?
1
```

After -- fixed, and the CI gate goes green:

```console
$ mcpshape tools.json --provider openai
mcpshape: 1 tool(s) checked against [openai] -- 0 findings, clean.
$ echo $?
0
```

## Install and run

Zero-friction, zero-config, no network, no API key, no server running:

```console
$ pipx run mcpshape tools.json
$ python -m mcpshape tools.json --provider openai
$ mcpshape --provider openai tools.json          # after `pip install mcpshape`
$ cat tools.json | mcpshape --provider anthropic  # reads stdin if no path given
```

`mcpshape` is pure Python, stdlib only -- **zero runtime dependencies.**

## Input format

Any of the three shapes an MCP `tools/list` response can take:

```json
{"tools": [ { "name": "...", "description": "...", "inputSchema": {...} } ]}
```
```json
{"result": {"tools": [ ... ]}}
```
```json
[ { "name": "...", "description": "...", "inputSchema": {...} } ]
```

## Choosing providers

`--provider NAME` may be repeated to check against several providers in one
pass. **If you omit `--provider` entirely, mcpshape checks against all three
known providers** (`openai`, `anthropic`, `google`) -- the useful-with-no-config
default. Pass an explicit `--provider` list to narrow the check to the
provider(s) you actually ship to; that also avoids findings that only
apply to a provider you don't use.

Naming a provider mcpshape doesn't have a table for (e.g. `--provider cohere`)
does **not** silently pass -- it produces an `unknown-provider` finding per
tool, because "we don't know" is never the same thing as "it's fine."

## Try it on the bundled examples

```
python -m mcpshape examples/clean-tools.json     # clean, exit 0
python -m mcpshape examples/broken-tools.json    # 10 findings, exit 1
cat examples/clean-tools.json | python -m mcpshape
```

`broken-tools.json` plants one defect per rule: a tool name with spaces, a
duplicated name, a `required` entry naming a property that does not exist, a
`default` that violates its own schema, a tool with no `inputSchema` at all,
and objects that leave `additionalProperties` unset.

The per-provider tables are the point, so check that they actually differ:

```
python -m mcpshape examples/clean-tools.json --provider anthropic
python -m mcpshape examples/clean-tools.json --provider not-a-real-provider
```

The second reports `unknown-provider` and exits non-zero. Pointing mcpshape at
a provider it does not know must never let CI go green having checked nothing
— "we don't know" is not "it's fine."

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Clean -- zero findings |
| `1` | One or more findings (including `unknown-provider` verdicts) |
| `2` | Malformed input: invalid JSON, not a recognized tools/list shape, or a tool missing `name` |

## `--json` mode

```console
$ mcpshape tools.json --provider openai --json
{
  "tool_count": 1,
  "providers": ["openai"],
  "finding_count": 1,
  "findings": [
    {
      "rule_id": "name-pattern",
      "severity": "error",
      "tool_name": "Update Inventory Item!",
      "json_pointer": "/tools/0/name",
      "provider": "openai",
      "evidence": {"pattern": "^[a-zA-Z0-9_-]{1,64}$"},
      "message": "tool name does not match OpenAI...'s required pattern ... (table v2024-08-06)"
    }
  ]
}
```

Output is deterministic: findings are sorted by `(tool_index, json_pointer,
rule_id)`, and stdout is byte-identical across repeated runs regardless of
`PYTHONHASHSEED` (verified in CI across 3+ subprocesses with differing hash
seeds -- see `tests/test_determinism.py`).

## The 9 rules

| rule_id | Provider-dependent? | Catches |
|---|---|---|
| `unsupported-keyword` | yes | JSON Schema keyword the provider is documented to ignore/reject |
| `nesting-too-deep` | yes | schema nests deeper than the provider is documented to handle |
| `name-pattern` | yes | tool name violates the provider's name regex or length cap |
| `description-too-long` | yes | description exceeds the provider's length cap |
| `additional-properties-open` | yes | object schema omits `additionalProperties` where the provider defaults it open |
| `required-missing-property` | no | `required` names a property absent from `properties` -- unsatisfiable by construction |
| `duplicate-tool-name` | no | two tools in one server share a name; one silently shadows the other |
| `empty-enum-or-bad-default` | no | empty `enum`, or a `default` that violates its own local schema |
| `missing-input-schema` | no | `inputSchema` absent, or its `type` isn't `"object"` |
| `unknown-provider` (fail-safe verdict, not one of the 9) | -- | provider named isn't in mcpshape's table; never silently "clean" |

Every finding is `{rule_id, severity, tool_name, json_pointer, provider, evidence, message}`.
`json_pointer` is an [RFC 6901](https://www.rfc-editor.org/rfc/rfc6901) pointer
that is guaranteed to resolve inside the document you supplied -- the test
suite asserts this for every planted defect, not just the happy path.

## Provider tables: sources and versions

| Provider | Table version | Source |
|---|---|---|
| `openai` | `2024-08-06` | https://platform.openai.com/docs/guides/function-calling , https://platform.openai.com/docs/guides/structured-outputs |
| `anthropic` | `2024-10-22` | https://docs.anthropic.com/en/docs/build-with-claude/tool-use/overview |
| `google` | `2024-09-01` | https://ai.google.dev/gemini-api/docs/function-calling |

These are frozen, vendored snapshots (see `mcpshape/providers.py`) -- mcpshape
never fetches them at runtime (offline guardrail). If a provider changes its
documented limits, the table needs a commit bumping `version`, same as
updating any pinned dependency.

## Known limitations / bounded coverage

`mcpshape` is deliberately bounded: every check is a declared, versioned,
mechanical fact, and anything outside that declared surface is left alone
rather than guessed at. An independent adversarial review found **zero false positives and zero
crashes** across its corpus; the findings below are the fail-safe *false
negatives* that review documented --
things mcpshape will not flag, by design, not bugs it happens to have. They
are listed here so you know exactly where the tool's edges are, not as an
apology for them.

- **Rule 8 (`empty-enum-or-bad-default`) is a bounded subset of JSON
  Schema default validation.** It checks `type`, `enum` membership,
  `pattern`, string length (`minLength`/`maxLength`), and numeric bounds
  (`minimum`/`maximum`/`exclusiveMinimum`/`exclusiveMaximum`), plus array
  item-count bounds (`minItems`/`maxItems`). It does **not** currently
  validate: `const`, `multipleOf`, recursion into a default *object*'s
  nested `properties`/`required`, or bool-vs-int enum identity (a
  `default: true` checked against `enum: [1]` is not flagged, because
  Python's `True == 1`). A default that violates only one of those
  unchecked keywords passes silently.
- **Rule 5 (`required-missing-property`)** only inspects `required` when
  it is a JSON array of strings, per spec. A malformed non-array
  `required` (e.g. a string or object) is left to other tooling -- it is
  not itself a signal this rule interprets.
- **A tool `description` that is present but not a string is accepted.**
  Only string length is checked (rule `description-too-long`); the 9
  rules do not include a description-*type* rule, so a non-string
  `description` value passes through unflagged.
- **Input deeper than the running interpreter's JSON decoder can parse is
  reported as malformed (exit 2), not linted.** CPython 3.11 and earlier
  exhaust the C stack decoding a document thousands of levels deep; 3.12
  raised that ceiling. mcpshape's own schema walk is iterative and cannot
  recurse, but a document that deep never reaches the walk -- `json.loads`
  fails first. Rather than leak a `RecursionError` traceback, it is caught
  and reported as malformed input. So the same pathological document can
  yield a `nesting-too-deep` finding on 3.12+ and a clean exit 2 on 3.9;
  both are correct, and neither is a crash.
- **Provider tables model the non-strict function-calling schema
  surface** (an object schema with `additionalProperties` unset is
  treated as open, matching default OpenAI/Anthropic/Google tool-calling
  behavior). OpenAI's **strict Structured Outputs** mode (`strict: true`)
  is materially more restrictive -- for example it requires
  `additionalProperties: false` on every object and rejects some
  composition keywords this table treats as allowed for the non-strict
  surface. If you lint schemas destined for strict Structured Outputs,
  treat an mcpshape "clean" verdict as **necessary, not sufficient**, for
  that stricter mode. This is a scope statement, not a defect -- the
  provider table is not changed to chase it.

## Out of scope

- **No natural-language / semantic judgment**, ever -- not for descriptions,
  not for "does this tool do what its name says."
- **No network calls, no API keys, no provider SDKs, no model calls**, in
  the linter or its test suite. Fully offline.
- **No live capture is required to use this tool, and none ships in this
  version.** A `tools/list` JSON file or stdin is enough -- get it from
  your server's own logs, a manual MCP Inspector session, or any
  stdio/HTTP capture you already have. mcpshape deliberately does not open
  a socket or spawn a subprocess to talk to a live server in this release,
  which keeps the "offline, no network in any code path" guarantee trivial
  to audit.
- Not a JSON Schema validator for your general API -- it only checks the
  provider-compatibility axis of an MCP tool's `inputSchema`.

## GitHub Action example

```yaml
name: mcpshape
on: [pull_request]
jobs:
  lint-mcp-tools:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pipx run mcpshape tools.json --provider openai --provider anthropic --provider google
```

## Development

```console
$ pip install -e ".[dev]"
$ python -m pytest -q
```

Test suite covers: every rule against a planted-defect corpus with a
resolving JSON Pointer (`tests/test_planted.py`), a two-sided false-flag
control on a realistic clean corpus (`tests/test_two_sided.py`), a
per-provider over-rejection control (`tests/test_per_provider.py`), table
sourcing plus the unknown-provider fail-safe (`tests/test_tables.py`),
cross-process determinism (`tests/test_determinism.py`), exit codes
(`tests/test_exit_codes.py`), and a positive control proving a silenced
rule is actually detectable as a regression (`tests/test_positive_control.py`).

## License

MIT
