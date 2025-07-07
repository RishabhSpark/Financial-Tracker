import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI


def get_llm():
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    model_name = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
    if provider == "gemini":
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=api_key)
    elif provider == "openai":
        return ChatOpenAI(model=model_name, api_key=api_key)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def get_json_parser():
    return JsonOutputParser()


def get_prompt(template: str):
    return ChatPromptTemplate.from_template(template)
