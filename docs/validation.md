# Release validation

Validated in the managed Linux cloud environment on 2026-11-12. These are observed checks, not a guarantee that every possible document or provider account works.

| Check | Result |
| --- | --- |
| Backend regression suite | 37 passed, including PDF/DOCX indexing, English OCR, citations, history, deletion, password/origin checks, BYOK isolation and non-persistence, request-size bounds, encrypted PDFs, and parser timeout recovery and interrupted-job recovery, hosted PostgreSQL/RPC/storage contracts, access restrictions, and deployment packaging |
| Browser integration suite | 3 passed: PDF question/source/export/mobile workflow; per-tab key add/replace/remove/reload and visitor separation; DOCX sections, upload errors, failed parsing, search, and deletion |
| Production TypeScript/Vite build | Passed |
| Release Docker container | Passed under 512 MiB / 1 CPU: password gate, four concurrent uploads, indexing, byte-range PDF serving, expected citation page, no-evidence answer, origin rejection, persistence after restart, and cascading deletion |
| Frontend formatting / Python dependency consistency | Passed |
| npm dependency audit | No reported vulnerabilities |
| pip-audit dependency audit | No reported vulnerabilities |
| Retrieval mechanics | 3/3 labeled synthetic targets retrieved at rank 1 with 10,000 synthetic distractors; see evaluation.json. Not a research-quality benchmark. |

The release fixes an affected Vite version and affected Python dependency versions. Parsing runs outside the API in a separate process rather than sharing PyMuPDF across threads. A parser has a 256 MiB address-space limit, 120-second CPU limit, and 180-second wall-time limit. One parser runs at a time; indexing jobs are durable in SQLite and interrupted work is retried at startup. These process limits are not a complete OS security sandbox.

Provider success, invalid citations, safety blocks, truncated output, invalid JSON, quota errors, and provider failures are exercised with mocked responses and synthetic keys. **Live Gemini/OpenAI generation has not been verified with a valid visitor key.** No key from chat was used. Each visitor must enter a valid key through the app's Response settings.

The repository includes Docker and Render configuration. An actual public website deployment and its external HTTPS/persistence checks require a hosting account and access; neither a local production build nor an environment snapshot establishes that a site was deployed. Shared workspace access is not private multi-user storage. Semantic retrieval and human-scored citation correctness remain future work, as documented in the README.

## Navy-and-white / free-hosting update

The interface has been changed to deep navy navigation and white reading surfaces. Supabase support uses service-only RPCs and a private storage bucket; local SQLite remains available. Four hosted-storage integration cases ran against PostgreSQL 16 with a mocked HTTP object-storage service, plus one fail-closed configuration test and three deployment-helper tests. The deployment-helper tests cover free-CPU configuration, management API requests, and keeping secrets out of the uploaded source. All 37 backend tests and all 3 browser scenarios passed. This does not constitute a live hosted Supabase/Space verification.

Target account/project identifiers have been supplied, but hosting credentials have not been applied to the running environment. No public Hugging Face Space deployment has been verified. The required secure settings are HF_TOKEN, SUPABASE_ACCESS_TOKEN, and the chosen workspace password. The deployment package was dry-run validated for the supplied target.

## GitHub repository-secrets deployment route

A manual `Deploy TracePaper` GitHub Actions workflow now provides deployment without Codex environment-secret fields. It is restricted to `main`, uses read-only GitHub token permissions, validates required secrets by name only, and runs a post-deployment HTTPS/authenticated smoke test. Restart verification requires the process instance ID to change; a stale health response is not accepted as persistence evidence. Only the verifier's uniquely named, unique-digest sample is deleted afterward. Model APIs are not called.

The two new live-verifier unit tests pass. The latest local suite reports 35 passed and four conditional PostgreSQL integration cases skipped because no test database container was selected; the earlier full PostgreSQL run passed before these two tests were added. Workflow YAML, its manual/main-only gate, and embedded shell syntax were checked. The GitHub-hosted deployment workflow itself has not run with hosting credentials yet, so no public deployment success is claimed.

## Read-only migration regression

A hosted deployment reported PostgreSQL `25006: cannot execute CREATE TABLE in a read-only transaction`. The migration now uses `BEGIN READ WRITE` instead of inheriting a session's default transaction mode. A real PostgreSQL regression first reproduces the failure with `default_transaction_read_only=on`, then applies the full updated migration successfully under that same default. The 14 storage/deployment/verifier tests passed. The hosted deployment still needs a fresh workflow run to validate this fix against the user's project; no global database settings were changed.

## Hosting eligibility correction

The actual GitHub-hosted run successfully authenticated, installed the Supabase schema/private bucket and created the dedicated backend key, then Hugging Face rejected Docker Space creation with HTTP 402 and an explicit PRO requirement. This supersedes earlier assumptions that CPU Basic was available free for this account. No hosting subscription was purchased, and no successful public Space deployment is claimed.

The Render Blueprint now requests `plan: free`, no Render disk/database, and Supabase persistence. Its YAML structure and secret prompting were checked, and the 8 deployment/verifier tests pass. Render's official web-service guidance describes Free services, but account-specific availability and the provider's final Blueprint validation must be confirmed in the Dashboard before creation. No Render website has been deployed or externally verified yet.
