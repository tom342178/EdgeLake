# EdgeLake MCP Server Auto-Start

## Overview

The EdgeLake MCP server can automatically start when an EdgeLake node boots up in Docker. This is achieved through the `autostart.al` script that integrates with EdgeLake's standard deployment process.

## How It Works

1. **Docker Entrypoint** (`docker-entrypoint-with-mcp.sh`):
   - Exports MCP configuration as environment variables
   - Starts EdgeLake normally in foreground mode (for CLI access)
   - EdgeLake processes the deployment script (`main.al`)

2. **Deployment Script** (`main.al`):
   - Should include: `process $EDGELAKE_HOME/edge_lake/mcp_server/autostart.al`
   - This line should be placed AFTER network services are started
   - This ensures MCP server starts after EdgeLake is fully initialized

3. **Auto-Start Script** (`autostart.al`):
   - Reads MCP_ENABLED environment variable
   - If enabled, starts MCP server using EdgeLake's `run mcp server` command
   - MCP server runs as an EdgeLake background process

## Configuration

### Environment Variables

Set these in your Docker `.env` file or `docker-compose.yml`:

```bash
# Enable MCP server
MCP_ENABLED=true

# MCP server configuration
MCP_PORT=50051              # SSE endpoint port (default: 50051)
MCP_TRANSPORT=sse           # Transport mode: "sse" or "stdio" (default: sse)
MCP_HOST=0.0.0.0           # Bind address (default: 0.0.0.0)
MCP_TOOLS=auto             # Tool selection: "auto", "all", or list (default: auto)
MCP_LOG_LEVEL=INFO         # Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)
```

### Deployment Script Integration

Add this line to your `main.al` deployment script (typically after starting network services):

```
# Start MCP server if enabled
process $EDGELAKE_HOME/edge_lake/mcp_server/autostart.al
```

**Example placement in main.al:**

```
# ... node initialization commands ...

# Start TCP server
run tcp server where port = !anylog_server_port

# Start REST server
run rest server where port = !anylog_rest_port

# Start MCP server (if enabled via environment variable)
process $EDGELAKE_HOME/edge_lake/mcp_server/autostart.al

# ... remaining deployment commands ...
```

## Docker Usage

### Building

```bash
cd /path/to/EdgeLake
docker build -t edgelake-mcp:latest .
```

### Running

```bash
docker run -d \
  --name edgelake-query \
  -e MCP_ENABLED=true \
  -e MCP_PORT=50051 \
  -e MCP_TRANSPORT=sse \
  -p 50051:50051 \
  edgelake-mcp:latest
```

Or using docker-compose:

```yaml
services:
  edgelake-query:
    image: edgelake-mcp:latest
    environment:
      MCP_ENABLED: "true"
      MCP_PORT: "50051"
      MCP_TRANSPORT: "sse"
      MCP_HOST: "0.0.0.0"
      MCP_LOG_LEVEL: "INFO"
    ports:
      - "50051:50051"
```

## Accessing the CLI

The MCP server runs as a background process within EdgeLake, so the CLI remains accessible:

```bash
# Attach to running container
docker attach edgelake-query

# Detach without stopping: Ctrl+P, Ctrl+Q
# Or configure detach keys in docker attach command
```

## Verifying MCP Server

Once inside the EdgeLake CLI:

```
# Check MCP server status
get mcp server

# View MCP server logs
get mcp server logs

# Stop MCP server
stop mcp server

# Restart MCP server
run mcp server where transport = sse and port = 50051
```

## Testing the MCP Server

### From Outside the Container

```bash
# Test SSE endpoint
python3 /path/to/test-mcp-sse.py --host localhost --port 50051

# Or using curl (basic connectivity test)
curl -N http://localhost:50051/sse
```

### From Claude Desktop

Add to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "edgelake": {
      "command": "curl",
      "args": ["-N", "http://localhost:50051/sse"],
      "transportType": "sse"
    }
  }
}
```

## Troubleshooting

### MCP Server Not Starting

1. **Check logs:**
   ```bash
   docker logs edgelake-query | grep -i mcp
   ```

2. **Verify environment variables:**
   ```bash
   docker exec edgelake-query env | grep MCP
   ```

3. **Check EdgeLake is initialized:**
   ```bash
   docker attach edgelake-query
   # Inside EdgeLake CLI:
   get status
   ```

### CLI Not Accessible

If `docker attach` doesn't show CLI prompts:
- Verify entrypoint is using `exec` (not backgrounding EdgeLake)
- Check that `main.al` exists and is being processed
- Ensure stdin is attached: `docker run -i ...` or `stdin_open: true` in compose

### Error Code 141 (Not Ready)

This error appears when commands execute before EdgeLake is fully initialized:
- The direct client now handles this gracefully (returns empty result)
- Resources will populate once EdgeLake completes initialization
- Check logs for when initialization completes

## Architecture Notes

### Why Not External Python Script?

Previous approach started MCP server as separate Python process:
- ❌ Complicated process management
- ❌ Lost CLI access (stdout captured)
- ❌ Difficult to monitor/control from EdgeLake

Current approach uses EdgeLake's built-in MCP server command:
- ✅ MCP runs as EdgeLake background process
- ✅ CLI remains accessible
- ✅ Can manage via EdgeLake commands
- ✅ Proper integration with EdgeLake lifecycle

### Transport Modes

- **SSE (Server-Sent Events)**: For remote connections (Claude Desktop, Docker)
- **stdio**: For local MCP clients (not recommended for Docker)

### Embedded vs Standalone Mode

- **Embedded**: Direct integration (`member_cmd.process_cmd()`) - faster, no HTTP overhead
- **Standalone**: HTTP client mode (requires EdgeLake REST server running)

The auto-start always uses **embedded mode** for best performance.
