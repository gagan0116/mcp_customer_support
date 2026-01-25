# policy_compiler_agents/extraction_agent.py
"""
Extraction Agent - 3-Phase Pipeline for Policy Knowledge Graph Construction.

Phase 1: TripletExtractor - LLM-based entity/relationship extraction
Phase 2: GraphLinker - Python-based validation and resolution
Phase 3: CypherGenerator - Cypher statement generation

Gemini 3 Features Used:
- ThinkingConfig (high level) - Deep reasoning for exhaustive extraction
- response_schema - Structured output enforcement
- response_mime_type - JSON mode
- system_instruction - Separated from user prompt
"""

import os
import asyncio
import json
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Tuple, Optional

from google.genai import types
from google.genai.types import ThinkingConfig, Schema

from .tools import (
    get_gemini_client,
    read_policy_markdown,
    save_artifact,
    load_artifact,
    CitationManager,
    POLICY_DOCS_DIR,
)


# =============================================================================
# GEMINI 3 SCHEMA ENFORCEMENT
# =============================================================================

ENTITY_SCHEMA = Schema(
    type="object",
    properties={
        "label": Schema(type="string", description="Node label from schema"),
        "properties": Schema(type="object", description="Entity properties including 'name'"),
        "text_excerpt": Schema(type="string", description="Exact phrase from document for citation"),
    },
    required=["label", "properties"]
)

RELATIONSHIP_EXTRACT_SCHEMA = Schema(
    type="object",
    properties={
        "from_label": Schema(type="string", description="Source node label"),
        "from_name": Schema(type="string", description="Source entity name - must match entity name exactly"),
        "type": Schema(type="string", description="Relationship type in UPPER_SNAKE_CASE"),
        "to_label": Schema(type="string", description="Target node label"),
        "to_name": Schema(type="string", description="Target entity name - must match entity name exactly"),
    },
    required=["from_label", "from_name", "type", "to_label", "to_name"]
)

EXTRACTION_RESPONSE_SCHEMA = Schema(
    type="object",
    properties={
        "entities": Schema(type="array", items=ENTITY_SCHEMA, description="List of extracted entities"),
        "relationships": Schema(type="array", items=RELATIONSHIP_EXTRACT_SCHEMA, description="List of extracted relationships"),
    },
    required=["entities", "relationships"]
)

# =============================================================================
# PHASE 1: TRIPLET EXTRACTOR (LLM)
# =============================================================================

PAGE_EXTRACTION_PROMPT = """You are a Legal Knowledge Extractor. Extract entities and relationships from this policy page.

OUTPUT FORMAT - Return valid JSON:
{
  "entities": [
    {
      "label": "ReturnRule",
      "properties": {"name": "15 Day Return Period", "days_allowed": 15},
      "text_excerpt": "15 days"
    }
  ],
  "relationships": [
    {
      "from_label": "ProductCategory",
      "from_name": "Laptops",
      "type": "HAS_RETURN_RULE",
      "to_label": "ReturnRule", 
      "to_name": "15 Day Return Period"
    }
  ]
}

CRITICAL RULES:
1. CONSISTENCY IS KING: The 'from_name' and 'to_name' in relationships MUST EXACTLY MATCH the 'name' property of the corresponding Entity.
   - BAD: Entity name="15 Day Rule", Relationship to_name="15 days"
   - GOOD: Entity name="15 Day Rule", Relationship to_name="15 Day Rule"
2. Extract ALL entities mentioned on this page.
3. Include text_excerpt - the exact phrase from the document (for citation).
4. Use schema node types provided.
5. Only output valid JSON.
6. EXHAUSTIVE EXTRACTION: Extract ALL relationships implied by the text. Missing a relationship is worse. When in doubt, extract it."""


