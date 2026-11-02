from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ConversationCreate(StrictModel):
    project_id: str = "general"
    title: str = Field(default="Cuộc trò chuyện mới", min_length=1, max_length=150)


class ConversationUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=150)
    project_id: str | None = Field(default=None, min_length=1, max_length=80)


class TutorContext(StrictModel):
    language: Literal['en', 'ja']
    level: Literal['A1','A2','B1','B2','C1','C2','N5','N4','N3','N2','N1'] = 'B1'
    exam: Literal['general','IELTS','TOEIC','TOEFL','JLPT'] = 'general'
    activity: Literal['lesson','exercise','writing','speaking','reading','listening'] = 'lesson'


class ChatInput(StrictModel):
    conversation_id: str | None = None
    project_id: str = "general"
    text: str = Field(min_length=1, max_length=16000)
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9-]+$")
    private: bool = False
    source: Literal["text", "voice"] = "text"
    history: list[dict[str, str]] = Field(default_factory=list, max_length=24)
    use_knowledge: bool = True
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    mode: Literal["chat", "read", "compare", "technical", "planner", "log", "tutor"] = "chat"
    performance: Literal['auto', 'fast', 'quality'] | None = None
    voice_conversation: bool = False
    response_length: Literal['short', 'standard', 'long'] = 'standard'
    continue_response: bool = False
    continuation_question: str | None = Field(default=None, min_length=1, max_length=16000)
    tutor: TutorContext | None = None

    @field_validator("history")
    @classmethod
    def check_history(cls, value):
        for message in value:
            if set(message) != {"role", "content"} or message["role"] not in {"user", "assistant"} or len(message["content"]) > 16000:
                raise ValueError("Lịch sử phiên riêng tư không hợp lệ")
        return value


class AppSettings(StrictModel):
    model: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.:/-]+$")
    context: int = Field(ge=2048, le=16384)
    max_output: int = Field(ge=128, le=8192)
    temperature: float = Field(ge=0, le=1)
    offline: bool = True
    save_history: bool = True
    user_name: str = Field(min_length=1, max_length=80)
    address_style: str = Field(max_length=240)
    allowed_roots: list[str] = Field(default_factory=list, max_length=12)
    tts_speed: float = Field(ge=0.5, le=2)
    stt_language: Literal["vi", "en", "ja", "auto"] = "vi"
    native_tools: bool = True
    auto_speak: bool = False
    pronunciations: dict[str, str] = Field(default_factory=dict, max_length=40)
    fast_model: str = Field(default='dbot-qwen35:4b', min_length=1, max_length=120, pattern=r'^[a-zA-Z0-9_.:-]+$')
    performance: Literal['auto', 'fast', 'quality'] = 'auto'
    keep_alive: Literal['30s', '2m', '5m', '10m'] = '5m'
    coding_model: str = Field(default='dbot-qwen35:4b', min_length=1, max_length=120, pattern=r'^[a-zA-Z0-9_.:-]+$')
    learn_from_conversations: bool = False

    @field_validator('pronunciations')
    @classmethod
    def validate_pronunciations(cls, value):
        if any(not key.strip() or len(key) > 40 or not text.strip() or len(text) > 120 for key, text in value.items()):
            raise ValueError('Từ điển phát âm: từ <=40 ký tự, cách đọc <=120 ký tự')
        return value

    @field_validator("model", 'fast_model', 'coding_model')
    @classmethod
    def local_model(cls, value):
        if "cloud" in value.lower() or "/" in value:
            raise ValueError("Chỉ dùng model local đã tải trong Ollama")
        return value
