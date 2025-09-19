from typing import Optional, Dict, Any
import httpx
from fastapi import HTTPException

from app.core.config import get_settings


class JiraMCPClient:
    def __init__(self, base_url: str, email: str, api_token: str) -> None:
        self.base_url = base_url.rstrip('/')
        self.auth = httpx.BasicAuth(email, api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._issuetype_cache: Dict[str, Any] = {}
        self._createmeta_fields_cache: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _normalize_issuetype_name(name: str) -> str:
        s = (name or "").strip().lower()
        s = s.replace("_", " ")
        s = s.replace("-", " ")
        s = " ".join(s.split())
        if s == "user story" or s == "story":
            return "story"
        if s in {"sub task", "subtask"}:
            return "sub-task"
        return s

    async def _get_project_issue_types(self, project_key: str) -> Any:
        if project_key in self._issuetype_cache:
            return self._issuetype_cache[project_key]

        url = f"{self.base_url}/rest/api/3/issue/createmeta"
        params = {"projectKeys": project_key, "expand": "projects.issuetypes"}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, auth=self.auth, headers=self.headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Failed to fetch issue types: {resp.text}")
        data = resp.json() or {}
        projects = data.get("projects", [])
        if not projects:
            params = {"projectKey": project_key, "expand": "projects.issuetypes"}
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, auth=self.auth, headers=self.headers)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"Failed to fetch issue types: {resp.text}")
            data = resp.json() or {}
            projects = data.get("projects", [])

        if not projects:
            raise HTTPException(status_code=400, detail=f"No project metadata found for '{project_key}'. Check project key and permissions.")

        issuetypes = projects[0].get("issuetypes", [])
        self._issuetype_cache[project_key] = issuetypes
        return issuetypes

    async def _resolve_issue_type_payload(self, project_key: str, requested_issue_type: Optional[str]) -> Dict[str, Any]:
        issuetypes = await self._get_project_issue_types(project_key)
        available = [(it.get("id"), it.get("name"), it.get("subtask", False)) for it in issuetypes]

        def choose_default() -> Optional[Dict[str, Any]]:
            preferred_order = ["task", "bug", "story", "epic"]
            normalized_map = {self._normalize_issuetype_name(n or ""): (i, n, sub) for i, n, sub in available}
            for pref in preferred_order:
                if pref in normalized_map and not normalized_map[pref][2]:
                    iid, name, _ = normalized_map[pref]
                    return {"id": iid}
            for iid, name, sub in available:
                if not sub:
                    return {"id": iid}
            if available:
                iid, name, _ = available[0]
                return {"id": iid}
            return None

        if not requested_issue_type:
            payload = choose_default()
            if payload:
                return payload
            raise HTTPException(status_code=400, detail="No issue types available for this project")

        req_norm = self._normalize_issuetype_name(requested_issue_type)

        for iid, name, sub in available:
            if name and name.strip().lower() == requested_issue_type.strip().lower():
                return {"id": iid}

        for iid, name, sub in available:
            if self._normalize_issuetype_name(name or "") == req_norm:
                return {"id": iid}

        payload = choose_default()
        if payload:
            return payload

        valid_names = [n for _, n, _ in available if n]
        raise HTTPException(status_code=400, detail=f"Invalid issue type '{requested_issue_type}'. Valid types: {', '.join(valid_names)}")

    async def _get_createmeta_fields(self, project_key: str, issuetype_id: str) -> Dict[str, Any]:
        cache_key = f"{project_key}:{issuetype_id}"
        if cache_key in self._createmeta_fields_cache:
            return self._createmeta_fields_cache[cache_key]

        url = f"{self.base_url}/rest/api/3/issue/createmeta"
        params = {
            "projectKeys": project_key,
            "issuetypeIds": issuetype_id,
            "expand": "projects.issuetypes.fields",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, auth=self.auth, headers=self.headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"Failed to fetch create metadata: {resp.text}")
        data = resp.json() or {}
        projects = data.get("projects", [])
        if not projects:
            proj_resp = None
            try:
                async with httpx.AsyncClient() as client:
                    proj_resp = await client.get(f"{self.base_url}/rest/api/3/project/{project_key}", auth=self.auth, headers=self.headers)
                if proj_resp.status_code == 200:
                    project_id = (proj_resp.json() or {}).get("id")
                    if project_id:
                        params = {
                            "projectIds": project_id,
                            "issuetypeIds": issuetype_id,
                            "expand": "projects.issuetypes.fields",
                        }
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(url, params=params, auth=self.auth, headers=self.headers)
                        if resp.status_code == 200:
                            data = resp.json() or {}
                            projects = data.get("projects", [])
            except Exception:
                pass

        if not projects:
            raise HTTPException(status_code=400, detail=f"No project metadata found for '{project_key}'. Check project key and permissions.")

        issuetypes = projects[0].get("issuetypes", [])
        fields: Dict[str, Any] = {}
        for it in issuetypes:
            if str(it.get("id")) == str(issuetype_id):
                fields = it.get("fields", {}) or {}
                break

        self._createmeta_fields_cache[cache_key] = fields
        return fields

    @staticmethod
    def _normalize_priority_name(name: str) -> str:
        s = (name or "").strip().lower()
        s = s.replace("_", " ").replace("-", " ")
        s = " ".join(s.split())
        if s in {"p0", "blocker", "critical", "urgent"}:
            return "highest"
        if s in {"p1", "major"}:
            return "high"
        if s in {"p2", "normal"}:
            return "medium"
        if s in {"p3", "minor"}:
            return "low"
        if s in {"p4", "trivial"}:
            return "lowest"
        return s

    async def _resolve_priority_payload(self, project_key: str, issuetype_id: str, requested_priority: Optional[str]) -> Optional[Dict[str, Any]]:
        if not requested_priority:
            return None
        fields = await self._get_createmeta_fields(project_key, issuetype_id)
        pr_field = fields.get("priority")
        if not pr_field:
            return None
        allowed = pr_field.get("allowedValues") or []
        if not allowed:
            return None

        req = requested_priority.strip().lower()
        req_norm = self._normalize_priority_name(requested_priority)

        for val in allowed:
            name = (val.get("name") or "").strip().lower()
            if name == req:
                return {"id": val.get("id")}

        for val in allowed:
            name = val.get("name")
            if self._normalize_priority_name(name) == req_norm:
                return {"id": val.get("id")}

        return None

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Task",
        priority: str = "Medium",
        labels: list | None = None,
        components: list | None = None,
        assignee: str | None = None,
    ) -> Dict[str, Any]:
        issuetype_payload = await self._resolve_issue_type_payload(project_key, issue_type)
        issuetype_id = issuetype_payload.get("id")

        issue_data: Dict[str, Any] = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {"type": "text", "text": description}
                            ],
                        }
                    ],
                },
                "issuetype": issuetype_payload,
            }
        }

        if issuetype_id:
            priority_payload = await self._resolve_priority_payload(project_key, issuetype_id, priority)
            if priority_payload:
                issue_data["fields"]["priority"] = priority_payload
        if labels:
            issue_data["fields"]["labels"] = labels
        if components:
            issue_data["fields"]["components"] = [{"name": c} for c in components]
        if assignee:
            issue_data["fields"]["assignee"] = {"accountId": assignee}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/rest/api/3/issue",
                json=issue_data,
                auth=self.auth,
                headers=self.headers,
            )

            if response.status_code == 201:
                return response.json()
            else:
                error_detail = None
                try:
                    error_json = response.json()
                    messages = []
                    if isinstance(error_json, dict):
                        if error_json.get("errorMessages"):
                            messages.extend(error_json["errorMessages"])
                        if error_json.get("errors") and isinstance(error_json["errors"], dict):
                            messages.extend([f"{k}: {v}" for k, v in error_json["errors"].items()])
                    error_detail = "; ".join(messages) if messages else None
                except Exception:
                    pass

                if not error_detail:
                    error_detail = response.text or getattr(response, "reason_phrase", "") or "Unknown error"

                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to create Jira issue ({response.status_code}): {error_detail}",
                )


_jira_singleton: JiraMCPClient | None = None


def get_jira_client() -> JiraMCPClient:
    global _jira_singleton
    if _jira_singleton is None:
        settings = get_settings()
        _jira_singleton = JiraMCPClient(
            base_url=settings.jira_base_url or "https://alishshop17.atlassian.net",
            email=settings.jira_email or "alishshop17@gmail.com",
            api_token=settings.jira_api_token or "",
        )
    return _jira_singleton