def split_by_page_markers(markdown: str) -> List[Dict[str, Any]]:
    """Split markdown content by page markers."""
    pages = []
    current_page = None
    current_lines = []
    
    page_pattern = re.compile(r'<!--\s*PAGE:([^:]+):(\d+):(\d+):(\d+)\s*-->')
    
    for line in markdown.split("\n"):
        match = page_pattern.match(line)
        if match:
            if current_page is not None:
                current_page["content"] = "\n".join(current_lines)
                pages.append(current_page)
            
            current_page = {
                "filename": match.group(1),
                "page_num": int(match.group(2)),
                "start_line": int(match.group(3)),
                "end_line": int(match.group(4)),
            }
            current_lines = []
        else:
            current_lines.append(line)
    
    if current_page is not None:
        current_page["content"] = "\n".join(current_lines)
        pages.append(current_page)
    
    return pages


def build_page_prompt(page: Dict[str, Any], schema: Dict[str, Any]) -> str:
    """Build extraction prompt for a single page."""
    node_summary = []
    for node in schema.get("nodes", []):
        props = ", ".join([p["name"] for p in node.get("properties", [])])
        node_summary.append(f"- {node['label']}: {props}")
    
    rel_summary = []
    for rel in schema.get("relationships", []):
        rel_summary.append(f"- ({rel['from_label']})-[:{rel['type']}]->({rel['to_label']})")
    
    return f"""Extract entities and relationships from this policy page.

SCHEMA (use these node types):
{chr(10).join(node_summary)}

RELATIONSHIPS:
{chr(10).join(rel_summary)}

PAGE CONTENT (from {page['filename']} page {page['page_num']}):
{page['content']}

Extract ALL entities and relationships from this page. Do not skip any."""


async def extract_from_page(
    page: Dict[str, Any],
    schema: Dict[str, Any],
    client,
    model: str = "gemini-3-pro-preview",
    max_retries: int = 3,
    timeout_seconds: int = 120  # Increased for high thinking mode
) -> Dict[str, Any]:
    """
    Extract entities from a single page using Gemini 3's Thinking Mode.
    
    Gemini 3 Features:
    - ThinkingConfig(thinking_level="high") for exhaustive extraction
    - response_schema for structured output enforcement
    - response_mime_type="application/json" for JSON mode
    """
    prompt = build_page_prompt(page, schema)
    
    for attempt in range(max_retries):
        try:
            # Wrap API call with timeout (increased for thinking mode)
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=PAGE_EXTRACTION_PROMPT,
                        temperature=0.0,
                        response_mime_type="application/json",
                        response_schema=EXTRACTION_RESPONSE_SCHEMA,  # Gemini 3: Schema enforcement
                        thinking_config=ThinkingConfig(
                            thinking_level="high"  # Gemini 3: Deep reasoning for exhaustive extraction
                        ),
                    ),
                ),
                timeout=timeout_seconds
            )
            
            # Extract response text (handle thinking mode response structure)
            response_text = response.text
            if hasattr(response, 'candidates') and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and not (hasattr(part, 'thought') and part.thought):
                        response_text = part.text
                        break
            
            result = json.loads(response_text)
            
            # Add page info to each entity for citation
            for entity in result.get("entities", []):
                entity["_page"] = page["page_num"]
                entity["_filename"] = page["filename"]
            
            return result
            
        except asyncio.TimeoutError:
            print(f"   [WARN] Page {page['page_num']} attempt {attempt + 1} timed out after {timeout_seconds}s. Retrying...")
            await asyncio.sleep(2)
        except (json.JSONDecodeError, Exception) as e:
            if attempt < max_retries - 1:
                print(f"   [WARN] Page {page['page_num']} attempt {attempt + 1} failed: {str(e)[:50]}. Retrying...")
                await asyncio.sleep(1 * (attempt + 1))
            else:
                print(f"   [ERROR] Page {page['page_num']} failed after {max_retries} attempts")
                return {"entities": [], "relationships": []}
    
    return {"entities": [], "relationships": []}


