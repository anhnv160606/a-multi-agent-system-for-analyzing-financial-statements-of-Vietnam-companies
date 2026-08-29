"""
FastAPI Web Server for Financial Multi-Agent System (Phase 6).
Serves the pixel-perfect HTML UI and provides /api/analyze endpoint connected to LangGraph.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.database.vector_store import VectorStore
from src.orchestrator.graph import build_graph, create_initial_state
from src.utils.llm_client import _load_env_file, get_default_llm
from src.utils.logger import get_logger

logger = get_logger("src.ui.server")
_load_env_file()

app = FastAPI(
    title="Vietnam Financial Multi-Agent System API",
    version="1.0.0",
    description="Backend API connecting pixel-perfect Hero Landing UI to LangGraph 7-Agent System.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global graph singleton
_graph = None


def get_compiled_graph():
    global _graph
    if _graph is None:
        config_path = PROJECT_ROOT / "configs" / "settings.yaml"
        config: Dict[str, Any] = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        llm = get_default_llm("default")
        vector_store = VectorStore()
        _graph = build_graph(config=config, llm=llm, vector_store=vector_store)
    return _graph


class AnalyzeRequest(BaseModel):
    query: str


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = PROJECT_ROOT / "src" / "ui" / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/documents")
async def list_documents():
    """Lists preloaded documents in data/ directory (Task 6.3)."""
    data_dir = PROJECT_ROOT / "data"
    docs = []
    if data_dir.exists():
        for file in data_dir.glob("*.*"):
            docs.append({
                "filename": file.name,
                "extension": file.suffix,
                "size_kb": round(file.stat().st_size / 1024, 2),
            })
    return {"status": "success", "count": len(docs), "documents": docs}


@app.post("/api/analyze")
async def analyze_query(req: AnalyzeRequest):
    """Executes full 7-Agent LangGraph analysis for the given user query."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    logger.info(f"Received API analyze request: '{query}'")
    try:
        graph = get_compiled_graph()
        initial_state = create_initial_state(query=query)
        final_state = graph.invoke(initial_state)

        ticker = final_state.get("company_ticker", "N/A")
        years = final_state.get("fiscal_years", [])
        confidence = float(final_state.get("confidence_score", 0.95) or 0.95)

        # Extract market price from VNStock
        price = None
        market_data = final_state.get("market_data")
        if market_data and hasattr(market_data, "records") and market_data.records:
            price = market_data.records[-1].close

        # Extract DuPont & KPI metrics
        calc = final_state.get("calculator_results") or {}
        analysis = final_state.get("analysis_results") or {}
        dupont = analysis.get("dupont", {}).get("dupont_3step", {})
        roe = None
        net_margin = None
        if dupont:
            latest_year = max(dupont.keys(), default=None)
            if latest_year and isinstance(dupont[latest_year], dict):
                roe = dupont[latest_year].get("roe")
                net_margin = dupont[latest_year].get("net_profit_margin")

        if roe is None and "roe" in calc:
            roe = calc.get("roe")
        if net_margin is None and "net_margin" in calc:
            net_margin = calc.get("net_margin")

        # Extract synthesis & report
        synthesis = final_state.get("synthesis_results") or {}
        exec_summary = synthesis.get("executive_summary") if isinstance(synthesis, dict) else ""
        strengths = synthesis.get("strengths", []) if isinstance(synthesis, dict) else []
        risks = synthesis.get("risks", []) if isinstance(synthesis, dict) else []
        final_report = final_state.get("final_report", "")

        return {
            "status": "success",
            "query": query,
            "ticker": ticker,
            "fiscal_years": years,
            "price": price,
            "roe": roe,
            "net_margin": net_margin,
            "confidence": confidence,
            "executive_summary": exec_summary,
            "strengths": strengths,
            "risks": risks,
            "final_report": final_report,
            "calculator_results": {
                k: v for k, v in calc.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool) and k != "parsed_financial_data"
            },
        }
    except Exception as exc:
        logger.error(f"Error during graph invocation: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n🚀 Khởi chạy Web Server tại: http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
