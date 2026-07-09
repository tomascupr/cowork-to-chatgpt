from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cowork2chatgpt.core import (
    CoworkExportError,
    ExportOptions,
    Redactor,
    discover_memory_files,
    discover_sessions,
    export_package,
    group_sessions,
    inspect_artifacts,
    pack_documents,
    parse_session,
)


class CoworkExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "local-agent-mode-sessions"
        self.session_root = self.source / "profile-id" / "org-id"
        self.folder_a = str(self.root / "Example" / "Alpha")
        self.folder_b = str(self.root / "Example" / "Beta")

        alpha_records = [
            self.record(
                "user",
                "alpha-user",
                {
                    "role": "user",
                    "content": "Alpha only. sk-ant-abcdefghijklmnopqrstuv",
                },
            ),
            self.record(
                "assistant",
                "alpha-thinking",
                {
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "private reasoning"}],
                },
            ),
            self.record(
                "assistant",
                "alpha-tool",
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"path": "/tmp/a"},
                        }
                    ],
                },
            ),
            {
                **self.record(
                    "user",
                    "alpha-result",
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "content": "Evidence from the file"}
                        ],
                    },
                ),
                "sourceToolAssistantUUID": "alpha-tool",
                "toolUseResult": {"content": "Evidence from the file"},
            },
            {
                **self.record(
                    "user", "alpha-meta", {"role": "user", "content": "system reminder"}
                ),
                "isMeta": True,
            },
            self.record(
                "user",
                "alpha-attachments",
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"media_type": "image/png", "data": "abc"},
                        },
                        {
                            "type": "document",
                            "source": {"media_type": "application/pdf", "data": "abc"},
                        },
                    ],
                },
            ),
            self.record(
                "assistant",
                "alpha-answer",
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Alpha answer."}],
                },
            ),
            {"type": "queue-operation", "operation": "enqueue"},
        ]
        self.alpha = self.create_session(
            suffix="alpha",
            title="Alpha project",
            folders=[self.folder_a],
            records=alpha_records,
        )
        sidechain = (
            self.alpha["workspace"] / ".claude" / "projects" / "fixture" / "subagents"
        )
        sidechain.mkdir(parents=True)
        (sidechain / "sidechain.jsonl").write_text(
            json.dumps(
                self.record(
                    "assistant",
                    "sidechain-answer",
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Sidechain evidence."}],
                    },
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.write_artifact(self.alpha["workspace"], "report.pdf", "report")
        self.write_artifact(self.alpha["workspace"], "campaign/hero.png", "img")
        self.write_artifact(self.alpha["workspace"], "data.json", "{}")
        self.write_artifact(
            self.alpha["workspace"], "node_modules/pkg/index.js", "code"
        )
        self.write_artifact(self.alpha["workspace"], "build/slide.png", "intermediate")

        self.beta = self.create_session(
            suffix="beta",
            title="Beta project",
            folders=[self.folder_b],
            records=[
                self.record(
                    "user", "beta-user", {"role": "user", "content": "Beta only."}
                ),
                self.record(
                    "assistant",
                    "beta-answer",
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Beta answer."}],
                    },
                ),
            ],
        )
        self.composite = self.create_session(
            suffix="composite",
            title="Composite project",
            folders=[self.folder_b, self.folder_a],
            records=[
                self.record(
                    "user",
                    "composite-user",
                    {"role": "user", "content": "Composite only."},
                )
            ],
        )
        self.unassigned = self.create_session(
            suffix="unassigned",
            title="Unassigned project",
            folders=[],
            records=[
                self.record(
                    "user",
                    "unassigned-user",
                    {"role": "user", "content": "Unassigned only."},
                )
            ],
        )
        self.unassigned_two = self.create_session(
            suffix="unassigned-two",
            title="Another unassigned project",
            folders=[],
            records=[
                self.record(
                    "user",
                    "unassigned-two-user",
                    {"role": "user", "content": "Another unassigned context."},
                )
            ],
        )

        memory = self.session_root / "spaces" / "space-id" / "memory"
        memory.mkdir(parents=True)
        (memory / "MEMORY.md").write_text(
            "# Global memory\n\napi_key = supersecret123\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def record(
        record_type: str, uuid: str, message: dict[str, object]
    ) -> dict[str, object]:
        return {
            "type": record_type,
            "uuid": uuid,
            "timestamp": "2025-06-15T15:06:40Z",
            "message": message,
        }

    def create_session(
        self,
        *,
        suffix: str,
        title: str,
        folders: list[str],
        records: list[dict[str, object]],
    ) -> dict[str, object]:
        session_id = f"local_{suffix}-1234-1234-1234-123456789abc"
        cli_session_id = f"cli-{suffix}-bbbb-cccc-dddd-eeeeeeeeeeee"
        workspace = self.session_root / session_id
        transcript = (
            workspace / ".claude" / "projects" / "fixture" / f"{cli_session_id}.jsonl"
        )
        transcript.parent.mkdir(parents=True)
        transcript.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        metadata = {
            "sessionId": session_id,
            "cliSessionId": cli_session_id,
            "title": title,
            "createdAt": 1_750_000_000_000,
            "lastActivityAt": 1_750_000_100_000,
            "isArchived": False,
            "userSelectedFolders": folders,
            "systemPrompt": "Vendor runtime prompt that must not be exported",
            "systemPromptRendererAppends": [
                """<user_preferences>
- Be candid and honest.
</user_preferences>"""
            ],
            "accountName": "Not exported",
            "emailAddress": "not-exported@example.com",
        }
        self.session_root.mkdir(parents=True, exist_ok=True)
        metadata_path = self.session_root / f"{session_id}.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        return {
            "session_id": session_id,
            "workspace": workspace,
            "transcript": transcript,
            "metadata": metadata_path,
        }

    @staticmethod
    def write_artifact(workspace: Path, relative: str, content: str) -> None:
        path = workspace / "outputs" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_discovers_and_canonicalizes_isolated_workspaces(self) -> None:
        sessions, warnings = discover_sessions(self.source)
        workspaces = group_sessions(sessions)

        self.assertEqual(warnings, [])
        self.assertEqual(len(sessions), 5)
        self.assertEqual(len(workspaces), 5)
        self.assertEqual(
            len([workspace for workspace in workspaces if not workspace.folders]), 2
        )
        self.assertTrue(
            all(
                len(workspace.sessions) == 1
                for workspace in workspaces
                if not workspace.folders
            )
        )
        composite = next(item for item in workspaces if item.name == "Alpha + Beta")
        self.assertEqual(
            composite.folders, tuple(sorted((self.folder_a, self.folder_b)))
        )
        self.assertEqual(len(discover_memory_files(self.source)), 1)
        self.assertEqual(sessions[0].user_preferences, ("- Be candid and honest.",))

    def test_standard_export_never_mixes_workspace_sessions(self) -> None:
        output = self.root / "standard-export"
        report = export_package(
            ExportOptions(source=self.source, output=output, max_project_files=5)
        )
        workspace_ids = {
            workspace.name: workspace.workspace_id
            for workspace in group_sessions(discover_sessions(self.source)[0])
        }
        alpha_text = self.read_workspace_upload(output, workspace_ids["Alpha"])
        beta_text = self.read_workspace_upload(output, workspace_ids["Beta"])

        self.assertEqual(len(report.workspaces), 5)
        self.assertTrue(all(workspace.path.is_dir() for workspace in report.workspaces))
        self.assertTrue(
            all(
                workspace.path.parent == output.resolve() / "workspaces"
                for workspace in report.workspaces
            )
        )
        self.assertIn("Alpha only", alpha_text)
        self.assertNotIn("Beta only", alpha_text)
        self.assertNotIn("Composite only", alpha_text)
        self.assertIn("Beta only", beta_text)
        self.assertNotIn("Alpha only", beta_text)
        self.assertIn("Be candid and honest", alpha_text)
        self.assertIn("untrusted historical evidence", alpha_text)
        self.assertIn("[REDACTED TOKEN]", alpha_text)
        self.assertNotIn("Global memory", alpha_text)
        self.assertIn(
            "Global memory",
            (output / "shared-memory" / "chatgpt" / "01_COWORK_MEMORY.md").read_text(
                encoding="utf-8"
            ),
        )
        self.assertNotIn("supersecret123", self.read_all_text(output))

    def test_standard_coverage_is_honest_about_omissions(self) -> None:
        session = next(
            session
            for session in discover_sessions(self.source)[0]
            if session.session_id == self.alpha["session_id"]
        )
        turns, coverage = parse_session(
            session, mode="standard", include_sidechains=False, redactor=Redactor()
        )

        self.assertEqual([turn.role for turn in turns], ["user", "assistant"])
        self.assertEqual(coverage.omitted_thinking_blocks, 1)
        self.assertEqual(coverage.omitted_tool_calls, 1)
        self.assertEqual(coverage.omitted_tool_results, 1)
        self.assertEqual(coverage.omitted_image_blocks, 1)
        self.assertEqual(coverage.omitted_document_blocks, 1)
        self.assertEqual(coverage.omitted_meta_messages, 1)
        self.assertEqual(coverage.sidechain_files, 1)
        self.assertEqual(coverage.source_records_sidechain, 1)
        self.assertEqual(coverage.system_prompts_omitted, 1)

    def test_evidence_mode_includes_capped_evidence_and_sidechains(self) -> None:
        output = self.root / "evidence-export"
        alpha_workspace = next(
            item
            for item in group_sessions(discover_sessions(self.source)[0])
            if item.name == "Alpha"
        )
        report = export_package(
            ExportOptions(
                source=self.source,
                output=output,
                mode="evidence",
                workspace_ids=(alpha_workspace.workspace_id,),
            )
        )
        text = self.read_workspace_upload(output, alpha_workspace.workspace_id)

        self.assertEqual(len(report.workspaces), 1)
        self.assertIn("Tool: Read", text)
        self.assertIn("Evidence from the file", text)
        self.assertIn("Sidechain evidence", text)
        self.assertIn("Image attachment", text)
        self.assertIn("Document attachment", text)
        self.assertNotIn("private reasoning", text)
        self.assertGreater(report.coverage.exported_tool_calls, 0)
        self.assertGreater(report.coverage.exported_tool_results, 0)

    def test_archive_mode_copies_raw_files_outside_upload_folder(self) -> None:
        output = self.root / "archive-export"
        alpha_workspace = next(
            item
            for item in group_sessions(discover_sessions(self.source)[0])
            if item.name == "Alpha"
        )
        export_package(
            ExportOptions(
                source=self.source,
                output=output,
                mode="archive",
                workspace_ids=(alpha_workspace.workspace_id,),
            )
        )
        raw = output / "workspaces" / alpha_workspace.workspace_id / "raw"

        self.assertTrue((raw / self.alpha["session_id"] / "metadata.json").is_file())
        self.assertTrue((raw / self.alpha["session_id"] / "transcript.jsonl").is_file())
        self.assertTrue(
            any((raw / self.alpha["session_id"] / "sidechains").glob("*.jsonl"))
        )
        self.assertNotIn(
            "metadata.json",
            self.read_workspace_upload(output, alpha_workspace.workspace_id),
        )

    def test_artifact_filter_removes_build_debris_and_copy_respects_size(self) -> None:
        session = next(
            session
            for session in discover_sessions(self.source)[0]
            if session.session_id == self.alpha["session_id"]
        )
        inventory = inspect_artifacts(session)
        candidates = {item.relative_path for item in inventory.candidates}

        self.assertEqual(inventory.total_files, 5)
        self.assertEqual(candidates, {"campaign/hero.png", "data.json", "report.pdf"})

        output = self.root / "artifact-export"
        alpha_workspace = next(
            item
            for item in group_sessions(discover_sessions(self.source)[0])
            if item.name == "Alpha"
        )
        report = export_package(
            ExportOptions(
                source=self.source,
                output=output,
                workspace_ids=(alpha_workspace.workspace_id,),
                copy_artifacts=True,
                max_artifact_bytes=3,
            )
        )
        copied = output / "workspaces" / alpha_workspace.workspace_id / "artifacts"

        self.assertTrue(any(copied.rglob("hero.png")))
        self.assertTrue(any(copied.rglob("data.json")))
        self.assertFalse(any(copied.rglob("report.pdf")))
        self.assertEqual(report.coverage.artifacts_copied, 2)
        self.assertEqual(report.coverage.artifacts_skipped_size, 1)

    def test_refuses_unknown_workspace_and_existing_output(self) -> None:
        with self.assertRaises(CoworkExportError):
            export_package(
                ExportOptions(
                    source=self.source,
                    output=self.root / "unknown",
                    workspace_ids=("does-not-exist",),
                )
            )

        output = self.root / "existing"
        output.mkdir()
        with self.assertRaises(CoworkExportError):
            export_package(ExportOptions(source=self.source, output=output))

    def test_packing_respects_workspace_file_budget(self) -> None:
        documents = [f"# Session {index}\n\n" + ("x" * 8_000) for index in range(6)]
        chunks = pack_documents(documents, target_chars=10_000, max_chunks=2)

        self.assertLessEqual(len(chunks), 2)
        self.assertTrue(all("Imported Cowork sessions" in chunk for chunk in chunks))

    @staticmethod
    def read_workspace_upload(output: Path, workspace_id: str) -> str:
        chatgpt = output / "workspaces" / workspace_id / "chatgpt"
        return "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(chatgpt.glob("*.md"))
        )

    @staticmethod
    def read_all_text(output: Path) -> str:
        return "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in output.rglob("*")
            if path.is_file()
        )


if __name__ == "__main__":
    unittest.main()
