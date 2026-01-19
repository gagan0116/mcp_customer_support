# policy_compiler_agents/builder_agent.py
"""
Graph Builder Agent - Executes Cypher statements in Neo4j.

This agent takes the validated Cypher statements and executes them
in the Neo4j database to build the knowledge graph.
"""

import json
import asyncio
from typing import Any, Dict, List

from .tools import load_artifact, save_artifact

# Import Neo4j operations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from neo4j_graph_engine.db import (
    execute_write,
    execute_query,
    test_connection,
    close_driver,
)


async def create_schema_constraints() -> Dict[str, Any]:
    """Create recommended indexes and constraints."""
    constraints = [
        "CREATE CONSTRAINT policy_name IF NOT EXISTS FOR (p:Policy) REQUIRE p.company_name IS UNIQUE",
        "CREATE CONSTRAINT category_name IF NOT EXISTS FOR (c:ProductCategory) REQUIRE c.name IS UNIQUE",
        "CREATE CONSTRAINT tier_name IF NOT EXISTS FOR (t:MembershipTier) REQUIRE t.tier_name IS UNIQUE",
        "CREATE INDEX rule_days IF NOT EXISTS FOR (r:ReturnRule) ON (r.return_days)",
        "CREATE INDEX source_citation IF NOT EXISTS FOR (n:ReturnRule) ON (n.source_citation)",
    ]
    
    results = []
    for constraint in constraints:
        try:
            await execute_write(constraint)
            results.append({"query": constraint[:60], "status": "success"})
        except Exception as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                results.append({"query": constraint[:60], "status": "already_exists"})
            else:
                results.append({"query": constraint[:60], "status": "error", "error": error_msg[:100]})
    
    return {"constraints": results}


