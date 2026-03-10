"""
GreenScope Backend — Production
FastAPI + PostgreSQL (SQLAlchemy async)
"""

import os, uuid, json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sqlalchemy import Column, String, Float, Integer, DateTime, Text, ForeignKey, select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

# ─── DB SETUP ───────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/greenscope"
)
# Railway/Render give postgres:// — fix the scheme
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


# ─── TABLES ─────────────────────────────────────────────────────────────────

class Supplier(Base):
    __tablename__ = "suppliers"
    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name         = Column(String, nullable=False)
    category     = Column(String, nullable=False)
    region       = Column(String, default="IN")
    annual_spend = Column(Float, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    entries      = relationship("EmissionEntry", back_populates="supplier", lazy="select")


class EmissionEntry(Base):
    __tablename__ = "emission_entries"
    id               = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    company_id       = Column(String, default="default", index=True)
    supplier_id      = Column(String, ForeignKey("suppliers.id"), nullable=True)
    supplier_name    = Column(String, nullable=True)
    description      = Column(String, nullable=False)
    scope3_category  = Column(Integer, nullable=False)
    category_name    = Column(String)
    activity_type    = Column(String, nullable=False)
    quantity         = Column(Float, nullable=False)
    unit             = Column(String, nullable=False)
    region           = Column(String, default="IN")
    reporting_year   = Column(Integer, default=2024, index=True)
    method           = Column(String, default="average_data")
    ef_value         = Column(Float)
    ef_unit          = Column(String)
    ef_source        = Column(String)
    ef_uncertainty   = Column(Float)
    co2e_kg          = Column(Float)
    co2e_tonnes      = Column(Float)
    confidence_score = Column(Float)
    uncertainty_low  = Column(Float)
    uncertainty_high = Column(Float)
    warnings         = Column(Text, default="[]")
    created_at       = Column(DateTime, default=datetime.utcnow)
    supplier         = relationship("Supplier", back_populates="entries")


async def get_db():
    async with SessionLocal() as session:
        yield session


# ─── EMISSION FACTORS ───────────────────────────────────────────────────────

GRID_FACTORS = {
    "IN": 0.716, "IN-MH": 0.680, "IN-DL": 0.709, "IN-KA": 0.740,
    "IN-TN": 0.820, "IN-GJ": 0.650, "IN-WB": 0.930, "IN-UP": 0.850,
}
FUEL_FACTORS = {
    "diesel":        {"value": 2.688, "unit": "kgCO2e/litre"},
    "petrol":        {"value": 2.315, "unit": "kgCO2e/litre"},
    "natural_gas":   {"value": 2.204, "unit": "kgCO2e/kg"},
    "coal_thermal":  {"value": 2.422, "unit": "kgCO2e/kg"},
    "lpg":           {"value": 1.557, "unit": "kgCO2e/litre"},
    "aviation_fuel": {"value": 2.520, "unit": "kgCO2e/litre"},
    "furnace_oil":   {"value": 3.179, "unit": "kgCO2e/litre"},
}
TRANSPORT_FACTORS = {
    "road_freight_hgv":     {"value": 0.0962, "unit": "kgCO2e/tonne.km"},
    "road_freight_lgv":     {"value": 0.1676, "unit": "kgCO2e/tonne.km"},
    "rail_freight":         {"value": 0.0035, "unit": "kgCO2e/tonne.km"},
    "sea_freight":          {"value": 0.0116, "unit": "kgCO2e/tonne.km"},
    "air_freight":          {"value": 0.8670, "unit": "kgCO2e/tonne.km"},
    "bus":                  {"value": 0.0390, "unit": "kgCO2e/passenger.km"},
    "flight_domestic":      {"value": 0.2550, "unit": "kgCO2e/passenger.km"},
    "flight_international": {"value": 0.1950, "unit": "kgCO2e/passenger.km"},
    "car_petrol":           {"value": 0.1710, "unit": "kgCO2e/passenger.km"},
    "two_wheeler":          {"value": 0.0830, "unit": "kgCO2e/passenger.km"},
}
MATERIAL_FACTORS = {
    "steel_virgin":     {"value": 1.890, "unit": "kgCO2e/kg"},
    "steel_recycled":   {"value": 0.430, "unit": "kgCO2e/kg"},
    "aluminium_virgin": {"value": 11.46, "unit": "kgCO2e/kg"},
    "cement":           {"value": 0.830, "unit": "kgCO2e/kg"},
    "plastic_pet":      {"value": 3.140, "unit": "kgCO2e/kg"},
    "paper_virgin":     {"value": 1.290, "unit": "kgCO2e/kg"},
    "glass":            {"value": 0.850, "unit": "kgCO2e/kg"},
    "copper":           {"value": 3.010, "unit": "kgCO2e/kg"},
}
WASTE_FACTORS = {
    "landfill_mixed": {"value": 467.0,  "unit": "kgCO2e/tonne"},
    "incineration":   {"value": 1000.0, "unit": "kgCO2e/tonne"},
    "composting":     {"value": 10.0,   "unit": "kgCO2e/tonne"},
    "recycling":      {"value": -950.0, "unit": "kgCO2e/tonne"},
}
SPEND_FACTORS = {
    "steel_manufacturing": 85.0, "cement_manufacturing": 120.0,
    "chemical_manufacturing": 95.0, "auto_components": 45.0,
    "it_services": 8.0, "logistics_services": 60.0,
    "construction": 75.0, "food_processing": 40.0,
    "pharma": 35.0, "textiles": 55.0,
}
SCOPE3_NAMES = {
    1:"Purchased Goods & Services", 2:"Capital Goods", 3:"Fuel & Energy Activities",
    4:"Upstream Transportation", 5:"Waste Generated", 6:"Business Travel",
    7:"Employee Commuting", 8:"Upstream Leased Assets", 9:"Downstream Transportation",
    10:"Processing of Sold Products", 11:"Use of Sold Products", 12:"End-of-Life Treatment",
    13:"Downstream Leased Assets", 14:"Franchises", 15:"Investments",
}
BRSR_MANDATORY = {1, 3, 4, 6, 7}


# ─── CALCULATION ENGINE ─────────────────────────────────────────────────────

def resolve_ef(at: str, unit: str, region: str, custom: Optional[float]) -> dict:
    if custom is not None:
        return {"value": custom, "unit": f"kgCO2e/{unit}", "source": "custom", "uncertainty_pct": 5.0}
    at = at.lower()
    if at == "electricity":
        v = GRID_FACTORS.get(region, GRID_FACTORS["IN"])
        return {"value": v, "unit": "kgCO2e/kWh", "source": "CEA India 2023", "uncertainty_pct": 5.0}
    for table, src, unc in [
        (FUEL_FACTORS, "IPCC AR6", 3.0), (TRANSPORT_FACTORS, "GHG Protocol", 8.0),
        (MATERIAL_FACTORS, "IPCC AR6", 15.0), (WASTE_FACTORS, "IPCC AR6", 20.0),
    ]:
        if at in table:
            return {**table[at], "source": src, "uncertainty_pct": unc}
    v = SPEND_FACTORS.get(at, 50.0)
    return {"value": v, "unit": "kgCO2e/INR_lakh", "source": "SEBI BRSR", "uncertainty_pct": 40.0}


def compute(quantity: float, unit: str, ef: dict) -> float:
    q = quantity
    if unit == "MWh": q *= 1000
    if unit == "GJ":  q *= 277.78
    if unit == "kg" and "tonne" in ef["unit"]: q /= 1000
    if unit == "INR": q /= 100_000
    return max(0.0, round(q * ef["value"], 4))


def make_entry(d: dict) -> dict:
    ef = resolve_ef(d["activity_type"], d["unit"], d.get("region", "IN"), d.get("custom_ef"))
    co2e_kg = compute(d["quantity"], d["unit"], ef)
    co2e_t  = co2e_kg / 1000.0
    conf    = max(0.1, min(1.0, 1.0
        + {"supplier_specific": 0, "average_data": -0.1, "spend_based": -0.35}.get(d.get("method", "average_data"), -0.1)
        + (-0.3 if ef["source"] == "default_estimate" else -0.05 if ef["source"] == "SEBI BRSR" else 0)
    ))
    margin  = co2e_t * ef["uncertainty_pct"] / 100
    cat     = d.get("scope3_category", 3)
    warns   = []
    if d.get("method") == "spend_based": warns.append("Spend-based — collect activity data for accuracy")
    if ef["uncertainty_pct"] > 20: warns.append(f"High uncertainty ({ef['uncertainty_pct']}%)")
    return dict(
        id=str(uuid.uuid4()), company_id=d.get("company_id","default"),
        supplier_id=d.get("supplier_id"), supplier_name=d.get("supplier_name"),
        description=d["description"], scope3_category=cat,
        category_name=SCOPE3_NAMES.get(cat, "Unknown"), activity_type=d["activity_type"],
        quantity=d["quantity"], unit=d["unit"], region=d.get("region","IN"),
        reporting_year=d.get("reporting_year", 2024), method=d.get("method","average_data"),
        ef_value=ef["value"], ef_unit=ef["unit"], ef_source=ef["source"],
        ef_uncertainty=ef["uncertainty_pct"], co2e_kg=co2e_kg, co2e_tonnes=round(co2e_t,6),
        confidence_score=round(conf,2), uncertainty_low=round(max(0,co2e_t-margin),6),
        uncertainty_high=round(co2e_t+margin,6), warnings=json.dumps(warns),
        created_at=datetime.utcnow(),
    )


def row_to_dict(e: EmissionEntry) -> dict:
    return {
        "id": e.id, "company_id": e.company_id, "supplier_id": e.supplier_id,
        "supplier_name": e.supplier_name, "description": e.description,
        "scope3_category": e.scope3_category, "category_name": e.category_name,
        "activity_type": e.activity_type, "quantity": e.quantity, "unit": e.unit,
        "region": e.region, "reporting_year": e.reporting_year, "method": e.method,
        "emission_factor": {"value": e.ef_value, "unit": e.ef_unit, "source": e.ef_source, "uncertainty_pct": e.ef_uncertainty},
        "co2e_kg": e.co2e_kg, "co2e_tonnes": e.co2e_tonnes,
        "confidence_score": e.confidence_score, "uncertainty_low": e.uncertainty_low,
        "uncertainty_high": e.uncertainty_high,
        "warnings": json.loads(e.warnings) if e.warnings else [],
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ─── PYDANTIC ───────────────────────────────────────────────────────────────

class EntryReq(BaseModel):
    company_id: str = "default"
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    description: str
    scope3_category: int = Field(ge=1, le=15)
    activity_type: str
    quantity: float = Field(gt=0)
    unit: str
    region: str = "IN"
    reporting_year: int = 2024
    method: str = "average_data"
    custom_ef: Optional[float] = None

class SupplierReq(BaseModel):
    name: str
    category: str
    region: str = "IN"
    annual_spend_inr: Optional[float] = None


# ─── APP ────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="GreenScope API", version="1.0.0", lifespan=lifespan)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "healthy", "version": "1.0.0", "db": "postgresql"}


@app.post("/api/entries")
async def add_entry(req: EntryReq, db: AsyncSession = Depends(get_db)):
    data = make_entry(req.model_dump())
    entry = EmissionEntry(**data)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return row_to_dict(entry)


@app.get("/api/entries")
async def get_entries(company_id: str = "default", year: int = 2024, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(EmissionEntry)
        .where(EmissionEntry.company_id == company_id, EmissionEntry.reporting_year == year)
        .order_by(EmissionEntry.created_at.desc())
    )
    return [row_to_dict(e) for e in res.scalars().all()]


@app.delete("/api/entries/{entry_id}")
async def delete_entry(entry_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(EmissionEntry).where(EmissionEntry.id == entry_id))
    await db.commit()
    return {"deleted": True}


@app.get("/api/dashboard")
async def dashboard(company_id: str = "default", year: int = 2024, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(EmissionEntry).where(EmissionEntry.company_id == company_id, EmissionEntry.reporting_year == year)
    )
    records = res.scalars().all()
    if not records:
        return {"total_co2e_tonnes": 0, "record_count": 0, "by_category": [], "by_supplier": [],
                "top_activities": [], "brsr_ready": False, "completeness_pct": 0, "avg_confidence": 0,
                "categories_covered": [], "categories_missing": list(range(1, 16))}

    total = sum(r.co2e_tonnes for r in records)
    cat_map = {}
    for r in records:
        c = r.scope3_category
        cat_map.setdefault(c, {"category": c, "name": SCOPE3_NAMES.get(c,"?"), "co2e_tonnes": 0.0, "count": 0})
        cat_map[c]["co2e_tonnes"] += r.co2e_tonnes
        cat_map[c]["count"] += 1
    by_category = sorted(
        [{**v, "co2e_tonnes": round(v["co2e_tonnes"],4), "pct": round(v["co2e_tonnes"]/total*100,1) if total else 0}
         for v in cat_map.values()], key=lambda x: x["co2e_tonnes"], reverse=True)

    sup_map = {}
    for r in records:
        k = r.supplier_name or "Direct"; sup_map[k] = sup_map.get(k,0) + r.co2e_tonnes
    by_supplier = sorted([{"name":k,"co2e_tonnes":round(v,4)} for k,v in sup_map.items()], key=lambda x:-x["co2e_tonnes"])[:10]

    act_map = {}
    for r in records:
        act_map[r.activity_type] = act_map.get(r.activity_type,0) + r.co2e_tonnes
    top_activities = sorted([{"activity":k,"co2e_tonnes":round(v,4)} for k,v in act_map.items()], key=lambda x:-x["co2e_tonnes"])[:5]

    covered = set(cat_map.keys())
    return {
        "total_co2e_tonnes": round(total,4), "record_count": len(records),
        "by_category": by_category, "by_supplier": by_supplier, "top_activities": top_activities,
        "brsr_ready": BRSR_MANDATORY.issubset(covered),
        "completeness_pct": round(len(covered)/15*100,1),
        "avg_confidence": round(sum(r.confidence_score for r in records)/len(records),2),
        "categories_covered": list(covered),
        "categories_missing": [c for c in range(1,16) if c not in covered],
    }


@app.post("/api/calculate/preview")
async def preview(req: EntryReq):
    data = make_entry(req.model_dump())
    data["emission_factor"] = {"value":data.pop("ef_value"),"unit":data.pop("ef_unit"),
                                "source":data.pop("ef_source"),"uncertainty_pct":data.pop("ef_uncertainty")}
    data["warnings"] = json.loads(data["warnings"]) if data.get("warnings") else []
    data.pop("created_at", None)
    return data


@app.post("/api/suppliers")
async def add_supplier(req: SupplierReq, db: AsyncSession = Depends(get_db)):
    s = Supplier(name=req.name, category=req.category, region=req.region, annual_spend=req.annual_spend_inr)
    db.add(s); await db.commit(); await db.refresh(s)
    return {"id":s.id,"name":s.name,"category":s.category,"region":s.region,"annual_spend":s.annual_spend}


@app.get("/api/suppliers")
async def get_suppliers(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Supplier))
    out = []
    for s in res.scalars().all():
        er = await db.execute(select(EmissionEntry).where(EmissionEntry.supplier_id == s.id))
        entries = er.scalars().all()
        out.append({"id":s.id,"name":s.name,"category":s.category,"region":s.region,
                    "total_co2e_tonnes":round(sum(e.co2e_tonnes for e in entries),4),"record_count":len(entries)})
    return sorted(out, key=lambda x: x["total_co2e_tonnes"], reverse=True)


@app.get("/api/factors")
def factors():
    return {"electricity":{r:f"{v} kgCO2e/kWh" for r,v in GRID_FACTORS.items()},
            "fuels":FUEL_FACTORS,"transport":TRANSPORT_FACTORS,"materials":MATERIAL_FACTORS,"waste":WASTE_FACTORS}


@app.get("/api/scope3/categories")
def categories():
    return [{"id":k,"name":v,"brsr_mandatory":k in BRSR_MANDATORY} for k,v in SCOPE3_NAMES.items()]
