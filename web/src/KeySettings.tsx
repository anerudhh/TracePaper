import { useEffect, useRef, useState } from "react";
import { X, ArrowUpRight } from "lucide-react";
export type Credential = { provider: "gemini" | "openai"; key: string };
type Props = {
  credential: Credential | null;
  onChange: (value: Credential | null) => void;
  onClose: () => void;
};
export default function KeySettings({ credential, onChange, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [provider, setProvider] = useState<Credential["provider"]>(
    credential?.provider || "gemini",
  );
  // Existing keys never repopulate the settings form; replacing requires a new entry.
  const [key, setKey] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
    return () => dialog.current?.close();
  }, []);
  function close() {
    setKey("");
    onClose();
  }
  return (
    <dialog
      ref={dialog}
      className="key-dialog"
      aria-labelledby="key-title"
      onCancel={close}
    >
      <div className="key-dialog-top">
        <span className="eyebrow">RESPONSE SETTINGS</span>
        <button
          type="button"
          className="icon"
          aria-label="Close response settings"
          onClick={close}
        >
          <X size={18} />
        </button>
      </div>
      <h2 id="key-title">Your research. Your key.</h2>
      <p>
        Use your own provider account for generated, cited answers. Reading and
        searching your documents works without a key.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const value = key.trim();
          if (value.length < 8) return;
          onChange({ provider, key: value });
          close();
        }}
      >
        <label htmlFor="provider">Provider</label>
        <select
          id="provider"
          value={provider}
          onChange={(e) => {
            setProvider(e.target.value as Credential["provider"]);
            setKey("");
          }}
        >
          <option value="gemini">Google Gemini</option>
          <option value="openai">OpenAI</option>
        </select>
        <div className="key-label">
          <label htmlFor="provider-key">
            {provider === "gemini" ? "Gemini" : "OpenAI"} API key
          </label>
          <a
            href={
              provider === "gemini"
                ? "https://aistudio.google.com/api-keys"
                : "https://platform.openai.com/api-keys"
            }
            target="_blank"
            rel="noreferrer"
          >
            Get a key <ArrowUpRight size={12} />
          </a>
        </div>
        <input
          id="provider-key"
          autoFocus
          type="password"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          value={key}
          minLength={8}
          maxLength={4096}
          onChange={(e) => setKey(e.target.value)}
          placeholder={
            credential ? "Enter a replacement key" : "Paste your API key"
          }
          aria-describedby="key-privacy"
          required
        />
        <div className="key-privacy" id="key-privacy">
          <strong>Only for this tab.</strong>
          <p>
            Your key stays in browser memory and is cleared on refresh or sign
            out. It is sent through TracePaper’s server to{" "}
            {provider === "gemini" ? "Google" : "OpenAI"} only when you request
            an answer. It is not saved in browser storage, documents, or answer
            history.
          </p>
          <p>
            Your question and retrieved passages are sent to the provider. Its
            usage limits and charges apply to your account.
          </p>
        </div>
        {credential && (
          <div className="key-current" role="status">
            {credential.provider === "gemini" ? "Gemini" : "OpenAI"} key is set
            for this tab. Connection is checked when you ask a question.
          </div>
        )}
        <div className="key-actions">
          {credential ? (
            <button
              type="button"
              className="remove-key"
              onClick={() => {
                onChange(null);
                close();
              }}
            >
              Remove key
            </button>
          ) : (
            <button type="button" onClick={close}>
              Continue without a key
            </button>
          )}
          <button
            className="primary"
            type="submit"
            disabled={key.trim().length < 8}
          >
            Use key for this tab
          </button>
        </div>
      </form>
    </dialog>
  );
}
