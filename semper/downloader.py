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
def current_month_range_ddmmyyyy():
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
    try:
        page.evaluate(
            "(el,v)=>{el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}",
            locator, str(text)
        )
    except: pass
    try: page.keyboard.press("Tab")
    except: pass
    page.wait_for_timeout(100)

# ----------------------------
# Login
# ----------------------------
def _do_login(page, venue, username, password, out_dir):
    page.goto(SEMPER_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-load")

    inputs = page.locator('form >> input:not([type="hidden"])').all()
    if len(inputs) < 3:
        inputs = page.locator('input:not([type="hidden"])').all()
    if len(inputs) < 3:
        raise RuntimeError("Login inputs not found")

    v_inp, u_inp = inputs[0], inputs[1]
    p_inp = page.locator('input[type="password"]').first

    _force_type_input(page, v_inp, venue)
    _force_type_input(page, u_inp, username)
    _force_type_input(page, p_inp, password)
    _snapshot(page, out_dir, "after-filling-login")

    btn = page.locator('button:has-text("Login"), input[type="submit"], [value="Login"]').first
    btn.click()
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-login")

# ----------------------------
# Open All Reports
# ----------------------------
def _open_all_reports_via_menu(page, out_dir):
    candidates = [
        'text=All Reports',
        'a:has-text("All Reports")',
        'li:has-text("All Reports")',
        'button:has-text("All Reports")'
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                loc.click(timeout=DEF_TIMEOUT)
                _snapshot(page, out_dir, "after-open-all-reports")
                return
        except: pass
    _snapshot(page, out_dir, "could-not-find-all-reports")
    raise RuntimeError("Could not reach 'All Reports'")

# ----------------------------
# Open “Room Types History and Forecast”
# ----------------------------
def _open_report_room_types(page, out_dir):
    right_pane = page.locator("div.col-md-5.border.shadowbox.table-container").nth(1)
    right_pane.wait_for(state="visible", timeout=DEF_TIMEOUT)

    try:
        hdr = right_pane.get_by_text("History & Forecast", exact=True).first
        hdr.scroll_into_view_if_needed()
        hdr.click()
        page.wait_for_timeout(300)
    except Exception:
        pass

    row_sel = "div.report:has-text('Room Types History and Forecast')"
    row = right_pane.locator(row_sel).first
    if not row.is_visible():
        hdr.click()
        page.wait_for_timeout(300)

    row.scroll_into_view_if_needed()
    try:
        row.dblclick(timeout=DEF_TIMEOUT)
    except Exception:
        page.evaluate(
            "(el)=>{el.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,cancelable:true,view:window}));}", row
        )

    # Wait for modal
    sel_from = 'input[name="fromDate"], input[name="startDate"], input[placeholder*="Start" i], input[placeholder*="From" i]'
    page.wait_for_selector(sel_from, timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-open-room-types-modal")

# ----------------------------
# Fill dates → Generate → Export
# ----------------------------
def _fill_dates_generate_export(page, start_ddmmyyyy, end_ddmmyyyy, out_dir, filename_hint, context):
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
                "(el,v)=>{el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}",
                inp, value
            )
        except: pass
        try: page.keyboard.press("Tab")
        except: pass
        page.wait_for_timeout(100)

    _set_date(date_from_sel, start_ddmmyyyy)
    _set_date(date_to_sel, end_ddmmyyyy)

    # --- Detect popup on Generate ---
    with context.expect_page() as new_pg:
        page.locator(generate_sel).first.click(timeout=DEF_TIMEOUT)
    new_page = new_pg.value
    new_page.wait_for_load_state("domcontentloaded")
    _snapshot(new_page, out_dir, "after-generate-click")

    # Handle “No” if visible
    try:
        new_page.locator(no_sel).first.click(timeout=1500)
    except Exception:
        pass

    # Wait for Export button in new page
    new_page.locator(export_sel).first.wait_for(state="visible", timeout=60000)
    _snapshot(new_page, out_dir, f"{filename_hint}-ready-to-export")

    with new_page.expect_download(timeout=120000) as dl:
        new_page.locator(export_sel).first.click()
    download = dl.value
    dest = os.path.join("outputs", "raw", f"{filename_hint}.xlsx")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    download.save_as(dest)
    print(f"✅ Saved: {dest}")
    return dest

# ----------------------------
# Main Orchestrator
# ----------------------------
def download_all_reports(month: str, out_dir: str):
    load_dotenv()
    os.makedirs(out_dir, exist_ok=True)

    start_ddmmyyyy, end_ddmmyyyy = current_month_range_ddmmyyyy()

    venue    = os.getenv("SEMPER_VENUE_ID") or ""
    username = os.getenv("SEMPER_USERNAME") or ""
    password = os.getenv("SEMPER_PASSWORD") or ""
    headful  = os.getenv("HEADFUL", "0") == "1"
    keep_open = os.getenv("KEEP_OPEN", "0") == "1"
    slowmo_ms = int(os.getenv("SLOWMO_MS", "0"))

    if not venue:
        raise RuntimeError("SEMPER_VENUE_ID is missing")

    files, error = {}, None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful, slow_mo=slowmo_ms if slowmo_ms > 0 else None)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            _do_login(page, venue, username, password, out_dir)
            _open_all_reports_via_menu(page, out_dir)
            _open_report_room_types(page, out_dir)

            files["history_forecast"] = _fill_dates_generate_export(
                page, start_ddmmyyyy, end_ddmmyyyy, out_dir, f"{month}-history-forecast", context
            )

        except Exception as e:
            error = e
            _snapshot(page, out_dir, "error")
            print(f"[ERROR] {e}")
        finally:
            if keep_open:
                print("🟢 KEEP_OPEN=1 — leaving browser open.")
                try: page.wait_for_timeout(3_600_000)
                except: pass
            else:
                try: context.close()
                except: pass
                try: browser.close()
                except: pass
        if error:
            raise error

    return files
