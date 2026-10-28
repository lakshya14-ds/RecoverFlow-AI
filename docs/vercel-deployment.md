# Deploy RecoverFlow from GitHub to Vercel

Vercel hosts the static workbench. FastAPI and its workers run on a persistent Python host with an HTTPS URL. This split is required by the current SQLite database, stored evidence files, and continuous intake processing. It is a **synthetic pilot**, with SIMULATED Razorpay payments and sandbox-only outbound messages.

**Required before starting:** a GitHub repository containing the deployment files in this checkout, a Vercel account connected to GitHub, and an HTTPS URL for the continuously running backend. Importing GitHub into Vercel alone publishes the UI but cannot run the full workflow. The current backend is not deployable as a Vercel Function because its writable files and workers must survive requests.

## 1. Prepare the backend

Use one Python 3.12 host with a persistent disk and a public HTTPS URL. Deploy this repository there, install `requirements.txt`, and run the API and worker as two supervised processes from the repository root:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
python -m app.worker
```

The last two commands are separate long-running processes. Set the host's HTTP routing to forward HTTPS traffic to port 8002. Start with one API instance and one worker when using SQLite; do not scale this pilot to multiple hosts.

Set these **backend** environment variables in the host's secret manager, not in Git:

```text
RECOVERFLOW_API_KEY=<a new, long, random staff key>
APEX_DB_PATH=/persistent/recoverflow/recoverflow.db
INTAKE_STORAGE_PATH=/persistent/recoverflow/intake
INCOMING_STORAGE_PATH=/persistent/recoverflow/incoming
PDF_STORAGE_PATH=/persistent/recoverflow/invoices
FRONTEND_ORIGINS=https://YOUR-PROJECT.vercel.app
EMAIL_DRY_RUN=true
```

Generate `RECOVERFLOW_API_KEY` locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`; copy the result directly into the backend host's secret manager. Do not paste it into GitHub, Vercel, or chat. The user enters that same key in the workbench after deployment.

| Variable | Where | Required? | Purpose |
| --- | --- | --- | --- |
| `RECOVERFLOW_BACKEND_URL` | **Vercel** | Yes | Public HTTPS backend origin, such as `https://api.example.com`; the build embeds it in browser JavaScript. |
| `RECOVERFLOW_API_KEY` | **Backend only** | Yes | Private staff API key. Never set it on Vercel for this static frontend. |
| `FRONTEND_ORIGINS` | **Backend only** | Yes | Exact Vercel site origin(s) allowed by CORS, separated by commas. |
| `APEX_DB_PATH` | **Backend only** | Yes | SQLite file on the persistent disk. |
| `INTAKE_STORAGE_PATH`, `INCOMING_STORAGE_PATH`, `PDF_STORAGE_PATH` | **Backend only** | Yes | Writable evidence and upload directories on the persistent disk. |
| `EMAIL_DRY_RUN` | **Backend only** | Yes, `true` | Keeps email in sandbox mode. |
| `META_API_KEY_1`, `_2`, `_3` | **Backend only** | Optional | Model assistance; leave unset for rules fallback. |
| `ADMIN_BOOTSTRAP_PASSWORD` | **Backend only** | Optional | Initial password login on a fresh database. The UI uses the staff API key instead. |

Keep `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, WhatsApp/Meta tokens, SMTP credentials, and Shopify credentials unset for the synthetic demo. The payment flow remains SIMULATED and messages remain sandbox-only. No provider key belongs in Vercel's environment variables for this deployment.

Create the `/persistent/recoverflow` directory and mount the host's persistent disk there. The service account must be able to write it. Set `ADMIN_BOOTSTRAP_PASSWORD` only if password login is required; give it a new strong value **before the first start on a fresh database**. The web UI uses `RECOVERFLOW_API_KEY`, so password login is optional. An existing database created by older versions may still contain the former fixed admin password: rotate or remove that account before exposing that database to the internet. Never copy a local pilot database containing real or private data into this deployment.

Optional `META_API_KEY_1`, `_2`, and `_3` stay on the backend. Without them, rules fallback remains available and unsupported documents go to staff review. Do not enable live messaging or payment credentials for this demo.

Before connecting Vercel, visit `https://YOUR-BACKEND/api/v1/system/health` and confirm `status: ok`. Test an authenticated endpoint with the new staff key from a private terminal. A public health response only proves that the API process is reachable; also confirm both worker processes and the persistent disk in the host's logs.

