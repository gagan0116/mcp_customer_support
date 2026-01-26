# policy_compiler_agents/ontology_agent.py
"""
Ontology Designer Agent - Analyzes policy markdown and proposes a graph schema.

This agent reads the parsed policy document and generates a Neo4j schema
with node labels, properties, and relationship types.

Gemini 3 Features Used:
- ThinkingConfig (high level) - Deep reasoning for comprehensive schema identification
- response_schema - Structured output enforcement
- response_mime_type - JSON mode
- system_instruction - Separated from user prompt
"""

import os
import json
from typing import Any, Dict

from google.genai import types
from google.genai.types import ThinkingConfig, Schema

from .tools import get_gemini_client, read_policy_markdown, save_artifact

PROPERTY_SCHEMA = Schema(
    type="object",
    properties={
        "name": Schema(type="string", description="Property name"),
        "type": Schema(type="string", description="Property type: string, integer, float, boolean"),
        "required": Schema(type="boolean", description="Whether property is required"),
        "description": Schema(type="string", description="Description of the property"),
    },
    required=["name", "type"]
)

NODE_SCHEMA = Schema(
    type="object",
    properties={
        "label": Schema(type="string", description="Node label in PascalCase"),
        "description": Schema(type="string", description="Description of what this node represents"),
        "properties": Schema(type="array", items=PROPERTY_SCHEMA, description="List of node properties"),
        "constraints": Schema(type="array", items=Schema(type="string"), description="Constraints like UNIQUE(name)"),
    },
    required=["label", "description", "properties"]
)

RELATIONSHIP_SCHEMA = Schema(
    type="object",
    properties={
        "type": Schema(type="string", description="Relationship type in UPPER_SNAKE_CASE"),
        "from_label": Schema(type="string", description="Source node label"),
        "to_label": Schema(type="string", description="Target node label"),
        "description": Schema(type="string", description="Description of the relationship"),
        "cardinality": Schema(type="string", description="Cardinality like 1:N, N:M"),
    },
    required=["type", "from_label", "to_label", "description"]
)

ONTOLOGY_RESPONSE_SCHEMA = Schema(
    type="object",
    properties={
        "nodes": Schema(type="array", items=NODE_SCHEMA, description="List of node types"),
        "relationships": Schema(type="array", items=RELATIONSHIP_SCHEMA, description="List of relationship types"),
        "design_rationale": Schema(type="string", description="Explanation of schema design decisions"),
    },
    required=["nodes", "relationships", "design_rationale"]
)


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

ONTOLOGY_SYSTEM_PROMPT = """You are a Neo4j Schema Designer for retail policy documents.

CRITICAL RULES:
1. Every node MUST have a 'name' property (string, required) in addition to 'source_citation'. This ensures every entity is identifiable.
2. Use PascalCase for node labels (e.g., ReturnWindow), UPPER_SNAKE_CASE for relationships (e.g., HAS_RETURN_WINDOW).
3. Model conditional logic with explicit condition nodes linked via REQUIRES or EXCLUDES relationships.
4. Include constraint types where appropriate (UNIQUE, NOT NULL).
5. The 'from_label' and 'to_label' in relationships MUST EXACTLY MATCH a 'label' defined in the 'nodes' array. No spelling variations or plurals.
6. Be EXHAUSTIVE - identify ALL node types and relationships mentioned in the policy. Missing entities is worse than having too many.

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
      "label": "ReturnWindow",
      "description": "Time period allowed for returns",
      "properties": [
        {"name": "name", "type": "string", "required": true},
        {"name": "days_allowed", "type": "integer", "required": true},
        {"name": "source_citation", "type": "string", "required": true}
      ]
    }
  ],
  "relationships": [
    {
      "type": "HAS_RETURN_WINDOW",
      "from_label": "ProductCategory",
      "to_label": "ReturnWindow",
      "description": "Links a category to its applicable return window",
      "cardinality": "1:N"
    }
  ],
  "design_rationale": "Categories link to return windows; membership tiers can extend via APPLIES_TO_MEMBERSHIP relationship."
}

Think carefully through the entire document to identify:
- All product categories with different return rules
- All membership tiers and their special privileges  
- All conditions (opened, sealed, defective, etc.)
- All exceptions and special cases
- All time-based rules (return windows, extended periods)
- All fees (restocking fees, shipping fees)

OUTPUT FORMAT: Valid JSON matching the schema structure. Output JSON only, no additional text."""


# =============================================================================
# MAIN FUNCTION
# =============================================================================

