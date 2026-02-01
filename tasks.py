import os
from celery import Celery
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


app = Celery('tasks', broker=os.getenv('CELERY_BROKER_URL'), backend=os.getenv('CELERY_RESULT_BACKEND'))


genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-2.5-flash')

@app.task(bind=True, max_retries=3)
def retriever_agent(self, query):
    
    try:
        prompt = f"Act as a Retriever Agent. Gather detailed raw information and facts about: {query}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)

@app.task(bind=True, max_retries=3)
def analyzer_agent(self, raw_data):
    
    try:
        prompt = f"Act as an Analyzer Agent. Extract key insights and patterns from this raw data: {raw_data}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)

@app.task(bind=True, max_retries=3)
def writer_agent(self, analysis):
   
    try:
        prompt = f"Act as a Writer Agent. Create a professional report based on these insights: {analysis}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)