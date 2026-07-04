# In this file, you can set the configurations of the app.

from constants import DEBUG

#config related to logging must have prefix LOG_
LOG_LEVEL = DEBUG
LOG_SELENIUM_LEVEL = DEBUG
LOG_TO_FILE = True
LOG_TO_CONSOLE = True

MINIMUM_WAIT_TIME_IN_SECONDS = 60

JOB_APPLICATIONS_DIR = "job_applications"
JOB_SUITABILITY_SCORE = 7

JOB_MAX_APPLICATIONS = 5
JOB_MIN_APPLICATIONS = 1

LLM_ENABLED = True
LLM_PROVIDER = 'ollama'
LLM_MODEL_TYPE = 'ollama'
LLM_MODEL = 'gemma:latest'
OLLAMA_BASE_URL = 'http://127.0.0.1:11434'
LLM_TIMEOUT_SECONDS = 60
LLM_MAX_RETRIES = 2
LLM_API_URL = OLLAMA_BASE_URL