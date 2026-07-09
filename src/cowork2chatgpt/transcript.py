from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .discovery import normalize_home, parse_timestamp
from .models import Coverage, ExportMode, Session, Turn


MAX_TOOL_CALL_CHARS = 4_000
MAX_TOOL_RESULT_CHARS = 12_000
MAX_EVIDENCE_CHARS_PER_SESSION = 120_000


class Redactor:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.replacements = 0

    def redact(self, text: str) -> str:
        text = normalize_home(text)
        if not self.enabled:
            return text

        substitutions: tuple[tuple[re.Pattern[str], str], ...] = (
            (
                re.compile(
                    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
                    r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                    re.DOTALL,
                ),
                "[REDACTED PRIVATE KEY]",
            ),
            (
                re.compile(
                    r"\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{16,}"
                    r"|github_pat_[A-Za-z0-9_]{20,}"
                    r"|gh[pousr]_[A-Za-z0-9]{20,}"
                    r"|xox[baprs]-[A-Za-z0-9-]{16,}"
                    r"|AKIA[A-Z0-9]{16}"
                    r"|AIza[A-Za-z0-9_-]{20,})\b"
                ),
                "[REDACTED TOKEN]",
            ),
            (
                re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{12,}=*"),
                "Bearer [REDACTED]",
            ),
        )
        for pattern, replacement in substitutions:
            text, count = pattern.subn(replacement, text)
            self.replacements += count

        assignment = re.compile(
            r"(?im)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)"
            r"\b\s*[:=]\s*[\"']?)([A-Za-z0-9_./+=:-]{8,})([\"']?)"
        )

        def replace_assignment(match: re.Match[str]) -> str:
            self.replacements += 1
            return f"{match.group(1)}[REDACTED]{match.group(3)}"

        return assignment.sub(replace_assignment, text)


@dataclass
class EvidenceBudget:
    used: int = 0

    def fit(self, text: str, per_item_limit: int, coverage: Coverage) -> str | None:
        available = MAX_EVIDENCE_CHARS_PER_SESSION - self.used
        if available <= 0:
            coverage.evidence_items_truncated += 1
            return None
        limit = min(per_item_limit, available)
        if len(text) > limit:
            text = text[: max(0, limit - 32)].rstrip() + "\n[…evidence truncated…]"
            coverage.evidence_items_truncated += 1
        self.used += len(text)
        return text


def parse_session(
    session: Session,
    *,
    mode: ExportMode = "standard",
    include_sidechains: bool = False,
    redactor: Redactor,
) -> tuple[list[Turn], Coverage]:
    coverage = Coverage(
        sidechain_files=len(session.sidechain_transcripts),
        system_prompts_omitted=1 if session.system_prompt_present else 0,
        user_preferences_preserved=len(session.user_preferences),
    )
    if session.main_transcript is None:
        return [], coverage

    include_evidence = mode in {"evidence", "archive"}
    include_sidechain_content = include_sidechains or include_evidence
    paths: list[tuple[Any, bool]] = [(session.main_transcript, False)]
    if include_sidechain_content:
        paths.extend((path, True) for path in session.sidechain_transcripts)
    else:
        for path in session.sidechain_transcripts:
            try:
                coverage.source_records_sidechain += len(
                    path.read_text(encoding="utf-8").splitlines()
                )
            except (OSError, UnicodeDecodeError):
                coverage.warnings += 1

    ordered: list[tuple[datetime, int, int, Turn]] = []
    budget = EvidenceBudget()
    for path_index, (path, is_sidechain) in enumerate(paths):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            coverage.warnings += 1
            continue
        for line_index, line in enumerate(lines):
            if is_sidechain:
                coverage.source_records_sidechain += 1
            else:
                coverage.source_records_main += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                coverage.warnings += 1
                continue
            for turn in turns_from_record(
                record,
                include_evidence=include_evidence,
                redactor=redactor,
                coverage=coverage,
                budget=budget,
            ):
                timestamp = turn.timestamp or datetime.max.replace(tzinfo=UTC)
                ordered.append((timestamp, path_index, line_index, turn))

    if include_sidechain_content:
        ordered.sort(key=lambda item: (item[0], item[1], item[2]))
    else:
        ordered.sort(key=lambda item: (item[1], item[2]))

    seen: set[str] = set()
    turns: list[Turn] = []
    for _, _, _, turn in ordered:
        if turn.event_id and turn.event_id in seen:
            continue
        if turn.event_id:
            seen.add(turn.event_id)
        if turns and turns[-1].role == turn.role and turns[-1].text == turn.text:
            continue
        turns.append(turn)

    coverage.exported_items = len(turns)
    for turn in turns:
        if turn.role == "user":
            coverage.exported_user_messages += 1
        elif turn.role == "assistant":
            coverage.exported_assistant_messages += 1
        elif turn.role == "tool_call":
            coverage.exported_tool_calls += 1
        elif turn.role == "tool_result":
            coverage.exported_tool_results += 1
        elif turn.role == "attachment":
            coverage.exported_attachment_descriptors += 1
    return turns, coverage


