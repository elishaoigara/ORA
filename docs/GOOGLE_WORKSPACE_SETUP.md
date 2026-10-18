# Connect Google Workspace to ORA

Open ORA on the web, then **Connections → Google Workspace → Connect Google**. Sign in to your Google account, grant the requested services, return to ORA and refresh status. The connected account is available to the web app and paired phones through the backend; no new APK is required for the server-provided tools.

## One-time owner setup

1. In https://console.cloud.google.com/ select or create a project.
2. Enable **Google Calendar API, Google Drive API, Google Docs API and Google Sheets API**.
3. In **Google Auth Platform**, configure Branding, Audience and Data Access. For a personal account, select External and add your own Google email as a test user while Testing. Add the scopes listed below. Google may require verification before broader public use; Drive read access is a restricted scope.
4. Under Clients, create an OAuth client of type **Web application**. Set its authorized redirect URI to your actual Render backend URL plus `/api/v2/google/callback`. For the backend currently configured in the Android workflow, this is `https://ora-oovf.onrender.com/api/v2/google/callback`. Confirm the backend URL in Render before saving. This is a backend callback, not the Vercel frontend URL.
5. Set these private environment variables on the Render backend:

   - `GOOGLE_CLIENT_ID`: the web OAuth client ID.
   - `GOOGLE_CLIENT_SECRET`: the web OAuth client secret.
   - `GOOGLE_REDIRECT_URI`: exactly the authorized redirect URI above.
   - `ORA_GOOGLE_TOKEN_KEY`: a Fernet encryption key. Generate once using `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` in an environment with cryptography installed. Keep it stable and private. Changing it requires reconnecting Google.

6. Redeploy the backend, then connect from ORA's web owner session. Do not put these secrets in Vercel frontend variables, the APK, GitHub source, chat, or screenshots.

The OAuth refresh token is obtained automatically and encrypted in the existing workspace database. Ensure Render's existing `DATABASE_URL` is configured for durable storage. No `GOOGLE_REFRESH_TOKEN` is needed for this flow. Legacy Gmail uses its separate environment-token integration and is not included in this consent flow. Calendar now uses the new Workspace connection rather than the legacy manual token.

## Permissions and limits

- `https://www.googleapis.com/auth/userinfo.email`
- `https://www.googleapis.com/auth/calendar.readonly`
- `https://www.googleapis.com/auth/calendar.events`
- `https://www.googleapis.com/auth/drive.readonly`
- `https://www.googleapis.com/auth/documents`
- `https://www.googleapis.com/auth/spreadsheets`

Drive search can find existing files across your Drive. Docs and Sheets scopes permit access to existing files, not just files created by ORA. These scopes are shown on Google's consent screen. This first version requires all listed permissions; it does not implement a Google Picker for per-file access.

Google's External Testing refresh tokens generally expire after seven days for these scopes. Reconnect when required, or configure the production consent application according to Google's verification requirements. Google Workspace administrators can also restrict third-party access.

## Available tools

- Calendar: list events, find free time, propose a new event.
- Drive: search file names and return IDs and links.
- Docs: read, create, and append text. Existing-document appends use Google's revision check.
- Sheets: read bounded A1 ranges, create spreadsheets, and overwrite an explicit range after preview. Use up to 200 rows × 30 columns. All cell inputs are literal values, not formulas. Edits compare the current cells against the preview before writing; Google Sheets does not provide an atomic compare-and-swap here, so avoid concurrent edits during approval.

Use Tools & activity for exact previews and approvals. A file-creation request may leave an empty Doc if its subsequent text insertion fails; check Google before retrying. ORA does not automatically retry ambiguous writes. Reconnecting or disconnecting invalidates previously prepared Google write approvals.

Disconnect removes ORA's stored credentials and attempts to revoke access at Google. It does not delete files, events, or previously saved chat/tool results. If revocation cannot reach Google, remove ORA from https://myaccount.google.com/connections as well.

## Verification

Automated tests mock Google and exercise owner-only management, one-time state, browser binding, cancellation, encrypted persistence, disconnect and stale sheet previews. A real account sign-in requires the owner to configure the client and approve consent; it is not claimed as tested before that happens.

References: https://developers.google.com/identity/protocols/oauth2/web-server and https://developers.google.com/identity/protocols/oauth2/resources/best-practices
