from google import genai
from app.core.config import settings

class LLMHandler:
    def __init__(self):
        # The client automatically looks for GOOGLE_API_KEY if not passed
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_id = "gemini-1.5-flash"

    async def generate_structured(self, prompt: str, response_model):
        """
        Sends a prompt and forces the response into a Pydantic model structure.
        """
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': response_model, # Forces structural adherence
            }
        )
        return response.parsed # Returns the data already as a Pydantic object