import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    MINDEE_API_KEY = os.getenv("MINDEE_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    
    # File paths
    DOWNLOADS_DIR = "downloads"
    MINDEE_DATA_DIR = "mindee_data"
    
    # API settings
    MINDEE_MIN_REQUEST_INTERVAL = 3
    MINDEE_MAX_ATTEMPTS = 10
    MINDEE_RETRY_DELAY = 3
    
    GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_MODEL = "mixtral-8x7b-32768"
    GROQ_TEMPERATURE = 0.7
    GROQ_TIMEOUT = 30
    
settings = Settings()