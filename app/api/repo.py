"""Repo (ca_data GitHub sync) API router (extracted from main.py).

Thin HTTP wrappers over the repo/credential helpers that still live in ``main``
(``repo_config_load``/``repo_config_save``, ``creds_load``/``creds_save``, ``_git_run``,
``_ensure_ca_data_gitignore``, ``CA_DATA_DIR``, ``logger``). They are imported lazily inside each
handler because they are defined late in ``main.py``; see docs/MAINTAINABILITY_PLAN.md.
"""
from __future__ import annotations

import os
from datetime import datetime

import requests
from fastapi import APIRouter, Request

router = APIRouter(tags=["repo"])


@router.get("/repo/config")
def get_repo_config():
    """リポジトリ設定取得（機密トークンは除く）"""
    from main import creds_load, repo_config_load
    cfg = repo_config_load()
    creds = creds_load()
    return {
        **cfg,
        "has_token": bool(creds.get("github_token")),
        "github_username_saved": creds.get("github_username", ""),
    }


@router.post("/repo/config")
async def save_repo_config(request: Request):
    """リポジトリ設定保存（トークンは機密ファイルへ、それ以外はDB）"""
    from main import creds_load, creds_save, repo_config_save
    data = await request.json()
    # 機密情報を .codeagent/.credentials へ
    token = data.pop("github_token", None)
    cred_username = data.pop("github_username_cred", None)
    if token is not None or cred_username is not None:
        creds = creds_load()
        if token is not None:
            creds["github_token"] = token
        if cred_username is not None:
            creds["github_username"] = cred_username
        creds_save(creds)
    # 非機密設定を DB へ
    repo_config_save(data)
    return {"ok": True}


@router.post("/repo/init")
async def init_repo(request: Request):
    """GitHubリポジトリを作成してリモートを設定"""
    from main import (
        CA_DATA_DIR,
        _ensure_ca_data_gitignore,
        _git_run,
        creds_load,
        logger,
        repo_config_load,
        repo_config_save,
    )
    data = await request.json()
    cfg = repo_config_load()
    creds = creds_load()

    token = creds.get("github_token", "")
    username = creds.get("github_username", "") or cfg.get("github_username", "")
    repo_name = data.get("repo_name") or cfg.get("github_repo_name", "codeagent-data")
    visibility = data.get("visibility") or cfg.get("github_repo_visibility", "private")
    branch = data.get("branch") or cfg.get("github_default_branch", "main")

    if not token:
        err_msg = "GitHub Personal Access Token が設定されていません (設定モーダル → GitHub 連携でトークンを保存してください)"
        logger.warning("[GH] init skipped: %s", err_msg)
        return {"ok": False, "error": err_msg}
    if not username:
        err_msg = "GitHub ユーザー名が設定されていません"
        logger.warning("[GH] init skipped: %s", err_msg)
        return {"ok": False, "error": err_msg}

    # GitHub API でリポジトリ作成
    try:
        resp = requests.post(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={
                "name": repo_name,
                "private": (visibility == "private"),
                "description": "CodeAgent data repository (managed by CodeAgent)",
                "auto_init": False,
            },
            timeout=15,
        )
        if resp.status_code == 422:
            # Already exists
            pass
        elif not resp.ok:
            err_msg = f"GitHub API エラー: {resp.status_code} {resp.text[:200]}"
            logger.error("[GH] init error: %s", err_msg)
            return {"ok": False, "error": err_msg}
    except requests.RequestException as e:
        err_msg = f"GitHub API 接続エラー: {e}"
        logger.error("[GH] init error: %s", err_msg)
        return {"ok": False, "error": err_msg}

    remote_url = f"https://github.com/{username}/{repo_name}.git"
    clean_url = remote_url  # トークンなし版

    # ca_data/ でリポジトリを初期化
    os.makedirs(CA_DATA_DIR, exist_ok=True)
    rc, out, err = _git_run(["init", "-b", branch], CA_DATA_DIR)
    if rc != 0:
        # older git: init then rename branch
        _git_run(["init"], CA_DATA_DIR)
        _git_run(["checkout", "-b", branch], CA_DATA_DIR)

    _git_run(["config", "user.email", "codeagent@local"], CA_DATA_DIR)
    _git_run(["config", "user.name", "CodeAgent"], CA_DATA_DIR)

    # リモート設定（既存なら更新）
    rc2, _, _ = _git_run(["remote", "get-url", "origin"], CA_DATA_DIR)
    if rc2 == 0:
        _git_run(["remote", "set-url", "origin", clean_url], CA_DATA_DIR)
    else:
        _git_run(["remote", "add", "origin", clean_url], CA_DATA_DIR)

    # .gitignore 作成（ca_data/ 用）
    _ensure_ca_data_gitignore()

    # 設定保存
    repo_config_save({
        "github_repo_name": repo_name,
        "github_repo_visibility": visibility,
        "github_default_branch": branch,
        "github_remote_url": clean_url,
        "github_username": username,
    })

    return {"ok": True, "remote_url": clean_url, "repo": repo_name}


