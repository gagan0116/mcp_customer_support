import asyncio
import sys
import os
import json
from contextlib import AsyncExitStack
from typing import Dict, Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

# Add parent directory to path to find servers and utility scripts
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

# Import the GCS download function
from extract_json_gcs import download_blob

# Configure Gemini Client
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY not found in .env")
    sys.exit(1)

# Initialize global Gemini client
# Note: Newer SDK uses a client instance instead of module-level configure
gemini_client = genai.Client(api_key=api_key)

class RefundsClient:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.sessions: Dict[str, ClientSession] = {}
        self.server_configs = {
            "doc_server": {
                "command": sys.executable,
                "args": [os.path.join(PROJECT_ROOT, "doc_server", "mcp_doc_server.py")],
                "env": None
            }
        }

    async def connect_to_server(self, server_name: str, config: Dict[str, Any]):
        """Connects to a single MCP server."""
        print(f"Connecting to {server_name}...")
        try:
            server_params = StdioServerParameters(**config)
            
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = stdio_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            
            self.sessions[server_name] = session
            print(f"✅ Connected to {server_name}")

        except Exception as e:
            print(f"❌ Error connecting to {server_name}: {e}")
            raise

    async def connect_to_all_servers(self):
        """Iterates through configuration and connects to all servers."""
        for name, config in self.server_configs.items():
            await self.connect_to_server(name, config)

    async def extract_order_details(self, combined_text):
        """
        Uses Gemini to extract structured order details from the combined text.
        """
        prompt = f"""
        You are an expert data extraction agent.
        Your task is to analyze the following customer support email and its attached invoice content.
        Extract the specific details listed below into a strict JSON format.
        
        If a field is not found in the text, leave it as null or an empty string, do not invent data.
        
        REQUIRED JSON STRUCTURE:
        {{
            "customer_email": "string (Sender's email)",
            "full_name": "string",
            "phone": "string",
            "invoice_number": "string",
            "order_invoice_id": "string",
            "order_date": "string (YYYY-MM-DD format if possible)",
            "ship_mode": "string",
            "ship_city": "string",
            "ship_state": "string",
            "ship_country": "string",
            "currency": "string (e.g., USD)",
            "discount_amount": "number",
            "shipping_amount": "number",
            "total_amount": "number",
            "order_items": [
                {{
                    "sku": "string",
                    "item_name": "string",
                    "category": "string",
                    "subcategory": "string",
                    "quantity": "integer",
                    "unit_price": "number",
                    "line_total": "number"
                }}
            ],
            "return_category": "string (RETURN / REPLACEMENT / REFUND)",
            "return_reason": "string (Summary of why they want a return/refund)",
            "confidence_score": "number (0.0 to 1.0 - how confident are you in this extraction)"
        }}

        INPUT TEXT:
        {combined_text}
        
        OUTPUT ONLY VALID JSON.
        """

        try:
            # Updated call for google.genai package
            response = gemini_client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            return response.text
        except Exception as e:
            return f"{{\"error\": \"LLM Extraction failed: {str(e)}\"}}"

    async def process_refund_request(self, json_file_path):
        """
        Main workflow:
        1. Reads JSON email data
        2. Filters Categories
        3. Parses All PDF Attachments (using doc_server session)
        4. Combines text
        5. Calls LLM for extraction
        """
        doc_session = self.sessions.get("doc_server")
        if not doc_session:
            print("Error: doc_server session not available.")
            return

        if not os.path.exists(json_file_path):
            print(f"Error: File {json_file_path} not found.")
            return

        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        category = data.get("category", "NONE")
        print(f"\nProcessing Request Category: {category}")

        # Check for Eligible Categories
        eligible_categories = ["RETURN", "REPLACEMENT", "REFUND"]
        if category not in eligible_categories:
            print("Skipping: Request does not belong to eligible category.")
            return

        # --- Aggregate Context ---
        combined_text = f"""
        --- EMAIL METADATA ---
        Sender: {data.get('user_id', 'Unknown')}
        Received At: {data.get('received_at', 'Unknown')}
        Category: {category}
        
        --- EMAIL BODY ---
        {data.get('email_body', '')}
        """

        # Handle Attachments
        attachments = data.get("attachments", [])
        if attachments:
            print(f"Processing {len(attachments)} attachment(s)...")
            
            for attachment in attachments:
                filename = attachment.get("filename", "")
                
                if filename.lower().endswith(".pdf"):
                    print(f"  - Parsing PDF: {filename}")
                    
                    # Extract Base64 Data
                    file_data = attachment.get("data", {})
                    base64_content = ""
                    if isinstance(file_data, dict):
                         base64_content = file_data.get("data", "")
                    elif isinstance(file_data, str):
                         base64_content = file_data
                    
                    if not base64_content:
                        continue

                    try:
                        # 1. Save PDF
                        save_result = await doc_session.call_tool(
                            "save_base64_pdf",
                            arguments={
                                "base64_content": base64_content,
                                "filename": filename
                            }
                        )
                        saved_pdf_path = save_result.content[0].text
                        
                        # 2. Parse PDF
                        parse_result = await doc_session.call_tool(
                            "parse_invoice",
                            arguments={"pdf_path": saved_pdf_path}
                        )
                        
                        extracted_text = parse_result.content[0].text
                        combined_text += f"\n\n--- INVOICE ATTACHMENT: {filename} ---\n{extracted_text}"
                        
                    except Exception as e:
                        print(f"    Error processing attachment {filename}: {e}")

        # --- Final LLM Extraction ---
        print("\nSending combined context to LLM for extraction...")
        extraction_result = await self.extract_order_details(combined_text)
        
        print("\n" + "="*40)
        print("EXTRACTED ORDER DETAILS (JSON)")
        print("="*40)
        print(extraction_result)
        
        # Save result to file
        output_path = os.path.join(os.path.dirname(__file__), "extracted_order.json")
        with open(output_path, "w", encoding='utf-8') as f:
            f.write(extraction_result)
        print(f"\nSaved extraction to {output_path}")

    async def cleanup(self):
        await self.exit_stack.aclose()
        print("\nAll connections closed.")

async def main():
    # 1. DOWNLOAD LATEST JSON FROM GCS
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    blob_name = os.getenv("GCS_BLOB_NAME")
    # Prefer env variable for destination, fallback to hardcoded path
    dest_path = os.getenv("GCS_DESTINATION_PATH")
    
    if not dest_path:
        # Fallback to local default if env var is missing
        dest_path = os.path.join(PROJECT_ROOT, "artifacts", "latest_email.json")

    print("\n--- Step 1: Downloading from GCS ---")
    download_blob(bucket_name, blob_name, dest_path)
    
    # 2. PROCESS THE REFUND REQUEST
    if os.path.exists(dest_path):
        print(f"\n--- Step 2: Processing {dest_path} ---")
        client = RefundsClient()
        try:
            await client.connect_to_all_servers()
            await client.process_refund_request(dest_path)
        finally:
            await client.cleanup()
    else:
        print("Aborting: JSON input file could not be found.")

if __name__ == "__main__":
    asyncio.run(main())