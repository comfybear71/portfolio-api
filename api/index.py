from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

app = FastAPI(
    title="Portfolio Crypto API",
    description="Backend API for Swyftx portfolio data",
    version="1.0.0"
)

# CORS for your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://portfolio-crypto.vercel.app",
        "https://portfolio-crypto-git-main-comfybear71.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Swyftx API Configuration
SWYFTX_API_URL = "https://api.swyftx.com.au"
SWYFTX_API_KEY = os.getenv("SWYFTX_API_KEY")

# Pydantic Models
class AssetBalance(BaseModel):
    asset_id: int
    code: str
    name: str
    balance: float
    available_balance: float
    usd_value: float
    aud_value: float
    last_price: float
    change_24h: Optional[float] = None

class PortfolioSummary(BaseModel):
    total_aud_value: float
    total_usd_value: float
    assets: List[AssetBalance]
    last_updated: datetime

class MarketData(BaseModel):
    asset_id: int
    code: str
    name: str
    last_price: float
    change_24h: float
    volume_24h: float

# Swyftx API Client
class SwyftxClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = SWYFTX_API_URL
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def get_balances(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/user/balance/",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def get_assets(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/markets/assets/",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def get_live_rates(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/live/rates/",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

def get_swyftx_client():
    if not SWYFTX_API_KEY:
        raise HTTPException(status_code=500, detail="SWYFTX_API_KEY not configured")
    return SwyftxClient(SWYFTX_API_KEY)

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
        client = get_swyftx_client()
        
        balances, assets, rates = await client.get_balances(), await client.get_assets(), await client.get_live_rates()
        
        assets_dict = {a['id']: a for a in assets}
        rates_dict = {r['asset']: r for r in rates}
        
        portfolio_assets = []
        total_aud = 0.0
        total_usd = 0.0
        
        for balance in balances:
            asset_id = balance.get('asset_id')
            asset_info = assets_dict.get(asset_id, {})
            rate_info = rates_dict.get(asset_id, {})
            
            if balance.get('balance', 0) <= 0:
                continue
            
            balance_qty = float(balance.get('balance', 0))
            last_price = float(rate_info.get('bid', 0))
            aud_value = balance_qty * last_price
            usd_value = aud_value * 0.65  # Approximate conversion
            
            portfolio_assets.append({
                "asset_id": asset_id,
                "code": asset_info.get('code', 'UNKNOWN'),
                "name": asset_info.get('name', 'Unknown Asset'),
                "balance": balance_qty,
                "available_balance": float(balance.get('available_balance', 0)),
                "usd_value": usd_value,
                "aud_value": aud_value,
                "last_price": last_price,
                "change_24h": rate_info.get('change_24h')
            })
            
            total_aud += aud_value
            total_usd += usd_value
        
        portfolio_assets.sort(key=lambda x: x['aud_value'], reverse=True)
        
        return {
            "total_aud_value": total_aud,
            "total_usd_value": total_usd,
            "assets": portfolio_assets,
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market-data")
async def get_market_data():
    try:
        client = get_swyftx_client()
        assets, rates = await client.get_assets(), await client.get_live_rates()
        
        assets_dict = {a['id']: a for a in assets}
        market_data = []
        
        for rate in rates:
            asset_id = rate.get('asset')
            asset_info = assets_dict.get(asset_id, {})
            
            market_data.append({
                "asset_id": asset_id,
                "code": asset_info.get('code', 'UNKNOWN'),
                "name": asset_info.get('name', 'Unknown'),
                "last_price": float(rate.get('bid', 0)),
                "change_24h": float(rate.get('change_24h', 0)),
                "volume_24h": float(rate.get('volume_24h', 0))
            })
        
        market_data.sort(key=lambda x: x['volume_24h'], reverse=True)
        return market_data[:50]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
