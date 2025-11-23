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
