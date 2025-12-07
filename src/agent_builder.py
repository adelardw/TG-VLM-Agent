import asyncio
from langchain_core.prompts.chat import BaseChatPromptTemplate
from langchain.agents import AgentExecutor, create_react_agent, create_structured_chat_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field, create_model
from src.llm import OpenRouterChat
import typing as tp
from loguru import logger
import inspect
from datetime import datetime
from langchain_core.output_parsers import StrOutputParser




class MakeRoutingMultiAgents():
    def __init__(self, llm: BaseChatModel | OpenRouterChat,
                       router_system_prompt: BaseChatPromptTemplate):

        self.agents: dict[str, AgentExecutor] | dict[str, BaseChatModel] = {}
        self.agent_types: dict[str, str] = {}
        self.tools: dict[str, tp.Callable] = {}
        self.prompts: dict[str, str] = {}
        self.schemas: dict[str, BaseChatModel] = {}
        self.agent_answer: dict[str, dict[datetime, tp.Any]] = {}

        self.llm: BaseChatModel = llm
        self.router_structured_output = {}
        self.runner_type = {}
        self.router_class: tp.Optional[tp.Type[BaseModel]] = None
        self.router_system_prompt =  router_system_prompt
        self.base_description = 'Нужно выбрать имя одного из агентов. Они представлены в виде: ИМЯ АГЕНТА - ЧТО УМЕЕТ ДЕЛАТЬ АГЕНТ.'


    def _create_router(self) -> None:
        '''Создает Pydantic модель на основе зарегистрированных агентов'''
        fields = {}

        agents = list(self.router_structured_output.keys())
        for agent_name, agent_description in self.router_structured_output.items():
            self.base_description += f"\n {agent_name} - {agent_description}"

        fields = {"agent_name": (tp.Literal[*agents], Field(..., description=self.base_description))}

        self.router_class = create_model('RouterStructuredOutput', **fields)
        self.router_chain = self.router_system_prompt | self.llm.with_structured_output(self.router_class)


    def update(self, system_prompt: tp.Optional[BaseChatPromptTemplate],
               agent_name: str,
               agent_type: tp.Literal['react','create_structured_chat_agent', 'with_strucutured_outputs',
                                      'free','multimodal',
                                      'graph'],

               agent_description: str,
               llm_or_graph: tp.Optional[BaseChatModel] | tp.Optional[CompiledStateGraph] = None,
               tools: tp.Optional[list[tp.Callable]] = None,
               output_schema: tp.Optional[BaseModel] = None):

        '''
        Args:
            system_prompt (str): Системный промпт агента
            agent_name (str): Имя агента

            tools (str): Описание задач, которые должен выполнять агент
            description(str): описание агента

        '''
        assert ((agent_type=='react' or agent_type=='create_structured_chat_agent') and tools and not output_schema) or \
                (agent_type=="with_strucutured_outputs" and output_schema) or (agent_type=='free' and not tools and not output_schema) \
                or (agent_type=='multimodal' and not tools and not output_schema and llm_or_graph) \
                or (agent_type == 'graph' and not tools and not output_schema), \
                f'Sorry but this option is not supported for {agent_name} type'\
                f'If you use `multimodal` please add new OpenRouterChat instance with supported multimodal model'

        self.router_structured_output[agent_name] = agent_description

        self.prompts[agent_name] = system_prompt
        self.schemas[agent_name] = output_schema
        self.agent_types[agent_name] = agent_type

        if agent_type == 'react' or agent_type == 'create_structured_chat_agent':
            if agent_type == 'react':
                agent = create_react_agent(self.llm, tools, system_prompt)
            else:
                agent = create_structured_chat_agent(self.llm, tools, system_prompt)

            agent_executor = AgentExecutor(agent=agent,tools=tools,verbose=True,handle_parsing_errors=True)
            self.agents[agent_name] = agent_executor

        if agent_type == "with_strucutured_outputs":
            self.agents[agent_name] = system_prompt | self.llm.with_structured_output(output_schema)

        if agent_type == 'free':
            self.agents[agent_name] = system_prompt | self.llm | StrOutputParser()

        if agent_type == 'multimodal':
            assert llm_or_graph
            self.agents[agent_name] = system_prompt | llm_or_graph | StrOutputParser()

        if agent_type == 'graph':
            assert llm_or_graph

            self.agents[agent_name] = llm_or_graph

        if tools and isinstance(tools, list) and all([inspect.isfunction(tool) for tool in tools]):
            self.tools[agent_name] = tools

        self._create_router()

    def run(self, agent_name: str ,input: dict):
        
        user_id = input.get('user_id')
        if self.agent_types[agent_name] == 'react' or self.agent_types[agent_name] == 'graph' or \
                                    self.agent_types[agent_name] == 'create_structured_chat_agent':

            answer = self.agents[agent_name].invoke(input=input)['output']
            self.agent_answer[agent_name] = {datetime.now().isoformat(): answer}

        elif self.agent_types[agent_name] == 'with_strucutured_outputs':
            answer = self.agents[agent_name].invoke(input=input)
            tool = self.tools.get(agent_name, None)[0]

            if tool:
                tool_args = answer.model_dump()
                sig = inspect.signature(tool)
                if 'user_id' in sig.parameters and user_id is not None:
                    
                    tool_args['user_id'] = user_id

                try:
                    answer = tool(tool_args)
                except TypeError as e:
                    answer = tool(**tool_args)

                self.agent_answer[agent_name] = {datetime.now().isoformat(): answer if answer else 'function has been called!'}
            else:
                self.agent_answer[agent_name] = {datetime.now().isoformat(): answer.model_dump()}

        elif self.agent_types[agent_name] == 'free':
            answer = self.agents[agent_name].invoke(input=input)


        return answer

    async def arun(self, agent_name: str ,input: dict):
        
        user_id = input.get('user_id')
        if self.agent_types[agent_name] == 'react' or self.agent_types[agent_name] == 'graph' or \
                                    self.agent_types[agent_name] == 'create_structured_chat_agent':

            answer = (await self.agents[agent_name].ainvoke(input=input))
            answer = answer['output']
            self.agent_answer[agent_name] = {datetime.now().isoformat(): answer}

        elif self.agent_types[agent_name] == 'with_strucutured_outputs':
            answer = self.agents[agent_name].invoke(input=input)
            tool = self.tools.get(agent_name, None)[0]

            if tool:
                tool_args = answer.model_dump()
                sig = inspect.signature(tool)
                if 'user_id' in sig.parameters and user_id is not None:
                    
                    tool_args['user_id'] = user_id

                try:
                    answer = tool(tool_args)
                except TypeError as e:
                    answer = tool(**tool_args)

                self.agent_answer[agent_name] = {datetime.now().isoformat(): answer if answer else 'function has been called!'}
            else:
                self.agent_answer[agent_name] = {datetime.now().isoformat(): answer.model_dump()}

        elif self.agent_types[agent_name] == 'free':
            answer = await self.agents[agent_name].ainvoke(input=input)

        return answer
    
    def __call__(self, input: dict):

        activated_agent = self.router_chain.invoke(input)
        agent_name = activated_agent.agent_name
        logger.info(f'>>>> ACTIVATED AGENT <<< {agent_name}')
        agent_result = self.run(agent_name, input=input)
        logger.info(f'>>>> ACTIVATED AGENT  RESULT <<< {agent_result}')
        return agent_result
    
    async def __acall__(self, input: dict):

        activated_agent = await self.router_chain.ainvoke(input)
        agent_name = activated_agent.agent_name
        logger.info(f'>>>> ACTIVATED AGENT <<< {agent_name}')
        agent_result = await self.arun(agent_name, input=input)
        logger.info(f'>>>> ACTIVATED AGENT  RESULT <<< {agent_result}')
        return agent_result
    
    def invoke(self, input: dict):
        return self(input)
    
    async def ainvoke(self, input: dict):
        return await self.__acall__(input)