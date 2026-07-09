# Security policy

## Sensitive data

Cowork transcripts can contain credentials, personal information, customer data, and other
confidential material. The built-in redactor is best effort, not a guarantee. Review every
export before uploading, publishing, or sharing it.

`--mode archive` intentionally copies untouched Cowork metadata and JSONL files outside the
ChatGPT upload folders. Those raw files can contain system prompts, account details, tool inputs,
tool results, and credentials. Never upload or publish them without a separate security review.

Do not attach real Cowork metadata, transcripts, memory, manifests, or exports to public bug
reports. Reproduce parser problems with a minimal synthetic fixture.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for issues that could expose source data or bypass
redaction. For non-sensitive defects, open a normal GitHub issue using anonymized inputs.
