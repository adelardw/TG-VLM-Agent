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
    #memory_chunk_ind: int | None = Field(..., description='Номер участка локальной памяти который соответствует запросу пользователя '\
    #                                            'Номер участка начинается от 0. Если ни один участок не подходит или нужен поиск в глобальной памяти - ответ None')

class MemoryWonderStructuredOutputs(BaseModel):
    need_remember: bool = Field(..., description='True, если момент кажется удивительным, и требует внимания для будущего, который нужно однозначно запомнить.'\
                                                 'False - иначе')
    reason: str = Field(..., description='То, почему тебе показался момент удивительным')

class MemoryFindStructuredOutputs(BaseModel):
    true_context: bool = Field(..., description='True, если текущее воспоминание из памяти подходит под контекст.False - иначе')

class IntentSchema(BaseModel):
    action: Literal["chat", "recall", "maintain"] = Field(..., description="chat - обычный ответ, recall - нужен поиск в памяти, maintain - пользователь просит саммари или завершает тему")

class AnswerSchema(BaseModel):
    final_answer: str = Field(description="Финальный ответ пользователю.")


class SearchQuerySchema(BaseModel):
    query: str = Field(..., description="Поисковый запрос для векторной базы данных, чтобы найти контекст для ответа на сообщение пользователя. Запрос должен быть автономным (содержать сущности, а не местоимения).")

class FactExtractionSchema(BaseModel):
    """Извлечение конкретных фактов из истории."""
    found_facts: list[str] = Field(default_factory=list, description="Список конкретных фактов, найденных в предоставленной истории, которые отвечают на вопрос пользователя.")
    is_relevant: bool = Field(..., description="Есть ли в этом куске истории информация, полезная для текущего вопроса.")


class RecallAction(BaseModel):
    need_recall: bool = Field(description="Нужно ли искать в прошлых беседах")
    search_query: str | None = Field(description="Оптимизированный запрос для поиска (сущности вместо местоимений)")
    visual_search_query: str | None = Field(description="Что искать на изображениях, если применимо")
    
    
class Elemetns(BaseModel):
    id: int = Field(..., description='Индекс элемента')
    description: int = Field(..., description='Индекс элемента')

class ActualJSElementsStructuredOutputs(BaseModel):
    actual_elements: list[int] = Field(..., description = """Список из id веб елементов, в которых действия
                                                            для данного запроса пользователя подходят наилучшим образом.""")

class WebStructuredOutputs(BaseModel):
    action: Literal['click', 'type', 'scroll', 'done', 'submit','back'] = Field(..., description="""Тип действия.
                                                                         'click' - нажатие,
                                                                         'type' - ввод текста,
                                                                         'submit' - отправка формы (нажатие Enter),
                                                                         'scroll' - прокрутка на сайте. Можно скроллить либо снизу-вверх (up) , либо сверху - вниз (down).
                                                                         'back' - возвращение к другим поисковым результатам.
                                                                         'done' - задача выполнена.""")

    direction: Optional[Literal['up','down']] = Field(None, description='Если action=scroll, иначе - None')
    element_id: Optional[int] = Field(None, description='Id элемента, с которым нужно как - то провзаимодейстовать (нажать, или найти информацию - аттрибут text)')
    text: Optional[str] = Field(None, description='Указывается если action=type - это поле с тектом у элемента с номером element_id')
    reason: Optional[str] = Field(None, description='Указывается если action=done - причина по которой action=done. Во всех остальных случаях - None')

    @field_validator('direction', mode='before')
    @classmethod
    def clean_direction(cls, v):
        """Преобразует строковый 'null' от LLM в настоящий None."""
        if v == 'null':
            return None
        return v
