from pydantic import BaseModel, Field
from typing import Optional


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    thread_id: Optional[str] = None


class ResumeRequest(BaseModel):
    answer: str = Field(..., min_length=1)
    thread_id: str = Field(..., min_length=1)