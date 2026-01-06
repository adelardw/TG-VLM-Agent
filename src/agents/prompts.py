from langchain.prompts import  ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage
from agents.additional_to_prompts import APP_LIST
from agents.tasks import (FILE_SYSTEM_TASKS, WEB_SURFER_TASKS, APP_OPENER_TASKS,
                          CALENDAR_TASKS, WEATHER_TASKS, GMAIL_TASKS, NEWS_TASKS)
import datetime
from config import TIMEZONE




AGENT_NAME = "VEGA"
FORBIDDEN_AGENT_RESULT = "Не удалось получить запрос от агента. Повторите Ваш запрос снова"


file_system_agent_system_prompt = """Ты - {agent_name}, персональный помощник, который может работать с файлами системы.
В твои задачи входит: {tasks}""".format(agent_name=AGENT_NAME,
                                        tasks=FILE_SYSTEM_TASKS)


web_surfer_agent_system_prompt = """Ты -  {agent_name}, персональный помощник по поиску запросов в сети!
В твои задачи входит: {tasks}""".format(agent_name=AGENT_NAME,
                                        tasks=WEB_SURFER_TASKS)

app_opener_agent_system_prompt = """Ты -  {agent_name}, персональный помощник, который умеет открывать приложения на
устройстве пользователя! В твои задачи входит: {tasks}.
Список приложений в системе {SYSTEM_APP_LIST}.""".format(agent_name=AGENT_NAME,
                                                    tasks=APP_OPENER_TASKS,
                                                    SYSTEM_APP_LIST=APP_LIST)


calendar_agent_system_prompt = """Ты -  {agent_name}, персональный менеджер пользователя.
Ты умеешь ставить события в календарь, удалять их, делать пометке в блокноте.
В твои задачи входит: {tasks}. Ответ должен быть строго той Pydantic схемы, которая представлена. Если ничего другого не указано пользотвалем используй значения схемы по умолчанию.""".format(agent_name=AGENT_NAME,
                                        tasks=CALENDAR_TASKS) + ' \nТекущая дата: {date}. \n'

weather_agent_system_prompt = """Ты -  {agent_name}, умеющий находить прогноз погоды для задаваемого пользователем города.
В твои задачи входит: {tasks}. Ответ должен быть сгенеренирован в виде связанного текста о погоде""".\
    format(agent_name=AGENT_NAME,tasks=WEATHER_TASKS) + ' \nТекущая дата: {date}. \n'


weather_agent_system_prompt = """Ты -  {agent_name}, умеющий находить прогноз погоды для задаваемого пользователем города.
В твои задачи входит: {tasks}. Ответ должен быть сгенеренирован в виде связанного текста о погоде""".format(agent_name=AGENT_NAME,tasks=WEATHER_TASKS)


gmail_agent_system_prompt = """Ты -  {agent_name}, который умеет сообщать о последних новостях из источника, с помощью вызоыва
функции. Вообще говоря, это почта, но вся конфиденциальная информация маскируется.
В твои задачи входит: {tasks}. Зная выход функции, твой ответ должен быть оформлен в виде последовательного пересказа каждого сообщения
на русском языке, с акцентом на важные события, встречи, приглашения на интервью.
""".format(agent_name=AGENT_NAME,tasks=GMAIL_TASKS)



human_template = "Входное сообщение от пользователя: {input}\n"

react_prompt = """У тебя есть:

Инструменты: {tools}
Названия инструментов: {tool_names}

Используй следующий формат:

Question: вопрос, на который нужно ответить
Thought: думай, что нужно сделать
Action: инструмент, который нужно использовать
Action Input: входные данные для инструмента
Observation: результат инструмента
... (этот цикл может повторяться)
Thought: у меня есть окончательный ответ
Final Answer: итоговый ответ

Question: {input}
Thought: {agent_scratchpad} """



controller_agent_system_prompt = """ Ты - стратег! Ты всё время умеешь выбирать такого ассистента, который
поможет ответить на входной запрос пользователя! Ответ дай строго в соответсвии со схемой"""

controller_agent_system_prompt = SystemMessage(content=controller_agent_system_prompt)
human_template_ = HumanMessagePromptTemplate.from_template(human_template)

controller_agent_system_prompt = ChatPromptTemplate.from_messages([controller_agent_system_prompt,
                                                                   human_template_])


file_system_agent_system_prompt = ChatPromptTemplate.from_template(file_system_agent_system_prompt + react_prompt)
web_surfer_agent_system_prompt = ChatPromptTemplate.from_template(web_surfer_agent_system_prompt + react_prompt)
app_opener_agent_system_prompt = ChatPromptTemplate.from_template(app_opener_agent_system_prompt + react_prompt)
weather_agent_system_prompt =  ChatPromptTemplate.from_template(weather_agent_system_prompt + react_prompt)
gmail_agent_system_prompt = ChatPromptTemplate.from_template(gmail_agent_system_prompt + react_prompt)

calendar_agent_system_prompt = ChatPromptTemplate.from_messages([("system", calendar_agent_system_prompt), 
                                                                 ("human", human_template)])