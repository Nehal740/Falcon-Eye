# Deploy Falcon Eye for free: Cloudflare + Render + Supabase

Falcon Eye has three parts. Each goes to the free service that fits it:

| Part | What it is | Where | Address |
|---|---|---|---|
| Website | The React pages (static files) | **Cloudflare** | `https://falcon.projectfalcon.cc` |
| Backend | The Python/FastAPI program that must always run | **Render** (free web service) | `https://api.projectfalcon.cc` |
| Database | PostgreSQL | **Supabase** (free project) | private connection string |

Replace `projectfalcon.cc` with your domain. You cannot *rename* a registered domain. You can use any
subdomain for free (here `falcon.` and `api.`), or buy a different domain later.

## Honest limits of the free plan
* **Render free sleeps after 15 minutes without traffic** and takes about a minute to wake. The first
  request after a quiet period is slow, and an agent's first call may time out once. Fine for a portfolio or
  personal use. For real company use, move the backend to a paid always-on service (about $7/month) or a VPS.
* Render's free disk is temporary. That is fine because all data lives in Supabase.
* Rate-limit counters and approval-email timers live in memory, so they reset when Render restarts.
* Supabase free projects can pause after a period of inactivity. Check Supabase's current rules and unpause from its dashboard if needed.
* Free tiers change. Check each provider's pricing page before relying on them.

## Step 1 - Supabase (database)
1. supabase.com -> sign in -> **New project**. Name `falcon-eye`, choose a region near you, set a strong database password (save it in a password manager, never in chat or GitHub).
2. Wait until the project is ready, then click **Connect** at the top.
3. Choose **Session pooler** (it works on IPv4, which Render uses). Copy the connection string. It looks like `postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-0-REGION.pooler.supabase.com:5432/postgres`.
4. Replace `[YOUR-PASSWORD]` with your database password. Keep this string private: it is your `DATABASE_URL`.
Do not use the "Direct connection" string (IPv6 only on the free plan) and do not use port 6543.

Falcon Eye creates its own tables on first start and switches on row-level security so Supabase's public
REST API cannot read them. If you want to be extra sure, also run `scripts/supabase_lockdown.sql` in
Supabase -> SQL Editor once after the first start.

## Step 2 - Render (backend)
1. Push this project to GitHub (it already is).
2. render.com -> sign in with GitHub -> **New -> Blueprint** -> pick the `Falcon-Eye` repository. It reads `render.yaml`.
3. When asked, fill the three values:
   * `DATABASE_URL`: the Supabase string from Step 1
   * `CORS_ORIGINS`: `https://falcon.projectfalcon.cc`
   * `APP_BASE_URL`: `https://falcon.projectfalcon.cc`
4. Click **Apply**. Wait for "Live". Open `https://<your-service>.onrender.com/health` - you should see `{"status":"ok"...}`.
5. Optional but recommended, in the service's **Environment** tab add your email settings (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`) and AI settings (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`) exactly as in your local `.env`. Type them only in Render's page.
6. **Settings -> Custom Domains -> Add** `api.projectfalcon.cc`. Render shows a CNAME target.
7. Cloudflare -> your domain -> **DNS -> Records -> Add record**: Type `CNAME`, Name `api`, Target = the value Render showed, **Proxy status: DNS only (grey cloud)**. Back in Render click Verify; it issues HTTPS automatically.

## Step 3 - Cloudflare (website)
1. Cloudflare -> **Workers & Pages -> Create -> connect to Git** -> choose the `Falcon-Eye` repository.
2. Settings:
   * Root directory: `frontend`
   * Build command: `npm ci && npm run build`
   * Deploy command (if asked): `npx wrangler deploy`
   * Build variable: `VITE_API_URL` = `https://api.projectfalcon.cc`
   (If Cloudflare offers the "Pages" flow instead: build output directory `dist`, same variable.)
3. Deploy. Then open the project's **Settings -> Domains & Routes -> Add -> Custom domain** and enter `falcon.projectfalcon.cc`. Cloudflare adds the DNS record for you.
4. If your backend address is not `api.projectfalcon.cc`, edit the `connect-src` line in `frontend/public/_headers`, commit and push.

## Step 4 - Check it works
1. Open `https://falcon.projectfalcon.cc`, register, confirm the welcome email arrives.
2. In Supabase -> Table Editor you should see Falcon Eye's tables (users, agents, ...).
3. Create an agent, copy its key, and send a test request to `https://api.projectfalcon.cc/v1/ping`.

## Troubleshooting
* **Page loads but sign-in says it cannot reach the server**: `VITE_API_URL` was not set at build time (set it and redeploy), or `CORS_ORIGINS` on Render does not exactly match the website address (no trailing slash).
* **First request is very slow**: Render woke up from sleep. Wait a minute and retry.
* **Render log says it cannot connect to the database**: you used the direct connection or port 6543. Use the Session pooler string.
* **Build fails on Render**: copy the last 30 lines of the build log and ask for help.

Do not paste keys, passwords or connection strings into chat or GitHub.
