#!/bin/bash
# PolyDash — fetch market data + signals + push to GitHub Pages
set -e
cd "$(dirname "$0")"

# ודא SSH remote
git remote set-url origin git@github.com:noamm-opencalw/polydash.git 2>/dev/null || true

echo "📡 Fetching markets + signals..."
python3 fetch_markets.py

echo "📤 Pushing to GitHub..."
git add data.json
git commit -m "chore: update market data $(date -u '+%Y-%m-%d %H:%M') UTC" --allow-empty
git push origin main

echo "✅ Done — https://noamm-opencalw.github.io/polydash/"
