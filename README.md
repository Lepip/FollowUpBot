# Follow up bot

To run, fill in your Telegram bot key, Mistral API key in Dockerfile and execute:

`docker compose up`

Awailable Telegram bot commands:
- `/start` - get a greeting from the bot
- `/restart` - start a new conversation
- `/status` - get debug info

Upon finishing the conversation bot will try to compile your answers into a list.

Questionnaire is stored in `stages.json`, a test questionnaire in `test_stages.json`.

`bot.py` is the entry point.
