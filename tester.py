
from openai import OpenAI
import os
client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)
model=os.environ
response = client.responses.create(
    input="Explain the importance of fast language models",
    model="openai/llama-3.3-70b-versatile", 
)
print(response.output_text)
