# Architecture

The first release is a Python library with a direct CLI. Each pipeline owns source-specific logic; shared code is limited to contracts, capture metadata, local storage, quality gates, and run context.

```text
source adapter -> immutable raw capture -> canonical records -> quality gates -> materialization
```

The local storage implementation writes JSONL and metadata under a configurable data root. It is intentionally storage-neutral so a later approved object-store adapter can replace it without changing pipeline business logic.

Pipeline code must not import downstream QuantSmith code. The published product manifest is the integration boundary.
