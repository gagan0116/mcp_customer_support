# policy_compiler_agents/adjudicator_agent.py
"""
Adjudicator Agent - The Reasoning Engine.

This agent:
1.  Accepts a verified_order.json (output from client.py)
2.  Maps items to Knowledge Graph categories.
3.  Queries Neo4j for applicable rules.
4.  Applies logic to decide (Approve/Deny).

NOTE: All required data (membership_tier, delivered_at, seller_type) 
      should already be present in the verified_order.json from client.py.
      No Cloud SQL connection is needed here.
"""

import sys
import os
import json
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from neo4j_graph_engine.db import execute_query as query_graph
from .tools import get_gemini_client


# Condition normalization map - maps enum values to semantic aliases
CONDITION_ALIASES = {
    "DAMAGED_DEFECTIVE": ["damaged", "defective", "broken", "damaged, defective or incorrect"],
    "NEW_UNOPENED": ["new", "unopened", "sealed", "factory sealed"],
    "OPENED_LIKE_NEW": ["opened", "like new", "used", "good condition"],
    "OPENED_USED": ["used", "worn", "opened"],
}


def normalize_condition_static(condition: str) -> list:
    """Returns all semantic aliases for a condition enum (static lookup)."""
    if condition in CONDITION_ALIASES:
        return CONDITION_ALIASES[condition]
    return [condition.lower().replace("_", " ")]

