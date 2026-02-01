import asyncio
import sys
import os
import json
import uuid
from datetime import datetime, timezone
from contextlib import AsyncExitStack
from typing import Dict, Any, Optional
from google.cloud import storage

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables
load_dotenv()

# Define Project Root
# In Docker, this will be /app (where this script is).
# Locally, it might be mcp_processor, so we need to go up one level if testing locally.
current_dir = os.path.dirname(os.path.abspath(__file__))
# If we are in mcp_processor subdir locally, project root is parent. 
# But in Docker, we copy files to root /app. 
# Let's rely on an env var or default to current dir.
PROJECT_ROOT = os.getenv("PROJECT_ROOT", current_dir)
sys.path.append(PROJECT_ROOT)

try:
    from policy_compiler_agents.adjudicator_agent import Adjudicator
    from db_verification.db import db_connection
except ImportError:
    # Fallback for local testing if running from subdirectory
    sys.path.append(os.path.dirname(current_dir))
    from policy_compiler_agents.adjudicator_agent import Adjudicator
    from db_verification.db import db_connection


# Configure Gemini Client
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Warning: GEMINI_API_KEY not set (ok if building, but needed for runtime)")

gemini_client = genai.Client(api_key=api_key) if api_key else None

def download_blob(bucket_name, source_blob_name, destination_file_name):
    """Downloads a blob from the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    
    directory = os.path.dirname(destination_file_name)
    if directory:
        os.makedirs(directory, exist_ok=True)
        
    blob.download_to_filename(destination_file_name)
    print(f"Downloaded {source_blob_name} to {destination_file_name}")

class MCPProcessor:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.sessions: Dict[str, ClientSession] = {}
        
        # Configuration for MCP servers
        # We assume the server scripts are copied to the container root
        self.server_configs = {
            "doc_server": {
                "command": sys.executable,
                "args": [os.path.join(PROJECT_ROOT, "doc_server", "mcp_doc_server.py")],
                "env": None
            },
            "db_verification": {
                "command": sys.executable,
                "args": ["-m", "db_verification.db_verification_server"],
                "env": {**os.environ, "PYTHONPATH": PROJECT_ROOT}  # Inherit all env vars + set PYTHONPATH
            },
            "defect_analyzer": {
                "command": sys.executable,
                "args": [os.path.join(PROJECT_ROOT, "defect_analyzer", "mcp_server.py")],
                "env": None
            }
        }
    
    async def generate_with_retry(self, model, contents, config=None, max_retries=5):
        if not gemini_client:
             raise Exception("Gemini Client not initialized")
             
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

    def insert_refund_case(self, email_data, extracted_data, verified_record, adjudication_result=None):
        # ... logic from client.py ...
        # Copied verbatim from client.py insert_refund_case to save space in thought process
        # but I must write full code to file.
        try:
            case_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            
            from_email = email_data.get("user_id", "")
            received_at_str = email_data.get("received_at")
            received_at = datetime.fromisoformat(received_at_str.replace("Z", "+00:00")) if received_at_str else now
            classification = email_data.get("category", "UNKNOWN")
            confidence = email_data.get("confidence")
            email_body = email_data.get("email_body", "")
            attachments = email_data.get("attachments", [])
            
            source_message_id = email_data.get("message_id") or f"{from_email}_{received_at.strftime('%Y%m%dT%H%M%SZ')}_{case_id[:8]}"
            
            from_name = extracted_data.get("full_name")
            extracted_invoice_number = extracted_data.get("invoice_number")
            extracted_order_invoice_id = extracted_data.get("order_invoice_id")
            
            customer_id = None
            order_id = None
            if verified_record:
                data_section = verified_record.get("data", {})
                if data_section:
                    customer_info = data_section.get("customer", {})
                    order_details = data_section.get("order_details", {})
                    customer_id = customer_info.get("customer_id")
                    order_id = order_details.get("order_id")
                if not customer_id:
                    customer_id = verified_record.get("customer_id")
                if not order_id:
                    order_id = verified_record.get("order_id")
            
            if verified_record:
                verification_status = "VERIFIED"
            else:
                verification_status = "PENDING_REVIEW"
            
            verification_notes = None
            if adjudication_result:
                decision = adjudication_result.get("decision", "")
                reason = adjudication_result.get("details", {}).get("reason", "")
                verification_notes = f"Decision: {decision}. {reason}"
            
            metadata = {
                "extraction_confidence": extracted_data.get("confidence_score"),
                "return_reason_category": extracted_data.get("return_reason_category"),
                "return_reason": extracted_data.get("return_reason"),
                "item_condition": extracted_data.get("item_condition"),
            }
            if adjudication_result:
                metadata["adjudication"] = adjudication_result
            
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
                case_id, "EMAIL", source_message_id, received_at,
                from_email, from_name, None, email_body,
                customer_id, order_id,
                extracted_invoice_number, extracted_order_invoice_id,
                classification, confidence,
                verification_status, verification_notes,
                json.dumps(attachments_json) if attachments_json else None,
                json.dumps(metadata), now, now
            )
            
            with db_connection() as conn:
                cur = conn.cursor()
                cur.execute(insert_sql, params)
                result = cur.fetchone()
                conn.commit()
                returned_case_id = result[0] if result else case_id
                print(f"✅ Refund case inserted: {returned_case_id}")
                return returned_case_id
                
        except Exception as e:
            print(f"❌ Error inserting refund case: {e}")
            import traceback
            traceback.print_exc()
            raise # Re-raise to ensure task failure implies retry

    async def connect_to_all_servers(self):
        for name, config in self.server_configs.items():
            print(f"Connecting to {name}...")
            try:
                server_params = StdioServerParameters(**config)
                stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
                read, write = stdio_transport
                session = await self.exit_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self.sessions[name] = session
                print(f"✅ Connected to {name}")
            except Exception as e:
                print(f"❌ Error connecting to {name}: {e}")
                raise

    async def extract_order_details(self, combined_text):
        from google.genai.types import Schema
        
        ORDER_ITEM_SCHEMA = Schema(
            type="object",
            properties={
                "sku": Schema(type="string", description="Product SKU"),
                "item_name": Schema(type="string", description="Product name"),
                "category": Schema(type="string", description="Product category"),
                "subcategory": Schema(type="string", description="Product subcategory"),
                "quantity": Schema(type="integer", description="Quantity ordered"),
                "unit_price": Schema(type="number", description="Price per unit"),
                "line_total": Schema(type="number", description="Total for this line item"),
            }
        )
        
        EXTRACTION_SCHEMA = Schema(
            type="object",
            properties={
                "customer_email": Schema(type="string", description="Sender's email address"),
                "full_name": Schema(type="string", description="Customer full name"),
                "phone": Schema(type="string", description="Customer phone number"),
                "invoice_number": Schema(type="string", description="Invoice number"),
                "order_invoice_id": Schema(type="string", description="Order/Invoice ID"),
                "order_date": Schema(type="string", description="Order date in YYYY-MM-DD format"),
                "return_request_date": Schema(type="string", description="Date email was received"),
                "ship_mode": Schema(type="string", description="Shipping method"),
                "ship_city": Schema(type="string", description="Shipping city"),
                "ship_state": Schema(type="string", description="Shipping state"),
                "ship_country": Schema(type="string", description="Shipping country"),
                "currency": Schema(type="string", description="Currency code e.g. USD"),
                "discount_amount": Schema(type="number", description="Discount applied"),
                "shipping_amount": Schema(type="number", description="Shipping cost"),
                "total_amount": Schema(type="number", description="Order total"),
                "order_items": Schema(type="array", items=ORDER_ITEM_SCHEMA, description="List of order items"),
                "item_condition": Schema(type="string", description="NEW_UNOPENED, OPENED_LIKE_NEW, DAMAGED_DEFECTIVE, MISSING_PARTS, or UNKNOWN"),
                "return_category": Schema(type="string", description="RETURN, REPLACEMENT, or REFUND"),
                "return_reason_category": Schema(type="string", description="CHANGED_MIND, DEFECTIVE, WRONG_ITEM_SENT, ARRIVED_LATE, or OTHER"),
                "return_reason": Schema(type="string", description="Detailed summary of return reason"),
                "confidence_score": Schema(type="number", description="Extraction confidence 0.0 to 1.0"),
            },
            required=["customer_email"]
        )
        
        prompt = f"""You are an expert data extraction agent.
