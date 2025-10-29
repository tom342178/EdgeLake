FROM python:3.11-alpine as base

# declare params
ENV PYTHONPATH=/app/EdgeLake/ \
    EDGELAKE_PATH=/app \
    EDGELAKE_HOME=/app/EdgeLake \
    BLOCKCHAIN_DIR=/app/EdgeLake/blockchain \
    DATA_DIR=/app/EdgeLake/data \
    LOCAL_SCRIPTS=/app/deployment-scripts/node-deployment \
    TEST_DIR=/app/deployment-scripts/test \
    DEBIAN_FRONTEND=noninteractive \
    NODE_TYPE=generic \
    NODE_NAME=edgelake-node \
    COMPANY_NAME="New Company" \
    ANYLOG_SERVER_PORT=32548 \
    ANYLOG_REST_PORT=32549 \
    ANYLOG_MCP_PORT=50051 \
    LEDGER_CONN=127.0.0.1:32049

WORKDIR /app

EXPOSE $ANYLOG_SERVER_PORT $ANYLOG_REST_PORT $ANYLOG_BROKER_PORT $ANYLOG_MCP_PORT

# ============================================================================
# LAYER 1: System dependencies (rarely change - heavily cached)
# ============================================================================
RUN apk update && apk upgrade && \
    apk add bash git gcc openssh-client python3 python3-dev py3-pip musl-dev build-base libffi-dev py3-psutil && \
    python3 -m pip install --upgrade pip

# ============================================================================
# LAYER 2: Python dependencies (only rebuilds when requirements change)
# ============================================================================
# Copy only requirements files first (not entire codebase)
COPY requirements.txt /tmp/edgelake-requirements.txt
COPY edge_lake/mcp_server/requirements.txt /tmp/mcp-requirements.txt

# Install MCP server requirements first (needed by mcp_server/__init__.py imports)
RUN python3 -m pip install --upgrade -r /tmp/mcp-requirements.txt

# Install main EdgeLake requirements
RUN python3 -m pip install --upgrade -r /tmp/edgelake-requirements.txt

# ============================================================================
# LAYER 3: External dependencies (only rebuilds when repo changes)
# ============================================================================
# Clone deployment-scripts from your public fork (includes MCP autostart integration)
ARG CACHEBUST=f8e7d2c1
RUN echo "Cache bust: $CACHEBUST" && git clone https://github.com/tom342178/deployment-scripts.git

# Alternative: Use upstream EdgeLake deployment-scripts (without MCP autostart)
# RUN git clone https://github.com/EdgeLake/deployment-scripts

# ============================================================================
# LAYER 4: Application code (rebuilds on every code change - fastest layer)
# ============================================================================
COPY . EdgeLake
COPY setup.cfg /app
COPY LICENSE /app
COPY README.md /app

FROM base AS deployment

# Make sure to set the EDGELAKE_HOME environment variable for Python explicitly
ENV EDGELAKE_HOME=/app/EdgeLake

# Copy MCP auto-start files
COPY edge_lake/mcp_server/autostart.al /app/EdgeLake/edge_lake/mcp_server/
COPY docker-entrypoint-with-mcp.sh /app/
RUN chmod +x /app/docker-entrypoint-with-mcp.sh

# Use entrypoint wrapper that includes MCP auto-start
# Set MCP_ENABLED=true in environment to enable MCP server
ENTRYPOINT ["/app/docker-entrypoint-with-mcp.sh"]