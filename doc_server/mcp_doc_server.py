import os
import base64
import io
from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader

# Initialize FastMCP server
mcp = FastMCP("doc_server")

@mcp.tool()
def parse_invoice_from_base64(base64_content: str) -> str:
    """
    Decodes a base64 string, parses it as a PDF in memory, and returns the text content.
    Does not save files to disk.

    Args:
        base64_content: The base64 encoded string of the PDF file.

    Returns:
        The extracted text content from the PDF.
    """
    try:
        # Sanitize base64 string (remove data prefix if present)
        if "," in base64_content:
            base64_content = base64_content.split(",")[1]

        pdf_bytes = base64.b64decode(base64_content)
        
        # Create a file-like object in memory
        pdf_file = io.BytesIO(pdf_bytes)
        
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        return f"Successfully parsed.\n\nEXTRACTED TEXT:\n{text}"

    except Exception as e:
        return f"Error parsing PDF: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport='stdio')