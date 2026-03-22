# Angular Frontend

## Application
- Framework: Angular 21 (standalone components)
- Runtime: Node.js 20+
- Hosting: Firebase Hosting

## Build
- Build command: `ng build`
- Output: `dist/angular-frontend/browser`
- Test command: `ng test --watch=false --browsers=ChromeHeadless`

## Deployment
- Target: Firebase Hosting
- Config: `firebase.json`
- Preview channel: `preview`
- Production: `live` channel

## Backend Connection
- API URL configured in `src/app/environments/environment.ts`
- Authenticates via Firebase Anonymous Auth
- Sends ID token as `Authorization: Bearer <token>` header
