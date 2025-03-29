import json
import time
import logging
import requests
from typing import Dict
from beanstalkc import Connection as BeanstalkConnection
from ..config import *

class RemoteServerUploader:
    """Handles remote plate data uploads with retry logic"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'LicensePlateProcessor/2.0',
            'Content-Type': 'application/json'
        })
        if REMOTE_SERVER_API_KEY:
            self.session.headers['Authorization'] = f'Bearer {REMOTE_SERVER_API_KEY}'
    
    def upload(self, plate_data: Dict) -> bool:
        """Attempt to upload plate data with retries"""
        for attempt in range(REMOTE_UPLOAD_RETRIES + 1):
            try:
                response = self.session.post(
                    REMOTE_SERVER_URL,
                    data=json.dumps(plate_data),
                    timeout=10
                )
                if response.ok:
                    return True
                logging.warning(f"Upload failed (attempt {attempt}): {response.status_code}")
            except Exception as e:
                logging.error(f"Upload error: {str(e)}")
            if attempt < REMOTE_UPLOAD_RETRIES:
                time.sleep(2 ** attempt)
        return False

class BeanstalkdQueue:
    """Manages plate data queueing with fallback mechanisms"""
    
    def __init__(self):
        self.connection = None
        self.uploader = RemoteServerUploader() if REMOTE_UPLOAD_ENABLED else None
        self._connect()
    
    def _connect(self) -> bool:
        """Establish Beanstalkd connection"""
        try:
            self.connection = BeanstalkConnection(
                host=BEANSTALKD_HOST,
                port=BEANSTALKD_PORT
            )
            self.connection.use(BEANSTALKD_TUBE)
            return True
        except Exception as e:
            logging.error(f"Beanstalkd connection failed: {str(e)}")
            return False
    
    def put_plate(self, plate_data: Dict) -> bool:
        """Store plate data with remote upload fallback"""
        # Try direct upload first
        if REMOTE_UPLOAD_ENABLED and self.uploader.upload(plate_data):
            logging.info(f"Uploaded plate: {plate_data.get('plate')}")
            return True
        
        # Fallback to Beanstalkd
        if not self.connection and not self._connect():
            return False
        
        try:
            self.connection.put(json.dumps(plate_data))
            logging.info(f"Queued plate: {plate_data.get('plate')}")
            return True
        except Exception as e:
            logging.error(f"Queueing failed: {str(e)}")
            self.connection = None
            return False