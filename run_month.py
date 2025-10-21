import os, sys, json, yaml
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

from semper.downloader import download_all_reports
from transforms.pipeline import build_dashboard_json

def resolve_month(cfg_month):
    if cfg_month:
        return cfg_month
    now = datetime.now()
    prev = (now.replace(day=1) - relativedelta(days=1)).strftime("%Y-%m")
    return prev

def main():
    load_dotenv()
    with open("config.yaml", "r") as f:
        cfg = yaml.safe_load(f) or {}

    month = resolve_month(cfg.get("month"))
    vat = float(os.getenv("VAT_RATE", "0.15"))

    paths = cfg.get("paths", {})
    raw_dir = paths.get("raw_dir", "outputs/raw")
    working_dir = paths.get("working_dir", "outputs/working")
    json_dir = paths.get("json_dir", "outputs/json")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(working_dir, exist_ok=True)
    os.makedirs(json_dir, exist_ok=True)

    print(f"Downloading Semper reports for {month} …")
    download_all_reports(month=month, out_dir=raw_dir)

    print("Transforming to dashboard JSON …")
    final_json = build_dashboard_json(
        month=month,
        raw_dir=raw_dir,
        working_dir=working_dir,
        room_type_map=cfg.get("room_type_map", {}),
        extra_income_map=cfg.get("extra_income_map", {}),
        vat_rate=vat,
        targets=cfg.get("targets", {}),
    )

    out_path = os.path.join(json_dir, f"{month}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)
    print(f"Done → {out_path}")

if __name__ == "__main__":
    sys.exit(main())
