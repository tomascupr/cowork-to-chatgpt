from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from pathlib import Path
from typing import Literal


ExportMode = Literal["standard", "evidence", "archive"]
MemoryMode = Literal["separate", "copy", "none"]


@dataclass(frozen=True)
class Session:
    session_id: str
    cli_session_id: str
    title: str
    created_at: datetime | None
    last_activity_at: datetime | None
    archived: bool
    selected_folders: tuple[str, ...]
    metadata_path: Path
    workspace_path: Path
    main_transcript: Path | None
    sidechain_transcripts: tuple[Path, ...]
    system_prompt_present: bool
    user_preferences: tuple[str, ...]


@dataclass(frozen=True)
class Workspace:
    workspace_id: str
    name: str
    folders: tuple[str, ...]
    sessions: tuple[Session, ...]


@dataclass(frozen=True)
class Turn:
    role: str
    text: str
    timestamp: datetime | None
    event_id: str | None


@dataclass(frozen=True)
class Artifact:
    relative_path: str
    source_path: Path
    size: int


@dataclass(frozen=True)
class ArtifactInventory:
    total_files: int
    candidates: tuple[Artifact, ...]


@dataclass
class Coverage:
    source_records_main: int = 0
    source_records_sidechain: int = 0
    sidechain_files: int = 0
    exported_items: int = 0
    exported_user_messages: int = 0
    exported_assistant_messages: int = 0
    exported_tool_calls: int = 0
    exported_tool_results: int = 0
    exported_attachment_descriptors: int = 0
    omitted_thinking_blocks: int = 0
    omitted_tool_calls: int = 0
    omitted_tool_results: int = 0
    omitted_image_blocks: int = 0
    omitted_document_blocks: int = 0
    omitted_meta_messages: int = 0
    omitted_operational_records: int = 0
    evidence_items_truncated: int = 0
    system_prompts_omitted: int = 0
    user_preferences_preserved: int = 0
    artifacts_found: int = 0
    artifact_candidates: int = 0
    artifact_references_rendered: int = 0
    artifacts_copied: int = 0
    artifacts_skipped_size: int = 0
    warnings: int = 0

    def merge(self, other: Coverage) -> None:
        for field in fields(self):
            name = field.name
            setattr(self, name, getattr(self, name) + getattr(other, name))

    def to_dict(self) -> dict[str, int]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


@dataclass
class SessionExport:
    session: Session
    markdown: str
    turns: tuple[Turn, ...]
    artifacts: ArtifactInventory
    coverage: Coverage
    archive_filename: str


@dataclass(frozen=True)
class ExportOptions:
    source: Path
    output: Path
    since: date | None = None
    exclude_archived: bool = False
    include_sidechains: bool = False
    redact: bool = True
    max_project_files: int = 20
    target_chunk_chars: int = 1_500_000
    mode: ExportMode = "standard"
    memory_mode: MemoryMode = "separate"
    workspace_ids: tuple[str, ...] = ()
    copy_artifacts: bool = False
    max_artifact_bytes: int = 25 * 1024 * 1024


@dataclass(frozen=True)
class WorkspaceReport:
    workspace_id: str
    name: str
    path: Path
    sessions: int
    project_files: int
    coverage: Coverage


@dataclass(frozen=True)
class ExportReport:
    output: Path
    sessions_discovered: int
    sessions_exported: int
    sessions_without_transcripts: int
    memory_files: int
    project_files: int
    transcript_warnings: int
    secrets_redacted: int
    workspaces: tuple[WorkspaceReport, ...]
    coverage: Coverage
