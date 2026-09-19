from typing import List

from pydantic import BaseModel, Field


class PaperIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    topics: List[str] = []
    required_reviews: int = Field(default=2, ge=1, le=20)


class ReviewerIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    topics: List[str] = []
    capacity: int = Field(default=3, ge=0, le=100)


class ConflictIn(BaseModel):
    paper_id: int
    reviewer_id: int


class SolveParams(BaseModel):
    mismatch_penalty: int = Field(default=10, ge=0, le=10000)
    load_weight: int = Field(default=1, ge=0, le=10000)


class LockIn(BaseModel):
    locked: bool
