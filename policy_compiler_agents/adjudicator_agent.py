# policy_compiler_agents/adjudicator_agent.py
"""
Adjudicator Agent - Redesigned for Reliability and Accuracy.

Architecture:
1. Category Classification: Pure LLM with 76 categories
2. Graph Traversal: Structured 3-hop traversal (no hardcoded queries)
3. Source Retrieval: Fetch policy text from combined_policy.md
4. Decision Making: LLM with full context (graph + source text)

Gemini 3 Features Used:
- ThinkingConfig (high level) - Deep reasoning for decisions
- response_schema - Structured output enforcement
- system_instruction - Persona for decision-making
"""

import sys
import os
import json
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from google.genai import types
from google.genai.types import ThinkingConfig, Schema

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from neo4j_graph_engine.db import execute_query as query_graph
from .tools import get_gemini_client
from .graph_traversal import traverse_from_category, build_policy_profile, get_all_categories
from .source_retrieval import get_source_text, format_source_texts_for_prompt


# =============================================================================
# CONDITION NORMALIZATION
# =============================================================================
# Maps user condition enums to graph condition names for deterministic matching

CONDITION_TO_GRAPH = {
    # Damaged/defective items - full fee waiver typically applies
    "DAMAGED_DEFECTIVE": "Damaged, defective, or incorrect",
    "DAMAGED": "Damaged, defective, or incorrect",
    "DEFECTIVE": "Damaged, defective, or incorrect",
    
    # Unopened items - restocking fee typically waived
    "NEW_UNOPENED": "Unopened",
    "UNOPENED": "Unopened",
    "SEALED": "Unopened",
    
    # Opened but like new - no special waiver
    "OPENED_LIKE_NEW": None,  # Explicitly no match
    "LIKE_NEW": None,
    "OPENED": None,
    "USED": None,
}

def normalize_condition(user_condition: str) -> tuple:
    """
    Normalize user condition to graph condition name.
    
    Returns:
        tuple: (normalized_name, is_exact_match)
        - normalized_name: Graph condition name or original if no match
        - is_exact_match: True if we found an explicit mapping
    """
    if not user_condition:
        return (None, False)
    
    # Try exact match first
    upper = user_condition.upper().replace(" ", "_")
    if upper in CONDITION_TO_GRAPH:
        graph_condition = CONDITION_TO_GRAPH[upper]
        return (graph_condition, True)
    
    # No mapping found - return original
    return (user_condition, False)


# =============================================================================
# SCHEMA DEFINITIONS
# =============================================================================

CATEGORY_MATCH_SCHEMA = Schema(
    type="object",
    properties={
        "matched_category": Schema(type="string", description="The matched category from the list"),
        "confidence": Schema(type="number", description="Confidence 0.0-1.0"),
    },
    required=["matched_category", "confidence"]
)

DECISION_SCHEMA = Schema(
    type="object",
    properties={
        "decision": Schema(
            type="string", 
            enum=["APPROVED", "DENIED", "MANUAL_REVIEW"],
            description="The return decision"
        ),
        "applicable_fees": Schema(
            type="array",
            items=Schema(
                type="object",
                properties={
                    "name": Schema(type="string"),
                    "value": Schema(type="number"),
                    "waived": Schema(type="boolean"),
                    "reason": Schema(type="string")
                }
            ),
            description="List of applicable fees"
        ),
        "reasoning": Schema(type="string", description="Brief reasoning for the decision"),
        "policy_citations": Schema(
            type="array",
            items=Schema(type="string"),
            description="Policy citations supporting the decision"
        )
    },
    required=["decision", "reasoning"]
)


# =============================================================================
# PROMPTS
# =============================================================================

CATEGORY_CLASSIFICATION_PROMPT = """You are a product category classifier for a return policy system.

## Valid Product Categories
{categories}

## Product Information
- Product Name: "{item_name}"
- Order Category: "{order_category}"

## Task
Classify this product into ONE of the valid categories listed above.
- Choose the most specific matching category
- If no good match exists, use "Most products" as the default
- Return ONLY a category from the valid list

Return the exact category name from the list."""

