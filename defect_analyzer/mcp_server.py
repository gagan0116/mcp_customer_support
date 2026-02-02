# defect_analyzer/mcp_server.py
"""
Defect Analyzer MCP Server - Analyzes product defect images using Gemini 3 Vision.
Uses the new google.genai SDK for Gemini 3 compatibility.
"""

import os
import base64
import json
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from google import genai
from google.genai import types

load_dotenv()

mcp = FastMCP("defect_analyzer")

ANALYSIS_PROMPT = """You are an expert product defect analyst for electronics and appliances.

Analyze this image and provide a ONE-LINE description of any visible defects.

RULES:
1. Be concise - maximum ONE sentence
2. Describe the defect type and location clearly
3. If you cannot determine the defect with confidence, respond with exactly: "Human review required"
4. If there is no visible defect, say: "No visible defect detected"

Examples of good responses:
- "Cracked screen with fracture lines extending from the top-left corner"
- "Deep scratch marks across the back panel of the device"
- "Dented corner on the bottom-right edge of the appliance body"
- "Water damage stains visible on the internal circuit board"
- "No visible defect detected"
- "Human review required"

Respond with ONLY the one-line description, nothing else."""


@mcp.tool()
async def analyze_defect_image(
    image_path: str = None,
    image_base64: str = None
) -> str:
    """
    Analyzes a product defect image using Gemini 3 Vision and returns a one-line description.
    
    Args:
        image_path: Local file path to the image (e.g., "C:/images/defect.jpg")
        image_base64: Base64 encoded image string (alternative to image_path)
        
    Returns:
        JSON string with defect description and status.
        Example: {"description": "Cracked screen on the display", "status": "success"}
    """
    if not image_path and not image_base64:
        return json.dumps({
            "description": "Error: No image provided. Please provide image_path or image_base64.",
            "status": "error"
        })
    
    try:
        # Check if API key is valid
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return json.dumps({
                "description": "Error: GEMINI_API_KEY not found in environment variables.",
                "status": "error"
            })
        
        # Initialize Gemini 3 client (new SDK)
        client = genai.Client(api_key=api_key)
        
        # Prepare the image
        if image_path:
            if not os.path.exists(image_path):
                return json.dumps({
                    "description": f"Error: File not found at {image_path}",
                    "status": "error"
                })
            
            # Read the image
            with open(image_path, "rb") as f:
                image_data = f.read()
            
            # Determine mime type
            ext = os.path.splitext(image_path)[1].lower()
            mime_types = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp"
            }
            mime_type = mime_types.get(ext, "image/jpeg")
        else:
            # Use base64 image
            image_data = base64.b64decode(image_base64)
            mime_type = "image/jpeg"
        
        # Create image part for Gemini 3 (new SDK format)
        image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)
        
        # Send to Gemini 3 (new SDK pattern)
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=[ANALYSIS_PROMPT, image_part]
        )
        
        description = response.text.strip()
        
        # Determine status
        if "human review required" in description.lower():
            status = "human_review_required"
            description = "Human review required"
        elif "error" in description.lower():
            status = "error"
        else:
            status = "success"
        print(f"Defect analysis result: {description}, status: {status}")
        return json.dumps({
            "description": description,
            "status": status
        })
        
    except Exception as e:
        return json.dumps({
            "description": "Human review required",
            "status": "human_review_required",
            "error_details": str(e)
        })


if __name__ == "__main__":
    mcp.run(transport='stdio')
