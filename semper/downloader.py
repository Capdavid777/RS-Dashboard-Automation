# FILE: semper/downloader.py
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from .selectors import NAV, REPORTS, COMMON, CHECKS

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

def _dump(page, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    page.screenshot(path=os.path.join(out_dir, f"{name}.png"), full_page=True)
    with open(os.path.join(out_dir, f"{name}.html"), "w", encoding="utf-8") as f:
        f.write(page.content())

def _force_type_input(page, locator, text):
    locator.wait_for(state="visible", timeout=DEF_TIMEOUT)
    locator.click()
    try: page.keyboard.press("Control+A")
    except: pass
    try: locator.fill("")     # clear if allowed
    except: pass
    try: locator.type(str(text), delay=30)
    except: pass
    # JS set + events (for controlled inputs)
    try:
        page.evaluate(
            "(el, val)=>{el.value=val;el.dispatchEvent(new Event('input',{bubbles:true}));"
            "el.dispatchEvent(new Event('change',{bubbles:true}));}", locator, str(text)
        )
    except: pass
    try: page.keyboard.press("Tab")
    except: pass
    page.wait_for_timeout(150)

def _do_login(page, venue, username, password, out_dir):
    page.goto(SEMPER_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)

    _dump(page, out_dir, "login-1-at-page-load")

    # Collect visible inputs (expect: 0=Venue ID, 1=Username, 2=Password)
    inputs = page.locator('input:not([type="hidden"])').all()
    visible_inputs = [i for i in inputs if i.is_visible()]
    if len(visible_inputs) < 3:
        # Try within a form as fallback
        inputs = page.locator('form >> input:not([type="hidden"])').all()
        visible_inputs = [i for i in inputs if i.is_visible()]
    if len(visible_inputs) < 3:
        raise RuntimeError(f"Login page did not expose 3 inputs (found {len(visible_inputs)}).")

    v_inp = visible_inputs[0]
    u_inp = visible_inputs[1]
    # Prefer explicit password selector
    try:
        p_inp = page.locator('input[type="password"]').first
        if not p_inp.is_visible():
            p_inp = visible_inputs[2]
    except:
        p_inp = visible_inputs[2]

    # Fill all three fields robustly
    _force_type_input(page, v_inp, venue)
    _force_type_input(page, u_inp, username)
    _force_type_input(page, p_inp, password)

    _dump(page, out_dir, "login-2-after-fill")

    # Click Login
    btn = page.locator('button:has-text("Login"), input[type="submit"], [value="Login"]').first
    btn.wait_for(state="visible", timeout=DEF_TIMEOUT)
    btn.click()

    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)

    _dump(page, out_dir, "login-3-after-click-login")

def _goto_all_reports(page):
    candidates_all_reports = [
        'text="All Reports"', 'text=All Reports',
        'a:has-text("All Reports")', 'button:has-text("All Reports")'
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
        except: pass

    for mb in candidates_menu_button:
        try:
            if page.locator(mb).first.is_visible():
                _click(page, mb); page.wait_for_timeout(400)
                for sel in candidates_all_reports:
                    try:
                        if page.locator(sel).first.is_visible():
                            _click(page, sel); return
                    except: pass
        except: pass

    for parent in candidates_reports_menu:
        try:
            if page.locator(parent).first.is_visible():
                _click(page, parent); page.wait_for_timeout(400)
                for sel in candidates_all_reports:
                    try:
                        if page.locator(sel).first.is_visible():
                            _click(page, sel); return
                    except: pass
        except: pass

    # Try any frame
    for f in [page] + page.frames:
        try:
            loc = f.locator('text=All Reports').first
            if loc.count() > 0:
                loc.click(timeout=DEF_TIMEOUT); return
        except: pass

    raise RuntimeError("Could not find 'All Reports' after login.")

def download_all_reports(month: str, out_dir: str):
    load_dotenv()
    os.makedirs(out_dir, exist_ok=True)
    start, end = first_last_day(month)

    venue    = os.getenv("SEMPER_VENUE_ID") or os.getenv("SEMPER_COMPANY_CODE") or ""
    username = os.getenv("SEMPER_USERNAME") or ""
    password = os.getenv("SEMPER_PASSWORD") or ""
    headful  = os.getenv("HEADFUL", "0") == "1"

    if not venue:
        raise RuntimeError("SEMPER_VENUE_ID is empty. Set it in your .env")

    print(f"[INFO] Raw output folder: {os.path.abspath(out_dir)}")

    files = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Login (always dumps screenshots/HTML)
        _do_login(page, venue, username, password, out_dir)

        # Navigate to All Reports
        _goto_all_reports(page)

        # ---- Room Types History & Forecast
        _click(page, REPORTS["room_types_history_forecast"])
        _fill(page, COMMON["from_date"], start)
        _fill(page, COMMON["to_date"], end)
        _click(page, COMMON["generate"])
        try: _click(page, COMMON["no_prompt"])
        except: pass
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
        except: pass
        page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
        files["transactions_user_selected"] = _export(page, out_dir, f"{month}-transactions-user-selected")
        _click(page, COMMON["back"])

        # ---- Deposits Applied & Received
        _click(page, REPORTS["deposits_applied_received"])
        _fill(page, COMMON["from_date"], start)
        _fill(page, COMMON["to_date"], end)
        _click(page, COMMON["generate"])
        try: _click(page, COMMON["no_prompt"])
        except: pass
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
            except: pass
        _click(page, COMMON["generate"])
        page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
        files["income_by_products_monthly"] = _export(page, out_dir, f"{month}-income-by-products-monthly")
        _click(page, COMMON["back"])

        browser.close()

    return files
