"""Supabase persistence helpers."""
from __future__ import annotations

import datetime as dt
import importlib
from typing import Any, Dict, List, Optional

from config import settings

if importlib.util.find_spec("supabase"):
    from supabase import Client, create_client  # type: ignore
else:  # pragma: no cover - supabase optional during local dev
    Client = None  # type: ignore
    create_client = None  # type: ignore


class DatabaseService:
    """A thin wrapper around Supabase for assumptions and projects."""

    def __init__(self) -> None:
        self._client: Optional[Client] = None
        if settings.supabase_url and settings.supabase_key and create_client:
            try:
                self._client = create_client(settings.supabase_url, settings.supabase_key)
            except Exception:
                self._client = None
        self._memory_projects: Dict[str, Dict[str, Any]] = {}
        self._memory_assumptions: Dict[str, List[Dict[str, Any]]] = {}
        self._memory_user_state: Dict[str, str] = {}

    async def list_assumptions(self, project_id: str) -> List[Dict[str, Any]]:
        if self._client is None:
            return self._memory_assumptions.get(project_id, [])
        try:
            resp = self._client.table("assumptions").select("*").eq("project_id", project_id).execute()
            return resp.data or []
        except Exception:
            return []

    async def upsert_assumptions(self, project_id: str, assumptions: List[Dict[str, Any]]) -> None:
        now_iso = dt.datetime.utcnow().isoformat()
        if self._client is None:
            stored = self._memory_assumptions.setdefault(project_id, [])
            for assumption in assumptions:
                assumption.setdefault("project_id", project_id)
                assumption.setdefault("last_verified_at", now_iso)
                stored.append(assumption)
            return
        try:
            payload = [
                {
                    **assumption,
                    "project_id": project_id,
                    "last_verified_at": assumption.get("last_verified_at", now_iso),
                }
                for assumption in assumptions
            ]
            self._client.table("assumptions").upsert(payload).execute()
        except Exception:
            return

    async def get_project(self, user_id: str) -> Optional[Dict[str, Any]]:
        if self._client is None:
            for project in self._memory_projects.values():
                if project.get("owner_id") == user_id:
                    return project
            return None
        try:
            resp = self._client.table("projects").select("*").eq("owner_id", user_id).limit(1).execute()
            if resp.data:
                return resp.data[0]
        except Exception:
            return None
        return None

    async def create_project(self, name: str, owner_id: str) -> Dict[str, Any]:
        project = {"name": name, "owner_id": owner_id}
        if self._client is None:
            project_id = f"local-{len(self._memory_projects)+1}"
            project["id"] = project_id
            self._memory_projects[project_id] = project
            self._memory_assumptions.setdefault(project_id, [])
            return project
        try:
            resp = self._client.table("projects").insert(project).execute()
            if resp.data:
                return resp.data[0]
        except Exception:
            return project
        return project

    async def get_current_view(self, user_id: str) -> str:
        """Return the persisted workspace for the user, defaulting to overview."""

        default_view = "overview"
        if self._client is None:
            return self._memory_user_state.get(user_id, default_view)

        try:
            resp = (
                self._client.table("user_state")
                .select("current_workspace")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if resp.data:
                return resp.data[0].get("current_workspace", default_view)
        except Exception:
            return default_view

        return default_view

    async def set_current_view(self, user_id: str, workspace: str) -> None:
        if self._client is None:
            self._memory_user_state[user_id] = workspace
            return

        try:
            payload = {"user_id": user_id, "current_workspace": workspace}
            self._client.table("user_state").upsert(payload, on_conflict="user_id").execute()
        except Exception:
            return


db_service = DatabaseService()
