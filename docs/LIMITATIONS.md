# Known limitations in v0.1

- One local operator and one default identity core per CLI data directory are assumed.
- SQLite serialization is suitable for local experiments, not a distributed writer fleet.
- Memory comparison uses exact normalized text and typed tags, not semantic embeddings.
- OpenAI extraction relies on JSON returned by the model and may require model-specific tuning.
- Redaction covers the active database and derived memories, not user-created exports or backups.
- Human approval reduces accidental core changes but cannot establish that a memory is true.
- `self_description` remains stable in v0.1; reviewed memories carry most identity evolution.
- Import, web UI, multi-user permissions, vector search, and decentralized exchange are deferred.
