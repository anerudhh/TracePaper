"""Local SQLite storage and durable Supabase HTTP storage behind one interface."""

import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask


def passages(pages):
    for page, text in enumerate(pages, 1):
        words = text.split()
        for start in range(0, len(words), 180):
            text = " ".join(words[start : start + 230])
            if len(text) >= 30:
                for offset in range(0, len(text), 18000):
                    yield {"page": page, "text": text[offset : offset + 20000]}


class LocalStore:
    hosted = False

    def __init__(self, connection, data):
        self.db, self.data = connection, Path(data)

    def health(self):
        with self.db() as c:
            c.execute("SELECT id FROM papers LIMIT 1").fetchone()

    def get(self, pid):
        with self.db() as c:
            row = c.execute("SELECT * FROM papers WHERE id=?", (pid,)).fetchone()
            return dict(row) if row else None

    def create(self, row):
        with self.db() as c:
            c.execute(
                "INSERT INTO papers(id,name,kind,size,digest,status) VALUES(?,?,?,?,?,'queued') ON CONFLICT(digest) DO NOTHING",
                tuple(row[k] for k in ("id", "name", "kind", "size", "digest")),
            )
            return dict(
                c.execute(
                    "SELECT * FROM papers WHERE digest=?", (row["digest"],)
                ).fetchone()
            )

    def list(self, q, limit, offset):
        with self.db() as c:
            term = "%" + q + "%"
            items = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM papers WHERE name LIKE ? ORDER BY created DESC,id DESC LIMIT ? OFFSET ?",
                    (term, limit, offset),
                )
            ]
            total = c.execute(
                "SELECT count(*) FROM papers WHERE name LIKE ?", (term,)
            ).fetchone()[0]
            stats = dict(
                c.execute(
                    "SELECT count(*) papers,coalesce(sum(pages),0) pages,coalesce(sum(status='ready'),0) ready FROM papers"
                ).fetchone()
            )
        return {"items": items, "total": total, "stats": stats}

    def status(self, pid, status, error=None):
        with self.db() as c:
            c.execute(
                "UPDATE papers SET status=?,error=? WHERE id=?", (status, error, pid)
            )

    def index(self, pid, pages):
        with self.db() as c:
            c.execute("DELETE FROM chunks WHERE paper_id=?", (pid,))
            c.executemany(
                "INSERT INTO chunks(paper_id,page,text) VALUES(?,?,?)",
                ((pid, p["page"], p["text"]) for p in passages(pages)),
            )
            c.execute(
                "UPDATE papers SET status='ready',error=NULL,pages=? WHERE id=?",
                (len(pages), pid),
            )

    def ensure_file(self, row):
        path = self.data / (row["id"] + "." + row["kind"])
        if not path.exists():
            raise HTTPException(404, "Original document is unavailable.")
        return path

    def put_file(self, row, path):
        pass  # The upload was already written to the local data directory.

    def file_response(self, row, request):
        return FileResponse(
            self.ensure_file(row),
            media_type="application/pdf"
            if row["kind"] == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=row["name"],
            content_disposition_type="inline" if row["kind"] == "pdf" else "attachment",
        )

    def delete(self, pid):
        with self.db() as c:
            row = c.execute("SELECT * FROM papers WHERE id=?", (pid,)).fetchone()
            if not row:
                raise HTTPException(404, "Paper not found.")
            if row["status"] in ("queued", "indexing", "uploading"):
                raise HTTPException(409, "Wait for indexing to finish before deleting.")
            c.execute("DELETE FROM papers WHERE id=?", (pid,))
            for h in c.execute("SELECT id,result FROM history").fetchall():
                if any(
                    s["paper_id"] == pid for s in json.loads(h["result"])["sources"]
                ):
                    c.execute("DELETE FROM history WHERE id=?", (h["id"],))
        (self.data / (pid + "." + row["kind"])).unlink(missing_ok=True)
        return {"ok": True}

    def search(self, tokens, paper_ids):
        expression = " OR ".join('"' + t + '"' for t in tokens)
        scope = (
            " AND p.id IN (" + ",".join("?" for _ in paper_ids) + ")"
            if paper_ids
            else ""
        )
        with self.db() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT ch.*,p.name,p.kind,bm25(search) rank FROM search JOIN chunks ch ON ch.id=search.rowid JOIN papers p ON p.id=ch.paper_id WHERE search MATCH ? AND p.status='ready'"
                    + scope
                    + " ORDER BY rank LIMIT 24",
                    [expression, *paper_ids],
                )
            ]

    def save(self, result):
        with self.db() as c:
            c.execute(
                "INSERT INTO history(id,question,result) VALUES(?,?,?)",
                (result["id"], result["question"], json.dumps(result)),
            )

    def history(self):
        with self.db() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT id,question,created FROM history ORDER BY created DESC,rowid DESC LIMIT 50"
                )
            ]

    def answer(self, hid):
        with self.db() as c:
            row = c.execute("SELECT result FROM history WHERE id=?", (hid,)).fetchone()
            return json.loads(row[0]) if row else None


