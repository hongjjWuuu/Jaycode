from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Jaycode"
    app_env: str = "dev"
    max_scan_files: int = 800
    max_file_preview_chars: int = 4000
    jaycode_task_max_runtime_seconds: int = Field(default=900, validation_alias="JAYCODE_TASK_MAX_RUNTIME_SECONDS")
    jaycode_worker_supervisor_enabled: bool = Field(default=False, validation_alias="JAYCODE_WORKER_SUPERVISOR_ENABLED")
    jaycode_worker_supervisor_max_restarts: int = Field(default=5, validation_alias="JAYCODE_WORKER_SUPERVISOR_MAX_RESTARTS")
    jaycode_worker_count: int = Field(default=1, ge=1, le=16, validation_alias="JAYCODE_WORKER_COUNT")
    jaycode_llm_fallback_rate_threshold: float = Field(default=0.2, ge=0, le=1, validation_alias="JAYCODE_LLM_FALLBACK_RATE_THRESHOLD")
    jaycode_llm_schema_failure_rate_threshold: float = Field(default=0.05, ge=0, le=1, validation_alias="JAYCODE_LLM_SCHEMA_FAILURE_RATE_THRESHOLD")
    jaycode_llm_p95_latency_threshold_ms: int = Field(default=30000, ge=1, validation_alias="JAYCODE_LLM_P95_LATENCY_THRESHOLD_MS")
    jaycode_llm_alert_min_samples: int = Field(default=20, ge=1, validation_alias="JAYCODE_LLM_ALERT_MIN_SAMPLES")
    jaycode_persistence_store: str = Field(default="sqlite", validation_alias="JAYCODE_PERSISTENCE_STORE")
    jaycode_auth_enabled: bool = Field(default=True, validation_alias="JAYCODE_AUTH_ENABLED")
    jaycode_api_keys: str = Field(default="", validation_alias="JAYCODE_API_KEYS")
    jaycode_marketplace_remote_enabled: bool = Field(default=False, validation_alias="JAYCODE_MARKETPLACE_REMOTE_ENABLED")
    jaycode_marketplace_allowed_hosts: str = Field(default="", validation_alias="JAYCODE_MARKETPLACE_ALLOWED_HOSTS")
    jaycode_marketplace_require_signature: bool = Field(default=True, validation_alias="JAYCODE_MARKETPLACE_REQUIRE_SIGNATURE")
    jaycode_marketplace_max_download_bytes: int = Field(default=25 * 1024 * 1024, validation_alias="JAYCODE_MARKETPLACE_MAX_DOWNLOAD_BYTES")
    jaycode_marketplace_max_extracted_bytes: int = Field(default=100 * 1024 * 1024, validation_alias="JAYCODE_MARKETPLACE_MAX_EXTRACTED_BYTES")
    jaycode_marketplace_max_files: int = Field(default=1000, validation_alias="JAYCODE_MARKETPLACE_MAX_FILES")
    jaycode_external_skill_require_docker: bool = Field(default=True, validation_alias="JAYCODE_EXTERNAL_SKILL_REQUIRE_DOCKER")
    jaycode_mcp_allowed_commands: str = Field(default="", validation_alias="JAYCODE_MCP_ALLOWED_COMMANDS")
    jaycode_mcp_max_runtime_seconds: int = Field(default=15, validation_alias="JAYCODE_MCP_MAX_RUNTIME_SECONDS")
    jaycode_mcp_max_output_bytes: int = Field(default=1024 * 1024, validation_alias="JAYCODE_MCP_MAX_OUTPUT_BYTES")
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
