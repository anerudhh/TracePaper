"""Deploy the committed/staged app to free Hugging Face CPU hosting and Supabase.

Tokens are read only from process environment. No secret values are printed or
written to disk. The Supabase backend key is retained only in memory and sent to
Hugging Face's secret API, never committed with source. Run --dry-run first.
"""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def project_ref(url):
    match = re.fullmatch(r"https://([a-z]{20})\.supabase\.co/?", url)
    if not match:
        raise ValueError("Provide the Supabase project API URL, not the dashboard URL.")
    return match.group(1)


def deployment_files():
    files = (
        subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
        .decode()
        .split("\0")
    )
    # git ls-files includes staged additions. Secrets, caches and uploads are never included.
    selected = []
    for name in filter(None, files):
        if name.startswith(
            (".git/", ".venv/", "data/", "web/node_modules/", "web/dist/", ".env")
        ) or name.endswith(".log"):
            continue
        if (ROOT / name).is_symlink():
            raise ValueError("Deployment refuses symlinked source files.")
        if (ROOT / name).is_file():
            selected.append(name)
    for required in (
        "Dockerfile",
        "backend/main.py",
        "backend/store.py",
        "supabase/migrations/001_tracepaper.sql",
        "deploy/SPACE_README.md",
    ):
        if required not in selected:
            raise ValueError("Stage or commit all deployment files before uploading.")
    return selected


def prepare_folder(target, files):
    for name in files:
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    shutil.copyfile(ROOT / "deploy/SPACE_README.md", target / "README.md")


def deploy(repo_id, url, api, client, files, password):
    ref = project_ref(url)
    api.whoami()  # Fail before any mutation if hosting authentication is unavailable.
    response = client.get(f"https://api.supabase.com/v1/projects/{ref}")
    response.raise_for_status()
    # Only app-prefixed tables/functions and the tracepaper bucket are touched.
    response = client.post(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        json={
            "query": (ROOT / "supabase/migrations/001_tracepaper.sql").read_text(),
            "read_only": False,
        },
    )
    response.raise_for_status()
    print("Supabase schema and private document bucket installed.")
    response = client.get(
        f"https://api.supabase.com/v1/projects/{ref}/api-keys",
        params={"reveal": "true"},
    )
    response.raise_for_status()
    key = next(
        (
            k.get("api_key")
            for k in response.json()
            if k.get("name") == "tracepaper_backend" and k.get("api_key")
        ),
        None,
    )
    if not key:
        response = client.post(
            f"https://api.supabase.com/v1/projects/{ref}/api-keys",
            params={"reveal": "true"},
            json={
                "type": "secret",
                "name": "tracepaper_backend",
                "description": "TracePaper private storage backend",
                "secret_jwt_template": {"role": "service_role"},
            },
        )
        response.raise_for_status()
        key = response.json().get("api_key")
    if not key:
        raise RuntimeError("A dedicated backend storage key was not returned.")
    # No GPU, paid hardware, or persistent Hugging Face disk is requested.
    api.create_repo(
        repo_id=repo_id,
        repo_type="space",
        space_sdk="docker",
        private=False,
        exist_ok=True,
    )
    info = api.repo_info(repo_id=repo_id, repo_type="space")
    runtime = api.get_space_runtime(repo_id=repo_id)
    if runtime.hardware not in (
        None,
        "cpu-basic",
    ) or runtime.requested_hardware not in (None, "cpu-basic"):
        raise RuntimeError(
            "The existing Space is not on free CPU hardware. Choose a free CPU Space before deployment."
        )
    if getattr(info, "sdk", "docker") != "docker":
        raise RuntimeError(
            "Existing Space does not use Docker; refusing to overwrite it."
        )
    for name, value in {
        "TRACEPAPER_STORAGE": "supabase",
        "SUPABASE_URL": url.rstrip("/"),
        "SUPABASE_BUCKET": "tracepaper",
        "TRACEPAPER_DATA": "/data",
        "PORT": "8000",
        "TRACEPAPER_REQUIRE_PASSWORD": "1",
    }.items():
        api.add_space_variable(repo_id=repo_id, key=name, value=value)
    api.add_space_secret(repo_id=repo_id, key="SUPABASE_SERVICE_ROLE_KEY", value=key)
    if password:
        api.add_space_secret(repo_id=repo_id, key="TRACEPAPER_PASSWORD", value=password)
    with tempfile.TemporaryDirectory(prefix="tracepaper-space-source-") as folder:
        prepare_folder(Path(folder), files)
        api.upload_folder(
            repo_id=repo_id,
            repo_type="space",
            folder_path=folder,
            commit_message="Deploy navy-and-white TracePaper with durable Supabase storage",
        )
    print("Source uploaded: https://huggingface.co/spaces/" + repo_id)
    print(
        "Deployment is not verified until the Space is running and its HTTPS health/authenticated workflows pass."
    )
    if not password:
        print(
            "Set TRACEPAPER_PASSWORD in the Space Settings secrets before the backend can start."
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--space", default="tracepaper")
    parser.add_argument("--supabase-url", default=os.getenv("SUPABASE_URL", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,64}", args.namespace) or not re.fullmatch(
        r"[A-Za-z0-9_-]{2,64}", args.space
    ):
        parser.error("Invalid account or Space name.")
    project_ref(args.supabase_url)
    files = deployment_files()
    if args.dry_run:
        with tempfile.TemporaryDirectory() as folder:
            prepare_folder(Path(folder), files)
        print(
            f"Deployment package validated: {len(files)} source files; Docker CPU Space; durable Supabase schema; no local uploads or credentials."
        )
        return
    missing = [
        key for key in ("HF_TOKEN", "SUPABASE_ACCESS_TOKEN") if not os.getenv(key)
    ]
    if missing:
        parser.error(
            "Enter these credentials securely in environment settings: "
            + ", ".join(missing)
        )
    os.environ.setdefault(
        "HF_HOME", str(Path(tempfile.gettempdir()) / "tracepaper-hf-cache")
    )
    import httpx
    from huggingface_hub import HfApi

    api = HfApi(token=os.environ["HF_TOKEN"])
    with httpx.Client(
        timeout=120,
        headers={"Authorization": "Bearer " + os.environ["SUPABASE_ACCESS_TOKEN"]},
    ) as client:
        deploy(
            args.namespace + "/" + args.space,
            args.supabase_url,
            api,
            client,
            files,
            os.getenv("TRACEPAPER_PASSWORD"),
        )


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        print(
            "Deployment stopped ("
            + type(error).__name__
            + (f", HTTP {status}" if status else "")
            + "). Check credentials, project access, and provider status; no secret values are included in this output."
        )
        raise SystemExit(1) from None
