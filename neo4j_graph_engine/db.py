# neo4j_graph_engine/db.py
"""
Neo4j connection management for the Policy Knowledge Graph.
Provides async connection handling with context managers.
"""

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession

load_dotenv()

# Connection configuration from environment
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Global driver instance (singleton pattern)
_driver: Optional[AsyncDriver] = None


def get_driver() -> AsyncDriver:
    """Get or create the Neo4j async driver singleton."""
    global _driver
    if _driver is None:
        if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
            raise ValueError(
                "Missing Neo4j credentials. Ensure NEO4J_URI, NEO4J_USER, "
                "and NEO4J_PASSWORD are set in .env"
            )
        _driver = AsyncGraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD),
        )
    return _driver


async def close_driver():
    """Close the Neo4j driver connection."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


@asynccontextmanager
async def get_session() -> AsyncSession:
    """
    Async context manager for Neo4j sessions.
    
    Usage:
        async with get_session() as session:
            result = await session.run("MATCH (n) RETURN n LIMIT 10")
    """
    driver = get_driver()
    session = driver.session()
    try:
        yield session
    finally:
        await session.close()


async def execute_query(
    query: str,
    parameters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Execute a Cypher query and return results as a list of dicts.
    
    Args:
        query: Cypher query string
        parameters: Optional query parameters
        
    Returns:
        List of record dictionaries
    """
    async with get_session() as session:
        result = await session.run(query, parameters or {})
        records = await result.data()
        return records


async def execute_write(
    query: str,
    parameters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute a write transaction (CREATE, MERGE, DELETE, etc).
    
    Args:
        query: Cypher write query
        parameters: Optional query parameters
        
    Returns:
        Summary of the write operation
    """
    async with get_session() as session:
        result = await session.run(query, parameters or {})
        summary = await result.consume()
        return {
            "nodes_created": summary.counters.nodes_created,
            "nodes_deleted": summary.counters.nodes_deleted,
            "relationships_created": summary.counters.relationships_created,
            "relationships_deleted": summary.counters.relationships_deleted,
            "properties_set": summary.counters.properties_set,
            "labels_added": summary.counters.labels_added,
        }


async def test_connection() -> Dict[str, Any]:
    """
    Test the Neo4j connection and return database info.
    
    Returns:
        Dict with connection status and database info
    """
    try:
        driver = get_driver()
        async with driver.session() as session:
            result = await session.run("RETURN 1 as test")
            await result.consume()
            
        # Get server info
        info = await driver.get_server_info()
        return {
            "status": "connected",
            "server_address": str(info.address),
            "server_version": info.agent,
            "protocol_version": str(info.protocol_version),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


# For standalone testing
if __name__ == "__main__":
    import asyncio
    
    async def main():
        result = await test_connection()
        print("Connection test:", result)
        await close_driver()
    
    asyncio.run(main())
