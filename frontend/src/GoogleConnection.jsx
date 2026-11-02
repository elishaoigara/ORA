import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./mini-client";

const CHECK_STATE_LABEL = {
  ok: "Ready",
  missing: "Missing on the backend",
  invalid: "Set, but not valid",
};

function RedirectHint({ value }) {
  const [copied, setCopied] = useState(false);
  if (!value) return null;
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="google-setup-redirect">
      <small>Authorized redirect URI to register in Google Cloud Console</small>
      <code>{value}</code>
      <button className="button quiet" type="button" onClick={copy}>
        {copied ? "Copied" : "Copy URI"}
      </button>
    </div>
  );
}

function SetupChecklist({ setup }) {
  if (!setup?.checks?.length) {
    return (
      <p className="muted">
        Google Cloud OAuth and server-side token encryption need one-time backend setup before you can connect.
      </p>
    );
  }
  const failing = setup.checks.filter((check) => check.state !== "ok");
  return (
    <div className="google-setup">
      <p className="muted">
        Google is not connectable yet. The backend reports {failing.length === 1 ? "one setting to fix" : `${failing.length} settings to fix`}:
      </p>
      <ul>
        {setup.checks.map((check) => (
          <li key={check.key} className={check.state === "ok" ? "ok" : "todo"}>
            <div>
              <strong>{check.label}</strong>{" "}
              <code>{check.key}</code>{" "}
              <span className={`status-pill ${check.state === "ok" ? "success" : "warning"}`}>
                {CHECK_STATE_LABEL[check.state] || check.state}
              </span>
              {check.state !== "ok" && <p>{check.hint}</p>}
            </div>
          </li>
        ))}
      </ul>
      <RedirectHint value={setup.expected_redirect_uri || setup.redirect_uri} />
      <p className="muted">
        Set these on the Render backend service, not in Vercel, then redeploy it. Refresh status afterwards.
      </p>
    </div>
  );
}

export default function GoogleConnection() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [message, setMessage] = useState("");
  const [apiChecks, setApiChecks] = useState(null);
  const [waiting, setWaiting] = useState(false);
  const pollRef = useRef(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      setStatus(await api("/google/status"));
    } catch (error) {
      setStatus(null);
      setLoadError(error.message || "Could not check Google connection status.");
    } finally {
      setLoading(false);
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    setWaiting(false);
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener("focus", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      stopPolling();
    };
  }, [refresh, stopPolling]);

  // Consent happens in a separate window. Watch it, so returning to ORA is not
  // required for the panel to notice a successful connection.
  const watchConsent = useCallback(
    (popup) => {
      stopPolling();
      setWaiting(true);
      const started = Date.now();
      pollRef.current = setInterval(async () => {
        if (Date.now() - started > 5 * 60 * 1000) {
          stopPolling();
          return;
        }
        try {
          const next = await api("/google/status");
          setStatus(next);
          if (next.connected) {
            stopPolling();
            setMessage("Google connected. Calendar, Drive, Docs and Sheets tools are now available.");
            try {
              popup?.close();
            } catch {
              /* Cross-origin or already closed; the tab is harmless. */
            }
          } else if (popup?.closed) {
            stopPolling();
          }
        } catch {
          /* Status polling is best-effort; the Refresh status button still works. */
        }
      }, 4000);
    },
    [stopPolling],
  );

  async function connect() {
    // The popup must be opened directly from the user's click before any await.
    const popup = window.open("about:blank", "ora-google-consent", "popup,width=640,height=760");
    if (popup) popup.opener = null;
    setBusy(true);
    setMessage("");
    try {
      const result = await api("/google/connect", {});
      if (popup && !popup.closed) {
        popup.location.href = result.url;
        setMessage("Google’s consent page opened. Approve the requested services there.");
        watchConsent(popup);
      } else {
        window.location.assign(result.url);
        setMessage("Your browser blocked the popup, so this tab is opening Google’s consent page. Finish there, then use the back button and refresh status.");
        return;
      }
    } catch (error) {
      popup?.close();
      setMessage(error.message || "Could not start Google authorization.");
    } finally {
      setBusy(false);
    }
  }

  async function testConnection() {
    setBusy(true);
    setMessage("");
    setApiChecks(null);
    try {
      const result = await api("/google/check");
      setMessage(result.message || (result.ok ? "Google is reachable." : "Google did not answer."));
      setApiChecks(result.apis?.length ? result.apis : null);
      if (result.ok) await refresh();
    } catch (error) {
      setMessage(error.message || "Could not reach Google through the backend.");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect Google Workspace from ORA? ORA will lose this authorization; your Google files and calendar events remain in your Google account.")) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await api("/google/connection", null, "DELETE");
      setMessage(result.message || "Google Workspace disconnected.");
      await refresh();
    } catch (error) {
      setMessage(error.message || "Could not disconnect Google Workspace.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel settings-panel google-connection" aria-labelledby="google-heading">
      <h2 id="google-heading">Google Workspace</h2>
      <p>With your consent, ORA can read Drive files, read calendars, create or update calendar events, and read or edit Google Docs and Sheets. ORA does not connect Gmail here.</p>
      <p className="muted">Changes proposed through ORA tools remain review-gated. You approve each exact operation before it runs.</p>

      {loading && <p role="status">Checking Google connection…</p>}
      {loadError && (
        <div className="global-notice error-notice" role="alert">
          <div><strong>Could not check Google connection</strong><p>{loadError}</p></div>
          <button className="button secondary" type="button" disabled={loading} onClick={refresh}>Retry</button>
        </div>
      )}
      {!loading && status && (
        <p>
          <span className={`status-pill ${status.connected ? "success" : ""}`}>
            {status.connected ? `Connected${status.email ? ` as ${status.email}` : ""}` : "Not connected"}
          </span>
        </p>
      )}
      {!loading && status && !status.configured && <SetupChecklist setup={status.setup} />}
      {!loading && status && !status.can_manage && (
        <p className="muted">Manage this connection from the web owner session.</p>
      )}
      {!loading && status?.can_manage && (
        <div className="button-row">
          <button className="button primary" type="button" disabled={busy || waiting || !status.configured} onClick={connect}>
            {busy ? "Opening consent…" : waiting ? "Waiting for Google…" : status.connected ? "Reconnect Google" : "Connect Google"}
          </button>
          {status.connected && <button className="button secondary" type="button" disabled={busy} onClick={testConnection}>Test connection</button>}
          {status.connected && <button className="button destructive" type="button" disabled={busy} onClick={disconnect}>Disconnect Google</button>}
          <button className="button quiet" type="button" disabled={busy || loading} onClick={refresh}>Refresh status</button>
        </div>
      )}
      {message && <p className="google-message" role="status" aria-live="polite">{message}</p>}
      {apiChecks && (
        <ul className="google-api-checks" aria-label="Google API checks">
          {apiChecks.map((item) => (
            <li key={item.api}>
              <span className={`status-pill ${item.enabled ? "success" : "warning"}`}>
                {item.enabled ? "Enabled" : "Not enabled"}
              </span>
              <span>{item.api}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
