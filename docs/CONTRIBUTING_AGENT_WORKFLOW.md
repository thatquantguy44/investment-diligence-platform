# Agent and Machine-Generated Change Workflow

This repository treats documentation as part of the implementation contract.
Machine-generated code, documentation, configuration, and fixtures must keep
the roadmap and handoff truthful.

## Required context before making changes

An agent must read:

1. [`docs/MASTER_HANDOFF.md`](MASTER_HANDOFF.md)
2. [`docs/MASTER_ROADMAP.md`](MASTER_ROADMAP.md)
3. The relevant spec folder’s `HANDOFF.md` and `ROADMAP.md`.
4. The relevant pipeline and source documentation.

## Documentation update rules

- Update `MASTER_ROADMAP.md` when status, priority, sequencing, scope, or
  cross-spec dependencies change.
- Update `MASTER_HANDOFF.md` when current capabilities, setup, commands,
  limitations, validation results, or next-agent instructions change.
- Update the individual spec roadmap when work is added, completed, deferred,
  or materially reordered within that spec.
- Keep every numbered spec folder limited to one spec document, `HANDOFF.md`,
  and `ROADMAP.md`. Put supporting source and pipeline notes under `docs/`.
- Update the pipeline document when its behavior, inputs, outputs, source path,
  quality gates, or operational commands change.
- Update the root `README.md` when user-facing setup, supported capabilities,
  or primary navigation changes.
- Do not mark work complete without an implementation or test reference.
- Do not call a path live, scheduled, PostgreSQL-backed, or production-ready
  unless that claim has been verified and documented.

Pure refactors do not require a roadmap update, but the agent must still check
whether commands, schemas, tests, or operational behavior changed.

## Required verification

Before handing off or committing a change, run:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m diligence_pipelines.cli validate-manifests
PYTHONPATH=src python -m diligence_pipelines.cli validate-docs
git diff --check
```

If a check cannot run, the handoff must state the exact command, reason, and
remaining risk. Never convert an unrun check into a success claim.

## Change handoff format

Every machine-generated change should leave a concise handoff containing:

- What changed.
- What was verified and with which commands.
- What remains incomplete or untested.
- Which roadmap item moved, if any.
- The recommended next step.

The master handoff is a current-state document, not a historical changelog.
Historical detail belongs in Git history, issue tracking, or a spec-specific
design note.
