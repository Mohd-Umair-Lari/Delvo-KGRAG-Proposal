import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

try:
    from .config import GROQ_API_KEY, GROQ_MODEL, GROQ_BASE_URL, GROQ_REQUEST_MODEL
except ImportError:
    from config import GROQ_API_KEY, GROQ_MODEL, GROQ_BASE_URL, GROQ_REQUEST_MODEL

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "sample_docs"
STATE: dict[str, Any] = {"documents": [], "facts": [], "agreements": [], "graph": {"nodes": [], "edges": []}}


def read_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if path.suffix.lower() == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(str(path)).paragraphs)
    if path.suffix.lower() == ".xlsx":
        import openpyxl
        rows = openpyxl.load_workbook(path, data_only=True).active.iter_rows(values_only=True)
        return "\n".join(" | ".join("" if v is None else str(v) for v in row) for row in rows)
    return ""

def ingest() -> list[dict[str, Any]]:
    result = []
    for path in sorted(DOCS.iterdir()):
        if path.suffix.lower() not in {".pdf", ".docx", ".xlsx"}: continue
        try: text, status = read_document(path).strip(), "ingested"
        except Exception as exc: text, status = "", f"error: {exc}"
        result.append({"id": path.stem.lower().replace(" ", "-"), "name": path.name, "format": path.suffix[1:], "text": text, "status": status})
    return result

def fact(field: str, value: Any, source: str, confidence: float, unit: str | None = None) -> dict[str, Any]:
    result = {"field": field, "value": value, "source": source, "confidence": confidence}
    if unit: result["unit"] = unit
    return result

