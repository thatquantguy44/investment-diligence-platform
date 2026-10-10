# Data contracts

Canonical records use Pydantic models and carry `record_id`, `schema_version`, `pipeline_id`, `source_id`, `run_id`, and `created_at`.

`SourceRecord` captures retrieval metadata and the hash of an immutable raw payload. `Entity`, `EntityAlias`, `Relationship`, `EvidenceRef`, and `QualityResult` are the first shared contract types. Source-native fields should remain in source-specific payloads until a second pipeline demonstrates a need for a broader shared model.

Breaking changes require a new major contract version. Additive optional fields use a compatible minor version.
