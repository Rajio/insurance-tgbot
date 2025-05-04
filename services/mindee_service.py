import time
import requests
from requests.exceptions import RequestException
import logging
from typing import Optional, Dict
from config.settings import settings

logger = logging.getLogger(__name__)

class MindeeBaseAPI:
    """Base class for Mindee API services"""
    
    def __init__(self):
        self.max_attempts = 5
        self.retry_delay = 2
        self.timeout = 30  # Спеціальний timeout для Mindee API
        
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with error handling and rate limit management"""
        for attempt in range(self.max_attempts):
            try:
                # Видаляємо timeout з kwargs, якщо він там є
                kwargs.pop('timeout', None)
                response = requests.request(
                    method, 
                    url, 
                    timeout=self.timeout,
                    **kwargs
                )
                
                # Обробка 429 помилки
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', self._calculate_backoff(attempt)))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                    
                response.raise_for_status()
                return response
                
            except RequestException as e:
                if hasattr(e, 'response') and e.response is not None and e.response.status_code == 429:
                    retry_after = int(e.response.headers.get('Retry-After', self._calculate_backoff(attempt)))
                    logger.warning(f"Rate limited (exception). Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                    
                logger.error(f"Request failed (attempt {attempt+1}): {str(e)}")
                if attempt == self.max_attempts - 1:
                    raise
                time.sleep(self._calculate_backoff(attempt))
                
            except Exception as e:
                logger.error(f"Unexpected error (attempt {attempt+1}): {str(e)}")
                if attempt == self.max_attempts - 1:
                    raise
                time.sleep(self._calculate_backoff(attempt))
    
    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff time"""
        return min(self.retry_delay * (2 ** attempt), 60)  # Максимум 60 секунд

class MindeePassportAPI(MindeeBaseAPI):
    """Service for passport document processing"""
    
    def __init__(self):
        super().__init__()
        self.api_url = "https://api.mindee.net/v1/products/Rajiole/id_card/v1/predict_async"
        self.headers = {"Authorization": f"Token {settings.MINDEE_API_KEY}"}
        self.retry_delay = 3
        
    def upload_document(self, file_path: str) -> Optional[str]:
        try:
            with open(file_path, 'rb') as f:
                files = {'document': f}
                response = self._make_request(
                    'POST', 
                    self.api_url,
                    headers=self.headers,
                    files=files
                )
            
            logger.info(f"Mindee upload response: {response.text}")
            
            if response.status_code == 202:
                response_data = response.json()
                if 'job' in response_data and 'id' in response_data['job']:
                    return response_data['job']['id']
            
            logger.error(f"Mindee upload failed with status {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Exception in upload_document: {str(e)}", exc_info=True)
            return None
    
    def get_result(self, job_id: str) -> Optional[Dict]:
        if not job_id:
            return None
            
        url = f"https://api.mindee.net/v1/products/Rajiole/id_card/v1/documents/queue/{job_id}"
        
        for attempt in range(self.max_attempts):
            try:
                response = self._make_request('GET', url, headers=self.headers)
                data = response.json()
                
                logger.info(f"Mindee status check attempt {attempt+1}")
                
                if data.get('job', {}).get('status') == "completed":
                    if 'document' in data and 'id' in data['document']:
                        document_id = data['document']['id']
                        return self._get_document_data(document_id)
                    return data
                elif data.get('job', {}).get('status') == "failed":
                    logger.error(f"Mindee processing failed: {data}")
                    return None
                    
                time.sleep(self._calculate_backoff(attempt))
            except Exception as e:
                logger.error(f"Error checking status (attempt {attempt+1}): {str(e)}")
                if attempt == self.max_attempts - 1:
                    return None
                time.sleep(self._calculate_backoff(attempt))
        
        logger.error(f"Max attempts reached for job {job_id}")
        return None
    
    def _get_document_data(self, document_id: str) -> Optional[Dict]:
        url = f"https://api.mindee.net/v1/products/Rajiole/id_card/v1/documents/{document_id}"
        
        try:
            response = self._make_request('GET', url, headers=self.headers)
            return response.json()
        except Exception as e:
            logger.error(f"Error getting document data: {str(e)}")
            return None
    
    @staticmethod
    def extract_passport_data(response: Dict) -> Optional[Dict]:
        if not response:
            return None
            
        try:
            prediction = response.get('document', {}).get('inference', {}).get('prediction', {})
            
            return {
                'document_type': prediction.get('document_type', {}).get('value'),
                'document_number': prediction.get('document_number', {}).get('value'),
                'surname': prediction.get('surnames', {}).get('value'),
                'given_name': prediction.get('given_names', {}).get('value'),
                'sex': prediction.get('sex', {}).get('value'),
                'birth_date': prediction.get('birth_date', {}).get('value'),
                'nationality': prediction.get('nationality', {}).get('value'),
                'personal_number': prediction.get('personal_number', {}).get('value'),
                'country_of_issue': prediction.get('country_of_issue', {}).get('value'),
                'issue_date': prediction.get('issue_date', {}).get('value'),
                'expiration_date': prediction.get('expiration_date', {}).get('value'),
                'tech_passport': None
            }
        except Exception as e:
            logger.error(f"Error parsing data: {e}", exc_info=True)
            return None

