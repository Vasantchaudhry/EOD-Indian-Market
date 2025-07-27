from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from bs4 import BeautifulSoup
import yfinance as yf
import requests
import datetime
import pytz
import logging

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
IST = pytz.timezone('Asia/Kolkata')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1'
}

def get_eod_data():
    """Get end-of-day market data"""
    data = {
        "nifty50": {},
        "banknifty": {},
        "vix": {},
        "other_indices": [],
        "gainers": [],
        "losers": [],
        "pcr": {"value": 0, "sentiment": "N/A"},
        "pe_ratio": 0,
        "results": []
    }
    
    try:
        # Get current date in IST
        today = datetime.datetime.now(IST)
        
        # Only fetch data after market close (3:30 PM IST)
        if today.hour < 15 or (today.hour == 15 and today.minute < 30):
            logger.info("Market still open - using previous close data")
            today = today - datetime.timedelta(days=1)
        
        # Format date for API calls
        formatted_date = today.strftime("%d-%b-%Y")
        
        # Fetch index data
        url = "https://www.nseindia.com/api/allIndices"
        response = requests.get(url, headers=HEADERS)
        index_data = response.json()["data"]
        
        for index in index_data:
            if index["index"] in ["NIFTY 50", "NIFTY BANK", "INDIA VIX"]:
                change = index["variation"]
                change_pct = index["percentChange"]
                
                if index["index"] == "NIFTY 50":
                    data["nifty50"] = {
                        "name": "Nifty 50",
                        "price": index["last"],
                        "change": change,
                        "change_pct": change_pct
                    }
                elif index["index"] == "NIFTY BANK":
                    data["banknifty"] = {
                        "name": "Bank Nifty",
                        "price": index["last"],
                        "change": change,
                        "change_pct": change_pct
                    }
                elif index["index"] == "INDIA VIX":
                    data["vix"] = {
                        "name": "India VIX",
                        "price": index["last"],
                        "change": change,
                        "change_pct": change_pct
                    }
            elif "NIFTY" in index["index"]:
                data["other_indices"].append({
                    "name": index["index"].replace("NIFTY ", ""),
                    "price": index["last"],
                    "change": index["variation"],
                    "change_pct": index["percentChange"]
                })
        
        # Get top gainers and losers
        gainers_url = "https://www.nseindia.com/api/live-analysis-variations?index=gainers"
        losers_url = "https://www.nseindia.com/api/live-analysis-variations?index=losers"
        
        gainers_res = requests.get(gainers_url, headers=HEADERS)
        losers_res = requests.get(losers_url, headers=HEADERS)
        
        data["gainers"] = gainers_res.json()["NIFTY"]["data"][:5]
        data["losers"] = losers_res.json()["NIFTY"]["data"][:5]
        
        # Get PCR
        pcr_url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        pcr_res = requests.get(pcr_url, headers=HEADERS)
        pcr_data = pcr_res.json()
        pcr_value = pcr_data["filtered"]["PCR"]["value"]
        
        if pcr_value > 1.2:
            sentiment = "Bearish"
        elif pcr_value < 0.8:
            sentiment = "Bullish"
        else:
            sentiment = "Neutral"
            
        data["pcr"] = {"value": pcr_value, "sentiment": sentiment}
        
        # Get P/E Ratio
        pe_url = "https://www.nseindia.com/api/market-data-pe"
        pe_res = requests.get(pe_url, headers=HEADERS)
        pe_data = pe_res.json()["data"]
        for item in pe_data:
            if item["key"] == "NIFTY 50":
                data["pe_ratio"] = item["pe"]
                break
        
        # Get upcoming results
        results_url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&from_date={formatted_date}&to_date={formatted_date}"
        results_res = requests.get(results_url, headers=HEADERS)
        for item in results_res.json():
            if "Result" in item["subject"]:
                data["results"].append({
                    "company": item["symbol"],
                    "date": datetime.datetime.strptime(
                        item["recDt"], "%d-%b-%Y"
                    ).strftime("%d %b %Y")
                })
        data["results"] = data["results"][:5]
        
    except Exception as e:
        logger.error(f"Error fetching EOD data: {str(e)}")
    
    return data

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """End-of-Day Dashboard"""
    try:
        # Get market data
        market_data = get_eod_data()
        
        # Get current date/time
        now = datetime.datetime.now(IST)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "nifty50": market_data["nifty50"],
            "banknifty": market_data["banknifty"],
            "vix": market_data["vix"],
            "other_indices": market_data["other_indices"],
            "gainers": market_data["gainers"],
            "losers": market_data["losers"],
            "pcr": market_data["pcr"],
            "pe_ratio": market_data["pe_ratio"],
            "results": market_data["results"],
            "updated_at": now.strftime("%d %b %Y, %I:%M %p"),
            "market_status": "Closed" if now > market_close else "Open"
        })
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        return "Error loading dashboard. Please try again later."

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