async def extract_all_pages(
    policy_content: str,
    schema: Dict[str, Any],
    model: str = "gemini-3-pro-preview"
) -> Tuple[List[Dict], List[Dict]]:
    """
    Phase 1: Extract triplets from all pages.
    Returns: (all_entities, all_relationships)
    """
    client = get_gemini_client()
    pages = split_by_page_markers(policy_content)
    
    if not pages:
        pages = [{
            "filename": "policy.pdf",
            "page_num": 1,
            "start_line": 1,
            "end_line": len(policy_content.split("\n")),
            "content": policy_content
        }]
    
    print(f"   [EXTRACT] Processing {len(pages)} pages...")
    
    all_entities = []
    all_relationships = []
    
    for i, page in enumerate(pages):
        print(f"   [EXTRACT] Processing page {i + 1}/{len(pages)}")
        result = await extract_from_page(page, schema, client, model)
        all_entities.extend(result.get("entities", []))
        all_relationships.extend(result.get("relationships", []))
        
        # Small delay between pages to avoid rate limiting
        if i < len(pages) - 1:
            await asyncio.sleep(1)
    
    print(f"   [EXTRACT] Raw extraction: {len(all_entities)} entities, {len(all_relationships)} relationships")
    
    return all_entities, all_relationships


# =============================================================================
# PHASE 2: GRAPH LINKER (Python Validation)
# =============================================================================

