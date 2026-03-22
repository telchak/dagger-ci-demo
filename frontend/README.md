# Angular Frontend — Items App

Minimal Angular 21 SPA that displays items from the FastAPI backend (`../backend/`).

## Stack

- Angular 21 with standalone components
- Firebase Auth (anonymous) for API authentication
- Firebase Hosting for deployment

## Development

```bash
npm install
ng serve
```

Open http://localhost:4200. The app expects the backend running at http://localhost:8080.

## Configuration

Edit `src/app/environments/environment.ts` with your Firebase project config and backend API URL.
