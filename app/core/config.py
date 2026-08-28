from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Jaycode"
    app_env: str = "dev"
    max_scan_files: int = 800
    max_file_preview_chars: int = 4000
    openai_api_key: str = ""
    openai_base_url: str = ""
    jaycode_agent_llm_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias="JAYCODE_AGENT_LLM",
    )
    jaycode_memory_extractor: str = Field(
        default="rule",
        validation_alias="JAYCODE_MEMORY_EXTRACTOR",
    )
    jaycode_rag_store: str = Field(
        default="sqlite",
        validation_alias="JAYCODE_RAG_STORE",
    )
    jaycode_rag_reranker: str = Field(
        default="off",
        validation_alias="JAYCODE_RAG_RERANKER",
    )
    pgvector_database_url: str = ""
    database_url: str = ""
    jaycode_embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias="JAYCODE_EMBEDDING_MODEL",
    )
    jaycode_embedding_dim: int = Field(
        default=1536,
        validation_alias="JAYCODE_EMBEDDING_DIM",
    )
    jaycode_mcp_provider: str = Field(
        default="local",
        validation_alias="JAYCODE_MCP_PROVIDER",
    )
    jaycode_skill_sandbox: str = Field(
        default="subprocess",
        validation_alias="JAYCODE_SKILL_SANDBOX",
    )
    jaycode_skill_sandbox_image: str = Field(
        default="python:3.13-slim",
        validation_alias="JAYCODE_SKILL_SANDBOX_IMAGE",
    )
    jaycode_skill_sandbox_memory: str = Field(
        default="256m",
        validation_alias="JAYCODE_SKILL_SANDBOX_MEMORY",
    )
    jaycode_skill_sandbox_cpus: str = Field(
        default="0.5",
        validation_alias="JAYCODE_SKILL_SANDBOX_CPUS",
    )
    jaycode_skill_sandbox_pids_limit: int = Field(
        default=64,
        validation_alias="JAYCODE_SKILL_SANDBOX_PIDS_LIMIT",
    )
    jaycode_skill_sandbox_fallback: bool = Field(
        default=False,
        validation_alias="JAYCODE_SKILL_SANDBOX_FALLBACK",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
