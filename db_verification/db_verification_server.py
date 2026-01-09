# db_verification/db_verification_server.py
from __future__ import annotations

from typing import Any, Dict, List

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import os
import json
from google import genai
from google.genai import types

# IMPORTANT: load .env BEFORE importing db.py (db.py reads env at import time)
load_dotenv()

from .db import db_connection, rows_as_dicts  # noqa: E402

mcp = FastMCP("db_verification")


_ORDER_SELECT_COLUMNS = """
    o.order_id::text            AS order_id,
    o.invoice_number            AS invoice_number,
    o.order_invoice_id          AS order_invoice_id,
    o.customer_id::text         AS customer_id,
    o.order_date                AS order_date,
    o.order_state               AS order_state,
    o.currency                  AS currency,
    o.subtotal_amount           AS subtotal_amount,
    o.discount_amount           AS discount_amount,
    o.shipping_amount           AS shipping_amount,
    o.total_amount              AS total_amount,
    o.balance_due               AS balance_due,
    o.refunded_amount           AS refunded_amount,
    o.ship_mode                 AS ship_mode,
    o.ship_city                 AS ship_city,
    o.ship_state                AS ship_state,
    o.ship_country              AS ship_country,
    o.delivered_at              AS delivered_at,
    o.created_at                AS created_at,
    o.updated_at                AS updated_at
"""

_ORDER_ITEM_SELECT_COLUMNS = """
    oi.order_item_id::text      AS order_item_id,
    oi.order_id::text           AS order_id,
    oi.sku                      AS sku,
    oi.item_name                AS item_name,
    oi.category                 AS category,
    oi.subcategory              AS subcategory,
    oi.quantity                 AS quantity,
    oi.unit_price               AS unit_price,
    oi.line_total               AS line_total,
    oi.refunded_qty             AS refunded_qty,
    oi.returned_qty             AS returned_qty,
    oi.metadata                 AS metadata
"""

_CUSTOMER_SELECT_COLUMNS = """
    c.customer_id::text AS customer_id,
    c.customer_email    AS customer_email,
    c.full_name         AS full_name,
    c.phone             AS phone,
    c.created_at        AS created_at
"""


@mcp.tool()
def list_orders_by_customer_email(customer_email: str, limit: int = 20) -> Dict[str, Any]:
    """List orders for a given customer email (case-insensitive)."""
    if not customer_email or not customer_email.strip():
        return {"customer_email": customer_email, "count": 0, "orders": [], "error": "customer_email is required"}

    limit = max(1, min(int(limit), 100))
    email = customer_email.strip()

    sql = f"""
        SELECT
            {_ORDER_SELECT_COLUMNS}
        FROM customers c
        JOIN orders o
          ON o.customer_id = c.customer_id
        WHERE lower(c.customer_email) = lower(%s)
        ORDER BY
            o.order_date DESC NULLS LAST,
            o.created_at DESC
        LIMIT %s;
    """

    try:
        with db_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql, (email, limit))
                orders: List[Dict[str, Any]] = rows_as_dicts(cur)
            finally:
                cur.close()
        return {"customer_email": email, "count": len(orders), "orders": orders}
    except Exception as e:
        return {"customer_email": email, "count": 0, "orders": [], "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def find_order_by_invoice_number(invoice_number: str) -> Dict[str, Any]:
    """Find a single order by invoice number (exact match)."""
    if not invoice_number or not invoice_number.strip():
        return {"invoice_number": invoice_number, "found": False, "order": None, "error": "invoice_number is required"}

    inv = invoice_number.strip()

    sql = f"""
        SELECT
            {_ORDER_SELECT_COLUMNS}
        FROM orders o
        WHERE o.invoice_number = %s
        LIMIT 1;
    """

    try:
        with db_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql, (inv,))
                rows = rows_as_dicts(cur)
            finally:
                cur.close()
        order = rows[0] if rows else None
        return {"invoice_number": inv, "found": order is not None, "order": order}
    except Exception as e:
        return {"invoice_number": inv, "found": False, "order": None, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def find_order_by_order_invoice_id(order_invoice_id: str) -> Dict[str, Any]:
    """Find a single order by order_invoice_id (exact match)."""
    if not order_invoice_id or not order_invoice_id.strip():
        return {
            "order_invoice_id": order_invoice_id,
            "found": False,
            "order": None,
            "error": "order_invoice_id is required",
        }

    oid = order_invoice_id.strip()

    sql = f"""
        SELECT
            {_ORDER_SELECT_COLUMNS}
        FROM orders o
        WHERE o.order_invoice_id = %s
        LIMIT 1;
    """

    try:
        with db_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql, (oid,))
                rows = rows_as_dicts(cur)
            finally:
                cur.close()
        order = rows[0] if rows else None
        return {"order_invoice_id": oid, "found": order is not None, "order": order}
    except Exception as e:
        return {"order_invoice_id": oid, "found": False, "order": None, "error": f"{type(e).__name__}: {e}"}


