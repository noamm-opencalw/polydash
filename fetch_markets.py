#!/usr/bin/env python3
"""
PolyDash - fetch_markets.py
Fetches Polymarket data and generates data.json for the dashboard.
"""

import json
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = "https://gamma-api.polymarket.com"

CATEGORY_KEYWORDS = {
    "politics": ["election", "president", "congress", "senate", "vote", "biden", "trump", "democrat", "republican",
                 "harris", "party", "governor", "minister", "parliament", "legislation", "impeach", "primary"],
    "economy": ["fed", "interest rate", "inflation", "gdp", "recession", "unemployment", "market", "stock",
                "bitcoin", "crypto", "dollar", "euro", "rate", "bank", "economy", "economic", "trade",
                "tariff", "deficit", "debt", "fiscal"],
    "sports": ["nfl", "nba", "mlb", "nhl", "soccer", "football", "basketball", "baseball", "tennis", "golf",
               "super bowl", "world cup", "championship", "playoffs", "season", "game", "match", "team",
               "player", "coach", "olympic", "ufc", "mma", "boxing", "formula", "f1", "wimbledon"],
    "crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain", "defi", "nft", "altcoin",
               "solana", "sol", "binance", "coinbase", "token", "wallet", "doge", "xrp", "ripple"],
    "tech": ["ai", "artificial intelligence", "openai", "gpt", "google", "apple", "microsoft", "meta",
             "tesla", "nvidia", "amazon", "tech", "software", "hardware", "startup", "ipo", "acquisition",
             "antitrust", "regulation", "data", "privacy", "cyber", "space", "nasa", "spacex"],
    "geo": ["russia", "ukraine", "china", "taiwan", "israel", "iran", "war", "military", "nato", "un",
            "sanctions", "ceasefire", "peace", "conflict", "invasion", "nuclear", "missile", "troops",
            "north korea", "middle east", "gaza", "hamas"],
}

def categorize(question: str) -> str:
    q = question.lower()
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def interesting_reason(question: str, category: str, yes_pct: float, volume24hr: float) -> str:
    """Generate a short 'why interesting' explanation."""
    q_lower = question.lower()
    
    if 40 <= yes_pct <= 60:
        base = "שוק מאוזן — התוצאה פתוחה לגמרי"
    elif yes_pct >= 85:
        base = "הסיכוי גבוה מאוד — כמעט בטוח"
    elif yes_pct <= 15:
        base = "סיכוי נמוך מאוד — ספקולציה טהורה"
    elif yes_pct >= 70:
        base = "הסיכוי נוטה בבירור לכן"
    else:
        base = "סיכוי נמוך — שוק מנוגד"

    if volume24hr > 1_000_000:
        base += " • נסחר מאסיבית היום"
    elif volume24hr > 100_000:
        base += " • נפח מסחר גבוה"

    cat_labels = {
        "politics": "🗳️ פוליטיקה",
        "economy": "💰 כלכלה",
        "sports": "🏆 ספורט",
        "crypto": "₿ קריפטו",
        "tech": "🔬 טכנולוגיה",
        "geo": "🌍 גאופוליטיקה",
        "other": "🎭 שונות",
    }
    return f"{cat_labels.get(category, '📊')} • {base}"


def fetch_markets(url: str, params: dict) -> list:
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return []


def process_market(m: dict) -> dict | None:
    question = m.get("question", "")
    if not question:
        return None

    # Parse outcomePrices
    try:
        prices = json.loads(m.get("outcomePrices", "[]"))
    except Exception:
        prices = []

    yes_pct = round(float(prices[0]) * 100, 1) if prices else 50.0
    no_pct = round(float(prices[1]) * 100, 1) if len(prices) > 1 else round(100 - yes_pct, 1)

    # Parse outcomes
    try:
        outcomes = json.loads(m.get("outcomes", '["Yes","No"]'))
    except Exception:
        outcomes = ["Yes", "No"]

    volume = float(m.get("volume") or 0)
    volume24hr = float(m.get("volume24hr") or 0)
    liquidity = float(m.get("liquidity") or 0)

    # 24h price change (from oneWeekPriceChange scaled — use available data)
    price_change_24h = float(m.get("oneDayPriceChange") or 0)
    # Some markets expose this
    if not price_change_24h:
        # Estimate from best bid movement — not available, set to 0
        price_change_24h = 0.0

    category = categorize(question)
    end_date = m.get("endDate", "")
    start_date = m.get("startDate", m.get("createdAt", ""))

    # Image from events
    image = m.get("image", "")
    events = m.get("events", [])
    if events and isinstance(events, list) and events[0].get("image"):
        image = events[0]["image"]

    # Slug / link
    slug = m.get("slug", "")
    link = f"https://polymarket.com/event/{slug}" if slug else ""

    interesting = interesting_reason(question, category, yes_pct, volume24hr)

    # Financial Truth: net return after 25% tax + 0.1% commission (on $100 bet)
    net_return_100 = None
    gross_return_100 = None
    roi_pct = None
    p = yes_pct / 100.0
    if 0.01 < p < 0.99:
        bet = 100.0
        shares = bet / p
        gross = shares * (1 - p)
        after_fees = gross - (bet * 0.001)
        net = after_fees * 0.75
        net_return_100 = round(net, 1)
        gross_return_100 = round(gross, 1)
        roi_pct = round((net / bet) * 100, 0)

    return {
        "id": m.get("id", ""),
        "question": question,
        "yes_pct": yes_pct,
        "no_pct": no_pct,
        "outcomes": outcomes,
        "volume": volume,
        "volume24hr": volume24hr,
        "liquidity": liquidity,
        "price_change_24h": price_change_24h,
        "category": category,
        "end_date": end_date,
        "start_date": start_date,
        "image": image,
        "link": link,
        "interesting": interesting,
        "oneWeekPriceChange": float(m.get("oneWeekPriceChange") or 0),
        "oneMonthPriceChange": float(m.get("oneMonthPriceChange") or 0),
        "lastTradePrice": float(m.get("lastTradePrice") or 0),
        "net_return_100": net_return_100,
        "gross_return_100": gross_return_100,
        "roi_pct": roi_pct,
    }


