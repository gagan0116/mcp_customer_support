import os
from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader

# Initialize FastMCP server
mcp = FastMCP("doc_server")

# Use absolute path for artifacts to avoid "file not found" errors
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Go up one level to project root, then into artifacts
PROJECT_ROOT = os.path.dirname(BASE_DIR)
ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "artifacts")

@mcp.tool()
def parse_invoice(pdf_path: str) -> str:
    """
    Parse a PDF invoice, save the text to artifacts, and return the content.

    Args:
        pdf_path: The absolute path to the PDF file to parse.

    Returns:
        The extracted text content from the PDF.
    """
    if not os.path.exists(pdf_path):
        return f"Error: File not found at {pdf_path}"

    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        # Create artifacts directory if it doesn't exist
        os.makedirs(ARTIFACTS_DIR, exist_ok=True)
        
        # Generate output filename
        base_name = os.path.basename(pdf_path)
        file_name = os.path.splitext(base_name)[0]
        output_file = os.path.join(ARTIFACTS_DIR, f"{file_name}_parsed.txt")
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text)
            
        # Return the actual text so the LLM can use it immediately
        return f"Successfully parsed. Saved to {output_file}\n\nEXTRACTED TEXT:\n{text}"

    except Exception as e:
        return f"Error parsing PDF: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport='stdio')