"""
Simplify VMS -> Google Drive downloader.

Logs into marriott.simplifyvmsapp.com, navigates to the
"Active Assignments Details - Vendor" Sigma report, intercepts the
download request to remove the Assignment Status filter (so ALL statuses
are exported: Open + Closed + Cancelled), then uploads the file to
Google Drive.

Required environment variables:
    SIMPLIFY_EMAIL              Vendor login email
    SIMPLIFY_PASSWORD           Vendor login password
    GOOGLE_DRIVE_FOLDER_ID      Target Drive folder ID (not the full URL)
    GOOGLE_SERVICE_ACCOUNT_JSON Full JSON string of the service account key
                                OR leave unset and place the key file at
                                ./marriot-500909-1256558fa03b.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Route

SIMPLIFY_URL = "https://marriott.simplifyvmsapp.com"
REPORT_URL = (
    f"{SIMPLIFY_URL}/Report/EmbeddedReports/ViewWorkbook1"
    "/report_id/b8fc9f41-4b67-44b3-b7d2-43e5c19817fa"
    "/workbookName/Active%2BAssignments%2BDetails%2B-%2BVendor"
    "/myReport/No/memberId/odtfItQSEapfhZsH92MnHwx3CPfcY"
)
SIGMA_DOWNLOAD_URL = "https://aws-api.sigmacomputing.com/api/v2/db/ir/download"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Default target: the Marriott Shared Drive. Used when GOOGLE_DRIVE_FOLDER_ID is unset.
DEFAULT_DRIVE_FOLDER_ID = "0AKKb9XtARP0zUk9PVA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"[ERROR] Environment variable {name!r} is not set.", flush=True)
        sys.exit(1)
    return value


def get_service_account_credentials() -> Credentials:
    json_secret = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if json_secret:
        info = json.loads(json_secret)
        return Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)

    candidates = [
        Path(__file__).parent / "marriot-500909-1256558fa03b.json",
        Path(__file__).parent / "service_account_key.json",
    ]
    for path in candidates:
        if path.exists():
            return Credentials.from_service_account_file(str(path), scopes=DRIVE_SCOPES)

    print("[ERROR] No Google service account credentials found.", flush=True)
    sys.exit(1)


def upload_to_drive(local_path: Path, folder_id: str) -> str:
    print(f"[INFO] Uploading {local_path.name} to Drive folder {folder_id} ...", flush=True)
    creds = get_service_account_credentials()
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    file_name = f"simplify_report_{date.today().isoformat()}.xlsx"
    file_metadata = {"name": file_name, "parents": [folder_id]}
    media = MediaFileUpload(
        str(local_path),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id,name",
        supportsAllDrives=True,
    ).execute()
    file_id = uploaded["id"]
    print(f"[INFO] Uploaded as '{file_name}' (Drive file ID: {file_id})", flush=True)
    return file_id


# ---------------------------------------------------------------------------
# Route interceptor — removes the Assignment Status filter before it hits Sigma
# ---------------------------------------------------------------------------

def patch_download_route(route: Route) -> None:
    """
    Intercepts POST to Sigma's download endpoint and sets
    Assignment-Status to Open+Closed+Cancelled so all rows are exported.
    """
    try:
        body = json.loads(route.request.post_data or "{}")
        output_ir = body.get("outputIR", {})

        # 1. Patch the variables section
        variables = output_ir.get("variables", {})
        if "Assignment-Status" in variables:
            original = variables["Assignment-Status"]["value"]
            variables["Assignment-Status"]["value"] = ["Open", "Closed", "Cancelled"]
            print(f"[INFO] Patched variables: Assignment-Status {original} -> all 3", flush=True)
        else:
            print(f"[WARN] Assignment-Status not found in variables. Keys: {list(variables.keys())}", flush=True)

        # 2. Patch the node filter — hgMrXNZco3 is the Assignment Status column ID
        nodes = output_ir.get("nodes", {})
        print(f"[DEBUG] Node IDs: {list(nodes.keys())}", flush=True)
        for node_id, node in nodes.items():
            filters = node.get("filters", {})
            if "hgMrXNZco3" in filters:
                original_filter = filters["hgMrXNZco3"]
                filters["hgMrXNZco3"] = [
                    {"values": [
                        {"type": "string", "val": "Open"},
                        {"type": "string", "val": "Closed"},
                        {"type": "string", "val": "Cancelled"},
                    ], "type": "include2"}
                ]
                print(f"[INFO] Patched node {node_id} filter: {original_filter} -> all 3 statuses", flush=True)

        route.continue_(post_data=json.dumps(body))
    except Exception as exc:
        print(f"[WARN] Route patch failed ({exc}), continuing unmodified.", flush=True)
        route.continue_()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    email = required_env("SIMPLIFY_EMAIL")
    password = required_env("SIMPLIFY_PASSWORD")
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "").strip() or DEFAULT_DRIVE_FOLDER_ID
    print(f"[INFO] Drive upload target folder: {folder_id}", flush=True)

    # Headless by default (required on servers like Replit that have no display).
    # Set HEADLESS=0/false locally to watch the browser drive itself.
    headless = os.environ.get("HEADLESS", "true").strip().lower() not in ("0", "false", "no")
    slow_mo = int(os.environ.get("SLOW_MO", "0" if headless else "200"))

    launch_kwargs: dict = {"headless": headless, "slow_mo": slow_mo}
    # On Nix/Replit, point Playwright at the system Chromium via this env var.
    exe_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", "").strip()
    if exe_path:
        launch_kwargs["executable_path"] = exe_path
    print(f"[INFO] Launching Chromium (headless={headless}, exe={exe_path or 'bundled'}) ...", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # Register the route interceptor for the Sigma download endpoint
        page.route(SIGMA_DOWNLOAD_URL, patch_download_route)

        # ------------------------------------------------------------------
        # Step 1: Login
        # ------------------------------------------------------------------
        print("[INFO] Opening login page ...", flush=True)
        page.goto(f"{SIMPLIFY_URL}/site/login", wait_until="domcontentloaded", timeout=90_000)

        page.fill("input[type='email'], input[name='_uemail'], input[placeholder*='email' i]", email)
        page.click("button:has-text('Continue'), input[type='submit'][value*='Continue' i]")

        page.wait_for_selector("input[type='password']", timeout=15_000)
        page.fill("input[type='password']", password)
        page.click("button[type='submit'], input[type='submit']")

        try:
            page.wait_for_url(f"{SIMPLIFY_URL}/dashboard**", timeout=20_000)
        except PlaywrightTimeoutError:
            if "/dashboard" not in page.url:
                print(f"[ERROR] Login failed. URL: {page.url}", flush=True)
                browser.close()
                sys.exit(1)
        print(f"[INFO] Logged in.", flush=True)

        # ------------------------------------------------------------------
        # Step 2: Navigate to report
        # ------------------------------------------------------------------
        print("[INFO] Navigating to report ...", flush=True)
        page.goto(REPORT_URL, wait_until="domcontentloaded", timeout=90_000)

        page.wait_for_selector("iframe", timeout=20_000)
        iframe_handle = page.locator("iframe").first.element_handle(timeout=10_000)
        sigma_actual = iframe_handle.content_frame()
        sigma_actual.wait_for_selector("table tr, [class*='row'], [role='row']", timeout=30_000)
        page.wait_for_timeout(3_000)
        print("[INFO] Report loaded.", flush=True)

        # ------------------------------------------------------------------
        # Step 3: Open Filters -> open Assignment Status dropdown -> tick "All"
        # ------------------------------------------------------------------
        print("[INFO] Opening Filters panel ...", flush=True)
        sigma_frame = page.frame_locator("iframe").first
        sigma_actual_frame = page.locator("iframe").first.element_handle(timeout=10_000).content_frame()

        # Open the Filters panel (do NOT linger here)
        sigma_frame.get_by_role("button", name="Filters").click(timeout=15_000)
        sigma_actual_frame.wait_for_selector("text=Assignment Status", timeout=15_000)
        page.wait_for_timeout(3_000)

        # Open the Assignment Status dropdown by clicking its value control
        print("[INFO] Opening Assignment Status dropdown ...", flush=True)
        opened = False
        try:
            # The control shows the current value ("Open"); click it to open the list
            sigma_frame.get_by_text("Open", exact=True).first.click(timeout=8_000)
            opened = True
        except PlaywrightTimeoutError:
            try:
                sigma_frame.get_by_text("Assignment Status", exact=True).first.click(timeout=5_000)
                opened = True
            except PlaywrightTimeoutError:
                print("[WARN] Could not open Assignment Status dropdown.", flush=True)

        # Wait for all options (All / Closed / Open / Cancelled) to load
        print("[INFO] Waiting for status options to load ...", flush=True)
        page.wait_for_timeout(15_000)

        # Tick the "All" checkbox so every status (Open + Closed + Cancelled) is selected.
        # Ticking "All" auto-checks Open, Closed and Cancelled.
        print("[INFO] Selecting 'All' checkbox ...", flush=True)
        selected_all = False
        try:
            sigma_frame.get_by_text("All", exact=True).first.click(timeout=8_000)
            selected_all = True
            print("[INFO] Clicked 'All'.", flush=True)
        except PlaywrightTimeoutError:
            try:
                sigma_frame.get_by_role("checkbox", name="All").first.click(timeout=5_000)
                selected_all = True
                print("[INFO] Clicked 'All' checkbox (role).", flush=True)
            except PlaywrightTimeoutError:
                print("[WARN] Could not click 'All' checkbox; the network patch will still apply.", flush=True)

        page.wait_for_timeout(5_000)

        # Close the Filters panel (no Apply button needed; it auto-applies)
        print("[INFO] Closing Filters panel ...", flush=True)
        try:
            sigma_frame.get_by_role("button", name="Close").click(timeout=5_000)
        except PlaywrightTimeoutError:
            try:
                sigma_frame.locator("[aria-label*='close' i], [aria-label*='dismiss' i]").first.click(timeout=3_000)
            except PlaywrightTimeoutError:
                page.keyboard.press("Escape")

        # Wait for the report to reload with all statuses
        print("[INFO] Waiting for report to reload with all statuses ...", flush=True)
        page.wait_for_timeout(30_000)

        # ------------------------------------------------------------------
        # Step 4: Download
        # ------------------------------------------------------------------
        print("[INFO] Clicking Download ...", flush=True)
        with page.expect_download(timeout=120_000) as download_info:
            try:
                sigma_frame.get_by_role("button", name="Download").click(timeout=10_000)
            except PlaywrightTimeoutError:
                page.get_by_role("button", name="Download").click(timeout=10_000)

        download = download_info.value
        print(f"[INFO] Download complete: {download.suggested_filename}", flush=True)

        # ------------------------------------------------------------------
        # Step 5: Save locally
        # ------------------------------------------------------------------
        out_dir = Path(__file__).parent / "downloads"
        out_dir.mkdir(exist_ok=True)
        dest = out_dir / f"simplify_report_{date.today().isoformat()}.xlsx"
        download.save_as(str(dest))
        print(f"[INFO] Saved: {dest} ({dest.stat().st_size:,} bytes)", flush=True)

        browser.close()

    # ------------------------------------------------------------------
    # Step 6: Upload to Google Drive
    # ------------------------------------------------------------------
    try:
        upload_to_drive(dest, folder_id)
    except Exception as exc:
        print(f"[WARN] Drive upload failed: {exc}", flush=True)
        print(f"[INFO] File saved locally: {dest}", flush=True)

    print("[INFO] Done. All statuses (Open + Closed + Cancelled) included.", flush=True)


if __name__ == "__main__":
    run()
