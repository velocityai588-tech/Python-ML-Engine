from google import genai  # <--- Ensure this matches exactly
from app.core.config import settings

class LLMHandler:
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_id = "gemini-2.5-flash" 

    async def generate_structured(self, prompt: str, response_model):
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': response_model,
            }
        )
        return response.parsed