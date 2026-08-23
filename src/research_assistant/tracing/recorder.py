import time

from pydantic import BaseModel

from research_assistant.llm.base import LLMUsage


class RunTrace(BaseModel):
    variant: str
    topic: str
    duration_seconds: float
    llm_calls: int
    search_calls: int
    input_tokens: int
    output_tokens: int


class RunRecorder:
    def __init__(self, variant: str, topic: str) -> None:
        self._variant = variant
        self._topic = topic
        self._started_at = time.monotonic()
        self._llm_calls = 0
        self._search_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0

    def record_llm_call(self, usage: LLMUsage) -> None:
        self._llm_calls += 1
        self._input_tokens += usage.input_tokens
        self._output_tokens += usage.output_tokens

    def record_tool_call(self, tool_name: str) -> None:
        if tool_name == "web_search":
            self._search_calls += 1

    def finalize(self) -> RunTrace:
        return RunTrace(
            variant=self._variant,
            topic=self._topic,
            duration_seconds=time.monotonic() - self._started_at,
            llm_calls=self._llm_calls,
            search_calls=self._search_calls,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
        )
