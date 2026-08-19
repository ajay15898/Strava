# Pace — frontend

React 19 + TypeScript + Vite. Part of [Pace](../README.md); it is not
useful on its own, since every view reads the backend API.

```bash
npm install
npm run dev      # http://localhost:5173
npm run build
```

`/api` is proxied to `http://127.0.0.1:8000`, so the client stays
origin-relative and CORS never enters the picture. Start the backend first.
