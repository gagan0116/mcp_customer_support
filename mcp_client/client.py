import asyncio
import sys
import os
import json
import time
import uuid
from datetime import datetime, timezone
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

# Import the Adjudicator Agent
from policy_compiler_agents.adjudicator_agent import Adjudicator

# Import database connection for refund_cases table
from db_verification.db import db_connection

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
            },
            "defect_analyzer": {
                "command": sys.executable,
                "args": [os.path.join(PROJECT_ROOT, "defect_analyzer", "mcp_server.py")],
                "env": None
            }
        }
    
    async def generate_with_retry(self, model, contents, config=None, max_retries=5):
        """Helper to call Gemini with exponential backoff for 429 errors."""
        base_delay = 2
        for attempt in range(max_retries):
            try:
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                return response
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    delay = base_delay * (2 ** attempt)
                    print(f"⚠️ Quota exceeded (429). Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    raise e
        raise Exception(f"Failed after {max_retries} retries due to quota exhaustion.")

    def insert_refund_case(
        self,
        email_data: Dict[str, Any],
        extracted_data: Dict[str, Any],
        verified_record: Optional[Dict[str, Any]],
        adjudication_result: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Insert a record into the refund_cases table.
        Returns the case_id if successful, None otherwise.
        """
        try:
            case_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            # Extract fields from email_data
            from_email = email_data.get("user_id", "")
            received_at_str = email_data.get("received_at")
            received_at = datetime.fromisoformat(received_at_str.replace("Z", "+00:00")) if received_at_str else now
            classification = email_data.get("category", "UNKNOWN")
            confidence = email_data.get("confidence")
            email_body = email_data.get("email_body", "")
            attachments = email_data.get("attachments", [])
            
            # Generate source_message_id from email data or use a unique identifier
            source_message_id = email_data.get("message_id") or f"{from_email}_{received_at.strftime('%Y%m%dT%H%M%SZ')}_{case_id[:8]}"
            
            # Extract customer name from extracted_data
            from_name = extracted_data.get("full_name")
            
            # Extract invoice identifiers from extracted_data
            extracted_invoice_number = extracted_data.get("invoice_number")
            extracted_order_invoice_id = extracted_data.get("order_invoice_id")
            
            # Get customer_id and order_id from verified_record if available
            # The verified_record has nested structure: data.customer.customer_id and data.order_details.order_id
            customer_id = None
            order_id = None
            if verified_record:
                data_section = verified_record.get("data", {})
                if data_section:
                    customer_info = data_section.get("customer", {})
                    order_details = data_section.get("order_details", {})
                    customer_id = customer_info.get("customer_id")
                    order_id = order_details.get("order_id")
                # Fallback to top-level if nested structure not found
                if not customer_id:
                    customer_id = verified_record.get("customer_id")
                if not order_id:
                    order_id = verified_record.get("order_id")
            
            # Determine verification status
            if verified_record:
                verification_status = "VERIFIED"
            else:
                verification_status = "PENDING_REVIEW"
            
            # Build verification notes
            verification_notes = None
            if adjudication_result:
                decision = adjudication_result.get("decision", "")
                reason = adjudication_result.get("details", {}).get("reason", "")
                verification_notes = f"Decision: {decision}. {reason}"
            
            # Prepare metadata
            metadata = {
                "extraction_confidence": extracted_data.get("confidence_score"),
                "return_reason_category": extracted_data.get("return_reason_category"),
                "return_reason": extracted_data.get("return_reason"),
                "item_condition": extracted_data.get("item_condition"),
            }
            if adjudication_result:
                metadata["adjudication"] = adjudication_result
            
            # Prepare attachments JSONB (store filenames only, not full data)
            attachments_json = [
                {"filename": att.get("filename"), "mimeType": att.get("mimeType")}
                for att in attachments
            ] if attachments else None
            
            insert_sql = """
                INSERT INTO refund_cases (
                    case_id, case_source, source_message_id, received_at,
                    from_email, from_name, subject, body,
                    customer_id, order_id,
                    extracted_invoice_number, extracted_order_invoice_id,
                    classification, confidence,
                    verification_status, verification_notes,
                    attachments, metadata,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s
                )
                ON CONFLICT (source_message_id) DO UPDATE SET
                    customer_id = EXCLUDED.customer_id,
                    order_id = EXCLUDED.order_id,
                    verification_status = EXCLUDED.verification_status,
                    verification_notes = EXCLUDED.verification_notes,
                    metadata = EXCLUDED.metadata,
                    updated_at = EXCLUDED.updated_at
                RETURNING case_id
            """
            
            params = (
                case_id,
                "EMAIL",  # case_source
                source_message_id,
                received_at,
                from_email,
                from_name,
                None,  # subject (not available in current data structure)
                email_body,
                customer_id,
                order_id,
                extracted_invoice_number,
                extracted_order_invoice_id,
                classification,
                confidence,
                verification_status,
                verification_notes,
                json.dumps(attachments_json) if attachments_json else None,
                json.dumps(metadata),
                now,
                now
            )
            
            with db_connection() as conn:
                cur = conn.cursor()
                try:
                    cur.execute(insert_sql, params)
                    result = cur.fetchone()
                    conn.commit()
                    returned_case_id = result[0] if result else case_id
                    print(f"\n✅ Refund case inserted/updated in database: {returned_case_id}")
                    return returned_case_id
                except Exception as db_err:
                    conn.rollback()
                    print(f"\n❌ Database error inserting refund case: {db_err}")
                    raise
                finally:
                    cur.close()
                    
        except Exception as e:
            print(f"\n❌ Error inserting refund case: {e}")
            import traceback
            traceback.print_exc()
            return None

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
            "return_request_date": "string (YYYY-MM-DD format - date email was received)",
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
            "item_condition": "string (Allowed values: 'NEW_UNOPENED', 'OPENED_LIKE_NEW', 'DAMAGED_DEFECTIVE', 'MISSING_PARTS', 'UNKNOWN')",
            "return_category": "string (RETURN / REPLACEMENT / REFUND)",
            "return_reason_category": "string (Allowed values: 'CHANGED_MIND', 'DEFECTIVE', 'WRONG_ITEM_SENT', 'ARRIVED_LATE', 'OTHER')",
            "return_reason": "string (Detailed and entire summary of the reason for return/refund)",
            "confidence_score": "number (0.0 to 1.0 - how confident are you in this extraction)"
        }}

        INPUT TEXT:
        {combined_text}
        
        OUTPUT ONLY VALID JSON.
        """

        try:
            response = await self.generate_with_retry(
                model='gemini-2.5-flash', 
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

        tools_response = await db_session.list_tools()
        tools_map = {t.name: t for t in tools_response.tools}
        tools_desc = []
        for t in tools_response.tools:
            tools_desc.append({
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema
            })

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
        context_str = f"EXTRACTED DATA:\n{json.dumps(extracted_data, indent=2)}\n\nAVAILABLE TOOLS:\n{json.dumps(tools_desc)}"
        messages.append(context_str)

        max_turns = 8
        for i in range(max_turns):
            print(f"\n--- Turn {i+1} ---")
            
            # Rate limiting sleep
            await asyncio.sleep(2)
            
            prompt_content = "\n".join(messages) + "\n\nWhat is the next step? Output valid JSON only."
            
            try:
                response = await self.generate_with_retry(
                    model='gemini-2.5-flash', 
                    contents=prompt_content,
                    config={"response_mime_type": "application/json"}
                )
                
                decision_text = response.text
                
                # Handle None or empty response from Gemini
                if decision_text is None or decision_text.strip() == "":
                    print(f"⚠️ Empty response from LLM on turn {i+1}. Retrying...")
                    messages.append("System: Your previous response was empty. Please provide a valid JSON response.")
                    continue
                
                print(f"🤖 Agent thought: {decision_text}")
                
                try:
                    decision = json.loads(decision_text)
                except json.JSONDecodeError as json_err:
                    print(f"⚠️ Failed to parse JSON response: {json_err}")
                    messages.append(f"System: Your response was not valid JSON. Error: {json_err}. Please output valid JSON only.")
                    continue

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
        
        # Store original email data for refund_cases table
        email_data = data.copy()

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
                
                # Handle image attachments for defect analysis
                elif filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                    print(f"  - Analyzing defect image: {filename}")
                    
                    defect_session = self.sessions.get("defect_analyzer")
                    if defect_session:
                        file_data = attachment.get("data", {})
                        base64_content = ""
                        if isinstance(file_data, dict):
                            base64_content = file_data.get("data", "")
                        elif isinstance(file_data, str):
                            base64_content = file_data
                        
                        if base64_content:
                            try:
                                result = await defect_session.call_tool(
                                    "analyze_defect_image",
                                    arguments={"image_base64": base64_content}
                                )
                                defect_result = json.loads(result.content[0].text)
                                description = defect_result.get("description", "No analysis available")
                                status = defect_result.get("status", "unknown")
                                
                                combined_text += f"\n\n--- DEFECT IMAGE: {filename} ---\nDefect Analysis: {description}\nAnalysis Status: {status}"
                                print(f"    Defect Analysis: {description}")
                            except Exception as e:
                                print(f"    Error analyzing image {filename}: {e}")
                                combined_text += f"\n\n--- DEFECT IMAGE: {filename} ---\nDefect Analysis: Human review required (analysis failed)"
                    else:
                        print(f"    Warning: defect_analyzer session not available")

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
            # Merge extracted intent fields into verified record
            verified_record["return_request_date"] = extracted_data.get("return_request_date")
            verified_record["return_category"] = extracted_data.get("return_category")
            verified_record["return_reason_category"] = extracted_data.get("return_reason_category")
            verified_record["return_reason"] = extracted_data.get("return_reason")
            verified_record["item_condition"] = extracted_data.get("item_condition")
            verified_record["confidence_score"] = extracted_data.get("confidence_score")
            
            verified_path = os.path.join(artifacts_dir, "verified_order.json")
            with open(verified_path, "w", encoding='utf-8') as f:
                json.dump(verified_record, f, indent=2)
            print(f"\n✅ Verified Order Details saved to {verified_path}")
            
            # --- Adjudication ---
            print("\n" + "="*50)
            print("RUNNING ADJUDICATOR AGENT")
            print("="*50)
            
            try:
                adjudicator = Adjudicator()
                adjudication_result = await adjudicator.adjudicate(verified_record)
                
                # Save adjudication decision
                decision_path = os.path.join(artifacts_dir, "adjudication_decision.json")
                with open(decision_path, "w", encoding='utf-8') as f:
                    json.dump(adjudication_result, f, indent=2, default=str)
                print(f"\n✅ Adjudication Decision saved to {decision_path}")
                
                # Print summary
                print("\n" + "="*50)
                print(f"DECISION: {adjudication_result.get('decision', 'UNKNOWN')}")
                print(f"REASON: {adjudication_result.get('details', {}).get('reason', 'N/A')}")
                print("="*50)
                
                # Insert refund case into database
                self.insert_refund_case(
                    email_data=email_data,
                    extracted_data=extracted_data,
                    verified_record=verified_record,
                    adjudication_result=adjudication_result
                )
                
            except Exception as e:
                print(f"\n⚠️ Adjudication failed: {e}")
                import traceback
                traceback.print_exc()
                
                # Still insert refund case even if adjudication failed
                self.insert_refund_case(
                    email_data=email_data,
                    extracted_data=extracted_data,
                    verified_record=verified_record,
                    adjudication_result=None
                )
        else:
            print("\nℹ️ No verified order data was returned to save.")
            
            # Insert refund case with pending review status
            self.insert_refund_case(
                email_data=email_data,
                extracted_data=extracted_data,
                verified_record=None,
                adjudication_result=None
            )

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
    import sys
    # Windows-specific: Use SelectorEventLoop to prevent SSL cleanup errors
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass