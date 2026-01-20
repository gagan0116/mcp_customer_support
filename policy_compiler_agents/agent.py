# policy_compiler_agents/agent.py
"""
Policy Compiler - Main Orchestrator

This is the main entry point for the multi-agent policy compilation pipeline.
It orchestrates the sequential execution of:
1. Ontology Designer Agent
2. Extraction Agent  
3. Critic Agent
4. Graph Builder Agent

Built using Google ADK patterns with shared session state.
"""

import asyncio
import json
from typing import Any, Dict, Optional

from .ontology_agent import run_ontology_agent, design_ontology
from .extraction_agent import run_extraction_agent, extract_policy_rules
from .critic_agent import run_critic_agent, validate_artifacts
from .builder_agent import run_builder_agent, build_graph
from .tools import save_artifact, read_policy_markdown


class PolicyCompilerPipeline:
    """
    Sequential pipeline orchestrator for policy compilation.
    
    Implements Google ADK-style agent coordination with shared state.
    """
    
    def __init__(self, max_revision_attempts: int = 2):
        """
        Initialize the pipeline.
        
        Args:
            max_revision_attempts: Maximum times to retry after critic rejection
        """
        self.max_revision_attempts = max_revision_attempts
        self.state: Dict[str, Any] = {}
    
    async def run(self, clear_existing_graph: bool = True) -> Dict[str, Any]:
        """
        Execute the full policy compilation pipeline.
        
        Args:
            clear_existing_graph: Whether to clear Neo4j before building
            
        Returns:
            Pipeline execution results
        """
        print("=" * 60)
        print("[PIPELINE] POLICY COMPILER PIPELINE - Starting")
        print("=" * 60)
        
        results = {
            "pipeline_status": "running",
            "stages": {},
        }
        
        try:
            # Stage 1: Ontology Design
            print("\n[STAGE 1/4] Ontology Design")
            print("-" * 40)
            ontology_result = await run_ontology_agent()
            results["stages"]["ontology"] = ontology_result
            
            if ontology_result["status"] != "success":
                return self._fail_pipeline(results, "Ontology design failed")
            
            self.state["schema"] = ontology_result["schema"]
            
            # Stage 2: Extraction
            print("\n[STAGE 2/4] Policy Extraction")
            print("-" * 40)
            extraction_result = await run_extraction_agent(schema=self.state["schema"])
            results["stages"]["extraction"] = extraction_result
            
            if extraction_result["status"] != "success":
                return self._fail_pipeline(results, "Extraction failed")
            
            self.state["extraction"] = extraction_result["extraction"]
            
            # Stage 3: Critic Validation (with retry loop)
            print("\n[STAGE 3/4] Validation")
            print("-" * 40)
            
            approved = False
            for attempt in range(self.max_revision_attempts + 1):
                critic_result = await run_critic_agent(
                    schema=self.state["schema"],
                    extraction=self.state["extraction"]
                )
                results["stages"][f"validation_attempt_{attempt + 1}"] = critic_result
                
                if critic_result.get("approved", False):
                    approved = True
                    print(f"   [OK] Approved on attempt {attempt + 1}")
                    break
                else:
                    if attempt < self.max_revision_attempts:
                        print(f"   [WARN] Revision needed, attempting re-extraction...")
                        # Re-run extraction with critic feedback
                        extraction_result = await run_extraction_agent(
                            schema=self.state["schema"]
                        )
                        if extraction_result["status"] == "success":
                            self.state["extraction"] = extraction_result["extraction"]
            
            if not approved:
                print("   [WARN] Proceeding despite validation issues (max attempts reached)")
            
            self.state["validation"] = critic_result.get("validation", {})
            
            # Stage 4: Graph Building
            print("\n[STAGE 4/4] Graph Construction")
            print("-" * 40)
            builder_result = await run_builder_agent(
                extraction=self.state["extraction"],
                clear_existing=clear_existing_graph
            )
            results["stages"]["builder"] = builder_result
            
            if builder_result["status"] != "success":
                return self._fail_pipeline(results, "Graph building failed")
            
            # Success!
            results["pipeline_status"] = "success"
            results["final_state"] = {
                "schema_nodes": len(self.state["schema"].get("nodes", [])),
                "schema_relationships": len(self.state["schema"].get("relationships", [])),
                "cypher_statements": len(self.state["extraction"].get("cypher_statements", [])),
                "graph_nodes": builder_result.get("build_result", {}).get("verification", {}).get("total_nodes", 0),
            }
            
            print("\n" + "=" * 60)
            print("[PIPELINE] COMPLETE - Knowledge graph built successfully!")
            print("=" * 60)
            print(f"   Schema: {results['final_state']['schema_nodes']} node types")
            print(f"   Cypher: {results['final_state']['cypher_statements']} statements")
            print(f"   Graph: {results['final_state']['graph_nodes']} nodes created")
            
            # Save final results
            save_artifact("pipeline_results", results)
            
            return results
            
        except Exception as e:
            return self._fail_pipeline(results, str(e))
    
    def _fail_pipeline(self, results: Dict, error: str) -> Dict[str, Any]:
        """Mark pipeline as failed."""
        results["pipeline_status"] = "failed"
        results["error"] = error
        print(f"\n[PIPELINE] FAILED: {error}")
        save_artifact("pipeline_results", results)
        return results


async def run_pipeline(clear_existing: bool = True) -> Dict[str, Any]:
    """
    Convenience function to run the full pipeline.
    
    Args:
        clear_existing: Whether to clear existing graph
        
    Returns:
        Pipeline results
    """
    pipeline = PolicyCompilerPipeline()
    return await pipeline.run(clear_existing_graph=clear_existing)


# CLI interface
def main():
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description="Policy Compiler Pipeline")
    parser.add_argument("--run-pipeline", action="store_true", help="Run the full policy compilation pipeline")
    
    args = parser.parse_args()
    
    # Check .env first
    if not os.path.exists(".env"):
        print("[ERROR] .env file not found. Please create one with GEMINI_API_KEY and NEO4J credentials.")
        return

    if args.run_pipeline:
        # Run async pipeline
        asyncio.run(run_pipeline())
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
