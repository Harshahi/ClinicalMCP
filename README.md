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

## Public EC2 deployment

The safest public setup is:

- EC2 instance with a public IP or Elastic IP
- security group allowing `22`, `80`, and `443` inbound
- NGINX listening on `80`/`443` and proxying to the MCP app on `127.0.0.1:8000`
- `systemd` service running the Python app with `MCP_PAT` set via a `.env` file
- GitHub Actions on pushes to `main` that SSHs into the instance and redeploys the app

### EC2 setup

1. Launch an Ubuntu or Amazon Linux 2023 EC2 instance.
2. Open inbound ports:
   - `22` for SSH
   - `80` for HTTP
   - `443` for HTTPS
3. Install nginx and Python dependencies on the EC2 VM:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git nginx
```

4. Clone the repo:

```bash
cd /home/ubuntu
git clone git@github.com:Harshahi/ClinicalMCP.git
cd ClinicalMCP
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
cp .env.example .env
```

5. Update `.env` with a real PAT and your public URL:

```bash
MCP_PAT=your-real-pat
MCP_ACCESS_URL=https://your-domain.example.com/mcp
MCP_PUBLIC_URL=https://your-domain.example.com
MCP_HOST=0.0.0.0
MCP_PORT=8000
```

6. Configure NGINX to proxy traffic:

```bash
sudo tee /etc/nginx/conf.d/clinicalmcp.conf <<'EOF'
server {
    listen 80;
    server_name your-domain.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo nginx -t
sudo systemctl enable --now nginx
```

7. Create a `systemd` service:

```bash
sudo tee /etc/systemd/system/clinicalmcp.service <<'EOF'
[Unit]
Description=ClinicalMCP Server
After=network.target

[Service]
WorkingDirectory=/home/ubuntu/ClinicalMCP
EnvironmentFile=/home/ubuntu/ClinicalMCP/.env
ExecStart=/home/ubuntu/ClinicalMCP/.venv/bin/python -m mcp_clinical.server
Restart=always
RestartSec=5
User=ubuntu
Group=ubuntu

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now clinicalmcp.service
sudo systemctl status clinicalmcp.service --no-pager
```

## GitHub Actions deployment to EC2

Add the following repository secrets in GitHub:

- `EC2_HOST`
- `EC2_USER`
- `EC2_SSH_KEY`
- `MCP_PAT`
- `MCP_PUBLIC_URL`

Example workflow:

```yaml
name: deploy-to-ec2

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e .

      - name: Deploy to EC2
        uses: appleboy/ssh-action@v1.1.0
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ${{ secrets.EC2_USER }}
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            set -e
            cd /home/ubuntu/ClinicalMCP || git clone git@github.com:Harshahi/ClinicalMCP.git /home/ubuntu/ClinicalMCP
            cd /home/ubuntu/ClinicalMCP
            git pull origin main
            python3 -m venv .venv
            . .venv/bin/activate
            python -m pip install --upgrade pip
            python -m pip install -e .
            cat > .env <<EOF
            MCP_PAT=${{ secrets.MCP_PAT }}
            MCP_ACCESS_URL=${{ secrets.MCP_PUBLIC_URL }}/mcp
            MCP_PUBLIC_URL=${{ secrets.MCP_PUBLIC_URL }}
            MCP_HOST=0.0.0.0
            MCP_PORT=8000
            EOF
            sudo cp infra/clinicalmcp.service /etc/systemd/system/clinicalmcp.service
            sudo systemctl daemon-reload
            sudo systemctl restart clinicalmcp.service
            sudo systemctl reload nginx || true
```

## Notes

- Use a public DNS name with HTTPS in front of the EC2 instance if you want a stable public URL.
- If you want to terminate TLS at the EC2 load balancer or NGINX layer, install Certbot and configure `443` with Let’s Encrypt.
- Keep the PAT in GitHub secrets and never commit it to source control.
