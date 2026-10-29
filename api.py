"""FastAPI backend: serves the prediction API and the web frontend.

Run:  uvicorn api:app --reload      then open http://127.0.0.1:8000
API docs (auto-generated): http://127.0.0.1:8000/docs
"""
import json
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from src.config import (AMENITIES, AMENITY_GROUPS, AUDIT_PATH, CITIES, FIGURES_DIR, MAX_BHK,
                        MODEL_PATH, ROOT)
from src.insights import compare, parse_listing, valuate, what_if
from src.predict import load_artifacts, predict

FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="HomeValue India API", version="3.0",
              description="Predicts apartment prices in Indian metros with a stacked ML ensemble.")


class PropertyInput(BaseModel):
    city: str = Field(..., description=f"One of {CITIES}", examples=["Mumbai"])
    locality: str = Field(..., min_length=2, max_length=80, examples=["Thane West"])
    area_sqft: float = Field(..., ge=200, le=20_000, description="Area in sq ft", examples=[1050])
    bhk: int = Field(..., ge=1, le=MAX_BHK, examples=[2])
    resale: bool = Field(False, description="True for a resale property, False for new")
    amenities: List[str] = Field(default_factory=list, examples=[["LiftAvailable", "CarParking"]])

    @field_validator("city")
    @classmethod
    def known_city(cls, v):
        if v not in CITIES:
            raise ValueError(f"city must be one of {CITIES}")
        return v

    @field_validator("amenities")
    @classmethod
    def known_amenities(cls, v):
        unknown = sorted(set(v) - set(AMENITIES))
        if unknown:
            raise ValueError(f"unknown amenities: {unknown}")
        return v


class Prediction(BaseModel):
    price: int
    low: int
    high: int
    coverage: float
    price_per_sqft: int
    locality: str
    locality_known: bool
    locality_median_ppsf: Optional[int]
    locality_listings: int
    warnings: List[str]


def require_model():
    if not MODEL_PATH.exists():
        raise HTTPException(503, "Model not trained. Run `python -m src.train` and `python -m src.evaluate`.")


@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": MODEL_PATH.exists()}


@app.get("/api/options")
def options():
    """Everything the form needs: cities, localities, amenity groups, input ranges."""
    require_model()
    _, meta, localities = load_artifacts()
    return {"cities": CITIES, "localities": localities, "amenity_groups": AMENITY_GROUPS,
            "area_range": meta["area_range"], "bhk_range": meta["bhk_range"]}


@app.get("/api/model-info")
def model_info():
    require_model()
    meta = load_artifacts()[1]
    return {**meta, "data_audit": json.loads(AUDIT_PATH.read_text()) if AUDIT_PATH.exists() else None}


@app.post("/api/predict", response_model=Prediction)
def predict_price(p: PropertyInput):
    require_model()
    return predict(p.city, p.locality, p.area_sqft, p.bhk, p.resale, p.amenities)


class ValuateInput(BaseModel):
    property: PropertyInput
    asking_price: float = Field(..., ge=100_000, le=1_000_000_000, description="Asking price in ₹")


class ListingText(BaseModel):
    text: str = Field(..., min_length=3, max_length=4000)


class CompareInput(BaseModel):
    properties: List[PropertyInput] = Field(..., min_length=2, max_length=6)


@app.post("/api/valuate")
def valuate_price(body: ValuateInput):
    """Judge an asking price against the model's fair range for the same property."""
    require_model()
    p = body.property
    estimate = predict(p.city, p.locality, p.area_sqft, p.bhk, p.resale, p.amenities)
    return {"estimate": estimate, **valuate(estimate, body.asking_price)}


@app.post("/api/what-if")
def what_if_scenarios(p: PropertyInput):
    """Price impact of changing area, BHK, property type or adding an influential amenity."""
    require_model()
    return what_if(p.city, p.locality, p.area_sqft, p.bhk, p.resale, p.amenities)


@app.post("/api/compare")
def compare_properties(body: CompareInput):
    """Estimate several properties and rank them by price per sq ft (best value first)."""
    require_model()
    return compare([p.model_dump() for p in body.properties])


@app.post("/api/parse-listing")
def parse_listing_text(body: ListingText):
    """Extract area, BHK, asking price, type and locality from pasted or OCR-read listing text."""
    require_model()
    return parse_listing(body.text)


app.mount("/figures", StaticFiles(directory=FIGURES_DIR), name="figures")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
