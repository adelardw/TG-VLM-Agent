from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_core.messages import SystemMessage, HumanMessage
from openai import OpenAI
import typing as tp
from pydantic import BaseModel
import json
import typing as tp
import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.embeddings.embeddings import Embeddings
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun


class OpenRouterChat(BaseChatModel):
    """
    Класс-обертка для работы с чат-моделями через API OpenRouter,
    совместимый с экосистемой LangChain и поддерживающий структурированный вывод.
    """
    _client: tp.Any = None
    generation_kwargs: dict = None

    def __init__(self,
                 api_key: str,
                 generation_kwargs: dict = None,
                 model_name: str = "qwen/qwen3-235b-a22b-2507"):
        super().__init__()

        self._api_key = api_key
        self._client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        self._model_name = model_name
        self._schema: tp.Optional[BaseModel] = None

        default_kwargs = {
            "temperature": 1e-5,
        }
        self.generation_kwargs = default_kwargs if not generation_kwargs else generation_kwargs

    @property
    def _llm_type(self) -> str:
        return "openrouter-chat"

    def _generate(
        self,
        messages: tp.List[BaseMessage],
        stop: tp.Optional[tp.List[str]] = None,
        run_manager: tp.Optional[CallbackManagerForLLMRun] = None,
        **kwargs: tp.Any,
    ) -> ChatResult:
        """
        Основной метод для вызова API, который принимает список сообщений
        и поддерживает structured output через tools.
        """
        message_dicts = [self._convert_message_to_dict(m) for m in messages]


        final_generation_kwargs = {**self.generation_kwargs, **kwargs}
        if stop:
            final_generation_kwargs['stop'] = stop


        tools = kwargs.get("tools")
        tool_choice = kwargs.get("tool_choice")

        if tools:
            final_generation_kwargs["tools"] = tools
            if tool_choice:
                final_generation_kwargs["tool_choice"] = tool_choice

        if not self._schema:
            completion = self._client.chat.completions.create(
                messages=message_dicts,
                model=self._model_name,
                **final_generation_kwargs)


            response_message = self._convert_dict_to_message(completion.choices[0].message.dict())
            generation = ChatGeneration(message=response_message)
            return ChatResult(generations=[generation])
        else:
            completion = self._client.chat.completions.parse(
                messages=message_dicts,
                model=self._model_name,
                response_format = self._schema,
                **final_generation_kwargs)

            data = self._parse_model_results(completion.choices[0].message.content)
            response_message = self._schema.model_validate(data)

            ai_message = AIMessage(
                content='',
                response_metadata={"structured_output": response_message}
            )

            generation = ChatGeneration(message=ai_message)
            return ChatResult(generations=[generation])


    @staticmethod
    def _parse_model_results(raw_output: str):
        try:
            data = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
        except:
            lines = raw_output.strip().splitlines()
            data = {}
            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    data[key.strip()] = value.strip()

        return data

    def _convert_message_to_dict(self, message: BaseMessage) -> dict:
        """Конвертирует сообщение LangChain в словарь для API."""
        if isinstance(message, HumanMessage):
            role = "user"
        elif isinstance(message, AIMessage):
            role = "assistant"
        elif isinstance(message, SystemMessage):
            role = "system"
        else:
            raise TypeError(f"Неподдерживаемый тип сообщения: {type(message)}")


        if isinstance(message, AIMessage) and message.tool_calls:
            return {
                "role": "assistant",
                "content": message.content or None,
                "tool_calls": message.tool_calls
            }

        return {"role": role, "content": message.content}

    def _convert_dict_to_message(self, message_dict: dict) -> AIMessage:
        """Конвертирует ответ от API (словарь) в AIMessage."""
        if tool_calls := message_dict.get("tool_calls"):
            parsed_tool_calls = []
            invalid_tool_calls = []

            for call in tool_calls:
                try:
                    function_args = json.loads(call["function"]["arguments"])
                    parsed_tool_calls.append(
                        {
                            "id": call["id"],
                            "name": call["function"]["name"],
                            "args": function_args,
                        }
                    )
                except json.JSONDecodeError:
                    invalid_tool_calls.append(
                        {
                            "id": call["id"],
                            "name": call["function"]["name"],
                            "args": call["function"]["arguments"],
                            "error": "Failed to decode JSON from arguments string.",
                        }
                    )
            return AIMessage(
                content=message_dict.get("content") or "",
                tool_calls=parsed_tool_calls,
                invalid_tool_calls=invalid_tool_calls,
            )
        else:
            return AIMessage(content=message_dict.get("content", ""))

    def invoke(
        self,
        input: tp.Union[str, tp.List[BaseMessage]],
        config: tp.Optional[RunnableConfig] = None,
        *,
        stop: tp.Optional[tp.List[str]] = None,
        **kwargs: tp.Any,
    ) -> tp.Union[BaseMessage, BaseModel]:
        """
        Переопределяет invoke. Если установлена схема (_schema), возвращает Pydantic-объект.
        Иначе возвращает AIMessage.
        """

        if isinstance(input, str):
            messages = [HumanMessage(content=input)]
        elif isinstance(input, list):
            messages = input
        else:
            messages = input.to_messages() if hasattr(input, "to_messages") else [HumanMessage(content=str(input))]


        run_manager = config.get("callbacks").on_chain_start if config and config.get("callbacks") else None

        result = self._generate(
            messages=messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs
        )

        message = result.generations[0].message

        if self._schema and "structured_output" in message.response_metadata:

            return message.response_metadata["structured_output"]

        return message

    def bind_tools(
        self,
        tools: tp.List[tp.Union[tp.Dict[str, tp.Any], tp.Type[BaseModel]]],
        **kwargs: tp.Any,
    ) -> Runnable:
        """
        Привязывает инструменты к модели в формате, совместимом с OpenAI.
        """

        formatted_tools = [convert_to_openai_tool(tool) for tool in tools]


        return self.bind(tools=formatted_tools, **kwargs)

    def with_structured_output(self, schema, *, include_raw = False, **kwargs):
        """Привязывает Pydantic схему для структурированного вывода."""


        new_obj = self.__class__(api_key=self._api_key,
                                generation_kwargs=self.generation_kwargs,
                                model_name=self._model_name)
        new_obj._schema = schema
        return new_obj
    
    async def ainvoke(self, input, config = None, *, stop = None, **kwargs):
        message = await super().ainvoke(input, config, stop=stop, **kwargs)
        if self._schema and "structured_output" in message.response_metadata:
            return message.response_metadata["structured_output"]

        return message
    
    
    
class OpenRouterEmbeddings(Embeddings):
    def __init__(self, api_key: str, model_name: str):
        self._api_key = api_key
        self._client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        self._model_name = model_name
        
    
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed search docs.

        Args:
            texts: List of text to embed.

        Returns:
            List of embeddings.
        """

        embedding =self._client.embeddings.create(
        model=self._model_name,
        input=texts,
        encoding_format="float")
        return [embed.embedding for embed in embedding.data]


    def embed_query(self, text: str) -> list[float]:
        """Embed query text.

        Args:
            text: Text to embed.

        Returns:
            Embedding.
        """
        embedding =self._client.embeddings.create(
        model=self._model_name,
        input=text,
        encoding_format="float")
        return embedding.data[0].embedding
