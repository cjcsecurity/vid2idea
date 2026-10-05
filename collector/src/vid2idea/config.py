import os
from pathlib import Path
from pydantic import BaseModel, Field, SecretStr
from typing import Literal
from dotenv import load_dotenv


class Settings(BaseModel):
    publishing_backend: Literal['supabase', 'notion'] = 'notion'
    notion_api_token: SecretStr = SecretStr('')
    notion_library_database_id: str = ''
    notion_library_data_source_id: str = ''
    notion_projects_data_source_id: str = ''
    notion_vid2idea_project_page_id: str = ''
    discord_token: SecretStr = SecretStr('')
    discord_channel_id: str = Field(default='', pattern=r'^(\d{17,20})?$')
    discord_author_id: str = Field(default='', pattern=r'^(\d{17,20})?$')
    supabase_url: str = ''
    supabase_secret_key: SecretStr = SecretStr('')
    owner_id: str = ''
    ai_base_url: str = ''
    ai_api_key: SecretStr = SecretStr('')
    ai_model: str = ''
    ai_vision_model: str = ''
    ai_provider: Literal['codex', 'openai'] = 'codex'
    codex_command: str = 'codex'
    codex_model: str = ''
    whisper_model: str = 'small'
    project_roots: str = ''
    github_owner: str = Field(default='', pattern=r'^[A-Za-z0-9-]*$')
    brief_context: str = Field(default='', max_length=4000)
    data_dir: Path = Path('.collector-data')
    max_video_seconds: int = Field(default=600, ge=1, le=600)
    max_download_bytes: int = Field(default=200 * 1024 * 1024, ge=1, le=200 * 1024 * 1024)

    @classmethod
    def from_env(cls):
        load_dotenv()
        return cls(**{name: os.environ[name.upper()] for name in cls.model_fields if name.upper() in os.environ})

    def missing(self, discord=True):
        names = (['notion_api_token','notion_library_data_source_id','notion_projects_data_source_id','notion_vid2idea_project_page_id']
                 if self.publishing_backend == 'notion' else ['supabase_url', 'supabase_secret_key', 'owner_id'])
        if discord:
            names += ['discord_token', 'discord_channel_id']
        return [n.upper() for n in names if not (getattr(self, n).get_secret_value() if isinstance(getattr(self, n), SecretStr) else getattr(self, n))]

    @property
    def ai_configured(self):
        if self.ai_provider == 'codex':
            import shutil
            return bool(shutil.which(self.codex_command))
        return bool(self.ai_base_url and self.ai_model)
