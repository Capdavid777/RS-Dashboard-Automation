# FILE: semper/downloader.py
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from .selectors import LOGIN, NAV, REPORTS, COMMON, CHECKS

SEMPER_URL = "https://web-prod.semper-services.com/auth"
DEF_TIMEOUT = 30000  # 30s

def first_last_day(month: str):
    y, m = map(int, month.split("-"))
    start = datetime(y, m, 1)
    end = (start + relativedelta(months=1) - relativedelta(days=1))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def _click(scope, selector): scope.locator(selector).first.click(timeout=DEF_TIMEOUT)
def _fill(scope, selector, value): scope.locator(selector).first.fill(value, timeout=DEF_TIMEOUT)

def _export(page, out_dir, filename_hint):
    with page.expect_download(timeout=60000) as dl_info:
        _click(page, COMMON["export_excel"])
    download = dl_info.value
    path = os.path.join(out_dir, filename_hint + ".xlsx")
    download.save_as(path)
    return path

def _snapshot(page, out_dir, tag):
    try:
        os.makedirs(out_dir, exist_ok=True)
        page.screenshot(path=os.path.join(out_dir, f"{tag}.png"), full_page=True)
        with open(os.path.join(out_dir, f"{tag}.html"), "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"📸 snapshot: {tag}")
    except Exception as e:
        print(f"[WARN] snapshot failed ({tag}): {e}")

def _goto_all_reports(page):
    # Try several routes to “All Reports”
    candidates_all_reports = [
        'text="All Reports"', 'text=All Reports',
        'a:has-text("All Reports")', 'button:has-text("All Reports")'
    ]
    candidates_reports_menu = [
        'text=Reports', 'a:has-text("Reports")', 'button:has-text("Reports")',
        'text=General', 'a:has-text("General")', 'button:has-text("General")'
    ]
    candidates_menu_button = [
        'button[aria-label*="menu" i]', 'button:has-text("Menu")', '.fa-bars', 'button.burger'
    ]

    # Direct
    for sel in candidates_all_reports:
        try:
            if page.locator(sel).first.is_visible():
                _click(page, sel); return
        except Exception: pass

    # Hamburger then All Reports
    for mb in candidates_menu_button:
        try:
            if page.locator(mb).first.is_visible():
                _click(page, mb); page.wait_for_timeout(400)
                for sel in candidates_all_reports:
                    try:
                        if page.locator(sel).first.is_visible():
                            _click(page, sel); return
                    except Exception: pass
        except Exception: pass

    # Click a parent then All Reports
    for parent in candidates_reports_menu:
        try:
            if page.locator(parent).first.is_visible():
                _click(page, parent); page.wait_for_timeout(400)
                for sel in candidates_all_reports:
                    try:
                        if page.locator(sel).first.is_visible():
                            _click(page, sel); return
                    except Exception: pass
        except Exception: pass

    # Search any frame
    frames = [page] + page.frames
    for f in frames:
        try:
            loc = f.locator('text=All Reports').first
            if loc.count() > 0:
                loc.click(timeout=DEF_TIMEOUT); return
        except Exception: pass

    raise RuntimeError("Could not find 'All Reports' after login.")

def _force_type_input(page, locator, text):
    locator.wait_for(state="visible", timeout=DEF_TIMEOUT)
    locator.click()
    try: page.keyboard.press("Control+A")
    except Exception: pass
    try: locator.fill("")
    except Exception: pass
    try: locator.type(str(text), delay=40)
    except Exception: pass
    try:
        page.evaluate(
            "(el, val)=>{el.value=val; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true}));}",
            locator, str(text)
        )
    except Exception: pass
    try: page.keyboard.press("Tab")
    except Exception: pass
    page.wait_for_timeout(150)

def _do_login(page, venue, username, password, out_dir):
    page.goto(SEMPER_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-load")

    # Grab first 3 visible inputs (Venue, Username, Password)
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

    # Click Login
    btn = page.locator('button:has-text("Login"), input[type="submit"], [value="Login"]').first
    btn.wait_for(state="visible", timeout=DEF_TIMEOUT)
    btn.click()
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-login")

def download_all_reports(month: str, out_dir: str):
    load_dotenv()
    os.makedirs(out_dir, exist_ok=True)
    start, end = first_last_day(month)

    venue    = os.getenv("SEMPER_VENUE_ID") or os.getenv("SEMPER_COMPANY_CODE") or ""
    username = os.getenv("SEMPER_USERNAME") or ""
    password = os.getenv("SEMPER_PASSWORD") or ""
    headful  = os.getenv("HEADFUL", "0") == "1"
    debug    = os.getenv("DEBUG", "0") == "1"
    keep_open = os.getenv("KEEP_OPEN", "0") == "1"
    slowmo_ms = int(os.getenv("SLOWMO_MS", "0"))

    if not venue:
        raise RuntimeError("SEMPER_VENUE_ID is empty. Set it in your .env")

    files = {}
    error = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful, slow_mo=slowmo_ms if slowmo_ms > 0 else None)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()

        try:
            # Login
            _do_login(page, venue, username, password, out_dir)

            # Navigate to All Reports
            _goto_all_reports(page)
            page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
            _snapshot(page, out_dir, "after-open-all-reports")

            # ---- Room Types History & Forecast
            _click(page, REPORTS["room_types_history_forecast"])
            _fill(page, COMMON["from_date"], start)
            _fill(page, COMMON["to_date"], end)
            _click(page, COMMON["generate"])
            try: _click(page, COMMON["no_prompt"])
            except Exception: pass
            page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
            files["history_forecast"] = _export(page, out_dir, f"{month}-history-forecast")
            _click(page, COMMON["back"])

            # ---- Transactions > User Selected
            _click(page, REPORTS["transactions_user_selected"])
            page.select_option('select[name="DataSelection"]', label="Bank Date")
            _fill(page, COMMON["from_date"], start)
            _fill(page, COMMON["to_date"], end)
            page.select_option('select[name="UserSelection"]', label="Payment Types")
            _click(page, COMMON["generate"])
            try: _click(page, COMMON["no_prompt"])
            except Exception: pass
            page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
            files["transactions_user_selected"] = _export(page, out_dir, f"{month}-transactions-user-selected")
            _click(page, COMMON["back"])

            # ---- Deposits Applied & Received
            _click(page, REPORTS["deposits_applied_received"])
            _fill(page, COMMON["from_date"], start)
            _fill(page, COMMON["to_date"], end)
            _click(page, COMMON["generate"])
            try: _click(page, COMMON["no_prompt"])
            except Exception: pass
            page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
            files["deposits_applied_received"] = _export(page, out_dir, f"{month}-deposits-applied-received")
            _click(page, COMMON["back"])

            # ---- Income by Products Monthly (all unchecked; split later)
            _click(page, REPORTS["income_by_products_monthly"])
            _fill(page, COMMON["from_date"], start)
            _fill(page, COMMON["to_date"], end)
            for key in ("cb1","cb2","cb3","cb4"):
                try:
                    box = page.locator(CHECKS[key]).first
                    if box.is_checked(): box.uncheck()
                except Exception: pass
            _click(page, COMMON["generate"])
            page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
            files["income_by_products_monthly"] = _export(page, out_dir, f"{month}-income-by-products-monthly")
            _click(page, COMMON["back"])

        except Exception as e:
            error = e
            _snapshot(page, out_dir, "error")
            print(f"[ERROR] {e}")

        finally:
            if keep_open:
                print("🟢 KEEP_OPEN is on. Leaving the browser open for inspection (up to 1 hour).")
                print("Close the window when you’re done.")
                try:
                    page.wait_for_timeout(3_600_000)  # 1 hour
                except Exception:
                    pass
            else:
                try: context.close()
                except Exception: pass
                try: browser.close()
                except Exception: pass

        if error:
            raise error

    return files
