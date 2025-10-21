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

def _find_in_any_frame(page, selectors):
    frames = [page] + page.frames
    for sel in selectors:
        for f in frames:
            try:
                loc = f.locator(sel).first
                if loc.count() > 0:
                    loc.wait_for(state="attached", timeout=DEF_TIMEOUT)
                    return f, sel
            except Exception:
                continue
    return None, None

def _all_visible_text_inputs(page):
    frames = [page] + page.frames
    locs = []
    for f in frames:
        try:
            for e in f.locator('input:not([type="password"])').all():
                try:
                    if e.is_visible():
                        locs.append((f, e))
                except Exception:
                    pass
        except Exception:
            pass
    return locs

def _do_login(page, venue, username, password):
    page.goto(SEMPER_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)

    # --- VENUE ID (first field) ---
    venue_filled = False
    # 1) Best: placeholder contains "Venue"
    try:
        page.get_by_placeholder("Venue", exact=False).first.fill(str(venue), timeout=DEF_TIMEOUT)
        venue_filled = True
    except Exception:
        pass
    # 2) Fallbacks: attribute contains "venue" or "property" or "company"
    if not venue_filled:
        sel_venue = (
            'input[placeholder*="venue" i], input[id*="venue" i], input[name*="venue" i], '
            'input[placeholder*="property" i], input[id*="property" i], input[name*="property" i], '
            'input[placeholder*="company" i], input[id*="company" i], input[name*="company" i]'
        )
        try:
            v = page.locator(sel_venue).first
            v.wait_for(state="visible", timeout=5000)
            v.click()
            v.fill(str(venue))
            venue_filled = True
        except Exception:
            pass
    # 3) Last resort: first visible non-password input
    if not venue_filled:
        try:
            first_input = page.locator('input:not([type="password"]):not([type="hidden"])').filter(
                has_not_text=""
            ).first
            first_input.wait_for(state="visible", timeout=5000)
            first_input.click()
            first_input.fill(str(venue))
            venue_filled = True
        except Exception:
            pass
    if not venue_filled:
        raise RuntimeError("Could not find/fill the Venue ID field. (Check placeholder/labels.)")

    # --- USERNAME (second field) ---
    user_filled = False
    try:
        # Try common placeholders/labels
        page.get_by_placeholder("User", exact=False).first.fill(username, timeout=3000)
        user_filled = True
    except Exception:
        pass
    if not user_filled:
        try:
            u = page.locator(
                'input[name*="user" i], input[id*="user" i], '
                'input[type="email"], input[placeholder*="email" i], input[placeholder*="user" i]'
            ).first
            u.wait_for(state="visible", timeout=5000)
            u.click()
            u.fill(username)
            user_filled = True
        except Exception:
            pass
    if not user_filled:
        try:
            # assume second visible input is username
            second = page.locator('input:not([type="hidden"])').nth(1)
            second.wait_for(state="visible", timeout=5000)
            second.click()
            second.fill(username)
            user_filled = True
        except Exception:
            pass
    if not user_filled:
        raise RuntimeError("Could not find/fill the Username field.")

    # --- PASSWORD (third field) ---
    pw = page.locator('input[type="password"], input[name*="pass" i], input[id*="pass" i]').first
    pw.wait_for(state="visible", timeout=DEF_TIMEOUT)
    pw.click()
    pw.fill(password)

    # --- SUBMIT ---
    login_btn = page.locator('button:has-text("Login"), input[type="submit"], [value="Login"]').first
    login_btn.wait_for(state="visible", timeout=DEF_TIMEOUT)
    login_btn.click()

    # Wait for navigation after login
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)

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

def download_all_reports(month: str, out_dir: str):
    load_dotenv()
    os.makedirs(out_dir, exist_ok=True)
    start, end = first_last_day(month)

    # ✅ Read Venue ID from .env (fallback to old name if present)
    venue    = os.getenv("SEMPER_VENUE_ID") or os.getenv("SEMPER_COMPANY_CODE") or os.getenv("SEM­PER_COMPANY_CODE") or ""
    username = os.getenv("SEMPER_USERNAME")  or os.getenv("SEM­PER_USERNAME") or ""
    password = os.getenv("SEMPER_PASSWORD")  or os.getenv("SEM­PER_PASSWORD") or ""
    debug    = os.getenv("DEBUG", "0") == "1"
    headful  = os.getenv("HEADFUL", "0") == "1"

    files = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Login with Venue ID
        _do_login(page, venue, username, password)
        page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
        if debug: _debug_dump(page, out_dir, "after-login")

        # Go to All Reports
        _goto_all_reports(page)
        page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
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
