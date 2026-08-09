from abc import ABC, abstractmethod

import httpx

from zubepredict_core.shared.config import Settings

SYSTEM_PROMPT = """You are the explanation layer for ZubePredict AI.
Never invent data, metrics, columns, results, or model performance.
Explain only the verified structured evidence provided by the application.
If evidence is insufficient, clearly request clarification.
Return concise, plain language suitable for a learner.
"""


class LLMClient(ABC):
    @abstractmethod
    async def explain(self, evidence: str, question: str) -> str: ...


class TemplateClient(LLMClient):
    async def explain(self, evidence: str, question: str) -> str:
        return (
            f"ZubePredict used verified analysis results. {question}\n\nEvidence: {evidence[:1200]}"
        )


class OpenAICompatibleClient(LLMClient):
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def explain(self, evidence: str, question: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Question: {question}\nVerified evidence:\n{evidence}",
                },
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions", headers=headers, json=payload
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("The language model returned non-text content.")
            return content


def create_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "openrouter":
        return OpenAICompatibleClient(
            "https://openrouter.ai/api/v1",
            settings.openrouter_api_key,
            settings.openrouter_model,
            settings.llm_timeout_seconds,
        )
    if settings.llm_provider == "ollama":
        return OpenAICompatibleClient(
            f"{settings.ollama_base_url}/v1",
            "ollama",
            settings.ollama_model,
            settings.llm_timeout_seconds,
        )
    return TemplateClient()
