# Contributing to Taiyi

Use Python 3.11 or newer. Create a virtual environment, install `.[dev]`, and run:

```bash
ruff check .
mypy src/taiyi
pytest
```

Commit messages should use an imperative subject and keep unrelated changes separate.
Changes to architecture or identity invariants require an ADR under `docs/adr/`.
