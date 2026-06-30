import os
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Import DB session helper
from .database import engine

app = FastAPI(title="Medical Telegram Analytical API",
              description="Endpoints for top products, channel activity, message search, and visual content statistics.",
              version="0.1.0")

# ----- Pydantic response models -----
class ProductStat(BaseModel):
    product: str
    count: int

class ChannelActivityStat(BaseModel):
    date: str  # ISO date string
    message_count: int
    view_sum: int
    forward_sum: int

class MessageRecord(BaseModel):
    message_id: int
    channel_name: str
    message_date: str
    message_text: str
    view_count: int
    forward_count: int
    has_image: bool

class VisualContentStat(BaseModel):
    image_category: str
    count: int
    avg_confidence: Optional[float] = None

# ----- Helper -----
def execute_query(sql: str, params: dict = None):
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql), params or {})
            return result.fetchall()
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=str(e))

# ----- Endpoints -----
@app.get("/api/reports/top-products", response_model=List[ProductStat])
def get_top_products(limit: int = Query(10, gt=0, le=100)):
    """Return the most frequently mentioned product terms across all messages.
    Simple tokenisation on whitespace; in a real system you would use a product taxonomy.
    """
    sql = """
        SELECT lower(trim(word)) AS product, COUNT(*) AS count
        FROM (
            SELECT unnest(string_to_array(message_text, ' ')) AS word
            FROM {{ ref('fct_messages') }}
        ) sub
        GROUP BY product
        ORDER BY count DESC
        LIMIT :limit
    """
    rows = execute_query(sql, {"limit": limit})
    return [ProductStat(product=row[0], count=row[1]) for row in rows]

@app.get("/api/channels/{channel_name}/activity", response_model=List[ChannelActivityStat])
def get_channel_activity(channel_name: str):
    """Daily activity metrics for a given channel.
    Returns date, message count, sum of views and forwards.
    """
    sql = """
        SELECT d.full_date::text AS date,
               COUNT(m.message_id) AS message_count,
               SUM(m.view_count) AS view_sum,
               SUM(m.forward_count) AS forward_sum
        FROM {{ ref('fct_messages') }} m
        JOIN {{ ref('dim_dates') }} d ON m.date_key = d.date_key
        JOIN {{ ref('dim_channels') }} c ON m.channel_key = c.channel_key
        WHERE lower(c.channel_name) = lower(:channel_name)
        GROUP BY d.full_date
        ORDER BY d.full_date;
    """
    rows = execute_query(sql, {"channel_name": channel_name})
    return [ChannelActivityStat(date=row[0], message_count=row[1], view_sum=row[2] or 0, forward_sum=row[3] or 0) for row in rows]

@app.get("/api/search/messages", response_model=List[MessageRecord])
def search_messages(query: str = Query(..., min_length=1), limit: int = Query(20, gt=0, le=100)):
    """Keyword search across message_text.
    Simple ILIKE pattern match.
    """
    pattern = f"%{query}%"
    sql = """
        SELECT message_id, channel_name, message_date::text, message_text,
               view_count, forward_count, has_image
        FROM {{ ref('fct_messages') }}
        WHERE message_text ILIKE :pattern
        ORDER BY message_date DESC
        LIMIT :limit;
    """
    rows = execute_query(sql, {"pattern": pattern, "limit": limit})
    return [MessageRecord(message_id=row[0], channel_name=row[1], message_date=row[2],
                          message_text=row[3], view_count=row[4], forward_count=row[5],
                          has_image=row[6]) for row in rows]

@app.get("/api/reports/visual-content", response_model=List[VisualContentStat])
def visual_content_stats():
    """Aggregate statistics on image categories detected by YOLO.
    Returns count per category and average confidence.
    """
    sql = """
        SELECT image_category, COUNT(*) AS count,
               AVG(confidence_score) AS avg_confidence
        FROM {{ ref('fct_image_detections') }}
        GROUP BY image_category;
    """
    rows = execute_query(sql)
    return [VisualContentStat(image_category=row[0], count=row[1], avg_confidence=row[2]) for row in rows]
