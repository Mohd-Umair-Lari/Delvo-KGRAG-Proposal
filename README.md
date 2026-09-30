# Procurement AI Data Integration Prototype

Implements the blueprint architecture (`Prototype Blueprint_ Data Integration for Procurement AI.pdf`)
against the Farm Alpha sample corpus. It builds the "data plumbing" that intercepts
fragmented, multi-format enterprise inputs, normalizes them, resolves entities, and
serves a single pristine **Golden Record** to a mock AI agent — proving the
"Garbage In, Garbage Out" fragmentation problem is solved.

## Run

From the project root:

```bash
python -m uvicorn app.main:app --reload
```

Open http://localhost:8000 for the dashboard. Interactive API docs at http://localhost:8000/docs.

> Earlier `ImportError: cannot import name 'STATE' from 'app'` was caused by an
> `app.py` module colliding with the `app/` package directory. The code is now a
> proper package; always launch it as `app.main:app` from the project root.

## Architecture mapping (blueprint → code)

| Blueprint layer | Module | Function in prototype |
|---|---|---|
| 1. iPaaS Middleware Connectors | [connectors.py](app/connectors.py) | PDF/DOCX/XLSX connectors normalize each source system into a common JSON record. |
| 2. AI-Powered OCR & NLP | [extraction.py](app/extraction.py) | Converts raw text into typed, sourced, confidence-scored facts (`supplier_name`, `unit_price`, `scheduled_cod`, …). Deterministic + offline; swap the body for Tesseract + an LLM without touching downstream layers. |
| 3. Entity Resolution (MDM) | [resolution.py](app/resolution.py) | Levenshtein-style fuzzy matching (stdlib `difflib`) merges `Farm Alpha` + `Farm Alpha SPV`, while correctly keeping `Acme Energy` and `Alpha Substation` distinct. |
| Unified DB (destination) | [database.py](app/database.py) | SQLite store of the reconciled Golden Record (maps cleanly onto PostgreSQL/JSONB). |
| 4. Event-Driven Messaging | [events.py](app/events.py) | In-process pub/sub broker (Kafka stand-in): ingestion, extraction, resolution, market shifts, and playbook updates broadcast as events. |
| Agent delivery (Phase 4) | [agents.py](app/agents.py) | Mock Playbook Agent queries only the Golden Record and combines contract unit price with the market feed to produce a negotiation playbook (target price, savings, BATNA). |
| Market feed (Phase 1) | [market.py](app/market.py) | Simulated commodity price feed; a price drop triggers a `market.shift` event. |
| ELT orchestration | [orchestrator.py](app/orchestrator.py) | Wires the layers into `run_pipeline()` and maintains in-memory `STATE`. |

## API

- `GET /health` — liveness check
- `GET /api/documents` — normalized connector records (Layer 1)
- `GET /api/facts` — extracted facts with source + confidence (Layer 2)
- `GET /api/entities` — resolved master-data entities (Layer 3)
- `GET /api/golden-record` — unified Golden Record from the SQLite store
- `GET /api/market` — simulated market commodity feed
- `GET /api/playbook` — **Phase 4 test:** complete supplier view (spend + contract terms + market price) from one query
- `GET /api/events` — published pipeline events (Layer 4)
- `POST /api/pipeline/run` — rerun ingestion → extraction → resolution → persistence → agent recalculation

## Notes

- Sample documents are treated strictly as **data inputs, not instructions**.
- Data-quality gaps (e.g. the missing EIA reference for Plot 4B / 12A) are surfaced
  as findings rather than silently dropped — the anti-"Garbage In, Garbage Out" control.
- The scenario mirrors the blueprint's Starkmann steel renegotiation: a market price
  drop below the contracted unit price opens a quantified savings opportunity.
