# Taiyi v0.1 architecture

## Dependency direction

```text
CLI -> application services -> domain models
             |                    ^
             +-> repository ------+
             +-> provider protocol

SQLite adapter -> repository contract
Mock/OpenAI adapters -> provider protocol
```

The domain contains immutable value models and enums. Application services own workflows
and access checks. SQLAlchemy and model SDKs remain adapters at the edge.

## Identity and worldlines

An `IdentityCore` is a stable name plus a pointer to the active `IdentitySnapshot`. A fork
records the exact base snapshot and gets a unique worldline. Normal reads resolve an
incarnation first and can only load its own events. Cross-worldline access occurs only in the
diff/merge service.

## Event and deletion model

`worldline_events` holds immutable identity, order, type, timestamp, and SHA-256 payload hash.
`event_payloads` holds the sensitive JSON body. Redaction clears the selected body, follows
recorded reply/source links to clear derived event bodies, and invalidates related memories
without changing the event sequence. This reconciles auditability with erasure, while
acknowledging that external backups remain outside Taiyi's control.

## Memory trust boundary

Memories are derived, untrusted records. Every memory names its source events, worldline,
extractor, prompt version, confidence, and importance. Repository validation rejects a normal
memory whose source is outside its own worldline. Human-reviewed synthesis may cite several
worldlines and is identified by a `merge:<proposal-id>` origin.

## Merge state machine

```text
pending -> approved -> applied -> new immutable snapshot
       \-> rejected
```

Applying a proposal checks that the core still points to the proposal's base snapshot. This
prevents a stale review from overwriting newer identity state. Rollback moves the core pointer
and writes an audit record; it never edits or deletes a snapshot.