@mcp.tool()
def list_order_items_by_order_invoice_id(order_invoice_id: str, limit: int = 200) -> Dict[str, Any]:
    """
    List order items for a given order_invoice_id (exact match).

    Args:
        order_invoice_id: The order invoice id to search for (orders.order_invoice_id).
        limit: Safety cap on number of items returned (default 200, capped at 500).

    Returns:
        Dict with order_invoice_id, resolved order_id (if found), count, and order_items.
    """
    if not order_invoice_id or not order_invoice_id.strip():
        return {
            "order_invoice_id": order_invoice_id,
            "order_id": None,
            "count": 0,
            "order_items": [],
            "error": "order_invoice_id is required",
        }

    limit = max(1, min(int(limit), 500))
    oid = order_invoice_id.strip()

    sql = f"""
        SELECT
            o.order_id::text       AS order_id,
            o.order_invoice_id     AS order_invoice_id,
            { _ORDER_ITEM_SELECT_COLUMNS }
        FROM orders o
        JOIN order_items oi
          ON oi.order_id = o.order_id
        WHERE o.order_invoice_id = %s
        ORDER BY oi.item_name ASC, oi.sku ASC
        LIMIT %s;
    """

    try:
        with db_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql, (oid, limit))
                rows: List[Dict[str, Any]] = rows_as_dicts(cur)
            finally:
                cur.close()

        if not rows:
            return {"order_invoice_id": oid, "order_id": None, "count": 0, "order_items": []}

        # Extract order_id from first row, and strip it out of each item
        resolved_order_id = rows[0].get("order_id")
        order_items: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            item.pop("order_invoice_id", None)
            item.pop("order_id", None)  # keep order_id at top-level
            order_items.append(item)

        return {
            "order_invoice_id": oid,
            "order_id": resolved_order_id,
            "count": len(order_items),
            "order_items": order_items,
        }
    except Exception as e:
        return {
            "order_invoice_id": oid,
            "order_id": None,
            "count": 0,
            "order_items": [],
            "error": f"{type(e).__name__}: {e}",
        }
    
# -------------------
# VERIFICATION TOOLS
# -------------------

@mcp.tool()
def verify_from_email_matches_customer(from_email: str) -> Dict[str, Any]:
    """
    Verify whether the given from_email exists in customers.customer_email (exact match, case-insensitive).

    Args:
        from_email: The sender email address from a refund/return email.

    Returns:
        Dict with matched flag and basic customer info if matched.
    """
    if not from_email or not from_email.strip():
        return {"from_email": from_email, "matched": False, "customer": None, "error": "from_email is required"}

    email = from_email.strip()

    sql = f"""
        SELECT
            {_CUSTOMER_SELECT_COLUMNS}
        FROM customers c
        WHERE lower(c.customer_email) = lower(%s)
        LIMIT 1;
    """

    try:
        with db_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql, (email,))
                rows = rows_as_dicts(cur)
            finally:
                cur.close()

        customer = rows[0] if rows else None
        return {"from_email": email, "matched": customer is not None, "customer": customer}
    except Exception as e:
        return {"from_email": email, "matched": False, "customer": None, "error": f"{type(e).__name__}: {e}"}
    