DECISION_SYSTEM_PROMPT = """You are a return policy decision engine for Best Buy.
Your role is to analyze policy rules and customer requests to make fair, accurate decisions.

Decision Guidelines:
- APPROVED: Return is within policy and conditions are met
- DENIED: Return violates policy (e.g., past return window, final sale item)
- MANUAL_REVIEW: Edge cases requiring human judgment

Always cite specific policy rules in your reasoning."""

DECISION_PROMPT = """## POLICY RULES (from Knowledge Graph)

### Category: {category}

### Return Windows
{windows}

### Fees
{fees}

### Restrictions
{restrictions}

### Required Conditions
{required_conditions}

---

## ORIGINAL POLICY TEXT
{source_text}

---

## CUSTOMER REQUEST

- Order ID: {order_id}
- Product: {item_name}
- Category: {category}
- Days Since Delivery: {days_since}
- Item Condition (user reported): {condition}
- Item Condition (for graph matching): {normalized_condition}
- Membership Tier: {membership_tier}
- Customer Region: {region}
- Return Reason: {return_reason}

---

## TASK

Analyze the policy rules and make a decision:

1. Check if the return is within the return window for this membership tier
2. Check for any restrictions that apply based on item condition
3. Determine which fees apply (and if any are waived)
4. Make a final decision: APPROVED, DENIED, or MANUAL_REVIEW

Be thorough but concise in your reasoning."""

EXPLANATION_PROMPT = """Generate a customer-friendly explanation for this return decision.

Decision: {decision}
Fees: {fees}
Reasoning: {reasoning}

Write 2-3 sentences in a helpful, empathetic tone that:
1. Acknowledges the customer's request
2. Explains the key factor in the decision
3. If denied, suggests next steps or alternatives

Do not use technical jargon."""


