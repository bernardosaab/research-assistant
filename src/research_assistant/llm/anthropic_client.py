import anthropic

from research_assistant.llm.base import (
    LLMMessage,
    LLMResponse,
    LLMUsage,
    ToolCall,
    ToolDef,
)


class AnthropicLLMClient:
    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        tools: list[ToolDef] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [_to_anthropic_message(m) for m in messages],
        }
        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]

        response = self._client.messages.create(**kwargs)
        return _from_anthropic_response(response)


def _to_anthropic_message(message: LLMMessage) -> dict:
    if message.tool_results:
        return {
            "role": message.role,
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tr.tool_call_id,
                    "content": tr.content,
                    "is_error": tr.is_error,
                }
                for tr in message.tool_results
            ],
        }
    if message.tool_calls:
        content: list[dict] = []
        if message.text:
            content.append({"type": "text", "text": message.text})
        content.extend(
            {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
            for tc in message.tool_calls
        )
        return {"role": message.role, "content": content}
    return {"role": message.role, "content": message.text or ""}


def _from_anthropic_response(response: anthropic.types.Message) -> LLMResponse:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))

    stop_reason = (
        response.stop_reason
        if response.stop_reason in ("end_turn", "tool_use", "max_tokens")
        else "other"
    )

    return LLMResponse(
        text="\n".join(text_parts) if text_parts else None,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        usage=LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        ),
        raw=response,
    )
