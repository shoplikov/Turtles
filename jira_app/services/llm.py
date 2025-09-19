import json
from typing import Dict, Any
from openai import OpenAI
from fastapi import HTTPException

from app.core.config import get_settings


_openai_client: OpenAI | None = None


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        settings = get_settings()
        _openai_client = OpenAI(
            base_url=settings.openai_base_url or "https://vsjz8fv63q4oju-8000.proxy.runpod.net/v1",
            api_key=settings.openai_api_key or "",
        )
    return _openai_client


def parse_instruction_with_llm(instruction: str, project_key: str) -> Dict[str, Any]:
    system_prompt = (
        "You are a senior product manager and Jira expert. Convert a short, possibly messy, natural-language instruction into a polished Jira issue for a software team.\n\n"
        "Language & tone:\n"
        "- Preserve the user's language. If the instruction is in Russian, produce the summary and description in clear, professional Russian suitable for Jira. Do not translate unless explicitly requested.\n"
        "- Use concise, action-oriented, neutral tone.\n\n"
        "Extract the following fields:\n"
        "- summary: <= 120 characters, start with an imperative verb, no trailing period (required).\n"
        "- description: A well-structured description (required). If the input is Russian, use Russian section headers. Prefer the following sections when applicable:\n"
        "  - Контекст / Context: brief background and goal.\n"
        "  - Требования / Requirements: what must be done.\n"
        "  - Критерии приемки / Acceptance Criteria: bullet points; use Given/When/Then where possible.\n"
        "  - Шаги реализации / Implementation Steps: optional, concise steps.\n"
        "  - Зависимости / Dependencies: optional.\n"
        "  - Вне рамок / Out of Scope: optional.\n"
        "- priority: One of [Highest, High, Medium, Low, Lowest] (default: Medium). Map common Russian urgency words: 'срочно/критично'→Highest, 'важно'→High, 'обычно'→Medium, 'низкий'→Low.\n"
        "- issue_type: One of [Task, Bug, Story, Epic] (default: Task). Infer Bug if the text mentions 'ошибка', 'баг', 'не работает', 'исправить'.\n"
        "- labels: Up to 3 short, relevant, lower-kebab-case tags. Use provided hashtags or tags if present.\n"
        "- components: List of components if they are explicitly and unambiguously mentioned.\n"
        "- assignee: Include if a specific person/email/account is clearly requested (e.g., '@ivanov', full name, or email).\n\n"
        "Output rules:\n"
        "- Return a single valid JSON object with ONLY these fields: summary, description, priority, issue_type, labels, components, assignee.\n"
        "- Do not include code fences, backticks, or any extra commentary."
    )

    user_prompt = (
        f"Convert the following instruction into a Jira issue for project {project_key}.\n"
        f"Rewrite informal Russian (if present) into a crisp, professional Jira-friendly summary and description, following the guidelines.\n\n"
        f"Instruction:\n{instruction}\n\n"
        "Return only the JSON object, with no extra text or code fences."
    )

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        settings = get_settings()
        client = get_openai_client()
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            max_tokens=512,
            temperature=0.3,
            stream=False,
        )

        result = response.choices[0].message.content
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]

        parsed_data = json.loads(result.strip())

        if "summary" not in parsed_data or "description" not in parsed_data:
            raise ValueError("Missing required fields: summary and description")

        return parsed_data

    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"LLM returned invalid JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing instruction with LLM: {str(e)}")


