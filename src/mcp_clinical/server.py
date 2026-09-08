import os
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

DEFAULT_PAT = "development-token"
MCP_PAT = os.getenv("MCP_PAT", DEFAULT_PAT)
MCP_ACCESS_URL = os.getenv("MCP_ACCESS_URL", "http://localhost:8000/mcp")
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))

mcp = FastMCP(
    "Clinical Research & Market Price MCP",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path="/mcp",
)


def _auth_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if MCP_PAT and MCP_PAT != DEFAULT_PAT:
        headers["Authorization"] = f"Bearer {MCP_PAT}"
    return headers


def _require_pat() -> None:
    if not MCP_PAT or MCP_PAT == DEFAULT_PAT:
        raise RuntimeError(
            "MCP_PAT is not configured. Set MCP_PAT to a real bearer token before starting the server."
        )


@mcp.tool()
def server_access_info() -> dict[str, Any]:
    """Return the configured server URL and PAT guidance for the MCP endpoint."""
    return {
        "access_url": MCP_ACCESS_URL,
        "pat_env_var": "MCP_PAT",
        "auth_header": "Authorization: Bearer <your_pat>",
        "note": "Set MCP_PAT in your environment before starting the server and pass the same bearer token to your MCP client.",
    }


@mcp.tool()
def clinical_trials_search(condition: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Search ClinicalTrials.gov by condition or keyword and return a lightweight summary."""
    if not condition or not condition.strip():
        raise ValueError("A condition or keyword is required.")
    cleaned = condition.strip()
    url = "https://clinicaltrials.gov/api/query/study_fields"
    params = {
        "expr": f'AREA[ConditionSearch] "{cleaned}"',
        "fields": "NCTId,BriefTitle,Condition,OverallStatus,StudyType,PrimaryCompletionDate,BriefSummary",
        "min_rnk": 1,
        "max_rnk": max(1, min(25, max_results)),
        "fmt": "json",
    }

    with httpx.Client(timeout=20.0) as client:
        response = client.get(url, params=params, headers=_auth_headers())
        response.raise_for_status()
        payload = response.json()

    studies = payload.get("StudyFieldsResponse", {}).get("StudyFields", [])
    result: list[dict[str, Any]] = []
    for study in studies:
        fields = study.get("StudyFields", [])
        mapping: dict[str, Any] = {}
        for field in fields:
            key = field.get("Field")
            value = field.get("FieldValue")
            if key:
                mapping[key] = value
        result.append(
            {
                "nct_id": mapping.get("NCTId"),
                "brief_title": mapping.get("BriefTitle"),
                "condition": mapping.get("Condition"),
                "overall_status": mapping.get("OverallStatus"),
                "study_type": mapping.get("StudyType"),
                "primary_completion_date": mapping.get("PrimaryCompletionDate"),
                "brief_summary": mapping.get("BriefSummary"),
            }
        )
    return result


@mcp.tool()
def get_company_price(ticker: str, range_name: str = "1d") -> dict[str, Any]:
    """Return the latest market price and price metadata for a stock ticker."""
    if not ticker or not ticker.strip():
        raise ValueError("A ticker symbol is required.")
    symbol = ticker.strip().upper()
    if range_name not in {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}:
        raise ValueError("Unsupported range_name. Use one of: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max.")

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": range_name, "interval": "1d" if range_name in {"1d", "5d"} else "1mo"}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(url, params=params, headers=_auth_headers())
        response.raise_for_status()
        payload = response.json()

    result = payload.get("chart", {}).get("result", [{}])[0]
    meta = result.get("meta", {})
    quote = (result.get("indicators", {}).get("quote", [{}])[0]) if result.get("indicators", {}).get("quote") else {}
    close_values = quote.get("close", [])
    latest_close = close_values[-1] if close_values else meta.get("regularMarketPrice")

    return {
        "ticker": symbol,
        "currency": meta.get("currency", "USD"),
        "price": latest_close,
        "previous_close": meta.get("previousClose"),
        "regular_market_price": meta.get("regularMarketPrice"),
        "market_state": meta.get("marketState"),
        "exchange": meta.get("exchangeName"),
        "source": "Yahoo Finance",
    }


def main() -> None:
    _require_pat()
    print(f"Starting Clinical Research MCP server on {MCP_HOST}:{MCP_PORT}")
    print(f"Access URL: {MCP_ACCESS_URL}")
    print(f"PAT env var: MCP_PAT (value is set: {bool(MCP_PAT and MCP_PAT != DEFAULT_PAT)})")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
