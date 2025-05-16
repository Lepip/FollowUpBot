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

    async def set_current_conv(self, chat_id: int, conv_id: int):
        await self.conn.execute(
            "UPDATE convs SET is_current=FALSE WHERE chat_id=$1",
            chat_id
        )
        await self.conn.execute(
            "UPDATE convs SET is_current=TRUE WHERE chat_id=$1 AND conv_id=$2",
            chat_id, conv_id
        )

    async def is_concluded(self, chat_id: int):
        current_conv = await self.get_current_conv(chat_id)
        if current_conv is None:
            log.warning(f"Couldn't get current conv for chat {chat_id}")
            return False
        conv_id, _ = current_conv
        res = await self.conn.fetchrow(
            "SELECT is_concluded FROM convs WHERE conv_id=$1",
            conv_id
        )
        return res['is_concluded'] if res else None
    
    async def is_started(self, chat_id: int):
        current_conv = await self.get_current_conv(chat_id)
        if current_conv is None:
            log.warning(f"Couldn't get current conv for chat {chat_id}")
            return False
        conv_id, _ = current_conv
        res = await self.conn.fetchrow(
            "SELECT is_started FROM convs WHERE conv_id=$1",
            conv_id
        )
        return res['is_started'] if res else None
    
    async def get_current_conv(self, chat_id: int) -> Tuple[int, str]:
        res = await self.conn.fetchrow(
            "SELECT conv_id, conv_name FROM convs WHERE chat_id=$1 AND is_current=TRUE",
            chat_id
        )
        return (res['conv_id'], res['conv_name']) if res else None

    async def get_convs(self, chat_id: int) -> list[str]:
        res = await self.conn.fetch(
            "SELECT conv_id, conv_name FROM convs WHERE chat_id=$1",
            chat_id
        )
        return [{
            'conv_id': entry['conv_id'], 
            'conv_name': entry['conv_name']
            } for entry in res]
    
    async def get_conv_id_by_name(self, chat_id: int, conv_name: str):
        res = await self.conn.fetchrow(
            "SELECT conv_id FROM convs where chat_id=$1 AND conv_name=$2",
            chat_id, conv_name
        )
        return res['conv_id'] if res else None

    async def set_current_conv_by_name(self, chat_id: int, conv_name: str):
        conv_id = await self.get_conv_id_by_name(chat_id, conv_name)
        await self.set_current_conv(chat_id, conv_id)

    async def delete_conv(self, conv_id: int):
        await self.conn.execute(
            "DELETE FROM convs WHERE conv_id=$1",
            conv_id
        )

    async def delete_conv_by_name(self, chat_id: int, conv_name: int):
        conv_id = await self.get_conv_id_by_name(chat_id, conv_name)
        if conv_id is not None:
            await self.delete_conv(conv_id)
    
    async def get_questions(self, chat_id: int) -> list[dict]:
        current_conv = await self.get_current_conv(chat_id)
        if current_conv is None:
            log.warning(f"Couldn't get current conv for chat {chat_id}")
            return False
        conv_id, _ = current_conv
        res = await self.conn.fetch(
            "SELECT question_id, question_text, answer FROM questions WHERE conv_id=$1",
            conv_id
        )
        return [{
            'question_id': entry['question_id'], 
            'question_text': entry['question_text'],
            'answer': entry['answer']
            } for entry in res]
    
    async def get_messages(self, chat_id: int) -> list[dict]:
        current_conv = await self.get_current_conv(chat_id)
        if current_conv is None:
            log.warning(f"Couldn't get current conv for chat {chat_id}")
            return False
        conv_id, _ = current_conv
        res = await self.conn.fetch(
            "SELECT role, message_text FROM chatlogs WHERE conv_id=$1 ORDER BY message_id",
            conv_id
        )
        return [{'role': entry['role'], 'content': entry['message_text']} for entry in res]
    
    async def add_message(self, conv_id: int, message_text: str, role: str):
        max_message_id = await self.conn.fetchval(
            "SELECT COALESCE(MAX(message_id), 0) FROM chatlogs WHERE conv_id=$1",
            conv_id
        )
        message_id = max_message_id + 1

        await self.conn.execute(
            "INSERT INTO chatlogs (conv_id, message_id, message_text, role) VALUES ($1, $2, $3, $4)",
            conv_id, message_id, message_text, role
        )

    async def write_answer(self, conv_id: int, question_id: int, answer: str):
        await self.conn.execute(
            "UPDATE questions SET answer=$1 WHERE conv_id=$2 AND question_id=$3",
            answer, conv_id, question_id
        )

    async def set_questions(self, chat_id: int, questions: list[str]):
        current_conv = await self.get_current_conv(chat_id)
        if current_conv is None:
            log.warning(f"Couldn't get current conv for chat {chat_id}")
            return False
        conv_id, _ = current_conv
        await self.conn.execute(
            "DELETE FROM questions WHERE conv_id=$1",
            conv_id
        )
        for idx, question_text in enumerate(questions, start=1):
            await self.conn.execute(
                "INSERT INTO questions (conv_id, question_id, question_text) VALUES ($1, $2, $3)",
                conv_id, idx, question_text
            )

    async def gen_conv_id(self):
        new_conv_id = await self.conn.fetchval(
            "SELECT nextval('conv_id_seq')"
        )
        return new_conv_id

    async def new_conv(self, chat_id: int, conv_name: str):
        conv_id = await self.gen_conv_id()
        await self.conn.execute(
            "INSERT INTO convs (chat_id, conv_id, conv_name) VALUES ($1, $2, $3)",
            chat_id, conv_id, conv_name
        )
        return conv_id

    async def clear_answers(self, conv_id: int):
        await self.conn.execute(
            "UPDATE questions SET answer=NULL WHERE conv_id=$1",
            conv_id
        )

    async def delete_chatlogs(self, conv_id: int):
        await self.conn.execute(
            "DELETE FROM chatlogs WHERE conv_id=$1",
            conv_id
        )

    async def set_status(self, conv_id: int, concluded_status: bool, started_status: bool):
        await self.conn.execute(
            "UPDATE convs SET is_concluded=$1, is_started=$2 WHERE conv_id=$3",
            concluded_status, started_status, conv_id
        )

    async def get_next_question(self, conv_id: int):
        res = await self.conn.fetchrow(
            "SELECT question_id, question_text\n"
            "FROM questions\n"
            "WHERE conv_id = $1 AND answer IS NULL\n"
            "ORDER BY question_id\n"
            "LIMIT 1\n",
            conv_id
        )
        return {'question_id': res['question_id'], 'question_text': res['question_text']} if res else None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.conn.close()
