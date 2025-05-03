import time
import requests
import logging
from typing import Optional, Dict
from config.settings import settings

logger = logging.getLogger(__name__)

class MindeeBaseAPI:
    """Base class for Mindee API services"""
    
    def __init__(self):
        self.last_request_time = 0
        self.min_request_interval = settings.MINDEE_MIN_REQUEST_INTERVAL
        self.max_attempts = settings.MINDEE_MAX_ATTEMPTS
        self.retry_delay = settings.MINDEE_RETRY_DELAY
        
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            logger.info(f"Waiting {sleep_time:.2f}s to avoid rate limiting")
            time.sleep(sleep_time)
        
        try:
            response = requests.request(method, url, **kwargs)
            self.last_request_time = time.time()
            
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', self.retry_delay))
                logger.warning(f"Rate limited, waiting {retry_after}s")
                time.sleep(retry_after)
                return self._make_request(method, url, **kwargs)
                
            return response
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            raise

class MindeePassportAPI(MindeeBaseAPI):
    """Service for passport document processing"""
    
    def __init__(self):
        super().__init__()
        self.api_url = "https://api.mindee.net/v1/products/mindee/international_id/v2/predict_async"
        self.headers = {"Authorization": f"Token {settings.MINDEE_API_KEY}"}
        
    def upload_document(self, file_path: str) -> Optional[str]:
        try:
            with open(file_path, 'rb') as f:
                files = {'document': f}
                response = self._make_request(
                    'POST', 
                    self.api_url, 
                    headers=self.headers, 
                    files=files, 
                    timeout=settings.GROQ_TIMEOUT
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
            
        url = f"https://api.mindee.net/v1/products/mindee/international_id/v2/documents/queue/{job_id}"
        
        for attempt in range(self.max_attempts):
            try:
                response = self._make_request('GET', url, headers=self.headers, timeout=settings.GROQ_TIMEOUT)
                data = response.json()
                
                logger.info(f"Mindee status check attempt {attempt+1}")
                
                if data.get('job', {}).get('status') == "completed":
                    if 'document' in data and 'id' in data['document']:
                        document_id = data['document']['id']
                        return self.get_document_data(document_id)
                    return data
                elif data.get('job', {}).get('status') == "failed":
                    logger.error(f"Mindee processing failed: {data}")
                    return None
                    
                time.sleep(self.retry_delay)
            except Exception as e:
                logger.error(f"Error checking status (attempt {attempt+1}): {str(e)}")
                time.sleep(self.retry_delay)
        
        logger.error(f"Max attempts reached for job {job_id}")
        return None
    
    def get_document_data(self, document_id: str) -> Optional[Dict]:
        url = f"https://api.mindee.net/v1/products/mindee/international_id/v2/documents/{document_id}"
        
        try:
            response = self._make_request('GET', url, headers=self.headers, timeout=settings.GROQ_TIMEOUT)
            response.raise_for_status()
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
            
            surname = prediction.get('surnames', [{}])[0].get('value', 'Не знайдено')
            given_name = prediction.get('given_names', [{}])[0].get('value', 'Не знайдено')
            passport_number = prediction.get('document_number', {}).get('value', 'Не знайдено')
            nationality = prediction.get('nationality', {}).get('value', 'Не знайдено')
            birth_date = prediction.get('birth_date', {}).get('value', 'Не знайдено')

            return {
                'surname': surname,
                'given_name': given_name,
                'passport_number': passport_number,
                'nationality': nationality,
                'birth_date': birth_date,
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
                    files=files, 
                    timeout=settings.GROQ_TIMEOUT
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
                response = self._make_request('GET', url, headers=self.headers, timeout=settings.GROQ_TIMEOUT)
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
                    
                time.sleep(self.retry_delay)
            except Exception as e:
                logger.error(f"Error checking vehicle status (attempt {attempt+1}): {str(e)}")
                time.sleep(self.retry_delay)
        
        logger.error(f"Max attempts reached for vehicle job {job_id}")
        return None
    
    def get_document_data(self, document_id: str) -> Optional[Dict]:
        url = f"https://api.mindee.net/v1/products/Rajiole/vehicle_registration_certificates/v1/documents/{document_id}"
        
        try:
            response = self._make_request('GET', url, headers=self.headers, timeout=settings.GROQ_TIMEOUT)
            response.raise_for_status()
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