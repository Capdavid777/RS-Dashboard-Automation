# FILE: semper/downloader.py
import os
import calendar
from datetime import date
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError

SEMPER_URL = "https://web-prod.semper-services.com/auth"
DEF_TIMEOUT = 30000  # 30s


# =========================
# Helpers
# =========================
def current_month_range_ddmmyyyy():
    """Return ('01/mm/yyyy', 'last/mm/yyyy') for the current month."""
    today = date.today()
    first = date(today.year, today.month, 1)
    last = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    return first.strftime("%d/%m/%Y"), last.strftime("%d/%m/%Y")


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
    try:
        page.keyboard.press("Control+A")
    except Exception:
        pass
    try:
        locator.fill("")
    except Exception:
        pass
    try:
        locator.type(str(text), delay=28)
    except Exception:
        pass
    # Also drive input via JS to satisfy masked/controlled inputs
    try:
        page.evaluate(
            "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
            locator,
            str(text),
        )
    except Exception:
        pass
    try:
        page.keyboard.press("Tab")
    except Exception:
        pass
    page.wait_for_timeout(90)


# =========================
# Login
# =========================
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
        raise RuntimeError("Login page did not expose 3 inputs.")

    v_inp, u_inp = inputs[0], inputs[1]
    try:
        p_inp = page.locator('input[type="password"]').first
    except Exception:
        p_inp = inputs[2]

    _force_type_input(page, v_inp, venue)
    _force_type_input(page, u_inp, username)
    _force_type_input(page, p_inp, password)
    _snapshot(page, out_dir, "after-filling-login")

    page.locator('button:has-text("Login"), input[type="submit"], [value="Login"]').first.click()
    page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-login")


