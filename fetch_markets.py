#!/usr/bin/env python3
"""
PolyDash v2 — fetch_markets.py
Aggregates all system data into data.json for the Strategy Command Center.
"""

import json
import os
from datetime import datetime, timezone

BASE = os.path.expanduser("~/.openclaw/workspace-main/polymarket/data")
OUT  = os.path.join(os.path.dirname(__file__), "data.json")

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
    if limit:
        rows = rows[-limit:]
    return rows

def build_data():
    now = datetime.now(timezone.utc)

    # --- Positions ---
    positions_cache = load_json(f"{BASE}/positions_cache.json", {})
    executed_bets   = load_json(f"{BASE}/executed_bets.json", {})
    
    positions = []
    total_value = 0.0
    total_cost  = 0.0
    
    # Build slug→question+value lookup from positions_cache
    # positions_cache keys are question strings; try to match by keyword overlap
    slug_to_cache = {}
    for slug in executed_bets:
        slug_words = set(slug.replace("-", " ").split())
        best_match = None
        best_score = 0
        for pname, pdata in positions_cache.items():
            pwords = set(pname.lower().split())
            score = len(slug_words & pwords)
            if score > best_score:
                best_score = score
                best_match = (pname, pdata)
        if best_match and best_score >= 3:
            slug_to_cache[slug] = best_match

    for slug, bet in executed_bets.items():
        if bet.get("order_id") == "manual_block":
            continue
        
        cost = float(bet.get("size_usd", 0))
        
        # Use cache match if available
        if slug in slug_to_cache:
            q, pdata = slug_to_cache[slug]
            cur = float(pdata.get("cur", cost))
        else:
            q = slug.replace("-", " ").title()
            cur = cost
        
        pnl = cur - cost
        pnl_pct = (pnl / cost * 100) if cost > 0 else 0
        
        expires_ts = bet.get("expires_ts", "")
        days_left = 0
        if expires_ts:
            try:
                exp = datetime.fromisoformat(expires_ts.replace("Z","+00:00"))
                days_left = max(0, (exp - now).days)
            except Exception:
                pass
        
        total_value += cur
        total_cost  += cost
        positions.append({
            "slug":         slug,
            "question":     q,
            "direction":    bet.get("direction", "YES"),
            "cost":         round(cost, 2),
            "current_value": round(cur, 2),
            "pnl":          round(pnl, 2),
            "pnl_pct":      round(pnl_pct, 1),
            "days_left":    days_left,
            "expires_ts":   expires_ts,
            "order_id":     bet.get("order_id", ""),
        })
    
    total_pnl = total_value - total_cost
    pnl_pct   = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    # --- Learned params ---
    lp = load_json(f"{BASE}/learned_params.json", {})
    
    # --- Geo context ---
    geo = load_json(f"{BASE}/geo_context.json", {})
    
    # --- Decisions ---
    decisions_raw = load_jsonl(f"{BASE}/decisions.jsonl", limit=50)
    decisions = []
    for d in reversed(decisions_raw):
        decisions.append({
            "timestamp": d.get("timestamp",""),
            "slug":      d.get("slug",""),
            "action":    d.get("action",""),
            "price":     d.get("price_at_decision", 0),
            "reason":    d.get("reason",""),
            "outcome":   d.get("outcome","OPEN"),
        })
    
    # --- Signals ---
    signals_raw = load_jsonl(f"{BASE}/signals.jsonl", limit=20)
    signals = []
    seen_slugs = set()
    for s in reversed(signals_raw):
        slug = s.get("slug","")
        if slug in seen_slugs: continue
        seen_slugs.add(slug)
        signals.append({
            "slug":       slug,
            "question":   s.get("question",""),
            "score":      s.get("score",0),
            "edge":       s.get("edge",0),
            "side":       s.get("side","YES"),
            "confidence": s.get("confidence",0),
            "days_left":  s.get("days_left",0),
            "type":       s.get("type",""),
        })
    
    # --- Strategy stats ---
    stats = load_json(f"{BASE}/strategy_stats.json", {})
    
    # --- Geo history ---
    geo_history = load_jsonl(f"{BASE}/geo_history.jsonl", limit=15)
    
    # --- Monthly goal ---
    goal = load_json(f"{BASE}/monthly_goal.json", {})
    
    data = {
        "updated_at": now.isoformat(),
        "portfolio": {
            "total_value":   round(total_value, 2),
            "total_cost":    round(total_cost, 2),
            "total_pnl":     round(total_pnl, 2),
            "pnl_pct":       round(pnl_pct, 1),
            "cash_available": float(goal.get("available_cash", 191.0)),
        },
        "positions":     positions,
        "learned_params": lp,
        "geo_context":   geo,
        "decisions":     decisions,
        "signals":       signals,
        "strategy_stats": stats,
        "geo_history":   geo_history,
        "monthly_goal":  goal,
    }
    
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"✅ data.json updated: {len(positions)} positions, {len(decisions)} decisions, {len(signals)} signals")

if __name__ == "__main__":
    build_data()
