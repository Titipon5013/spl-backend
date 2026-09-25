"""stdio entrypoint, used by reference MCP clients such as Claude Desktop.

    python -m mcp_server

Authentication is not applied on this transport: stdio means the client already
runs as a local process on the server, so the operating system is the trust
boundary. Rate limiting still applies.
"""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

os.environ["SQL_ECHO"] = "false"
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

from mcp_server.server import mcp  # noqa: E402


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
