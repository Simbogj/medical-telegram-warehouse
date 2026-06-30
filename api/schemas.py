from pydantic import BaseModel
from typing import List, Optional

class ProductCount(BaseModel):
    product: str
    count: int

class ChannelActivityRecord(BaseModel):
    date_key: int
    message_count: int

class MessageSearchResult(BaseModel):
    message_id: str
    message_text: str

class VisualContentStat(BaseModel):
    image_category: str
    count: int

class TopProductsResponse(BaseModel):
    top_products: List[ProductCount]

class ChannelActivityResponse(BaseModel):
    channel: str
    activity: List[ChannelActivityRecord]

class MessageSearchResponse(BaseModel):
    query: str
    results: List[MessageSearchResult]

class VisualContentResponse(BaseModel):
    stats: List[VisualContentStat]
