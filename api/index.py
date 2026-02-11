# index.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx
import os
from datetime import datetime
from typing import Optional, List, Dict
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
        "https://portfolio-crypto.vercel.app",  # Your frontend URL
        "https://portfolio-crypto-git-main-yourusername.vercel.app"  # Preview deployments
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# Swyftx API Configuration
SWYFTX_API_URL = "https://api.swyftx.com.au"
SWYFTX_API_KEY = os.getenv("SWYFTX_API_KEY")

if not SWYFTX_API_KEY:
    raise ValueError("SWYFTX_API_KEY environment variable not set")

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
    change_7d: Optional[float] = None
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
    
    async def get_balances(self) -> List[Dict]:
        """Fetch user balances from Swyftx"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/user/balance/",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def get_assets(self) -> List[Dict]:
        """Fetch all available assets/markets"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/markets/assets/",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def get_live_rates(self) -> List[Dict]:
        """Fetch live market rates"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/live/rates/",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

# Dependency
def get_swyftx_client():
    return SwyftxClient(SWYFTX_API_KEY)

# API Routes

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

@app.get("/api/portfolio", response_model=PortfolioSummary)
async def get_portfolio(client: SwyftxClient = Depends(get_swyftx_client)):
    """
    Get complete portfolio data including balances and current values
    """
    try:
        # Fetch data concurrently
        balances_task = client.get_balances()
        assets_task = client.get_assets()
        rates_task = client.get_live_rates()
        
        balances, assets, rates = await asyncio.gather(
            balances_task, assets_task, rates_task
        )
        
        # Create lookup dictionaries
        assets_dict = {a['id']: a for a in assets}
        rates_dict = {r['asset']: r for r in rates}
        
        portfolio_assets = []
        total_aud = 0.0
        total_usd = 0.0
        
        for balance in balances:
            asset_id = balance.get('asset_id')
            asset_info = assets_dict.get(asset_id, {})
            rate_info = rates_dict.get(asset_id, {})
            
            # Skip zero balances
            if balance.get('balance', 0) <= 0:
                continue
            
            # Calculate values
            balance_qty = float(balance.get('balance', 0))
            last_price = float(rate_info.get('bid', 0))
            aud_value = balance_qty * last_price
            
            # Get USD value (approximate using rate or separate call)
            usd_rate = float(rate_info.get('bid_usd', last_price * 0.65))  # Fallback conversion
            usd_value = balance_qty * usd_rate
            
            asset_data = AssetBalance(
                asset_id=asset_id,
                code=asset_info.get('code', 'UNKNOWN'),
                name=asset_info.get('name', 'Unknown Asset'),
                balance=balance_qty,
                available_balance=float(balance.get('available_balance', 0)),
                usd_value=usd_value,
                aud_value=aud_value,
                last_price=last_price,
                change_24h=rate_info.get('change_24h')
            )
            
            portfolio_assets.append(asset_data)
            total_aud += aud_value
            total_usd += usd_value
        
        # Sort by value (highest first)
        portfolio_assets.sort(key=lambda x: x.aud_value, reverse=True)
        
        return PortfolioSummary(
            total_aud_value=total_aud,
            total_usd_value=total_usd,
            assets=portfolio_assets,
            last_updated=datetime.utcnow()
        )
        
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Swyftx API error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/api/market-data", response_model=List[MarketData])
async def get_market_data(client: SwyftxClient = Depends(get_swyftx_client)):
    """
    Get current market data for all tracked assets
    """
    try:
        assets, rates = await asyncio.gather(
            client.get_assets(),
            client.get_live_rates()
        )
        
        rates_dict = {r['asset']: r for r in rates}
        assets_dict = {a['id']: a for a in assets}
        
        market_data = []
        for rate in rates:
            asset_id = rate.get('asset')
            asset_info = assets_dict.get(asset_id, {})
            
            market_data.append(MarketData(
                asset_id=asset_id,
                code=asset_info.get('code', 'UNKNOWN'),
                name=asset_info.get('name', 'Unknown'),
                last_price=float(rate.get('bid', 0)),
                change_24h=float(rate.get('change_24h', 0)),
                change_7d=rate.get('change_7d'),
                volume_24h=float(rate.get('volume_24h', 0))
            ))
        
        # Sort by volume (most traded first)
        market_data.sort(key=lambda x: x.volume_24h, reverse=True)
        return market_data[:50]  # Return top 50 by volume
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/asset/{asset_code}")
async def get_asset_details(
    asset_code: str,
    client: SwyftxClient = Depends(get_swyftx_client)
):
    """
    Get detailed information for a specific asset
    """
    try:
        assets = await client.get_assets()
        rates = await client.get_live_rates()
        
        # Find asset by code (case insensitive)
        asset = next(
            (a for a in assets if a['code'].upper() == asset_code.upper()),
            None
        )
        
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        rate = next(
            (r for r in rates if r['asset'] == asset['id']),
            {}
        )
        
        return {
            "asset_id": asset['id'],
            "code": asset['code'],
            "name": asset['name'],
            "type": asset.get('type'),
            "current_price_aud": rate.get('bid'),
            "current_price_usd": rate.get('bid_usd'),
            "change_24h": rate.get('change_24h'),
            "change_7d": rate.get('change_7d'),
            "high_24h": rate.get('high_24h'),
            "low_24h": rate.get('low_24h'),
            "volume_24h": rate.get('volume_24h')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# For Vercel serverless deployment
import asyncio