# =========================
# All Reports
# =========================
def _open_all_reports_via_menu(page, out_dir):
    # Your tenant shows "All Reports" as a top-level item — click it directly if visible.
    candidates = [
        'text=All Reports',
        'a:has-text("All Reports")',
        'li:has-text("All Reports")',
        'button:has-text("All Reports")',
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.is_visible():
                loc.click(timeout=DEF_TIMEOUT)
                page.wait_for_load_state("networkidle", timeout=DEF_TIMEOUT)
                _snapshot(page, out_dir, "after-open-all-reports")
                return
        except Exception:
            pass

    _snapshot(page, out_dir, "could-not-find-all-reports")
    raise RuntimeError("Could not reach 'All Reports'.")


# =========================
# Open the specific report
# =========================
def _open_report_room_types(page, out_dir):
    """
    Open 'Room Types History and Forecast' from the RIGHT panel.
    Right panel = second .table-container; expand 'History & Forecast'; dblclick row.
    """
    right_pane = page.locator("div.col-md-5.border.shadowbox.table-container").nth(1)
    right_pane.wait_for(state="visible", timeout=DEF_TIMEOUT)

    # Expand the section if needed
    try:
        hdr = right_pane.get_by_text("History & Forecast", exact=True).first
        hdr.scroll_into_view_if_needed()
        hdr.click(timeout=DEF_TIMEOUT)
        page.wait_for_timeout(250)
    except Exception:
        pass

    row = right_pane.locator("div.report:has-text('Room Types History and Forecast')").first
    if not row.is_visible():
        try:
            hdr.click(timeout=DEF_TIMEOUT)
            page.wait_for_timeout(250)
        except Exception:
            pass

    row.scroll_into_view_if_needed()
    try:
        row.dblclick(timeout=DEF_TIMEOUT)
    except Exception:
        # Fallback to JS dblclick
        try:
            page.evaluate(
                "(el)=>{el.dispatchEvent(new MouseEvent('dblclick',{bubbles:true,cancelable:true,view:window}));}",
                row,
            )
        except Exception:
            # Final fallback: coordinate dblclick
            box = row.bounding_box()
            if box:
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.mouse.dblclick()

    # Wait for date modal presence
    sel_from = 'input[name="fromDate"], input[name="startDate"], input[placeholder*="Start" i], input[placeholder*="From" i]'
    page.wait_for_selector(sel_from, timeout=DEF_TIMEOUT)
    _snapshot(page, out_dir, "after-open-room-types-modal")


# =========================
# Fill dates → Generate → (new tab OR same tab) → Export
# =========================
def _fill_dates_generate_export(page, context, start_ddmmyyyy, end_ddmmyyyy, out_dir, filename_hint):
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

    # Set both dates (robust)
    def _set_date(selector, value):
        inp = page.locator(selector).first
        inp.wait_for(state="visible", timeout=DEF_TIMEOUT)
        inp.click()
        try:
            page.keyboard.press("Control+A")
        except Exception:
            pass
        try:
            inp.fill("")
        except Exception:
            pass
        try:
            inp.type(value, delay=28)
        except Exception:
            pass
        try:
            page.evaluate(
                "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
                inp,
                value,
            )
        except Exception:
            pass
        try:
            page.keyboard.press("Tab")
        except Exception:
            pass
        page.wait_for_timeout(90)

    _set_date(date_from_sel, start_ddmmyyyy)
    _set_date(date_to_sel, end_ddmmyyyy)

    # Click Generate; if a popup tab opens, switch to it. Otherwise stay on same page.
    target_page = None
    try:
        with context.expect_page(timeout=5000) as pg_evt:
            page.locator(generate_sel).first.click(timeout=DEF_TIMEOUT)
        target_page = pg_evt.value
        target_page.wait_for_load_state("domcontentloaded")
        _snapshot(target_page, out_dir, "after-generate-new-tab")
    except TimeoutError:
        # No popup: report rendered in the same page
        page.wait_for_load_state("domcontentloaded")
        target_page = page
        _snapshot(target_page, out_dir, "after-generate-same-tab")

    # Optional "No" prompt (can be either on modal page or new tab)
    try:
        target_page.locator(no_sel).first.click(timeout=2000)
    except Exception:
        pass

    # Wait for Export To Excel and download
    target_page.locator(export_sel).first.wait_for(state="visible", timeout=60000)
    _snapshot(target_page, out_dir, f"{filename_hint}-ready-to-export")

    with target_page.expect_download(timeout=120000) as dl:
        target_page.locator(export_sel).first.click()
    download = dl.value

    dest = os.path.join("outputs", "raw", f"{filename_hint}.xlsx")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    download.save_as(dest)
    print(f"✅ Saved: {dest}")
    return dest


# =========================
# Orchestrator
# =========================
def download_all_reports(month: str, out_dir: str):
    load_dotenv()
    os.makedirs(out_dir, exist_ok=True)

    # Always use current month for the UI date range
    start_ddmmyyyy, end_ddmmyyyy = current_month_range_ddmmyyyy()

    venue = os.getenv("SEMPER_VENUE_ID") or os.getenv("SEMPER_COMPANY_CODE") or ""
    username = os.getenv("SEMPER_USERNAME") or ""
    password = os.getenv("SEMPER_PASSWORD") or ""
    headful = os.getenv("HEADFUL", "0") == "1"
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
            # Login
            _do_login(page, venue, username, password, out_dir)

            # All Reports
            _open_all_reports_via_menu(page, out_dir)

            # Room Types History & Forecast
            _open_report_room_types(page, out_dir)

            # Dates → Generate → Export
            files["history_forecast"] = _fill_dates_generate_export(
                page, context, start_ddmmyyyy, end_ddmmyyyy, out_dir, f"{month}-history-forecast"
            )

        except Exception as e:
            error = e
            try:
                _snapshot(page, out_dir, "error")
            except Exception:
                pass
            print(f"[ERROR] {e}")

        finally:
            if keep_open:
                print("🟢 KEEP_OPEN=1 — leaving browser open (close it when done).")
                try:
                    page.wait_for_timeout(3_600_000)  # 1 hour
                except Exception:
                    pass
            else:
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass

        if error:
            raise error

    return files
