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

The browser never calls the FastAPI service directly. The operator pastes
`SPAWND_API_TOKEN` on `/login`; the token is validated upstream and stored in
an httpOnly cookie. Every API call goes through Next.js route handlers
(`/api/spawnd/[...path]`, allowlisted prefixes only), which attach the bearer
token server-side. Live run events arrive over SSE through the same proxy.
The only configuration is `SPAWND_API_URL` — server-side, never `NEXT_PUBLIC_`,
and the token is never placed in compose env.

## Develop

Requires Node 22 (`corepack enable` provides the pinned pnpm).

```bash
# from the repo root: start postgres/redis/minio/api
docker compose up -d postgres redis minio minio-init migrate api

cd web
corepack enable
pnpm install
cp .env.example apps/dashboard/.env.local   # SPAWND_API_URL=http://localhost:8765
pnpm dev                                    # dashboard :3100, landing :3001
```

Sign in at http://localhost:3100/login with the compose token (`dev-token`).

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
