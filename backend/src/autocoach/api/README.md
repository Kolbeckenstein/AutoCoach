# AutoCoach API

FastAPI service that accepts video uploads, runs the pose pipeline, and returns form analysis results via a server-rendered HTML UI.

## Start the server

From the `backend/` directory:

```bash
uv run python -m autocoach.api
```

The server binds to `http://0.0.0.0:8000` by default.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `0.0.0.0` | Bind address |
| `--port` | `8000` | Bind port |
| `--reload` | off | Enable auto-reload on file changes |

```bash
# Custom port with auto-reload (dev mode)
uv run python -m autocoach.api --port 3000 --reload
```

## Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Video upload form |
| `POST` | `/upload` | Accept video, run pose pipeline, return results |
| `GET` | `/static/blob/...` | Serve stored keyframes and blob files |

## Constraints

- Max upload size: 100 MB
- Max video duration: 30 seconds
- Accepted MIME types: `video/*`
