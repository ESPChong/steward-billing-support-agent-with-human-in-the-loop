import os

from app.config import settings


def configure_langsmith() -> None:
    """Export LangSmith env vars for this process; keep CI / $0 mode clean."""
    if settings.langsmith_tracing and settings.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    else:
        os.environ.pop("LANGSMITH_TRACING", None)


def get_chat_model(temperature: float = 0.2, json_mode: bool = False):
    if settings.fake_model:
        from app.fake_model import FakeChatModel

        return FakeChatModel()
    from langchain_ollama import ChatOllama

    kwargs = {"format": "json"} if json_mode else {}
    return ChatOllama(
        model=settings.chat_model,
        base_url=settings.ollama_base_url,
        temperature=temperature,
        **kwargs,
    )


def get_embeddings():
    if settings.fake_model:
        from app.fake_model import DeterministicEmbeddings

        return DeterministicEmbeddings(dim=768)  # nomic-embed-text dim
    from langchain_ollama import OllamaEmbeddings

    return OllamaEmbeddings(model=settings.embed_model, base_url=settings.ollama_base_url)