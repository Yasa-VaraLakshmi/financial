from crewai import Task

def build_tasks(agents: dict) -> list[Task]:
    verification_task = Task(
        description=(
            "Review the provided document excerpt and determine if it looks like a financial document.\n"
            "Document excerpt:\n{document_excerpt}\n\n"
            "Return:\n"
            "1) A yes/no decision\n"
            "2) 3 short evidence points from the excerpt\n"
            "3) Any confidence limitations"
        ),
        expected_output=(
            "A concise verification report with decision, evidence bullets, and confidence notes."
        ),
        agent=agents["verifier"],
        async_execution=False,
    )

    analysis_task = Task(
        description=(
            "Answer the user query using only the document excerpt.\n"
            "User query: {query}\n\n"
            "Document excerpt:\n{document_excerpt}\n\n"
            "Rules:\n"
            "- Do not invent facts.\n"
            "- If information is missing, say 'Not stated in the document'.\n"
            "- Provide a structured response: Summary, Key Metrics, Risks, and Practical Next Steps.\n"
            "- Include a short disclaimer that this is not financial advice."
        ),
        expected_output=(
            "A structured financial analysis grounded in the provided document excerpt, with explicit uncertainty handling."
        ),
        agent=agents["analyst"],
        async_execution=False,
        context=[verification_task],
    )

    return [verification_task, analysis_task]
