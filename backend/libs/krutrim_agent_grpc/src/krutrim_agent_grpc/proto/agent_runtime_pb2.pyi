from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class RunTurnRequest(_message.Message):
    __slots__ = ("thread_id", "run_id", "user_message", "frontend_tools_json", "cross_agent_enabled")
    THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    USER_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    FRONTEND_TOOLS_JSON_FIELD_NUMBER: _ClassVar[int]
    CROSS_AGENT_ENABLED_FIELD_NUMBER: _ClassVar[int]
    thread_id: str
    run_id: str
    user_message: str
    frontend_tools_json: str
    cross_agent_enabled: bool
    def __init__(self, thread_id: _Optional[str] = ..., run_id: _Optional[str] = ..., user_message: _Optional[str] = ..., frontend_tools_json: _Optional[str] = ..., cross_agent_enabled: _Optional[bool] = ...) -> None: ...

class RunEvent(_message.Message):
    __slots__ = ("agui_event_json",)
    AGUI_EVENT_JSON_FIELD_NUMBER: _ClassVar[int]
    agui_event_json: str
    def __init__(self, agui_event_json: _Optional[str] = ...) -> None: ...

class InterruptRequest(_message.Message):
    __slots__ = ("thread_id",)
    THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    thread_id: str
    def __init__(self, thread_id: _Optional[str] = ...) -> None: ...

class InterruptAck(_message.Message):
    __slots__ = ("was_running",)
    WAS_RUNNING_FIELD_NUMBER: _ClassVar[int]
    was_running: bool
    def __init__(self, was_running: _Optional[bool] = ...) -> None: ...

class HealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthReply(_message.Message):
    __slots__ = ("ready", "detail")
    READY_FIELD_NUMBER: _ClassVar[int]
    DETAIL_FIELD_NUMBER: _ClassVar[int]
    ready: bool
    detail: str
    def __init__(self, ready: _Optional[bool] = ..., detail: _Optional[str] = ...) -> None: ...

class ShutdownRequest(_message.Message):
    __slots__ = ("flush",)
    FLUSH_FIELD_NUMBER: _ClassVar[int]
    flush: bool
    def __init__(self, flush: _Optional[bool] = ...) -> None: ...

class ShutdownAck(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ChatRequest(_message.Message):
    __slots__ = ("role", "messages_json", "tools_json", "model_kwargs_json", "stream")
    ROLE_FIELD_NUMBER: _ClassVar[int]
    MESSAGES_JSON_FIELD_NUMBER: _ClassVar[int]
    TOOLS_JSON_FIELD_NUMBER: _ClassVar[int]
    MODEL_KWARGS_JSON_FIELD_NUMBER: _ClassVar[int]
    STREAM_FIELD_NUMBER: _ClassVar[int]
    role: str
    messages_json: str
    tools_json: str
    model_kwargs_json: str
    stream: bool
    def __init__(self, role: _Optional[str] = ..., messages_json: _Optional[str] = ..., tools_json: _Optional[str] = ..., model_kwargs_json: _Optional[str] = ..., stream: _Optional[bool] = ...) -> None: ...

class ChatChunk(_message.Message):
    __slots__ = ("chunk_json", "done", "error")
    CHUNK_JSON_FIELD_NUMBER: _ClassVar[int]
    DONE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    chunk_json: str
    done: bool
    error: str
    def __init__(self, chunk_json: _Optional[str] = ..., done: _Optional[bool] = ..., error: _Optional[str] = ...) -> None: ...

class HostToolRequest(_message.Message):
    __slots__ = ("tool", "args_json", "thread_id")
    TOOL_FIELD_NUMBER: _ClassVar[int]
    ARGS_JSON_FIELD_NUMBER: _ClassVar[int]
    THREAD_ID_FIELD_NUMBER: _ClassVar[int]
    tool: str
    args_json: str
    thread_id: str
    def __init__(self, tool: _Optional[str] = ..., args_json: _Optional[str] = ..., thread_id: _Optional[str] = ...) -> None: ...

class HostToolReply(_message.Message):
    __slots__ = ("result_json", "error")
    RESULT_JSON_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    result_json: str
    error: str
    def __init__(self, result_json: _Optional[str] = ..., error: _Optional[str] = ...) -> None: ...
