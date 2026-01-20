# policy_compiler_agents/ontology_agent.py
"""
Ontology Designer Agent - Analyzes policy markdown and proposes a graph schema.

This agent reads the parsed policy document and generates a Neo4j schema
with node labels, properties, and relationship types.
"""

import os
import json
from typing import Any, Dict

from google import genai
from google.genai import types

from .tools import get_gemini_client, read_policy_markdown, save_artifact

ONTOLOGY_SYSTEM_PROMPT = """You are a Neo4j Schema Designer for retail policy documents.

CRITICAL RULES:
1. Every node MUST have a 'name' property (string, required) in addition to 'source_citation'. This ensures every entity is identifiable.
2. Use PascalCase for node labels (e.g., ReturnRule), UPPER_SNAKE_CASE for relationships (e.g., HAS_RETURN_RULE).
3. Model conditional logic with explicit condition nodes linked via REQUIRES or EXCLUDES relationships.
4. Include constraint types where appropriate (UNIQUE, NOT NULL).
5. The 'from_label' and 'to_label' in relationships MUST EXACTLY MATCH a 'label' defined in the 'nodes' array. No spelling variations or plurals.

DO NOT CREATE nodes for generic concepts: Policy, Document, Company, Website, Customer, Section, Page.

DOMAIN EXAMPLE:
{
  "nodes": [
    {
      "label": "ProductCategory",
      "description": "A category of products with specific return rules",
      "properties": [
        {"name": "name", "type": "string", "required": true},
        {"name": "source_citation", "type": "string", "required": true}
      ],
      "constraints": ["UNIQUE(name)"]
    },
    {
      "label": "ReturnRule",
      "description": "A rule specifying return window and conditions",
      "properties": [
        {"name": "name", "type": "string", "required": true},
        {"name": "days_allowed", "type": "integer", "required": false},
        {"name": "source_citation", "type": "string", "required": true}
      ]
    }
  ],
  "relationships": [
    {
      "type": "HAS_RETURN_RULE",
      "from_label": "ProductCategory",
      "to_label": "ReturnRule",
      "description": "Links a category to its applicable return rule",
      "cardinality": "1:N"
    }
  ],
  "design_rationale": "Categories link to rules; membership tiers can override via OVERRIDES relationship."
}

OUTPUT FORMAT: Valid JSON matching the structure above. Output JSON only, no additional text."""


async def design_ontology(
    policy_content: str = None,
    model: str = "gemini-3-flash-preview"
) -> Dict[str, Any]:
    """
    Analyze policy markdown and generate a graph schema.
    
    Args:
        policy_content: Optional policy markdown. If None, reads from file.
        model: Gemini model to use. Defaults to ONTOLOGY_MODEL env var or gemini-3-flash-preview.
        
    Returns:
        Schema definition with nodes and relationships
    """
    if policy_content is None:
        policy_content = read_policy_markdown()
    
    # Use environment variable for model, with sensible default
    if model is None:
        model = os.getenv("ONTOLOGY_MODEL", "gemini-3-flash-preview")
    
    client = get_gemini_client()
    
    # Streamlined user prompt (domain context only, no redundancy with system prompt)
    prompt = f"""Analyze this retail return policy document and design a comprehensive Neo4j knowledge graph schema.

POLICY DOCUMENT:
{policy_content}

Focus on capturing: product categories, return rules with time windows, membership tier overrides, 
restocking fees, non-returnable items, and special conditions (opened, defective, etc.).

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
    
    # Parse JSON response with robust error handling
    try:
        schema = json.loads(response.text)
    except json.JSONDecodeError as e:
        # Fail fast if response_mime_type didn't work
        raise ValueError(f"Failed to parse JSON response (JSONDecodeError: {e}). Raw: {response.text[:500]}")
    
    # === VALIDATION PHASE ===
    
    # 1. Validate structure types
    if not isinstance(schema.get("nodes"), list):
        raise ValueError("Schema 'nodes' must be a list")
    if not isinstance(schema.get("relationships"), list):
        raise ValueError("Schema 'relationships' must be a list")
    
    # 2. Ensure source_citation on all nodes
    for node in schema["nodes"]:
        props = [p["name"] for p in node.get("properties", [])]
        if "source_citation" not in props:
            node.setdefault("properties", []).append({
                "name": "source_citation",
                "type": "string",
                "required": True,
                "description": "Reference to source section in policy document"
            })
    
    # 3. Validate relationship integrity (from/to labels must exist)
    node_labels = {n['label'] for n in schema['nodes']}
    for rel in schema['relationships']:
        if rel['from_label'] not in node_labels:
            raise ValueError(f"Relationship '{rel['type']}' references undefined source node '{rel['from_label']}'")
        if rel['to_label'] not in node_labels:
            raise ValueError(f"Relationship '{rel['type']}' references undefined target node '{rel['to_label']}'")
    
    # Save artifact
    artifact_path = save_artifact("proposed_schema", schema)
    schema["_artifact_path"] = artifact_path
    
    return schema


async def run_ontology_agent() -> Dict[str, Any]:
    """
    Main entry point for the Ontology Designer agent.
    Reads policy, generates schema, saves artifact, returns result.
    """
    print("[ONTOLOGY] Starting schema design...")
    
    try:
        schema = await design_ontology()
        
        node_count = len(schema.get("nodes", []))
        rel_count = len(schema.get("relationships", []))
        
        print(f"[ONTOLOGY] Schema designed: {node_count} node types, {rel_count} relationship types")
        print(f"[ONTOLOGY] Saved to: {schema.get('_artifact_path')}")
        
        return {
            "status": "success",
            "schema": schema,
            "summary": {
                "node_types": node_count,
                "relationship_types": rel_count,
            }
        }
    except Exception as e:
        print(f"[ONTOLOGY] Design failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


# For testing
if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_ontology_agent())
    print(json.dumps(result, indent=2, default=str))
