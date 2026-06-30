"""
Task 4 — FastAPI analytical endpoints over dbt marts.

Run:
    uvicorn api.main:app --reload --port 8000
    Open http://localhost:8000/docs
"""

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api.database import engine
from api.schemas import (
    ChannelActivityResponse,
    ChannelActivityStat,
    MessageRecord,
    MessageSearchResponse,
    ProductStat,
    TopProductsResponse,
    VisualContentResponse,
    VisualContentStat,
)

app = FastAPI(
    title="Medical Telegram Analytical API",
    description=(
        "REST API exposing dbt mart tables for medical Telegram channel analytics: "
        "top products, channel activity, message search, and visual content statistics."
    ),
    version="1.0.0",
)


def execute_query(sql: str, params: dict | None = None) -> list:
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            return result.fetchall()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/health")
def health_check():
    """Verify API and database connectivity."""
    execute_query("SELECT 1")
    return {"status": "ok"}


@app.get(
    "/api/reports/top-products",
    response_model=TopProductsResponse,
    summary="Top frequently mentioned product terms",
)
def get_top_products(limit: int = Query(10, gt=0, le=100, description="Max terms to return")):
    sql = """
        SELECT lower(trim(word)) AS product, COUNT(*) AS count
        FROM (
            SELECT unnest(regexp_split_to_array(message_text, '\\s+')) AS word
            FROM fct_messages
        ) AS tokens
        WHERE length(trim(word)) > 3
          AND trim(word) !~ '^[0-9.,]+'
        GROUP BY product
        ORDER BY count DESC, product ASC
        LIMIT :limit
    """
    rows = execute_query(sql, {"limit": limit})
    return TopProductsResponse(
        items=[ProductStat(product=row[0], count=row[1]) for row in rows]
    )


@app.get(
    "/api/channels/{channel_name}/activity",
    response_model=ChannelActivityResponse,
    summary="Daily posting activity for a channel",
)
def get_channel_activity(channel_name: str):
    sql = """
        SELECT
            d.full_date::text AS activity_date,
            COUNT(m.message_id) AS message_count,
            COALESCE(SUM(m.view_count), 0) AS view_sum,
            COALESCE(SUM(m.forward_count), 0) AS forward_sum
        FROM fct_messages AS m
        JOIN dim_dates AS d ON m.date_key = d.date_key
        JOIN dim_channels AS c ON m.channel_key = c.channel_key
        WHERE lower(c.channel_name) = lower(:channel_name)
        GROUP BY d.full_date
        ORDER BY d.full_date
    """
    rows = execute_query(sql, {"channel_name": channel_name})
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Channel '{channel_name}' not found or has no messages",
        )
    return ChannelActivityResponse(
        channel_name=channel_name,
        activity=[
            ChannelActivityStat(
                date=row[0],
                message_count=row[1],
                view_sum=int(row[2]),
                forward_sum=int(row[3]),
            )
            for row in rows
        ],
    )


@app.get(
    "/api/search/messages",
    response_model=MessageSearchResponse,
    summary="Search messages by keyword",
)
def search_messages(
    query: str = Query(..., min_length=1, description="Keyword to search in message text"),
    limit: int = Query(20, gt=0, le=100, description="Maximum results"),
):
    sql = """
        SELECT
            m.message_id,
            c.channel_name,
            d.full_date::text AS message_date,
            m.message_text,
            m.view_count,
            m.forward_count,
            m.has_image
        FROM fct_messages AS m
        JOIN dim_channels AS c ON m.channel_key = c.channel_key
        JOIN dim_dates AS d ON m.date_key = d.date_key
        WHERE m.message_text ILIKE :pattern
        ORDER BY d.full_date DESC, m.message_id DESC
        LIMIT :limit
    """
    rows = execute_query(sql, {"pattern": f"%{query}%", "limit": limit})
    return MessageSearchResponse(
        query=query,
        results=[
            MessageRecord(
                message_id=row[0],
                channel_name=row[1],
                message_date=row[2],
                message_text=row[3],
                view_count=row[4],
                forward_count=row[5],
                has_image=row[6],
            )
            for row in rows
        ],
    )


@app.get(
    "/api/reports/visual-content",
    response_model=VisualContentResponse,
    summary="Image usage statistics by channel",
)
def visual_content_stats():
    sql = """
        WITH channel_totals AS (
            SELECT
                c.channel_name,
                COUNT(*) AS total_messages,
                COUNT(*) FILTER (WHERE m.has_image) AS messages_with_images
            FROM fct_messages AS m
            JOIN dim_channels AS c ON m.channel_key = c.channel_key
            GROUP BY c.channel_name
        ),
        top_categories AS (
            SELECT DISTINCT ON (c.channel_name)
                c.channel_name,
                fid.image_category
            FROM fct_image_detections AS fid
            JOIN dim_channels AS c ON fid.channel_key = c.channel_key
            GROUP BY c.channel_name, fid.image_category
            ORDER BY c.channel_name, COUNT(*) DESC
        )
        SELECT
            ct.channel_name,
            ct.total_messages,
            ct.messages_with_images,
            ROUND(
                100.0 * ct.messages_with_images / NULLIF(ct.total_messages, 0),
                1
            ) AS visual_pct,
            tc.image_category
        FROM channel_totals AS ct
        LEFT JOIN top_categories AS tc ON ct.channel_name = tc.channel_name
        ORDER BY visual_pct DESC NULLS LAST, ct.channel_name
    """
    rows = execute_query(sql)
    return VisualContentResponse(
        stats=[
            VisualContentStat(
                channel_name=row[0],
                total_messages=row[1],
                messages_with_images=row[2],
                visual_pct=float(row[3] or 0),
                top_image_category=row[4],
            )
            for row in rows
        ]
    )
