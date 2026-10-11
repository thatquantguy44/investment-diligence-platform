# React knowledge graph prototype

This is the React version of the Pipeline 01/02 knowledge graph prototype. It currently uses embedded fixture data and does not connect to PostgreSQL or external APIs.

## Run locally

```bash
cd app/knowledge
npm install
npm run dev
```

Then open the local Vite URL. Build a static bundle with `npm run build`.

## Next integration step

Replace `src/data.js` with a read-only API response or generated export from PostgreSQL `IDP`. Keep the current source/candidate styling and evidence panel when connecting real data.
