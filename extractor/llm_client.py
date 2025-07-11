import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from app.core.logger import setup_logger

logger = setup_logger()

def get_llm():
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    model_name = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
    logger.info(f"Initializing LLM with provider: {provider}, model: {model_name}")
    if provider == "gemini":
        if not api_key:
            logger.error("Google Gemini API key not found in environment variables.")
            raise ValueError("Google Gemini API key not found.")
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)
    elif provider == "openai":
        if not api_key:
            logger.error("OpenAI API key not found in environment variables.")
            raise ValueError("OpenAI API key not found.")
        return ChatOpenAI(model=model_name, api_key=api_key)
    else:
        logger.error(f"Unsupported LLM provider: {provider}")
        raise ValueError(f"Unsupported LLM provider: {provider}")

def get_json_parser():
    logger.debug("Creating JsonOutputParser instance.")
    return JsonOutputParser()

def get_prompt(template: str):
    logger.debug("Creating ChatPromptTemplate from template.")
    return ChatPromptTemplate.from_template(template)
