from typing import Protocol

from research_assistant.llm.base import ToolDef


class Tool(Protocol):
    name: str
    description: str
    input_schema: dict

    def run(self, **kwargs) -> str: ...

    def as_tooldef(self) -> ToolDef: ...
