# Hosting with Supabase persistence

Hugging Face rejected Docker Space creation for the selected account with **HTTP 402: a PRO subscription is required**. CPU Basic is therefore not a free route for this deployment. The helper does not purchase or upgrade any account. The Supabase schema and dedicated backend key were successfully created before hosting was rejected, so that setup can be reused.

## Render web service with Supabase

Render's current official web-service guidance describes a Free tier with sleep-on-idle and no persistent disks. Availability for a specific account must be confirmed in its Dashboard. The repository's `render.yaml` now explicitly requests **`plan: free`**, creates no Render database or disk, and uses Supabase for durable storage. Do not accept a paid plan if Free is unavailable to the account.

1. Sign in to [Render](https://dashboard.render.com/) using GitHub.
2. Open [Deploy TracePaper to Render](https://render.com/deploy?repo=https://github.com/anerudhh/TracePaper). Authorize access to this repository if prompted. Alternatively choose New → Web Service, select the repository, and choose Docker and the Free compute plan.
3. Confirm the review shows a Free web service and **no paid persistent disk or other paid resource**. Stop if a paid plan is required.
4. Supply `SUPABASE_SERVICE_ROLE_KEY` with the existing `tracepaper_backend` secret key from your Supabase project's API Keys settings. Keep it in Render's environment/secret field, never in chat or source. Set `TRACEPAPER_PASSWORD` to the chosen site password. The Blueprint supplies the Supabase URL and the remaining non-secret settings.
5. Create the service and wait for it to build. Share its public `onrender.com` URL for external verification; the URL is not secret.

No Render API token, Hugging Face token, or site-wide Gemini key is needed for this Dashboard route. Supabase already owns persistence; `/data` in the container is temporary parser workspace. Free-tier quotas and cold starts still apply. Shared workspace access remains password protected, and each visitor supplies their own AI key inside the app.

## Hugging Face alternative (account eligibility required)

The files below remain useful only if the account is eligible to host Docker Spaces. A CPU Basic identifier does not establish that the overall hosting route is free; the selected account received a PRO requirement. Do not rerun this route expecting it to bypass the paywall.

## Hugging Face deployment using GitHub repository secrets

No Codex environment-settings fields are required for this route.

1. Open [TracePaper repository secrets](https://github.com/anerudhh/TracePaper/settings/secrets/actions).
2. Click **New repository secret** three times, adding `HF_TOKEN` (a Hugging Face write token), `SUPABASE_ACCESS_TOKEN` (a Supabase account access token), and `TRACEPAPER_PASSWORD` (your chosen site password). Store values there, not in chat or source.
3. Open **Actions → Deploy TracePaper → Run workflow**, select `main`, and run it. The workflow uses the supplied Hugging Face account and Supabase URL by default. Optional repository variables `HF_NAMESPACE` and `SUPABASE_URL` override those targets.
4. The workflow installs the app-scoped Supabase schema, uploads the CPU Space (if the account is eligible), waits for its build, verifies password protection/upload/retrieval/PDF citations/history, restarts the Space, and requires a new process ID before checking persistence. It removes its own uniquely named sample. A successful run publishes a deployment summary with the Space link. No model call is made.

Only a manual run on `main` can execute this workflow; pull requests cannot trigger its deployment job. It does not request paid hardware or volumes or upgrade an account; it stops when the provider rejects account eligibility. The repository needs GitHub Actions enabled and sufficient runner quota. If a workflow step fails, it does not report deployment success.

## Secure deployment credentials for the CLI alternative

The deployment helper needs a Hugging Face **write** token (`HF_TOKEN`), a Supabase personal access token (`SUPABASE_ACCESS_TOKEN`), and an owner-chosen `TRACEPAPER_PASSWORD`. Set these in secure environment settings or your local process environment, never in source or chat. Use [Hugging Face token settings](https://huggingface.co/settings/tokens) and [Supabase account token settings](https://supabase.com/dashboard/account/tokens). The Supabase dashboard project link contains the project ref; the app API URL is `https://<project-ref>.supabase.co`.

The deployment helper authenticates with both providers, installs only app-prefixed SQL objects and the private `tracepaper` bucket, and creates/reuses a dedicated `tracepaper_backend` secret API key. That project key is kept in memory and sent only to the Hugging Face Space secret API. It is never printed or included in uploaded source. The personal Supabase management token is **not** installed in the running app. Tokens need permission to perform these operations in the selected accounts/project; they are not visitor AI keys.

Hugging Face stores runtime secrets as real environment variables. If your execution environment supplies proxy placeholders instead of raw values, configure the workspace password directly in the Space's Settings secrets and confirm login with your chosen password; proxy-backed values are not general local-process credentials. The app fails closed when `TRACEPAPER_REQUIRE_PASSWORD=1` and the password is absent. There is no anonymous private-library fallback.

## Publish

From the repository root:

```sh
python -m venv .deploy-venv
.deploy-venv/bin/pip install -r requirements-deploy.txt
# Credentials must already be supplied securely to this process.
.deploy-venv/bin/python scripts/deploy_space.py \
  --namespace YOUR_HF_USERNAME --space tracepaper \
  --supabase-url https://YOUR_PROJECT_REF.supabase.co --dry-run
# Remove --dry-run to install the schema and upload the Space.
```

Stage or commit the deployment source files first. The helper publishes only Git-tracked/staged source, excludes local `.env` files, uploads, caches and credentials, and substitutes `deploy/SPACE_README.md` as the Space's root README. This sets Docker SDK and port 8000 without changing the GitHub README. The app runs as user 1000 for Spaces compatibility. An existing Space on paid hardware or a different SDK is rejected, rather than silently reconfigured.

Source upload is **not** deployment success. Wait for the provider build to finish, check the external HTTPS `/api/health`, sign in with the chosen password, upload a sample PDF and DOCX, wait for indexing, ask a question, inspect the original page, and verify that documents/history remain after a Space restart. Live AI generation also needs a visitor-provided working Gemini or OpenAI key. Do not put model keys in Space settings.

## Manual alternative

1. Run `supabase/migrations/001_tracepaper.sql` in your project's SQL editor. Do **not** run `tests/supabase_roles.sql` in a hosted project; that file is test scaffolding only.
2. Create a Docker Space and upload this repository, using `deploy/SPACE_README.md` as its root README.
3. Set Space variables `TRACEPAPER_STORAGE=supabase`, `SUPABASE_URL=https://<ref>.supabase.co`, `SUPABASE_BUCKET=tracepaper`, `TRACEPAPER_DATA=/data`, `PORT=8000`, and `TRACEPAPER_REQUIRE_PASSWORD=1`.
4. Set Space secrets `SUPABASE_SERVICE_ROLE_KEY` to a backend secret/service-role key, and `TRACEPAPER_PASSWORD` to your workspace password.
5. Perform the live checks above.

## Access and limits

Database tables have RLS enabled, direct access is revoked from `anon`/`authenticated`, and RPC execution is restricted to the backend `service_role`. The storage bucket is private. Originals are streamed through the password-protected backend, including PDF byte ranges. Browser code receives neither the Supabase backend key nor signed storage URLs.

This is one password-protected research workspace; people who share its password can see its documents and history. It does not implement separate private user accounts. Each visitor's AI key remains independently held in tab memory and is sent only on that visitor's answer requests. Protect uploaded documents accordingly.

Hosted retrieval uses PostgreSQL full-text indexing and relevance ranking; local mode retains SQLite FTS5/BM25. Both are lexical search, not semantic embeddings. Cloud passages are inserted in bounded batches and become searchable only after indexing completes. Interrupted indexing is recovered at startup. Interrupted uploads become failed entries that can be removed and reuploaded. A durable cleanup queue retries remote-object deletions at startup if the storage API was unavailable when a document was removed.

The fixed 50 MB upload and parser resource limits still apply. Supabase database, storage, and egress quotas and Hugging Face sleep/build limits bound the free demo; the app does not claim unlimited papers. PostgreSQL/RPC semantics are tested against real local PostgreSQL with an object-storage HTTP contract double. Those tests do not establish that a hosted Supabase account or public Space is configured correctly; live checks remain separate.

## Diagnosing a deployment failure

The helper prints a `Deployment step:` label before each provider operation. On failure it prints the stage, HTTP status, and selected provider error fields with known credentials and token formats redacted. A paused Supabase project is reported before running the migration; resume it in the dashboard and wait for it to be healthy.

After a code fix, start **Actions → Deploy TracePaper → Run workflow → main**. **Re-run jobs** on an older run uses its original commit and will not pick up fixes pushed afterward. If a run still fails, share the named failed deployment step and redacted provider error text, never the secret values.
