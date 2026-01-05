from datetime import datetime
from typing import Annotated, TypedDict, List
import operator


class DefaultAssistant(TypedDict):
    user_message: str
    local_context: list[str]
    global_context: Annotated[list, operator.add] 
    image_url: list[str]
    generation: str 

    user_id: str
    thread_id: str
    make_history_summary: bool
    previous_thread_id: str
    search_query: str
    web_query: str
    
    time: datetime
    web_context: str
    web_images: list[str]
    need_recall: bool
    need_web_search: bool
    need_images_search: bool
    
    links_text: str
    links_images: list[str]