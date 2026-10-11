# React knowledge graph prototype

This is the React version of the Pipeline 01/02 knowledge graph prototype. It starts in embedded fixture mode and can switch to a read-only PostgreSQL graph through the local Python API.

## Run locally

```bash
cd app/knowledge
npm install
npm run dev
```

Then open the local Vite URL. Build a static bundle with `npm run build`.

## Use real PostgreSQL data

From the repository root, install PostgreSQL support and start the read-only API:

```bash
pip install -e '.[postgres]'
DILIGENCE_STORAGE_BACKEND=postgres PYTHONPATH=src python -m diligence_pipelines.knowledge_api
```

In Terminal 1, from repository root:

```bash
pip install -e '.[postgres]'
DILIGENCE_STORAGE_BACKEND=postgres PYTHONPATH=src python -m diligence_pipelines.knowledge_api
```
In Terminal 2:

```bash
cd app/knowledge
npm install
npm run dev
```


In a second terminal, run the React app with `npm run dev`, then select **Live PostgreSQL**. The browser never receives the database password; the Python API reads the configured `IDP` database and returns a bounded graph payload.

## Next integration step

The API endpoint is `GET /api/knowledge/graph?limit=120`. Keep the current source/candidate styling and evidence panel when expanding the live integration.
