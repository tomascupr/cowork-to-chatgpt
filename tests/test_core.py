from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from cowork2chatgpt.core import (
    CoworkExportError,
    ExportOptions,
    Redactor,
    discover_memory_files,
    discover_sessions,
    export_package,
    pack_documents,
    parse_session,
)


class CoworkExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "local-agent-mode-sessions"
        self.session_root = self.source / "profile-id" / "org-id"
        self.session_id = "local_12345678-1234-1234-1234-123456789abc"
        self.cli_session_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.workspace = self.session_root / self.session_id
        self.transcript = (
            self.workspace
            / ".claude"
            / "projects"
            / "fixture-project"
            / f"{self.cli_session_id}.jsonl"
        )
        self.transcript.parent.mkdir(parents=True)

        metadata = {
            "sessionId": self.session_id,
            "cliSessionId": self.cli_session_id,
            "title": "Fixture migration",
            "createdAt": 1_750_000_000_000,
            "lastActivityAt": 1_750_000_100_000,
            "isArchived": False,
            "userSelectedFolders": [str(self.root / "Example")],
            "accountName": "Not exported",
            "emailAddress": "not-exported@example.com",
            "systemPrompt": "Not exported",
        }
        self.session_root.mkdir(parents=True, exist_ok=True)
        (self.session_root / f"{self.session_id}.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )

        records = [
            {
                "type": "user",
                "uuid": "user-1",
                "timestamp": "2025-06-15T15:06:40Z",
                "message": {
                    "role": "user",
                    "content": "Move this context. Token: sk-ant-abcdefghijklmnopqrstuv",
                },
            },
            {
                "type": "assistant",
                "uuid": "assistant-thinking",
                "timestamp": "2025-06-15T15:06:41Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "private reasoning"}],
                },
            },
            {
                "type": "assistant",
                "uuid": "assistant-tool",
                "timestamp": "2025-06-15T15:06:42Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "name": "Read", "input": {}}],
                },
            },
            {
                "type": "user",
                "uuid": "tool-result",
                "sourceToolAssistantUUID": "assistant-tool",
                "timestamp": "2025-06-15T15:06:43Z",
                "toolUseResult": {"secret": "raw tool output"},
                "message": {
                    "role": "user",
                    "content": [{"type": "tool_result", "content": "raw tool output"}],
                },
            },
            {
                "type": "user",
                "uuid": "meta-user",
                "isMeta": True,
                "timestamp": "2025-06-15T15:06:44Z",
                "message": {"role": "user", "content": "system reminder"},
            },
            {
                "type": "assistant",
                "uuid": "assistant-1",
                "timestamp": "2025-06-15T15:06:45Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "The useful answer."}],
                },
            },
        ]
        self.transcript.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n{malformed}\n",
            encoding="utf-8",
        )

        memory = self.session_root / "spaces" / "space-id" / "memory"
        memory.mkdir(parents=True)
        (memory / "MEMORY.md").write_text(
            "# Working style\n\napi_key = supersecret123\n",
            encoding="utf-8",
        )
        outputs = self.workspace / "outputs"
        outputs.mkdir()
        (outputs / "report.md").write_text("result", encoding="utf-8")
        (outputs / ".hidden").write_text("ignore", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_discovers_session_transcript_and_memory(self) -> None:
        sessions, warnings = discover_sessions(self.source)

        self.assertEqual(warnings, [])
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].title, "Fixture migration")
        self.assertEqual(sessions[0].main_transcript, self.transcript)
        self.assertEqual(len(discover_memory_files(self.source)), 1)

    def test_parser_keeps_conversation_and_omits_internal_events(self) -> None:
        session = discover_sessions(self.source)[0][0]
        redactor = Redactor()

        turns, warnings = parse_session(
            session, include_sidechains=False, redactor=redactor
        )

        self.assertEqual(warnings, 1)
        self.assertEqual([turn.role for turn in turns], ["user", "assistant"])
        combined = "\n".join(turn.text for turn in turns)
        self.assertIn("[REDACTED TOKEN]", combined)
        self.assertNotIn("private reasoning", combined)
        self.assertNotIn("raw tool output", combined)
        self.assertNotIn("system reminder", combined)
        self.assertEqual(redactor.replacements, 1)

    def test_exports_upload_folder_archive_and_manifest(self) -> None:
        output = self.root / "export"
        report = export_package(
            ExportOptions(
                source=self.source,
                output=output,
                since=date(2025, 1, 1),
                max_project_files=4,
                target_chunk_chars=10_000,
            )
        )

        project_files = sorted((output / "chatgpt").glob("*.md"))
        exported_text = "\n".join(
            path.read_text(encoding="utf-8") for path in project_files
        )
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(report.sessions_exported, 1)
        self.assertEqual(report.project_files, 4)
        self.assertEqual(len(project_files), 4)
        self.assertIn("The useful answer.", exported_text)
        self.assertIn("report.md", exported_text)
        self.assertIn("[REDACTED TOKEN]", exported_text)
        self.assertIn("[REDACTED]", exported_text)
        self.assertNotIn("abcdefghijklmnopqrstuv", exported_text)
        self.assertNotIn("supersecret123", exported_text)
        self.assertNotIn("Not exported", exported_text)
        self.assertEqual(manifest["summary"]["sessions"], 1)
        self.assertEqual(len(list((output / "archive" / "sessions").glob("*.md"))), 1)

    def test_refuses_to_overwrite_output(self) -> None:
        output = self.root / "existing"
        output.mkdir()

        with self.assertRaises(CoworkExportError):
            export_package(ExportOptions(source=self.source, output=output))

    def test_packing_respects_project_file_budget(self) -> None:
        documents = [f"# Session {index}\n\n" + ("x" * 8_000) for index in range(6)]

        chunks = pack_documents(documents, target_chars=10_000, max_chunks=2)

        self.assertLessEqual(len(chunks), 2)
        self.assertTrue(all("Imported Cowork sessions" in chunk for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
