import hmac
import os
from typing import Any

import httpx
import uvicorn
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

load_dotenv()

MCP_PAT = os.getenv("MCP_PAT", "")
MCP_ACCESS_URL = os.getenv("MCP_ACCESS_URL", "http://localhost:8000/mcp")
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))

# Browser origins permitted to call this server. Empty means "no browser may".
MCP_ALLOWED_ORIGINS = frozenset(
    origin.strip()
    for origin in os.getenv("MCP_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
)

# Escape hatch for local development only. Must be set explicitly, so an
# unauthenticated server is always a deliberate choice rather than an accident.
MCP_ALLOW_UNAUTHENTICATED = os.getenv("MCP_ALLOW_UNAUTHENTICATED", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

mcp = FastMCP(
    "Clinical Research & Market Price MCP",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path="/mcp",
)


def _auth_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if MCP_PAT:
        headers["Authorization"] = f"Bearer {MCP_PAT}"
    return headers


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
    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {"query.term": cleaned, "pageSize": max(1, min(25, max_results)), "format": "json"}

    with httpx.Client(timeout=20.0) as client:
        response = client.get(url, params=params, headers=_auth_headers())
        response.raise_for_status()
        payload = response.json()

    studies = payload.get("studies", [])
    result: list[dict[str, Any]] = []
    for study in studies[: max(1, min(25, max_results))]:
        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        conditions_module = protocol.get("conditionsModule", {})
        status_module = protocol.get("statusModule", {})
        design_module = protocol.get("designModule", {})
        description_module = protocol.get("descriptionModule", {})

        condition_items = conditions_module.get("conditions", [])
        condition_name = next(
            (item.get("condition") for item in condition_items if isinstance(item, dict) and item.get("condition")),
            None,
        )

        result.append(
            {
                "nct_id": identification.get("nctId"),
                "brief_title": identification.get("briefTitle"),
                "condition": condition_name,
                "overall_status": status_module.get("overallStatus"),
                "study_type": design_module.get("studyType"),
                "primary_completion_date": status_module.get("primaryCompletionDate"),
                "brief_summary": description_module.get("briefSummary"),
            }
        )
    return result


@mcp.tool()
def get_company_price(ticker: str, range_name: str = "1d") -> dict[str, Any]:
    """Return the latest market price and price metadata for a stock ticker."""
    if not ticker or not ticker.strip():
        raise ValueError("A ticker symbol is required.")
    symbol = ticker.strip().upper()

    api_key = os.getenv("FINNHUB_API_KEY")
    if api_key:
        url = "https://finnhub.io/api/v1/quote"
        params = {"symbol": symbol, "token": api_key}
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.get(url, params=params, headers={"Accept": "application/json"})
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPStatusError, httpx.RequestError):
            payload = {}

        if payload:
            return {
                "ticker": symbol,
                "currency": "USD",
                "price": payload.get("c"),
                "previous_close": payload.get("pc"),
                "regular_market_price": payload.get("c"),
                "market_state": "closed" if payload.get("c") is not None else None,
                "exchange": "NASDAQ",
                "source": "Finnhub",
            }

    twelve_data_key = os.getenv("TWELVEDATA_API_KEY", "demo")
    twelve_data_url = "https://api.twelvedata.com/price"
    twelve_data_params = {"symbol": symbol, "apikey": twelve_data_key}
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(twelve_data_url, params=twelve_data_params, headers={"Accept": "application/json"})
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError):
        payload = {}

    if payload and payload.get("price") is not None:
        price_value = payload.get("price")
        try:
            price_value = float(price_value)
        except (TypeError, ValueError):
            price_value = None
        if price_value is not None:
            return {
                "ticker": symbol,
                "currency": "USD",
                "price": price_value,
                "previous_close": None,
                "regular_market_price": price_value,
                "market_state": "open",
                "exchange": "NASDAQ",
                "source": "Twelve Data",
            }

    if range_name not in {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}:
        raise ValueError("Unsupported range_name. Use one of: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max.")

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": range_name, "interval": "1d" if range_name in {"1d", "5d"} else "1mo"}
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, params=params, headers=_auth_headers())
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError):
        raise RuntimeError(f"Unable to fetch price data for {symbol} from the configured market data source.")

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


def _json_rpc_error(status_code: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": None, "error": {"code": code, "message": message}},
        status_code=status_code,
    )


def _token_matches(token: str) -> bool:
    """Compare in constant time so the PAT cannot be recovered byte by byte."""
    return hmac.compare_digest(token.encode("utf-8"), MCP_PAT.encode("utf-8"))


class RequirePatMiddleware(BaseHTTPMiddleware):
    """Require a bearer token on every request.

    Deliberately fail-closed. The check applies to all paths rather than a list
    of protected prefixes, so a route added later is guarded by default instead
    of being exposed by omission.
    """

    async def dispatch(self, request, call_next):
        # DNS-rebinding protection. Browsers always attach Origin on cross-site
        # requests, so an unrecognised value means the caller is a page we do
        # not trust. Non-browser MCP clients send no Origin and are unaffected.
        origin = request.headers.get("Origin")
        if origin and origin not in MCP_ALLOWED_ORIGINS:
            return _json_rpc_error(403, -32003, f"Forbidden: origin {origin} is not allowed")

        if not MCP_PAT:
            if MCP_ALLOW_UNAUTHENTICATED:
                return await call_next(request)
            # Refuse to serve rather than silently accept anonymous callers.
            return _json_rpc_error(
                503,
                -32002,
                "Server misconfigured: MCP_PAT is not set. Set it, or set "
                "MCP_ALLOW_UNAUTHENTICATED=true to run without auth locally.",
            )

        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.strip().lower() != "bearer" or not _token_matches(token.strip()):
            return _json_rpc_error(
                401, -32001, "Unauthorized: send Authorization: Bearer <your_pat>"
            )

        return await call_next(request)


def main() -> None:
    if not MCP_PAT and not MCP_ALLOW_UNAUTHENTICATED:
        raise SystemExit(
            "Refusing to start: MCP_PAT is not set, so the server would accept "
            "unauthenticated requests.\nSet MCP_PAT, or set "
            "MCP_ALLOW_UNAUTHENTICATED=true if you really want an open server locally."
        )

    print(f"Starting Clinical Research MCP server on {MCP_HOST}:{MCP_PORT}")
    print(f"Access URL: {MCP_ACCESS_URL}")
    print(f"PAT env var: MCP_PAT (value is set: {bool(MCP_PAT)})")
    if MCP_ALLOWED_ORIGINS:
        print(f"Allowed browser origins: {', '.join(sorted(MCP_ALLOWED_ORIGINS))}")
    else:
        print("Allowed browser origins: none (requests carrying an Origin header are refused)")
    if not MCP_PAT:
        print("WARNING: running WITHOUT authentication because MCP_ALLOW_UNAUTHENTICATED is set.")

    app = RequirePatMiddleware(mcp.streamable_http_app())
    uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
