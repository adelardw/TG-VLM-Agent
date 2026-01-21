from agents.prompts import (controller_agent_system_prompt, file_system_agent_system_prompt,
                            web_surfer_agent_system_prompt, weather_agent_system_prompt, calendar_agent_system_prompt,
                            app_opener_agent_system_prompt,
                            gmail_agent_system_prompt)

from tools import (FILE_SYSTEM_TOOL, WEB_SURFER_TOOLS,APP_OPENER_TOOL,NOTIFICATION_TOOL,
                   WEATHER_TOOL, CALENDAR_TOOLS, EMAIL_TOOLS)

from agents.tasks import *
from agents.structured_outputs import CalendarStructuredOutput
from agent_builder import MakeRoutingMultiAgents
from llm import OpenRouterChat
from config import OPEN_ROUTER_API_KEY, TEXT_IMAGE_MODEL

llm = OpenRouterChat(api_key=OPEN_ROUTER_API_KEY, model_name=TEXT_IMAGE_MODEL)

tgc_mas = MakeRoutingMultiAgents(llm, controller_agent_system_prompt)


# tgc_mas.update(system_prompt=weather_agent_system_prompt,
#            agent_name='weather_agent',
#            agent_type='react',
#            agent_description=WEATHER_TASKS,
#            tools=WEATHER_TOOL)

# tgc_mas.update(system_prompt=gmail_agent_system_prompt,
#            agent_name='mail_agent',
#            agent_type="react",
#            tools=EMAIL_TOOLS,
#            agent_description=GMAIL_TASKS)

tgc_mas.update(system_prompt=calendar_agent_system_prompt,
           agent_name='calendar_agent',
           agent_type="with_strucutured_outputs",
           tools=NOTIFICATION_TOOL,
           agent_description=CALENDAR_TASKS,
           output_schema=CalendarStructuredOutput)
