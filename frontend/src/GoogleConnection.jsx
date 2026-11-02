import { useCallback, useEffect, useState } from "react";
import { api } from "./mini-client";

export default function GoogleConnection() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [message, setMessage] = useState("");

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

  useEffect(() => {
    refresh();
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [refresh]);

  async function connect() {
    // The popup must be opened directly from the user's click before any await.
    const popup = window.open("about:blank", "ora-google-consent", "popup,width=640,height=760");
    if (popup) popup.opener = null;
    setBusy(true);
    setMessage("");
    try {
      const result = await api("/google/connect", {});
      if (popup && !popup.closed) popup.location.href = result.url;
      else window.location.assign(result.url);
      setMessage("Google’s consent page opened. Finish there, return here, then refresh the connection status.");
    } catch (error) {
      popup?.close();
      setMessage(error.message || "Could not start Google authorization.");
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
      {!loading && status && !status.configured && (
        <p className="muted">Google Cloud OAuth and server-side token encryption need one-time backend setup before you can connect.</p>
      )}
      {!loading && status && !status.can_manage && (
        <p className="muted">Manage this connection from the web owner session.</p>
      )}
      {!loading && status?.can_manage && (
        <div className="button-row">
          <button className="button primary" type="button" disabled={busy || !status.configured} onClick={connect}>
            {busy ? "Opening consent…" : status.connected ? "Reconnect Google" : "Connect Google"}
          </button>
          {status.connected && <button className="button destructive" type="button" disabled={busy} onClick={disconnect}>Disconnect Google</button>}
          <button className="button quiet" type="button" disabled={busy || loading} onClick={refresh}>Refresh status</button>
        </div>
      )}
      {message && <p className="google-message" role="status" aria-live="polite">{message}</p>}
    </section>
  );
}
