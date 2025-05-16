from utils.config import cfg
import logging

log = logging.getLogger(__name__)

DEBUG = cfg["debug"]

class Question:
    def __init__(self, id, text, if_cond=False, questions=None):
        self.id = id
        self.text = text
        self.if_cond = if_cond
        self.questions = questions if questions else []

class Batch:
    def __init__(self, questions=None, batch_if_yes=None, batch_done=None):
        self.questions = questions if questions else []
        self.batch_if_yes = batch_if_yes
        self.batch_done = batch_done
    
    def __repr__(self):
        return f"Batch(questions={self.questions}, batch_if_yes={self.batch_if_yes}, batch_done={self.batch_done})"

def dfs(questions):
    batches = []
    current = Batch()
    linking_out = []
    for q in questions:
        if not q.if_cond:
            current.questions.append(q.text)
            while linking_out:
                linking_out.pop().batch_done = current
        else:
            if current.questions:
                if_batch = Batch()
                current.batch_done = if_batch
                batches.append(current)
                current = if_batch
            current.questions.append(q.text)
            linking_out.append(current)
            new_batches, new_linking_out = dfs(q.questions)
            current.batch_if_yes = new_batches[0] if new_batches else None
            batches.append(current)
            linking_out.extend(new_linking_out)
            batches.extend(new_batches)
            current = Batch()
    if current.questions:
        batches.append(current)
        linking_out.append(current)
    return batches, linking_out

def parse_json_to_questions(json_data):
    def parse_question(dto):
        id = dto["id"]
        text = dto["text"]
        if_cond = dto.get("if", False)
        nested_questions = [parse_question(q) for q in dto.get("questions", [])] if if_cond else []
        return Question(id, text, if_cond, nested_questions)
    
    return [parse_question(q) for q in json_data]

class StageOperator:
    def __init__(self, stage_questions=None, batch_id=0):
        self.current_batch = None
        self.raw = None
        self.questions = None
        self.batches = None
        if stage_questions is not None:
            self.set(stage_questions, batch_id)

    def set(self, stage_questions, batch_id=-1):
        self.raw = stage_questions
        self.questions = parse_json_to_questions(stage_questions)
        self.batches, _ = dfs(self.questions)
        if DEBUG:
            print(f"Batches:")
            for i, batch in enumerate(self.batches, 1):
                if_yes_idx = self.batches.index(batch.batch_if_yes) + 1 if batch.batch_if_yes in self.batches else None
                done_idx = self.batches.index(batch.batch_done) + 1 if batch.batch_done in self.batches else None
                print(f"{i}: (questions={batch.questions}, if_yes={if_yes_idx}, done={done_idx})")
        if batch_id >= len(self.batches):
            log.warning(f"Batch id {batch_id} is out of range. Setting to None.")
            self.current_batch = None
            return
        
        if batch_id < 0:
            self.current_batch = Batch(None, None, (self.batches[0]) if self.batches else None)
        else:
            self.current_batch = self.batches[batch_id]


    def get(self, if_yes: bool = False):
        if self.current_batch is None:
            return None, False
        
        if if_yes and self.current_batch.batch_if_yes is not None:
            self.current_batch = self.current_batch.batch_if_yes
        else:
            self.current_batch = self.current_batch.batch_done
        if self.current_batch is None:
            return None, False
        return (self.current_batch.questions, self.current_batch.batch_if_yes is not None)
    
    def get_current_batch(self):
        return self.current_batch
    
    def get_current_batch_id(self):
        if self.current_batch is None:
            return -1
        return self.batches.index(self.current_batch)
        
        