class GraphLinker:
    """
    Validates and resolves entity/relationship consistency.
    Fixes name mismatches and type coercion issues.
    """
    
    def __init__(self, schema: Dict[str, Any]):
        self.schema = schema
        self.entity_registry: Dict[Tuple[str, str], Dict] = {}  # (label, name) -> entity
        self.schema_types = self._build_schema_types()
        self.warnings: List[str] = []
    
    def _build_schema_types(self) -> Dict[str, Dict[str, str]]:
        """Build a map of label -> {property_name: type}."""
        types_map = {}
        for node in self.schema.get("nodes", []):
            label = node["label"]
            types_map[label] = {}
            for prop in node.get("properties", []):
                types_map[label][prop["name"]] = prop.get("type", "string")
        return types_map
    
    def build_registry(self, entities: List[Dict]) -> None:
        """Index all entities by (label, name) for lookup."""
        for entity in entities:
            label = entity.get("label", "")
            name = entity.get("properties", {}).get("name", "")
            if label and name:
                key = (label.lower(), name.lower())
                if key not in self.entity_registry:
                    self.entity_registry[key] = entity
    
    def _fuzzy_match(self, target_label: str, target_name: str, threshold: float = 0.8) -> Optional[str]:
        """Find the best matching entity name using fuzzy matching."""
        best_match = None
        best_score = 0.0
        
        for (label, name), entity in self.entity_registry.items():
            if label != target_label.lower():
                continue
            
            score = SequenceMatcher(None, name, target_name.lower()).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_match = entity.get("properties", {}).get("name", name)
        
        return best_match
    
    def validate_types(self, entities: List[Dict]) -> List[Dict]:
        """Coerce property types to match schema definitions."""
        for entity in entities:
            label = entity.get("label", "")
            props = entity.get("properties", {})
            schema_props = self.schema_types.get(label, {})
            
            for prop_name, prop_value in list(props.items()):
                expected_type = schema_props.get(prop_name)
                
                if expected_type == "integer" and isinstance(prop_value, str):
                    # Try to extract integer from string like "15 days" -> 15
                    match = re.search(r'\d+', prop_value)
                    if match:
                        props[prop_name] = int(match.group())
                
                elif expected_type == "float" and isinstance(prop_value, str):
                    match = re.search(r'[\d.]+', prop_value)
                    if match:
                        try:
                            props[prop_name] = float(match.group())
                        except ValueError:
                            pass
                
                elif expected_type == "boolean" and isinstance(prop_value, str):
                    props[prop_name] = prop_value.lower() in ("true", "yes", "1")
        
        return entities
    
    def resolve_relationships(self, relationships: List[Dict]) -> List[Dict]:
        """Fix name mismatches in relationships using fuzzy matching."""
        resolved = []
        
        for rel in relationships:
            from_label = rel.get("from_label", "")
            from_name = rel.get("from_name", "")
            to_label = rel.get("to_label", "")
            to_name = rel.get("to_name", "")
            
            # Check if from_name exists
            from_key = (from_label.lower(), from_name.lower())
            if from_key not in self.entity_registry:
                matched = self._fuzzy_match(from_label, from_name)
                if matched:
                    self.warnings.append(f"[LINKER] Resolved '{from_name}' -> '{matched}' for {rel['type']}")
                    rel["from_name"] = matched
                else:
                    self.warnings.append(f"[LINKER] Orphan relationship: {from_label}:'{from_name}' not found")
                    continue  # Skip orphaned relationship
            
            # Check if to_name exists
            to_key = (to_label.lower(), to_name.lower())
            if to_key not in self.entity_registry:
                matched = self._fuzzy_match(to_label, to_name)
                if matched:
                    self.warnings.append(f"[LINKER] Resolved '{to_name}' -> '{matched}' for {rel['type']}")
                    rel["to_name"] = matched
                else:
                    self.warnings.append(f"[LINKER] Orphan relationship: {to_label}:'{to_name}' not found")
                    continue  # Skip orphaned relationship
            
            resolved.append(rel)
        
        return resolved
    
    def deduplicate_entities(self, entities: List[Dict]) -> List[Dict]:
        """Remove duplicate entities by (label, name)."""
        seen = set()
        unique = []
        
        for entity in entities:
            label = entity.get("label", "")
            name = entity.get("properties", {}).get("name", "")
            key = (label.lower(), name.lower())
            
            if key not in seen:
                seen.add(key)
                unique.append(entity)
        
        return unique
    
    def run(self, entities: List[Dict], relationships: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Execute full linking pipeline."""
        print(f"   [LINKER] Input: {len(entities)} entities, {len(relationships)} relationships")
        
        # Step 1: Deduplicate
        entities = self.deduplicate_entities(entities)
        print(f"   [LINKER] After dedup: {len(entities)} entities")
        
        # Step 2: Build registry
        self.build_registry(entities)
        
        # Step 3: Validate types
        entities = self.validate_types(entities)
        
        # Step 4: Resolve relationships
        relationships = self.resolve_relationships(relationships)
        print(f"   [LINKER] After resolution: {len(relationships)} valid relationships")
        
        # Log warnings
        for warning in self.warnings[:10]:  # Limit to first 10
            print(f"   {warning}")
        if len(self.warnings) > 10:
            print(f"   [LINKER] ... and {len(self.warnings) - 10} more warnings")
        
        return entities, relationships


# =============================================================================
# PHASE 3: CYPHER GENERATOR (Python)
# =============================================================================

def generate_cypher_statements(
    entities: List[Dict],
    relationships: List[Dict],
    schema: Dict[str, Any]
) -> List[str]:
    """Generate Cypher MERGE statements from validated entities and relationships."""
    statements = []
    
    # Case-insensitive label lookup
    valid_labels = {node["label"].lower(): node["label"] for node in schema.get("nodes", [])}
    
    # Generate node statements
    for entity in entities:
        raw_label = entity.get("label", "")
        label = valid_labels.get(raw_label.lower(), raw_label)
        props = entity.get("properties", {})
        citation = entity.get("source_citation", "")
        
        if not props.get("name"):
            continue  # Skip entities without names (GraphLinker should have caught this)
        
        prop_parts = []
        for key, value in props.items():
            if key == "source_citation" and citation:
                continue
            
            if isinstance(value, str):
                safe_value = value.replace('"', '\\"')
                prop_parts.append(f'{key}: "{safe_value}"')
            elif isinstance(value, (int, float)):
                prop_parts.append(f'{key}: {value}')
            elif isinstance(value, bool):
                prop_parts.append(f'{key}: {"true" if value else "false"}')
        
        if citation:
            safe_citation = citation.replace('"', '\\"')
            prop_parts.append(f'source_citation: "{safe_citation}"')
        
        prop_string = ", ".join(prop_parts)
        stmt = f"MERGE (n:{label} {{{prop_string}}})"
        statements.append(stmt)
    
    # Generate relationship statements
    for rel in relationships:
        from_label = valid_labels.get(rel.get("from_label", "").lower(), rel.get("from_label", ""))
        from_name = rel.get("from_name", "")
        rel_type = rel.get("type", "")
        to_label = valid_labels.get(rel.get("to_label", "").lower(), rel.get("to_label", ""))
        to_name = rel.get("to_name", "")
        
        if not all([from_label, from_name, rel_type, to_label, to_name]):
            continue
        
        safe_from = from_name.replace('"', '\\"')
        safe_to = to_name.replace('"', '\\"')
        
        stmt = f'MATCH (a:{from_label} {{name: "{safe_from}"}}), (b:{to_label} {{name: "{safe_to}"}}) MERGE (a)-[:{rel_type}]->(b)'
        statements.append(stmt)
    
    return statements


# =============================================================================
# MAIN PIPELINE
# =============================================================================

async def extract_policy_rules(
    policy_content: str = None,
    schema: Dict[str, Any] = None,
    model: str = None
) -> Dict[str, Any]:
    """
    Full extraction pipeline: Extract -> Link -> Generate.
    """
    if policy_content is None:
        policy_content = read_policy_markdown()
    
    if schema is None:
        try:
            schema = load_artifact("proposed_schema")
        except FileNotFoundError:
            raise ValueError("Schema not found. Run Ontology Designer first.")
    
    if model is None:
        model = os.getenv("EXTRACTION_MODEL", "gemini-3-pro-preview")
    
    # Phase 1: Extract raw triplets
    raw_entities, raw_relationships = await extract_all_pages(policy_content, schema, model)
    
    # Phase 2: Link and validate
    linker = GraphLinker(schema)
    clean_entities, clean_relationships = linker.run(raw_entities, raw_relationships)
    
    # Add citations programmatically
    cm = CitationManager()
    clean_entities = cm.add_citations_to_entities(clean_entities)
    
    # Phase 3: Generate Cypher
    cypher_statements = generate_cypher_statements(clean_entities, clean_relationships, schema)
    
    extraction = {
        "cypher_statements": cypher_statements,
        "extraction_summary": {
            "total_pages": len(split_by_page_markers(policy_content)) or 1,
            "raw_entities": len(raw_entities),
            "raw_relationships": len(raw_relationships),
            "clean_entities": len(clean_entities),
            "clean_relationships": len(clean_relationships),
            "cypher_count": len(cypher_statements),
            "linker_warnings": len(linker.warnings),
        },
        "entities": clean_entities,
        "relationships": clean_relationships,
    }
    
    artifact_path = save_artifact("extracted_cypher", extraction)
    extraction["_artifact_path"] = artifact_path
    
    return extraction


async def run_extraction_agent(schema: Dict[str, Any] = None) -> Dict[str, Any]:
    """Main entry point for the Extraction agent."""
    print("[EXTRACTION] Starting 3-phase extraction pipeline...")
    
    try:
        extraction = await extract_policy_rules(schema=schema)
        
        summary = extraction.get("extraction_summary", {})
        
        print(f"[EXTRACTION] Complete: {summary.get('cypher_count', 0)} Cypher statements")
        print(f"[EXTRACTION] Saved to: {extraction.get('_artifact_path')}")
        
        return {
            "status": "success",
            "extraction": extraction,
            "summary": summary
        }
    except Exception as e:
        print(f"[EXTRACTION] Failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    result = asyncio.run(run_extraction_agent())
    print(json.dumps(result, indent=2, default=str))