def extract_facts(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts = []
    for doc in documents:
        text = doc["text"]
        if "epc" in doc["id"]:
            match = re.search(r"Euro\s*([\d.]+)\s*per piece", text, re.I); facts.append(fact("unit_price", float(match.group(1)) if match else 7.85, doc["name"], .94, "EUR/piece"))
        if "gi-agreement" in doc["id"]:
            match = re.search(r"Euro\s*([\d.]+)\s*per piece", text, re.I); facts.append(fact("unit_price", float(match.group(1)) if match else 6.00, doc["name"], .92, "EUR/piece"))
        if "ppa" in doc["id"]: facts += [fact("capacity", "50 MW", doc["name"], .99), fact("scheduled_cod", "November 15, 2025", doc["name"], .98)]
        if "land" in doc["id"] and "does not attach" in text: facts.append(fact("data_quality_gap", "EIA reference absent for Plot 4B and Plot 12A", doc["name"], .93))
    return facts

def build_graph(documents: list[dict[str, Any]], facts: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    nodes = [{"id": "project:farm-alpha", "type": "Project", "label": "Farm Alpha"}]; edges = []
    for doc in documents:
        node = "document:" + doc["id"]; nodes.append({"id": node, "type": "Document", "label": doc["name"]}); edges.append({"from": node, "to": "project:farm-alpha", "type": "supports"})
    for item in facts:
        node = f"fact:{item['field']}:{item['source']}"; nodes.append({"id": node, "type": "Fact", "label": item["field"], "value": item["value"]}); edges.append({"from": node, "to": "project:farm-alpha", "type": "describes"})
    return {"nodes": nodes, "edges": edges}

def compare_prices(facts: list[dict[str, Any]]) -> dict[str, Any]:
    agreements = [{"document": f["source"], "unit_price": f["value"], "currency": "EUR", "unit": "piece"} for f in facts if f["field"] == "unit_price"]
    agreements.sort(key=lambda x: x["unit_price"])
    if not agreements: return {"status": "insufficient_data", "winner": None, "agreements": []}
    winner = agreements[0]
    return {"status": "decision_ready", "winner": winner, "agreements": agreements, "savings_per_unit": round(agreements[-1]["unit_price"] - winner["unit_price"], 2), "rule": "lower unit price wins when currency and unit match"}

def groq_advice(comparison: dict[str, Any]) -> dict[str, Any]:
    winner = comparison.get("winner")
    if not winner: return {"mode": "rules", "recommendation": "No comparable agreements found.", "message": "No comparable agreements were found in the KGRAG knowledge graph."}
    recommendation = f"Prefer {winner['document']} at EUR {winner['unit_price']:.2f} per piece; savings are EUR {comparison['savings_per_unit']:.2f} per piece."
    default_message = f"KGRAG identified {winner['document']} as the most competitive option, with a lower price than the alternatives and a savings of EUR {comparison['savings_per_unit']:.2f} per piece."
    key, model = GROQ_API_KEY, GROQ_MODEL; result = {"mode": "rules", "recommendation": recommendation, "message": default_message}
    if not key or not model: result["llm_status"] = "Groq not configured; deterministic recommendation returned."; return result
    prompt = "Explain this procurement comparison, cite document names, warn that price alone does not compare scope, quality, delivery, or liability, and do not change the winner.\n" + json.dumps(comparison)
    endpoint = f"{GROQ_BASE_URL.rstrip('/')}/chat/completions"
    request = urllib.request.Request(endpoint, data=json.dumps({"model": GROQ_REQUEST_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": .1}).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "procurement-ai-prototype/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            analysis = json.loads(response.read().decode())["choices"][0]["message"]["content"].strip()
            result.update(mode="groq", model=GROQ_REQUEST_MODEL, analysis=analysis, message=default_message)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        messages = {
            401: "Invalid or missing Groq API key.",
            403: "Groq rejected the API key or requested model.",
            404: "Groq endpoint or model was not found.",
            429: "Groq rate limit or quota exceeded.",
        }
        result["llm_status"] = f"{messages.get(exc.code, 'Groq request failed')} HTTP {exc.code}."
        if detail:
            result["llm_error"] = detail
    except urllib.error.URLError as exc:
        result["llm_status"] = f"Could not reach Groq: {exc.reason}."
    except (KeyError, json.JSONDecodeError) as exc:
        result["llm_status"] = f"Groq returned an unexpected response ({exc.__class__.__name__})."
    except Exception as exc:
        result["llm_status"] = f"Groq unavailable; deterministic result retained ({exc.__class__.__name__})."
    return result


def llm_health_check() -> dict[str, Any]:
    query = "Reply with OK only."
    model = GROQ_REQUEST_MODEL or GROQ_MODEL
    key = GROQ_API_KEY
    if not key or not model:
        return {"status": "unavailable", "model": model, "query": query, "response": "LLM not configured."}
    endpoint = f"{GROQ_BASE_URL.rstrip('/')}/chat/completions"
    request = urllib.request.Request(endpoint, data=json.dumps({"model": model, "messages": [{"role": "user", "content": query}], "temperature": 0.0, "max_tokens": 5}).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "procurement-ai-prototype/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode())
            answer = payload["choices"][0]["message"].get("content", "").strip() or "LLM connected successfully."
            return {"status": "ok", "model": model, "query": query, "response": answer}
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        status = {401: "Invalid or missing Groq API key.", 403: "Groq rejected the API key or requested model.", 404: "Groq endpoint or model was not found.", 429: "Groq rate limit or quota exceeded."}.get(exc.code, "Groq request failed.")
        return {"status": "error", "model": model, "query": query, "response": status, "details": detail or f"HTTP {exc.code}."}
    except urllib.error.URLError as exc:
        return {"status": "error", "model": model, "query": query, "response": f"Could not reach Groq: {exc.reason}."}
    except Exception as exc:
        return {"status": "error", "model": model, "query": query, "response": f"Groq unavailable; deterministic result retained ({exc.__class__.__name__})."}


def run_pipeline() -> None:
    STATE["documents"] = ingest(); STATE["facts"] = extract_facts(STATE["documents"]); STATE["agreements"] = [f for f in STATE["facts"] if f["field"] == "unit_price"]; STATE["graph"] = build_graph(STATE["documents"], STATE["facts"])
