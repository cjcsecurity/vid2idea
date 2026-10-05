import os
import io
import stat
from pathlib import Path
from pydantic import BaseModel, Field, SecretStr
from typing import Literal
from dotenv import dotenv_values


class ConfigurationError(ValueError):
    """Safe, actionable errors that never include configuration values."""


def read_environment_file(path: Path, *, required=False):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if not required:
            return {}
        raise ConfigurationError('Configuration file does not exist. Run vid2idea init first.') from None
    except OSError:
        raise ConfigurationError('Cannot read configuration. Use a regular private file, not a symlink.') from None
    with os.fdopen(descriptor, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ConfigurationError('Configuration must be owned by you and private. Run chmod 600 on the file.')
        content = handle.read(65537)
    if len(content) > 65536:
        raise ConfigurationError('Configuration file exceeds 64 KiB.')
    try:
        return dotenv_values(stream=io.StringIO(content.decode('utf-8')), interpolate=False)
    except UnicodeError:
        raise ConfigurationError('Configuration must use UTF-8 text.') from None


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
    def from_env(cls, env_file: Path | None = None):
        path = Path(env_file) if env_file is not None else Path.cwd() / '.env'
        values = {**read_environment_file(path, required=env_file is not None), **os.environ}
        settings = cls(**{name: values[name.upper()] for name in cls.model_fields if values.get(name.upper()) is not None})
        if not settings.data_dir.is_absolute():
            settings.data_dir = path.absolute().parent / settings.data_dir
        return settings

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
