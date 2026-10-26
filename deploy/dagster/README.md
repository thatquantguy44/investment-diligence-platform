# Dagster OSS runtime

This deployment runs the Dagster webserver and daemon with two persistent
volumes:

- `investment_diligence_dagster_home` for Dagster metadata and run state;
- `investment_diligence_uspto_artifacts` for reviewed selections, downloaded
  USPTO releases, immutable approval and discovery records, retry audits, and
  refresh reports.

The runtime is configured to use the repository's PostgreSQL-backed storage
adapter for pipeline data. Database credentials and the USPTO API key are
injected at runtime; they are never copied into the image or committed to Git.

For a local Docker deployment, copy the template and populate it from a secret
manager or other approved runtime source:

```bash
cp deploy/dagster/.env.example deploy/dagster/.env
chmod 600 deploy/dagster/.env
```

`deploy/dagster/.env` is ignored by Git. In a managed deployment, inject the
same variables through the platform's secret store instead of creating that
file.

Build and start the runtime after completing runtime-secret configuration:

```bash
docker compose -f deploy/dagster/docker-compose.yml up --build -d
```

The Dagster UI will be available at `http://localhost:3000`. Starting the
runtime does not enable any schedule or trigger a source request.

Set the configured analyst name and OS user in the runtime environment before
attempting an approved refresh. The template contains the provisional reviewed
size and freshness bounds for `PVGPATDIS/g_patent.tsv.zip`; changing them
invalidates prior discovery fingerprints and approvals. A prepared result with
`stale_review_required` still requires analyst review before it is presented
as current data or manually ingested. The six-hour discovery schedule remains
stopped until a manual approved refresh passes its acceptance checks.

For the manual acceptance run, create the discovery snapshot and approval on
the mounted `/var/lib/diligence` artifact volume and use the same PostgreSQL
capture store as the daemon. A host-only `.data` discovery or approval is not
visible inside the container. The reviewer OS user setting must match the
account that actually runs the review command in that environment.
