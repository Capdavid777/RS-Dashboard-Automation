# FILE: semper/downloader.py
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

SEMPER_URL = "https://web-prod.semper-services.com/auth"
DEF_TIMEOUT = 30000  # 30s

def first_last_day(month: str):
    y, m = map(int, month.split("-"))
    start = datetime(y, m, 1)
    end = (start + relativedelta(months=1) - relativedelta(days=1))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def _click(scope, selector): scope.locator(selector).first.click(timeout=DEF_TIMEOUT)
def _fill(scope, selector, value): scope.locator(selector).first.fill(value, timeout=DEF_TIMEOUT)

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
    try: locator.type(str(text), delay=40)
    except: pass
    try:
        page.evaluate("(el,v)=>{el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}", locator, str(text))
    except: pass
    try: page.keyboard.press("Tab")
    except: pass
    page.wait_for_timeout(120)

def _do_login(page, venue, username, password, out_dir):
    page.goto(SEMPER_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-load")

    # first 3 inputs (Venue, Username, Password)
    inputs = page.locator('form >> input:not([type="hidden"])').all()
    if len(inputs) < 3:
        inputs = page.locator('input:not([type="hidden"])').all()
    if len(inputs) < 3:
        _snapshot(page, out_dir, "missing-inputs")
        raise RuntimeError(f"Login page did not expose 3 inputs (found {len(inputs)}).")

    v_inp, u_inp = inputs[0], inputs[1]
    try:
        p_inp = page.locator('input[type="password"]').first
    except:
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

def _open_all_reports_via_menu(page, out_dir):
    """Reach All Reports by hovering/clicking top menu only."""
    top_tabs = [
        'text=General', 'text=Reservations', 'text=Front Desk', 'text=Accounting',
        'text=Setup & Admin', 'text=Calendar View', 'text=Channel Management'
    ]
    candidates_all_reports = [
        'text=All Reports', 'a:has-text("All Reports")', 'li:has-text("All Reports")', 'button:has-text("All Reports")'
    ]

    # Already visible?
    for sel in candidates_all_reports:
        try:
            if page.locator(sel).first.is_visible():
                page.locator(sel).first.click(timeout=DEF_TIMEOUT)
                _snapshot(page, out_dir, "after-open-all-reports")
                return
        except: pass

    # Hover each tab until All Reports appears
    for tab in top_tabs:
        try:
            page.locator(tab).first.hover(timeout=DEF_TIMEOUT)
            page.wait_for_timeout(300)
            for sel in candidates_all_reports:
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

def _open_report_by_name(page, name, out_dir):
    """
    On the 'All Reports' screen, double-click a report by its visible text on the RIGHT column.
    If not found, use the search box, then double-click the item in the LEFT list and click 'Add >>' first.
    """
    # 1) Try double-click directly in the right column
    try:
        right_pane = page.locator('div:has-text("History & Forecast")').last
        target = right_pane.get_by_text(name, exact=False).first
        target.scroll_into_view_if_needed()
        target.dblclick(timeout=DEF_TIMEOUT)
        return
    except Exception:
        pass

    # 2) Use the search box to find it in the left list, add to right, then double-click
    try:
        search = page.get_by_placeholder("Search All Reports", exact=False).first
        search.click(); search.fill(""); search.type(name, delay=20)
        page.wait_for_timeout(400)
        left_item = page.locator("div").filter(has_text=name).first
        left_item.scroll_into_view_if_needed()
        left_item.click()
        add_btn = page.get_by_role("button", name="Add >>", exact=False).first
        add_btn.click()
        page.wait_for_timeout(300)
        # Now in the right pane—double-click it
        right_item = page.locator("div").filter(has_text=name).nth(1)
        right_item.scroll_into_view_if_needed()
        right_item.dblclick(timeout=DEF_TIMEOUT)
        return
    except Exception:
        _snapshot(page, out_dir, "report-not-found")
        raise RuntimeError(f"Couldn't open report '{name}'")

def _fill_dates_generate_export(page, start, end, out_dir, filename_hint):
    """
    Handles the standard Semper date modal → Generate → No → Export To Excel.
    Tries multiple input names/placeholders commonly used on Semper reports.
    """
    # Date inputs in the popup
    date_from_sel = (
        'input[name="fromDate"], input[name="startDate"], input[placeholder*="Start" i], input[placeholder*="From" i]'
    )
    date_to_sel = (
        'input[name="toDate"], input[name="endDate"], input[placeholder*="End" i], input[placeholder*="To" i]'
    )
    generate_sel = 'button:has-text("Generate"), input[type="submit"][value*="Generate"], input[type="button"][value*="Generate"]'
    no_sel = 'button:has-text("No"), text=No'
    export_sel = 'text=Export To Excel, a:has-text("Export To Excel"), button:has-text("Export To Excel"), button:has-text("Export")'

    # Fill dates
    page.locator(date_from_sel).first.wait_for(state="visible", timeout=DEF_TIMEOUT)
    _force_type_input(page, page.locator(date_from_sel).first, start)
    _force_type_input(page, page.locator(date_to_sel).first, end)

    # Generate
    page.locator(generate_sel).first.click(timeout=DEF_TIMEOUT)
    page.wait_for_timeout(300)

    # Optional "No" prompt
    try:
        page.locator(no_sel).first.click(timeout=2000)
    except Exception:
        pass

    # Wait for export button
    page.locator(export_sel).first.wait_for(state="visible", timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, f"{filename_hint}-ready-to-export")

    # Download
    with page.expect_download(timeout=120000) as dl_info:
        page.locator(export_sel).first.click()
    download = dl_info.value
    out_path = os.path.join("outputs", "raw", f"{filename_hint}.xlsx")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    download.save_as(out_path)
    print(f"✅ Saved: {out_path}")
    return out_path

def download_all_reports(month: str, out_dir: str):
    load_dotenv()
    os.makedirs(out_dir, exist_ok=True)
    start, end = first_last_day(month)

    venue    = os.getenv("SEMPER_VENUE_ID") or os.getenv("SEMPER_COMPANY_CODE") or ""
    username = os.getenv("SEMPER_USERNAME") or ""
    password = os.getenv("SEMPER_PASSWORD") or ""
    headful  = os.getenv("HEADFUL", "0") == "1"
    keep_open = os.getenv("KEEP_OPEN", "0") == "1"
    slowmo_ms = int(os.getenv("SLOWMO_MS", "0"))

    if not venue:
        raise RuntimeError("SEMPER_VENUE_ID is empty. Set it in .env")

    files = {}
    error = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful, slow_mo=slowmo_ms if slowmo_ms > 0 else None)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            # Login
            _do_login(page, venue, username, password, out_dir)

            # Open "All Reports"
            _open_all_reports_via_menu(page, out_dir)

            # === 1) Room Types History and Forecast ===
            _open_report_by_name(page, "Room Types History and Forecast", out_dir)
            files["history_forecast"] = _fill_dates_generate_export(
                page, start, end, out_dir, f"{month}-history-forecast"
            )

            # (next reports to follow here — we’ll wire them after this succeeds)

        except Exception as e:
            error = e
            _snapshot(page, out_dir, "error")
            print(f"[ERROR] {e}")

        finally:
            if keep_open:
                print("🟢 KEEP_OPEN=1 — leaving browser open (close it when done).")
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
