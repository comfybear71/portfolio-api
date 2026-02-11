from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
from datetime import datetime
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
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Swyftx API Configuration
SWYFTX_API_URL = "https://api.swyftx.com.au"
SWYFTX_API_KEY = os.getenv("SWYFTX_API_KEY")

# Coin mapping (from your working Python code)
COIN_MAP = {
    1: {'code': 'AUD', 'name': 'Australian Dollar', 'cgId': None, 'fixed': 1.0},
    3: {'code': 'BTC', 'name': 'Bitcoin', 'cgId': 'bitcoin'},
    5: {'code': 'ETH', 'name': 'Ethereum', 'cgId': 'ethereum'},
    6: {'code': 'XRP', 'name': 'XRP', 'cgId': 'ripple'},
    12: {'code': 'ADA', 'name': 'Cardano', 'cgId': 'cardano'},
    130: {'code': 'SOL', 'name': 'Solana', 'cgId': 'solana'},
    73: {'code': 'DOGE', 'name': 'Dogecoin', 'cgId': 'dogecoin'},
    53: {'code': 'USDC', 'name': 'USD Coin', 'cgId': 'usd-coin'},
}

async def get_swyftx_token():
    """Get access token from Swyftx - EXACTLY like your working Python code"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SWYFTX_API_URL}/auth/refresh/",
            json={"apiKey": SWYFTX_API_KEY},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()
        return response.json().get("accessToken")

@app.get("/")
async def root():
    return {
        "message": "Portfolio Crypto API",
        "status": "operational",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

@app.get("/api/portfolio")
async def get_portfolio():
    try:
        if not SWYFTX_API_KEY:
            raise HTTPException(status_code=500, detail="SWYFTX_API_KEY not configured")
        
        # Step 1: Get token (EXACTLY like your working Python code)
        token = await get_swyftx_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # Step 2: Get balances (EXACTLY like your working Python code)
        async with httpx.AsyncClient() as client:
            balances_resp = await client.get(
                f"{SWYFTX_API_URL}/user/balance/",
                headers=headers,
                timeout=10
            )
            balances_resp.raise_for_status()
            balances_data = balances_resp.json()
        
        # Process balances (matching your working logic)
        assets = []
        total_aud = 0.0
        
        for balance in balances_data:
            asset_id = balance.get('assetId')
            available = float(balance.get('availableBalance', 0))
            
            if available <= 0 or asset_id not in COIN_MAP:
                continue
            
            coin_info = COIN_MAP[asset_id]
            
            # For now, use simple values (you can add CoinGecko later)
            # This is placeholder logic - replace with real price lookup
            asset_data = {
                "asset_id": asset_id,
                "code": coin_info['code'],
                "name": coin_info['name'],
                "balance": available,
                "aud_value": available * 100,  # Placeholder - replace with real price
                "usd_value": available * 65,   # Placeholder
                "change_24h": 0.0  # Placeholder
            }
            
            assets.append(asset_data)
            total_aud += asset_data['aud_value']
        
        # Sort by value
        assets.sort(key=lambda x: x['aud_value'], reverse=True)
        
        return {
            "total_aud_value": total_aud,
            "total_usd_value": total_aud * 0.65,
            "assets": assets,
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Swyftx API error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
