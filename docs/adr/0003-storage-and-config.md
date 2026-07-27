# ADR 0003: Local storage and configuration

- Status: Accepted
- Date: 2026-07-27

## Decision

Taiyi stores v0.1 state in one SQLite database under `TAIYI_DATA_DIR`. The default is the
operating system's local application-data directory. CLI `--data-dir` overrides it. Runtime
configuration comes from environment variables; secrets are never written by Taiyi.

Events are append-only metadata records. Sensitive payload bodies are stored separately so
they can be cryptographically or physically erased later without rewriting event identity,
ordering, or hashes.
