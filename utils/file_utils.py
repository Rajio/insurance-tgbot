import os
import json
import uuid
from datetime import datetime
from typing import Optional
from config.settings import settings
from utils.logging_utils import logger

def ensure_directories_exist():
    """Create necessary directories if they don't exist"""
    os.makedirs(settings.DOWNLOADS_DIR, exist_ok=True)
    os.makedirs(settings.MINDEE_DATA_DIR, exist_ok=True)

def save_mindee_response(job_id: str, response: dict) -> Optional[str]:
    """Save Mindee API response to a file"""
    try:
        filename = f"{settings.MINDEE_DATA_DIR}/mindee_response_{job_id}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(response, f, ensure_ascii=False, indent=4)
        return filename
    except Exception as e:
        logger.error(f"Error saving JSON: {e}")
        return None

def generate_policy_filename(passport_data: dict) -> str:
    """Generate filename for insurance policy"""
    name = f"{passport_data.get('given_name', '')}_{passport_data.get('surname', '')}".strip()
    return f"insurance_{name}_{datetime.now().strftime('%Y%m%d')}.txt"