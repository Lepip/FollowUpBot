from typing import Tuple
import asyncpg
from utils.config import cfg
import logging

log = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.conn: asyncpg.Connection = ...

    async def connect(self):
        self.conn: asyncpg.Connection = await asyncpg.connect(
            host=cfg['db_host'],
            port=cfg['db_port'],
            user=cfg['db_user'],
            database=cfg['db_name'],
            password=cfg['db_password']
        )

    async def restart_conv(self, chat_id: int):
        await self.conn.execute(
            "DELETE FROM convs WHERE chat_id=$1",
            chat_id
        )
        await self.conn.execute(
            "DELETE FROM chatlogs WHERE chat_id=$1",
            chat_id
        )
        await self.conn.execute(
            '''
            INSERT INTO convs (chat_id, is_started, is_concluded, set_theme, stage_id, batch_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            ''', 
            chat_id, False, False, False, 0, -1
        )
    
    async def start_conv(self, chat_id: int):
        await self.conn.execute(
            "UPDATE convs SET is_started = $2 WHERE chat_id = $1",
            chat_id, True
        )

    async def end_conv(self, chat_id: int):
        await self.conn.execute(
            "UPDATE convs SET is_concluded = $2 WHERE chat_id = $1",
            chat_id, True
        )

    async def get_conv_stage(self, chat_id: int) -> Tuple[int, int, bool, bool]:
        res = await self.conn.fetchrow(
            "SELECT stage_id, batch_id, is_started, is_concluded, set_theme FROM convs WHERE chat_id=$1", 
            chat_id
        )
        if not res:
            await self.restart_conv(chat_id)
        return (res['stage_id'], res['batch_id'], res['is_started'], res['is_concluded'], res['set_theme']) if res else (0, -1, False, False, False)
    
    async def set_conv_stage(self, chat_id: int, stage_id: int, batch_id: int, is_started: bool, is_concluded: bool, set_theme: bool):
        await self.conn.execute(
            "UPDATE convs SET stage_id = $2, batch_id = $3, is_started = $4, is_concluded = $5, set_theme = $6 WHERE chat_id = $1",
            chat_id, stage_id, batch_id, is_started, is_concluded, set_theme
        )

    async def get_messages(self, chat_id: int) -> list[dict]:
        res = await self.conn.fetch(
            "SELECT role, message_text FROM chatlogs WHERE chat_id=$1 ORDER BY message_id",
            chat_id
        )
        return [{'role': entry['role'], 'content': entry['message_text']} for entry in res]
    
    async def add_message(self, chat_id: int, message_text: str, role: str, stage_id: int):
        max_message_id = await self.conn.fetchval(
            "SELECT COALESCE(MAX(message_id), 0) FROM chatlogs WHERE chat_id=$1",
            chat_id
        )
        message_id = max_message_id + 1

        await self.conn.execute(
            "INSERT INTO chatlogs (chat_id, message_id, message_text, role, stage_id) VALUES ($1, $2, $3, $4, $5)",
            chat_id, message_id, message_text, role, stage_id
        )

    async def get_stage_messages(self, chat_id: int, stage_id: int):
        res = await self.conn.fetch(
            "SELECT role, message_text FROM chatlogs WHERE chat_id=$1 AND stage_id=$2 ORDER BY message_id",
            chat_id, stage_id
        )
        return [{'role': entry['role'], 'content': entry['message_text']} for entry in res]

    async def insert_answers(self, chat_id: int, questions: dict, answers: dict):
        for question in questions:
            answer_text = answers.get(question['id'])
            await self.conn.execute(
                '''
                INSERT INTO public.answers (chat_id, question_id, question_text, answer_text)
                VALUES ($1, $2, $3, $4)
                ''', 
                chat_id, question['id'], question['text'], answer_text
            )

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.conn.close()
