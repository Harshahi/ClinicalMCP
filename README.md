# MCP Clinical Research Server

This project exposes an MCP server that can:

- search ClinicalTrials.gov for studies by condition or keyword
- fetch the latest stock price for a company ticker from Yahoo Finance

## Local setup

### Run with Docker Compose

1. Copy the example env file:

   cp .env.example .env

2. Update the values in `.env` with a real PAT if you want to use one:

   MCP_PAT=your_personal_access_token
   MCP_ACCESS_URL=http://localhost:8000/mcp
   MCP_PUBLIC_URL=http://localhost
   MCP_HOST=0.0.0.0
   MCP_PORT=8000

3. Start the app with Docker Compose:

   docker compose up --build

4. The server will be available at:

   http://localhost:8000/mcp

### Run directly with Python

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

- URL: http://localhost:8000/mcp (or your EC2 HTTPS URL)
- Auth header: Authorization: Bearer <your_pat>

The server expects the same token in the `MCP_PAT` environment variable when it starts. When `MCP_PAT` is set, requests without the bearer token are rejected with a 401 response.

### VS Code MCP config

Create a `.vscode/mcp.json` file with a PAT-based config like this:

```json
{
  "servers": {
    "clinicalmcp-local": {
      "type": "http",
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer ${input:clinicalmcp_pat}"
      }
    },
    "clinicalmcp-ec2": {
      "type": "http",
      "url": "https://your-ec2-host.example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${input:clinicalmcp_pat}"
      }
    }
  },
  "inputs": [
    {
      "id": "clinicalmcp_pat",
      "type": "promptString",
      "description": "ClinicalMCP PAT"
    }
  ]
}
```

Use the EC2 entry when the app is deployed on your VM.

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

## Public EC2 deployment

The app is deployed to EC2 as a Docker container fronted by NGINX:

- EC2 instance with a public IP or Elastic IP
- security group allowing `22`, `80`, and `443` inbound (port `8000` stays closed)
- the container publishes only to `127.0.0.1:8000`, so it is not reachable directly
- NGINX listens on `80` and proxies to `127.0.0.1:8000`
- `MCP_PAT` is supplied through a `.env` file written by the deploy workflow
- GitHub Actions runs the tests, then SSHes into the instance and redeploys on pushes to `main`

Deployment is handled entirely by [.github/workflows/deploy-ec2.yml](.github/workflows/deploy-ec2.yml).
It installs Docker and NGINX if they are missing, so a bare Ubuntu instance needs no manual
preparation beyond SSH access and the security group rules.

### One-time setup

1. Launch an Ubuntu EC2 instance.
2. Open inbound ports `22`, `80`, and `443`. Do **not** open `8000`.
3. Add the repository secrets listed below.
4. Push to `main` (or run the workflow manually via **Actions -> Run workflow**).

### Required repository secrets

| Secret | Required | Purpose |
| --- | --- | --- |
| `EC2_HOST` | yes | Public DNS name or IP of the instance |
| `EC2_USER` | yes | SSH user, `ubuntu` on Ubuntu AMIs |
| `EC2_SSH_KEY` | yes | Full contents of the private key, including the BEGIN/END lines |
| `MCP_PAT` | yes | Bearer token clients must send; the deploy fails if this is empty |
| `MCP_PUBLIC_URL` | yes | Public base URL, e.g. `http://your-host` with no trailing slash |
| `FINNHUB_API_KEY` | no | Preferred market price source |
| `TWELVEDATA_API_KEY` | no | Fallback price source, defaults to `demo` |

`MCP_ACCESS_URL` is derived automatically as `${MCP_PUBLIC_URL}/mcp` and should not be set separately.

### What the workflow does

1. **test** job: installs the package and runs `pytest`. A failing test blocks the deploy.
2. **deploy** job:
   - installs `docker.io`, `docker-compose-v2`, `git`, and `nginx` if absent
   - clones or fast-forwards the repo at `/home/ubuntu/ClinicalMCP` over HTTPS
   - writes `.env` (mode `600`) from the repository secrets
   - runs `docker compose up -d --build` and prunes dangling images
   - installs the NGINX proxy config as the `default_server` on port `80`
   - smoke tests the app directly, then through NGINX, and asserts that an
     unauthenticated request is rejected with `401`

The deploy is idempotent: it runs `git reset --hard origin/main`, so the instance always
matches `main`. `.env` is gitignored and survives the reset.

### Operating the deployed instance

```bash
ssh -i /path/to/key.pem ubuntu@<EC2_HOST>
cd /home/ubuntu/ClinicalMCP

sudo docker compose ps               # container status and health
sudo docker compose logs -f          # follow application logs
sudo docker compose restart          # restart without rebuilding
sudo docker compose up -d --build    # rebuild after a code change
```

## Notes

- The NGINX config disables `proxy_buffering` and uses a long `proxy_read_timeout`. MCP
  streamable HTTP holds SSE connections open, and the NGINX defaults would truncate
  tool responses mid-stream.
- Requests are served over plain HTTP, so the PAT crosses the network in cleartext. For
  anything beyond testing, put TLS in front: point a DNS name at the instance and run
  `sudo certbot --nginx`, then update `MCP_PUBLIC_URL` to the `https://` URL.
- Keep the PAT in GitHub secrets and never commit it to source control.
- `infra/clinicalmcp.service` is left over from the earlier systemd-based deployment and is
  no longer used by the workflow.
