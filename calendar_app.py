from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime, timedelta

from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_community.tools.gmail.utils import (
    build_resource_service,
    get_gmail_credentials,
)
import json
from dotenv import load_dotenv
import os
load_dotenv()



MODEL = os.getenv("OPENAI_MODEL", "llama4scout")
API_BASE = os.getenv("OPENAI_BASE_URL")
API_KEY = os.getenv("OPENAI_API_KEY")

TOKEN_FILE = "../token.json"
CLIENT_SECRETS_FILE = "./credentials.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


app = FastAPI(title="Call Analysis API")


class ActionItem(BaseModel):
    action: str = Field(
        ...,
        description="Описание действия, напр. 'Назначить демо на 20 сентября 2025 года в 14:00 по времени Астаны'"
    )
    owner: Optional[str] = Field(None, description="Кто выполняет действие")
    due: Optional[str] = Field(None, description="Дата дедлайна в формате YYYY-MM-DD")
    priority: Optional[str] = Field(None, description="Приоритет: high/medium/low")

    def __str__(self) -> str:
        parts = [f"Действие: {self.action}"]
        if self.owner:
            parts.append(f"Ответственный: {self.owner}")
        if self.due:
            parts.append(f"Срок: {self.due}")
        if self.priority:
            parts.append(f"Приоритет: {self.priority}")
        return " | ".join(parts)


class BestActions(BaseModel):
    actions_list: List[ActionItem] = Field(..., description="Список действий")


best_actions_prompt = PromptTemplate(
    input_variables=["context"],
    template="""
    Ты – эксперт по структурированию данных.  
    Извлеки список действий (next best actions), которые нужно выполнить.  

    Формат ответа (строго JSON):  
    {{
      "actions_list": [
        {{
          "action": "Назначить демо на 20 сентября 2025 года в 14:00 по времени Астаны",
          "owner": "менеджер",
          "due": "2025-09-20",
          "priority": "high"
        }}
      ]
    }}

    Правила:  
    1. Поле `action` всегда содержит полное описание задачи в виде команды.  
    2. Если нет информации о `owner`, `due`, `priority` → укажи null.  
    3. Если действий нет → верни `"actions_list": []`.  
    4. Используй только факты из текста.  

    Контекст:  
    {context}
    """
)


def setup_llm_and_calendar():
    """Setup LLM and Google Calendar service"""
    llm = ChatOpenAI(
        model=MODEL,
        openai_api_base=API_BASE,
        openai_api_key=API_KEY,
        temperature=0,
    )

    credentials = get_gmail_credentials(
        token_file=TOKEN_FILE,
        scopes=SCOPES,
        client_secrets_file=CLIENT_SECRETS_FILE,
    )
    calendar_service = build_resource_service(
        credentials=credentials,
        service_name="calendar",
        service_version="v3"
    )

    return llm, calendar_service



@app.post("/create-event")
async def analyze_call(payload: dict):
    print("Raw payload:", payload["instruction"])

    payload = payload["instruction"]
    # 1. Setup LLM + Calendar
    llm, calendar_service = setup_llm_and_calendar()

    # 2. Extract actions
    llm_structured = llm.with_structured_output(BestActions)
    prompt = best_actions_prompt.format(context=payload)
    actions: BestActions = await llm_structured.ainvoke(prompt)

    # 3. Create events directly in Google Calendar
    created_events = []
    for action in actions.actions_list:
        if action.due:
            start_time = f"{action.due}T14:00:00"
            end_time = f"{action.due}T15:00:00"
        else:
            start_time = datetime.utcnow().isoformat()
            end_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()

        event = {
            "summary": action.action,
            "description": f"Приоритет: {action.priority}, Ответственный: {action.owner}",
            "start": {"dateTime": start_time, "timeZone": "Asia/Almaty"},
            "end": {"dateTime": end_time, "timeZone": "Asia/Almaty"},
        }

        created = calendar_service.events().insert(
            calendarId="primary",
            body=event
        ).execute()
        created_events.append(created)

    return {
        "message": "Events created successfully in Google Calendar",
        "parsed_actions": [str(a) for a in actions.actions_list],
        "created_events": created_events,
    }

