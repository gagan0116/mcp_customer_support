import asyncio
import os
from paperbanana import PaperBananaPipeline, GenerationInput, DiagramType
from paperbanana.core.config import Settings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def generate_illustration():
    # Configure settings for PREMIUM quality
    settings = Settings(
        vlm_provider="gemini",
        vlm_model="gemini-2.0-flash", 
        image_provider="google_imagen",
        image_model="gemini-3-pro-image-preview", 
        refinement_iterations=5, # Max iterations for design polish
        verbose=True
    )

    pipeline = PaperBananaPipeline(settings=settings)

    # Detailed Narrative Summary (2+ Pages equivalent)
    source_context = """
    # Comprehensive System Architecture: The Autonomous Customer Support Pipeline

    ## Introduction
    This document details the architecture of a next-generation "Autonomous Customer Support Agent" designed to handle complex e-commerce return requests without human intervention. Unlike simple chatbots, this system is a sophisticated Multi-Agent orchestration that can "read" documents, "see" product defects, "verify" truth against a database, and "adjudicate" claims based on dynamic policy rules. The system mimics the workflow of a senior support agent but operates at machine speed and scale.

    ## Phase 1: Ingestion and Event Triggering
    The lifecycle of a support ticket begins in the wild—specifically, in a customer's email inbox. The `Gmail Event Processor` acts as the system's sensory organ, constantly monitoring for new messages. It doesn't just forward everything; it applies intelligent filtering at the edge. 
    
    When an email arrives, the processor analyzes the metadata and content. It looks for specific intent markers indicating a "RETURN" or "REFUND" request. For example, a subject line like "Item damaged, need return" triggers the workflow. Crucially, it identifies and extracts key attachments: the **Proof of Purchase** (usually a PDF invoice) and **Proof of Defect** (a photo of the damaged item). These files are lifted from the email and securely stored in Google Cloud Storage (GCS), while the email body and metadata are packaged into a structured event object. This event is then pushed to the central nervous system: the `MCP Processor`.

    ## Phase 2: The Multi-Modal Perception Grid
    Upon receiving the event, the `MCP Processor` initiates parallel processing streams to "understand" the unstructured data. This is where the system uses specialized tools—exposed via the Model Context Protocol (MCP)—to convert raw files into machine-readable intelligence.

    ### The Document Server (The Reader)
    The system spins up the `Doc Server Agent` to handle the PDF invoice. Using the `process_invoice` tool (powered by `pypdf`), this agent opens the invoice, parses the layout, and extracts the raw text. It doesn't just grab text; it identifies key fields like the Order Number, Date of Purchase, and Line Items. This turns a static PDF into a searchable text block.

    ### The Defect Analyzer (The Eye)
    Simultaneously, the `Defect Analyzer Agent` wakes up to examine the user-submitted photo. Using **Gemini 3 Vision**, this agent looks at the image not as pixels, but as a semantic scene. It uses the `analyze_defect_image` tool to answer specific questions: "Is the item damaged?", "What is the nature of the damage?", and "Does this look like user error or shipping damage?". It condenses this visual analysis into a precise description, such as "Screen cracked in top-left corner, impact point visible."

    ## Phase 3: Structural Extraction
    With the email body, invoice text, and visual defect description now available, the **Extraction Agent** takes over. Its job is normalization. It synthesizes these three disparate data sources into a single, coherent JSON structure. It creates a preliminary "Order Object" containing the Customer's Email, the claimed Order ID, the specific Item being returned, and the Reason for Return. 
    
    However, this data is "Unverified"—it relies on what the customer *said*, not what is *known*.

    ## Phase 4: The Agentic Verification Loop (The Detective)
    This is the most complex component of the pipeline. The **DB Verification Agent** is responsible for establishing ground truth. It connects to the `Postgres Database` and attempts to match the claim to a real transaction. This is not a simple lookup; it is an intelligent, hierarchical search strategy implemented as a loop.

    **Step 1: Identity Verification**
    First, the agent calls `verify_from_email_matches_customer` to ensure the email address belongs to a real customer in the database. If the user doesn't exist, the process halts immediately.

    **Step 2: Hierarchical Order Search**
    The agent then tries to find the specific order. It uses a "fall-through" logic, trying the most precise methods first and getting fuzzier if they fail:
    *   **Attempt 1 (The Sniper)**: It tries `find_order_by_order_invoice_id` using the exact ID extracted from the PDF. If this works, it locks the target.
    *   **Attempt 2 (The Backup)**: If the ID is messy, it calls `find_order_by_invoice_number`, searching for the invoice string specifically.
    *   **Attempt 3 (The Dragnet)**: If exact matches fail, it calls `get_customer_orders_with_items`. This pulls *all* recent orders for that customer and the agent manually filters the list to find the item that matches the description. 
    *   **Attempt 4 (The Specialist)**: If all strictly programmed tools fail, the agent unlocks its most powerful capability: `llm_find_orders`. It dynamically writes a raw SQL query based on the natural language context of the request to dig through the database in creative ways. 
    
    Only when the order has been definitively located and the details (Item, Price, Date) confirmed against the "Source of Truth" does the agent output a **Verified Order Object**.

    ## Phase 5: The Policy Adjudicator (The Judge)
    With a verified order, the system moves to decision-making. The `Adjudicator Agent` is the brain of the operation. It decides *if* the return should be approved. This isn't a simple "Yes/No" script; it's a 6-step cognitive process.

    1.  **Context Building**: The agent calculates derived metrics, such as "Days Since Delivery" (comparing the verified delivery date to the email timestamp) and looks up the Customer's Loyalty Tier (VIP, Standard).
    2.  **Taxonomy Classification**: It uses an LLM to map the returned item to one of 76 specific product categories (e.g., "Consumer Electronics > Laptops > Gaming"). This is crucial because different categories have different rules.
    3.  **Graph Traversal**: The system consults a **Neo4j Knowledge Graph**. It starts at the node for the identified Category and traverses the edges to find all applicable `Policy Rules`. It "collects" rules about Return Windows, Restocking Fees, and Damage Waivers.
    4.  **Source Retrieval**: To ensure hallucination-free decisions, the agent fetches the *exact text citations* from the original policy documents that back up the found rules.
    5.  **Reasoning (The Thinking Mode)**: The agent enters a "Thinking Mode." It weighs the evidence: "The user is a VIP, the item is damaged (verified by vision), but the request is 2 days outside the window." It uses the retrieved policy logic to make a nuanced decision.
    6.  **The Verdict**: It outputs a final status: `APPROVED`, `DENIED`, or `MANUAL_REVIEW`.
    7.  **Explanation**: Finally, it drafts a empathetic, policy-backed email response to the customer explaining the decision.

    ## Phase 6: Resolution and Feedback
    The final decision is written to the `Refund Requests Database` for accounting. The drafted response is sent back to the customer. If the decision was "Manual Review," the entire package of evidence (PDF, Image Analysis, Verification Log, Adjudication Reasoning) is flagged for a human agent, saving them 15 minutes of investigation time.
    """

    caption = "A premium, detailed architectural diagram of the End-to-End Support Pipeline. It must show the Gmail Ingestion, the specific MCP Tools (Doc Server, Defect Analyzer), the complex DB Verification Agent loop, and the 6-step Adjudicator logic."

    print("Generating Premium End-to-End Illustration...")
    print(f"Communicative Intent: {caption}")
    
    try:
        result = await pipeline.generate(
            GenerationInput(
                source_context=source_context,
                communicative_intent=caption,
                diagram_type=DiagramType.METHODOLOGY,
            )
        )

        print(f"Illustration generated successfully!")
        print(f"Output saved to: {result.image_path}")
        print(f"Run ID: {result.metadata.get('run_id')}")
    except Exception as e:
        print(f"Error generating illustration: {e}")

if __name__ == "__main__":
    asyncio.run(generate_illustration())
