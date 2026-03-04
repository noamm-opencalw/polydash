#!/usr/bin/env python3
"""
PolyDash - fetch_markets.py
Fetches Polymarket data and generates data.json for the dashboard.
"""

import json
import os
import requests
from datetime import datetime, timezone, timedelta

SIGNALS_FILE = os.path.expanduser(
    "~/.openclaw/workspace-main/polymarket/data/signals.jsonl"
)


def load_signals() -> list:
    """טוען signals מ-signals.jsonl — מחזיר ייחודיים לפי slug, ממוינים לפי ציון"""
    if not os.path.exists(SIGNALS_FILE):
        return []
    by_slug = {}
    with open(SIGNALS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
                slug = s.get("slug", "")
                ts   = s.get("timestamp", "")
                if slug not in by_slug or ts > by_slug[slug].get("timestamp", ""):
                    by_slug[slug] = s
            except Exception:
                pass
    return sorted(by_slug.values(), key=lambda x: x.get("score", 0), reverse=True)


def load_active_bets() -> list:
    """טוען הימורים פעילים — signals שטרם פג תוקפם, מועשרים במחיר נוכחי"""
    if not os.path.exists(SIGNALS_FILE):
        return []
    now = datetime.now(timezone.utc)
    by_slug: dict = {}
    with open(SIGNALS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
                slug = s.get("slug", "")
                ts   = s.get("timestamp", "")
                if slug not in by_slug or ts > by_slug[slug].get("timestamp", ""):
                    by_slug[slug] = s
            except Exception:
                pass

    # תחילה: כולל גם markets שעדיין לא פג תוקפם (days_left > 0 מהזמן שנשמר)
    # אחרי fetch של end_date, נסנן שוב לפי התאריך האמיתי
    all_sigs = list(by_slug.values())

    active = all_sigs  # will filter by real end_date after fetching

    # Normalise field names (two schema versions exist)
    for s in active:
        if "bet_side" not in s:
            s["bet_side"] = "No"   # old signals bet the No side (LATE_SURGE whale)
        if "yes_price" not in s:
            s["yes_price"] = None
        if "no_price" not in s:
            s["no_price"] = s.get("no_price") or (1 - s["yes_price"] if s.get("yes_price") else None)
        s["score"]      = s.get("score")   # may be None for old signals
        s["kelly_pct"]  = s.get("kelly_pct", 0)
        s["persistence"] = s.get("persistence", 0)
        s["reasons"]    = s.get("reasons", [s.get("reason", "")])
        s["whale_names"] = s.get("whale_names") or [
            w["name"] for w in s.get("whales", [])[:2]
        ]

    # Fetch current prices from gamma API — one request per slug (small set)
    for s in active:
        s["current_yes"] = None
        s["current_no"]  = None
        try:
            resp = requests.get(
                f"{BASE_URL}/markets",
                params={"slug": s["slug"], "limit": "1"},
                timeout=10,
            )
            if resp.ok:
                markets = resp.json()
                if isinstance(markets, list) and markets:
                    m = markets[0]
                elif isinstance(markets, dict):
                    m = markets
                else:
                    continue
                try:
                    prices = json.loads(m.get("outcomePrices", "[]"))
                    s["current_yes"] = round(float(prices[0]) * 100, 1) if prices else None
                    s["current_no"]  = round(float(prices[1]) * 100, 1) if len(prices) > 1 else None
                except Exception:
                    pass
                s["market_title"] = m.get("question", s.get("question", ""))
                end_date_raw      = m.get("endDate", "")
                s["end_date"]     = end_date_raw
                s["volume24hr"]   = float(m.get("volume24hr") or 0)
                s["image"]        = m.get("image", "")
                slug_val          = m.get("slug", s["slug"])
                s["link"]         = f"https://polymarket.com/event/{slug_val}" if slug_val else ""
                # Recalculate days_left from actual end_date
                try:
                    ed = datetime.fromisoformat(end_date_raw.replace("Z", "+00:00"))
                    s["days_left"] = max(0, (ed - now).days)
                except Exception:
                    pass  # keep stored days_left
                s["market_closed"] = m.get("closed", False) or m.get("active", True) is False
        except Exception as e:
            print(f"Warning: price fetch failed for {s['slug']}: {e}")

    # חלק לפעילים וסגורים
    resolved = [s for s in active if s.get("market_closed", False) or (s.get("days_left") or 0) == 0]
    active   = [s for s in active if not s.get("market_closed", False) and (s.get("days_left") or 0) > 0]

    # חישוב win/loss על הסגורים
    for s in resolved:
        side = s["bet_side"]
        yes_now = s.get("current_yes", 0) or 0
        no_now  = s.get("current_no",  0) or 0
        if side == "Yes":
            s["resolved_win"] = yes_now >= 99
        else:
            s["resolved_win"] = no_now >= 99

    # Compute simulated P&L
    for s in active:
        size      = float(s.get("size_usd") or 0)
        entry_pct = None
        current   = None
        side      = s["bet_side"]

        if side == "Yes":
            yp        = s.get("yes_price")
            entry_pct = float(yp) * 100 if yp is not None else None
            current   = s.get("current_yes")
        else:
            np_val    = s.get("no_price")
            entry_pct = float(np_val) * 100 if np_val is not None else None
            current   = s.get("current_no")

        if entry_pct and current and entry_pct > 0 and size > 0:
            shares      = size / (entry_pct / 100)
            entry_value = size
            current_value = shares * (current / 100)
            pnl_usd     = current_value - entry_value
            pnl_pct     = (pnl_usd / entry_value) * 100
            s["pnl_usd"]     = round(pnl_usd, 2)
            s["pnl_pct"]     = round(pnl_pct, 1)
            s["entry_pct"]   = round(entry_pct, 1)
            s["current_pct"] = round(current, 1)
        else:
            s["pnl_usd"]     = None
            s["pnl_pct"]     = None
            s["entry_pct"]   = round(entry_pct, 1) if entry_pct else None
            s["current_pct"] = current

    return {
        "active":   sorted(active,   key=lambda x: x.get("timestamp", ""), reverse=True),
        "resolved": sorted(resolved, key=lambda x: x.get("timestamp", ""), reverse=True),
    }

BASE_URL   = "https://gamma-api.polymarket.com"
PROXY_WALLET = "0xBDDB0bFB7dbf1cffdeaD288f6E3027AB1a4D7bF1"


def fetch_real_positions() -> dict:
    """שולף פוזיציות אמיתיות מPolymarket API עבור ה-proxy wallet."""
    try:
        resp = requests.get(
            f"https://data-api.polymarket.com/positions",
            params={"user": PROXY_WALLET, "limit": 50},
            timeout=10,
        )
        resp.raise_for_status()
        positions = resp.json() or []
    except Exception as e:
        print(f"Warning: positions fetch failed: {e}")
        return {"active": [], "resolved": []}

    # טען מחירים קודמים לחישוב שינוי 24h
    prev_prices = {}
    if os.path.exists("data.json"):
        try:
            with open("data.json") as f:
                old = json.load(f)
            for p in old.get("real_positions", {}).get("active", []):
                prev_prices[p["asset"]] = {
                    "price": p.get("curPrice"),
                    "ts": old.get("updated_at", ""),
                }
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    active, resolved = [], []

    for p in positions:
        cur_price    = float(p.get("curPrice", 0))
        avg_price    = float(p.get("avgPrice", 0))
        size         = float(p.get("size", 0))
        initial_val  = float(p.get("initialValue", 0))
        current_val  = float(p.get("currentValue", 0))
        cash_pnl     = float(p.get("cashPnl", 0))
        pct_pnl      = float(p.get("percentPnl", 0))
        end_date_str = p.get("endDate", "")

        # שינוי מחיר מאז העדכון האחרון
        prev = prev_prices.get(p.get("asset", ""), {})
        prev_price   = prev.get("price")
        price_change = None
        if prev_price is not None:
            price_change = round((cur_price - prev_price) * 100, 2)

        # ימים לסיום
        days_left = None
        try:
            ed = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            if ed.tzinfo is None:
                ed = ed.replace(tzinfo=timezone.utc)
            days_left = max(0, (ed - now).days)
        except Exception:
            pass

        # שווי יציאה משוערך (אם מכרנו עכשיו)
        exit_value = round(size * cur_price, 2)

        enriched = {
            "asset":          p.get("asset", ""),
            "conditionId":    p.get("conditionId", ""),
            "title":          p.get("title", ""),
            "outcome":        p.get("outcome", "Yes"),
            "slug":           p.get("slug", ""),
            "eventSlug":      p.get("eventSlug", ""),
            "icon":           p.get("icon", ""),
            "size":           round(size, 4),
            "avgPrice":       round(avg_price, 4),
            "curPrice":       round(cur_price, 4),
            "initialValue":   round(initial_val, 2),
            "currentValue":   round(current_val, 2),
            "exitValue":      exit_value,
            "cashPnl":        round(cash_pnl, 2),
            "percentPnl":     round(pct_pnl, 2),
            "priceChangeSinceUpdate": price_change,
            "endDate":        end_date_str,
            "daysLeft":       days_left,
            "redeemable":     p.get("redeemable", False),
            "negativeRisk":   p.get("negativeRisk", False),
            "link":           f"https://polymarket.com/event/{p.get('eventSlug', p.get('slug', ''))}",
        }

        if days_left == 0 or p.get("redeemable"):
            resolved.append(enriched)
        else:
            active.append(enriched)

    # מיון: הכי גדול קודם
    active.sort(key=lambda x: abs(x["currentValue"]), reverse=True)

    # סטטיסטיקת תיק אמיתי
    total_invested = sum(p["initialValue"] for p in active + resolved)
    total_current  = sum(p["currentValue"] for p in active)
    total_pnl      = sum(p["cashPnl"] for p in active + resolved)
    wins   = sum(1 for p in resolved if p["cashPnl"] > 0)
    losses = sum(1 for p in resolved if p["cashPnl"] <= 0)

    # יתרת USDC
    usdc_balance = 0.0
    try:
        r = requests.get(
            f"https://data-api.polymarket.com/value",
            params={"user": PROXY_WALLET},
            timeout=8,
        )
        data_val = r.json()
        if isinstance(data_val, list) and data_val:
            usdc_balance = float(data_val[0].get("value", 0)) - total_current
    except Exception:
        pass

    # שולף activity (עסקאות היסטוריות)
    activity = []
    try:
        r = requests.get(
            "https://data-api.polymarket.com/activity",
            params={"user": PROXY_WALLET, "limit": 100},
            timeout=10,
        )
        raw_activity = r.json() or []
        for t in raw_activity:
            cid   = t.get("conditionId", "")
            side  = t.get("side", "BUY")
            size  = float(t.get("size", 0))
            usdc  = float(t.get("usdcSize", 0))
            price = float(t.get("price", 0))
            ts    = t.get("timestamp", 0)
            title = t.get("title", "")
            slug  = t.get("slug", "")
            ev    = t.get("eventSlug", "")
            icon  = t.get("icon", "")
            outcome = t.get("outcome", "Yes")
            tx    = t.get("transactionHash", "")
            activity.append({
                "conditionId": cid,
                "title":   title,
                "outcome": outcome,
                "slug":    slug,
                "eventSlug": ev,
                "icon":    icon,
                "side":    side,
                "size":    round(size, 4),
                "usdcSize": round(usdc, 2),
                "price":   round(price, 4),
                "timestamp": ts,
                "tx":      tx,
                "link":    f"https://polymarket.com/event/{ev or slug}",
            })
        activity.sort(key=lambda x: x["timestamp"], reverse=True)
    except Exception as e:
        print(f"Warning: activity fetch failed: {e}")

    return {
        "active":   active,
        "resolved": resolved,
        "activity": activity,
        "portfolio": {
            "total_invested":  round(total_invested, 2),
            "total_current":   round(total_current, 2),
            "total_pnl":       round(total_pnl, 2),
            "wins":   wins,
            "losses": losses,
            "active": len(active),
            "usdc_balance": round(usdc_balance, 2),
        },
    }

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

    # --- Section 5: Good Chances (55–92% probability, any liquidity) ---
    # Polymarket tends to be polarized; capture anything in the "likely" zone
    good_chances = []
    seen_gc = set()
    for m in sorted(all_markets, key=lambda x: (x["liquidity"] + x["volume24hr"]), reverse=True):
        if m["id"] in seen_gc:
            continue
        p = m["yes_pct"]
        if 55 <= p <= 92 and m["liquidity"] >= 500:
            good_chances.append(m)
            seen_gc.add(m["id"])
        if len(good_chances) >= 10:
            break

    # --- Section 6: Beat the Market (best ROI/Kelly edge) ---
    def edge_score(m):
        """Score based on ROI potential × probability sweet-spot × liquidity"""
        roi = m.get("roi_pct") or 0
        vol = min(m["volume24hr"] / 500_000, 1.0)
        liq = min(m["liquidity"] / 100_000, 1.0)
        p   = m["yes_pct"] / 100.0
        # Sweet spot: 30-70% prob — meaningful edge without pure lottery
        if p < 0.08 or p > 0.92:
            sweetness = 0.1   # near-certain or near-impossible — not interesting
        else:
            sweetness = 1.0 - abs(p - 0.5) * 1.5
        return (roi * 0.4) + (sweetness * 35) + (vol * 10) + (liq * 15)

    beat_market = sorted(
        [m for m in all_markets if (m.get("roi_pct") or 0) > 5 and 8 <= m["yes_pct"] <= 92 and m["liquidity"] >= 1_000],
        key=edge_score,
        reverse=True
    )[:10]

    # --- Real positions from Polymarket ---
    real_positions = fetch_real_positions()

    # --- Recommendation: top pick with reasoning ---
    signals          = load_signals()
    bets_result      = load_active_bets()
    active_bets      = bets_result["active"]
    resolved_bets    = bets_result["resolved"]

    def generate_recommendation(signals, good_chances, beat_market, hot):  # noqa: C901
        """Pick the best opportunity and explain why."""
        # Priority 1: Strong signal with high score and meaningful probability
        strong = [
            s for s in signals
            if s.get("strength") == "STRONG"
            and 0.10 <= s.get("yes_price", 0) <= 0.90  # not near-certain
            and s.get("days_left", 0) > 0               # not expired
        ]
        if strong:
            s = strong[0]
            yes_pct = round(s.get("yes_price", 0.5) * 100, 1)
            return {
                "source": "signal",
                "title": s.get("question", ""),
                "bet_side": s.get("bet_side", "Yes"),
                "yes_pct": yes_pct,
                "score": s.get("score", 0),
                "size_usd": s.get("size_usd", 0),
                "reasoning": [
                    f"Signal חזק עם ציון {s.get('score', 0)}/100",
                    f"הימור על {s.get('bet_side', 'Yes')} — מחיר {yes_pct}%",
                    *[r for r in s.get("reasons", [])[:3]],
                ],
                "action": s.get("action", "DRY_RUN"),
                "link": f"https://polymarket.com/event/{s.get('slug', '')}",
            }
        # Priority 2: Best edge from beat_market (prefer 30-70% probability range)
        mid_range = [m for m in beat_market if 25 <= m["yes_pct"] <= 70]
        bm_pick = mid_range[0] if mid_range else (beat_market[0] if beat_market else None)
        if bm_pick:
            m = bm_pick
            roi   = m.get("roi_pct", 0)
            vol   = m.get("volume24hr", 0)
            price = m["yes_pct"]
            return {
                "source": "edge",
                "title": m["question"],
                "bet_side": "Yes",
                "yes_pct": price,
                "score": round(edge_score(m), 1),
                "size_usd": None,
                "reasoning": [
                    f"ROI נטו צפוי: {roi:.0f}% על $100 הימור",
                    f"מחיר YES: {price}% — נזילות: ${m['liquidity']:,.0f}",
                    f"נפח 24h: ${vol:,.0f}" if vol > 1000 else None,
                    m.get("interesting", ""),
                ],
                "action": "DRY_RUN",
                "link": m.get("link", ""),
            }
        # Priority 3: Best good_chance
        if good_chances:
            m = good_chances[0]
            return {
                "source": "good_chance",
                "title": m["question"],
                "bet_side": "Yes",
                "yes_pct": m["yes_pct"],
                "score": None,
                "size_usd": None,
                "reasoning": [
                    f"סיכוי YES גבוה: {m['yes_pct']}%",
                    f"נזילות גבוהה: ${m['liquidity']:,.0f}",
                    m.get("interesting", ""),
                ],
                "action": "DRY_RUN",
                "link": m.get("link", ""),
            }
        return None

    recommendation = generate_recommendation(signals, good_chances, beat_market, hot)

    # Portfolio summary (active + resolved)
    all_bets       = active_bets + resolved_bets
    total_invested = sum(float(b.get("size_usd") or 0) for b in all_bets)
    wins           = sum(1 for b in resolved_bets if b.get("resolved_win"))
    losses         = sum(1 for b in resolved_bets if not b.get("resolved_win", True))
    # P&L on resolved: win = get back size_usd/entry_pct per share; rough calc
    total_pnl      = sum(b.get("pnl_usd") or 0 for b in all_bets)

    data = {
        "updated_at": now.isoformat(),
        "real_positions": real_positions,
        "hot": hot,
        "movers": movers,
        "new_interesting": new_interesting,
        "worth_watching": worth_watching,
        "good_chances": good_chances,
        "beat_market": beat_market,
        "recommendation": recommendation,
        "all_markets": all_for_tabs,
        "signals": signals,
        "signals_count": len(signals),
        "active_bets": active_bets,
        "resolved_bets": resolved_bets,
        "active_bets_count": len(active_bets),
        "resolved_bets_count": len(resolved_bets),
        "portfolio": {
            "total_invested": round(total_invested, 2),
            "total_pnl": round(total_pnl, 2),
            "wins": wins,
            "losses": losses,
            "active": len(active_bets),
        },
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ data.json written — hot: {len(hot)}, movers: {len(movers)}, new: {len(new_interesting)}, watching: {len(worth_watching)}, good_chances: {len(good_chances)}, beat_market: {len(beat_market)}, active_bets: {len(active_bets)}")


if __name__ == "__main__":
    main()
