"""Skills API router (extracted from main.py).

Thin HTTP wrappers over the skill helpers that still live in ``main`` (``_load_all_skills``,
``_active_skills``, ``_upsert_skill`` and the SKILLS_DIR constants). They are imported lazily inside
each handler because they are defined late in ``main.py``; see docs/MAINTAINABILITY_PLAN.md.
"""
from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["skills"])


@router.get("/skills")
def list_skills_api():
    from main import (
        DEFAULT_SKILLS_DIR_LOCAL,
        DEFAULT_SKILLS_DIR_RUNPOD,
        IS_RUNPOD_RUNTIME,
        SKILLS_DIR,
        _active_skills,
        _load_all_skills,
    )
    _load_all_skills(force=True)
    skills = _active_skills()
    return {
        "skills": skills,
        "count": len(skills),
        "paths": {
            "active": SKILLS_DIR,
            "default_local": DEFAULT_SKILLS_DIR_LOCAL,
            "default_runpod": DEFAULT_SKILLS_DIR_RUNPOD,
            "runtime": "runpod" if IS_RUNPOD_RUNTIME else "local",
        },
    }


@router.post("/skills")
def create_skill_api(req: dict):
    from main import _upsert_skill
    return _upsert_skill(req, merge_reason="manual save", prefer_merge=True)


@router.delete("/skills/{name}")
def delete_skill_api(name: str):
    import shutil

    from main import SKILLS_DIR, _load_all_skills
    skills = _load_all_skills()
    s = skills.get(name)
    if s and s.get("path"):
        skill_dir = os.path.dirname(s["path"])
        # スキルフォルダごと削除（SKILLS_DIR直下は保護）
        if os.path.isdir(skill_dir) and os.path.abspath(skill_dir) != os.path.abspath(SKILLS_DIR):
            shutil.rmtree(skill_dir, ignore_errors=True)
        elif os.path.exists(s["path"]):
            os.remove(s["path"])
    _load_all_skills(force=True)
    return {"ok": True}


@router.post("/skills/reload")
def reload_skills():
    from main import _load_all_skills
    skills = _load_all_skills(force=True)
    return {"ok": True, "count": len(skills)}
