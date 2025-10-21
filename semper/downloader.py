# FILE: semper/downloader.py
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
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

def _debug_dump(page, out_dir, name):
    try:
        os.makedirs(out_dir, exist_ok=True)
        page.screenshot(path=os.path.join(out_dir, f"{name}.png"), full_page=True)
        with open(os.path.join(out_dir, f"{name}.html"), "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass

def _goto_all_reports(page):
    # Flexible navigation to "All Reports"
    candidates_all_reports = [
        'text="All Reports"', 'text=All Reports', 'a:has-text("All Reports")', 'button:has-text("All Reports")'
    ]
    candidates_reports_menu = [
        'text=Reports', 'a:has-text("Reports")', 'button:has-text("Reports")',
        'text=General', 'a:has-text("General")', 'button:has-text("General")',
    ]
    candidates_menu_button = [
        'button[aria-label*="menu" i]', 'button:has-text("Menu")', '.fa-bars', 'button.burger',
    ]

    for sel in candidates_all_reports:
        try:
            if page.locator(sel).first.is_visible():
                _click(page, sel); return
        except Exception:
            pass

    for mb in candidates_menu_button:
        try:
            if page.locator(mb).first.is_visible():
                _click(page, mb); page.wait_for_timeout(400)
                for sel in candidates_all_reports:
                    try:
                        if page.locator(sel).first.is_visible():
                            _click(page, sel); return
                    except Exception:
                        pass
        except Exception:
            pass

    for parent in candidates_reports_menu:
        try:
            if page.locator(parent).first.is_visible():
                _click(page, parent); page.wait_for_timeout(400)
                for sel in candidates_all_reports:
                    try:
                        if page.locator(sel).first.is_visible():
                            _click(page, sel); return
                    except Exception:
                        pass
        except Exception:
            pass

    frames = [page] + page.frames
    for f in frames:
        try:
            loc = f.locator('text=All Reports').first
            if loc.count() > 0:
                loc.click(timeout=DEF_TIMEOUT); return
        except Exception:
            pass

    raise RuntimeError("Could not find 'All Reports' after login. Update navigation selectors.")

def _force_type_input(page, locator, text):
    """Make absolutely sure a text lands in the input (handles 'controlled' inputs)."""
    locator.wait_for(state="visible", timeout=DEF_TIMEOUT)
    locator.click()
    try:
        page.keyboard.press("Control+A")
    except Exception:
        pass
    try:
        locator.fill("")  # clear if allowed
    except Exception:
        pass
    try:
        locator.type(str(text), delay=40)
    except Exception:
        pass
    # Also set via JS + dispatch input/change
    try:
        page.evaluate(
            "(el, val) => { el.value = val; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
            locator, str(text)
        )
    except Exception:
        pass
    # Tab out to trigger validation
    try:
        page.keyboard.press("Tab")
    except Exception:
        pass
    page.wait_for_timeout(200)

def _do_login(page, venue, username, password, debug=False, out_dir="outputs/raw"):
    page.goto(SEMPER_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)

    # Collect visible inputs (DOM order). Expecting: 0=Venue, 1=Username, 2=Password
    inputs = page.locator('input:not([type="hidden"])').filter(has_not_text="").all()
    if len(inputs) < 3:
        # Try within a <form>
        inputs = page.locator('form >> input:not([type="hidden"])').all()
    if len(inputs) < 3:
        raise RuntimeError(f"Login page did not expose 3 inputs (found {len(inputs)}).")

    v_inp, u_inp, p_inp = inputs[0], inputs[1], None
    # Password: explicit selector (in case DOM order differs)
    try:
        p_inp = page.locator('input[type="password"]').first
    except Exception:
        p_inp = inputs[2]

    # Fill them forcefully
    _force_type_input(page, v_inp, venue)
    _force_type_input(page, u_inp, username)
    _force_type_input(page, p_inp, password)

    if debug:
        _debug_dump(page, out_dir, "after-filling-login")

    # Click the Login button
    btn = page.locator('button:has-text("Login"), input[type="submit"], [value="Login"]').first
    btn.wait_for(state="visible", timeout=DEF_TIMEOUT)
    btn.click()

    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)

def download_all_reports(month: str, out_dir: str):
    load_dotenv()
    os.makedirs(out_dir, exist_ok=True)
    start, end = first_last_day(month)

    # Read creds (Venue ID is required)
    venue    = os.getenv("SEMPER_VENUE_ID") or os.getenv("SEMPER_COMPANY_CODE") or ""
    username = os.getenv("SEMPER_USERNAME") or ""
    password = os.getenv("SEMPER_PASSWORD") or ""
    headful  = os.getenv("HEADFUL", "0") == "1"
    debug    = os.getenv("DEBUG", "0") == "1"

    if not venue:
        raise RuntimeError("SEMPER_VENUE_ID is empty. Set it in your .env")

    files = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Login (index-based, force-typing)
        _do_login(page, venue, username, password, debug=debug, out_dir=out_dir)
        if debug: _debug_dump(page, out_dir, "after-login")

        # Navigate to All Reports
        _goto_all_reports(page)
        if debug: _debug_dump(page, out_dir, "after-open-all-reports")

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
            except Exception:
                pass
        _click(page, COMMON["generate"])
        page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
        files["income_by_products_monthly"] = _export(page, out_dir, f"{month}-income-by-products-monthly")
        _click(page, COMMON["back"])

        browser.close()

    return files