def turns_from_record(
    record: Any,
    *,
    include_evidence: bool,
    redactor: Redactor,
    coverage: Coverage,
    budget: EvidenceBudget,
) -> list[Turn]:
    if not isinstance(record, dict):
        coverage.omitted_operational_records += 1
        return []
    record_type = record.get("type")
    if record_type not in {"user", "assistant"}:
        coverage.omitted_operational_records += 1
        return []
    message = record.get("message")
    if not isinstance(message, dict):
        coverage.omitted_operational_records += 1
        return []

    timestamp = parse_timestamp(record.get("timestamp"))
    event_id = str(record.get("uuid")) if record.get("uuid") else None
    content = message.get("content")
    blocks = content if isinstance(content, list) else []

    if record_type == "assistant":
        return assistant_turns(
            content,
            timestamp=timestamp,
            event_id=event_id,
            include_evidence=include_evidence,
            redactor=redactor,
            coverage=coverage,
            budget=budget,
        )

    attachment_blocks = [
        (index, block)
        for index, block in enumerate(blocks)
        if isinstance(block, dict) and block.get("type") in {"image", "document"}
    ]
    for _, block in attachment_blocks:
        if block.get("type") == "image":
            coverage.omitted_image_blocks += 1
        else:
            coverage.omitted_document_blocks += 1
    if record.get("isMeta"):
        coverage.omitted_meta_messages += 1
        return []
    tool_result_blocks = [
        block
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    is_tool_result = bool(tool_result_blocks) or any(
        record.get(key) is not None
        for key in ("toolUseResult", "sourceToolUseID", "sourceToolAssistantUUID")
    )
    if is_tool_result:
        count = max(1, len(tool_result_blocks))
        if not include_evidence:
            coverage.omitted_tool_results += count
            return []
        raw = tool_result_blocks[0].get("content") if tool_result_blocks else None
        if raw in (None, "", []):
            raw = record.get("toolUseResult")
        text = budget.fit(
            redactor.redact(safe_value_text(raw)), MAX_TOOL_RESULT_CHARS, coverage
        )
        if not text:
            coverage.omitted_tool_results += count
            return []
        turns = [
            Turn(
                role="tool_result",
                text=text,
                timestamp=timestamp,
                event_id=f"{event_id}:tool-result" if event_id else None,
            )
        ]
        turns.extend(
            Turn(
                role="attachment",
                text=attachment_descriptor(str(block.get("type")), block),
                timestamp=timestamp,
                event_id=(f"{event_id}:attachment:{index}" if event_id else None),
            )
            for index, block in attachment_blocks
        )
        return turns

    turns: list[Turn] = []
    text_parts: list[str] = []
    if isinstance(content, str):
        text_parts.append(content)
    for block_index, block in enumerate(blocks):
        if isinstance(block, str):
            text_parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text" and isinstance(block.get("text"), str):
            text_parts.append(block["text"])
        elif block_type in {"image", "document"}:
            if include_evidence:
                turns.append(
                    Turn(
                        role="attachment",
                        text=attachment_descriptor(block_type, block),
                        timestamp=timestamp,
                        event_id=(
                            f"{event_id}:{block_type}:{block_index}"
                            if event_id
                            else None
                        ),
                    )
                )
    text = "\n\n".join(part.strip() for part in text_parts if part.strip()).strip()
    if text:
        turns.insert(
            0,
            Turn(
                role="user",
                text=redactor.redact(text),
                timestamp=timestamp,
                event_id=f"{event_id}:text" if event_id else None,
            ),
        )
    return turns


def assistant_turns(
    content: Any,
    *,
    timestamp: datetime | None,
    event_id: str | None,
    include_evidence: bool,
    redactor: Redactor,
    coverage: Coverage,
    budget: EvidenceBudget,
) -> list[Turn]:
    blocks = content if isinstance(content, list) else []
    turns: list[Turn] = []
    if isinstance(content, str) and content.strip():
        turns.append(
            Turn(
                role="assistant",
                text=redactor.redact(content.strip()),
                timestamp=timestamp,
                event_id=f"{event_id}:text" if event_id else None,
            )
        )
        return turns

    for block_index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text" and isinstance(block.get("text"), str):
            text = block["text"].strip()
            if text:
                turns.append(
                    Turn(
                        role="assistant",
                        text=redactor.redact(text),
                        timestamp=timestamp,
                        event_id=(
                            f"{event_id}:text:{block_index}" if event_id else None
                        ),
                    )
                )
        elif block_type == "thinking":
            coverage.omitted_thinking_blocks += 1
        elif block_type == "tool_use":
            if not include_evidence:
                coverage.omitted_tool_calls += 1
                continue
            name = str(block.get("name") or "unknown tool")
            payload = safe_value_text(block.get("input"))
            text = budget.fit(
                redactor.redact(f"Tool: {name}\n\nInput:\n{payload}"),
                MAX_TOOL_CALL_CHARS,
                coverage,
            )
            if not text:
                coverage.omitted_tool_calls += 1
                continue
            turns.append(
                Turn(
                    role="tool_call",
                    text=text,
                    timestamp=timestamp,
                    event_id=(f"{event_id}:tool:{block_index}" if event_id else None),
                )
            )
    return turns


def attachment_descriptor(block_type: str, block: dict[str, Any]) -> str:
    source = block.get("source")
    details: list[str] = []
    if isinstance(source, dict):
        for key in ("media_type", "type", "file_name", "name"):
            value = source.get(key)
            if isinstance(value, str) and value:
                details.append(value)
    label = "Image" if block_type == "image" else "Document"
    suffix = f" ({', '.join(dict.fromkeys(details))})" if details else ""
    return f"{label} attachment{suffix}. Binary content was not embedded."


def safe_value_text(value: Any) -> str:
    if value is None:
        return "[empty result]"
    if isinstance(value, str):
        return value
    scrubbed = scrub_binary_values(value)
    try:
        return json.dumps(scrubbed, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(scrubbed)


def scrub_binary_values(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in {"base64", "bytes", "data"}:
                scrubbed[str(key)] = "[binary data omitted]"
            else:
                scrubbed[str(key)] = scrub_binary_values(item)
        return scrubbed
    if isinstance(value, list):
        return [scrub_binary_values(item) for item in value]
    if isinstance(value, str) and len(value) > MAX_TOOL_RESULT_CHARS * 2:
        return value[:MAX_TOOL_RESULT_CHARS] + "[…value truncated…]"
    return value