@mcp.tool()
def get_customer_orders_with_items(
    customer_email: str,
    max_orders: int = 50,
    max_items_per_order: int = 50,
    include_item_metadata: bool = False,
) -> Dict[str, Any]:
    """
    Fallback retrieval tool:
    Given only a customer email, return customer + (orders -> items) so an LLM can pick the relevant order.

    Notes:
    - No timeframe filtering.
    - Soft caps to avoid huge payloads as the DB grows.
    - By default, item metadata is excluded (can be large).
    """
    if not customer_email or not customer_email.strip():
        return {
            "customer_email": customer_email,
            "found_customer": False,
            "customer": None,
            "orders_count": 0,
            "orders": [],
            "error": "customer_email is required",
        }

    email = customer_email.strip()
    max_orders = max(1, min(int(max_orders), 200))
    max_items_per_order = max(1, min(int(max_items_per_order), 500))

    customer_sql = f"""
        SELECT
            {_CUSTOMER_SELECT_COLUMNS}
        FROM customers c
        WHERE lower(c.customer_email) = lower(%s)
        LIMIT 1;
    """

    # "All orders" (no timeframe), still ordered for usefulness
    orders_sql = """
        SELECT
            o.order_id::text       AS order_id,
            o.order_invoice_id     AS order_invoice_id,
            o.invoice_number       AS invoice_number,
            o.customer_id::text    AS customer_id,
            o.order_date           AS order_date,
            o.order_state          AS order_state,
            o.currency             AS currency,
            o.subtotal_amount      AS subtotal_amount,
            o.discount_amount      AS discount_amount,
            o.shipping_amount      AS shipping_amount,
            o.total_amount         AS total_amount,
            o.balance_due          AS balance_due,
            o.refunded_amount      AS refunded_amount,
            o.ship_mode            AS ship_mode,
            o.ship_city            AS ship_city,
            o.ship_state           AS ship_state,
            o.ship_country         AS ship_country,
            o.delivered_at         AS delivered_at
        FROM orders o
        WHERE o.customer_id = %s::uuid
        ORDER BY
            o.order_date DESC NULLS LAST,
            o.created_at DESC
        LIMIT %s;
    """

    # Optionally include per-item metadata
    item_cols = """
        oi.order_item_id::text AS order_item_id,
        oi.order_id::text      AS order_id,
        oi.sku                 AS sku,
        oi.item_name           AS item_name,
        oi.category            AS category,
        oi.subcategory         AS subcategory,
        oi.quantity            AS quantity,
        oi.unit_price          AS unit_price,
        oi.line_total          AS line_total,
        oi.refunded_qty        AS refunded_qty,
        oi.returned_qty        AS returned_qty
    """
    if include_item_metadata:
        item_cols += ", oi.metadata AS metadata"

    try:
        with db_connection() as conn:
            # 1) Fetch customer
            cur = conn.cursor()
            try:
                cur.execute(customer_sql, (email,))
                customer_rows = rows_as_dicts(cur)
            finally:
                cur.close()

            if not customer_rows:
                return {
                    "customer_email": email,
                    "found_customer": False,
                    "customer": None,
                    "orders_count": 0,
                    "orders": [],
                }

            customer = customer_rows[0]
            customer_id = customer["customer_id"]

            # 2) Fetch orders (no timeframe)
            cur = conn.cursor()
            try:
                cur.execute(orders_sql, (customer_id, max_orders))
                orders = rows_as_dicts(cur)
            finally:
                cur.close()

            if not orders:
                return {
                    "customer_email": email,
                    "found_customer": True,
                    "customer": customer,
                    "orders_count": 0,
                    "orders": [],
                }

            # 3) Fetch all items for these orders in one query (IN clause)
            order_ids = [o["order_id"] for o in orders]
            placeholders = ",".join(["%s"] * len(order_ids))

            items_sql = f"""
                SELECT
                    {item_cols}
                FROM order_items oi
                WHERE oi.order_id IN ({placeholders})
                ORDER BY oi.order_id, oi.item_name ASC, oi.sku ASC;
            """

            cur = conn.cursor()
            try:
                cur.execute(items_sql, tuple(order_ids))
                items_rows = rows_as_dicts(cur)
            finally:
                cur.close()

        # 4) Group items by order_id and apply per-order cap
        items_by_order: Dict[str, List[Dict[str, Any]]] = {}
        for r in items_rows:
            oid = r["order_id"]
            items_by_order.setdefault(oid, []).append(r)

        orders_out: List[Dict[str, Any]] = []
        items_truncated_any = False

        for o in orders:
            oid = o["order_id"]
            items = items_by_order.get(oid, [])

            if len(items) > max_items_per_order:
                items_truncated_any = True
                items = items[:max_items_per_order]

            # remove redundant order_id inside each item (kept at order level)
            cleaned_items: List[Dict[str, Any]] = []
            for it in items:
                it2 = dict(it)
                it2.pop("order_id", None)
                cleaned_items.append(it2)

            orders_out.append(
                {
                    **o,
                    "items_count": len(cleaned_items),
                    "items": cleaned_items,
                }
            )

        return {
            "customer_email": email,
            "found_customer": True,
            "customer": customer,
            "orders_count": len(orders_out),
            "orders_truncated": len(orders) >= max_orders,
            "items_truncated": items_truncated_any,
            "orders": orders_out,
        }

    except Exception as e:
        return {
            "customer_email": email,
            "found_customer": False,
            "customer": None,
            "orders_count": 0,
            "orders": [],
            "error": f"{type(e).__name__}: {e}",
        }
    
