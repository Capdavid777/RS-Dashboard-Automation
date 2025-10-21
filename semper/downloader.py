import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from .selectors import LOGIN, NAV, REPORTS, COMMON, CHECKS

SEMPER_URL = "https://web-prod.semper-services.com/auth"

def first_last_day(month: str):
    y, m = map(int, month.split("-"))
    start = datetime(y, m, 1)
    end = (start + relativedelta(months=1) - relativedelta(days=1))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def _click(page, selector):
    try:
        page.locator(selector).first.click(timeout=8000)
    except:
        page.wait_for_timeout(300)
        page.locator(selector).first.click(timeout=10000)

def _fill(page, selector, value):
    page.locator(selector).first.fill(value, timeout=8000)

def _export(page, out_dir, filename_hint):
    with page.expect_download(timeout=60000) as dl_info:
        _click(page, COMMON["export_excel"])
    download = dl_info.value
    path = os.path.join(out_dir, filename_hint + ".xlsx")
    download.save_as(path)
    return path

def download_all_reports(month: str, out_dir: str):
    load_dotenv()
    os.makedirs(out_dir, exist_ok=True)
    start, end = first_last_day(month)
    username = os.getenv("SEM­PER_USERNAME")
    password = os.getenv("SEM­PER_PASSWORD")

    files = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # Login
        page.goto(SEMPER_URL)
        _fill(page, LOGIN["username"], username)
        _fill(page, LOGIN["password"], password)
        _click(page, LOGIN["submit"])
        page.wait_for_load_state("networkidle")

        # Open All Reports
        _click(page, NAV["general_hover"])
        _click(page, NAV["all_reports"])

        # Room Types History & Forecast
        _click(page, REPORTS["room_types_history_forecast"])
        _fill(page, COMMON["from_date"], start)
        _fill(page, COMMON["to_date"], end)
        _click(page, COMMON["generate"])
        _click(page, COMMON["no_prompt"])
        page.wait_for_selector(COMMON["export_excel"])
        files["history_forecast"] = _export(page, out_dir, f"{month}-history-forecast")
        _click(page, COMMON["back"])

        # Transactions > User Selected
        _click(page, REPORTS["transactions_user_selected"])
        page.select_option('select[name="DataSelection"]', label="Bank Date")
        _fill(page, COMMON["from_date"], start)
        _fill(page, COMMON["to_date"], end)
        page.select_option('select[name="UserSelection"]', label="Payment Types")
        _click(page, COMMON["generate"])
        _click(page, COMMON["no_prompt"])
        page.wait_for_selector(COMMON["export_excel"])
        files["transactions_user_selected"] = _export(page, out_dir, f"{month}-transactions-user-selected")
        _click(page, COMMON["back"])

        # Deposits Applied & Received
        _click(page, REPORTS["deposits_applied_received"])
        _fill(page, COMMON["from_date"], start)
        _fill(page, COMMON["to_date"], end)
        _click(page, COMMON["generate"])
        _click(page, COMMON["no_prompt"])
        page.wait_for_selector(COMMON["export_excel"])
        files["deposits_applied_received"] = _export(page, out_dir, f"{month}-deposits-applied-received")
        _click(page, COMMON["back"])

        # Income by Products Monthly (All unchecked; we split later)
        _click(page, REPORTS["income_by_products_monthly"])
        _fill(page, COMMON["from_date"], start)
        _fill(page, COMMON["to_date"], end)
        for key in ("cb1","cb2","cb3","cb4"):
            try:
                box = page.locator(CHECKS[key]).first
                if box.is_checked():
                    box.uncheck()
            except:
                pass
        _click(page, COMMON["generate"])
        page.wait_for_selector(COMMON["export_excel"])
        files["income_by_products_monthly"] = _export(page, out_dir, f"{month}-income-by-products-monthly")
        _click(page, COMMON["back"])

        browser.close()

    return files
