# cowork-to-chatgpt

Export local Claude Cowork sessions and durable memory into a compact, privacy-conscious
folder for a ChatGPT Project.

Cowork and ChatGPT do not currently provide a native cross-product conversation import.
This tool reads Cowork's local desktop data without modifying it, keeps the useful
human/assistant context, and packages it as Markdown that ChatGPT can retrieve well.

## What it exports

- Human and assistant messages from local Cowork transcripts
- Cowork's durable memory files under `spaces/*/memory`
- Session titles, timestamps, archive state, and working-folder references
- Names of generated artifacts, without copying the artifact contents
- A compact upload folder capped to a configurable number of files
- A per-session Markdown archive and a machine-readable manifest

It deliberately omits system prompts, account details, tool configuration, hidden reasoning,
tool calls, and raw tool results. Best-effort credential redaction is enabled by default.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/tomascupr/cowork-to-chatgpt.git
cd cowork-to-chatgpt
uv sync
uv run cowork2chatgpt scan
uv run cowork2chatgpt export ./cowork-export
```

Then create a ChatGPT Project and add every file from:

```text
cowork-export/chatgpt/
```

The generated `00_READ_ME_FIRST.md` contains a suggested Project instruction. ChatGPT
Projects support reference files and project-specific instructions; current limits vary by
plan. See OpenAI's [Projects documentation](https://help.openai.com/en/articles/10169521-projects-in-chatgpt)
and [file upload limits](https://help.openai.com/en/articles/8555545-uploading-images-and-files-in-chatgpt).

## Commands

### Inspect before exporting

`scan` only reads session metadata and reports counts. It does not read transcript contents.

```bash
uv run cowork2chatgpt scan
uv run cowork2chatgpt scan --json --limit 50
```

### Export

```bash
uv run cowork2chatgpt export ./cowork-export
```

Useful options:

```bash
# Only recent sessions
uv run cowork2chatgpt export ./recent --since 2026-06-01

# Skip archived sessions
uv run cowork2chatgpt export ./active --exclude-archived

# Include subagent sidechains; this can be much larger
uv run cowork2chatgpt export ./deep --include-sidechains

# Match your ChatGPT plan's project file budget
uv run cowork2chatgpt export ./small --max-project-files 10

# Explicit source directory
uv run cowork2chatgpt export ./export --source "/path/to/local-agent-mode-sessions"
```

Use `--no-redact` only if you understand that raw transcripts may contain credentials.

## Output

```text
cowork-export/
├── chatgpt/
│   ├── 00_READ_ME_FIRST.md
│   ├── 01_COWORK_MEMORY.md
│   ├── 02_SESSION_INDEX.md
│   └── 10_SESSIONS_001.md
├── archive/
│   └── sessions/
│       └── 2026-07-09-example-session-ab12cd34.md
└── manifest.json
```

Upload only `chatgpt/`. The archive is for local browsing and traceability.

## Data locations

The source is auto-detected when possible:

- macOS: `~/Library/Application Support/Claude/local-agent-mode-sessions`
- Windows: `%APPDATA%\Claude\local-agent-mode-sessions`
- Linux and custom setups: pass `--source` or set `COWORK_DATA_DIR`

Only locally persisted Cowork sessions are available. Cloud-only remote sessions and regular
Claude Chat conversations may not exist in this directory.

## Privacy and safety

The source data is read-only and the exporter refuses to overwrite an existing output
directory. Redaction covers common API key, access token, bearer token, and private-key
patterns, but it cannot detect every secret or piece of personal information. Review the
generated files before uploading them or sharing them.

Never commit an export to this repository. `cowork-export/` is ignored as a guardrail.

## Format stability

Cowork's local storage format is undocumented and can change. The parser skips malformed or
unknown records, reports warnings in `manifest.json`, and only depends on a small stable-looking
surface: `local_*.json` metadata plus Claude Code-style `.jsonl` transcripts. Please open an
issue with a fully anonymized fixture if a future Cowork release breaks discovery.

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q src tests
```

## License

[MIT](LICENSE)
