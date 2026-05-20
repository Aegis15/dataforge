# DataForge Playground - Cloudflare Workers Static Assets Deployment

This document contains the authoritative steps to deploy the React/Vite
playground frontend to Cloudflare Workers Static Assets. The API backend stays
in the separate Hugging Face Docker Space and is wired through
`playground/web/public/config.js`.

## Prerequisites

- A Cloudflare account on the free tier
- Node.js 22 or newer
- The repository pushed to GitHub
- A live Hugging Face Space URL for the API backend

## Step 1: Configure the backend URL

In the Cloudflare project settings, add:

| Variable | Value | Scope |
| -------- | ----- | ----- |
| `BACKEND_URL` | `https://<hf-user>-dataforge-playground.hf.space` | Production |
| `BACKEND_URL` | `https://<hf-user>-dataforge-playground.hf.space` | Preview |

The build must render this value before Vite copies public assets:

```bash
python scripts/playground/render_web_config.py
```

## Step 2: Build the static app

From the repository root:

```bash
npm --prefix playground/web ci
npm --prefix playground/web run build
```

The build writes `playground/web/dist`. `wrangler.toml` points Cloudflare at
that directory. `public/_headers` is copied into the build so `config.js` is
served with `Cache-Control: no-store` and hashed assets are long-cacheable.

## Step 3: Deploy

```bash
npx wrangler@4.85.0 deploy --config wrangler.toml
```

No Worker script is required; this remains an assets-only frontend deploy.

## Step 4: Verify

```bash
python scripts/playground/verify_frontend_deploy.py \
  --frontend-url https://dataforge.<your-workers-subdomain>.workers.dev \
  --backend-url https://<hf-user>-dataforge-playground.hf.space
```

The verifier checks that:

- The Cloudflare root serves the built React shell and hashed assets.
- `config.js` contains the Hugging Face backend URL and is uncached.
- The backend root returns API metadata instead of stale frontend HTML.
- `/api/health` exposes `status`, `advanced_available`, and `max_upload_bytes`.
- Backend CORS allows the exact deployed frontend origin.

## Quality Gates

Run the frontend gates locally before deployment:

```bash
npm --prefix playground/web run typecheck
npm --prefix playground/web run test:unit
npm --prefix playground/web run test:e2e
```

The browser suite covers sample and upload flows, repair dry-run evidence,
keyboard tabs, mobile viewport behavior, export/copy actions, and axe-powered
accessibility checks.

## Notes

- No browser persistence is used.
- No API keys are embedded in the frontend; provider keys stay in Hugging Face
  Space secrets.
- In production, `DATAFORGE_PLAYGROUND_ORIGINS` must contain the exact
  Cloudflare frontend origin. The backend does not allow broad `workers.dev`
  wildcards.