class AdjudicatorV2:
    """
    Adjudicator Agent v2.0 - Redesigned Architecture
    
    Uses:
    - Pure LLM for category classification (all 76 categories)
    - Structured graph traversal (no hardcoded Cypher)
    - Source text retrieval for full policy context
    - LLM for decision-making with deep reasoning
    """
    
    def __init__(self, model: str = "gemini-3-pro-preview"):
        self.model = os.getenv("ADJUDICATOR_MODEL", model)
        self.client = get_gemini_client()
        self.categories_cache = []
    
    # =========================================================================
    # LLM Helper
    # =========================================================================
    async def generate_with_retry(
        self, 
        prompt: str, 
        system_instruction: str = None,
        response_schema: Schema = None,
        use_thinking: bool = False,
        max_retries: int = 3
    ) -> Any:
        """Generate content with retry logic."""
        
        config_kwargs = {}
        
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        
        if response_schema:
            config_kwargs["response_schema"] = response_schema
            config_kwargs["response_mime_type"] = "application/json"
        
        if use_thinking:
            config_kwargs["thinking_config"] = ThinkingConfig(thinking_level="high")
        
        config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
        
        for attempt in range(max_retries):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                
                if response_schema:
                    return json.loads(response.text)
                return response.text.strip()
                
            except Exception as e:
                print(f"   [WARN] Attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1)
    
    # =========================================================================
    # STEP 1: Category Classification (Pure LLM)
    # =========================================================================
    async def classify_category(self, item: Dict[str, Any]) -> str:
        """
        Classify product into one of 76 ProductCategory values.
        Uses pure LLM with all categories - no fuzzy matching.
        """
        # Fetch categories if not cached
        if not self.categories_cache:
            self.categories_cache = await get_all_categories()
            print(f"   [CLASSIFY] Cached {len(self.categories_cache)} categories")
        
        item_name = item.get("item_name", "Unknown")
        order_category = item.get("category", "Unknown")
        
        prompt = CATEGORY_CLASSIFICATION_PROMPT.format(
            categories=json.dumps(self.categories_cache, indent=2),
            item_name=item_name,
            order_category=order_category
        )
        
        print(f"   [CLASSIFY] Classifying: {item_name} ({order_category})")
        
        try:
            result = await self.generate_with_retry(
                prompt,
                response_schema=CATEGORY_MATCH_SCHEMA
            )
            
            matched = result.get("matched_category", "Most products")
            confidence = result.get("confidence", 0.0)
            
            # Validate that result is in our category list
            if matched in self.categories_cache:
                print(f"   [CLASSIFY] Result: '{matched}' (confidence: {confidence:.2f})")
                return matched
            else:
                print(f"   [CLASSIFY] LLM returned unknown category: {matched}, defaulting")
                return "Most products"
                
        except Exception as e:
            print(f"   [CLASSIFY] Error: {e}, defaulting to 'Most products'")
            return "Most products"
    
    # =========================================================================
    # STEP 2: Build Context from Order
    # =========================================================================
    def build_context(self, verified_order: Dict[str, Any], user_request: Dict[str, Any] = None) -> Dict[str, Any]:
        """Build context from verified_order.json."""
        user_request = user_request or {}
        
        # Handle nested structure
        if "data" in verified_order:
            data = verified_order["data"]
            order_details = data.get("order_details", {})
            items = data.get("items", [])
            customer = data.get("customer", {})
        else:
            data = verified_order
            order_details = verified_order.get("order_details", {})
            items = verified_order.get("items") or verified_order.get("order_items", [])
            customer = verified_order.get("customer", {})
        
        # Extract order_id
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
        
        # Extract membership_tier
        membership_tier = (
            verified_order.get("membership_tier") or
            customer.get("membership_tier") or
            "Standard"
        )
        
        # Extract seller_type
        seller_type = (
            verified_order.get("seller_type") or
            order_details.get("seller_type") or
            "BestBuy"
        )
        
        # Calculate days_since_delivery
        mode = user_request.get("mode", "production")
        
        if mode == "test" and "days_since_delivery" in user_request:
            days_since = user_request["days_since_delivery"]
        else:
            return_request_date = verified_order.get("return_request_date")
            
            if delivered_at and return_request_date:
                dt_delivered = self._parse_date(delivered_at)
                dt_request = self._parse_date(return_request_date)
                days_since = (dt_request.date() - dt_delivered.date()).days
            elif delivered_at:
                dt_delivered = self._parse_date(delivered_at)
                days_since = (datetime.now().date() - dt_delivered.date()).days
            else:
                days_since = 9999
        
        # Ensure items list exists
        if not items:
            items = [{"category": "General", "item_name": "Unknown Item"}]
        
        return {
            "order_id": order_id,
            "items": items,
            "membership_tier": membership_tier,
            "seller_type": seller_type,
            "delivered_at": delivered_at,
            "days_since_delivery": days_since,
            "item_condition": (
                verified_order.get("item_condition") or 
                user_request.get("condition", "UNKNOWN")
            ),
            "return_reason": (
                verified_order.get("return_reason_category") or
                user_request.get("reason", "CHANGED_MIND")
            ),
            "region": verified_order.get("region") or customer.get("region") or "UNKNOWN"
        }
    
    def _parse_date(self, date_val):
        """Parse date from string or datetime."""
        if isinstance(date_val, str):
            if "T" in date_val:
                return datetime.fromisoformat(date_val.replace("Z", "+00:00"))
            else:
                return datetime.strptime(date_val, "%Y-%m-%d")
        return date_val
    
    # =========================================================================
    # STEP 3: Format Policy Profile for Prompt
    # =========================================================================
    def format_profile_for_prompt(self, profile: Dict[str, Any]) -> Dict[str, str]:
        """Format policy profile sections for the decision prompt."""
        
        # Format windows
        windows_text = ""
        if profile["windows"]:
            for w in profile["windows"]:
                tiers = ", ".join(w.get("tiers", [])) or "All tiers"
                windows_text += f"- {w.get('name', 'N/A')}: {w.get('days', 'N/A')} days (for: {tiers})\n"
        else:
            windows_text = "No specific return window found. Standard policy may apply.\n"
        
        # Format fees
        fees_text = ""
        if profile["fees"]:
            for f in profile["fees"]:
                waivers = ", ".join(f.get("waivers", [])) or "None"
                exemptions = ", ".join(f.get("exemptions", [])) or "None"
                fees_text += f"- {f.get('name', 'N/A')}: {f.get('value', 'N/A')} ({f.get('amount_type', 'N/A')})\n"
                fees_text += f"  Waived if: {waivers}\n"
                fees_text += f"  Exempt in regions: {exemptions}\n"
        else:
            fees_text = "No restocking fees for this category.\n"
        
        # Format restrictions
        restrictions_text = ""
        if profile["restrictions"]:
            for r in profile["restrictions"]:
                triggers = ", ".join(r.get("triggers", [])) or "Always applies"
                restrictions_text += f"- {r.get('name', 'N/A')}: Triggered by {triggers}\n"
        else:
            restrictions_text = "No special restrictions.\n"
        
        # Format required conditions
        required_text = ""
        if profile["required_conditions"]:
            for c in profile["required_conditions"]:
                required_text += f"- {c.get('name', 'N/A')}\n"
        else:
            required_text = "No special conditions required.\n"
        
        return {
            "windows": windows_text,
            "fees": fees_text,
            "restrictions": restrictions_text,
            "required_conditions": required_text
        }
    
    # =========================================================================
    # STEP 4: LLM Decision Making
    # =========================================================================
    async def make_llm_decision(
        self, 
        profile: Dict[str, Any], 
        source_texts: Dict[str, str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Use LLM to analyze policy and make decision."""
        
        formatted = self.format_profile_for_prompt(profile)
        source_text_str = format_source_texts_for_prompt(source_texts)
        
        prompt = DECISION_PROMPT.format(
            category=profile["category"],
            windows=formatted["windows"],
            fees=formatted["fees"],
            restrictions=formatted["restrictions"],
            required_conditions=formatted["required_conditions"],
            source_text=source_text_str,
            order_id=context["order_id"],
            item_name=context["items"][0].get("item_name", "Unknown") if context["items"] else "Unknown",
            days_since=context["days_since_delivery"],
            condition=context["item_condition"],
            normalized_condition=context.get("normalized_condition") or context["item_condition"],
            membership_tier=context["membership_tier"],
            region=context["region"],
            return_reason=context["return_reason"]
        )
        
        print("   [DECISION] Calling LLM for policy decision...")
        
        try:
            result = await self.generate_with_retry(
                prompt,
                system_instruction=DECISION_SYSTEM_PROMPT,
                response_schema=DECISION_SCHEMA,
                use_thinking=True
            )
            
            print(f"   [DECISION] LLM decision: {result.get('decision', 'UNKNOWN')}")
            return result
            
        except Exception as e:
            print(f"   [DECISION] Error: {e}")
            return {
                "decision": "MANUAL_REVIEW",
                "reasoning": f"Decision failed: {str(e)}",
                "applicable_fees": [],
                "policy_citations": []
            }
    
    # =========================================================================
    # STEP 5: Generate Customer Explanation
    # =========================================================================
    async def generate_explanation(self, decision_result: Dict[str, Any]) -> str:
        """Generate customer-friendly explanation."""
        
        fees_text = ""
        for fee in decision_result.get("applicable_fees", []):
            if fee.get("waived"):
                fees_text += f"- {fee['name']}: Waived ({fee.get('reason', '')})\n"
            else:
                fees_text += f"- {fee['name']}: ${fee.get('value', 0)}\n"
        
        if not fees_text:
            fees_text = "No fees apply."
        
        prompt = EXPLANATION_PROMPT.format(
            decision=decision_result["decision"],
            fees=fees_text,
            reasoning=decision_result.get("reasoning", "")
        )
        
        try:
            explanation = await self.generate_with_retry(prompt)
            return explanation
        except Exception as e:
            print(f"   [EXPLAIN] Error: {e}")
            return decision_result.get("reasoning", "Please contact customer service for details.")
    
    # =========================================================================
    # MAIN ORCHESTRATOR
    # =========================================================================
    async def adjudicate(self, verified_order: Dict[str, Any], user_request: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Main entry point - orchestrates the adjudication flow.
        
        1. Build context from order
        2. Classify category (LLM)
        3. Traverse graph for policy rules
        4. Fetch source text from citations
        5. Make decision (LLM)
        6. Generate customer explanation
        """
        user_request = user_request or {}
        
        print("\n" + "="*60)
        print("ADJUDICATOR AGENT v2.0 - Policy Decision Engine")
        print("="*60)
        
        # STEP 1: Build context
        context = self.build_context(verified_order, user_request)
        print(f"   [CONTEXT] Order ID: {context['order_id']}")
        print(f"   [CONTEXT] Days since delivery: {context['days_since_delivery']}")
        print(f"   [CONTEXT] Membership: {context['membership_tier']}")
        print(f"   [CONTEXT] Condition: {context['item_condition']}")
        
        # STEP 1.5: Normalize condition for graph matching
        normalized_condition, is_match = normalize_condition(context["item_condition"])
        context["normalized_condition"] = normalized_condition
        context["condition_matched"] = is_match
        if is_match:
            print(f"   [CONDITION] Normalized: '{context['item_condition']}' -> '{normalized_condition}'")
        else:
            print(f"   [CONDITION] No mapping for: '{context['item_condition']}'")
        
        # STEP 2: Classify category (Pure LLM)
        primary_item = context["items"][0] if context["items"] else {"item_name": "Unknown"}
        mapped_category = await self.classify_category(primary_item)
        context["mapped_category"] = mapped_category
        
        # STEP 3: Traverse graph for policy rules
        print(f"   [GRAPH] Traversing from: {mapped_category}")
        traversal_result = await traverse_from_category(mapped_category)
        policy_profile = build_policy_profile(traversal_result)
        
        # STEP 4: Fetch source text
        print(f"   [SOURCE] Fetching {len(policy_profile['citations'])} citations...")
        source_texts = get_source_text(policy_profile["citations"])
        
        # STEP 5: Make decision (LLM)
        decision_result = await self.make_llm_decision(policy_profile, source_texts, context)
        
        # STEP 6: Generate customer explanation
        print("   [EXPLAIN] Generating customer explanation...")
        explanation = await self.generate_explanation(decision_result)
        
        # Build final output
        output = {
            "order_id": context["order_id"],
            "decision": decision_result["decision"],
            "customer_explanation": explanation,
            "details": {
                "reasoning": decision_result.get("reasoning", ""),
                "applicable_fees": decision_result.get("applicable_fees", []),
                "policy_citations": decision_result.get("policy_citations", [])
            },
            "context_used": {
                "days_since_delivery": context["days_since_delivery"],
                "membership_tier": context["membership_tier"],
                "item_condition": context["item_condition"],
                "mapped_category": mapped_category,
                "region": context["region"]
            },
            "policy_profile": policy_profile  # Include for debugging
        }
        
        # =========================================================================
        # PRESENTATION OUTPUT
        # =========================================================================
        print("\n" + "="*60)
        print(f"FINAL DECISION: {decision_result['decision']}")
        print("="*60)
        print(f"\nReasoning:\n{decision_result.get('reasoning', 'N/A')}\n")
        
        
        print(f"\nCustomer Explanation:\n\"{explanation}\"")
        print("="*60)
        
        return output



# =============================================================================
# CLI Entry Point
# =============================================================================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Adjudicator Agent v2.0")
    parser.add_argument("--order-file", type=str, help="Path to verified_order.json")
    parser.add_argument("--test-mode", action="store_true", help="Use test mode")
    parser.add_argument("--days", type=int, default=10, help="Days since delivery")
    parser.add_argument("--condition", type=str, default="OPENED_LIKE_NEW", help="Item condition")
    
    args = parser.parse_args()
    
    async def main():
        agent = AdjudicatorV2()
        
        if args.order_file and os.path.exists(args.order_file):
            with open(args.order_file, 'r') as f:
                verified_order = json.load(f)
        else:
            verified_order = {
                "order_id": "test-order-001",
                "items": [{"category": "Furniture", "item_name": "Office Chair"}],
                "membership_tier": "Standard",
                "seller_type": "BestBuy",
                "item_condition": args.condition
            }
        
        user_request = {
            "mode": "test" if args.test_mode else "production",
            "days_since_delivery": args.days,
            "condition": args.condition
        }
        
        result = await agent.adjudicate(verified_order, user_request)
        print("\n" + json.dumps(result, indent=2, default=str))
    
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())


# =============================================================================
# Backward Compatibility Alias
# =============================================================================
# Allow importing as "Adjudicator" for backward compatibility with client.py
Adjudicator = AdjudicatorV2

