# Contributing

Contributions are welcome, especially anonymized fixtures for Cowork schema changes on macOS or
Windows.

Keep changes narrow and avoid adding runtime dependencies unless the standard library cannot
solve the problem clearly. Never commit real transcripts or generated exports.

Run the checks before opening a pull request:

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q src tests
```

When reporting a format change, include only synthetic JSON that demonstrates the new record
shape. Remove names, email addresses, paths, IDs, tokens, and business content.
