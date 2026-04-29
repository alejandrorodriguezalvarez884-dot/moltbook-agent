from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    moltbook_api_key: str
    moltbook_base_url: str = "https://www.moltbook.com/api/v1"

    anthropic_api_key: str

    agent_name: str = "MoltAgent"
    agent_description: str = "An AI agent participating in the Moltbook ecosystem"
    target_submolts: str = "general,agents,aitools"

    gcp_project_id: str = ""

    model_config = {"env_file": ".env"}

    @property
    def submolts_list(self) -> list[str]:
        return [s.strip() for s in self.target_submolts.split(",") if s.strip()]


settings = Settings()
