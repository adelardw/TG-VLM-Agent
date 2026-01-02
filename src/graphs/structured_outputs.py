from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional


class NewsStructuredOutputs(BaseModel):
    ners: list[str] = Field([], description='Python список из всевозможных именованных сущностей, которые могут содержаться в тексте')
    summary: str = Field(..., description='Суммаризация текста из новости')

class SearchStructuredOutputs(BaseModel):
    search_query: str = Field(..., description='Поисковый запрос из запроса пользователя')


class SummarizeStructuredOutputs(BaseModel):

    summary: str | None= Field(..., description='Суммаризация всего диалога, кратко, но чтобы можно было легко вспомнить'\
                                                   'Верни None, если диалог вообше не конструктивный')

class MemoryRememberStructuredOutputs(BaseModel):
    need_remember: bool = Field(..., description='True, если нужно запомнить в долгосрочную память. False - иначе')

class MemoryRecallStructuredOutputs(BaseModel):
    need_recall: bool = Field(..., description='True, если пользователь намекает что - то вспомнить. False - иначе')

class MemoryWonderStructuredOutputs(BaseModel):
    need_remember: bool = Field(..., description='True, если момент кажется удивительным, и требует внимания для будущего, который нужно однозначно запомнить.'\
                                                 'False - иначе')
    reason: str = Field(..., description='То, почему тебе показался момент удивительным')

class MemoryFindStructuredOutputs(BaseModel):
    true_context: bool = Field(..., description='True, если текущее воспоминание из памяти подходит под контекст.False - иначе')

class AnswerSchema(BaseModel):
    final_answer: str = Field(description="Финальный ответ пользователю.")
    reasoning: str = Field(description="Причина, почему такой ответ.")

class SelectedThreads(BaseModel):
    relevant_thread_ids: list[str] = Field(description="Список ID наиболее релевантных тредов")

class SearchQuerySchema(BaseModel):
    query: str = Field(..., description="Поисковый запрос для векторной базы данных, чтобы найти контекст для ответа на сообщение пользователя. Запрос должен быть автономным (содержать сущности, а не местоимения).")

class FactExtractionSchema(BaseModel):
    """Извлечение конкретных фактов из истории."""
    found_facts: list[str] = Field(default_factory=list, description="Список конкретных фактов, найденных в предоставленной истории, которые отвечают на вопрос пользователя.")
    is_relevant: bool = Field(..., description="Есть ли в этом куске истории информация, полезная для текущего вопроса.")


class RecallAction(BaseModel):
    need_recall: bool = Field(description="Нужно ли лезть в векторную базу (прошлое пользователя)")
    need_web_search: bool = Field(description="Нужно ли лезть в Google (актуальные данные)")
    search_query: str | None = Field(description="Поисковый запрос для векторной модели")
    web_query: str | None = Field(description="Запрос для интернета (например, 'Apple stock price today')")
    visual_search_query: str | None = Field(description="Что искать на изображениях (применимо в случае поиска внутри векторной базы)")
    
