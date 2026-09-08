# MCP Clinical Research Server

This project exposes an MCP server that can:

- search ClinicalTrials.gov for studies by condition or keyword
- fetch the latest stock price for a company ticker from Yahoo Finance

## Setup

1. Create a virtual environment if you want one.
2. Install dependencies:

   python -m pip install -e .

3. Set your PAT and the server endpoint:

   export MCP_PAT="your_personal_access_token"
   export MCP_ACCESS_URL="http://localhost:8000/mcp"
   export MCP_HOST="0.0.0.0"
   export MCP_PORT="8000"

4. Start the server:

   python -m mcp_clinical.server

   or:

   mcp-clinical

## Access pattern

Your MCP client should connect to:

- URL: http://localhost:8000/mcp
- Auth header: Authorization: Bearer <your_pat>

The server expects the same token in the `MCP_PAT` environment variable when it starts.

## Available tools

- `server_access_info()`
- `clinical_trials_search(condition, max_results=5)`
- `get_company_price(ticker, range_name="1d")`

## Example calls

### ClinicalTrials.gov

- condition: "breast cancer"
- max_results: 5

### Market ticker

- ticker: "AAPL"
- range_name: "1d"

This is a simple deployment scaffold. If you want to expose it publicly, place it behind a reverse proxy or an API gateway that enforces the PAT before the request reaches the MCP endpoint.
