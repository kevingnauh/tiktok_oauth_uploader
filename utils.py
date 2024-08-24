# handles error logging and retry logic

import logging
import os
import traceback
from config import MAX_RETRIES
import sys
import json

# Configure logging
logging.basicConfig(
    filename='upload.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s'
)

def log_error(message):
    exc_type, exc_value, exc_traceback = sys.exc_info()
    filename = os.path.basename(exc_traceback.tb_frame.f_code.co_filename)
    lineno = exc_traceback.tb_lineno
    logging.error(f"{message} (Error in {filename} at line {lineno})")


def retry_on_failure(function):
    def wrapper(*args, **kwargs):
        for attempt in range(MAX_RETRIES):
            try:
                return function(*args, **kwargs)
            except Exception as e:
                log_error(f'Attempt {attempt + 1} failed: {e}')
                traceback.print_exc()  
        raise Exception('Max retries reached')
    return wrapper


def read_json(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def get_access_token_from_file(user, filename):
    tokens = read_json(filename)
    data = tokens[user]
    return data['access_token']

