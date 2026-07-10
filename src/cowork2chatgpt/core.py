"""Public compatibility surface for the exporter modules."""

from .discovery import (
    CoworkExportError,
    default_source_candidates,
    discover_memory_files,
    discover_sessions,
    discover_workspace_memory_files,
    group_sessions,
    normalize_home,
    parse_timestamp,
    resolve_source,
)
from .exporter import (
    MAX_PROJECT_TEXT_CHARS,
    export_package,
    format_datetime,
    install_workspaces,
    pack_documents,
)
from .models import (
    Coverage,
    ExportOptions,
    ExportReport,
    InstallOptions,
    InstallReport,
    Session,
    SkippedWorkspace,
    Turn,
    Workspace,
    WorkspaceReport,
)
from .transcript import Redactor, parse_session

DEFAULT_TARGET_CHARS = 1_500_000

__all__ = [
    "Coverage",
    "CoworkExportError",
    "DEFAULT_TARGET_CHARS",
    "ExportOptions",
    "ExportReport",
    "InstallOptions",
    "InstallReport",
    "MAX_PROJECT_TEXT_CHARS",
    "Redactor",
    "Session",
    "SkippedWorkspace",
    "Turn",
    "Workspace",
    "WorkspaceReport",
    "default_source_candidates",
    "discover_memory_files",
    "discover_sessions",
    "discover_workspace_memory_files",
    "export_package",
    "format_datetime",
    "group_sessions",
    "install_workspaces",
    "normalize_home",
    "pack_documents",
    "parse_session",
    "parse_timestamp",
    "resolve_source",
]
