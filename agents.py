import os
from dotenv import load_dotenv
from crewai import Agent

load_dotenv()


def _model_name() -> str:
    return os.getenv("CREWAI_MODEL", "gpt-4o-mini")


def create_agents() -> dict:
    llm = _model_name()

    document_verifier = Agent(
        role="Financial Document Verifier",
        goal="Verify whether the provided text appears to be a financial document and summarize what evidence supports that conclusion.",
        backstory=(
            "You are a strict compliance-oriented verifier. You do not guess or invent facts. "
            "If evidence is missing, you explicitly say so."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    financial_analyst = Agent(
        role="Senior Financial Analyst",
        goal="Answer the user's financial analysis question using only information present in the provided document excerpt.",
        backstory=(
            "You produce evidence-based analysis, quantify uncertainty, and avoid speculation. "
            "You are explicit about assumptions and data gaps."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    return {
        "verifier": document_verifier,
        "analyst": financial_analyst,
    }
