# Semper → Dashboard Automation

## Quick Start
1) Copy `.env.example` to `.env` and fill your Semper credentials.
2) (Optional) Set the month in `config.yaml` as `YYYY-MM` or leave blank to use the previous month automatically.
3) Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   . .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python -m playwright install chromium
   ```
4) Run:
   ```bash
   python run_month.py
   ```
5) Output JSON will be in `outputs/json/<YYYY-MM>.json`.
