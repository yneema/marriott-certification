# Simplify VMS -> Google Drive automation

Logs into `marriott.simplifyvmsapp.com`, opens the "Active Assignments Details - Vendor"
Sigma report, selects **All** assignment statuses (Open + Closed + Cancelled), downloads
the `.xlsx`, and uploads it to a Google Drive Shared Drive.

Runs headless via Playwright + Chromium, designed to run on a schedule (e.g. Replit
Scheduled Deployments).

## What it does

1. Logs in with `SIMPLIFY_EMAIL` / `SIMPLIFY_PASSWORD`.
2. Opens the report, opens the **Assignment Status** filter, and ticks **All**.
3. A network interceptor also forces `Open + Closed + Cancelled` at the request layer
   as a safety net.
4. Downloads the report and uploads it to Google Drive as
   `simplify_report_<YYYY-MM-DD>.xlsx`.

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `SIMPLIFY_EMAIL` | yes | Vendor login email |
| `SIMPLIFY_PASSWORD` | yes | Vendor login password |
| `GOOGLE_DRIVE_FOLDER_ID` | no | Target Drive/Shared Drive folder ID. Defaults to the Marriott Shared Drive. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | yes (on Replit) | Full JSON of the service account key, as one value |
| `HEADLESS` | no | `true` (default) on servers; set `0`/`false` locally to watch the browser |

The service account must be a member (Content Manager / Contributor) of the target
Shared Drive, otherwise the upload fails with a permission error.

## Run locally

```bash
pip install -r requirements.txt
python3 -m playwright install chromium   # local only; not needed on Replit (Nix provides Chromium)
export SIMPLIFY_EMAIL=... SIMPLIFY_PASSWORD=... GOOGLE_SERVICE_ACCOUNT_JSON="$(cat key.json)"
python3 simplify_fetch.py
```

## Deploy on Replit

1. Import this repo into Replit (Import code -> GitHub).
2. Add these under **Tools -> Secrets**: `SIMPLIFY_EMAIL`, `SIMPLIFY_PASSWORD`,
   `GOOGLE_SERVICE_ACCOUNT_JSON` (paste the whole key file), optionally
   `GOOGLE_DRIVE_FOLDER_ID`.
3. `pip install -r requirements.txt`, then Run.
4. Schedule it: Deploy -> Scheduled Deployment -> cron (e.g. `0 6 * * *`),
   run command `python3 simplify_fetch.py`.

`.replit` and `replit.nix` configure headless mode and the system Chromium.

