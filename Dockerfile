# ==== Part 1: Build stage ====
FROM python:3.11-slim AS builder

# Build argument for deployment-scripts repo (can be overridden at build time)
ARG DEPLOYMENT_SCRIPTS_REPO=https://github.com/tom342178/deployment-scripts

WORKDIR /app/

# Copy source code
COPY . EdgeLake/

# Install dependencies (skip compilation - use Python source for MCP compatibility)
RUN apt-get update && \
    apt-get install -y --no-install-recommends bash git openssh-client gcc python3-dev libffi-dev && \
    python3 -m pip install --upgrade pip wheel && \
    python3 -m pip install --upgrade -r /app/EdgeLake/requirements.txt && \
    apt-get purge -y gcc python3-dev libffi-dev && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# ==== Part 2: Runtime stage ====
FROM python:3.11-slim AS runtime

WORKDIR /app/

# Copy Python source and dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/EdgeLake /app/EdgeLake

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash ca-certificates git && \
    rm -rf /var/lib/apt/lists/*

# Copy deployment scripts and configs
RUN git clone https://github.com/oshadmon/nebula-anylog /app/nebula

# Copy setup.cfg
COPY setup.cfg /app/EdgeLake/setup.cfg

# ==== Part 3: Runtime configuration ====
# Pass build arg to runtime env
ARG DEPLOYMENT_SCRIPTS_REPO

ENV PYTHONPATH=/app/EdgeLake \
    EDGELAKE_PATH=/app \
    EDGELAKE_HOME=/app/EdgeLake \
    BLOCKCHAIN_DIR=/app/EdgeLake/blockchain \
    DATA_DIR=/app/EdgeLake/data \
    DEBIAN_FRONTEND=noninteractive \
    NODE_TYPE=generic \
    NODE_NAME=edgelake-node \
    COMPANY_NAME="New Company" \
    ANYLOG_SERVER_PORT=32548 \
    ANYLOG_REST_PORT=32549 \
    ANYLOG_MCP_PORT=50051 \
    LEDGER_CONN=127.0.0.1:32049 \
    INIT_TYPE=prod \
    DEPLOYMENT_SCRIPTS_REPO=${DEPLOYMENT_SCRIPTS_REPO}

# Create startup wrapper script for Python-based deployment
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Clone deployment-scripts if not present\n\
if [[ ! -d $EDGELAKE_PATH/deployment-scripts || ! "$(ls -A $EDGELAKE_PATH/deployment-scripts)" ]] ; then\n\
  echo "Cloning deployment-scripts from ${DEPLOYMENT_SCRIPTS_REPO}"\n\
  git clone ${DEPLOYMENT_SCRIPTS_REPO} $EDGELAKE_PATH/deployment-scripts\n\
fi\n\
\n\
# Run EdgeLake with main.al initialization script\n\
cd $EDGELAKE_HOME\n\
exec python3 edge_lake/edgelake.py process $EDGELAKE_PATH/deployment-scripts/node-deployment/main.al\n\
' > /app/start_edgelake.sh && chmod +x /app/start_edgelake.sh

WORKDIR /app/EdgeLake
ENTRYPOINT ["/app/start_edgelake.sh"]
