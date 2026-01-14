import asyncio
import sys
import os
import json
from contextlib import AsyncExitStack
from typing import Dict, Any, Optional, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
from google import genai
from google.genai import types

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
gemini_client = genai.Client(api_key=api_key)

class RefundsClient:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.sessions: Dict[str, ClientSession] = {}
        # Configuration for all MCP servers we want to use
        self.server_configs = {
            "doc_server": {
                "command": sys.executable,
                "args": [os.path.join(PROJECT_ROOT, "doc_server", "mcp_doc_server.py")],
                "env": None
            },
            "db_verification": {
                "command": sys.executable,
                "args": ["-m", "db_verification.db_verification_server"],
                "env": {"PYTHONPATH": PROJECT_ROOT}
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
            response = gemini_client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            return response.text
        except Exception as e:
            return f"{{\"error\": \"LLM Extraction failed: {str(e)}\"}}"

    async def verify_request_with_db(self, extracted_data: Dict[str, Any]):
        """
        Agentic verification flow loops using Gemini to interpret tool outputs and decide next steps.
        """
        db_session = self.sessions.get("db_verification")
        if not db_session:
            print("❌ Error: db_verification session not available.")
            return

        print("\n" + "="*40)
        print("DATABASE VERIFICATION (AGENT LOOP)")
        print("="*40)

        # 1. Fetch available tools dynamically
        tools_response = await db_session.list_tools()
        tools_map = {t.name: t for t in tools_response.tools}
        # Prepare tool definitions for Gemini
        # We need to reshape them slightly to match what Gemini's API might expect if we were using function calling,
        # but here we are doing "ReAct" style: Prompt -> Text Decision -> Code Execution -> Prompt.
        tools_desc = []
        for t in tools_response.tools:
            tools_desc.append({
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema
            })

        # Initial Context
        messages = [
            """
            You are an expert DB Verification Agent. Your goal is to verify a customer refund request.
            
            STRICT VERIFICATION PROCESS (Follow in order):
            
            STEP 1: IDENTITY CHECK
            - Call 'verify_from_email_matches_customer' with the customer_email.
            - IF 'matched' is False: Call llm _find_orders. Output "Request sent for Human Review" and terminate.
            - IF 'matched' is True: Proceed to Step 2.
            
            STEP 2: FIND ORDER (Hierarchical Search)
            - ATTEMPT 1: If 'order_invoice_id' exists in data, call 'find_order_by_order_invoice_id'.
              - If found, you are DONE. Return the order details.
            - ATTEMPT 2: If finding by ID failed or ID was missing, check if 'invoice_number' exists in data.
              - If yes, call 'find_order_by_invoice_number'.
              - If found, you are DONE.
            - ATTEMPT 3: If specific searches fail, call 'get_customer_orders_with_items' to get a list of recent orders.
              - Then immediately call 'select_order_id' passing that usage data to pick the best one.
              - If a 'selected_order_id' is returned, specific logic to confirm it? No, just accept the selection.
            - ATTEMPT 4: If all else fails, call 'llm_find_orders' to search via SQL.
            
            STEP 3: REPORT
            - If an order is found in any step, output "Verification Successful" and ensure you copy the full order JSON into 'verified_data'.
            - If completely stuck after all attempts, output "Sending for Human Review".
            
            INSTRUCTIONS:
            - Decide the NEXT SINGLE Action.
            - Output JSON ONLY: { "tool_name": "...", "arguments": { ... } }
            - If you are done or need to stop, output JSON: { "action": "terminate", "reason": "...", "verified_data": object|null }
              (If verification was successful, you MUST include the full retrieved order details in the 'verified_data' field).
            """
        ]


        # Context Data
        context_str = f"EXTRACTED DATA:\n{json.dumps(extracted_data, indent=2)}\n\nAVAILABLE TOOLS:\n{json.dumps(tools_desc)}"
        messages.append(context_str)

        # Agent Loop
        max_turns = 8
        for i in range(max_turns):
            print(f"\n--- Turn {i+1} ---")
            
            prompt_content = "\n".join(messages) + "\n\nWhat is the next step? Output valid JSON only."
            
            try:
                # Ask LLM
                response = gemini_client.models.generate_content(
                    model='gemini-2.0-flash', 
                    contents=prompt_content,
                    config={"response_mime_type": "application/json"}
                )
                
                decision_text = response.text
                print(f"🤖 Agent thought: {decision_text}")
                
                decision = json.loads(decision_text)
                
                # Check termination
                if "action" in decision and decision["action"] == "terminate":
                    print(f"🏁 Agent Finished: {decision.get('reason')}")
                    return decision.get("verified_data")
                
                tool_name = decision.get("tool_name")
                args = decision.get("arguments", {})
                
                if not tool_name:
                    print(f"⚠️ Invalid decision format. Stopping.")
                    break

                # Validations before calling
                if tool_name not in tools_map:
                    print(f"❌ Error: Tool {tool_name} not found.")
                    messages.append(f"System: Tool {tool_name} does not exist. Choose from available tools.")
                    continue

                # Execute Tool
                print(f"▶️ Executing: {tool_name}...")
                result = await db_session.call_tool(tool_name, arguments=args)
                tool_output_str = result.content[0].text
                
                # Print snippet for user
                display_output = tool_output_str[:500] + "..." if len(tool_output_str) > 500 else tool_output_str
                print(f"📄 Output: {display_output}")
                
                # Feed result back to context
                messages.append(f"Tool '{tool_name}' Result:\n{tool_output_str}")
                
            except Exception as e:
                print(f"❌ Error in Agent Loop: {e}")
                break

    async def process_refund_request(self, json_file_path):
        """
        Main workflow:
        1. Reads JSON
        2. Parses PDFs
        3. LLM Extraction
        4. Agentic Verification
        """
        doc_session = self.sessions.get("doc_server")
        if not doc_session:
            print("Error: doc_server session not available.")
            return

        if not os.path.exists(json_file_path):
            print(f"Error: File {json_file_path} not found.")
            return

        # Determine artifacts directory from json file path
        artifacts_dir = os.path.dirname(json_file_path)

        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        category = data.get("category", "NONE")
        print(f"\nProcessing Request Category: {category}")

        if category not in ["RETURN", "REPLACEMENT", "REFUND"]:
            print("Skipping: Request does not belong to eligible category.")
            return

        # --- Aggregate Context ---
        combined_text = f"""
        --- EMAIL METADATA ---
        Sender: {data.get('user_id', 'Unknown')}
        Received At: {data.get('received_at', 'Unknown')}
        confidence_score: {data.get('confidence', 'N/A')}
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
                    
                    file_data = attachment.get("data", {})
                    base64_content = ""
                    if isinstance(file_data, dict):
                         base64_content = file_data.get("data", "")
                    elif isinstance(file_data, str):
                         base64_content = file_data
                    
                    if not base64_content:
                        continue

                    try:
                        # Construct output text path
                        txt_filename = f"{os.path.splitext(filename)[0]}.txt"
                        txt_path = os.path.join(artifacts_dir, txt_filename)
                        
                        parse_result = await doc_session.call_tool(
                            "process_invoice",
                            arguments={"base64_content": base64_content, "output_txt_path": txt_path}
                        )
                        combined_text += f"\n\n--- INVOICE ATTACHMENT: {filename} ---\n{parse_result.content[0].text}"
                        
                    except Exception as e:
                        print(f"    Error processing attachment {filename}: {e}")

        # --- Extracion ---
        print("\nSending combined context to LLM for extraction...")
        extraction_json_str = await self.extract_order_details(combined_text)
        
        try:
            extracted_data = json.loads(extraction_json_str)
        except json.JSONDecodeError:
            print("Error decoding extraction result.")
            extracted_data = {}

        print("\n" + "="*40)
        print("EXTRACTED ORDER DETAILS")
        print("="*40)
        print(json.dumps(extracted_data, indent=2))
        
        output_path = os.path.join(artifacts_dir, "extracted_order.json")
        with open(output_path, "w", encoding='utf-8') as f:
            f.write(json.dumps(extracted_data, indent=2))
        print(f"\nSaved extraction to {output_path}")

        # --- DB Verification (Agentic) ---
        verified_record = await self.verify_request_with_db(extracted_data)

        if verified_record:
            verified_path = os.path.join(artifacts_dir, "verified_order.json")
            with open(verified_path, "w", encoding='utf-8') as f:
                json.dump(verified_record, f, indent=2)
            print(f"\n✅ Verified Order Details saved to {verified_path}")
        else:
            print("\nℹ️ No verified order data was returned to save.")

    async def cleanup(self):
        await self.exit_stack.aclose()
        print("\nAll connections closed.")

async def main():
    # 1. DOWNLOAD LATEST JSON FROM GCS
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    blob_name = os.getenv("GCS_BLOB_NAME")
    
    base_filename = os.path.basename(blob_name)
    folder_name = os.path.splitext(base_filename)[0]
    
    # Create the instance artifacts directory
    instance_artifacts_dir = os.path.join(PROJECT_ROOT, "artifacts", folder_name)
    os.makedirs(instance_artifacts_dir, exist_ok=True)
    
    dest_path = os.path.join(instance_artifacts_dir, base_filename)

    print("\n--- Step 1: Downloading from GCS ---")
    print(f"Downloading {blob_name} to {dest_path}")
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