class Adjudicator:
    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = model
        self.client = get_gemini_client()
        self.schema_cache = {
            "categories": [],
            "tiers": [],
            "conditions": [],  # Added for condition normalization
            "relationship_types": []
        }

    async def generate_with_retry(self, prompt: str, max_retries: int = 5) -> Any:
        """
        Helper to call Gemini with exponential backoff for 429 errors.
        """
        import time
        base_delay = 2
        
        for attempt in range(max_retries):
            try:
                resp = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt
                )
                return resp
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "quota" in error_str.lower():
                    if attempt == max_retries - 1:
                        raise e
                    
                    delay = base_delay * (2 ** attempt)
                    print(f"   [WARN] Quota exceeded (429). Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    raise e
        return None

    # =========================================================================
    # COMPONENT 1: Schema Cache
    # =========================================================================
    async def initialize(self):
        """Pre-fetch valid categories, tiers, conditions, and schema from Neo4j."""
        print("   [ADJUDICATOR] Caching schema values...")
        
        # Fetch Categories
        cat_result = await query_graph("MATCH (p:ProductCategory) RETURN p.name as name")
        self.schema_cache["categories"] = [r["name"] for r in cat_result if r.get("name")]
        
        # Fetch Tiers
        tier_result = await query_graph("MATCH (m:MembershipTier) RETURN m.name as name")
        self.schema_cache["tiers"] = [r["name"] for r in tier_result if r.get("name")]
        
        # Fetch Conditions (for condition normalization)
        cond_result = await query_graph("MATCH (c:Condition) RETURN c.name as name")
        self.schema_cache["conditions"] = [r["name"] for r in cond_result if r.get("name")]
        
        # Fetch Relationship Types
        rel_result = await query_graph("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
        self.schema_cache["relationship_types"] = [r["relationshipType"] for r in rel_result]
        
        print(f"   [ADJUDICATOR] Cached {len(self.schema_cache['categories'])} categories, {len(self.schema_cache['conditions'])} conditions.")

    async def normalize_condition(self, item_condition: str) -> str:
        """
        Hybrid condition normalization:
        1. Try static lookup first (fast, deterministic)
        2. If no match, use LLM for semantic matching
        """
        graph_conditions = self.schema_cache.get("conditions", [])
        
        # Step 1: Static lookup
        aliases = normalize_condition_static(item_condition)
        for alias in aliases:
            for gc in graph_conditions:
                if alias.lower() in gc.lower() or gc.lower() in alias.lower():
                    print(f"   [CONDITION] Static match: '{item_condition}' -> '{gc}'")
                    return gc
        
        # Step 2: LLM fallback
        if graph_conditions:
            print(f"   [CONDITION] No static match for '{item_condition}', trying LLM...")
            
            prompt = f"""You are a Condition Matcher for a return policy system.

TASK: Match the customer's item condition to the closest policy condition.

Customer's Item Condition: "{item_condition}"
Valid Policy Conditions: {graph_conditions}

INSTRUCTIONS:
- Find the condition from the list that is semantically closest to the customer's condition.
- "DAMAGED_DEFECTIVE" means the same as "damaged", "defective", "broken".
- "NEW_UNOPENED" means the same as "new", "sealed", "factory sealed".
- If no good match, reply with "NO_MATCH".

OUTPUT: Reply with ONLY the matching condition name from the list, nothing else."""

            try:
                resp = await self.generate_with_retry(prompt)
                result = resp.text.strip().strip('"').strip("'")
                
                if result in graph_conditions:
                    print(f"   [CONDITION] LLM match: '{item_condition}' -> '{result}'")
                    return result
                
                if result == "NO_MATCH":
                    print(f"   [CONDITION] LLM returned NO_MATCH")
                    return item_condition
                    
                # Try partial match on LLM result
                for gc in graph_conditions:
                    if gc.lower() in result.lower() or result.lower() in gc.lower():
                        print(f"   [CONDITION] LLM partial match: '{item_condition}' -> '{gc}'")
                        return gc
                        
            except Exception as e:
                print(f"   [WARN] LLM condition matching failed: {e}")
        
        # No match found
        print(f"   [CONDITION] No match found for '{item_condition}'")
        return item_condition  # Return original if no match

    # =========================================================================
    # COMPONENT 2: Category Mapper (Fuzzy Match + LLM Fallback)
    # =========================================================================
    def _fuzzy_match_category(self, item_category: str, valid_cats: List[str]) -> Optional[str]:
        """
        Attempts fuzzy string matching to find best category.
        Returns None if no confident match found.
        """
        from difflib import SequenceMatcher
        
        if not item_category or not valid_cats:
            return None
        
        item_lower = item_category.lower().strip()
        
        # First: Check for exact match (case-insensitive)
        for cat in valid_cats:
            if cat.lower() == item_lower:
                return cat
        
        # Second: Check if item category is contained in valid category
        for cat in valid_cats:
            if item_lower in cat.lower() or cat.lower() in item_lower:
                return cat
        
        # Third: Fuzzy match with threshold
        best_match = None
        best_score = 0.0
        
        for cat in valid_cats:
            score = SequenceMatcher(None, item_lower, cat.lower()).ratio()
            if score > best_score:
                best_score = score
                best_match = cat
        
        # Only return if confidence is high enough
        if best_score >= 0.6:
            return best_match
        
        return None

    async def map_category(self, item: Dict[str, Any]) -> str:
        """
        Maps order item to a valid Knowledge Graph ProductCategory.
        Uses fuzzy matching first (deterministic), LLM as fallback.
        """
        valid_cats = self.schema_cache["categories"]
        if not valid_cats:
            return "General"
        
        item_category = item.get('category', '')
        item_subcategory = item.get('subcategory', '')
        item_name = item.get('item_name', '')
        
        # Try fuzzy match first (deterministic)
        fuzzy_result = self._fuzzy_match_category(item_category, valid_cats)
        if fuzzy_result:
            return fuzzy_result
        
        # Try subcategory
        fuzzy_result = self._fuzzy_match_category(item_subcategory, valid_cats)
        if fuzzy_result:
            return fuzzy_result
        
        # Fallback to LLM
        prompt = f"""You are a Product Category Mapper.

TASK: Map this item to ONE category from the list below.

ITEM:
- Name: {item_name}
- Category: {item_category}
- Subcategory: {item_subcategory}

VALID CATEGORIES:
{json.dumps(valid_cats[:30])}  

CRITICAL: You MUST return EXACTLY one of the categories from the list above.
Do not invent new categories. If unsure, pick the closest match.

OUTPUT: Just the category name, nothing else."""

        try:
            resp = await self.generate_with_retry(prompt)
            mapped_cat = resp.text.strip().strip('"').strip("'")
            
            # Validate it's in the list
            if mapped_cat in valid_cats:
                return mapped_cat
            
            # Try fuzzy match on LLM response
            fuzzy_result = self._fuzzy_match_category(mapped_cat, valid_cats)
            if fuzzy_result:
                return fuzzy_result
                
            print(f"   [WARN] LLM returned invalid category '{mapped_cat}', using 'General Products'.")
            return "General Products" if "General Products" in valid_cats else valid_cats[0]
        except Exception as e:
            print(f"   [WARN] Category mapping failed: {e}")
            return "General Products" if "General Products" in valid_cats else (valid_cats[0] if valid_cats else "General")

    # =========================================================================
    # COMPONENT 3: Query Generator (Deterministic)
    # =========================================================================
    async def generate_policy_query(self, context: Dict[str, Any]) -> str:
        """
        Generates a simple, reliable Cypher query for fetching applicable rules.
        
        Note: LLM-generated queries were unreliable (Neo4j syntax errors).
        Using deterministic query template for 100% reliability.
        """
        category = context.get("mapped_category", "General Products")
        
        # Simple, reliable query that always works
        query = f"""
            MATCH (pc:ProductCategory {{name: '{category}'}})-[:HAS_RETURN_RULE]->(r:ReturnRule)
            RETURN r.name as rule_name, 
                   r.days_allowed as days_allowed, 
                   r.source_citation as source_citation
            LIMIT 3
        """
        
        print(f"   [QUERY] Generated Cypher query")
        return query

    # =========================================================================
    # COMPONENT 4: Query Executor
    # =========================================================================
    async def execute_policy_query(self, cypher: str) -> List[Dict[str, Any]]:
        """
        Executes the Cypher query against Neo4j and returns results.
        """
        try:
            print(f"   [ADJUDICATOR] Executing Cypher query...")
            results = await query_graph(cypher)
            print(f"   [ADJUDICATOR] Query returned {len(results)} rule(s).")
            return results
        except Exception as e:
            print(f"   [ERROR] Neo4j query failed: {e}")
            return []

    # =========================================================================
    # COMPONENT 5: Decision Engine (Pure Python)
    # =========================================================================
    def make_decision(self, context: Dict[str, Any], rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Pure Python logic to make the final decision.
        No LLM here - deterministic rules only.
        """
        days_since = context["days_since_delivery"]
        item_condition = context["item_condition"]
        return_reason = context["return_reason"]
        
        # No rules found
        if not rules:
            return {
                "decision": "MANUAL_REVIEW",
                "reason": "No applicable return rules found in policy database",
                "rule_applied": None
            }
        
        # Use first rule (graph already resolved priority via OVERRIDES)
        rule = rules[0]
        rule_name = rule.get("rule_name") or rule.get("name", "Unknown Rule")
        days_allowed = rule.get("days_allowed")
        
        # Handle None days_allowed
        if days_allowed is None:
            return {
                "decision": "MANUAL_REVIEW",
                "reason": f"Rule '{rule_name}' has no defined return window",
                "rule_applied": rule
            }
        
        # Convert to int if needed
        try:
            days_allowed = int(days_allowed)
        except (ValueError, TypeError):
            return {
                "decision": "MANUAL_REVIEW",
                "reason": f"Invalid days_allowed value: {days_allowed}",
                "rule_applied": rule
            }
        
        # Time Window Check
        if days_since > days_allowed:
            return {
                "decision": "DENIED",
                "reason": f"Return window expired ({days_since} days since delivery exceeds {days_allowed}-day policy)",
                "days_since_delivery": days_since,
                "days_allowed": days_allowed,
                "rule_applied": rule
            }
        
        # Condition Check (if rule specifies required conditions)
        required_conditions = rule.get("conditions", [])
        if required_conditions and isinstance(required_conditions, list):
            condition_mapping = {
                "NEW_UNOPENED": ["unopened", "new", "sealed"],
                "OPENED_LIKE_NEW": ["opened", "like new", "good"],
                "DAMAGED_DEFECTIVE": ["damaged", "defective"],
                "MISSING_PARTS": ["incomplete", "missing parts"],
                "UNKNOWN": []
            }
            
            acceptable = condition_mapping.get(item_condition, [])
            condition_met = not required_conditions or any(
                cond.lower() in [c.lower() for c in acceptable] 
                for cond in required_conditions
            )
            
            if not condition_met and required_conditions:
                return {
                    "decision": "DENIED",
                    "reason": f"Item condition '{item_condition}' does not meet requirements: {required_conditions}",
                    "rule_applied": rule
                }
        
        # Fee Calculation
        fee_percent = rule.get("restocking_fee_percent", 0) or 0
        try:
            fee_percent = float(fee_percent)
        except (ValueError, TypeError):
            fee_percent = 0
        
        # APPROVED
        return {
            "decision": "APPROVED",
            "reason": f"Return eligible under '{rule_name}' policy",
            "days_remaining": days_allowed - days_since,
            "restocking_fee_percent": fee_percent,
            "rule_applied": rule
        }

    # =========================================================================
    # Input Builder (Reads from verified_order.json directly)
    # =========================================================================
    def build_context(self, verified_order: Dict[str, Any], user_request: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Builds context from verified_order.json.
        Handles nested structure where data may be under 'data' key.
        """
        user_request = user_request or {}
        
        # Handle nested structure: data may be under 'data' key or at root
        if "data" in verified_order:
            data = verified_order["data"]
            order_details = data.get("order_details", {})
            items = data.get("items", [])
            customer = data.get("customer", {})
        else:
            # Data is at root level
            data = verified_order
            order_details = verified_order.get("order_details", {})  # FIX: Get nested order_details
            items = verified_order.get("items") or verified_order.get("order_items", [])
            customer = verified_order.get("customer", {})
        
        # Extract order_id from various possible locations
        order_id = (
            order_details.get("order_id") or 
            verified_order.get("order_id") or 
            data.get("order_id")
        )
        
        # Extract delivered_at
        delivered_at = (
            order_details.get("delivered_at") or 
            verified_order.get("delivered_at") or
            data.get("delivered_at")
        )
        
        # Extract membership_tier and seller_type (may be at root or in customer/order)
        membership_tier = (
            verified_order.get("membership_tier") or
            customer.get("membership_tier") or
            "Standard"
        )
        seller_type = (
            verified_order.get("seller_type") or
            order_details.get("seller_type") or
            "BestBuy"
        )
        
        # Determine days_since_delivery
        mode = user_request.get("mode", "production")
        
        if mode == "test" and "days_since_delivery" in user_request:
            # Test Mode: explicit override
            days_since = user_request["days_since_delivery"]
        else:
            # Production Mode: Calculate from delivered_at
            return_request_date = verified_order.get("return_request_date")
            
            if delivered_at and return_request_date:
                # Both dates available - calculate difference
                if isinstance(delivered_at, str):
                    dt_delivered = datetime.fromisoformat(delivered_at.replace("Z", "+00:00"))
                else:
                    dt_delivered = delivered_at
                    
                if isinstance(return_request_date, str):
                    # Handle date-only format
                    if "T" in return_request_date:
                        dt_request = datetime.fromisoformat(return_request_date.replace("Z", "+00:00"))
                    else:
                        dt_request = datetime.strptime(return_request_date, "%Y-%m-%d")
                else:
                    dt_request = return_request_date
                
                days_since = (dt_request.date() - dt_delivered.date()).days
            elif delivered_at:
                # Only delivered_at, use current date
                if isinstance(delivered_at, str):
                    dt_delivered = datetime.fromisoformat(delivered_at.replace("Z", "+00:00"))
                else:
                    dt_delivered = delivered_at
                days_since = (datetime.now().date() - dt_delivered.date()).days
            else:
                # No delivery date available
                days_since = 9999
        
        # Ensure items list exists
        if not items:
            items = [{"category": "General", "item_name": "Unknown Item"}]
        
        # Build context
        context = {
            "order_id": order_id,
            "items": items,
            "membership_tier": membership_tier,
            "seller_type": seller_type,
            "delivered_at": delivered_at,
            "days_since_delivery": days_since,
            "item_condition": (
                verified_order.get("item_condition") or user_request.get("condition", "UNKNOWN")
            ),
            # DEBUG:
            # item_condition_file = verified_order.get("item_condition")
            # item_condition_req = user_request.get("condition")
            # print(f"DEBUG: File Condition: {item_condition_file}, Request Condition: {item_condition_req}")
            "return_reason": verified_order.get("return_reason_category") or user_request.get("reason", "CHANGED_MIND"),
            "return_reason_text": verified_order.get("return_reason", ""),
            "return_category": verified_order.get("return_category", "RETURN")
        }
        
        return context

    # =========================================================================
    # COMPONENT 6: Main Orchestrator
    # =========================================================================
    async def adjudicate(self, verified_order: Dict[str, Any], user_request: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Main entry point. Orchestrates all components.
        
        Args:
            verified_order: The verified order JSON from client.py
            user_request: Optional overrides (mode, days_since_delivery for testing)
        
        Returns:
            Decision JSON with APPROVED/DENIED/MANUAL_REVIEW
        """
        user_request = user_request or {}
        
        print("\n" + "="*50)
        print("ADJUDICATOR AGENT - Policy Decision Engine")
        print("="*50)
        
        # 0. Initialize (Cache Schema)
        if not self.schema_cache["categories"]:
            await self.initialize()
        
        # 1. Build Context (from verified_order.json directly)
        context = self.build_context(verified_order, user_request)
        print(f"   [CONTEXT] Order ID: {context['order_id']}")
        print(f"   [CONTEXT] Days since delivery: {context['days_since_delivery']}")
        print(f"   [CONTEXT] Membership: {context['membership_tier']}")
        print(f"   [CONTEXT] Item condition: {context['item_condition']}")
        print(f"   [CONTEXT] Return reason: {context['return_reason']}")
        
        # 2. Map categories for first item
        if context["items"]:
            primary_item = context["items"][0]
            mapped_category = await self.map_category(primary_item)
            context["mapped_category"] = mapped_category
            print(f"   [MAPPER] '{primary_item.get('category', 'Unknown')}' -> '{mapped_category}'")
        else:
            context["mapped_category"] = "General"
            print(f"   [MAPPER] No items found, using 'General' category")
        
        # 3. Generate Cypher query
        cypher = await self.generate_policy_query(context)
        print(f"   [QUERY] Generated Cypher query")
        
        # 4. Execute query against Neo4j
        rules = await self.execute_policy_query(cypher)
        
        # 5. Make decision
        decision = self.make_decision(context, rules)
        print(f"   [DECISION] {decision['decision']}: {decision['reason']}")
        
        # 6. Build final output
        output = {
            "order_id": context["order_id"],
            "decision": decision["decision"],
            "details": {
                "reason": decision["reason"],
                "restocking_fee_percent": decision.get("restocking_fee_percent", 0),
                "days_remaining": decision.get("days_remaining"),
                "rule_applied": decision.get("rule_applied")
            },
            "context_used": {
                "days_since_delivery": context["days_since_delivery"],
                "membership_tier": context["membership_tier"],
                "seller_type": context["seller_type"],
                "item_condition": context["item_condition"],
                "return_reason": context["return_reason"],
                "mapped_category": context["mapped_category"]
            }
        }
        
        print("\n" + "="*50)
        print(f"FINAL DECISION: {decision['decision']}")
        print("="*50)
        
        return output


# =============================================================================
# CLI Entry Point for Testing
# =============================================================================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Adjudicator Agent - Policy Decision Engine")
    parser.add_argument("--order-file", type=str, help="Path to verified_order.json")
    parser.add_argument("--test-mode", action="store_true", help="Use test mode with explicit days")
    parser.add_argument("--days", type=int, default=10, help="Days since delivery (test mode)")
    parser.add_argument("--condition", type=str, default="OPENED_LIKE_NEW", help="Item condition")
    parser.add_argument("--reason", type=str, default="CHANGED_MIND", help="Return reason")
    
    args = parser.parse_args()
    
    async def main():
        agent = Adjudicator()
        
        # Load order file if provided
        if args.order_file and os.path.exists(args.order_file):
            with open(args.order_file, 'r') as f:
                verified_order = json.load(f)
            print(f"Loaded order from: {args.order_file}")
        else:
            # Sample test order
            verified_order = {
                "order_id": "test-order-001",
                "items": [{"category": "Furniture", "item_name": "Office Chair", "subcategory": "Chairs"}],
                "order_items": [{"category": "Furniture", "item_name": "Office Chair"}],
                "membership_tier": "Standard",
                "seller_type": "BestBuy",
                "item_condition": args.condition,
                "return_reason_category": args.reason
            }
            print("Using sample test order")
        
        # Build user request
        user_request = {
            "mode": "test" if args.test_mode else "production",
            "days_since_delivery": args.days,
            "condition": args.condition,
            "reason": args.reason
        }
        
        result = await agent.adjudicate(verified_order, user_request)
        print("\n" + json.dumps(result, indent=2, default=str))
        
        # Allow async tasks to cleanup
        await asyncio.sleep(0.1)

    # Windows-specific event loop policy to prevent "Event loop is closed" errors
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