async def design_ontology(
    policy_content: str = None,
    model: str = "gemini-3-pro-preview"
) -> Dict[str, Any]:
    """
    Analyze policy markdown and generate a graph schema using Gemini 3's
    Thinking Mode for comprehensive node/relationship identification.
    
    Gemini 3 Features:
    - ThinkingConfig(thinking_level="high") for deep reasoning
    - response_schema for structured output enforcement
    - response_mime_type="application/json" for JSON mode
    
    Args:
        policy_content: Optional policy markdown. If None, reads from file.
        model: Gemini model to use. Defaults to ONTOLOGY_MODEL env var or gemini-3-pro-preview.
        
    Returns:
        Schema definition with nodes and relationships
    """
    if policy_content is None:
        policy_content = read_policy_markdown()
    
    # Use environment variable override if set
    model = os.getenv("ONTOLOGY_MODEL", model)
    
    client = get_gemini_client()
    
    # Streamlined user prompt (domain context only, no redundancy with system prompt)
    prompt = f"""Analyze this retail return policy document and design a comprehensive Neo4j knowledge graph schema.

POLICY DOCUMENT:
{policy_content}

Focus on capturing: product categories, return rules with time windows, membership tier overrides, 
restocking fees, non-returnable items, and special conditions (opened, defective, etc.).

IMPORTANT: Be exhaustive in identifying ALL entity types and relationships. 
Think through every section of the document carefully.

Remember: Every node type MUST include 'name' and 'source_citation' properties."""

    print("[ONTOLOGY] Using Gemini 3 Thinking Mode (high) for comprehensive schema design...")
    
    # === GEMINI 3 ENHANCED API CALL ===
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=ONTOLOGY_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=ONTOLOGY_RESPONSE_SCHEMA,
            thinking_config=ThinkingConfig(
                thinking_level="high"
            ),
        ),
    )
    
    # Extract thinking process if available (for debugging/transparency)
    thinking_text = None
    response_text = None
    
    if hasattr(response, 'candidates') and response.candidates:
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'thought') and part.thought:
                thinking_text = part.text
                print(f"[ONTOLOGY] Thinking process captured ({len(part.text)} chars)")
            elif hasattr(part, 'text'):
                response_text = part.text
    
    # Fallback to response.text if parts parsing didn't work
    if response_text is None:
        response_text = response.text
    
    # Parse JSON response with robust error handling
    try:
        schema = json.loads(response_text)
    except json.JSONDecodeError as e:
        # Fail fast if response_mime_type didn't work
        raise ValueError(f"Failed to parse JSON response (JSONDecodeError: {e}). Raw: {response_text[:500]}")
    
    # === VALIDATION PHASE (Secondary to schema enforcement) ===
    # These checks are now a safety net since response_schema should guarantee structure
    
    # 1. Validate structure types
    if not isinstance(schema.get("nodes"), list):
        raise ValueError("Schema 'nodes' must be a list")
    if not isinstance(schema.get("relationships"), list):
        raise ValueError("Schema 'relationships' must be a list")
    
    # 2. Ensure 'name' and 'source_citation' on all nodes
    for node in schema["nodes"]:
        props = [p["name"] for p in node.get("properties", [])]
        
        # Ensure 'name' property exists
        if "name" not in props:
            node.setdefault("properties", []).insert(0, {
                "name": "name",
                "type": "string",
                "required": True,
                "description": "Unique identifier name for this entity"
            })
        
        # Ensure 'source_citation' property exists
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
    
    # Add thinking trace to schema for transparency (Gemini 3 feature)
    if thinking_text:
        schema["_thinking_trace"] = thinking_text
    
    # Save artifact
    artifact_path = save_artifact("proposed_schema", schema)
    schema["_artifact_path"] = artifact_path
    
    return schema


async def run_ontology_agent() -> Dict[str, Any]:
    """
    Main entry point for the Ontology Designer agent.
    Reads policy, generates schema, saves artifact, returns result.
    
    Uses Gemini 3 Thinking Mode for comprehensive schema identification.
    """
    print("[ONTOLOGY] Starting schema design with Gemini 3 Thinking Mode...")
    print("[ONTOLOGY] Using high thinking level for exhaustive node/relationship extraction")
    
    try:
        schema = await design_ontology()
        
        node_count = len(schema.get("nodes", []))
        rel_count = len(schema.get("relationships", []))
        has_thinking = "_thinking_trace" in schema
        
        print(f"[ONTOLOGY] Schema designed: {node_count} node types, {rel_count} relationship types")
        print(f"[ONTOLOGY] Thinking trace captured: {has_thinking}")
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


# =============================================================================
# CLI TESTING
# =============================================================================

if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_ontology_agent())
    print(json.dumps(result, indent=2, default=str))
