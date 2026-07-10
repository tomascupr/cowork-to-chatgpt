# Changelog

## 0.3.0 — 2026-07-10

- Replace nested migration packages with one ready-to-open folder per workspace.
- Export the portable `AGENTS.md`, `MEMORY.md`, `HISTORY_INDEX.md`, and `HISTORY*.md` format.
- Use each workspace's existing `CLAUDE.md` and `memory/**/*.md` as its primary durable memory.
- Keep hidden cross-workspace Cowork memory quarantined for selective review.
- Reduce the CLI to workspace selection, date/archive filters, optional evidence, and shared-memory
  exclusion.
- Remove raw archive and artifact-copy modes from the transfer workflow.

## 0.2.0 — 2026-07-10

- Divide exports into isolated packages based on canonical Cowork folder sets.
- Keep sessions without a folder signal isolated one-by-one.
- Keep durable Cowork memory separate by default.
- Preserve structured user preferences without copying Cowork runtime prompts.
- Add standard, evidence, and local raw-archive modes.
- Add per-workspace migration coverage reports and top-level coverage metrics.
- Filter build debris from artifact candidates and support opt-in artifact copying.
- Add explicit prompt-injection boundaries to generated ChatGPT Project instructions.
- Add workspace selection and a default dated output directory.

## 0.1.0 — 2026-07-10

- Initial read-only Cowork transcript and memory exporter.