## 2. Push the deployment files to GitHub

The local working tree currently contains changes from multiple agents. Review `git status --short`, commit the application and deployment changes you intend to publish, and push to the branch you want Vercel to use (currently `master`). Do not commit `.env`, `.db`/`.db-shm`/`.db-wal`, `dist/`, `output/`, or local test artifacts. Vercel builds the **pushed commit**, not your uncommitted files. You can push through your Git client or use:

```bash
git status --short
git add <reviewed source and deployment files>
git commit -m "Prepare RecoverFlow Vercel frontend"
git push origin master
```

Replace the placeholder in `git add` with only the reviewed paths. Do not run `git add .` while the unrelated generated artifacts remain in this checkout.

## 3. Import GitHub into Vercel

In [Vercel's new project page](https://vercel.com/new), connect GitHub if prompted, select `lakshya14-ds/RecoverFlow-AI`, and choose:

| Setting | Value |
| --- | --- |
| Root Directory | repository root |
| Framework Preset | Other |
| Install Command | empty; `vercel.json` skips it |
| Build Command | `node scripts/build_vercel_frontend.mjs` (also in `vercel.json`) |
| Output Directory | `dist` (also in `vercel.json`) |
| Production Branch | `master` |
| Environment variable, Production and Preview | `RECOVERFLOW_BACKEND_URL=https://YOUR-BACKEND` |

Add the environment variable **before** clicking Deploy. Use the backend origin only, with no `/api` path or trailing path. `RECOVERFLOW_BACKEND_URL` is public, never a key or token. The build rejects HTTP, paths, credentials, and missing values. `vercel.json` already supplies the build and output settings; verify that the import screen matches it, then click **Deploy**.

After Vercel gives you the site URL, put its exact origin (for example `https://YOUR-PROJECT.vercel.app`) in the backend's `FRONTEND_ORIGINS` and restart the API. Add each exact custom domain or preview origin you intend to use, separated by commas. The browser will otherwise reject cross-origin API calls. If you change a Vercel environment variable later, redeploy for the new value to be embedded in `config.js`.

Open the Vercel URL, enter the new staff key in the workbench, and check that the status says **Connected**. Confirm cases load, an intake upload advances, and a source document opens. The frontend's bundled synthetic PDFs and evaluation file are static; case data comes from the backend.

Each new commit pushed to the connected production branch triggers another Vercel deployment. Other branches create previews; an interactive preview needs its exact preview origin added to backend `FRONTEND_ORIGINS`.

## 4. Limits of this pilot

- This is not a production migration. SQLite, local files, the in-process intake loop, and the separate worker need a single persistent host. Back up the database and evidence directory together.
- The backend's current upload limit is 10 MB. This architecture sends uploads directly from the browser to the backend, so the Vercel Function payload limit does not apply; your backend proxy must allow 10 MB requests.
- Frontend preview domains change. Add each exact preview origin to `FRONTEND_ORIGINS` if you need interactive previews.
- Do not deploy the Python API itself as a Vercel Function without replacing its database, file storage, and continuous workers. Vercel Functions have ephemeral writable scratch space.

For local verification before deployment:

```powershell
$env:RECOVERFLOW_BACKEND_URL = "https://api.example.com"
node scripts/build_vercel_frontend.mjs
node --check frontend/app.js
python -m pytest -q
```

Replace the example backend URL with the real one. The resulting `dist/` contains only the static frontend and is ignored by Git.
