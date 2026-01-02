import os
from mcp.server.fastmcp import FastMCP
from pypdf import PdfReader

# Initialize FastMCP server
mcp = FastMCP("doc_server")

ARTIFACTS_DIR = "artifacts"

@mcp.tool()
def parse_invoice(pdf_path: str) -> str:
    """
    Parse a PDF invoice and save the extracted text to the artifacts directory.

    Args:
        pdf_path: The path to the PDF file to parse.

    Returns:
        A message indicating where the parsed text has been saved.
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
            
        return f"Successfully parsed {base_name}. Text saved to {output_file}"

    except Exception as e:
        return f"Error parsing PDF: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport='stdio')