async def clear_existing_graph() -> Dict[str, Any]:
    """Clear all existing nodes and relationships."""
    try:
        # Delete relationships first
        await execute_write("MATCH ()-[r]->() DELETE r")
        # Then delete nodes
        result = await execute_write("MATCH (n) DELETE n")
        return {"status": "cleared", "summary": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def execute_cypher_batch(
    statements: List[str],
    batch_size: int = 10,
    stop_on_error: bool = False
) -> Dict[str, Any]:
    """
    Execute Cypher statements in batches.
    
    Args:
        statements: List of Cypher statements
        batch_size: Number of statements per batch
        stop_on_error: Whether to stop on first error
        
    Returns:
        Execution summary
    """
    results = []
    total_nodes_created = 0
    total_rels_created = 0
    errors = []
    
    for i, stmt in enumerate(statements):
        try:
            summary = await execute_write(stmt)
            total_nodes_created += summary.get("nodes_created", 0)
            total_rels_created += summary.get("relationships_created", 0)
            results.append({
                "index": i,
                "status": "success",
                "nodes": summary.get("nodes_created", 0),
                "rels": summary.get("relationships_created", 0),
            })
        except Exception as e:
            error_info = {
                "index": i,
                "status": "error",
                "error": str(e)[:200],
                "statement": stmt[:100],
            }
            errors.append(error_info)
            results.append(error_info)
            
            if stop_on_error:
                break
        
        # Progress logging
        if (i + 1) % batch_size == 0:
            print(f"   Executed {i + 1}/{len(statements)} statements...")
    
    return {
        "total_statements": len(statements),
        "successful": len([r for r in results if r["status"] == "success"]),
        "failed": len(errors),
        "total_nodes_created": total_nodes_created,
        "total_relationships_created": total_rels_created,
        "errors": errors[:10],  # Limit error details
    }


async def verify_graph() -> Dict[str, Any]:
    """Verify the constructed graph."""
    try:
        # Get node counts by label
        label_counts = await execute_query("""
            MATCH (n)
            UNWIND labels(n) as label
            RETURN label, count(*) as count
            ORDER BY count DESC
        """)
        
        # Get relationship counts
        rel_counts = await execute_query("""
            MATCH ()-[r]->()
            RETURN type(r) as type, count(*) as count
            ORDER BY count DESC
        """)
        
        # Check for source citations
        citation_check = await execute_query("""
            MATCH (n)
            WHERE n.source_citation IS NOT NULL
            RETURN count(n) as with_citation
        """)
        
        total_nodes = await execute_query("MATCH (n) RETURN count(n) as count")
        
        return {
            "status": "success",
            "total_nodes": total_nodes[0]["count"] if total_nodes else 0,
            "nodes_by_label": {r["label"]: r["count"] for r in label_counts},
            "relationships_by_type": {r["type"]: r["count"] for r in rel_counts},
            "nodes_with_citations": citation_check[0]["with_citation"] if citation_check else 0,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def build_graph(
    extraction: Dict[str, Any] = None,
    clear_existing: bool = True,
    create_constraints: bool = True
) -> Dict[str, Any]:
    """
    Build the knowledge graph from extracted Cypher statements.
    
    Args:
        extraction: Extraction artifact with cypher_statements
        clear_existing: Whether to clear existing graph first
        create_constraints: Whether to create indexes/constraints
        
    Returns:
        Build results and verification
    """
    # Test connection first
    conn_test = await test_connection()
    if conn_test.get("status") != "connected":
        return {
            "status": "error",
            "error": f"Neo4j connection failed: {conn_test.get('error')}",
        }
    
    # Load extraction if not provided
    if extraction is None:
        try:
            extraction = load_artifact("extracted_cypher")
        except FileNotFoundError:
            return {
                "status": "error",
                "error": "Extraction artifact not found. Run Extraction Agent first.",
            }
    
    statements = extraction.get("cypher_statements", [])
    if not statements:
        return {
            "status": "error",
            "error": "No Cypher statements to execute",
        }
    
    build_log = {
        "connection": conn_test,
        "statements_to_execute": len(statements),
    }
    
    # Clear existing graph if requested
    if clear_existing:
        print("   Clearing existing graph...")
        clear_result = await clear_existing_graph()
        build_log["clear_result"] = clear_result
    
    # Create constraints if requested
    if create_constraints:
        print("   Creating schema constraints...")
        constraint_result = await create_schema_constraints()
        build_log["constraints"] = constraint_result
    
    # Execute statements
    print(f"   Executing {len(statements)} Cypher statements...")
    execution_result = await execute_cypher_batch(statements)
    build_log["execution"] = execution_result
    
    # Verify the graph
    print("   Verifying graph...")
    verification = await verify_graph()
    build_log["verification"] = verification
    
    # Determine overall status
    if execution_result["failed"] == 0 and verification.get("total_nodes", 0) > 0:
        build_log["status"] = "success"
    elif execution_result["successful"] > 0 and verification.get("total_nodes", 0) > 0:
        build_log["status"] = "partial_success"
    else:
        build_log["status"] = "failed"
    
    # Save build log
    artifact_path = save_artifact("build_log", build_log)
    build_log["_artifact_path"] = artifact_path
    
    return build_log


async def run_builder_agent(
    extraction: Dict[str, Any] = None,
    clear_existing: bool = True
) -> Dict[str, Any]:
    """
    Main entry point for the Graph Builder agent.
    Builds the knowledge graph from extraction artifact.
    """
    print("🏗️ Graph Builder Agent: Building knowledge graph...")
    
    try:
        result = await build_graph(
            extraction=extraction,
            clear_existing=clear_existing,
        )
        
        status = result.get("status", "unknown")
        verification = result.get("verification", {})
        
        if status == "success":
            print(f"✅ Graph built successfully!")
            print(f"   Nodes: {verification.get('total_nodes', 0)}")
            print(f"   With citations: {verification.get('nodes_with_citations', 0)}")
        elif status == "partial_success":
            print(f"⚠️ Graph built with some errors")
            print(f"   Nodes: {verification.get('total_nodes', 0)}")
        else:
            print(f"❌ Graph build failed")
        
        print(f"📁 Log saved to: {result.get('_artifact_path')}")
        
        return {"status": "success", "build_result": result}
        
    except Exception as e:
        print(f"❌ Build failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        await close_driver()


if __name__ == "__main__":
    result = asyncio.run(run_builder_agent())
    print(json.dumps(result, indent=2, default=str))
