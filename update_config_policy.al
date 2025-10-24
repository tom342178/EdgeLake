#-----------------------------------------------------------------------------------------------------------------------
# Update Config Policy to Include MCP Server Autostart
#
# This script forces recreation of the config policy with MCP server autostart included
#-----------------------------------------------------------------------------------------------------------------------

# Set flag to force recreation
set create_config = true

# Set local_scripts path
local_scripts = /app/deployment-scripts/node-deployment

# Process config policy script to create new policy
process !local_scripts/policies/config_policy.al

# Wait for policy to be published
wait 5

# Reload blockchain metadata
blockchain reload metadata

echo "Config policy updated successfully"
