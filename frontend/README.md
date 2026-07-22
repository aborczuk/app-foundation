# Financial Acceleration Tracker UI

This is the local browser seam for the filing-backed MVP. It follows TailAdmin's sidebar, card, table, and chart visual language without copying its template source into the repository.

## Run

From the repository root, start the API:

```bash
uv run uvicorn financial_tracker.app:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite proxy forwards `/health` and `/api` to the API on port 8000.
