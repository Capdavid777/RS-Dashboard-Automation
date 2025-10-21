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

def _click(scope, selector):
    scope.locator(selector).first.click(timeout=DEF_TIMEOUT)

def _fill(scope, selector, value):
    scope.locator(selector).first.fill(value, timeout=DEF_TIMEOUT)

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
            except PWTimeout:
                continue
            except Exception:
                continue
    return None, None

def _all_visible_text_inputs(page):
    # Find all visible non-password inputs in DOM order (page + iframes)
    frames = [page] + page.frames
    locs = []
    for f in frames:
        try:
            elems = f.locator('input:not([type="password"])').all()
            for e in elems:
                try:
                    if e.is_visible():
                        locs.append((f, e))
                except Exception:
                    continue
        except Exception:
            continue
    return locs

def _do_login(page, company, username, password, headful=False):
    page.goto(SEMPER_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)

    # 1) Company / Property code
    scope_co, co_sel = _find_in_any_frame(page, LOGIN["company_any"])
    if co_sel:
        _fill(scope_co, co_sel, company)
    else:
        # Fallback: first visible text input is company
        text_inputs = _all_visible_text_inputs(page)
        if not text_inputs:
            raise RuntimeError("No visible text inputs found on login page.")
        f0, e0 = text_inputs[0]
        e0.fill(company)

    # 2) Username
    scope_user, user_sel = _find_in_any_frame(page, LOGIN["username_any"])
    if user_sel:
        _fill(scope_user, user_sel, username)
    else:
        # Fallback: second visible text input (after company) is username
        text_inputs = _all_visible_text_inputs(page)
        if len(text_inputs) < 2:
            raise RuntimeError("Username field not found on login page.")
        f1, e1 = text_inputs[1]
        e1.fill(username)

    # 3) Password
    scope_pw, pw_sel = _find_in_any_frame(page, LOGIN["password_any"])
    if not pw_sel:
        raise RuntimeError("Password field not found on login page.")
    _fill(scope_pw, pw_sel, password)

    # Submit
    scope_btn, submit_sel = _find_in_any_frame(page, LOGIN["submit_any"])
    if not submit_sel:
        raise RuntimeError("Login button not found on login page.")
    _click(scope_btn, submit_sel)

    # Wait for the post-login UI
    try:
        page.wait_for_selector(NAV["general_hover"], timeout=DEF_TIMEOUT)
    except PWTimeout:
        page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
        page.wait_for_selector(NAV["general_hover"], timeout=DEF_TIMEOUT)

def download_all_reports(month: str, out_dir: str):
    load_dotenv()
    os.makedirs(out_dir, exist_ok=True)
    start, end = first_last_day(month)

    # Support both correct and earlier env names (just in case)
    company = os.getenv("SEMPER_COMPANY_CODE") or os.getenv("SEM­PER_COMPANY_CODE") or ""
    username = os.getenv("SEMPER_USERNAME")    or os.getenv("SEM­PER_USERNAME") or ""
    password = os.getenv("SEMPER_PASSWORD")    or os.getenv("SEM­PER_PASSWORD") or ""

    files = {}
    headful = os.getenv("HEADFUL", "0") == "1"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headful)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Login
        _do_login(page, company, username, password, headful=headful)

        # Navigate to All Reports
        _click(page, NAV["general_hover"])
        _click(page, NAV["all_reports"])

        # Room Types History & Forecast
        _click(page, REPORTS["room_types_history_forecast"])
        _fill(page, COMMON["from_date"], start)
        _fill(page, COMMON["to_date"], end)
        _click(page, COMMON["generate"])
        try:
            _click(page, COMMON["no_prompt"])
        except Exception:
            pass
        page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
        files["history_forecast"] = _export(page, out_dir, f"{month}-history-forecast")
        _click(page, COMMON["back"])

        # Transactions > User Selected
        _click(page, REPORTS["transactions_user_selected"])
        page.select_option('select[name="DataSelection"]', label="Bank Date")
        _fill(page, COMMON["from_date"], start)
        _fill(page, COMMON["to_date"], end)
        page.select_option('select[name="UserSelection"]', label="Payment Types")
        _click(page, COMMON["generate"])
        try:
            _click(page, COMMON["no_prompt"])
        except Exception:
            pass
        page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
        files["transactions_user_selected"] = _export(page, out_dir, f"{month}-transactions-user-selected")
        _click(page, COMMON["back"])

        # Deposits Applied & Received
        _click(page, REPORTS["deposits_applied_received"])
        _fill(page, COMMON["from_date"], start)
        _fill(page, COMMON["to_date"], end)
        _click(page, COMMON["generate"])
        try:
            _click(page, COMMON["no_prompt"])
        except Exception:
            pass
        page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
        files["deposits_applied_received"] = _export(page, out_dir, f"{month}-deposits-applied-received")
        _click(page, COMMON["back"])

        # Income by Products Monthly (all unchecked; split later)
        _click(page, REPORTS["income_by_products_monthly"])
        _fill(page, COMMON["from_date"], start)
        _fill(page, COMMON["to_date"], end)
        for key in ("cb1","cb2","cb3","cb4"):
            try:
                box = page.locator(CHECKS[key]).first
                if box.is_checked():
                    box.uncheck()
            except Exception:
                pass
        _click(page, COMMON["generate"])
        page.wait_for_selector(COMMON["export_excel"], timeout=DEF_TIMEOUT)
        files["income_by_products_monthly"] = _export(page, out_dir, f"{month}-income-by-products-monthly")
        _click(page, COMMON["back"])

        browser.close()

    return files
