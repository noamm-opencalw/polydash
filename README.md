# 📊 PolyDash — שוק הניבויים

**PolyDash** is a beautiful, real-time Polymarket dashboard with Hebrew UI.

🌐 **Live:** https://noamm-opencalw.github.io/polydash/

## Features

| Section | Description |
|---------|-------------|
| 🔥 **חם עכשיו** | Top markets by 24h trading volume |
| 📈 **תנועות גדולות** | Biggest weekly price movers (up & down) |
| ✨ **חדש ומעניין** | Recently created markets with high liquidity |
| 🎯 **שווה לעקוב** | Curated markets by category |

## Design
- Clean white cards, bold typography
- Huge YES/NO probability percentages
- Mobile-first, max-width 520px
- RTL Hebrew UI, English market names
- Auto-refresh every 5 minutes

## Tech Stack
- Pure HTML/CSS/JavaScript (no framework)
- Python fetch script → generates `data.json`
- GitHub Actions runs hourly to update data
- GitHub Pages for hosting

## Local Dev
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests
python fetch_markets.py
# Then open index.html in browser
```

## Data Sources
All data from [Polymarket Gamma API](https://gamma-api.polymarket.com) (public, no key needed).

---
Built with ❤️ by PolyDash
