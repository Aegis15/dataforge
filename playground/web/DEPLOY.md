# DataForge Playground - Cloudflare Workers Static Assets Deployment

This document contains the authoritative steps to deploy the static frontend to
Cloudflare Workers Static Assets. The backend is a separate Hugging Face Space
and is wired into the frontend through `playground/web/config.js`.

## Prerequisites

- A Cloudflare account on the free tier
- The repository pushed to GitHub
- A live Hugging Face Space URL for the API backend

## Step 1: Connect the repository

1. Log in to Cloudflare Dashboard.
2. Go to **Workers & Pages** and open the existing connected Worker project.
3. Connect the GitHub repository.

Use these build settings:

- **Project name**: `dataforge`
- **Production branch**: `main`
- **Build command**:

```bash
python scripts/playground/render_web_config.py
```

- **Deploy command**:

```bash
npx wrangler@4.85.0 deploy --config wrangler.toml
```

- **Root directory**: `/`

`wrangler.toml` is the frontend deployment source of truth. The renderer is the
only supported way to produce the deployable `config.js` file.

## Step 2: Set the backend URL

In the Cloudflare project settings, add:

| Variable | Value | Scope |
| -------- | ----- | ----- |
| `BACKEND_URL` | `https://Praneshrajan15-data-quality-env.hf.space` | Production |
| `BACKEND_URL` | `https://Praneshrajan15-data-quality-env.hf.space` | Preview |

## Step 3: Deploy

After the first successful deploy, the frontend will be served at:

- Production: the Worker project's configured `workers.dev` hostname or custom
  domain
- Preview: the preview URL emitted by Workers Builds for the branch/version

## Step 4: Verify

```bash
python scripts/playground/verify_frontend_deploy.py \
  --frontend-url https://dataforge.<your-workers-subdomain>.workers.dev
```

Confirm that:

- The page loads with `config.js`, `style.css`, and `app.js` as relative assets.
- `config.js` contains the Hugging Face backend URL and is served with
  `Cache-Control: no-store`.
- The frontend warms `/api/health` on load.
- The advanced toggle matches the backend's `advanced_available` field.
- The backend returns `Access-Control-Allow-Origin` for the deployed frontend
  hostname.

## Notes

- No Worker script is required; this remains an assets-only frontend deploy.
- No custom domain is required for the free-tier launch, but any custom domain
  must be added to `DATAFORGE_PLAYGROUND_ORIGINS` in the Hugging Face Space.
- No browser storage is used.
- No API keys are embedded in the frontend; all provider keys stay in Hugging
  Face Space secrets.
