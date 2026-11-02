from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://steward:steward@localhost:5432/billing"
    checkpoint_db_url: str = "postgresql://steward:steward@localhost:5432/agent_checkpoints"
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "llama3.1:8b"
    embed_model: str = "nomic-embed-text"
    fake_model: bool = False
    refund_threshold_cents: int = 5000
    confidence_floor: float = 0.6
    max_revisions: int = 2
    agent_max_tool_rounds: int = 6
    policy_dir: str = "../docs/policies"
    chunk_size: int = 800
    chunk_overlap: int = 150
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "steward"

    model_config = {"env_file": ".env", "env_prefix": "AGENT_"}


settings = Settings()