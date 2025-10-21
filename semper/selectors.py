LOGIN = {
  "username": 'input[name="username"], input[type="email"]',
  "password": 'input[name="password"], input[type="password"]',
  "submit":   'button[type="submit"], button:has-text("Login"), input[type="submit"]'
}

NAV = {
  "general_hover": 'text=General',
  "all_reports":   'text=All Reports'
}

REPORTS = {
  "room_types_history_forecast": 'text=Room Types History and Forecast',
  "transactions_user_selected":  'text=User Selected',
  "deposits_applied_received":   'text=Deposits Applied and Received',
  "income_by_products_monthly":  'text=Income by Products Monthly',
}

COMMON = {
  "from_date": 'input[name="fromDate"], input[placeholder*="Start"], input[placeholder*="From"]',
  "to_date":   'input[name="toDate"], input[placeholder*="End"], input[placeholder*="To"]',
  "generate":  'button:has-text("Generate"), input[type="button"][value*="Generate"], input[type="submit"][value*="Generate"]',
  "no_prompt": 'button:has-text("No"), text=No',
  "export_excel": 'text=Export To Excel, a:has-text("Export To Excel"), button:has-text("Export")',
  "back": 'a:has-text("Back"), button:has-text("Back")'
}

CHECKS = {
  "cb1": '(//input[@type="checkbox"])[1]',
  "cb2": '(//input[@type="checkbox"])[2]',
  "cb3": '(//input[@type="checkbox"])[3]',
  "cb4": '(//input[@type="checkbox"])[4]',
}

TRANSACTIONS = {
  "data_selection_bank_date": 'select[name="DataSelection"], option:has-text("Bank Date")',
  "user_selection_payment_types": 'select[name="UserSelection"], option:has-text("Payment Types")',
}

DEPOSITS = {
  "grid_table": "table",
}
