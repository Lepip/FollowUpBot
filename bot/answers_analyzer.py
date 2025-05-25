from bot.prompt_engineer import PromptEngineer
from utils.database import Database
from bot.questionnaire import parse_json_to_questions
import logging
log = logging.getLogger(__name__)
import time

def construct_questions(questions):
    result = []
    for q in questions:
        result.append({"id": q.id, "text": q.text})
        if q.if_cond:
            result.extend(construct_questions(q.questions))
    return result

def parse_answers(answers):
    lines = answers.strip().split('\n')
    texts = {}
    for line in lines:
        if ':' in line:
            parts = line.split(':', 1)
            id = int(parts[0].strip())
            text = parts[1].strip()
            texts[id] = text if text.lower() != 'none' else None
        else:
            texts[id] = None
    return texts
        
async def analyze_answers(chat_id: int, llm):
    stages = PromptEngineer.load_stages()
    max_stage_id = len(stages)
    analysis = []
    questions = []
    for stage_id in range(1, max_stage_id + 1):
        async with Database() as db:
            messages = await db.get_stage_messages(chat_id, stage_id - 1)
        stage_questions = stages[stage_id - 1]['questions']
        stage_questions = parse_json_to_questions(stage_questions)
        stage_questions = construct_questions(stage_questions)
        questions.extend(stage_questions)
        messages.append({'role': 'user', 'content': PromptEngineer.prompt_answers_list(stage_questions)})
        answer = llm.generate(messages)
        log.info(f"Answers analysis for stage {stage_id}: {answer}")
        analysis.append(answer)
        time.sleep(3)
    analysis = "\n".join(analysis)
    async with Database() as db:
        await db.insert_answers(chat_id, questions, parse_answers(analysis))
    return analysis

