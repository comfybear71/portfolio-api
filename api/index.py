from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
from datetime import datetime, timedelta
from typing import Optional, List

app = FastAPI(
    title="Portfolio Crypto API",
    description="Backend API for Swyftx portfolio data",
    version="1.0.0"
)

# CORS for your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://portfolio-crypto-inky.vercel.app",
        "https://portfolio-crypto-git-main-comfybear71.vercel.app",
        "https://flub.vercel.app",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Swyftx API Configuration
SWYFTX_API_URL = "https://api.swyftx.com.au"
SWYFTX_API_KEY = os.getenv("SWYFTX_API_KEY")

# ─── Simple in-memory cache ───────────────────────────────────────────────────
# Vercel serverless functions don't share memory between invocations, but
# within a single warm instance this prevents hammering the APIs on rapid
# repeated requests (e.g. multiple browser tabs, quick refresh taps).
# Cache TTL: 60 seconds — fresh enough for a portfolio view.

CACHE_TTL_SECONDS = 60

_cache = {
    "data":       None,
    "expires_at": datetime.utcnow()
}

def _cache_valid():
    return _cache["data"] is not None and datetime.utcnow() < _cache["expires_at"]

def _set_cache(data):
    _cache["data"]       = data
    _cache["expires_at"] = datetime.utcnow() + timedelta(seconds=CACHE_TTL_SECONDS)

# ─────────────────────────────────────────────────────────────────────────────

# Complete coin mapping
COIN_MAP = {
    1:   ('AUD',  'aud',                       1.0),
    3:   ('BTC',  'bitcoin',                   None),
    5:   ('ETH',  'ethereum',                  None),
    6:   ('XRP',  'ripple',                    None),
    12:  ('ADA',  'cardano',                   None),
    36:  ('USD',  'usd',                       1.0),
    53:  ('USDC', 'usd-coin',                  None),
    73:  ('DOGE', 'dogecoin',                  None),
    130: ('SOL',  'solana',                    None),
    405: ('LUNA', 'terra-luna-2',                None),
    407: ('NEXO', 'nexo',                      None),
    438: ('SUI',  'sui',                       None),
    496: ('ENA',  'ethena',                    None),
    569: ('POL',  'polygon-ecosystem-token',   None),
    635: ('XAUT', 'tether-gold',               None),
}

ASSET_COLORS = {
    'BTC':  '#F7931A', 'ETH':  '#627EEA', 'XRP':  '#23292F',
    'ADA':  '#0033AD', 'SOL':  '#9945FF', 'DOGE': '#C2A633',
    'USDC': '#2775CA', 'AUD':  '#FFCD00', 'USD':  '#85BB65',
    'LUNA': '#FF6B6B', 'NEXO': '#1A5AFF', 'SUI':  '#4DA2FF',
    'ENA':  '#000000', 'POL':  '#8247E5', 'XAUT': '#FFD700'
}


@app.get("/")
async def root():
    return {
        "message": "Portfolio Crypto API",
        "status":  "operational",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}


@app.get("/api/portfolio")
async def get_portfolio():
    # Return cached data if still fresh — avoids hitting Swyftx/CoinGecko
    # on every refresh tap
    if _cache_valid():
        return _cache["data"]

    try:
        if not SWYFTX_API_KEY:
            raise HTTPException(status_code=500, detail="SWYFTX_API_KEY not configured")

        # ── Step 1: Authenticate with Swyftx ─────────────────────────────────
        async with httpx.AsyncClient() as client:
            auth_resp = await client.post(
                f"{SWYFTX_API_URL}/auth/refresh/",
                json={"apiKey": SWYFTX_API_KEY},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            auth_resp.raise_for_status()
            token   = auth_resp.json().get("accessToken")
            headers = {"Authorization": f"Bearer {token}"}

            # ── Step 2: Get balances ──────────────────────────────────────────
            balances_resp = await client.get(
                f"{SWYFTX_API_URL}/user/balance/",
                headers=headers,
                timeout=10
            )
            balances_resp.raise_for_status()
            balances_data = balances_resp.json()

        # Process balances — only keep assets with a positive balance
        balances = {}
        for b in balances_data:
            asset_id  = b.get('assetId')
            available = float(b.get('availableBalance', 0))
            if available > 0:
                balances[asset_id] = available

        # ── Step 3: Get prices from CoinGecko ─────────────────────────────────
        cg_ids = [
            COIN_MAP[asset_id][1]
            for asset_id in balances.keys()
            if asset_id in COIN_MAP and COIN_MAP[asset_id][2] is None
        ]

        prices = {}
        if cg_ids:
            cg_url = (
                "https://api.coingecko.com/api/v3/simple/price"
                f"?ids={','.join(set(cg_ids))}"
                "&vs_currencies=aud"
                "&include_24hr_change=true"
            )
            async with httpx.AsyncClient() as client:
                cg_resp = await client.get(cg_url, timeout=10)
                cg_resp.raise_for_status()
                cg_prices = cg_resp.json()

            for asset_id, (code, cg_id, fixed_price) in COIN_MAP.items():
                if fixed_price is not None:
                    prices[asset_id] = {'price': fixed_price, 'change': 0, 'code': code}
                elif cg_id in cg_prices:
                    prices[asset_id] = {
                        'price':  cg_prices[cg_id]['aud'],
                        'change': cg_prices[cg_id].get('aud_24h_change', 0),
                        'code':   code
                    }

        # ── Step 4: Build portfolio response ─────────────────────────────────
        assets    = []
        total_aud = 0.0

        for asset_id, balance in balances.items():
            if asset_id not in COIN_MAP or asset_id not in prices:
                continue

            code, _, _ = COIN_MAP[asset_id]
            price  = prices[asset_id]['price']
            change = prices[asset_id]['change']
            value  = balance * price

            assets.append({
                "asset_id":  asset_id,
                "code":      code,
                "name":      code,
                "balance":   balance,
                "aud_value": value,
                "usd_value": value * 0.65,
                "change_24h": change,
                "color":     ASSET_COLORS.get(code, '#666')
            })
            total_aud += value

        assets.sort(key=lambda x: x['aud_value'], reverse=True)

        total_change        = sum(a['aud_value'] * a['change_24h'] / 100 for a in assets)
        portfolio_change_pct = (total_change / total_aud * 100) if total_aud > 0 else 0

        result = {
            "total_aud_value":  total_aud,
            "total_usd_value":  total_aud * 0.65,
            "total_change_24h": portfolio_change_pct,
            "assets":           assets,
            "last_updated":     datetime.utcnow().isoformat()
        }

        # Store in cache before returning
        _set_cache(result)
        return result

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"API error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
