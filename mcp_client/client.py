import asyncio
import sys
import os

# Add parent directory to path to find mcp_doc_server if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run():
    # Define the server connection parameters
    # We point to the python executable in the .venv and the doc_server.py script
    server_params = StdioServerParameters(
        command=sys.executable, # Uses the current python interpreter (from .venv)
        args=["mcp_doc_server/doc_server.py"],
        env=None
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 1. Initialize the connection
            await session.initialize()
            
            # 2. List available tools
            tools = await session.list_tools()
            print("\n--- Connected to MCP Server ---")
            print(f"Found {len(tools.tools)} tools:")
            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description}")

            # 3. (Optional) Call the tool directly to test connection
            # This simulates the Agent deciding to call the tool
            print("\n--- Testing Tool Call ---")
            pdf_path = os.path.abspath("artifacts/INVOICE.pdf")
            
            if os.path.exists(pdf_path):
                result = await session.call_tool("parse_invoice", arguments={"pdf_path": pdf_path})
                print("Tool Output (First 200 chars):")
                # The result content is a list of TextContent or ImageContent
                print(result.content[0].text[:200] + "...")
            else:
                print(f"Skipping test: {pdf_path} not found")

if __name__ == "__main__":
    asyncio.run(run())