Analyze the following customer support email and its attached invoice content.
Extract all available details. If a field is not found, leave it as null.

INPUT TEXT:
{combined_text}

Extract all order and customer details from the text above."""

        try:
            response = await self.generate_with_retry(
                model='gemini-2.0-flash', # Using flash for speed/cost, pro availability
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": EXTRACTION_SCHEMA
                }
            )
            return response.text
        except Exception as e:
            return f"error: LLM Extraction failed: {str(e)}"

    async def verify_request_with_db(self, extracted_data):
        db_session = self.sessions.get("db_verification")
        if not db_session:
            print("❌ Error: db_verification session not available.")
            return

        print("Starting DB Verification Agent Loop...")
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
            """You are an expert DB Verification Agent. Your goal is to verify a customer refund request.
            STRICT VERIFICATION PROCESS:
            1. IDENTITY CHECK: Call 'verify_from_email_matches_customer'. If false, call llm_find_orders then terminate.
            2. FIND ORDER: 
               - Try 'find_order_by_order_invoice_id'.
               - Try 'find_order_by_invoice_number'.
               - Try 'get_customer_orders_with_items' then 'select_order_id'.
               - Try 'llm_find_orders'.
            3. REPORT:
               - If found, output "Verification Successful" and include full order JSON in 'verified_data'.
               - If stuck, output "Sending for Human Review".
            
            Output JSON ONLY: { "tool_name": "...", "arguments": { ... } }
            Or if done: { "action": "terminate", "reason": "...", "verified_data": object|null }
            """
        ]
        context_str = f"EXTRACTED DATA:\n{json.dumps(extracted_data, indent=2)}\n\nAVAILABLE TOOLS:\n{json.dumps(tools_desc)}"
        messages.append(context_str)

        max_turns = 8
        for i in range(max_turns):
            print(f"--- Turn {i+1} ---")
            await asyncio.sleep(1) # Slight pause
            
            prompt_content = "\n".join(messages) + "\n\nWhat is the next step? Output valid JSON only."
            try:
                response = await self.generate_with_retry(
                    model='gemini-2.0-flash',
                    contents=prompt_content,
                    config={"response_mime_type": "application/json"}
                )
                decision_text = response.text
                if not decision_text: continue
                
                decision = json.loads(decision_text)
                
                if decision.get("action") == "terminate":
                    print(f"Agent Finished: {decision.get('reason')}")
                    return decision.get("verified_data")
                
                tool_name = decision.get("tool_name")
                args = decision.get("arguments", {})
                
                if tool_name not in tools_map:
                    messages.append(f"System: Tool {tool_name} does not exist.")
                    continue
                
                print(f"Executing: {tool_name}...")
                result = await db_session.call_tool(tool_name, arguments=args)
                tool_output = result.content[0].text
                
                messages.append(f"Tool '{tool_name}' Result:\n{tool_output}")
            except Exception as e:
                print(f"Error in Agent Loop: {e}")
                break
        return None

    async def process_single_email(self, bucket, blob_path):
        """Processes a single email from GCS."""
        print(f"Processing: gs://{bucket}/{blob_path}")
        
        # Local path for artifacts (in container)
        # Use /tmp for temporary storage or a dedicated artifacts dir
        base_name = os.path.basename(blob_path)
        folder_name = os.path.splitext(base_name)[0]
        artifacts_dir = f"/tmp/artifacts/{folder_name}"
        os.makedirs(artifacts_dir, exist_ok=True)
        
        json_file_path = os.path.join(artifacts_dir, base_name)
        
        # Download
        download_blob(bucket, blob_path, json_file_path)
        
        if not os.path.exists(json_file_path):
            raise Exception("Failed to download JSON file")

        doc_session = self.sessions.get("doc_server")
        if not doc_session: raise Exception("doc_server not connected")

        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        category = data.get("category", "NONE")
        if category not in ["RETURN", "REPLACEMENT", "REFUND"]:
             print(f"Skipping category: {category}")
             return

        combined_text = f"""
        --- EMAIL METADATA ---
        Sender: {data.get('user_id')}
        Received: {data.get('received_at')}
        Category: {category}
        Body: {data.get('email_body','')}
        """
        
        # Process attachments
        attachments = data.get("attachments", [])
        for attachment in attachments:
            filename = attachment.get("filename", "")
            if filename.lower().endswith(".pdf"):
                file_data = attachment.get("data", "")
                if isinstance(file_data, dict): file_data = file_data.get("data", "")
                if file_data:
                    txt_path = os.path.join(artifacts_dir, f"{filename}.txt")
                    parse_result = await doc_session.call_tool(
                        "process_invoice",
                        arguments={"base64_content": file_data, "output_txt_path": txt_path}
                    )
                    combined_text += f"\n\n--- INVOICE {filename} ---\n{parse_result.content[0].text}"
            elif filename.lower().endswith((".jpg", ".png", ".jpeg", ".webp")):
                 defect_session = self.sessions.get("defect_analyzer")
                 if defect_session:
                     file_data = attachment.get("data", "")
                     if isinstance(file_data, dict): file_data = file_data.get("data", "")
                     if file_data:
                         result = await defect_session.call_tool("analyze_defect_image", arguments={"image_base64": file_data})
                         combined_text += f"\n\n--- IMAGE {filename} ---\n{result.content[0].text}"

        # Extract
        extraction_json = await self.extract_order_details(combined_text)
        try:
            extracted_data = json.loads(extraction_json)
        except:
            extracted_data = {}
        
        # Verify
        verified_record = await self.verify_request_with_db(extracted_data)
        
        # Adjudicate
        adjudication_result = None
        if verified_record:
            # Merge fields
            for k in ["return_request_date", "return_category", "return_reason", "item_condition"]:
                verified_record[k] = extracted_data.get(k)
            
            try:
                print("RUNNING ADJUDICATOR AGENT")
                adjudicator = Adjudicator()
                adjudication_result = await adjudicator.adjudicate(verified_record)
                
                print(f"DECISION: {adjudication_result.get('decision', 'UNKNOWN')}")
                print(f"REASON: {adjudication_result.get('details', {}).get('reasoning', 'N/A')}")
                
            except Exception as e:
                print(f"⚠️ Adjudication failed: {e}")
                import traceback
                traceback.print_exc()
                # Adjudication result remains None, so we proceed to insert without it, same as client.py
        
        else:
            print("ℹ️ No verified order data was returned. Marking as PENDING_REVIEW.")

        # Insert to DB (Always insert, with or without verified_record/adjudication_result)
        self.insert_refund_case(
            email_data=data,
            extracted_data=extracted_data,
            verified_record=verified_record,
            adjudication_result=adjudication_result
        )
        
        print("Processing Complete.")

    async def cleanup(self):
        await self.exit_stack.aclose()
