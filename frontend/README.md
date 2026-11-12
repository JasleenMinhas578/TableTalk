# TableTalk frontend

React website for TableTalk: upload spreadsheets, see how your tables connect, ask questions, and test SQL.

## Run it

You need two terminals.

**Terminal 1, the backend** (from the TableTalk folder):

```bash
uv run uvicorn app.main:app --reload
```

**Terminal 2, the website** (from TableTalk/frontend):

```bash
npm install      # first time only
npm run dev
```

Then open http://localhost:5173. Ollama must be running for chat answers.

## What's inside

| File | What it does |
| --- | --- |
| `src/App.jsx` | The page layout: top bar, tables sidebar, and the three tabs |
| `src/components/Upload.jsx` | Drag-and-drop upload and recent sessions |
| `src/components/Sidebar.jsx` | Your tables, columns, types and keys |
| `src/components/ErMap.jsx` | The interactive data map (React Flow + dagre layout) |
| `src/components/Chat.jsx` | Ask questions, see intent, SQL, results and warnings |
| `src/components/Playground.jsx` | SQL editor with autocomplete, run, AI fix, and saved checks |
| `src/components/ResultView.jsx` | Results as a table (first 100 rows, with the real total) and CSV download |
| `src/components/Mascot.jsx` | Tabby, the spreadsheet mascot |
| `src/api.js` | Every call to the backend |
| `src/lib/data.js` | Chart picking, formatting, starter questions |
| `src/lib/storage.js` | Recent sessions and saved checks in the browser |

Calls to `/api/...` are forwarded to the FastAPI server on port 8000 (see `vite.config.js`).
