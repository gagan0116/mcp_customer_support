# policy_compiler_agents/ontology_agent.py
"""
Ontology Designer Agent - Analyzes policy markdown and proposes a graph schema.

This agent reads the parsed policy document and generates a Neo4j schema
with node labels, properties, and relationship types.
"""

import json
from typing import Any, Dict

from google import genai
from google.genai import types

from .tools import get_gemini_client, read_policy_markdown, save_artifact

ONTOLOGY_SYSTEM_PROMPT = """You are a Knowledge Graph Architect specializing in retail policy documents.
Your task is to analyze a policy document and design an optimal Neo4j graph schema.

RULES:
1. Identify ALL entity types (nodes) with their properties
2. Define relationships between entities with clear semantics
3. EVERY node type MUST have a `source_citation` property for traceability
4. Support hierarchy (e.g., Category → SubCategory via SUB_CATEGORY_OF)
5. Model exceptions and overrides explicitly with relationships
6. Use descriptive, consistent naming (PascalCase for labels, UPPER_SNAKE_CASE for relationships)
7. Include constraint types where appropriate (UNIQUE, NOT NULL)

IMPORTANT CONSIDERATIONS:
- Membership tiers affect return policies - model this with OVERRIDES relationships
- Some products have restocking fees - need a way to associate fees with categories
- Non-returnable items are a special case - model as constraints or exception nodes
- Extended return periods exist for specific categories

OUTPUT FORMAT: Valid JSON with this exact structure:
{
  "nodes": [
    {
      "label": "NodeLabelName",
      "description": "What this node represents",
      "properties": [
        {"name": "property_name", "type": "string|integer|float|boolean|date", "required": true|false, "description": "..."}
      ],
      "constraints": ["UNIQUE(property_name)", "NOT_NULL(property_name)"]
    }
  ],
  "relationships": [
    {
      "type": "RELATIONSHIP_TYPE",
      "from_label": "SourceNodeLabel",
      "to_label": "TargetNodeLabel",
      "description": "What this relationship represents",
      "properties": []
    }
  ],
  "design_rationale": "Brief explanation of key design decisions"
}

Only output the JSON, no additional text."""


async def design_ontology(
    policy_content: str = None,
    model: str = "gemini-3-pro-preview"
) -> Dict[str, Any]:
    """
    Analyze policy markdown and generate a graph schema.
    
    Args:
        policy_content: Optional policy markdown. If None, reads from file.
        model: Gemini model to use
        
    Returns:
        Schema definition with nodes and relationships
    """
    if policy_content is None:
        policy_content = read_policy_markdown()
    
    client = get_gemini_client()
    
    prompt = f"""Analyze this retail return policy document and design a comprehensive Neo4j knowledge graph schema.

POLICY DOCUMENT:
{policy_content}

Generate a complete schema that captures:
1. The overall policy structure
2. Product categories and their hierarchies
3. Return rules with time windows
4. Membership tier benefits and overrides
5. Restocking fees by category
6. Non-returnable items and exceptions
7. Special conditions (damaged, defective, opened items)
8. Return methods (store, mail, manufacturer)

Remember: Every node type MUST include source_citation property."""

    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=ONTOLOGY_SYSTEM_PROMPT,
            temperature=0.1,  # Low temperature for deterministic output
            response_mime_type="application/json",
        ),
    )
    
    # Parse JSON response
    try:
        schema = json.loads(response.text)
    except json.JSONDecodeError:
        # Try to extract JSON from response
        import re
        json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if json_match:
            schema = json.loads(json_match.group())
        else:
            raise ValueError(f"Could not parse schema from response: {response.text[:500]}")
    
    # Validate required fields
    if "nodes" not in schema or "relationships" not in schema:
        raise ValueError("Schema must contain 'nodes' and 'relationships' arrays")
    
    # Ensure source_citation on all nodes
    for node in schema["nodes"]:
        props = [p["name"] for p in node.get("properties", [])]
        if "source_citation" not in props:
            node["properties"].append({
                "name": "source_citation",
                "type": "string",
                "required": True,
                "description": "Reference to source section in policy document"
            })
    
    # Save artifact
    artifact_path = save_artifact("proposed_schema", schema)
    schema["_artifact_path"] = artifact_path
    
    return schema


async def run_ontology_agent() -> Dict[str, Any]:
    """
    Main entry point for the Ontology Designer agent.
    Reads policy, generates schema, saves artifact, returns result.
    """
    print("🧠 Ontology Designer Agent: Starting schema design...")
    
    try:
        schema = await design_ontology()
        
        node_count = len(schema.get("nodes", []))
        rel_count = len(schema.get("relationships", []))
        
        print(f"✅ Schema designed: {node_count} node types, {rel_count} relationship types")
        print(f"📁 Saved to: {schema.get('_artifact_path')}")
        
        return {
            "status": "success",
            "schema": schema,
            "summary": {
                "node_types": node_count,
                "relationship_types": rel_count,
            }
        }
    except Exception as e:
        print(f"❌ Ontology design failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


# For testing
if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_ontology_agent())
    print(json.dumps(result, indent=2, default=str))
