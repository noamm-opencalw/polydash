#!/usr/bin/env python3
"""
PolyDash v2 — fetch_markets.py
שולף נתוני אמת מ-Polymarket ומצרף נתוני מערכת לdata.json
"""

import json
import os
import requests
from datetime import datetime, timezone

BASE_DIR = os.path.expanduser("~/.openclaw/workspace-main/polymarket/data")
OUT = os.path.join(os.path.dirname(__file__), "data.json")
GAMMA = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
WALLET = "0xbddb0bfb7dbf1cffdead288f6e3027ab1a4d7bf1"

def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def load_jsonl(path, limit=None):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows[-limit:] if limit else rows

def fetch_positions_live():
    """שולף פוזיציות חיות מ-Polymarket Data API"""
    try:
        r = requests.get(f"{DATA_API}/positions",
                         params={"user": WALLET, "limit": 50, "sizeThreshold": "0.01"},
                         timeout=15)
        return r.json() if r.ok else []
    except Exception:
        return []

def fetch_market_price(slug):
    """שולף מחיר חי לפי slug"""
    try:
        r = requests.get(f"{GAMMA}/markets", params={"slug": slug}, timeout=8)
        data = r.json()
        if data:
            m = data[0]
            prices = json.loads(m.get("outcomePrices", "[]") or "[]")
            return {
                "yes": float(prices[0]) if prices else 0,
                "no": float(prices[1]) if len(prices) > 1 else 0,
                "question": m.get("question", ""),
                "end": m.get("endDate", ""),
                "closed": m.get("closed", False),
                "resolved": m.get("resolved", False),
                "liq": float(m.get("liquidityNum", 0)),
                "vol24h": float(m.get("volume24hr", 0)),
            }
    except Exception:
        pass
    return None

def fetch_clob_midpoint(token_id):
    """שולף midpoint מ-CLOB"""
    try:
        r = requests.get(f"{CLOB}/midpoint", params={"token_id": token_id}, timeout=6)
        d = r.json()
        if "mid" in d:
            return float(d["mid"])
    except Exception:
        pass
    return None

def get_days_left(end_str):
    if not end_str:
        return 0
    try:
        end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, (end - now).days)
    except Exception:
        return 0

