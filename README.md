# dagger-ci-demo

Companion repository for the 4-part article series: **What CI/CD Looks Like When Platform Engineering Meets AI Agents**.

## The Product

A two-app stack deployed to Google Cloud:

- **`backend/`** — FastAPI REST API on Cloud Run, validates Firebase ID tokens
- **`frontend/`** — Angular 21 SPA on Firebase Hosting, authenticates via Firebase Anonymous Auth

The frontend gets a Firebase ID token and sends it as a `Bearer` header to the backend.

## The Pipeline

The `.dagger/` module is a deterministic CI/CD pipeline — no LLM in the hot path:

- **Pipeline** — lint, test, build, publish, deploy (parallel backend + frontend)
- **Suggest Fix** — on failure, routes to Monty (Python) or Angie (Angular) to post code suggestions on the PR

```bash
dagger call pipeline \
  --source=. \
  --project-id=my-dagger-demo \
  --region=us-central1 \
  --credentials=env:GCP_SA_KEY
```

## Quick Start

```bash
# Install Dagger
curl -fsSL https://dl.dagger.io/dagger/install.sh | sh

# Run backend tests
cd backend
dagger call test --source=.

# Build backend container
dagger call build --source=.
```

## Article Series

1. [The CI/CD Bottleneck Nobody Talks About](https://medium.com/@sami-telchak) — Pipelines as real code
2. [Decoupling Pipelines from Infrastructure](https://medium.com/@sami-telchak) — GitHub Actions, Depot, Kubernetes ARC
3. [From Scripts to a Platform: Your CI/CD Module Library](https://medium.com/@sami-telchak) — Reusable GCP modules
4. [AI-Assisted Pipelines: Agents That Write and Fix Your CI](https://medium.com/@sami-telchak) — Fixed pipelines + AI on failure

## Agent Modules

The Dagger agent modules (Daggie, Monty, Angie) and CI modules are maintained at:
[github.com/telchak/daggerverse](https://github.com/telchak/daggerverse)
