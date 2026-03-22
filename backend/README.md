# Python API Example App

A FastAPI REST API with Firebase Auth token validation. This is the **backend service** for the Angular frontend (`../frontend/`).

## Local Development

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8080
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/items` | List all items |
| GET | `/api/items/{id}` | Get item by ID |
| POST | `/api/items` | Create new item |

## Run with Dagger

From the **repository root** (where `.dagger/` lives):

```bash
# Run tests
dagger call test-backend --source=./backend

# Build container
dagger call build-backend --source=./backend
```