def build_data():
    now = datetime.now(timezone.utc)

    # ── נתוני מערכת ──
    lp = load_json(f"{BASE_DIR}/learned_params.json", {})
    geo = load_json(f"{BASE_DIR}/geo_context.json", {})
    geo_history = load_jsonl(f"{BASE_DIR}/geo_history.jsonl", limit=20)
    stats = load_json(f"{BASE_DIR}/strategy_stats.json", {})
    goal = load_json(f"{BASE_DIR}/monthly_goal.json", {})
    decisions_raw = load_jsonl(f"{BASE_DIR}/decisions.jsonl", limit=100)
    signals_raw = load_jsonl(f"{BASE_DIR}/signals.jsonl", limit=30)

    # ── פוזיציות עם נתוני Polymarket אמיתיים ──
    live_positions_api = fetch_positions_live()

    # מפה של slug → metadata שלנו
    our_positions = [
        {
            "slug": "will-crude-oil-cl-hit-high-100-by-end-of-march-658-396-769-971",
            "slug_display": "נפט גולמי $100 עד סוף מרץ",
            "side": "NO",
            "entry_price": 0.24,
            "cost": 7.75,
            "size": 32.31,
            "token_id": None,
            "rationale": "WTI היה ~$67, הנחנו שלא יגיע ל-$100 עד סוף מרץ",
            "assessment": "המלחמה קפצה את WTI ל-$91. השוק עכשיו 97% YES — שגינו בכיוון",
            "outcome_tag": "bad",
        },
        {
            "slug": "will-bitcoin-reach-75k-in-march-2026",
            "slug_display": "ביטקוין $75,000 במרץ",
            "side": "NO",
            "entry_price": 0.54,
            "cost": 12.00,
            "size": 22.22,
            "token_id": None,
            "rationale": "BTC היה ~$67K, הנחנו שלא יגיע ל-$75K — סביבת risk-off",
            "assessment": "BTC נשאר מתחת $70K. NO עכשיו 66% — הכיוון נכון",
            "outcome_tag": "good",
        },
        {
            "slug": "will-another-country-strike-iran-by-march-31-833",
            "slug_display": "מדינה תתקוף איראן עד 31/3",
            "side": "YES",
            "entry_price": 0.48,
            "cost": 10.00,
            "size": 20.83,
            "token_id": None,
            "rationale": "מלחמה פעילה — ארה\"ב וישראל כבר מתקיפות",
            "assessment": "תקיפות נמשכות. YES עלה ל-52.5% (היה 48%) — כיוון נכון",
            "outcome_tag": "good",
        },
        {
            "slug": "will-crude-oil-cl-hit-high-110-by-end-of-march-732-945-787-552",
            "slug_display": "נפט גולמי $110 עד סוף מרץ",
            "side": "YES",
            "entry_price": 0.54,
            "cost": 10.00,
            "size": 18.52,
            "token_id": None,
            "rationale": "מיצרי הורמוז בסיכון, WTI עלול לעלות עוד",
            "assessment": "YES קפץ ל-84%! עלייה של 56% — ניצחון ברור",
            "outcome_tag": "great",
        },
        {
            "slug": "houthi-strike-on-israel-by-march-15-2026",
            "slug_display": "Houthi תקיפה על ישראל עד 15/3",
            "side": "YES",
            "entry_price": 0.28,
            "cost": 10.00,
            "size": 34.48,
            "token_id": "19974892541512192867354884407997665863065737581621295585232510223430257860132",
            "rationale": "חות'ים פעילים, הסתברות שלנו 45% מול 28% בשוק",
            "assessment": "YES עלה ל-35.5%, כיוון נכון — עוד 6 ימים לאירוע",
            "outcome_tag": "good",
        },
        {
            "slug": "will-bitcoin-dip-to-65k-in-march-2026",
            "slug_display": "ביטקוין ינחת $65,000 במרץ",
            "side": "YES",
            "entry_price": 0.786,
            "cost": 10.00,
            "size": 12.59,
            "token_id": "112493481455469093769281852159558847572704253342416714876781522096078968514094",
            "rationale": "BTC ב-$67K, הסתברות שלנו 88% מול 78.6% בשוק",
            "assessment": "YES עלה ל-87.4% — קרוב ל-$65K, מגמה נכונה",
            "outcome_tag": "good",
        },
    ]

    # שליפת מחירים חיים
    positions = []
    total_value = 0.0
    total_cost = 0.0

    # בנה bulk fetch — 2000 markets
    print("שולף 2000 שווקים...")
    all_markets = {}
    for page in range(4):
        try:
            r = requests.get(f"{GAMMA}/markets",
                params={"limit": 500, "offset": page * 500,
                        "order": "volume24hr", "ascending": "false"},
                timeout=15)
            batch = r.json()
            for m in batch:
                all_markets[m.get("slug", "")] = m
            if len(batch) < 500:
                break
        except Exception as e:
            print(f"  שגיאה בדף {page}: {e}")
            break

    print(f"  נטענו {len(all_markets)} שווקים")

    for pos in our_positions:
        slug = pos["slug"]
        entry = pos["entry_price"]
        side = pos["side"]
        cost = pos["cost"]
        size = pos["size"]

        # מחיר חי
        live_yes = 0.0
        live_data = all_markets.get(slug)
        if live_data:
            prices = json.loads(live_data.get("outcomePrices", "[]") or "[]")
            live_yes = float(prices[0]) if prices else 0.0
            end_str = live_data.get("endDate", "")
            closed = live_data.get("closed", False)
            liq = float(live_data.get("liquidityNum", 0))
            vol = float(live_data.get("volume24hr", 0))
        elif pos.get("token_id"):
            # נסה CLOB midpoint
            mid = fetch_clob_midpoint(pos["token_id"])
            live_yes = mid if mid is not None else entry
            end_str = ""
            closed = False
            liq = 0
            vol = 0
        else:
            live_yes = entry  # fallback
            end_str = ""
            closed = False
            liq = 0
            vol = 0

        live_side = live_yes if side == "YES" else (1.0 - live_yes)
        pnl_pct = (live_side - entry) / entry * 100 if entry > 0 else 0
        value = size * live_side
        pnl_usd = value - cost
        days_left = get_days_left(end_str)

        total_value += value
        total_cost += cost

        positions.append({
            "slug": slug,
            "slug_display": pos["slug_display"],
            "side": side,
            "entry_price": round(entry, 4),
            "live_yes": round(live_yes, 4),
            "live_no": round(1 - live_yes, 4),
            "live_side_price": round(live_side, 4),
            "cost": round(cost, 2),
            "size": round(size, 4),
            "current_value": round(value, 2),
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 1),
            "days_left": days_left,
            "expires_ts": end_str,
            "closed": closed,
            "liq": round(liq, 0),
            "vol24h": round(vol, 0),
            "rationale": pos["rationale"],
            "assessment": pos["assessment"],
            "outcome_tag": pos["outcome_tag"],
        })

    total_pnl = total_value - total_cost
    pnl_pct_total = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    # ── decisions (ייחודיות לפי slug) ──
    seen_slugs = set()
    decisions = []
    for d in reversed(decisions_raw):
        key = f"{d.get('slug','')}:{d.get('action','')}"
        if key in seen_slugs:
            continue
        seen_slugs.add(key)
        decisions.insert(0, {
            "timestamp": d.get("timestamp", ""),
            "slug": d.get("slug", ""),
            "action": d.get("action", ""),
            "price": round(float(d.get("price_at_decision", 0)), 4),
            "reason": d.get("reason", ""),
            "outcome": d.get("outcome") or "OPEN",
        })

    # ── signals ייחודיים ──
    seen_sig = set()
    signals = []
    for s in reversed(signals_raw):
        slug = s.get("slug", "")
        if slug in seen_sig:
            continue
        seen_sig.add(slug)
        signals.insert(0, {
            "slug": slug,
            "question": s.get("question", ""),
            "score": s.get("score", 0),
            "edge": round(float(s.get("edge", 0)), 4),
            "side": s.get("side", "YES"),
            "confidence": s.get("confidence", 0),
            "days_left": s.get("days_left", 0),
            "type": s.get("type", ""),
        })
    signals = signals[-10:]  # רק 10 אחרונים ייחודיים

    data = {
        "updated_at": now.isoformat(),
        "portfolio": {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2),
            "pnl_pct": round(pnl_pct_total, 1),
            "cash_available": float(goal.get("available_cash", 191.0)),
            "positions_count": len(positions),
        },
        "positions": positions,
        "learned_params": lp,
        "geo_context": geo,
        "decisions": decisions,
        "signals": signals,
        "strategy_stats": stats,
        "geo_history": geo_history,
        "monthly_goal": goal,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    print(f"✅ data.json עודכן: {len(positions)} פוזיציות | P&L: ${total_pnl:+.2f} ({pnl_pct_total:+.1f}%)")
    for p in positions:
        icon = {"great": "🚀", "good": "✅", "bad": "❌"}.get(p["outcome_tag"], "•")
        print(f"  {icon} {p['slug_display'][:30]:30} | {p['side']} {p['entry_price']:.2f}→{p['live_side_price']:.2f} | {p['pnl_pct']:+.1f}% | ${p['pnl_usd']:+.2f}")

if __name__ == "__main__":
    build_data()
