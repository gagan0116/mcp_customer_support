import asyncio
import os
from paperbanana import PaperBananaPipeline, GenerationInput, DiagramType
from paperbanana.core.config import Settings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def generate_google_stack_illustration():
    # Configure settings
    settings = Settings(
        vlm_provider="gemini",
        vlm_model="gemini-2.0-flash", 
        image_provider="google_imagen",
        image_model="gemini-3-pro-image-preview", 
        refinement_iterations=5, 
        verbose=True
    )

    pipeline = PaperBananaPipeline(settings=settings)

    # Google Tech Stack List (No Explanations)
    # Detailed Visual Script for a Premium Tech Stack Grid
    source_context = """
    # VISUAL DIRECTIVE: GOOGLE TECHNOLOGY STACK
    
    **LAYOUT STYLE**: Modern "Bento Box" Grid. Clean, organized, and perfectly aligned in 4 Columns.
    **MANDATORY HEADER**: "GOOGLE TECHNOLOGY STACK" (Large, Bold, Sans-Serif at the top).
    **DONT HAVE ANY ARROWS BETWEEN THE STACKS**
    **COLOR PALETTE**: 
    - Background: Deep Slate Gray (#202124) or Clean White.
    - Accents: Google Blue (#4285F4), Red (#EA4335), Yellow (#FBBC04), Green (#34A853).
    - Text: High Contrast.

    ---

    ## COL 1: AI MODELS (Theme: Gemini Purple/Blue)
    *   **Container**: Tall, prominent card.
    *   **Content**:
        -   `gemini-3-pro-preview`
        -   `gemini-3-flash-preview`
        -   `imagen-3`
        -   `gemini-3-pro-image-preview`

    ## COL 2: GOOGLE CLOUD (Theme: Google Blue)
    *   **Container**: Solid structural card.
    *   **Content**:
        -   `Cloud Run`
        -   `Cloud Storage`
        -   `Cloud SQL`
        -   `Cloud Firestore`
        -   `Secret Manager`
        -   `Cloud Pub/Sub`
        -   `Artifact Registry`
        -   `Cloud Tasks`

    ## COL 3: APIs & SDKs (Theme: Google Green)
    *   **Container**: Connection card.
    *   **Content**:
        -   `Gmail API`
        -   `Google GenAI SDK`
        -   `Google Auth`

    ## COL 4: LIBRARIES (Theme: Google Yellow)
    *   **Container**: Tooling card.
    *   **Content**:
        -   `Paper Banana`
        -   `Nano Banana`

    ---
    **FINAL POLISH**: ensure strictly aligned boxes. Professional Technical Documentation standard.
    """

    caption = "A professional Tech Stack architecture diagram showing the integration of Gemini AI models with Google Cloud Serverless and Data infrastructure."

    print("Generating Google Stack Illustration...")
    
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
    except Exception as e:
        print(f"Error generating illustration: {e}")

if __name__ == "__main__":
    asyncio.run(generate_google_stack_illustration())
