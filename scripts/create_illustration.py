import asyncio
import os
from paperbanana import PaperBananaPipeline, GenerationInput, DiagramType
from paperbanana.core.config import Settings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def generate_illustration():
    # Configure settings for MAXIMUM quality
    settings = Settings(
        vlm_provider="gemini",
        vlm_model="gemini-2.0-flash", # High reasoning capability
        image_provider="google_imagen",
        image_model="gemini-3-pro-image-preview", # Best image generation
        refinement_iterations=5, # Iterate more to refine the design
        verbose=True
    )

    pipeline = PaperBananaPipeline(settings=settings)

    # RICH VISUAL CONTEXT
    # This description guides the 'Planner' and 'Visualizer' to create a complete, professional diagram.
    source_context = """
    The system is a "Multi-Agent Knowledge Graph Construction Pipeline" for Retail Policy Documents.
    
    The diagram must clearly show the Sequential Flow of Data through 5 Specialized Agents, with a Feedback Loop.

    **Visual Flow & Components:**

    1.  **Start Point**: 
        -   **Input**: "Policy PDFs" (Document Icon).
        -   **Action**: Enters the **Ingestion Agent**.

    2.  **Ingestion Agent**:
        -   **Process**: Parsing.
        -   **Output**: "Hierarchy Markdown" (Document Icon).
        -   **Flow**: Markdown is passed to the *Ontology Designer* and *Extraction Agent*.

    3.  **Ontology Designer Agent** (The Brain):
        -   **Action**: Analyzes Markdown using "Gemini Thinking Mode".
        -   **Output**: "Graph Schema" (JSON structure icon).
        -   **Flow**: Schema is sent to *Extraction Agent*.

    4.  **Extraction Agent** (The Worker):
        -   **Inputs**: "Hierarchy Markdown" AND "Graph Schema".
        -   **Process**: 
            -   Phase 1: Triplet Extraction (LLM).
            -   Phase 2: Graph Linker (Code validation).
            -   Phase 3: Cypher Generation.
        -   **Output**: "Extracted Cypher" (Code block icon).
        -   **Flow**: Output sent to *Critic Agent*.

    5.  **Critic Agent** (The Gatekeeper / Quality Assurance):
        -   **Inputs**: "Extracted Cypher" AND "Graph Schema".
        -   **Action**: Validates logic, consistency, and completeness.
        -   **Decision Diamond**: "Is Valid?"
            -   **NO (Feedback Loop)**: A RED dashed arrow goes BACK to the **Extraction Agent**. Label: "Improvement Feedback".
            -   **YES (Approval)**: A GREEN solid arrow goes FORWARD to the **Graph Builder**.

    6.  **Graph Builder Agent** (The Constructor):
        -   **Input**: Validated Cypher.
        -   **Process**: Executes queries.
        -   **Target**: **Neo4j Database** (Cylinder Database Icon).

    7.  **End Point**:
        -   **Output**: "Knowledge Graph" (Network/Graph Viz Icon).

    **Design Style**: 
    -   Make sure the illustration has high resolution and quality.
    -   Make sure the illustration has an appropriate heading.
    -   Professional Technical Architecture.
    -   Clean, modern, distinct nodes for Agents.
    -   Make sure the illustration is visually appealing and detailed.
    -   Use high quality icons for each component.
    -   Use distinct and appropriate colors for each agent.
    -   Clear labeled arrows for Data Flow (Markdown, JSON, Cypher).
    -   Highlight the "Critic Feedback Loop" to show the agentic self-correction.
    """

    caption = "Architectural Diagram of the Multi-Agent Knowledge Graph Pipeline. Shows the flow from PDF Ingestion -> Ontology Design -> Extraction -> Critic Validation (with Feedback Loop) -> Graph Construction."

    print("Generating High-Quality Illustration for Multi Agent Workflow...")
    print(f"Communicative Intent: {caption}")
    
    try:
        result = await pipeline.generate(
            GenerationInput(
                source_context=source_context,
                communicative_intent=caption,
                diagram_type=DiagramType.METHODOLOGY, # Methodology fits best for process flows
            )
        )

        print(f"Illustration generated successfully!")
        print(f"Output saved to: {result.image_path}")
        print(f"Run ID: {result.metadata.get('run_id')}")
    except Exception as e:
        print(f"Error generating illustration: {e}")

if __name__ == "__main__":
    asyncio.run(generate_illustration())