class MindeeVehicleAPI(MindeeBaseAPI):
    """Service for vehicle document processing"""
    
    def __init__(self):
        super().__init__()
        self.api_url = "https://api.mindee.net/v1/products/Rajiole/vehicle_registration_certificates/v1/predict_async"
        self.headers = {"Authorization": f"Token {settings.MINDEE_API_KEY}"}
        
    def upload_document(self, file_path: str) -> Optional[str]:
        try:
            with open(file_path, 'rb') as f:
                files = {'document': f}
                response = self._make_request(
                    'POST', 
                    self.api_url,
                    headers=self.headers,
                    files=files
                )
            
            logger.info(f"Mindee vehicle upload response: {response.text}")
            
            if response.status_code == 202:
                response_data = response.json()
                if 'job' in response_data and 'id' in response_data['job']:
                    return response_data['job']['id']
            
            logger.error(f"Mindee vehicle upload failed with status {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Exception in upload_vehicle_document: {str(e)}", exc_info=True)
            return None
    
    def get_result(self, job_id: str) -> Optional[Dict]:
        if not job_id:
            return None
            
        url = f"https://api.mindee.net/v1/products/Rajiole/vehicle_registration_certificates/v1/documents/queue/{job_id}"
        
        for attempt in range(self.max_attempts):
            try:
                response = self._make_request('GET', url, headers=self.headers)
                data = response.json()
                
                logger.info(f"Mindee vehicle status check attempt {attempt+1}")
                
                if data.get('job', {}).get('status') == "completed":
                    if 'document' in data and 'id' in data['document']:
                        document_id = data['document']['id']
                        return self.get_document_data(document_id)
                    return data
                elif data.get('job', {}).get('status') == "failed":
                    logger.error(f"Mindee vehicle processing failed: {data}")
                    return None
                    
                time.sleep(self._calculate_backoff(attempt))
            except Exception as e:
                logger.error(f"Error checking vehicle status (attempt {attempt+1}): {str(e)}")
                if attempt == self.max_attempts - 1:
                    return None
                time.sleep(self._calculate_backoff(attempt))
        
        logger.error(f"Max attempts reached for vehicle job {job_id}")
        return None
    
    def get_document_data(self, document_id: str) -> Optional[Dict]:
        url = f"https://api.mindee.net/v1/products/Rajiole/vehicle_registration_certificates/v1/documents/{document_id}"
        
        try:
            response = self._make_request('GET', url, headers=self.headers)
            return response.json()
        except Exception as e:
            logger.error(f"Error getting vehicle document data: {str(e)}")
            return None
    
    @staticmethod
    def extract_vehicle_data(response: Dict) -> Optional[Dict]:
        if not response:
            return None
            
        try:
            prediction = response.get('document', {}).get('inference', {}).get('prediction', {})
            
            vehicle_data = {
                'vehicle_registration_number': prediction.get('vehicle_registration_number', {}).get('value', None),
                'registration_date': prediction.get('registration_date', {}).get('value', None),
                'owner_name': prediction.get('owner_name', {}).get('value', None),
                'vehicle_identification_number': prediction.get('vehicle_identification_number', {}).get('value', None),
                'make': prediction.get('make', {}).get('value', None),
                'insurance_details': prediction.get('insurance_details', [])
            }
            
            return {k: v for k, v in vehicle_data.items() if v is not None}
        except Exception as e:
            logger.error(f"Error parsing vehicle data: {e}", exc_info=True)
            return None