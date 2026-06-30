from pydantic import BaseModel, Field
from typing import List, Optional


class ProductStat(BaseModel):
    product: str = Field(..., description="Token or term extracted from message text")
    count: int = Field(..., description="Number of messages mentioning this term")


class TopProductsResponse(BaseModel):
    items: List[ProductStat]


class ChannelActivityStat(BaseModel):
    date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    message_count: int
    view_sum: int
    forward_sum: int


class ChannelActivityResponse(BaseModel):
    channel_name: str
    activity: List[ChannelActivityStat]


class MessageRecord(BaseModel):
    message_id: int
    channel_name: str
    message_date: str
    message_text: str
    view_count: int
    forward_count: int
    has_image: bool


class MessageSearchResponse(BaseModel):
    query: str
    results: List[MessageRecord]


class VisualContentStat(BaseModel):
    channel_name: str
    total_messages: int
    messages_with_images: int
    visual_pct: float = Field(..., description="Percentage of messages with images")
    top_image_category: Optional[str] = None


class VisualContentResponse(BaseModel):
    stats: List[VisualContentStat]