def main():
    now = datetime.now(timezone.utc)
    print(f"Fetching Polymarket data at {now.isoformat()}")

    # Fetch top markets by 24h volume
    hot_raw = fetch_markets(f"{BASE_URL}/markets", {
        "active": "true",
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": "50",
    })

    # Fetch new markets by start date
    new_raw = fetch_markets(f"{BASE_URL}/markets", {
        "active": "true",
        "closed": "false",
        "order": "startDate",
        "ascending": "false",
        "limit": "50",
    })

    # Fetch by liquidity for "worth watching"
    liquid_raw = fetch_markets(f"{BASE_URL}/markets", {
        "active": "true",
        "closed": "false",
        "order": "liquidity",
        "ascending": "false",
        "limit": "50",
    })

    # Combine all, deduplicate by id
    seen_ids = set()
    all_markets = []
    for m in hot_raw + new_raw + liquid_raw:
        mid = m.get("id")
        if mid and mid not in seen_ids:
            seen_ids.add(mid)
            processed = process_market(m)
            if processed:
                all_markets.append(processed)

    print(f"Total unique markets: {len(all_markets)}")

    # --- Section 1: Hot Markets (top 10 by volume24hr) ---
    hot = sorted(all_markets, key=lambda x: x["volume24hr"], reverse=True)[:10]

    # --- Section 2: Big Movers (by 1-week price change as proxy for momentum) ---
    movers_up = sorted(
        [m for m in all_markets if m["oneWeekPriceChange"] > 0.01],
        key=lambda x: x["oneWeekPriceChange"],
        reverse=True
    )[:5]
    movers_down = sorted(
        [m for m in all_markets if m["oneWeekPriceChange"] < -0.01],
        key=lambda x: x["oneWeekPriceChange"]
    )[:5]
    movers = movers_up + movers_down

    # --- Section 3: New & Interesting (last 14 days, min liquidity 5k) ---
    cutoff = now - timedelta(days=14)
    new_interesting = []
    for m in all_markets:
        try:
            sd = datetime.fromisoformat(m["start_date"].replace("Z", "+00:00"))
            if sd >= cutoff and m["liquidity"] >= 5000:
                new_interesting.append(m)
        except Exception:
            pass
    new_interesting = sorted(new_interesting, key=lambda x: x["volume24hr"], reverse=True)[:8]

    # --- Section 4: Worth Watching (curated: uncertain + high volume + interesting topic) ---
    worth_watching = []
    seen_worth = set()
    # Priority: markets near 50%, high liquidity, interesting categories
    for m in sorted(all_markets, key=lambda x: (x["liquidity"] + x["volume24hr"]), reverse=True):
        if m["id"] in seen_worth:
            continue
        # Prefer uncertain markets or notable categories
        uncertainty = 1 - abs(m["yes_pct"] / 100 - 0.5) * 2  # 1.0 = perfectly uncertain
        score = (uncertainty * 0.4) + (min(m["liquidity"] / 1_000_000, 1) * 0.4) + (min(m["volume24hr"] / 500_000, 1) * 0.2)
        if score > 0.3 or m["category"] in ["geo", "politics"]:
            worth_watching.append(m)
            seen_worth.add(m["id"])
        if len(worth_watching) >= 12:
            break

    # --- All markets (for category filtering) ---
    all_for_tabs = sorted(all_markets, key=lambda x: x["volume24hr"], reverse=True)

    data = {
        "updated_at": now.isoformat(),
        "hot": hot,
        "movers": movers,
        "new_interesting": new_interesting,
        "worth_watching": worth_watching,
        "all_markets": all_for_tabs,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ data.json written — hot: {len(hot)}, movers: {len(movers)}, new: {len(new_interesting)}, watching: {len(worth_watching)}")


if __name__ == "__main__":
    main()
