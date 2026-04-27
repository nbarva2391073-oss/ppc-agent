# ============================================================
# PPC AGENT v2 — КОНФІГУРАЦІЯ
# ============================================================
import os

# --- Google Sheets ---
SPREADSHEET_ID = "1yDQzK8EpOhyMFxRnKYCT41SXUBIES9wsZ_7jqxy9qLM"

# --- Amazon Ads API ---
ADS_CLIENT_ID     = os.environ.get("ADS_CLIENT_ID")
ADS_CLIENT_SECRET = os.environ.get("ADS_CLIENT_SECRET")
ADS_REFRESH_TOKEN = os.environ.get("ADS_REFRESH_TOKEN")

# Profile IDs для кожного маркетплейсу
ADS_PROFILE_ID_USA = os.environ.get("ADS_PROFILE_ID_USA")
ADS_PROFILE_ID_CA  = os.environ.get("ADS_PROFILE_ID_CA")

# --- Amazon SP-API ---
AMAZON_CLIENT_ID          = os.environ.get("AMAZON_CLIENT_ID")
AMAZON_CLIENT_SECRET      = os.environ.get("AMAZON_CLIENT_SECRET")
AMAZON_REFRESH_TOKEN_USA  = os.environ.get("AMAZON_REFRESH_TOKEN_USA")
AMAZON_REFRESH_TOKEN_CA   = os.environ.get("AMAZON_REFRESH_TOKEN_CA")

MARKETPLACE_IDS = {
    "USA": "ATVPDKIKX0DER",
    "CA":  "A2EUQ1WTGCTBG2",
}

# --- Claude API ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
# БАГ ВИПРАВЛЕНО: застарілий model string → актуальний
CLAUDE_MODEL = "claude-sonnet-4-6"

# --- Google Sheets Service Account ---
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS  = os.environ.get("TELEGRAM_CHAT_IDS", "").split(",")

# --- Бізнес параметри ---
MARGIN = {
    "USA": 0.25,
    "CA":  0.25,
}

TARGET_TACOS = 0.12
INVENTORY_WARNING_DAYS = 21

# --- Пороги для сповіщень ---
ALERTS = {
    "impressions_drop_critical":  0.50,
    "impressions_drop_warning":   0.25,
    "acos_critical_multiplier":   1.5,
    "acos_warning_multiplier":    1.2,
    "tacos_critical":             0.15,
    "tacos_warning":              0.12,
    "inventory_critical_days":    14,
    "inventory_warning_days":     21,
    "budget_depleted_hour":       16,
    "ctr_low":                    0.003,
    "cvr_low":                    0.08,
}

# --- Аркуші Google Sheets ---
SHEETS_USA = {
    "raw_data":             "Raw Data USA",
    "campaign_analysis":    "Campaign Analysis USA",
    "bid_history":          "Bid History USA",
    "placement_analysis":   "Placement Analysis USA",
    "keyword_intelligence": "Keyword Intelligence USA",
    "ai_recommendations":   "AI Recommendations USA",
    "dayparting":           "Dayparting USA",
    "competitor_tracker":   "Competitor Tracker USA",
}

SHEETS_CA = {
    "raw_data":             "Raw Data CA",
    "campaign_analysis":    "Campaign Analysis CA",
    "bid_history":          "Bid History CA",
    "placement_analysis":   "Placement Analysis CA",
    "keyword_intelligence": "Keyword Intelligence CA",
    "ai_recommendations":   "AI Recommendations CA",
    "dayparting":           "Dayparting CA",
    "competitor_tracker":   "Competitor Tracker CA",
}

SHEETS_COMMON = {
    "weekly_summary":   "Weekly Summary",
    "monthly_summary":  "Monthly Summary",
    "inventory_tracker": "Inventory Tracker",
    "alert_log":        "Alert Log",
}
