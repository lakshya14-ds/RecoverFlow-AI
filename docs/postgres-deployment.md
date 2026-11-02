# Deploy RecoverFlow with PostgreSQL (AWS example)

This is the route for a hosted pilot, not a completed production certification.
The 2026-11-01 handoff records all 18 migrations applied on AWS RDS PostgreSQL
18.3, with zero pending or unknown revisions, and an HTTP 200 public health
response through Nginx. That is a migration and availability check, not the
full staging gate below. Complete that gate before putting customer data in
this environment.
Keep payments SIMULATED and outbound messaging in sandbox mode until those separate
integrations have been validated and explicitly enabled.

## 1. Prepare the release

1. Review the checkout with `git status --short`. Commit and push only reviewed
   application and deployment files. Never commit `.env`, database files, uploads,
   or secrets. The server deploys the reviewed commit.
2. Use Python 3.12. On the backend install `requirements-postgres.txt` rather than
   `requirements.txt`; it adds the pinned psycopg 3 driver. Keep one API process and
   one `app.worker` process initially. The API already runs intake and supervisor
   background loops, so do not start multiple API replicas until their coordination
   and file storage have been validated in that topology.

## 2. Create the AWS resources

1. In the AWS console choose **Asia Pacific (Mumbai), ap-south-1**. Create an EC2
   Linux host and an RDS PostgreSQL **15 or newer** instance in the same VPC. AWS's
   [EC2 + private RDS walkthrough](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_GettingStarted.CreatingConnecting.PostgreSQL.html)
   covers the networking and initial connection.
2. Set RDS **Public access: No**. Allow inbound TCP 5432 on its security group only
   from the EC2 security group. Do not open PostgreSQL to the internet. Enable RDS
   storage encryption and automated backups with a retention period appropriate to
   the pilot. Record the database endpoint, port, database name, and application
   username in the backend's private configuration.
3. Attach a persistent EBS volume to EC2 and mount it at `/srv/recoverflow-data`.
   Give the service user write access. Plan regular EBS snapshots: RDS backups do
   **not** include uploaded evidence files. Restrict EC2 ingress to HTTPS (and HTTP
   for certificate setup); use a controlled administrative access path.
4. Point `api.example.com` at the EC2 host and configure an HTTPS reverse proxy to
   forward to `127.0.0.1:8002`. The API process itself should remain bound to
   loopback behind the proxy. Use your actual domain in all later settings.

## 3. Configure the backend

On EC2, clone the reviewed release, create a Python 3.12 virtual environment, and
install the PostgreSQL dependency set:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-postgres.txt
```

Store settings in a private backend environment (for example a root-owned,
mode-0600 systemd environment file). Never put database credentials in GitHub,
frontend environment files, command-line arguments, or this document. Use the
private RDS endpoint and URL-encode reserved characters in the password:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@PRIVATE_RDS_HOST:5432/recoverflow?sslmode=verify-full&sslrootcert=/etc/ssl/certs/rds-ca.pem
RECOVERFLOW_API_KEY=GENERATE_A_NEW_LONG_RANDOM_VALUE
FRONTEND_ORIGINS=https://recoverflaw.duckdns.org
DOCUMENT_STORAGE_PATH=/srv/recoverflow-data/documents
INTAKE_STORAGE_PATH=/srv/recoverflow-data/intake
INCOMING_STORAGE_PATH=/srv/recoverflow-data/incoming
PDF_STORAGE_PATH=/srv/recoverflow-data/invoices
EMAIL_DRY_RUN=true
WHATSAPP_ENABLED=false
EMAIL_ENABLED=false
DEBUG=false
```

The TLS URL above assumes the AWS RDS CA bundle has been installed at the named
path. Download the current bundle from [AWS's RDS TLS instructions](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)
and test certificate verification. `DATABASE_URL` overrides `APEX_DB_PATH`. Set
`ADMIN_BOOTSTRAP_PASSWORD` before first startup only if password login is needed.
For the first pilot, keep `RAZORPAY_MODE=test` and do not configure live payment or
messaging credentials. Optional AFIS and AXIS paths need their source databases
mounted separately if those integrations are used.

## 4. Prove PostgreSQL in staging before launch

1. Create a **disposable staging PostgreSQL database**, with its own credentials.
   Point the backend environment at it; do not copy the local SQLite database or
   use customer data for this test.
2. From the repository root, run the initialization once:

   ```bash
   .venv/bin/python -c "from app.database.db_manager import init_db; init_db()"
   .venv/bin/python -c "from app.database.db_manager import engine; from app.database.migrations import status; print(status(engine))"
   ```

   Require `dialect: postgresql`, 18 applied revisions, `pending: []`, and
   `unknown: []`. Run initialization a second time to check idempotency. A failure
   here is a deployment blocker; do not edit `schema_revisions` by hand.
3. Run the repository test suite with an isolated SQLite test database; this catches
   general regressions but does not certify PostgreSQL. Then start one API process
   and one worker process against staging PostgreSQL. Check
   `https://api.example.com/api/v1/system/health` and the
   admin-only `/api/v1/system/migrations` endpoint. Test an authenticated case,
   upload, evidence retrieval, and worker completion using synthetic records.
   Health alone does not prove that PostgreSQL or the worker is functioning.
4. Take a backup and restore it to a separate scratch database. Check revision
   status, row counts, and evidence access after restore. Repeat the same drill
   with the intended production backup policy before accepting customer records.

## 5. Run the backend continuously

Run these as **two supervised services** from the repository root, under the same
service user and environment. Start the API first so migrations finish before the
worker starts:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
.venv/bin/python -m app.worker
```

Use systemd or an equivalent supervisor with automatic restart and logs. After
each release, run the migration-status check. Back up both RDS and the EBS evidence
volume, and rehearse restoring both together. See [database operations](ops-backup.md).

## 6. Publish the frontend

On the EC2 host, Nginx directly serves the static `frontend/` directory and reverse-proxies
API requests (`/api/` and WebSocket endpoints) to the backend uvicorn service running on
`127.0.0.1:8002`.
In `frontend/config.js`, leave `RECOVERFLOW_BACKEND_URL` empty to automatically use the
current domain (e.g., `https://recoverflaw.duckdns.org`). Ensure `FRONTEND_ORIGINS` in
the backend environment matches the hosting origin. Open the site in the browser,
verify the executive sign-in modal, enter credentials or use 1-click Demo Access, and
confirm all dashboards and live feeds connect properly.

## Launch gate

PostgreSQL end-to-end integration, restore, files, and worker checks above must pass
on a disposable staging database. The 2026-11-01 deployment checked migrations
and health only; the repository's 342-test baseline used SQLite. Real
payments, customer messaging, field accuracy, and legal requirements are separate
gates; a successful database deployment does not validate them.
