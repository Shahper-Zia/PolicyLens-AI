import os
from dotenv import load_dotenv
from openai import OpenAI
from src.config.logging import logger
load_dotenv()


def generate(prompt: str) -> str:
    client = OpenAI(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )

    response = client.responses.create(
        model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        input=prompt,
        temperature=0,
    )
    logger.info("Received LLM response")
    return response.output_text
