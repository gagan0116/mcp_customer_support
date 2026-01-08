# db_verification/db_verification_server.py
from __future__ import annotations

from typing import Any, Dict, List

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

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



if __name__ == "__main__":
    mcp.run(transport="stdio")