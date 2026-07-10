# Security policy

## Sensitive data

Cowork transcripts can contain credentials, personal information, customer data, and other
confidential material. The built-in redactor is best effort, not a guarantee. Review generated
files before uploading, publishing, sharing, or committing them.

`export` is read-only and creates a separate portable package. `install` updates a managed block
in `AGENTS.md` and writes `COWORK_HISTORY_INDEX.md` and `COWORK_HISTORY*.md` in original
single-folder workspaces. Oversized imported guidance uses `COWORK_INSTRUCTIONS.md`. It preserves
pre-existing instructions, refuses to replace unrelated files, and migrates only files carrying
exporter-owned markers or headers. All other workspace files remain untouched.

The tool never writes to `~/.codex/memories/`. OpenAI documents that directory as generated local
state rather than a manual import surface.

The exporter never copies raw metadata or JSONL transcripts. Standard mode excludes system
prompts, hidden reasoning, tool calls, and tool results. `--with-evidence` adds redacted,
size-capped tool evidence and subagent history, which can still contain confidential material or
credentials that the redactor does not recognize.

Workspace memory is read from `CLAUDE.md`, root memory/context files, and `memory/**/*.md` under
the selected working folders. Hidden cross-workspace Cowork memory is exported separately and
must not be added wholesale to unrelated projects.

Do not attach real Cowork metadata, transcripts, memory, manifests, or exports to public bug
reports. Reproduce parser problems with a minimal synthetic fixture.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for issues that could expose source data or bypass
redaction. For non-sensitive defects, open a normal GitHub issue using anonymized inputs.
