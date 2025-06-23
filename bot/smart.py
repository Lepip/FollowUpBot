import os
from mistralai import Mistral

class MistralAPI:
    '''LLM. Uses Mistral API. Generate expects format [{"role": "user", "content": "Hello, how are you?"}, ...]. System prompt may be only one and placed before every other message.'''
    def __init__(self, token: str, model: str = "mistral-large-latest"):
        self.api = Mistral(api_key=token)
        self.model = model
    
    def generate(self, messages: list[str]) -> str:
        chat_response = self.api.chat.complete(
            model=self.model, messages=messages
        )
        return chat_response.choices[0].message.content

    def generate_stream(self, messages: list[str]):
        for chunk in self.api.chat.complete_stream( model=self.model, messages=messages ):
            yield chunk.choices[0].delta.content

