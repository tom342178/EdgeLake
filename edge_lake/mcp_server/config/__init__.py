"""
Configuration management for EdgeLake MCP Server

Loads and manages configuration from YAML files and environment variables.

License: Mozilla Public License 2.0
"""

import os
import yaml
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class NodeConfig:
    """Configuration for an EdgeLake node"""
    
    def __init__(self, name: str, description: str, host: str, port: int, is_default: bool = False):
        self.name = name
        self.description = description
        self.host = host
        self.port = port
        self.is_default = is_default
    
    def __repr__(self):
        return f"NodeConfig(name={self.name}, host={self.host}, port={self.port}, default={self.is_default})"


class ToolConfig:
    """Configuration for an MCP tool"""
    
    def __init__(self, data: Dict[str, Any]):
        self.name = data['name']
        self.description = data['description']
        self.edgelake_command = data['edgelake_command']
        self.input_schema = data['input_schema']
    
    def __repr__(self):
        return f"ToolConfig(name={self.name})"


class Config:
    """Main configuration manager"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize configuration.
        
        Args:
            config_dir: Path to configuration directory. If None, uses default location.
        """
        if config_dir is None:
            # Default to config directory relative to this file
            config_dir = Path(__file__).parent
        
        self.config_dir = Path(config_dir)
        self.nodes: List[NodeConfig] = []
        self.tools: List[ToolConfig] = []
        self.client_config: Dict[str, Any] = {}
        
        # Load configurations
        self._load_nodes_config()
        self._load_tools_config()
        self._apply_env_overrides()
    
    def _load_nodes_config(self):
        """Load nodes configuration from YAML"""
        nodes_file = self.config_dir / "nodes.yaml"
        
        if not nodes_file.exists():
            logger.warning(f"Nodes configuration not found: {nodes_file}")
            # Create default local node
            self.nodes.append(NodeConfig(
                name="local",
                description="Local EdgeLake node",
                host="127.0.0.1",
                port=32049,
                is_default=True
            ))
            return
        
        try:
            with open(nodes_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Load nodes
            for node_data in config.get('nodes', []):
                self.nodes.append(NodeConfig(
                    name=node_data['name'],
                    description=node_data['description'],
                    host=node_data['host'],
                    port=node_data['port'],
                    is_default=node_data.get('is_default', False)
                ))
            
            # Load client configuration
            self.client_config = config.get('client', {})
            
            logger.info(f"Loaded {len(self.nodes)} node configurations")
            
        except Exception as e:
            logger.error(f"Failed to load nodes configuration: {e}")
            raise
    
    def _load_tools_config(self):
        """Load tools configuration from YAML"""
        tools_file = self.config_dir / "tools.yaml"
        
        if not tools_file.exists():
            logger.warning(f"Tools configuration not found: {tools_file}")
            return
        
        try:
            with open(tools_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Load tools
            for tool_data in config.get('tools', []):
                self.tools.append(ToolConfig(tool_data))

            logger.info(f"Loaded {len(self.tools)} tool configurations")
            
        except Exception as e:
            logger.error(f"Failed to load tools configuration: {e}")
            raise
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides"""
        # Check for default node override
        default_node_env = os.getenv("EDGELAKE_DEFAULT_NODE")
        if default_node_env:
            # Clear all defaults and set new one
            for node in self.nodes:
                node.is_default = (node.name == default_node_env)
        
        # Check for direct host/port overrides
        host_override = os.getenv("EDGELAKE_HOST")
        port_override = os.getenv("EDGELAKE_PORT")
        
        if host_override or port_override:
            # Find default node and override
            for node in self.nodes:
                if node.is_default:
                    if host_override:
                        node.host = host_override
                    if port_override:
                        node.port = int(port_override)
                    logger.info(f"Applied env overrides to default node: {node}")
                    break
    
    def get_default_node(self) -> NodeConfig:
        """Get the default node configuration"""
        for node in self.nodes:
            if node.is_default:
                return node
        
        # If no default set, return first node
        if self.nodes:
            return self.nodes[0]
        
        # Fallback to localhost
        return NodeConfig(
            name="local",
            description="Local EdgeLake node",
            host="127.0.0.1",
            port=32049,
            is_default=True
        )
    
    def get_node_by_name(self, name: str) -> Optional[NodeConfig]:
        """Get a node by name"""
        for node in self.nodes:
            if node.name == name:
                return node
        return None
    
    def get_tool_by_name(self, name: str) -> Optional[ToolConfig]:
        """Get a tool configuration by name"""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None
    
    def get_all_tools(self) -> List[ToolConfig]:
        """Get all tool configurations"""
        return self.tools
    
    def get_request_timeout(self) -> int:
        """Get request timeout from config or environment"""
        timeout_env = os.getenv("EDGELAKE_TIMEOUT")
        if timeout_env:
            return int(timeout_env)
        return self.client_config.get('request_timeout', 20)
    
    def get_max_workers(self) -> int:
        """Get max workers from config or environment"""
        workers_env = os.getenv("EDGELAKE_MAX_WORKERS")
        if workers_env:
            return int(workers_env)
        return self.client_config.get('max_workers', 10)
    
    def allows_custom_nodes(self) -> bool:
        """Check if custom nodes are allowed"""
        return self.client_config.get('allow_custom_nodes', True)
    
    def get_custom_node_hint(self) -> str:
        """Get hint text for custom nodes"""
        return self.client_config.get('custom_node_hint', '')
    
    def __repr__(self):
        return f"Config(nodes={len(self.nodes)}, tools={len(self.tools)})"
