"""damai-mcp: Android Emulator MCP for ticket-grabbing automation."""

from .server import main, mcp

__version__ = "0.2.3"
__all__ = ["mcp", "main", "__version__"]
