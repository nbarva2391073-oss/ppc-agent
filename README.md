# 🤖 PPC Agent v2 — Alfamarker

## 📁 Файли
- `main_weekly.py` — щотижневий аналіз (понеділок)
- `main_daily.py`  — щоденний моніторинг (вівторок-неділя)
- `amazon_ads.py`  — Amazon Ads API
- `analyzer.py`    — Claude AI аналіз
- `keywords.py`    — аналіз ключових слів
- `monitor.py`     — щоденні перевірки
- `sheets.py`      — Google Sheets
- `telegram_bot.py`— Telegram сповіщення
- `config.py`      — налаштування

## 🔑 GitHub Secrets (Settings → Secrets → Actions)

| Secret | Що це |
|--------|-------|
| `ADS_CLIENT_ID` | Amazon Ads LWA Client ID |
| `ADS_CLIENT_SECRET` | Amazon Ads LWA Client Secret |
| `ADS_REFRESH_TOKEN` | Amazon Ads Refresh Token |
| `ADS_PROFILE_ID_USA` | Profile ID для USA |
| `ADS_PROFILE_ID_CA` | Profile ID для Canada |
| `AMAZON_CLIENT_ID` | SP-API Client ID |
| `AMAZON_CLIENT_SECRET` | SP-API Client Secret |
| `AMAZON_REFRESH_TOKEN_USA` | SP-API Refresh Token USA |
| `AMAZON_REFRESH_TOKEN_CA` | SP-API Refresh Token Canada |
| `ANTHROPIC_API_KEY` | Claude API Key |
| `GOOGLE_CREDENTIALS_JSON` | Весь вміст JSON файлу |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `TELEGRAM_CHAT_IDS` | Chat IDs через кому: `111,222` |

## 📊 Google Sheets аркуші
США: Raw Data USA, Campaign Analysis USA, Bid History USA,
Placement Analysis USA, Keyword Intelligence USA,
AI Recommendations USA, Dayparting USA, Competitor Tracker USA

Canada: ті самі з суфіксом CA

Загальні: Weekly Summary, Monthly Summary,
Inventory Tracker, Alert Log

## ⏰ Розклад
- Понеділок 12:00 Київ → тижневий аналіз
- Вівторок-Неділя 12:00 Київ → щоденний моніторинг
