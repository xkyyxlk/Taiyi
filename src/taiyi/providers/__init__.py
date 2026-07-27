from taiyi.config import Settings
from taiyi.providers.base import ModelProvider
from taiyi.providers.mock import MockProvider
from taiyi.providers.openai import OpenAIProvider
from taiyi.storage import TaiyiError


def create_provider(settings: Settings) -> ModelProvider:
    if settings.provider == "mock":
        return MockProvider()
    if settings.provider == "openai":
        return OpenAIProvider(settings.openai_model)
    raise TaiyiError(f"unsupported provider: {settings.provider}")


__all__ = ["MockProvider", "ModelProvider", "OpenAIProvider", "create_provider"]
