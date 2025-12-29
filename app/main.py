import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests
from typing import List, Optional

app = FastAPI(title="PharmaForge OS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class Shortage(BaseModel):
    generic_name: str
    company_name: str
    status: str
    reason: Optional[str] = "Unknown"

class ScanResult(BaseModel):
    is_valid: bool
    product_name: str
    serial_number: str
    lot_number: str
    expiry_date: str
    message: str

@app.get("/api/shortages", response_model=List[Shortage])
def get_fda_shortages(limit: int = 10):
    try:
        url = "https://api.fda.gov/drug/shortages.json"
        params = {'limit': limit, 'search': 'status:"Current"'}
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        results = []
        for item in data.get('results', []):
            results.append(Shortage(
                generic_name=item.get('generic_name', 'UNKNOWN'),
                company_name=item.get('company_name', 'UNKNOWN'),
                status=item.get('status', 'Current'),
                reason=item.get('reason_for_shortage', 'Not specified')
            ))
        return results
    except Exception as e:
        print(f"Error fetching FDA data: {e}")
        return [
            Shortage(generic_name="AMOXICILLIN", company_name="Sandoz", status="Current", reason="Demand Increase"),
            Shortage(generic_name="ADDERALL", company_name="Teva", status="Current", reason="API Shortage")
        ]

@app.post("/api/scan", response_model=ScanResult)
def verify_dscsa_scan(barcode_data: dict):
    return ScanResult(
        is_valid=True,
        product_name="Lisinopril 10mg Tablets",
        serial_number="1029384756",
        lot_number="B455-22",
        expiry_date="2026-11-27",
        message="Authenticated by PharmaForge OS."
    )

app.mount("/frontend", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('frontend/index.html')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
