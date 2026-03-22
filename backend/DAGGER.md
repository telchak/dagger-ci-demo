# Deployment Context

## Service Type
Cloud Run

## Application
- Framework: FastAPI
- Runtime: Python 3.12 / uvicorn
- Port: 8080

## Build
- Dockerfile present in repo root
- Build command: `docker build -t app .`
- Health endpoint: `/health`

## Frontend Connection
- Angular frontend deployed to Firebase Hosting
- Backend validates Firebase ID tokens on `/api/*` routes
- Set `FRONTEND_URL` env var to the Firebase Hosting URL for CORS
- Set `GCP_PROJECT_ID` env var for token audience validation

## Deployment Preferences
- Memory: 512Mi
- CPU: 1
- Min instances: 0 (scale-to-zero)
- Max instances: 10
- Allow unauthenticated: true
- Environment variables: ENV=production, FRONTEND_URL=<firebase-hosting-url>, GCP_PROJECT_ID=<project-id>
