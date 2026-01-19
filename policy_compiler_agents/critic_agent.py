# policy_compiler_agents/critic_agent.py
"""
Critic Agent - Validates schema and extraction quality before graph construction.

This agent performs quality checks on the proposed schema and extracted Cypher
statements to ensure they are correct and complete before building the graph.
"""

import json
import re
from typing import Any, Dict, List

from google import genai
from google.genai import types

from .tools import get_gemini_client, load_artifact, save_artifact

CRITIC_SYSTEM_PROMPT = """You are a Quality Assurance Specialist for knowledge graph construction.
Your task is to validate schema designs and Cypher statements for correctness and completeness.

VALIDATION CRITERIA:

1. SCHEMA VALIDATION:
   - All node types have source_citation property
   - Relationships connect valid node types
   - Property types are appropriate
   - No missing essential entities

2. CYPHER VALIDATION:
   - All statements are syntactically correct
   - MERGE statements use appropriate unique identifiers
   - Relationships reference existing node patterns
   - No SQL-like errors (=, ==, wrong operators)

3. COVERAGE VALIDATION:
   - Key policy sections are represented
   - Membership tiers and overrides are captured
   - Return windows are extracted correctly
   - Restocking fees are included
   - Non-returnable items are modeled

4. SOURCE CITATION CHECK:
   - Every node has source_citation
   - Citations reference real sections

OUTPUT FORMAT:
{
  "validation_status": "approved" | "needs_revision",
  "schema_issues": [{"issue": "description", "severity": "error|warning", "fix": "suggested fix"}],
  "cypher_issues": [{"issue": "description", "statement_index": number, "severity": "error|warning", "fix": "suggested fix"}],
  "coverage_issues": [{"missing": "what's missing", "recommendation": "how to fix"}],
  "summary": "Overall assessment",
  "confidence_score": 0.0-1.0
}

Be thorough but practical. Minor warnings should not block approval."""


async def validate_artifacts(
    schema: Dict[str, Any] = None,
    extraction: Dict[str, Any] = None,
    model: str = "gemini-2.0-flash"
) -> Dict[str, Any]:
    """
    Validate the schema and extraction artifacts.
    
    Args:
        schema: Schema from Ontology Designer
        extraction: Extraction from Extraction Agent
        model: Gemini model to use
        
    Returns:
        Validation report
    """
    # Load artifacts if not provided
    if schema is None:
        try:
            schema = load_artifact("proposed_schema")
        except FileNotFoundError:
            return {
                "validation_status": "needs_revision",
                "schema_issues": [{"issue": "Schema not found", "severity": "error"}],
                "cypher_issues": [],
                "coverage_issues": [],
            }
    
    if extraction is None:
        try:
            extraction = load_artifact("extracted_cypher")
        except FileNotFoundError:
            return {
                "validation_status": "needs_revision",
                "schema_issues": [],
                "cypher_issues": [{"issue": "Extraction not found", "severity": "error"}],
                "coverage_issues": [],
            }
    
    # Perform local validation checks first
    local_issues = perform_local_validation(schema, extraction)
    
    # If critical local issues, return early
    critical_issues = [i for i in local_issues if i.get("severity") == "error"]
    if len(critical_issues) > 3:
        return {
            "validation_status": "needs_revision",
            "schema_issues": [i for i in local_issues if "schema" in i.get("type", "")],
            "cypher_issues": [i for i in local_issues if "cypher" in i.get("type", "")],
            "coverage_issues": [],
            "summary": "Multiple critical issues found in local validation",
            "confidence_score": 0.3,
        }
    
    # Use LLM for deeper validation
    client = get_gemini_client()
    
    prompt = f"""Validate this Neo4j schema and Cypher extraction for a retail return policy knowledge graph.

SCHEMA:
{json.dumps(schema, indent=2)}

CYPHER STATEMENTS (first 50):
{json.dumps(extraction.get("cypher_statements", [])[:50], indent=2)}

EXTRACTION SUMMARY:
{json.dumps(extraction.get("extraction_summary", {}), indent=2)}

Perform comprehensive validation and provide your assessment."""

    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=CRITIC_SYSTEM_PROMPT,
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    
    try:
        validation = json.loads(response.text)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
        if json_match:
            validation = json.loads(json_match.group())
        else:
            validation = {
                "validation_status": "needs_revision",
                "summary": "Could not parse validation response",
            }
    
    # Merge local issues
    if local_issues:
        validation["local_validation_issues"] = local_issues
    
    # Save artifact
    artifact_path = save_artifact("critic_report", validation)
    validation["_artifact_path"] = artifact_path
    
    return validation


def perform_local_validation(
    schema: Dict[str, Any],
    extraction: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Perform local validation checks without LLM."""
    issues = []
    
    # Check schema for source_citation
    for node in schema.get("nodes", []):
        props = [p["name"] for p in node.get("properties", [])]
        if "source_citation" not in props:
            issues.append({
                "type": "schema",
                "issue": f"Node '{node['label']}' missing source_citation",
                "severity": "error",
            })
    
    # Check Cypher syntax basics
    cypher_statements = extraction.get("cypher_statements", [])
    for i, stmt in enumerate(cypher_statements):
        if not isinstance(stmt, str):
            issues.append({
                "type": "cypher",
                "issue": f"Statement {i} is not a string",
                "severity": "error",
                "statement_index": i,
            })
            continue
        
        # Check for common syntax issues
        if "==" in stmt:
            issues.append({
                "type": "cypher",
                "issue": f"Statement {i} uses '==' instead of '='",
                "severity": "error",
                "statement_index": i,
            })
        
        if "source_citation" not in stmt.lower() and "MERGE" in stmt.upper():
            # Only check MERGE statements creating nodes
            if re.match(r'MERGE\s*\(', stmt, re.IGNORECASE):
                issues.append({
                    "type": "cypher",
                    "issue": f"Statement {i} might be missing source_citation",
                    "severity": "warning",
                    "statement_index": i,
                })
    
    return issues


async def run_critic_agent(
    schema: Dict[str, Any] = None,
    extraction: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Main entry point for the Critic agent.
    Validates schema and extraction, returns approval status.
    """
    print("🔍 Critic Agent: Validating schema and extraction...")
    
    try:
        validation = await validate_artifacts(schema=schema, extraction=extraction)
        
        status = validation.get("validation_status", "unknown")
        confidence = validation.get("confidence_score", 0)
        
        if status == "approved":
            print(f"✅ Validation APPROVED (confidence: {confidence:.1%})")
        else:
            print(f"⚠️ Validation needs revision (confidence: {confidence:.1%})")
            issues_count = (
                len(validation.get("schema_issues", [])) +
                len(validation.get("cypher_issues", []))
            )
            print(f"   Issues found: {issues_count}")
        
        print(f"📁 Saved to: {validation.get('_artifact_path')}")
        
        return {
            "status": "success",
            "validation": validation,
            "approved": status == "approved",
        }
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "approved": False,
        }


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_critic_agent())
    print(json.dumps(result, indent=2, default=str))
