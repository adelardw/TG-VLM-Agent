from typing import TypedDict, Literal
from graphs.structured_outputs import NewsStructuredOutputs
from graphs.utils import WebChromeSearch

class NewsGraphState(TypedDict):
    input: str
    search_query: str
    original_news: list[str]
    batch_results: list[NewsStructuredOutputs]
    output: str

class DefaultAssistant(TypedDict):
    user_message: str
    local_context: list[str]
    global_context: list[str]
    image_url: list[str]
    generation: str 
    
    user_id: str
    thread_id: str
    make_history_summary: bool
    previous_thread_id: str


class WebSurfer(TypedDict):
    query: str
    elements: list[dict[str, str | int]]
    reason: list
    action: list
    assistant_answer: str