# EdgeLake MCP Server - Quick Start

## 🚀 One-Minute Deploy

```bash
# 1. Build and start
cd /Users/tviviano/Documents/GitHub/docker-compose
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query

# 2. Wait for initialization
sleep 30

# 3. Test
curl -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq '.result.tools[].name'
```

**Expected**: List of 8-10 tool names

---

## 📋 What Got Built

✅ **Timeout Protection** - Commands timeout after 30s instead of hanging
✅ **Auto-Start** - MCP server starts automatically with container
✅ **Debug Logging** - Set `MCP_LOG_LEVEL=DEBUG` for troubleshooting
✅ **SSE Transport** - HTTP endpoint at `http://host:50051/sse`
✅ **Embedded Mode** - Direct integration, no HTTP overhead
✅ **Test Scripts** - `./test-mcp-sse-endpoints.sh`

---

## ⚙️ Configuration

**File**: `docker-makefiles/query-configs/advance_configs.env`

```bash
MCP_ENABLED=true          # ← Already set!
MCP_PORT=50051
MCP_TRANSPORT=sse
MCP_HOST=0.0.0.0
MCP_TOOLS=auto
MCP_LOG_LEVEL=INFO       # ← Change to DEBUG for troubleshooting
```

---

## 🧪 Test Commands

### List Tools
```bash
curl -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

### Get Server Info (Fast)
```bash
curl -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc":"2.0",
  "id":2,
  "method":"tools/call",
  "params":{"name":"server_info","arguments":{}}
}'
```

### Get Node Status (Calls EdgeLake)
```bash
curl -s --max-time 35 -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc":"2.0",
  "id":3,
  "method":"tools/call",
  "params":{"name":"node_status","arguments":{}}
}'
```

### List Databases
```bash
curl -s --max-time 35 -X POST http://localhost:50051/sse \
  -H "Content-Type: application/json" \
  -d '{
  "jsonrpc":"2.0",
  "id":4,
  "method":"tools/call",
  "params":{"name":"list_databases","arguments":{}}
}'
```

### Automated Tests
```bash
cd /Users/tviviano/Documents/GitHub/EdgeLake
./test-mcp-sse-endpoints.sh localhost 50051
```

---

## 🔍 Verify It's Running

```bash
# Check container logs
docker logs <container-name> | grep -i "mcp"

# Expected:
# Starting EdgeLake MCP Server...
#   Transport: sse
#   Port: 50051
#   Host: 0.0.0.0
#   Tools: auto
# [MCP Server] Started with SSE transport...

# Check from inside container
docker exec <container> python3 /app/EdgeLake/edge_lake/edgelake.py "get mcp server"

# Test endpoint
curl http://localhost:50051/sse
```

---

## 🐛 Troubleshooting

### Enable Debug Logging

```bash
# 1. Edit config
vim docker-makefiles/query-configs/advance_configs.env

# 2. Change to DEBUG
MCP_LOG_LEVEL=DEBUG

# 3. Rebuild
make down EDGELAKE_TYPE=query
make up IMAGE=edgelake-mcp TAG=latest EDGELAKE_TYPE=query

# 4. Watch logs
docker logs -f <container> 2>&1 | grep -i mcp
```

### Common Issues

| Issue | Solution |
|-------|----------|
| MCP not starting | Check `MCP_ENABLED=true` in env file |
| Port not accessible | Verify `0.0.0.0:50051->50051/tcp` in `docker ps` |
| Commands timeout | Enable DEBUG logging, check EdgeLake initialization |
| Connection refused | Wait 30s for full startup |

---

## 📚 Documentation

- **`MCP_AUTOSTART_SUMMARY.md`** - Complete overview
- **`DOCKER_MCP_AUTOSTART.md`** - Detailed setup guide
- **`MCP_TESTING_GUIDE.md`** - Manual testing procedures
- **`test-mcp-sse-endpoints.sh`** - Automated test script

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                Docker Container                      │
│  ┌──────────────────────────────────────────────┐  │
│  │           EdgeLake Process                    │  │
│  │  ┌────────────────┐  ┌──────────────────┐   │  │
│  │  │  Main Thread   │  │   MCP Thread     │   │  │
│  │  │   (CLI)        │  │  (SSE Server)    │   │  │
│  │  └────────────────┘  └──────────────────┘   │  │
│  │          │                     │             │  │
│  │          └─────────┬───────────┘             │  │
│  │                    ↓                         │  │
│  │           member_cmd.process_cmd()           │  │
│  │              (Direct Call)                   │  │
│  └──────────────────────────────────────────────┘  │
│                     ↑                               │
│              Port 50051 (HTTP/SSE)                  │
└─────────────────────────────────────────────────────┘
                       ↑
               External Clients
           (Claude Desktop, curl, etc.)
```

**Benefits**:
- ✅ Zero HTTP overhead (direct calls)
- ✅ Shared memory space
- ✅ No stdio conflicts
- ✅ Timeout protection
- ✅ Auto-start on boot

---

## 🎯 Next Steps

1. ✅ Built and configured
2. Test with your demo environment
3. Configure Claude Desktop (see `SSE_USAGE.md`)
4. Monitor performance
5. Production deployment

---

## 💡 Pro Tips

- **Use DEBUG mode** when first testing: `MCP_LOG_LEVEL=DEBUG`
- **Test locally first** before deploying to remote
- **Check logs** if tools timeout: `docker logs <container>`
- **Wait 30 seconds** after container starts for full initialization
- **Use automated tests**: `./test-mcp-sse-endpoints.sh`

---

That's it! 🎉

The MCP server will start automatically when you deploy. Just build and test!
