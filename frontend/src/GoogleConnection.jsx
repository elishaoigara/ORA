import { useCallback, useEffect, useState } from "react";
import { api } from "./mini-client";

export default function GoogleConnection() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const refresh = useCallback(async () => {
    try { setStatus(await api("/google/status")); }
    catch (error) { setMessage(error.message); }
  }, []);
  useEffect(() => {
    refresh();
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [refresh]);

  async function connect() {
    // Open synchronously so browsers do not block the consent window after fetch.
    const popup = window.open("about:blank", "_blank");
    if (popup) popup.opener = null;
    setBusy(true); setMessage("");
    try {
      const result = await api("/google/connect", {});
      if (popup && !popup.closed) popup.location.href = result.url;
      else window.location.assign(result.url);
      setMessage("Finish Google's consent screen, then return here and refresh status.");
    } catch (error) {
      popup?.close(); setMessage(error.message);
    } finally { setBusy(false); }
  }

  async function disconnect() {
    if (!window.confirm("Disconnect Google from ORA? Your Google files and calendar events will stay in your account.")) return;
    setBusy(true); setMessage("");
    try {
      const result = await api("/google/connection", null, "DELETE");
      setMessage(result.message); await refresh();
    } catch (error) { setMessage(error.message); }
    finally { setBusy(false); }
  }

  return <section className="panel settings-panel" style={{ marginBottom: 24 }}>
    <h2>Google Workspace</h2>
    <p>Connect Calendar, Drive, Docs and Sheets. The same connection works with your paired Android app.</p>
    <p className="muted">ORA requests permission to read Drive files and to read or edit your calendars, Docs and Sheets. Changes made through ORA tools require your approval. Gmail is a separate integration.</p>
    <p role="status">{!status ? "Checking connection…" : status.connected
      ? `Connected${status.email ? ` as ${status.email}` : ""}` : "Not connected"}</p>
    {status && !status.configured && <p className="muted">One-time Google Cloud setup is required on the backend before you can connect. See the repository's Google Workspace setup guide.</p>}
    {status?.can_manage && <div className="button-row">
      <button className="button primary" disabled={busy || !status.configured} onClick={connect}>
        {status.connected ? "Reconnect Google" : "Connect Google"}
      </button>
      {status.connected && <button className="button ghost" disabled={busy} onClick={disconnect}>Disconnect Google</button>}
      <button className="text-button" disabled={busy} onClick={refresh}>Refresh status</button>
    </div>}
    {status && !status.can_manage && <p className="muted">Manage this connection from the web owner session.</p>}
    {message && <p role="status" style={{ marginTop: 16 }}>{message}</p>}
    <p className="muted" style={{ marginTop: 16 }}>After connecting, try: “What is on my calendar tomorrow?”, “Find my budget in Google Drive”, or “Create a Google Doc for my project plan”. Review proposed changes in Tools &amp; activity.</p>
  </section>;
}
