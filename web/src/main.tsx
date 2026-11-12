import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowUpRight,
  ArrowUp,
  Plus,
  Search,
  BookOpen,
  PanelLeftClose,
  FileText,
  X,
  Check,
  ChevronLeft,
  ChevronRight,
  Trash2,
  ArrowDownToLine,
  Loader2,
  LogOut,
  Settings2,
} from "lucide-react";
import "./style.css";
import KeySettings, { type Credential } from "./KeySettings";
type Paper = {
  id: string;
  name: string;
  kind: string;
  pages: number;
  status: string;
  error: string;
  size: number;
};
type Source = {
  id: number;
  paper_id: string;
  name: string;
  kind: string;
  page: number;
  text: string;
  citation: number;
};
type Answer = {
  id: string;
  question: string;
  claims: { text: string; citations: number[] }[];
  sources: Source[];
  mode: string;
  warning: string | null;
  insufficient: boolean;
  latency_ms: number;
  estimated_cost_usd: number | null;
};
type Config = {
  storage: "local" | "supabase";
  requires_user_key: boolean;
  models: Record<string, string>;
  ocr: boolean;
  private: boolean;
};
async function api(path: string, options: RequestInit = {}) {
  const r = await fetch("/api" + path, options);
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: "Request failed." }));
    throw new Error(r.status === 401 ? "AUTH" : e.detail || "Request failed.");
  }
  return r.json();
}
function App() {
  const [tab, setTab] = useState("workspace"),
    [papers, setPapers] = useState<Paper[]>([]),
    [total, setTotal] = useState(0),
    [stats, setStats] = useState({ papers: 0, pages: 0, ready: 0 }),
    [search, setSearch] = useState(""),
    [offset, setOffset] = useState(0),
    [question, setQuestion] = useState(""),
    [answer, setAnswer] = useState<Answer | null>(null),
    [source, setSource] = useState<Source | null>(null),
    [busy, setBusy] = useState(false),
    [uploading, setUploading] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [config, setConfig] = useState<Config | null>(null),
    [history, setHistory] = useState<
      { id: string; question: string; created: string }[]
    >([]),
    [selected, setSelected] = useState<string[]>([]),
    [auth, setAuth] = useState(false),
    [password, setPassword] = useState(""),
    [mobile, setMobile] = useState(false),
    [remove, setRemove] = useState<Paper | null>(null),
    [viewPdf, setViewPdf] = useState(false);
  const [credential, setCredential] = useState<Credential | null>(null),
    [keySettings, setKeySettings] = useState(false);
  const input = useRef<HTMLInputElement>(null),
    composer = useRef<HTMLTextAreaElement>(null);
  const fail = (e: Error) => {
    if (e.message === "AUTH") {
      setAuth(true);
      setCredential(null);
    } else setError(e.message);
  };
  async function refresh() {
    try {
      const d = await api(
        `/papers?q=${encodeURIComponent(search)}&offset=${offset}`,
      );
      setPapers(d.items);
      setTotal(d.total);
      setStats(d.stats);
      setConfig(await api("/config"));
      setHistory(await api("/history"));
    } catch (e) {
      fail(e as Error);
    }
  }
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [search, offset]);
  async function upload(files: FileList | null) {
    if (!files) return;
    setUploading(true);
    setError("");
    let added = 0,
      duplicates = 0;
    for (const f of Array.from(files)) {
      try {
        const data = new FormData();
        data.append("file", f);
        const r = await api("/papers", { method: "POST", body: data });
        if (r.duplicate) duplicates++;
        else added++;
      } catch (e) {
        fail(e as Error);
      }
    }
    setNotice(
      `${added} document${added === 1 ? "" : "s"} queued${duplicates ? ` · ${duplicates} already in library` : ""}`,
    );
    setUploading(false);
    refresh();
    if (input.current) input.current.value = "";
  }
  async function ask(text = question) {
    if (text.trim().length < 3 || busy) return;
    setBusy(true);
    setError("");
    setQuestion(text);
    setSource(null);
    setTab("workspace");
    try {
      const a = await api("/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(credential ? { "X-Provider-Key": credential.key } : {}),
        },
        body: JSON.stringify({
          question: text,
          paper_ids: selected,
          provider: credential?.provider || "gemini",
        }),
      });
      setAnswer(a);
      setSource(a.sources[0] || null);
      setViewPdf(false);
      refresh();
    } catch (e) {
      fail(e as Error);
    } finally {
      setBusy(false);
    }
  }
  async function load(id: string) {
    try {
      const a = await api("/history/" + id);
      setAnswer(a);
      setQuestion(a.question);
      setSource(a.sources[0] || null);
      setTab("workspace");
      setViewPdf(false);
      setMobile(false);
    } catch (e) {
      fail(e as Error);
    }
  }
  function cite(id: number) {
    const s = answer?.sources.find((s) => s.citation === id);
    if (s) {
      setSource(s);
      setViewPdf(false);
    }
  }
  if (auth)
    return (
      <main className="login">
        <div className="brand">
          t<span>p</span>
          <i>TracePaper</i>
        </div>
        <h1>A place for your research.</h1>
        <p>Enter your library password to continue.</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await api("/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ password }),
              });
              setAuth(false);
              setPassword("");
              setError("");
              refresh();
            } catch {
              setError("Incorrect password. Try again.");
            }
          }}
        >
          <input
            aria-label="Library password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button className="primary">
            Open library <ArrowUpRight size={16} />
          </button>
        </form>
        {error && <p role="alert">{error}</p>}
      </main>
    );
  return (
    <div className="app">
      <input
        ref={input}
        type="file"
        accept=".pdf,.docx"
        multiple
        hidden
        onChange={(e) => upload(e.target.files)}
      />
      <aside className={"sidebar " + (mobile ? "open" : "")}>
        <div className="brand">
          t<span>p</span>
          <i>TracePaper</i>
          <button
            className="mobile-only icon"
            aria-label="Close menu"
            onClick={() => setMobile(false)}
          >
            <X size={18} />
          </button>
        </div>
        <div className="library-label">
          PERSONAL LIBRARY <span>01</span>
        </div>
        <nav>
          <button
            className={tab === "workspace" ? "active" : ""}
            onClick={() => {
              setTab("workspace");
              setMobile(false);
            }}
          >
            <BookOpen size={17} /> Research desk <span>↗</span>
          </button>
          <button
            className={tab === "library" ? "active" : ""}
            onClick={() => {
              setTab("library");
              setMobile(false);
            }}
          >
            <FileText size={17} /> All documents <em>{stats.papers}</em>
          </button>
          <button
            className={tab === "insights" ? "active" : ""}
            onClick={() => {
              setTab("insights");
              setMobile(false);
            }}
          >
            <span className="chart-icon">▥</span> Research insights
          </button>
          <button
            onClick={() => {
              setKeySettings(true);
              setMobile(false);
            }}
          >
            <Settings2 size={17} /> Response settings
          </button>
        </nav>
        <button
          className="upload-side"
          onClick={() => input.current?.click()}
          disabled={uploading}
        >
          <Plus size={16} />
          {uploading ? "Uploading…" : "Add documents"}
        </button>
        <div className="recent-label">
          RECENT QUESTIONS{" "}
          <span>{history.length.toString().padStart(2, "0")}</span>
        </div>
        <div className="recent">
          {history.length === 0 ? (
            <p>
              Your research trail starts here.
              <br />
              Questions will be saved as you go.
            </p>
          ) : (
            history.slice(0, 10).map((h) => (
              <button
                key={h.id}
                onClick={() => load(h.id)}
                className={answer?.id === h.id ? "chosen" : ""}
              >
                {h.question}
                <ArrowUpRight size={13} />
              </button>
            ))
          )}
        </div>
        <div className="sidebar-bottom">
          <span className="avatar">R</span>
          <div>
            Your workspace
            <small>
              {config?.private
                ? "Password protected"
                : "Local library · no password"}
            </small>
          </div>
          {config?.private && (
            <button
              className="icon"
              aria-label="Sign out"
              onClick={async () => {
                await api("/logout", { method: "POST" });
                setCredential(null);
                setAuth(true);
              }}
            >
              <LogOut size={16} />
            </button>
          )}
        </div>
      </aside>
      <main className="main">
        <header>
          <div>
            <button
              className="mobile-only icon"
              aria-label="Open menu"
              onClick={() => setMobile(true)}
            >
              <PanelLeftClose size={18} />
            </button>
            <span>Workspace</span>
            <b>/</b>
            {tab === "workspace"
              ? "Research desk"
              : tab === "library"
                ? "All documents"
                : "Research insights"}
          </div>
          <button
            className="system key-control"
            onClick={() => setKeySettings(true)}
          >
            <span className="status-dot" />
            {credential
              ? `${credential.provider === "gemini" ? "Gemini" : "OpenAI"} · your key`
              : "Add API key"}
            <ChevronRight size={12} />
          </button>
        </header>
        {error && (
          <div className="banner error" role="alert">
            {error}
            <button aria-label="Dismiss error" onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        {notice && (
          <div className="banner" role="status">
            {notice}
            <button
              aria-label="Dismiss notification"
              onClick={() => setNotice("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        <div className="content">
          <div className="page-top">
            <div className="eyebrow">YOUR RESEARCH, WITH RECEIPTS.</div>
            <div className="heading-row">
              <h1>
                {tab === "workspace"
                  ? "Follow the evidence."
                  : tab === "library"
                    ? "A library worth exploring."
                    : "Make the work measurable."}
              </h1>
              <span className="edition">TRACEPAPER / WORKSPACE 01</span>
            </div>
            <p>
              {tab === "workspace"
                ? "Ask across your papers. Find an answer you can trace back to the page."
                : tab === "library"
                  ? "Your papers, indexed and ready for a closer look."
                  : "A transparent view of your library, retrieval, and answer generation."}
            </p>
          </div>
          {tab === "workspace" && (
            <>
              <div className="desk-grid">
                <section className="research">
                  <div className="section-label">
                    <span>01 / ASK A QUESTION</span>
                    <span>
                      {selected.length
                        ? `${selected.length} selected`
                        : "Entire library"}
                    </span>
                  </div>
                  <form
                    className="composer"
                    onSubmit={(e) => {
                      e.preventDefault();
                      ask();
                    }}
                  >
                    <textarea
                      ref={composer}
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                          e.preventDefault();
                          ask();
                        }
                      }}
                      maxLength={2000}
                      placeholder="What would you like to understand?"
                      aria-label="Research question"
                    />
                    <div className="composer-bottom">
                      <button
                        type="button"
                        className="scope"
                        onClick={() => setTab("library")}
                      >
                        <FileText size={14} />
                        {selected.length
                          ? `${selected.length} selected papers`
                          : `${stats.ready || 0} indexed papers`}{" "}
                        <ChevronRight size={13} />
                      </button>
                      <button
                        className="submit"
                        aria-label="Ask question"
                        disabled={
                          busy || question.trim().length < 3 || !stats.ready
                        }
                      >
                        {busy ? (
                          <Loader2 className="spin" size={20} />
                        ) : (
                          <ArrowUp size={20} />
                        )}
                      </button>
                    </div>
                  </form>
                  <div className="hint">
                    <span>
                      {credential ? (
                        "Generated answers · using your API key"
                      ) : (
                        <>
                          Extractive mode ·{" "}
                          <button
                            className="inline-key"
                            onClick={() => setKeySettings(true)}
                          >
                            add your key for generated answers
                          </button>
                        </>
                      )}
                    </span>
                    <span>⌘ / Ctrl + Enter</span>
                  </div>
                  {!answer && !busy && (
                    <div className="welcome">
                      <div className="book-mark">
                        <BookOpen size={28} strokeWidth={1} />
                      </div>
                      <h2>Good questions start with good sources.</h2>
                      <p>
                        {stats.ready
                          ? "Your library is ready. Ask a focused question, compare findings, or explore a method."
                          : "Add a few papers to begin. TracePaper keeps the evidence attached, so you can read beyond the answer."}
                      </p>
                      {!stats.ready ? (
                        <button
                          className="primary"
                          onClick={() => input.current?.click()}
                        >
                          <Plus size={16} />
                          Add your first documents
                        </button>
                      ) : (
                        <div className="prompts">
                          {[
                            "What are the main findings and limitations?",
                            "Which methods are used in these papers?",
                            "What evidence supports the conclusions?",
                          ].map((q) => (
                            <button key={q} onClick={() => ask(q)}>
                              {q}
                              <ArrowUpRight size={15} />
                            </button>
                          ))}
                        </div>
                      )}
                      <div className="small-note">
                        PDF & DOCX · Up to 50 MB per file · Stored in your
                        library
                      </div>
                    </div>
                  )}
                  {busy && (
                    <div className="loading" role="status">
                      <Loader2 className="spin" size={22} />
                      <h2>Following the evidence…</h2>
                      <p>
                        Searching your library
                        {credential ? " and composing a cited answer" : ""}.
                      </p>
                    </div>
                  )}
                  {answer && !busy && (
                    <article className="answer">
                      <div className="section-label">
                        <span>
                          02 /{" "}
                          {answer.mode === "generated"
                            ? "GROUNDED ANSWER"
                            : "RETRIEVED EVIDENCE"}
                        </span>
                        <button
                          className="text-button"
                          onClick={() => {
                            const blob = new Blob(
                              [
                                `# ${answer.question}\n\n${answer.claims.map((c) => c.text + " " + c.citations.map((n) => "[" + n + "]").join(" ")).join("\n\n")}\n\n## Sources\n${answer.sources.map((s) => `[${s.citation}] ${s.name}, ${s.kind === "pdf" ? "page" : "section"} ${s.page}\n${s.text}`).join("\n\n")}`,
                              ],
                              { type: "text/markdown" },
                            );
                            const a = document.createElement("a");
                            a.href = URL.createObjectURL(blob);
                            a.download = "tracepaper-notes.md";
                            a.click();
                            URL.revokeObjectURL(a.href);
                          }}
                        >
                          <ArrowDownToLine size={13} /> Export notes
                        </button>
                      </div>
                      <h2>{answer.question}</h2>
                      {answer.warning && (
                        <div className="warning">
                          {answer.warning}{" "}
                          <button
                            className="inline-key"
                            onClick={() => setKeySettings(true)}
                          >
                            Review your key
                          </button>
                        </div>
                      )}
                      {answer.insufficient ? (
                        <div className="empty-answer">
                          <h3>Insufficient evidence.</h3>
                          <p>
                            Your indexed papers don’t provide enough evidence to
                            answer this question. Try a more specific phrase,
                            broaden your document selection, or add relevant
                            papers.
                          </p>
                        </div>
                      ) : (
                        answer.claims.map((c, i) => (
                          <div
                            className={
                              "claim " +
                              (answer.mode === "extractive" ? "excerpt" : "")
                            }
                            key={i}
                          >
                            {answer.mode === "extractive" && (
                              <span className="quote-label">
                                SOURCE EXCERPT
                              </span>
                            )}
                            <p>
                              {c.text}{" "}
                              <span className="citations">
                                {c.citations.map((n) => (
                                  <button
                                    key={n}
                                    onClick={() => cite(n)}
                                    aria-label={`Inspect citation ${n}`}
                                  >
                                    {n}
                                  </button>
                                ))}
                              </span>
                            </p>
                          </div>
                        ))
                      )}
                      <div className="answer-foot">
                        <span>
                          <Check size={13} /> {answer.sources.length} source
                          passages
                        </span>
                        <span>{(answer.latency_ms / 1000).toFixed(2)}s</span>
                        <span>
                          {answer.mode === "extractive"
                            ? "No model cost"
                            : answer.estimated_cost_usd !== null
                              ? `~$${answer.estimated_cost_usd.toFixed(5)}`
                              : "Cost unavailable"}
                        </span>
                      </div>
                      <p className="disclaimer">
                        {answer.mode === "generated"
                          ? "Citations identify retrieved passages. Check the source to verify each claim."
                          : "These are matching passages, not a synthesized answer. Relevance depends on the terms in your question."}
                      </p>
                    </article>
                  )}
                </section>
                <aside className="evidence">
                  <div className="section-label">
                    <span>SOURCE NOTES</span>
                    <span>
                      {source ? String(source.citation).padStart(2, "0") : "—"}
                    </span>
                  </div>
                  {source ? (
                    <>
                      <div className="source-heading">
                        <FileText size={19} />
                        <h3>{source.name}</h3>
                      </div>
                      <div className="source-meta">
                        {source.kind === "pdf" ? "PAGE" : "SECTION"}{" "}
                        {String(source.page).padStart(2, "0")}
                        <span>REFERENCE [{source.citation}]</span>
                      </div>
                      <div className="evidence-tabs">
                        <button
                          className={!viewPdf ? "selected" : ""}
                          onClick={() => setViewPdf(false)}
                        >
                          Passage
                        </button>
                        {source.kind === "pdf" && (
                          <button
                            className={viewPdf ? "selected" : ""}
                            onClick={() => setViewPdf(true)}
                          >
                            Original page
                          </button>
                        )}
                        <a
                          href={`/api/papers/${source.paper_id}/file#page=${source.page}`}
                          target="_blank"
                          rel="noreferrer"
                          aria-label="Open original document"
                        >
                          <ArrowUpRight size={16} />
                        </a>
                      </div>
                      {viewPdf ? (
                        <iframe
                          title="Original PDF page"
                          key={source.paper_id + source.page}
                          src={`/api/papers/${source.paper_id}/file#page=${source.page}&view=FitH`}
                        />
                      ) : (
                        <div className="source-passage">
                          <span className="margin-number">{source.page}</span>
                          <p>{source.text}</p>
                        </div>
                      )}
                      <div className="source-bottom">
                        {source.kind === "pdf"
                          ? "Page numbering follows the uploaded PDF."
                          : "DOCX sections are text groups, not page numbers."}
                      </div>
                      <div className="other-sources">
                        {answer?.sources.map((s) => (
                          <button
                            key={s.id}
                            className={s.id === source.id ? "current" : ""}
                            onClick={() => {
                              setSource(s);
                              setViewPdf(false);
                            }}
                          >
                            <span>
                              {s.citation.toString().padStart(2, "0")}
                            </span>
                            <div>
                              {s.name}
                              <small>
                                {s.kind === "pdf" ? "Page" : "Section"} {s.page}
                              </small>
                            </div>
                            <ChevronRight size={14} />
                          </button>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="evidence-empty">
                      <div className="paper-drawing">
                        <span />
                        <span />
                        <span />
                        <span />
                        <b>↗</b>
                      </div>
                      <h3>The source is part of the answer.</h3>
                      <p>
                        Click a citation to inspect the original passage and its
                        place in the paper.
                      </p>
                      <div className="evidence-key">
                        <span>01</span> Answer <i>→</i>
                        <span>[1]</span> Passage <i>→</i> Page
                      </div>
                    </div>
                  )}
                </aside>
              </div>
              <div className="principles">
                <span>BUILT FOR A CLOSER READ</span>
                <p>Evidence before fluency.</p>
                <p>Page-level provenance.</p>
                <p>Your library, your context.</p>
              </div>
            </>
          )}
          {tab === "library" && (
            <>
              <div className="library-toolbar">
                <label className="search">
                  <Search size={16} />
                  <input
                    placeholder="Search document titles…"
                    aria-label="Search documents"
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setOffset(0);
                    }}
                  />
                </label>
                <button
                  className="primary"
                  disabled={uploading}
                  onClick={() => input.current?.click()}
                >
                  <Plus size={16} />
                  Add documents
                </button>
              </div>
              <div className="table-caption">
                <span>
                  {total} documents · {selected.length} selected for questions
                </span>
                {selected.length > 0 && (
                  <button
                    className="text-button"
                    onClick={() => setSelected([])}
                  >
                    Clear selection
                  </button>
                )}
              </div>
              <div className="document-table">
                <div className="table-head">
                  <span>DOCUMENT</span>
                  <span>EXTENT</span>
                  <span>STATUS</span>
                  <span />
                </div>
                {papers.length === 0 ? (
                  <div className="table-empty">
                    <BookOpen size={28} />
                    <h2>
                      {search
                        ? "No matching titles."
                        : "Every research trail starts somewhere."}
                    </h2>
                    <p>
                      {search
                        ? "Try another search."
                        : "Upload PDF or DOCX documents to build your library."}
                    </p>
                  </div>
                ) : (
                  papers.map((p) => (
                    <div className="document-row" key={p.id}>
                      <div className="document-title">
                        <input
                          type="checkbox"
                          aria-label={`Select ${p.name}`}
                          checked={selected.includes(p.id)}
                          disabled={p.status !== "ready"}
                          onChange={() =>
                            setSelected((s) =>
                              s.includes(p.id)
                                ? s.filter((id) => id !== p.id)
                                : [...s, p.id],
                            )
                          }
                        />
                        <span className="file-type">
                          {p.kind.toUpperCase()}
                        </span>
                        <div>
                          <a
                            href={`/api/papers/${p.id}/file`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {p.name}
                          </a>
                          <small>
                            {(p.size / 1024 / 1024).toFixed(2)} MB
                            {p.error && (
                              <span className="file-error">{p.error}</span>
                            )}
                          </small>
                        </div>
                      </div>
                      <span className="extent">
                        {p.pages || "—"}{" "}
                        {p.kind === "pdf" ? "pages" : "sections"}
                      </span>
                      <span className={"badge " + p.status}>
                        <span className="status-dot" />
                        {p.status}
                      </span>
                      <button
                        className="icon"
                        disabled={["uploading", "queued", "indexing"].includes(
                          p.status,
                        )}
                        aria-label={`Delete ${p.name}`}
                        onClick={() => setRemove(p)}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  ))
                )}
              </div>
              <div className="pagination">
                <button
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 50))}
                >
                  <ChevronLeft size={15} />
                  Previous
                </button>
                <span>
                  {total ? offset + 1 : 0}–{Math.min(offset + 50, total)} of{" "}
                  {total}
                </span>
                <button
                  disabled={offset + 50 >= total}
                  onClick={() => setOffset(offset + 50)}
                >
                  Next
                  <ChevronRight size={15} />
                </button>
              </div>
              {selected.length > 0 && (
                <button
                  className="primary"
                  onClick={() => {
                    setTab("workspace");
                    setTimeout(() => composer.current?.focus(), 0);
                  }}
                >
                  Ask selected documents <ArrowUpRight size={16} />
                </button>
              )}
              <p className="library-note">
                PDFs preserve original pages. DOCX files use numbered text
                sections. Scanned PDFs{" "}
                {config?.ocr
                  ? "use English OCR when text is missing."
                  : "require optional OCR to be enabled on the server."}
              </p>
            </>
          )}
          {tab === "insights" && (
            <>
              <div className="metric-grid">
                {[
                  ["Documents", stats.papers],
                  ["Indexed pages / sections", stats.pages],
                  ["Ready to query", stats.ready || 0],
                  ["Recent questions", history.length],
                ].map(([label, value]) => (
                  <div className="metric" key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
              <section className="method">
                <div className="eyebrow">UNDER THE SURFACE</div>
                <h2>Know what the numbers mean.</h2>
                <div>
                  <h3>Retrieval</h3>
                  <p>
                    {config?.storage === "supabase"
                      ? "PostgreSQL full-text search with relevance ranking"
                      : "SQLite FTS5 with BM25 ranking"}
                    , word stemming, overlapping passages, and up to six
                    distinct source pages. Search stays on disk; it does not
                    scan the full library into memory. Semantic embedding
                    retrieval is not yet included.
                  </p>
                </div>
                <div>
                  <h3>Citation integrity</h3>
                  <p>
                    Generated claims must reference valid retrieved passage IDs.
                    This checks reference validity, not whether the passage
                    entails the claim. Human review is still needed to judge
                    citation correctness.
                  </p>
                </div>
                <div>
                  <h3>Generation & cost</h3>
                  <p>
                    {credential
                      ? `${credential.provider === "gemini" ? "Gemini" : "OpenAI"} selected with ${config?.models[credential.provider] || "the default model"}. Your key is held only in this tab.`
                      : "Add your own API key in Response settings for generated answers. Without one, you get matching passages without a model call."}{" "}
                    Latency is measured server-side. Gemini token usage is
                    recorded, including thinking tokens when reported. Cost is
                    marked unavailable for Gemini and custom models. Estimates
                    for OpenAI gpt-4.1-mini use $0.40 / million input and $1.60
                    / million output tokens; verify provider pricing.
                  </p>
                </div>
                <div>
                  <h3>Evaluation</h3>
                  <p>
                    The repository includes reproducible retrieval fixtures,
                    ingestion tests, and citation validation tests. No benchmark
                    score or citation accuracy claim is reported without a
                    labeled evaluation dataset.
                  </p>
                </div>
              </section>
            </>
          )}
          <footer>
            <span>TracePaper</span>
            <span>Keep your sources close.</span>
            <span>RESEARCH WORKSPACE / v0.1</span>
          </footer>
        </div>
      </main>
      {keySettings && (
        <KeySettings
          credential={credential}
          onClose={() => setKeySettings(false)}
          onChange={setCredential}
        />
      )}
      {remove && (
        <div className="modal-backdrop">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-title"
          >
            <h2 id="delete-title">Remove this document?</h2>
            <p>{remove.name}</p>
            <p>
              Its indexed passages and saved answers referencing it will also be
              removed.
            </p>
            <div>
              <button autoFocus onClick={() => setRemove(null)}>
                Keep document
              </button>
              <button
                className="danger"
                onClick={async () => {
                  try {
                    const deletion = await api("/papers/" + remove.id, {
                      method: "DELETE",
                    });
                    if (deletion.pending_cleanup)
                      setNotice(
                        "Document removed. Hosted file cleanup is pending and will retry on restart.",
                      );
                    setSelected((s) => s.filter((id) => id !== remove.id));
                    setAnswer(null);
                    setSource(null);
                    setRemove(null);
                    refresh();
                  } catch (e) {
                    fail(e as Error);
                    setRemove(null);
                  }
                }}
              >
                Remove document
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
