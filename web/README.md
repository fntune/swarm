# spawnd web

pnpm + turborepo monorepo for spawnd's web surfaces.

```
apps/dashboard         operator console (Next.js, standalone output)
apps/landing           spawnd.dev marketing site (Next.js, static export)
packages/ui            shared design system: tokens, shadcn primitives, brand
packages/api-client    typed client for the spawnd HTTP API (no React)
packages/typescript-config  shared tsconfig bases
```

## How the dashboard talks to spawnd

The browser never calls the FastAPI service directly. In the default `token`
mode, the operator pastes `SPAWND_API_TOKEN` on `/login`; the token is validated
upstream and stored in an httpOnly cookie. Every API call goes through Next.js
route handlers (`/api/spawnd/[...path]`, allowlisted prefixes only), which
attach the bearer token server-side. Live run events arrive over SSE through
the same proxy.

Tailnet-only deployments can set `SPAWND_DASHBOARD_AUTH_MODE=tailscale`,
`SPAWND_TAILSCALE_ALLOWED_USERS` to a comma-separated login allowlist, and
`SPAWND_API_TOKEN` as a server-side credential. The dashboard then requires
Tailscale Serve's verified `Tailscale-User-Login` header and does not expose a
manual token prompt. Keep this mode bound to localhost and expose it only
through Tailscale Serve; direct access to the FastAPI service remains token
protected.

## Develop

Requires Node 22 (`corepack enable` provides the pinned pnpm).

```bash
# from the repo root: start postgres/redis/minio/api
docker compose up -d postgres redis minio minio-init migrate api

cd web
corepack enable
pnpm install
cp apps/dashboard/.env.example apps/dashboard/.env.local
pnpm dev                                    # dashboard :3000, landing :3001
```

Sign in at http://localhost:3000/login with the compose token (`dev-token`).

## Quality gates

```bash
pnpm lint        # biome
pnpm typecheck
pnpm test        # vitest (api-client + dashboard lib)
pnpm build       # both apps; landing exports to apps/landing/out
```

End-to-end smoke (worker-free: login → submit plan → DAG renders → cancel)
needs the api + postgres + redis stack from above:

```bash
cd apps/dashboard
pnpm exec playwright install chromium   # first time
pnpm exec playwright test
```

CI runs all of this in `.github/workflows/ci.yml` (web, python, e2e jobs).

## Deploy

- **Dashboard** ships as a container (`apps/dashboard/Dockerfile`, Next
  standalone, non-root). The compose service exposes it at
  http://localhost:33000 with `SPAWND_API_URL=http://api:8765`;
  `deploy/podman/up.sh` starts the same container as `spawnd_dashboard_1`.
- **Landing** is a static export (`apps/landing/out/`) intended for spawnd.dev
  on any static host (Vercel, Cloudflare Pages). It is deliberately not part
  of the compose stack.
