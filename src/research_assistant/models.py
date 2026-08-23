from typing import Literal

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    query: str
    url: str
    title: str
    content: str
    score: float | None = None
    raw_content: str | None = None


class Source(BaseModel):
    id: int
    url: str
    title: str


class SubQuestion(BaseModel):
    id: str
    text: str
    status: Literal["pending", "in_progress", "done"] = "pending"
    findings: str | None = None
    search_results: list[SearchResult] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    topic: str
    sub_questions: list[SubQuestion]


class Brief(BaseModel):
    topic: str
    markdown: str
    sources: list[Source]


class Triple(BaseModel):
    subject: str
    relation: str
    object: str
    source_url: str
