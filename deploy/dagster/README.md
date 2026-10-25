# Dagster OSS runtime

This deployment runs the Dagster webserver and daemon with two persistent
volumes:

- `investment_diligence_dagster_home` for Dagster metadata and run state;
- `investment_diligence_uspto_artifacts` for reviewed selections, downloaded
  USPTO releases, and refresh reports.

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