@router.post("/repo/sync")
async def sync_repo(request: Request):
    """ca_data/ の変更をコミットして GitHub へプッシュ"""
    from main import (
        CA_DATA_DIR,
        _ensure_ca_data_gitignore,
        _git_run,
        creds_load,
        logger,
        repo_config_load,
    )
    data = await request.json()
    message = data.get("message") or f"chore: sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    cfg = repo_config_load()
    creds = creds_load()
    token = creds.get("github_token", "")
    username = creds.get("github_username", "") or cfg.get("github_username", "")
    repo_name = cfg.get("github_repo_name", "")
    branch = cfg.get("github_default_branch", "main")

    if not token:
        err_msg = "GitHub Personal Access Token が設定されていません (設定モーダル → GitHub 連携でトークンを保存してください)"
        logger.warning("[GH] sync skipped: %s", err_msg)
        return {"ok": False, "error": err_msg}
    if not username or not repo_name:
        err_msg = "リポジトリ設定が不完全です。先に Init を実行してください"
        logger.warning("[GH] sync skipped: %s", err_msg)
        return {"ok": False, "error": err_msg}

    auth_url = f"https://{token}@github.com/{username}/{repo_name}.git"
    clean_url = f"https://github.com/{username}/{repo_name}.git"

    _ensure_ca_data_gitignore()
    _git_run(["add", "-A"], CA_DATA_DIR)

    rc, out, err = _git_run(["commit", "-m", message], CA_DATA_DIR)
    if rc != 0 and "nothing to commit" not in out + err:
        return {"ok": False, "error": err or out}

    # 認証URLを一時設定してプッシュ
    _git_run(["remote", "set-url", "origin", auth_url], CA_DATA_DIR)
    try:
        rc, out, err = _git_run(["push", "-u", "origin", branch], CA_DATA_DIR)
    finally:
        _git_run(["remote", "set-url", "origin", clean_url], CA_DATA_DIR)

    if rc != 0:
        return {"ok": False, "error": err or out}

    return {"ok": True, "message": message, "branch": branch}


@router.get("/repo/test-connection")
def test_repo_connection():
    """GitHub API 接続確認（トークンの有効性・ユーザー情報・レートリミット）"""
    from main import creds_load
    creds = creds_load()
    token = creds.get("github_token", "")
    if not token:
        return {"ok": False, "error": "GitHub Personal Access Token が設定されていません (.codeagent/ に保存してください)"}
    try:
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        # ユーザー情報取得
        user_resp = requests.get("https://api.github.com/user", headers=headers, timeout=10)
        if not user_resp.ok:
            return {"ok": False, "error": f"認証失敗 (HTTP {user_resp.status_code}): トークンが無効か期限切れです"}
        user = user_resp.json()
        # レートリミット取得
        rate_resp = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=10)
        rate = {}
        if rate_resp.ok:
            core = rate_resp.json().get("rate", {})
            import datetime as _dt
            reset_ts = core.get("reset", 0)
            reset_str = _dt.datetime.fromtimestamp(reset_ts).strftime("%H:%M:%S") if reset_ts else "?"
            rate = {"remaining": core.get("remaining"), "limit": core.get("limit"), "reset": reset_str}
        return {
            "ok": True,
            "login": user.get("login", ""),
            "name": user.get("name", ""),
            "plan": user.get("plan", {}).get("name", "") if user.get("plan") else "",
            "public_repos": user.get("public_repos", 0),
            "private_repos": user.get("total_private_repos", 0),
            "rate_limit": rate,
        }
    except requests.RequestException as e:
        return {"ok": False, "error": f"通信エラー: {e}"}


@router.get("/repo/status")
def get_repo_status():
    """ca_data/ の Git ステータス取得"""
    from main import CA_DATA_DIR, _git_run, repo_config_load
    if not os.path.exists(os.path.join(CA_DATA_DIR, ".git")):
        return {"initialized": False, "status": "リポジトリ未初期化"}
    rc, out, err = _git_run(["status", "--short"], CA_DATA_DIR)
    rc2, log, _ = _git_run(["log", "--oneline", "-5"], CA_DATA_DIR)
    cfg = repo_config_load()
    return {
        "initialized": True,
        "status": out or "clean",
        "recent_commits": log,
        "remote_url": cfg.get("github_remote_url", ""),
        "branch": cfg.get("github_default_branch", "main"),
    }
