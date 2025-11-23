# Для чего:
1. TG Bot который по транскрибации речи может делать рутинные задачи: \n
  1.1 Давать напоминания о тех или иных событиях \n
  1.2 Смотреть прогноз погоды на текущий день + 2 дня вперед \n
  1.3 Делать саммари по заданным новостям из инетернета \n
  1.4 Если настроить интеграцию с GOOGLE-CLOUD API, то вместо напоминнаний будет доступен полноценный GOOGLE-CALENDAR + GOOGLE MAIL (Чтение почты) \n
   
Все это реализовано в формате нажатия кнопочки [AGENTIC MODE] в ТГ боте

3. Что еще можно добавить: \n
   2.1 Из меню бота (/start, /menu) слать сообщения LLM, если не выбирается кнопка [AGENTIC MODE]. То есть добавить так или иначе чат. \n
   2.2 Анализ картинок / документов \n
   2.3 Мб сделать кнопочку под Code LLM \n
   2.4 Сделать генерацию структурированных графиков / отчетов по данным. [AGENTIC MODE] \n
   2.5 Добавить журналирование каких- то событий, создание таблиц [AGENTIC MODE] \n
   


# Структура проекта:
```md
├── src
│   ├── agents
│   │   ├── __init__.py
│   │   ├── additional_to_prompts.py
│   │   ├── agents.py
│   │   ├── prompts.py
│   │   ├── structured_outputs.py
│   │   └── tasks.py
│   ├── beautylogger
│   │   ├── __init__.py
│   │   └── bl.py
│   ├── graphs
│   │   ├── __init__.py
│   │   ├── graph_states.py
│   │   ├── news_summary_graph.py
│   │   ├── prompts.py
│   │   ├── structured_outputs.py
│   │   ├── tasks.py
│   │   └── utils.py
│   ├── tgbot
│   │   ├── __init__.py
│   │   ├── billing.py
│   │   ├── bot_shemas.py
│   │   ├── bot.py
│   │   ├── users_cache.py
│   │   └── utils.py
│   ├── tools
│   │   ├── __init__.py
│   │   ├── app_opener_tools.py
│   │   ├── code_tools.py
│   │   ├── file_system_tools.py
│   │   ├── finance_tools.py
│   │   ├── google_api_tools.py
│   │   ├── notification_tools.py
│   │   ├── utils.py
│   │   ├── weather_tool.py
│   │   └── web_tools.py
│   └── vega
│   │   ├── __init__.py
│   │   ├── vega_config.py
│   │   ├── vega_bot.py
│   │   └── vega_stream.py
│   ├── llm.py
│   ├── config.py
│   ├── agent_builder.py
│   ├── scheduler_manager.py
│   ├── users_cache.py
├── app.py
├── tg.py
├── token.json
├── user_accept.md
├── client_secret.apps.googleusercontent.com.json
├── confidence.md
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── LICENSE.md
└── uv.lock
```

# Запуск:

1. В Google Cloud заведите проект с google calendar + gmail api
2. Сделайте креды -> client_secret.apps.googleusercontent.com.json
3. На первом запуске будет открыт бразуер с подтверждением Вашей почты и Вашего аккаунта

# После этого Вы можете:
1. Запускать ассистента в потоковом разпознавании:
```
uv run app.py
```
2. Создать ТГБота и запустить его:

```
uv run tg.py
```

# Особенности работы:
1. Если хотите работать со своей почтой, придумайте более свой способ масикрования перс данных, if you want,
но вроде и так норм должно работать
2. confidence.md / user_accept.md - это больше уже про бизнес, но учтите, лицензия в проекте - не для коммерческого использования
3. Работает через OpenRouter провайдера, пополнение через p2p и прочие сервисы.
4. Есть возможности интеграции своих агентов, см. agent_builder.py и пример создания agents.py
5. Вся конфиденциальная инфа - .env файл, смотрите как считываются переменные в config.py. Именно оттуда идет импорт во все остальные модули.