class SupabaseStore:
    hosted = True

    def __init__(self, data):
        self.data = Path(data)
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.url or not key:
            raise RuntimeError(
                "Supabase storage requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
            )
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost")
        ):
            raise RuntimeError(
                "SUPABASE_URL must use HTTPS (loopback HTTP is allowed only for local tests)."
            )
        self.headers = {"apikey": key}
        if not key.startswith("sb_secret_"):
            self.headers["Authorization"] = "Bearer " + key
        self.bucket = os.getenv("SUPABASE_BUCKET", "tracepaper")
        if not self.bucket.replace("-", "").isalnum():
            raise RuntimeError("Invalid SUPABASE_BUCKET identifier.")

    def rpc(self, name, **params):
        try:
            with httpx.Client(timeout=45) as client:
                r = client.post(
                    self.url + "/rest/v1/rpc/tp_" + name,
                    headers=self.headers,
                    json=params,
                )
                r.raise_for_status()
                return r.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(
                503,
                "Hosted storage is unavailable. Check the Supabase project and schema setup.",
            ) from None

    def health(self):
        self.rpc("health")

    def recover(self):
        self.cleanup()
        return self.rpc("recover")

    def get(self, pid):
        return self.rpc("get_paper", p_id=pid)

    def create(self, row):
        return self.rpc("create_paper", p_row=row)

    def list(self, q, limit, offset):
        return self.rpc("list_papers", p_query=q, p_limit=limit, p_offset=offset)

    def status(self, pid, status, error=None):
        self.rpc("set_status", p_id=pid, p_status=status, p_error=error)

    def search(self, tokens, paper_ids):
        return self.rpc("search", p_tokens=tokens, p_paper_ids=paper_ids)

    def save(self, result):
        self.rpc("save_answer", p_result=result)

    def history(self):
        return self.rpc("history")

    def answer(self, hid):
        return self.rpc("answer", p_id=hid)

    def index(self, pid, pages):
        self.rpc("begin_index", p_id=pid)
        batch = []
        for passage in passages(pages):
            batch.append(passage)
            if len(batch) == 20:
                self.rpc("add_chunks", p_id=pid, p_chunks=batch)
                batch = []
        if batch:
            self.rpc("add_chunks", p_id=pid, p_chunks=batch)
        self.rpc("finish_index", p_id=pid, p_pages=len(pages))

    def object_url(self, row):
        return (
            self.url
            + "/storage/v1/object/"
            + self.bucket
            + "/"
            + row["id"]
            + "."
            + row["kind"]
        )

    def put_file(self, row, path):
        try:
            with path.open("rb") as source, httpx.Client(timeout=120) as client:
                r = client.post(
                    self.object_url(row),
                    headers={
                        **self.headers,
                        "Content-Type": "application/pdf"
                        if row["kind"] == "pdf"
                        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "Content-Length": str(path.stat().st_size),
                        "x-upsert": "true",
                    },
                    content=source,
                )
                r.raise_for_status()
        except (httpx.HTTPError, OSError):
            raise HTTPException(
                503,
                "Document upload to hosted storage failed. Remove the failed entry and upload again.",
            ) from None

    def ensure_file(self, row):
        path = self.data / (row["id"] + "." + row["kind"])
        if path.exists():
            return path
        temporary = path.with_suffix(path.suffix + ".download")
        try:
            with (
                httpx.Client(timeout=120) as client,
                client.stream("GET", self.object_url(row), headers=self.headers) as r,
            ):
                r.raise_for_status()
                size = 0
                with temporary.open("wb") as out:
                    for chunk in r.iter_bytes(1024 * 1024):
                        size += len(chunk)
                        if size > 50 * 1024 * 1024:
                            raise ValueError("Oversized object")
                        out.write(chunk)
            temporary.replace(path)
            return path
        except (httpx.HTTPError, OSError, ValueError):
            temporary.unlink(missing_ok=True)
            raise HTTPException(
                503, "Original document could not be retrieved from hosted storage."
            ) from None

    def file_response(self, row, request):
        # Stream ranges directly, avoiding a full object download for every PDF-viewer range.
        client = httpx.Client(timeout=120)
        headers = {**self.headers}
        if request.headers.get("range"):
            headers["Range"] = request.headers["range"]
        try:
            response = client.send(
                client.build_request("GET", self.object_url(row), headers=headers),
                stream=True,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            client.close()
            raise HTTPException(
                503, "Original document could not be retrieved from hosted storage."
            ) from None
        outgoing = {
            k: v
            for k, v in response.headers.items()
            if k.lower() in ("content-range", "content-length", "accept-ranges")
        }
        filename = quote(row["name"], safe="")
        outgoing["Content-Disposition"] = (
            ("inline" if row["kind"] == "pdf" else "attachment")
            + "; filename*=UTF-8''"
            + filename
        )

        def close():
            response.close()
            client.close()

        return StreamingResponse(
            response.iter_bytes(),
            status_code=response.status_code,
            headers=outgoing,
            media_type="application/pdf"
            if row["kind"] == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            background=BackgroundTask(close),
        )

    def cleanup(self):
        pending = self.rpc("deleted_files")
        failed = False
        for row in pending:
            try:
                with httpx.Client(timeout=30) as client:
                    r = client.delete(self.object_url(row), headers=self.headers)
                    if r.status_code not in (200, 204, 404):
                        if not (
                            r.status_code == 400
                            and str(r.json().get("statusCode")) == "404"
                        ):
                            r.raise_for_status()
                self.rpc("ack_delete", p_id=row["id"])
                (self.data / (row["id"] + "." + row["kind"])).unlink(missing_ok=True)
            except (httpx.HTTPError, HTTPException, ValueError):
                failed = True
        return failed

    def delete(self, pid):
        result = self.rpc("delete_paper", p_id=pid)
        if result.get("error") == "missing":
            raise HTTPException(404, "Paper not found.")
        if result.get("error") == "busy":
            raise HTTPException(409, "Wait for indexing to finish before deleting.")
        return {"ok": True, "pending_cleanup": self.cleanup()}
