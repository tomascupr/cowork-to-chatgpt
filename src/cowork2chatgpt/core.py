"""Public compatibility surface for the exporter modules."""

from .discovery import (
    CoworkExportError,
    default_source_candidates,
    discover_memory_files,
    discover_sessions,
    group_sessions,
    inspect_artifacts,
    list_artifacts,
    normalize_home,
    parse_timestamp,
    resolve_source,
)
from .exporter import (
    MAX_PROJECT_TEXT_CHARS,
    export_package,
    format_datetime,
    pack_documents,
)
from .models import (
    Artifact,
    ArtifactInventory,
    Coverage,
    ExportOptions,
    ExportReport,
    Session,
    Turn,
    Workspace,
    WorkspaceReport,
)
from .transcript import Redactor, parse_session

DEFAULT_TARGET_CHARS = 1_500_000

__all__ = [
    "Artifact",
    "ArtifactInventory",
    "Coverage",
    "CoworkExportError",
    "DEFAULT_TARGET_CHARS",
    "ExportOptions",
    "ExportReport",
    "MAX_PROJECT_TEXT_CHARS",
    "Redactor",
    "Session",
    "Turn",
    "Workspace",
    "WorkspaceReport",
    "default_source_candidates",
    "discover_memory_files",
    "discover_sessions",
    "export_package",
    "format_datetime",
    "group_sessions",
    "inspect_artifacts",
    "list_artifacts",
    "normalize_home",
    "pack_documents",
    "parse_session",
    "parse_timestamp",
    "resolve_source",
]
