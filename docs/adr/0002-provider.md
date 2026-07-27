# ADR 0002: Provider boundary and first real provider

- Status: Accepted
- Date: 2026-07-27

## Decision

The domain and application layers depend on a small `ModelProvider` protocol. v0.1 ships
with deterministic `MockProvider` and an `OpenAIProvider` using the Responses API. The
default provider is `mock`; real calls require explicit configuration and `OPENAI_API_KEY`.
The default model is configurable and initially set to `gpt-5.6-terra`.

## Consequences

Tests and standard experiments are offline and reproducible. Provider output is treated as
untrusted derived data, validated at the application boundary, and never edits a snapshot
without review.
