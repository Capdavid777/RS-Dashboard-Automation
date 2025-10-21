import os, json
from datetime import datetime
import pandas as pd

def _try_load_xlsx(path, **kw):
    return pd.read_excel(path, **kw)

def _excl_vat(value, vat_rate):
    try:
        v = float(value)
    except:
        return 0.0
    return round(v / (1.0 + vat_rate), 2)

def _month_bounds(month: str):
    y, m = map(int, month.split("-"))
    start = pd.Timestamp(y, m, 1)
    end = (start + pd.offsets.MonthEnd(1))
    return start, end

def build_dashboard_json(month, raw_dir, working_dir, room_type_map, extra_income_map, vat_rate, targets):
    start, end = _month_bounds(month)

    hf_path = os.path.join(raw_dir, f"{month}-history-forecast.xlsx")
    tx_path = os.path.join(raw_dir, f"{month}-transactions-user-selected.xlsx")
    dep_path = os.path.join(raw_dir, f"{month}-deposits-applied-received.xlsx")
    ip_path  = os.path.join(raw_dir, f"{month}-income-by-products-monthly.xlsx")

    hf = _try_load_xlsx(hf_path, header=None)
    tx = _try_load_xlsx(tx_path)
    dep = _try_load_xlsx(dep_path)
    ip  = _try_load_xlsx(ip_path)

    # History section
    hist_row_idx = hf[ hf.apply(lambda r: r.astype(str).str.contains("History", case=False, na=False).any(), axis=1) ].index
    daily_rows = []
    if len(hist_row_idx):
        start_i = hist_row_idx[0] + 1
        tmp = hf.iloc[start_i:start_i+62, :3].dropna(how="all")
        tmp.columns = ["Date","Sold Rooms","Out Of Service"]
        tmp = tmp[tmp["Date"].astype(str).str.contains(r"\d{4}-\d{2}-\d{2}")]
        tmp["Date"] = pd.to_datetime(tmp["Date"])
        tmp = tmp[(tmp["Date"]>=start)&(tmp["Date"]<=end)]
        tmp["Sold Rooms"] = pd.to_numeric(tmp["Sold Rooms"], errors="coerce").fillna(0).astype(int)
        tmp["Out Of Service"] = pd.to_numeric(tmp["Out Of Service"], errors="coerce").fillna(0).astype(int)
        daily_rows = tmp.to_dict(orient="records")

    # Transactions: sum numeric
    tx_numeric = tx.select_dtypes(include=["number"])
    bank_income_incl = float(tx_numeric.sum().sum()) if not tx_numeric.empty else 0.0
    bank_income_excl = _excl_vat(bank_income_incl, vat_rate)

    # Deposits: previous-month bank dates
    dep["Bank date"] = pd.to_datetime(dep.get("Bank date") or dep.get("Bank Date") or dep.iloc[:,0], errors="coerce")
    dep["Amount"] = pd.to_numeric(dep.get("Amount") or dep.iloc[:, -1], errors="coerce").fillna(0.0)
    prev_month_mask = dep["Bank date"] < start
    prev_month_deposits_incl = float(dep.loc[prev_month_mask, "Amount"].sum())
    prev_month_deposits_excl = _excl_vat(prev_month_deposits_incl, vat_rate)

    # Income by Products → room types + extras
    ip_cols = {c.lower(): c for c in ip.columns}
    name_col = ip_cols.get("product") or ip_cols.get("type") or list(ip.columns)[0]
    sold_col = None
    for key in ["No. of Accom Rooms Sold", "Rooms Sold", "No. of Rooms Sold", "No. of rooms sold"]:
        if key in ip.columns:
            sold_col = key
            break
    revenue_col = None
    for key in ["Charges (Sales) - (Selected by effective date)", "Charges (Sales)", "Charges"]:
        if key in ip.columns:
            revenue_col = key
            break
    ip[name_col] = ip[name_col].astype(str)

    room_types = {}
    for dash_type, product_aliases in room_type_map.items():
        mask = False
        for alias in product_aliases:
            mask = mask | ip[name_col].str.contains(alias, case=False, na=False)
        block = ip[mask].copy()
        rooms_sold = int(pd.to_numeric(block.get(sold_col), errors="coerce").fillna(0).sum()) if sold_col else 0
        rev_incl = float(pd.to_numeric(block.get(revenue_col), errors="coerce").fillna(0).sum()) if revenue_col else 0.0
        rev_excl = _excl_vat(rev_incl, vat_rate)
        arr = round(rev_excl / rooms_sold, 2) if rooms_sold else 0.0
        room_types[dash_type] = {
            "rooms_sold": rooms_sold,
            "net_revenue": rev_excl,
            "arr": arr
        }

    extras = {}
    for dash_key, aliases in extra_income_map.items():
        mask = False
        for alias in aliases:
            mask = mask | ip[name_col].str.contains(alias, case=False, na=False)
        block = ip[mask].copy()
        rev_incl = float(pd.to_numeric(block.get(revenue_col), errors="coerce").fillna(0).sum()) if revenue_col else 0.0
        extras[dash_key] = _excl_vat(rev_incl, vat_rate)

    room_sum_revenue = sum(v["net_revenue"] for v in room_types.values())
    extra_sum_revenue = sum(extras.values())
    grand_total_revenue = round(room_sum_revenue + extra_sum_revenue, 2)

    json_out = {
        "month": month,
        "overview": {
            "targets": {
                "daily_revenue_target": targets.get("daily_revenue_target", 0),
                "occupancyPct": targets.get("occupancyPct", 0),
                "arrBreakeven": targets.get("arrBreakeven", 0),
            },
            "bank_income_to_date_ex_vat": bank_income_excl,
            "less_deposits_prev_months_ex_vat": prev_month_deposits_excl,
            "net_revenue_rooms_ex_vat": room_sum_revenue,
            "net_extra_income_ex_vat": extra_sum_revenue,
            "total_revenue_ex_vat": grand_total_revenue,
        },
        "daily": [
            {
                "date": r["Date"].strftime("%Y-%m-%d"),
                "sold_rooms": int(r["Sold Rooms"]),
                "oos_rooms": int(r["Out Of Service"])
            } for r in (daily_rows or [])
        ],
        "room_types": [
            {"type": k, **v} for k, v in room_types.items()
        ],
        "extra_income": extras,
        "generated_at": datetime.utcnow().isoformat() + "Z"
    }

    # debugging CSVs
    os.makedirs(working_dir, exist_ok=True)
    pd.DataFrame(json_out.get("daily", [])).to_csv(os.path.join(working_dir, f"{month}-daily.csv"), index=False)
    pd.DataFrame(json_out.get("room_types", [])).to_csv(os.path.join(working_dir, f"{month}-roomtypes.csv"), index=False)
    pd.DataFrame([{"key":k,"value":v} for k,v in extras.items()]).to_csv(os.path.join(working_dir, f"{month}-extras.csv"), index=False)

    return json_out
