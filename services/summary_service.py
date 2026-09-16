from pathlib import Path

from app.core.config import settings
from app.services.llm_factory import get_chat_llm


def _load_prompt() -> str:
    prompt_path = Path("app/core/prompts/patient_summary.prompt")
    return prompt_path.read_text(encoding="utf-8")


def generate_patient_summary(transcript: str) -> str:
    from langchain_core.prompts import PromptTemplate

    prompt = PromptTemplate(template=_load_prompt(), input_variables=["transcript"])

    llm = get_chat_llm()

    msg = (prompt | llm).invoke({"transcript": transcript})
    return getattr(msg, "content", str(msg)).strip()
