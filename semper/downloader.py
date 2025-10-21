# FILE: semper/downloader.py
import os
import calendar
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError

SEMPER_URL = "https://web-prod.semper-services.com/auth"
DEF_TIMEOUT = 30000  # 30s

# ----------------------------
# Date helpers
# ----------------------------
def first_last_day(month: str):
    """Keeps YYYY-MM-DD if you still call with a specific 'YYYY-MM' elsewhere."""
    y, m = map(int, month.split("-"))
    start = datetime(y, m, 1)
    end = (start + relativedelta(months=1) - relativedelta(days=1))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def current_month_range_ddmmyyyy():
    """Returns ('01/mm/yyyy', 'last/mm/yyyy') as strings (dd/mm/yyyy)."""
    today = date.today()
    first = date(today.year, today.month, 1)
    last = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    return first.strftime("%d/%m/%Y"), last.strftime("%d/%m/%Y")

# ----------------------------
# Utility
# ----------------------------
def _snapshot(page, out_dir, tag):
    try:
        os.makedirs(out_dir, exist_ok=True)
        page.screenshot(path=os.path.join(out_dir, f"{tag}.png"), full_page=True)
        with open(os.path.join(out_dir, f"{tag}.html"), "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"📸 {tag}")
    except Exception as e:
        print(f"[WARN] snapshot {tag} failed: {e}")

def _force_type_input(page, locator, text):
    locator.wait_for(state="visible", timeout=DEF_TIMEOUT)
    locator.click()
    try: page.keyboard.press("Control+A")
    except: pass
    try: locator.fill("")
    except: pass
    try: locator.type(str(text), delay=30)
    except: pass
    # JS set for masked/controlled inputs
    try:
        page.evaluate(
            "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
            locator, str(text)
        )
    except: pass
    try: page.keyboard.press("Tab")
    except: pass
    page.wait_for_timeout(120)

# ----------------------------
# Login
# ----------------------------
def _do_login(page, venue, username, password, out_dir):
    page.goto(SEMPER_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-load")

    # first 3 visible inputs (Venue, Username, Password)
    inputs = page.locator('form >> input:not([type="hidden"])').all()
    if len(inputs) < 3:
        inputs = page.locator('input:not([type="hidden"])').all()
    if len(inputs) < 3:
        _snapshot(page, out_dir, "missing-inputs")
        raise RuntimeError(f"Login page did not expose 3 inputs (found {len(inputs)}).")

    v_inp, u_inp = inputs[0], inputs[1]
    try:
        p_inp = page.locator('input[type="password"]').first
    except Exception:
        p_inp = inputs[2]

    _force_type_input(page, v_inp, venue)
    _force_type_input(page, u_inp, username)
    _force_type_input(page, p_inp, password)
    _snapshot(page, out_dir, "after-filling-login")

    btn = page.locator('button:has-text("Login"), input[type="submit"], [value="Login"]').first
    btn.wait_for(state="visible", timeout=DEF_TIMEOUT)
    btn.click()
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-login")

# ----------------------------
# Navigate to All Reports
# ----------------------------
def _open_all_reports_via_menu(page, out_dir):
    top_tabs = [
        'text=General','text=Reservations','text=Front Desk','text=Accounting',
        'text=Setup & Admin','text=Calendar View','text=Channel Management'
    ]
    candidates = [
        'text=All Reports','a:has-text("All Reports")','li:has-text("All Reports")','button:has-text("All Reports")'
    ]
    # Already visible?
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                loc.click(timeout=DEF_TIMEOUT)
                _snapshot(page, out_dir, "after-open-all-reports")
                return
        except: pass
    # Hover each tab until the item appears
    for tab in top_tabs:
        try:
            page.locator(tab).first.hover(timeout=DEF_TIMEOUT)
            page.wait_for_timeout(250)
            for sel in candidates:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible():
                        loc.click(timeout=DEF_TIMEOUT)
                        page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
                        _snapshot(page, out_dir, "after-open-all-reports")
                        return
                except: pass
        except: pass
    _snapshot(page, out_dir, "could-not-find-all-reports")
    raise RuntimeError("Could not reach 'All Reports' from the top menu.")

# ----------------------------
# Open the report entry (right pane)
# ----------------------------
def _open_report_room_types(page, out_dir):
    """
    Open 'Room Types History and Forecast' from the RIGHT panel.
    The right panel is the second .table-container on the page.
    Expand 'History & Forecast', then dblclick the row.
    """
    right_pane = page.locator("div.col-md-5.border.shadowbox.table-container").nth(1)
    right_pane.wait_for(state="visible", timeout=DEF_TIMEOUT)

    # Expand 'History & Forecast' header (toggle collapse)
    try:
        hdr = right_pane.get_by_text("History & Forecast", exact=True).first
        hdr.scroll_into_view_if_needed()
        hdr.click(timeout=DEF_TIMEOUT)
        page.wait_for_timeout(300)
    except Exception:
        pass  # might already be open

    row_sel = "div.report:has-text('Room Types History and Forecast')"
    row = right_pane.locator(row_sel).first

    if not row.is_visible():
        try:
            hdr = right_pane.get_by_text("History & Forecast", exact=True).first
            hdr.click(timeout=DEF_TIMEOUT)
            page.wait_for_timeout(300)
        except Exception:
            pass

    row.scroll_into_view_if_needed()
    try:
        row.dblclick(timeout=DEF_TIMEOUT)
    except Exception:
        try:
            page.evaluate(
                "(el)=>{el.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,cancelable:true,view:window}));}",
                row
            )
        except Exception:
            box = row.bounding_box()
            if box:
                page.mouse.move(box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                page.mouse.dblclick()

    # Wait until date modal is present
    sel_from = 'input[name="fromDate"], input[name="startDate"], input[placeholder*="Start" i], input[placeholder*="From" i]'
    page.wait_for_selector(sel_from, timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-open-room-types-modal")

# ----------------------------
# Fill dates → Generate → Export
# ----------------------------
def _fill_dates_generate_export(page, start_ddmmyyyy, end_ddmmyyyy, out_dir, filename_hint):
    date_from_sel = (
        'input[name="fromDate"], input[name="startDate"], '
        'input[placeholder*="start" i], input[placeholder*="from" i]'
    )
    date_to_sel = (
        'input[name="toDate"], input[name="endDate"], '
        'input[placeholder*="end" i], input[placeholder*="to" i]'
    )
    generate_sel = (
        'button:has-text("Generate"), '
        'input[type="submit"][value*="Generate"], '
        'input[type="button"][value*="Generate"]'
    )
    no_sel = 'button:has-text("No"), text=No'
    export_sel = (
        'text=Export To Excel, a:has-text("Export To Excel"), '
        'button:has-text("Export To Excel"), button:has-text("Export")'
    )

    def _set_date(selector, value):
        inp = page.locator(selector).first
        inp.wait_for(state="visible", timeout=DEF_TIMEOUT)
        inp.click()
        try: page.keyboard.press("Control+A")
        except: pass
        try: inp.fill("")
        except: pass
        try: inp.type(value, delay=30)
        except: pass
        try:
            page.evaluate(
                "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
                inp, value
            )
        except: pass
        try: page.keyboard.press("Tab")
        except: pass
        page.wait_for_timeout(120)

    # Fill dd/mm/yyyy
    _set_date(date_from_sel, start_ddmmyyyy)
    _set_date(date_to_sel,   end_ddmmyyyy)

    # Generate
    page.locator(generate_sel).first.click(timeout=DEF_TIMEOUT)
    page.wait_for_timeout(300)

    # Optional "No" confirmation
    try:
        page.locator(no_sel).first.click(timeout=1500)
    except Exception:
        pass

    # Export
    page.locator(export_sel).first.wait_for(state="visible", timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, f"{filename_hint}-ready-to-export")
    with page.expect_download(timeout=120000) as dl:
        page.locator(export_sel).first.click()
    download = dl.value
    dest = os.path.join("outputs", "raw", f"{filename_hint}.xlsx")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    download.save_as(dest)
    print(f"✅ Saved: {dest}")
    return dest

# ----------------------------
# Orchestrator
# ----------------------------
def download_all_reports(month: str, out_dir: str):
    load_dotenv()
    os.makedirs(out_dir, exist_ok=True)

    # Use current month (dd/mm/yyyy) for UI filling
    start_ddmmyyyy, end_ddmmyyyy = current_month_range_ddmmyyyy()

    venue    = os.getenv("SEMPER_VENUE_ID") or os.getenv("SEMPER_COMPANY_CODE") or ""
    username = os.getenv("SEMPER_USERNAME") or ""
    password = os.getenv("SEMPER_PASSWORD") or ""
    headful  = os.getenv("HEADFUL", "0") == "1"
    keep_open = os.getenv("KEEP_OPEN", "0") == "1"
    slowmo_ms = int(os.getenv("SLOWMO_MS", "0"))

    if not venue:
        raise RuntimeError("SEMPER_VENUE_ID is empty. Set it in .env")

    files, error = {}, None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful, slow_mo=slowmo_ms if slowmo_ms > 0 else None)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            page.on("console", lambda msg: print("[console]", msg.type, msg.text))

            # 1) Login
            _do_login(page, venue, username, password, out_dir)

            # 2) All Reports
            _open_all_reports_via_menu(page, out_dir)

            # 3) Room Types History & Forecast
            _open_report_room_types(page, out_dir)

            # 4) Dates → Generate → Export (current month)
            files["history_forecast"] = _fill_dates_generate_export(
                page, start_ddmmyyyy, end_ddmmyyyy, out_dir, f"{month}-history-forecast"
            )

            # (We’ll wire the remaining reports next in exactly the same style.)

        except Exception as e:
            error = e
            _snapshot(page, out_dir, "error")
            print(f"[ERROR] {e}")

        finally:
            if keep_open:
                print("🟢 KEEP_OPEN=1 — leaving browser open (close it when done).")
                try: page.wait_for_timeout(3_600_000)  # 1 hour
                except: pass
            else:
                try: context.close()
                except: pass
                try: browser.close()
                except: pass

        if error:
            raise error

    return files
