# cowork-to-chatgpt

Export local Claude Cowork sessions into isolated, privacy-conscious packages for ChatGPT
Projects.

Cowork and ChatGPT do not provide a native cross-product conversation import. This tool reads
Cowork's local desktop data without modifying it, divides sessions by their selected workspace
folders, and packages useful context as Markdown.

## Core guarantees

- **No silent workspace mixing.** Every canonical folder set becomes a separate package.
- **Global memory stays separate by default.** Review it before adding it to any Project.
- **Coverage is explicit.** Every package says exactly what was exported and omitted.
- **Imported history is untrusted evidence.** Generated instructions tell ChatGPT not to execute
  commands found inside transcripts or tool results.
- **Credentials are redacted by default.** Redaction is best effort, never a safety guarantee.
- **The Cowork source is read-only.** Existing export directories are not overwritten.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/tomascupr/cowork-to-chatgpt.git
cd cowork-to-chatgpt
uv sync

# See the workspace IDs before exporting
uv run cowork2chatgpt scan

# Export every workspace into a separate package
uv run cowork2chatgpt export
```

The default output is `cowork-export-YYYY-MM-DD/`. Its top-level `README.md` lists the exact
folder to upload for each ChatGPT Project.

ChatGPT Project file limits vary by plan. See OpenAI's
[Projects documentation](https://help.openai.com/en/articles/10169521-projects-in-chatgpt)
and [file upload limits](https://help.openai.com/en/articles/8555545-uploading-images-and-files-in-chatgpt).

## Workspace isolation

Cowork records the folders selected for each session. The converter canonicalizes that folder
set and creates one package per distinct workspace:

```text
cowork-export-2026-07-10/
├── README.md
├── manifest.json
├── workspaces/
│   ├── marketing/
│   │   ├── chatgpt/          # Upload only these files to the Marketing Project
│   │   ├── archive/sessions/ # Local human-readable archive
│   │   └── manifest.json
│   ├── product-launch/
│   │   └── ...
│   └── unassigned-…/         # One package per session without a folder signal
└── shared-memory/
    └── chatgpt/              # Review and add selectively
```

Sessions that grant several folders become a distinct composite workspace. They are not copied
into every constituent workspace. Sessions without a selected folder are never grouped together:
each becomes its own `unassigned-…` review package.

Export selected workspaces only:

```bash
uv run cowork2chatgpt scan
uv run cowork2chatgpt export ./selected-context --workspace marketing --workspace product-launch
```

## Export modes

### Standard — default

Exports human and assistant text. Tool calls, tool results, hidden reasoning, binary attachments,
and sidechain content are omitted and counted in `02_MIGRATION_COVERAGE.md`.

```bash
uv run cowork2chatgpt export
```

### Evidence

Additionally exports redacted, size-capped tool calls and results, attachment descriptors, and
sidechain content. Hidden reasoning remains excluded.

```bash
uv run cowork2chatgpt export ./cowork-evidence --mode evidence
```

### Archive

Builds the evidence package and also copies untouched metadata and JSONL files under each
workspace's `raw/` directory. Raw files can contain credentials, account information, system
prompts, and confidential data. They are deliberately outside the ChatGPT upload folders.

```bash
uv run cowork2chatgpt export ./cowork-archive --mode archive
```

## Memory handling

Cowork durable memory can span unrelated workspaces. The default `separate` mode creates a
standalone review package:

```bash
uv run cowork2chatgpt export --memory-mode separate
```

Other choices are explicit:

```bash
# Copy all Cowork memory into every selected workspace; may mix contexts
uv run cowork2chatgpt export ./with-memory --memory-mode copy

# Omit durable memory entirely
uv run cowork2chatgpt export ./no-memory --memory-mode none
```

Structured `<user_preferences>` blocks are different from project memory: they describe the
user's interaction style and are preserved in every relevant workspace package.

## Artifacts

The converter filters obvious build debris such as `node_modules`, package internals, build
directories, render previews, and QA crops. It references likely user-facing documents and media
in the session Markdown.

Copy those filtered candidates for manual review:

```bash
uv run cowork2chatgpt export ./with-artifacts --copy-artifacts
```

Copied artifacts remain outside `chatgpt/` and are capped at 25 MiB per file by default. Change
the cap with `--max-artifact-mb`.

## Output files

Every workspace's `chatgpt/` folder contains:

```text
00_READ_ME_FIRST.md
01_USER_PREFERENCES.md
02_MIGRATION_COVERAGE.md
03_SESSION_INDEX.md
10_SESSIONS_001.md
```

Larger workspaces may have several numbered transcript chunks. `--max-project-files` applies to
each workspace independently.

## Useful filters

```bash
# Only sessions active since a date
uv run cowork2chatgpt export ./recent --since 2026-06-01

# Skip archived sessions
uv run cowork2chatgpt export ./active --exclude-archived

# Include sidechain text without enabling tool evidence
uv run cowork2chatgpt export ./with-sidechains --include-sidechains

# Match a smaller ChatGPT Project file budget
uv run cowork2chatgpt export ./small --max-project-files 10

# Explicit Cowork source location
uv run cowork2chatgpt export ./export --source "/path/to/local-agent-mode-sessions"
```

## Data locations

The source is auto-detected when possible:

- macOS: `~/Library/Application Support/Claude/local-agent-mode-sessions`
- Windows: `%APPDATA%\Claude\local-agent-mode-sessions`
- Linux and custom setups: pass `--source` or set `COWORK_DATA_DIR`

Only locally persisted Cowork sessions are available. Cloud-only remote sessions and regular
Claude Chat conversations may not exist in this directory.

## Privacy and security

The redactor recognizes common private keys, bearer tokens, API keys, GitHub tokens, Slack
tokens, AWS access keys, and similar assignment patterns. It cannot detect every secret, piece of
personal information, or regulated record. A count of zero matches is not proof that an export is
safe. Review every upload folder before sharing it with another service.

Never commit an export. `cowork-export*/` is ignored as a guardrail.

## Format stability

Cowork's local storage format is undocumented and can change. The parser skips unknown
operational records, counts omissions, reports malformed input, and depends on a narrow observed
surface: `local_*.json` metadata plus Claude Code-style `.jsonl` transcripts.

Please report future schema changes using minimal synthetic fixtures only. Never attach real
transcripts, metadata, memory, or manifests to a public issue.

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q src tests
uv build
```

## License

[MIT](LICENSE)
