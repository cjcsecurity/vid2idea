from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
import ipaddress

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=700)]


class ProcessingStatus(StrEnum):
    queued = 'queued'
    processing = 'processing'
    ready = 'ready'
    partial = 'partial'
    blocked = 'blocked'
    failed = 'failed'


class IdeaStage(StrEnum):
    saved = 'saved'
    trying = 'trying'
    done = 'done'


class EvidenceKind(StrEnum):
    article_text = 'article_text'
    captions = 'captions'
    audio_transcript = 'audio_transcript'
    video_frames = 'video_frames'
    on_screen_text = 'on_screen_text'


class Resource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    url: str | None = Field(default=None, max_length=4096)
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]

    @field_validator('url')
    @classmethod
    def public_link(cls, value):
        if value is None:
            return value
        parsed = urlsplit(value)
        host = (parsed.hostname or '').rstrip('.').lower()
        if parsed.scheme not in ('https', 'http') or parsed.username or parsed.password or not host or parsed.port not in (None,80,443):
            raise ValueError('Unsupported resource URL')
        if '\\' in value or '%' in host or host == 'localhost' or host.endswith(('.local','.internal','.localhost')) or '.' not in host:
            raise ValueError('Private resource URL')
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            # WHATWG browsers normalize short/octal/hex IPv4 spellings. These
            # are not DNS names, even when Python's strict IP parser rejects them.
            import re
            ascii_host = host.encode('idna').decode('ascii')
            if re.fullmatch(r'(?:\d+|0x[0-9a-f]+)',ascii_host.split('.')[-1],re.I) or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label,re.I) for label in ascii_host.split('.')):
                raise ValueError('Unsupported resource hostname')
        else:
            if not address.is_global:
                raise ValueError('Private resource URL')
        return value


class UseCase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    description: Text
    kind: Literal['general','project'] = 'general'
    project: str | None = Field(default=None, max_length=160)


class EvidenceLink(BaseModel):
    name: str = Field(default='', max_length=200)
    url: str = Field(max_length=4096)


class EvidenceImage(BaseModel):
    path: Path
    caption: str = Field(max_length=300)
    timestamp_seconds: float | None = None


class ResearchSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    url: Annotated[str, StringConstraints(min_length=1, max_length=4096)]

    @field_validator('url')
    @classmethod
    def public_link(cls, value):
        return Resource.public_link(value)


class QuestionAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: Text
    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    status: Literal['answered','inconclusive','needs_you']
    sources: list[ResearchSource] = Field(default_factory=list, max_length=4)
    checked_at: AwareDatetime


class Brief(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    details: list[Text] = Field(default_factory=list, max_length=12)
    suggested_steps: list[Text] = Field(default_factory=list, max_length=8)
    open_questions: list[Text] = Field(default_factory=list, max_length=8)
    resources: list[Resource] = Field(default_factory=list, max_length=8)
    use_cases: list[UseCase] = Field(default_factory=list, max_length=8)
    question_answers: list[QuestionAnswer] = Field(default_factory=list, max_length=8)


class GeneratedBrief(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    brief: Brief
    tags: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]] = Field(default_factory=list, max_length=8)

    @field_validator('tags')
    @classmethod
    def normalize_tags(cls, value):
        return list(dict.fromkeys(tag.lower() for tag in value))


class SourceCapture(BaseModel):
    model_config = ConfigDict(extra='forbid')
    channel_id: str = Field(pattern=r'^\d{17,20}$')
    message_id: str = Field(pattern=r'^\d{17,20}$')
    original_url: str = Field(max_length=4096)
    canonical_url: str = Field(max_length=4096)
    note: str = Field(default='', max_length=4000)
    shared_at: AwareDatetime


class Evidence(BaseModel):
    text: str = Field(default='', max_length=48000)
    kinds: list[EvidenceKind] = Field(default_factory=list)
    frames: list[Path] = Field(default_factory=list, max_length=12)
    gaps: list[str] = Field(default_factory=list)
    source_url: str = Field(default='', max_length=4096)
    links: list[EvidenceLink] = Field(default_factory=list, max_length=80)
    ocr_text: str = Field(default='', max_length=24000)
    images: list[EvidenceImage] = Field(default_factory=list, max_length=3)


class RetryRequest(BaseModel):
    id: str
    idea_id: str
    capture: SourceCapture
    requested_at: datetime
