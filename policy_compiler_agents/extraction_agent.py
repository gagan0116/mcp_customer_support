# policy_compiler_agents/extraction_agent.py
"""
Extraction Agent - Generates Cypher MERGE statements from policy content.

This agent uses the schema from the Ontology Designer to extract
specific policy rules and generate Cypher statements for graph construction.
"""

import json
import re
from typing import Any, Dict, List

from google import genai
from google.genai import types

from .tools import (
    get_gemini_client,
    read_policy_markdown,
    save_artifact,
    load_artifact,
    extract_section_citations,
)

EXTRACTION_SYSTEM_PROMPT = """You are a Legal Knowledge Extractor specializing in retail policies.
Your task is to extract ALL policy rules from the document and generate Cypher MERGE statements.

CRITICAL RULES:
1. Use MERGE (not CREATE) to prevent duplicate nodes
2. EVERY node MUST have a source_citation property with the section number (e.g., "Section 3.1")
3. Extract ALL numeric constraints: days, fees, percentages, dollar amounts
4. For conditional rules (e.g., "60 days for Total members"), create separate rule nodes with appropriate relationships
5. Capture the full hierarchy of categories
6. Extract all exceptions and non-returnable conditions

CYPHER PATTERNS TO USE:
- For nodes: MERGE (n:Label {unique_prop: "value", source_citation: "Section X.Y"})
- For relationships: MATCH (a:LabelA {prop: "val"}), (b:LabelB {prop: "val"}) MERGE (a)-[:REL_TYPE]->(b)
- For setting additional properties: SET n.prop = value

OUTPUT FORMAT: Return a JSON object with:
{
  "cypher_statements": [
    "MERGE statement 1",
    "MERGE statement 2",
    ...
  ],
  "extraction_summary": {
    "total_rules_extracted": number,
    "categories_found": ["list", "of", "categories"],
    "relationship_types_used": ["list", "of", "relationships"]
  }
}

Only output valid JSON, no additional text."""


def build_extraction_prompt(policy_content: str, schema: Dict[str, Any]) -> str:
    """Build the extraction prompt with schema context."""
    
    # Summarize the schema for the prompt
    node_summary = []
    for node in schema.get("nodes", []):
        props = ", ".join([p["name"] for p in node.get("properties", [])])
        node_summary.append(f"- {node['label']}: {props}")
    
    rel_summary = []
    for rel in schema.get("relationships", []):
        rel_summary.append(f"- ({rel['from_label']})-[:{rel['type']}]->({rel['to_label']})")
    
    return f"""Extract ALL policy rules from this document and generate Cypher MERGE statements.

SCHEMA TO USE:

Node Types:
{chr(10).join(node_summary)}

Relationships:
{chr(10).join(rel_summary)}

POLICY DOCUMENT:
{policy_content}

REQUIREMENTS:
1. Start with the Policy node containing metadata (company_name, effective_date)
2. Create all ProductCategory nodes with their hierarchy
3. Extract every return rule with days/conditions
4. Create MembershipTier nodes and their override relationships
5. Extract all restocking fees with amounts/percentages
6. Create Exception nodes for non-returnable items and conditions
7. Include source_citation on EVERY node (use section numbers from headers)

Generate comprehensive Cypher statements that fully represent this policy in the graph."""


async def extract_policy_rules(
    policy_content: str = None,
    schema: Dict[str, Any] = None,
    model: str = "gemini-2.0-flash"
) -> Dict[str, Any]:
    """
    Extract policy rules and generate Cypher statements.
    
    Args:
        policy_content: Optional policy markdown
        schema: Schema from Ontology Designer (required)
        model: Gemini model to use
        
    Returns:
        Dict with cypher_statements and extraction summary
    """
    if policy_content is None:
        policy_content = read_policy_markdown()
    
    if schema is None:
        try:
            schema = load_artifact("proposed_schema")
        except FileNotFoundError:
            raise ValueError("Schema not found. Run Ontology Designer first.")
    
    client = get_gemini_client()
    prompt = build_extraction_prompt(policy_content, schema)
    
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=EXTRACTION_SYSTEM_PROMPT,
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    
    # Parse response
    try:
        extraction = json.loads(response.text)
    except json.JSONDecodeError:
        # Try to extract JSON
        json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if json_match:
            extraction = json.loads(json_match.group())
        else:
            raise ValueError(f"Could not parse extraction: {response.text[:500]}")
    
    # Validate
    if "cypher_statements" not in extraction:
        raise ValueError("Extraction must contain 'cypher_statements' array")
    
    # Post-process: ensure all statements are valid strings
    valid_statements = []
    for stmt in extraction["cypher_statements"]:
        if isinstance(stmt, str) and stmt.strip():
            # Basic Cypher validation
            stmt = stmt.strip()
            if stmt.upper().startswith(("MERGE", "MATCH", "CREATE", "SET")):
                valid_statements.append(stmt)
    
    extraction["cypher_statements"] = valid_statements
    
    # Save artifact
    artifact_path = save_artifact("extracted_cypher", extraction)
    extraction["_artifact_path"] = artifact_path
    
    return extraction


async def run_extraction_agent(schema: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Main entry point for the Extraction agent.
    Uses schema to extract rules and generate Cypher.
    """
    print("📋 Extraction Agent: Extracting policy rules...")
    
    try:
        extraction = await extract_policy_rules(schema=schema)
        
        stmt_count = len(extraction.get("cypher_statements", []))
        summary = extraction.get("extraction_summary", {})
        
        print(f"✅ Extracted {stmt_count} Cypher statements")
        print(f"📁 Saved to: {extraction.get('_artifact_path')}")
        
        return {
            "status": "success",
            "extraction": extraction,
            "summary": {
                "statement_count": stmt_count,
                "extraction_summary": summary,
            }
        }
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_extraction_agent())
    print(json.dumps(result, indent=2, default=str))
