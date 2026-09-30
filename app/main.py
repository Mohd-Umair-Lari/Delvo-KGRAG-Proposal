"""Small backend-only procurement AI prototype."""
from __future__ import annotations
import json, os, re, urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from fastapi import FastAPI

try:
    from .orchestration import STATE as ORCHESTRATION_STATE, run_pipeline, compare_prices, groq_advice, llm_health_check
except ImportError:
    from orchestration import STATE as ORCHESTRATION_STATE, run_pipeline, compare_prices, groq_advice, llm_health_check

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "sample_docs"
STATE = ORCHESTRATION_STATE

@asynccontextmanager
async def lifespan(_: FastAPI): run_pipeline(); yield

app = FastAPI(title="Procurement AI Prototype", version="1.0.0", lifespan=lifespan)

@app.get("/")
def root() -> dict[str, str]: return {"service": "procurement-ai-prototype", "dashboard": "/dashboard", "docs": "/docs"}

@app.get("/health")
def health() -> dict[str, Any]:
    llm = llm_health_check()
    status = "ok" if llm["status"] == "ok" else "degraded"
    return {"status": status, "llm": llm}

@app.get("/dashboard")
def dashboard() -> dict[str, Any]:
    comparison = compare_prices(STATE["facts"])
    consultant = groq_advice(comparison)
    return {"project": "Farm Alpha 50 MW Solar Plant", "documents_ingested": len(STATE["documents"]), "facts_extracted": len(STATE["facts"]), "kgraph": {"nodes": len(STATE["graph"]["nodes"]), "edges": len(STATE["graph"]["edges"]), "retrieved_documents": [x["source"] for x in STATE["agreements"]]}, "business_rules": {"comparison": "unit price", "preferred_direction": "lower is better"}, "price_comparison": comparison, "consultant": {"mode": consultant.get("mode", "rules"), "recommendation": consultant.get("recommendation", ""), "message": consultant.get("message", consultant.get("recommendation", ""))}}

@app.post("/pipeline/run")
def pipeline_run() -> dict[str, Any]: run_pipeline(); return {"status": "completed", "documents": len(STATE["documents"]), "facts": len(STATE["facts"])}
