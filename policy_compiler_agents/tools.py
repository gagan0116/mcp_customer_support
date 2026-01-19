# policy_compiler_agents/tools.py
"""
Shared tools for the Policy Compiler multi-agent system.
Provides utilities for reading policy documents, saving artifacts,
and interacting with the Neo4j knowledge graph.
"""

import os
import json
from datetime import datetime
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
POLICY_DOCS_DIR = os.path.join(PROJECT_ROOT, "policy_docs")
ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "artifacts", "knowledge_graph")

# Ensure artifacts directory exists
os.makedirs(ARTIFACTS_DIR, exist_ok=True)


def read_policy_markdown(filename: str = "combined_policy.md") -> str:
    """
    Read the parsed policy markdown file.
    
    Args:
        filename: Name of the markdown file in policy_docs/
        
    Returns:
        Content of the policy markdown file
    """
    filepath = os.path.join(POLICY_DOCS_DIR, filename)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Policy file not found: {filepath}")
    
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def save_artifact(name: str, content: Any, artifact_type: str = "json") -> str:
    """
    Save an artifact to the phase1 artifacts directory.
    
    Args:
        name: Base name of the artifact (without extension)
        content: Content to save (will be JSON serialized if not a string)
        artifact_type: "json" or "md"
        
    Returns:
        Path to the saved artifact
    """
    extension = ".json" if artifact_type == "json" else ".md"
    filepath = os.path.join(ARTIFACTS_DIR, f"{name}{extension}")
    
    # Add metadata
    if artifact_type == "json" and isinstance(content, dict):
        content["_metadata"] = {
            "generated_at": datetime.now().isoformat(),
            "artifact_name": name,
        }
    
    with open(filepath, "w", encoding="utf-8") as f:
        if artifact_type == "json":
            json.dump(content, f, indent=2, ensure_ascii=False)
        else:
            f.write(str(content))
    
    return filepath


def load_artifact(name: str, artifact_type: str = "json") -> Any:
    """
    Load a previously saved artifact.
    
    Args:
        name: Base name of the artifact (without extension)
        artifact_type: "json" or "md"
        
    Returns:
        Loaded artifact content
    """
    extension = ".json" if artifact_type == "json" else ".md"
    filepath = os.path.join(ARTIFACTS_DIR, f"{name}{extension}")
    
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Artifact not found: {filepath}")
    
    with open(filepath, "r", encoding="utf-8") as f:
        if artifact_type == "json":
            return json.load(f)
        return f.read()


def extract_section_citations(markdown_content: str) -> Dict[str, str]:
    """
    Extract section headers and their line numbers from markdown.
    Used for generating source_citation values.
    
    Args:
        markdown_content: The policy markdown content
        
    Returns:
        Dict mapping section text to section number (e.g., "Return Periods" -> "Section 3")
    """
    import re
    
    sections = {}
    current_section = "Header"
    current_subsection = ""
    
    lines = markdown_content.split("\n")
    for line in lines:
        # Match headers like "## 3. Return and Exchange Periods"
        h1_match = re.match(r'^# (.+)$', line)
        h2_match = re.match(r'^## (\d+\.?\s*)(.+)$', line)
        h3_match = re.match(r'^### (\d+\.\d+\.?\s*)(.+)$', line)
        
        if h1_match:
            current_section = "Header"
            sections[h1_match.group(1).strip()] = "Header"
        elif h2_match:
            section_num = h2_match.group(1).strip().rstrip('.')
            section_title = h2_match.group(2).strip()
            current_section = f"Section {section_num}"
            sections[section_title] = current_section
        elif h3_match:
            subsection_num = h3_match.group(1).strip().rstrip('.')
            subsection_title = h3_match.group(2).strip()
            current_subsection = f"Section {subsection_num}"
            sections[subsection_title] = current_subsection
    
    return sections


def get_gemini_client():
    """
    Get a configured Gemini client for agent operations.
    
    Returns:
        Configured genai client
    """
    from google import genai
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment")
    
    client = genai.Client(api_key=api_key)
    return client


# Pre-load policy content for agents
def get_policy_content() -> str:
    """Get the cached policy content."""
    return read_policy_markdown()
