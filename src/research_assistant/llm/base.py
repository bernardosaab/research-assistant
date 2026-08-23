from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass
class ToolDef:
    name: str
    description: str
    input_schema: dict


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class LLMMessage:
    role: Literal["user", "assistant"]
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class LLMUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class LLMResponse:
    text: str | None
    tool_calls: list[ToolCall]
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "other"]
    usage: LLMUsage
    raw: Any = None


class LLMClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        tools: list[ToolDef] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse: ...
