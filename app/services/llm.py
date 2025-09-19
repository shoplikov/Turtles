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
        "You are a helpful assistant that converts natural language instructions into structured Jira task data.\n"
        "Extract the following information from the user's instruction:\n"
        "- summary: A brief title for the task (required)\n"
        "- description: Detailed description of the task (required)\n"
        "- priority: One of [Highest, High, Medium, Low, Lowest] (default: Medium)\n"
        "- issue_type: One of [Task, Bug, Story, Epic] (default: Task)\n"
        "- labels: List of relevant labels (optional)\n"
        "- components: List of components (optional)\n\n"
        "Return the result as a valid JSON object with these fields.\n"
        "If information is not provided, use sensible defaults or omit optional fields."
    )

    user_prompt = (
        f"Convert this instruction into a Jira task for project {project_key}:\n\n"
        f"{instruction}\n\n"
        "Return only the JSON object, no additional text."
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


