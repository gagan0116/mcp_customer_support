# policy_compiler_agents/critic_agent.py
"""
Critic Agent - Validates schema and extraction quality before graph construction.

This agent performs quality checks on the proposed schema and extracted Cypher
statements to ensure they are correct and complete before building the graph.

Gemini 3 Features Used:
- ThinkingConfig (high level) - Deep reasoning for thorough validation
- response_schema - Structured output enforcement
- response_mime_type - JSON mode
- system_instruction - Separated from user prompt
"""

import json
import os
import re
import asyncio
from typing import Any, Dict, List

from google.genai import types
from google.genai.types import ThinkingConfig, Schema

from .tools import get_gemini_client, load_artifact, save_artifact

# Retry settings for transient API errors (503, 429)
MAX_RETRIES = 3
BASE_DELAY = 5.0


# =============================================================================
# GEMINI 3 SCHEMA ENFORCEMENT
# =============================================================================

SCHEMA_ISSUE_SCHEMA = Schema(
    type="object",
    properties={
        "issue": Schema(type="string", description="Description of the issue"),
        "severity": Schema(type="string", description="error or warning"),
        "fix": Schema(type="string", description="Suggested fix"),
    },
    required=["issue", "severity"]
)

CYPHER_ISSUE_SCHEMA = Schema(
    type="object",
    properties={
        "issue": Schema(type="string", description="Description of the issue"),
        "statement_index": Schema(type="integer", description="Index of problematic statement"),
        "severity": Schema(type="string", description="error or warning"),
        "fix": Schema(type="string", description="Suggested fix"),
    },
    required=["issue", "severity"]
)

COVERAGE_ISSUE_SCHEMA = Schema(
    type="object",
    properties={
        "missing": Schema(type="string", description="What is missing"),
        "recommendation": Schema(type="string", description="How to fix"),
    },
    required=["missing", "recommendation"]
)

VALIDATION_RESPONSE_SCHEMA = Schema(
    type="object",
    properties={
        "validation_status": Schema(type="string", description="approved or needs_revision"),
        "schema_issues": Schema(type="array", items=SCHEMA_ISSUE_SCHEMA, description="Schema issues found"),
        "cypher_issues": Schema(type="array", items=CYPHER_ISSUE_SCHEMA, description="Cypher issues found"),
        "coverage_issues": Schema(type="array", items=COVERAGE_ISSUE_SCHEMA, description="Coverage gaps"),
        "summary": Schema(type="string", description="Overall assessment"),
        "confidence_score": Schema(type="number", description="Confidence score 0.0-1.0"),
    },
    required=["validation_status", "summary", "confidence_score"]
)

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
    model: str = "gemini-3-pro-preview"
) -> Dict[str, Any]:
    """
    Validate the schema and extraction artifacts using Gemini 3's Thinking Mode.
    
    Gemini 3 Features:
    - ThinkingConfig(thinking_level="high") for thorough validation
    - response_schema for structured output enforcement
    - response_mime_type="application/json" for JSON mode
    
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
    
    # Use environment variable override if set
    model = os.getenv("CRITIC_MODEL", model)
    
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

    print("[CRITIC] Using Gemini 3 Thinking Mode (high) for thorough validation...")
    
    # === API CALL WITH RETRY FOR TRANSIENT ERRORS ===
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=CRITIC_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=VALIDATION_RESPONSE_SCHEMA,
                    thinking_config=ThinkingConfig(
                        thinking_level="high"
                    ),
                ),
            )
            break  # Success, exit retry loop
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            is_retryable = "503" in str(e) or "429" in str(e) or "overloaded" in error_str or "unavailable" in error_str
            if is_retryable and attempt < MAX_RETRIES - 1:
                delay = BASE_DELAY * (2 ** attempt)
                print(f"[CRITIC] API error (attempt {attempt + 1}/{MAX_RETRIES}): {str(e)[:80]}")
                print(f"[CRITIC] Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                raise
    else:
        raise last_error  # All retries failed
    
    # Extract response text (handle thinking mode response structure)
    response_text = response.text
    if hasattr(response, 'candidates') and response.candidates:
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'text') and not (hasattr(part, 'thought') and part.thought):
                response_text = part.text
                break
    
    try:
        validation = json.loads(response_text)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            validation = json.loads(json_match.group())
        else:
            validation = {
                "validation_status": "needs_revision",
                "summary": "Could not parse validation response",
                "confidence_score": 0.0,
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
    
    # Check linker warnings (orphaned relationships that couldn't be resolved)
    linker_warnings = extraction.get("extraction_summary", {}).get("linker_warnings", 0)
    if linker_warnings > 10:
        issues.append({
            "type": "extraction",
            "issue": f"Too many orphaned relationships: {linker_warnings} relationships could not be connected",
            "severity": "error",
        })
    elif linker_warnings > 0:
        issues.append({
            "type": "extraction",
            "issue": f"{linker_warnings} relationships could not be connected (minor)",
            "severity": "warning",
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
    extraction: Dict[str, Any] = None,
    log_callback: callable = None
) -> Dict[str, Any]:
    """
    Main entry point for the Critic agent.
    Validates schema and extraction, returns approval status.
    
    Args:
        schema: The schema from Ontology Agent
        extraction: The extraction from Extraction Agent
        log_callback: Optional callback for progress logging
    """
    log = log_callback or (lambda msg: print(msg))
    
    log("[CRITIC] Validating schema and extraction...")
    
    try:
        validation = await validate_artifacts(schema=schema, extraction=extraction)
        
        status = validation.get("validation_status", "unknown")
        confidence = validation.get("confidence_score", 0)
        
        if status == "approved":
            log(f"[CRITIC] ✓ Validation APPROVED (confidence: {confidence:.1%})")
        else:
            issues_count = (
                len(validation.get("schema_issues", [])) +
                len(validation.get("cypher_issues", []))
            )
            log(f"[CRITIC] Validation needs revision (confidence: {confidence:.1%})")
            log(f"[CRITIC] Issues found: {issues_count}")
        
        return {
            "status": "success",
            "validation": validation,
            "approved": status == "approved",
        }
    except Exception as e:
        log(f"[CRITIC] Validation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "approved": False,
        }


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_critic_agent())
    print(json.dumps(result, indent=2, default=str))