@mcp.tool()
def select_order_id(
    customer_orders_payload: Dict[str, Any],
    email_info: Dict[str, Any],
    model: str = "gemini-2.0-flash",
) -> Dict[str, Any]:
    """
    Use LLM to pick the most relevant order_id given:
      - customer_orders_payload (output of get_customer_orders_with_items)
      - email_info (your extracted JSON from the email)

    Returns a JSON dict like:
    {
      "selected_order_id": str|None,
      "confidence": float,
      "reason": str,
      "candidates": [{"order_id": str, "reason": str}]
    }
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {
            "selected_order_id": None,
            "confidence": 0.0,
            "reason": "Missing GEMINI_API_KEY in environment",
            "candidates": [],
            "error": "missing_api_key",
        }

    orders = customer_orders_payload.get("orders") if isinstance(customer_orders_payload, dict) else None
    if not orders or not isinstance(orders, list):
        return {
            "selected_order_id": None,
            "confidence": 0.0,
            "reason": "customer_orders_payload has no 'orders' list to choose from",
            "candidates": [],
            "error": "no_orders",
        }

    prompt = f"""
You are selecting the most likely order for a customer support request.

Context:
We are using this selection step ONLY because the email did NOT contain a usable invoice number or order_invoice_id.
So you MUST NOT rely on those identifiers.

You are given two JSON objects:

1) customer_orders_payload:
- Contains customer info and a list of orders.
- Each order includes a list of items.

2) email_info:
- Extracted/structured info from the customer's email.
- It may include item names, SKUs, quantities, amounts, currency, shipping location, and date hints.
- It does NOT include a reliable invoice number or order_invoice_id.

Task:
Choose the SINGLE best matching order from customer_orders_payload using only non-identifier details such as:
- item names / SKUs / categories
- quantities
- mentioned amount vs order total (allow small tolerance)
- shipping city/state/country (if mentioned)
- order recency hints in the email (e.g., "last week", "recent order") using order_date/delivered_at as context

Important rules:
- Prefer matches with clear item/SKU overlap.
- If multiple orders seem plausible, do NOT guess. Return up to 3 candidates.
- If there is not enough evidence to choose, set selected_order_id to null.

Return ONLY valid JSON in exactly this schema (no extra text):
{{
  "selected_order_id": string | null,
  "confidence": number,   // 0 to 1
  "reason": string,
  "candidates": [
    {{"order_id": string, "reason": string}}
  ]
}}

customer_orders_payload:
{json.dumps(customer_orders_payload, default=str)}

email_info:
{json.dumps(email_info, default=str)}
""".strip()


    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )

        text = (resp.text or "").strip()
        if not text:
            return {
                "selected_order_id": None,
                "confidence": 0.0,
                "reason": "Gemini returned empty response",
                "candidates": [],
                "error": "empty_model_response",
            }

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            return {
                "selected_order_id": None,
                "confidence": 0.0,
                "reason": "Gemini returned non-JSON output",
                "candidates": [],
                "error": "non_json_model_response",
                "raw_model_text": text[:2000],
            }

        # Minimal validation / normalization
        if not isinstance(result, dict):
            return {
                "selected_order_id": None,
                "confidence": 0.0,
                "reason": "Gemini returned JSON but not an object",
                "candidates": [],
                "error": "bad_json_shape",
                "raw_model_json": result,
            }

        result.setdefault("selected_order_id", None)
        result.setdefault("confidence", 0.0)
        result.setdefault("reason", "")
        result.setdefault("candidates", [])

        return result

    except Exception as e:
        return {
            "selected_order_id": None,
            "confidence": 0.0,
            "reason": f"{type(e).__name__}: {e}",
            "candidates": [],
            "error": "gemini_call_failed",
        }
    
@mcp.tool()
def llm_find_orders(email_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use Gemini to generate a safe SELECT query (schema + email_info) and execute it.
    Returns candidate rows for human review.
    """
    from db_verification.llm_sql_runner import llm_generate_and_execute  # local import to avoid import-time issues

    return llm_generate_and_execute(email_info=email_info)

if __name__ == "__main__":
    mcp.run(transport="stdio")