import logging
import json

log = logging.getLogger(__name__)

class PromptEngineer:
    stages_ = None

    @staticmethod
    def get_questions_text(questions):
        log.info(f"get_questions_text: {questions}")
        questions_text = []
        for question in questions:
            question_answer = question['answer'] if question['answer'] is not None else "Нет ответа"
            questions_text.append(f"Вопрос {question['question_id']}: {question['question_text']}. Ответ: {question_answer}")
        questions_text = "\n".join(questions_text)
        return questions_text
    
    @staticmethod
    def get_system_prompt(questions):
        system_prompt = "Ты доктор, и ведешь беседу с пациентом. Ты задаешь вопросы, а пациент (юзер) отвечает. Пиши только от лица доктора, только то, что сказал бы доктор в нормальном, неструктуризированном разговоре. Не пиши от лица пациента, не пиши ничего связанного с ответом пациента. Только одну реплику доктора."
        questions_text = PromptEngineer.get_questions_text(questions)
        system_prompt += f"Текущие вопросы и ответы:\n{questions_text}\n\n."
        system_prompt += "Как доктор, узнай ответы от пациента на неотвеченные вопросы. Если пациент не может ответить, переспроси, перефразируй, веди нормальный разговор с пациентом, будь вежливым и усидчивым. Задавай вопросы по одному, не перегружай пациента. Если вопрос сложный, задай его часть так, чтобы пациент мог ответить. Когда все вопросы отвечены, попрощайся с пациентом, поблагодари его и напиши /end."
        return system_prompt
    
    @staticmethod
    def get_question_check_prompt(questions):
        system_prompt = f"Текущие вопросы и ответы:\n{PromptEngineer.get_questions_text(questions)}\n\n."
        system_prompt += "На основе предыдущего ответа пациента, обнови текущий статус ответов на вопросы. Если пациент ответил на какой-то из неотвеченных вопросов, напиши '<Номер вопроса>:<Ответ пациента>', например '3:Да, принимал лекарства.', иначе, напиши 'Нет ответа'."
        return system_prompt
    
    @staticmethod
    def load_stages():
        if PromptEngineer.stages_ is None:
            with open('test_stages.json', 'r', encoding='utf-8') as file: # change to stages.json for production
                PromptEngineer.stages_ = json.load(file)["stages"]
        return PromptEngineer.stages_
    
    @staticmethod
    def get_stage(stage_id):
        if stage_id >= len(PromptEngineer.load_stages()):
            log.warning(f"Stage with id {stage_id} not found")
            return {}
        return PromptEngineer.load_stages()[stage_id]

    @staticmethod
    def initial_response():
        return "Здравствуйте! Вы проходили операцию в нашей клинике и мы хотели бы узнать, как вы себя чувствуете и все ли в порядке. Пожалуйста, ответьте на несколько вопросов."
    
    @staticmethod
    def last_response():
        return "Спасибо! Мы передадим ваши ответы врачу. Если у вас возникнут вопросы, вы всегда можете обратиться к нам."

    @staticmethod
    def initial_system_prompt():
        return "Это звонок с пациентом. Ты - врач, который должен провести разговор с пациентом с целью получения ответов на вопросы из опросника. Задавай вопросы ТОЛЬКО по одному, не нагружай пациента, НИКОГДА НЕ ПЕРЕЧИСЛЯЙ ВОПРОСЫ, это обычный разговор, в разговоре люди отвечают на вопросы по одному, будь вежлив и будь готов переспросить, если пациент не смог ответить. Веди нормальный, человечный, неструктурированный телефонный разговор, никаких дополнительных реплик, только вопросы! Пиши только сам вопрос, как это бы прозвучало в нормальном диалоге. Сами вопросы -- это темы для разговора, не сухие вопросы, перефразируй их как человеческий вопрос от доктора к пациенту. Пиши только от лица врача, никогда не пиши от лица пациента, юзер - пациент. Реплики пациента будут выглядеть \"Пациент: \"*текст того, что сказал пациент*\"\", а твои реплики будут выглядеть \"*текст того, что ты сказал*\". Помимо реплик пациента тебе будет передана информация о вопросах, её видишь только ты, ты отвечаешь только на реплики пациента."
    
    @staticmethod
    def initial_theme_prompt():
        return "Как вы себя сейчас чувствуете? Есть жалобы?"

    @staticmethod
    def construct_questions_prompt(questions, stage_name):
        questions = "\n".join(questions)
        prompt = f"Текущая тема: {stage_name}"
        prompt += f"\n\nВопросы, на которые нужно сейчас получить ответы от пациента:\n{questions}"
        prompt += "\n\nКогда получишь ответы на эти вопросы от пациента, напиши \"\\done\", чтобы продолжить к следующей теме или следующим вопросам."
        return prompt
    
    @staticmethod
    def construct_if_question_prompt(questions, stage_name):
        question = questions[0]
        prompt = f"Текущая тема: {stage_name}"
        prompt += f"\n\nВопрос, на который нужно получить ответ от пациента:\n{question}"
        prompt += "\n\nОт этого вопроса зависит, какие далее вопросы следует задавать. После получения ответа, если пациент ответил положительно, напиши \"\\yes\", если отрицательно, напиши \"\\no\""
        return prompt
    
    @staticmethod
    def prompt_answers_list(questions):
        questions_str = "\n".join([f"{q['id']}: {q['text']}" for q in questions])
        prompt = f"Запиши ответы пациента на следующие вопросы в формате \"id: ответ\", если пациент не дал ответа, напиши None. Вопросы: \n{questions_str}"
        return prompt