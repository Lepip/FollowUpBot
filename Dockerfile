FROM python:3.9

RUN mkdir /app
WORKDIR /app

ENV DB_HOST=db
ENV DB_PORT=51373
ENV DB_USER=postgres
ENV DB_NAME=followup_bot_db
ENV DB_PASSWORD=Jbf4833Tk3Q7
ENV BOT_TOKEN=<your tg token>
ENV MISTRAL_TOKEN=<your mistral token>
ENV MISTRAL_MODEL=mistral-large-latest
ENV DEBUG=False

ADD requirements.txt requirements.txt

RUN apt update -y
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

ADD . /app/

ENTRYPOINT ["python", "-u", "bot.py"]