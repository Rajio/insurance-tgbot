import requests
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict
from config.settings import settings

logger = logging.getLogger(__name__)

class GroqService:
    """Service for interacting with Groq API"""
    
    def __init__(self):
        self.api_url = settings.GROQ_API_URL
        self.headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
    
    async def chat_completion(self, system: str, user: str) -> Optional[str]:
        data = {
            "model": settings.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": settings.GROQ_TEMPERATURE
        }
        
        try:
            response = requests.post(
                self.api_url, 
                headers=self.headers, 
                json=data, 
                timeout=settings.GROQ_TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"Groq API error: {str(e)}")
            return None
    
    async def generate_insurance_policy(self, data: dict) -> str:
        """Generate insurance policy text using Groq API"""
        passport_data = data.get('passport_data', {})
        vehicle_data = data.get('vehicle_data', {})
        
        current_date = datetime.now().strftime("%d.%m.%Y")
        policy_number = f"POL-{uuid.uuid4().hex[:6].upper()}"
        
        prompt = (
            "Створи офіційний текст страхового поліса українською мовою з наступними даними:\n"
            f"1. Номер поліса: {policy_number}\n"
            f"2. Дата оформлення: {current_date}\n"
            f"3. Страхувальник: {passport_data.get('given_name', '')} {passport_data.get('surname', '')}\n"
            f"4. Паспорт: {passport_data.get('passport_number', '')}\n"
            f"5. Дата народження: {passport_data.get('birth_date', '')}\n"
            f"6. Автомобіль: {vehicle_data.get('make', '')}\n"
            f"7. Номерний знак: {vehicle_data.get('vehicle_registration_number', '')}\n"
            f"8. VIN: {vehicle_data.get('vehicle_identification_number', '')}\n"
            f"9. Дата реєстрації ТЗ: {vehicle_data.get('registration_date', '')}\n"
            "10. Умови страхування: базове покриття, термін дії 1 рік, вартість 100 USD\n\n"
            "Додай стандартні пункти страхового поліса, підпис та печатку."
        )
        
        system_prompt = (
            "Ти - асистент з оформлення страхової документації. "
            "Створюй офіційні, професійні тексти страхових полісів українською мовою. "
            "Використовуй стандартні формулювання та юридично коректні терміни. "
            "Включи всі обов'язкові реквізити страхового поліса."
        )
        
        policy_text = await self.chat_completion(
            system=system_prompt,
            user=prompt
        )
        
        if not policy_text:
            policy_text = self._generate_fallback_policy(policy_number, current_date, passport_data, vehicle_data)
        
        return policy_text
    
    def _generate_fallback_policy(self, policy_number: str, current_date: str, 
                                passport_data: dict, vehicle_data: dict) -> str:
        """Generate a fallback policy if Groq API fails"""
        return (
            f"СТРАХОВИЙ ПОЛІС №{policy_number}\n\n"
            f"Дата оформлення: {current_date}\n\n"
            "Страхувальник:\n"
            f"ПІБ: {passport_data.get('given_name', '')} {passport_data.get('surname', '')}\n"
            f"Паспорт: {passport_data.get('passport_number', '')}\n"
            f"Дата народження: {passport_data.get('birth_date', '')}\n\n"
            "Об'єкт страхування:\n"
            f"Марка: {vehicle_data.get('make', '')}\n"
            f"Номерний знак: {vehicle_data.get('vehicle_registration_number', '')}\n"
            f"VIN: {vehicle_data.get('vehicle_identification_number', '')}\n"
            f"Дата реєстрації: {vehicle_data.get('registration_date', '')}\n\n"
            "Умови страхування:\n"
            "- Вид: Автоцивілка (ОСЦПВ)\n"
            "- Термін дії: 1 рік\n"
            "- Сума: 100 USD\n"
            "- Територія: Україна\n\n"
            "Особливі умови:\n"
            "Страхувальник зобов'язаний повідомляти про будь-які зміни.\n\n"
            f"Дата: {current_date}\n"
            "Підпис: ___________\n"
            "Печатка: ___________"
        )