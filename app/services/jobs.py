"""Job submission and execution services.

This module keeps job runtime orchestration out of ``main.py`` without owning
HTTP routes. Route handlers pass the runtime dependencies explicitly so the
service does not import the application module or FastAPI app instance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException


def append_job_event(
    *,
    project: str,
    job_id: str,
    seq: int,
    event_type: str,
    data: dict[str, Any],
    append_step: Callable[[str, str, int, str, dict[str, Any]], Any],
    update_status: Callable[[str, str, str], Any],
    log_append: Callable[[str, dict[str, Any]], Any],
) -> None:
    """Persist a job event and mirror the existing per-job log entry shape."""
    append_step(project, job_id, seq, event_type, data)
    if event_type == "clarify":
        update_status(project, job_id, "waiting_input")

    log_entry: dict[str, Any] = {"type": event_type, "seq": seq}
    if event_type == "tool_call":
        log_entry.update(
            {
                "action": data.get("action", ""),
                "thought": data.get("thought", ""),
                "step_num": data.get("step_num"),
            }
        )
    elif event_type == "tool_result":
        log_entry["result_preview"] = data.get("result_preview", "")
    elif event_type in ("task_done", "task_error", "task_start"):
        log_entry.update(
            {
                "task_id": data.get("task_id"),
                "title": data.get("title", ""),
                "error": data.get("error", ""),
            }
        )
    elif event_type == "skill_hint":
        log_entry.update(
            {
                "missing_tool": data.get("missing_tool", ""),
                "thought": data.get("thought", ""),
            }
        )
    log_append(job_id, log_entry)


def finalize_job(project: str, job_id: str, update_status: Callable[[str, str, str], Any]) -> None:
    """Mark a job as done using the injected job status writer."""
    update_status(project, job_id, "done")


def fail_job(project: str, job_id: str, update_status: Callable[[str, str, str], Any]) -> None:
    """Mark a job as failed using the injected job status writer."""
    update_status(project, job_id, "error")


def submit_job_service(
    req: Any,
    *,
    create_job: Callable[[str, str, str], str],
    thread_factory: Callable[..., Any],
    background_runner: Callable[[str, Any], Any],
    current_model_key: str,
) -> dict[str, Any]:
    """Create a job and start the injected background execution runner."""
    job_id = create_job(req.project, req.message, req.mode)
    thread = thread_factory(target=background_runner, args=(job_id, req), daemon=True)
    thread.start()
    return {
        "job_id": job_id,
        "status": "queued",
        "model": current_model_key,
    }


def run_job_background_service(job_id: str, req: Any, deps: Any) -> None:
    """
    バックグラウンドスレッドで実行。
    全イベントをDBに書き込み続ける（ブラウザが閉じても継続）。
    """

    _resolve_effective_search_enabled = deps.resolve_effective_search_enabled
    _wait_threading = deps.wait_threading
    _job_wait_events = deps.job_wait_events
    _job_wait_answers = deps.job_wait_answers
    job_append_step = deps.job_append_step
    job_update_status = deps.job_update_status
    job_log_append = deps.job_log_append
    job_log_get = deps.job_log_get
    _resolve_runtime_llm_url = deps.resolve_runtime_llm_url
    execute_chat_with_optional_web_search = deps.execute_chat_with_optional_web_search
    save_session = deps.save_session
    plan = deps.plan
    get_runtime_model_catalog = deps.get_runtime_model_catalog
    _model_manager = deps.model_manager
    get_model_spec = deps.get_model_spec
    get_coder_ladder_keys = deps.get_coder_ladder_keys
    run_task_mode_stream = deps.run_task_mode_stream
    _job_option_choices = deps.job_option_choices
    call_llm_chat = deps.call_llm_chat
    extract_json = deps.extract_json
    run_shell = deps.run_shell
    setup_venv = deps.setup_venv
    _active_skills = deps.active_skills
    _upsert_skill = deps.upsert_skill
    settings_get = deps.settings_get
    execute_task = deps.execute_task
    _apply_ensemble_execution_mode_guard = deps.apply_ensemble_execution_mode_guard
    _is_quality_output_ok = deps.is_quality_output_ok
    _git_run = deps.git_run
    CA_DATA_DIR = deps.ca_data_dir
    list_files = deps.list_files
    memory_search = deps.memory_search
    verify_and_fix = deps.verify_and_fix
    auto_snapshot_ca_data = deps.auto_snapshot_ca_data
    analyze_job_for_skills = deps.analyze_job_for_skills
    _analyze_job_for_memory = deps.analyze_job_for_memory
    LLM_URL = deps.llm_url
    choose_model_for_role = deps.choose_model_for_role
    project = req.project
    effective_search_enabled = _resolve_effective_search_enabled(req.search_enabled)
    seq = 0

    # clarify待機用のEventを登録
    _ev = _wait_threading.Event()
    _job_wait_events[job_id] = _ev

    def _format_job_exception(ex: Exception) -> str:
        if isinstance(ex, HTTPException) and isinstance(ex.detail, dict):
            detail = ex.detail
            if detail.get("error") == "llm_not_ready":
                return f"LLM not ready: {detail.get('message', 'LLM server is not running.')}"
        return str(ex)

    def write(event_type: str, data: dict):
        nonlocal seq
        append_job_event(
            project=project,
            job_id=job_id,
            seq=seq,
            event_type=event_type,
            data=data,
            append_step=job_append_step,
            update_status=job_update_status,
            log_append=job_log_append,
        )
        seq += 1

    try:
        job_update_status(project, job_id, "running")

        if req.mode == "chat":
            exec_url = _resolve_runtime_llm_url(req.llm_url)
            chat_result = execute_chat_with_optional_web_search(
                req.message,
                max_steps=req.max_steps,
                search_enabled=effective_search_enabled,
                llm_url=exec_url,
                chat_history=req.chat_history,
                on_event=lambda ev: write(ev.get("type", "chat_step"), ev),
            )
            chat_output = chat_result.get("output") or chat_result.get("error") or ""
            write("done", {
                "result": chat_output,
                "status": "done" if chat_result.get("status") == "done" else "error",
                "usage": chat_result.get("usage", {}),
                "steps": chat_result.get("steps", []),
            })
            save_session(job_id, project, req.message, "chat", {
                "output": chat_output,
                "status": chat_result.get("status", "done"),
                "steps": chat_result.get("steps", []),
            })


        else:
            # taskモード: plan → モデル選択 → verify
            if req.approved_tasks:
                todos = req.approved_tasks
                plan_result = None
                print(f"[JOB {job_id}] approved_tasks count: {len(todos)}")
                for t in todos:
                    print(f"  task id={t.get('id')} title={t.get('title','')[:40]}")
            else:
                plan_result = plan(req.message, project)
                todos = plan_result.get("tasks", [])
                print(f"[JOB {job_id}] planned tasks count: {len(todos)}")

            write("plan", {"tasks": todos, "total": len(todos)})
            total = len(todos)
            print(f"[JOB {job_id}] total tasks to execute: {total}")
            results = []
            context = ""

            # ── プランニング後・実行前にモデル選択 ──
            # モデル選択: UIで手動指定 > Auto（heuristic_classify）
            forced_model = (req.recommended_model or "").strip()
            runtime_catalog = get_runtime_model_catalog()
            if forced_model and forced_model != "auto" and forced_model in runtime_catalog:
                # UIで手動選択されたモデルを使用
                best_key = forced_model
                print(f"[ModelManager] user selected: {best_key}")
            else:
                # Auto or 未指定: 現在のモデルをそのまま使う（切り替えしない）
                best_key = _model_manager.current_key
                print(f"[ModelManager] auto: keeping current model {best_key}")

            if best_key != _model_manager.current_key and runtime_catalog.get(best_key, {}).get("path"):
                write("model_switching", {
                    "from": _model_manager.current_key,
                    "to": best_key,
                    "model_name": runtime_catalog.get(best_key, {}).get("name", best_key),
                    "eta_sec": runtime_catalog.get(best_key, {}).get("load_sec", 60),
                    "message": f"Loading {runtime_catalog.get(best_key,{}).get('name',best_key)}..."
                })
                def _on_switch(ev):
                    write(ev.get("type","model_event"), ev)
                switched = _model_manager.ensure_model(best_key, on_event=_on_switch)
                if not switched:
                    print(f"[ModelManager] switch to {best_key} failed, staying on current model")
                    write("model_event", {"message": "Switch failed, using current model"})
                # model_readyはensure_model内のemitで既に発火（重複しない）
            else:
                print(f"[ModelManager] no switch needed for {best_key}")

            orchestration_policy = settings_get("orchestration_policy") or "ladder_fail_and_quality"
            quality_check_enabled = settings_get("quality_check_enabled") != "false"
            coder_ladder = get_coder_ladder_keys(runtime_catalog)
            feature_mode = settings_get("feature_mode") or "model_orchestration"
            if feature_mode == "ensemble":
                ensemble_status = _apply_ensemble_execution_mode_guard()
                write("ensemble_mode", {
                    "mode": ensemble_status.get("configured_mode", "parallel"),
                    "recommended_mode": ensemble_status.get("recommended_mode", "parallel"),
                    "warning": bool(ensemble_status.get("warning")),
                    "reason": ensemble_status.get("reason", ""),
                    "auto_switched": bool(ensemble_status.get("switched_by_guard")),
                    "free_vram_mb": ensemble_status.get("free_vram_mb", -1),
                    "required_vram_parallel_mb": ensemble_status.get("required_vram_parallel_mb", -1),
                    "required_vram_serial_mb": ensemble_status.get("required_vram_serial_mb", -1),
                })
            write("feature_mode", {"mode": feature_mode})

            for i, todo in enumerate(todos):
              try:  # ← per-task guard: 1タスクの例外がジョブ全体を止めないよう保護
                pre_snapshot = auto_snapshot_ca_data("pre-task snapshot", job_id, todo.get("id", i + 1))
                pre_snapshot_hash = pre_snapshot.get("commit_hash", "") if pre_snapshot.get("ok") else ""
                write("snapshot", {
                    "stage": "pre-task snapshot",
                    "task_id": todo.get("id", i + 1),
                    "ok": bool(pre_snapshot.get("ok")),
                    "skipped": bool(pre_snapshot.get("skipped")),
                    "reason": pre_snapshot.get("reason", ""),
                    "commit_hash": pre_snapshot_hash,
                    "error": pre_snapshot.get("error", ""),
                })

                write("task_start", {
                    "task_id": todo["id"], "title": todo["title"],
                    "task_index": i, "total": total
                })

                # run_task_mode_stream を使ってステップごとに書き込む
                task_steps = []
                task_status = "pending"  # done/error/pendingで区別
                task_output = ""

                # req.llm_urlが明示されていればそちら、なければModelManagerのURL
                task_url = _resolve_runtime_llm_url(req.llm_url)
                try:
                    for ev in run_task_mode_stream(
                        task_detail=todo["detail"], context=context,
                        max_steps=req.max_steps, project=project,
                        search_enabled=effective_search_enabled, llm_url=task_url,
                        job_id=job_id,
                        task_id=todo.get("id", i+1),
                        task_title=todo.get("title", ""),
                    ):
                        write(ev.get("type","step"), ev)
                        etype = ev.get("type","")
                        if etype == "clarify":
                            # clarify: waiting_input はwrite内で設定済み。再開待ち
                            _job_wait_events[job_id].wait(timeout=300)
                            _job_wait_events[job_id].clear()
                        if etype == "task_done":
                            task_status = "done"
                            task_output = ev.get("output","")
                            task_steps = ev.get("steps",[])
                        elif etype == "task_error":
                            task_status = "error"
                            task_output = ev.get("error","") or task_output
                except Exception as _task_ex:
                    # HTTPException(502/413)などがタスクループを突き抜けないよう捕捉
                    err_msg = _format_job_exception(_task_ex)
                    print(f"[JOB {job_id}] task {i+1}/{total} exception: {err_msg[:100]}")
                    write("task_error", {"task_id": todo["id"], "error": f"[exception] {err_msg[:200]}"})
                    task_status = "error"
                    task_output = f"[exception] {err_msg[:200]}"



                # ── 4段階フォールバック ─────────────────────────────────
                # Stage 1: 同じアプローチで再試行（一時的エラー・タイムアウト対応）
                # Stage 2: 別アプローチで再試行
                # Stage 3: 最小構成で再試行
                # Stage 4: 複数対応案をLLMが生成 → ユーザーが選択 → 再実行
                # ────────────────────────────────────────────────────────

                def _summarize_exploration_steps(_steps, limit=6):
                    exp_actions = {"list_files", "get_outline", "read_file", "search_in_files"}
                    chunks = []
                    for _s in _steps:
                        if _s.get("type") != "tool_call":
                            continue
                        _a = _s.get("action", "")
                        if _a not in exp_actions:
                            continue
                        _inp = _s.get("input", {}) if isinstance(_s.get("input"), dict) else {}
                        _target = (_inp.get("path") or _inp.get("subdir") or _inp.get("query") or "")
                        _preview = str(_s.get("result_preview", "")).replace("\n", " ")[:90]
                        chunks.append(f"{_a}({_target})=>{_preview}")
                    if not chunks:
                        return ""
                    return " / ".join(chunks[-limit:])

                def _run_stage(title_prefix, ctx, steps_limit, run_url=None):
                    """run_task_mode_streamを安全に実行してtask_status/outputを返す"""
                    _steps, _status, _output = [], "pending", ""
                    _url = run_url or task_url
                    try:
                        write("task_start", {
                            "task_id": todo["id"], "title": f"{title_prefix}{todo['title']}",
                            "task_index": i, "total": total
                        })
                        for ev in run_task_mode_stream(
                            task_detail=todo["detail"], context=ctx,
                            max_steps=steps_limit, project=project,
                            search_enabled=effective_search_enabled, llm_url=_url,
                            job_id=job_id,
                            task_id=todo.get("id", i+1),
                            task_title=f"{title_prefix}{todo.get('title','')}",
                        ):
                            write(ev.get("type","step"), ev)
                            etype = ev.get("type","")
                            if etype == "task_done":
                                _status = "done"
                                _output = ev.get("output","")
                                _steps  = ev.get("steps",[])
                            elif etype == "task_error":
                                _status = "error"
                                _output = ev.get("error","") or _output
                    except Exception as _ex:
                        _status = "error"
                        _output = f"[exception] {_format_job_exception(_ex)[:200]}"
                    return _steps, _status, _output

                def _classify_orchestration_error(err_text: str) -> str:
                    msg = (err_text or "").lower()
                    if "playwright: not found" in msg:
                        return "playwright_not_found"
                    if "targetclosederror" in msg:
                        return "target_closed_env"
                    return ""

                def _run_browser_precheck_flow() -> str:
                    checks = [
                        run_shell(command=".venv/bin/python -m playwright --version", project=project, timeout=60),
                        run_shell(
                            command=(
                                ".venv/bin/python - <<'PY'\n"
                                "from playwright.sync_api import sync_playwright\n"
                                "with sync_playwright() as p:\n"
                                "    print('chromium_executable=' + p.chromium.executable_path)\n"
                                "PY"
                            ),
                            project=project,
                            timeout=90,
                        ),
                    ]
                    return "\n\n".join(str(c) for c in checks if c)

                def _run_playwright_env_repair_flow() -> str:
                    repair_logs = [
                        setup_venv(requirements=["playwright"], project=project),
                        run_shell(
                            command=".venv/bin/pip install --upgrade pip playwright && .venv/bin/python -m playwright install chromium",
                            project=project,
                            timeout=300,
                        ),
                    ]
                    repair_logs.append(_run_browser_precheck_flow())
                    return "\n\n".join(str(c) for c in repair_logs if c)

                last_error_key = ""
                same_error_streak = 0

                def _update_same_error_streak(err_text: str) -> int:
                    nonlocal last_error_key, same_error_streak
                    key = " ".join((err_text or "").strip().split()).lower()[:220]
                    if not key:
                        last_error_key = ""
                        same_error_streak = 0
                        return 0
                    if key == last_error_key:
                        same_error_streak += 1
                    else:
                        last_error_key = key
                        same_error_streak = 1
                    return same_error_streak

                # Stage 1: 同じアプローチで再試行
                if task_status in ("error", "pending"):
                    err0 = task_output or "不明なエラー"
                    err0_type = _classify_orchestration_error(err0)
                    _update_same_error_streak(err0)
                    loop_summary0 = _summarize_exploration_steps(task_steps)
                    loop_note0 = ""
                    if loop_summary0:
                        loop_note0 = f"【直前の探索結果要約】{loop_summary0}\n同じ探索シーケンスを繰り返さないこと。\n"
                    preflight_note0 = ""
                    if err0_type == "playwright_not_found":
                        repair_log = _run_playwright_env_repair_flow()
                        preflight_note0 = (
                            "\n【オーケストレーション指示】Playwright 環境修復フローを実行済みです。"
                            " run_browser 再実行前は必ず前提チェック結果を確認してください。"
                            f"\n【環境修復ログ】\n{repair_log[:1200]}"
                        )
                    elif err0_type == "target_closed_env":
                        preflight_log = _run_browser_precheck_flow()
                        preflight_note0 = (
                            "\n【オーケストレーション指示】TargetClosedError を環境依存エラーとして分類。"
                            " Playwright 再インストールは行わず、ブラウザを閉じる順序と終了処理（close / context manager）を見直してから再実行してください。"
                            f"\n【run_browser 前提チェック】\n{preflight_log[:800]}"
                        )
                    print(f"[JOB {job_id}] task {i+1}/{total} stage1 same-approach retry")
                    # メモリ参照: 類似エラーの過去の解決策を注入
                    _mem_hits1 = memory_search(f"{todo['title']} {err0}", limit=2)
                    _mem_note1 = ""
                    if _mem_hits1:
                        _mem_note1 = "\n\n【過去の類似エラーと解決策（メモリ）】\n" + "\n".join(
                            f"- {h['title']}: {h['content'][:200]}" for h in _mem_hits1
                        )
                    ctx1 = (f"{context}\n\n【前回エラー】{err0[:200]}\n\n"
                            f"【指示】前回と同じタスクをもう一度実行してください。"
                            f"エラーの原因を確認して修正してから再実行してください。"
                            f"{loop_note0}"
                            f"{preflight_note0}"
                            f"{_mem_note1}")
                    task_steps, task_status, task_output = _run_stage("[再試行] ", ctx1, req.max_steps)

                # Stage 2: 別アプローチで再試行
                if task_status in ("error", "pending"):
                    err1 = task_output or err0
                    err1_type = _classify_orchestration_error(err1)
                    err1_streak = _update_same_error_streak(err1)
                    if err1_streak >= 2:
                        print(f"[JOB {job_id}] task {i+1}/{total} abort retry on same error twice")
                        collect_ctx = (
                            f"{context}\n\n【同一エラー連続検出】{err1[:200]}\n"
                            "【次アクション】設定確認ログ収集を実施してください。\n"
                            "- run_shell で `pwd && ls -la .venv/bin` を実行\n"
                            "- run_shell で `.venv/bin/python -m playwright --version` を実行\n"
                            "- run_shell で `.venv/bin/python -m playwright install chromium --dry-run` を実行\n"
                            "- run_browser は実行しない\n"
                        )
                        task_steps, task_status, task_output = _run_stage("[設定確認ログ収集] ", collect_ctx, req.max_steps)
                        err2 = task_output or err1
                    else:
                        loop_summary1 = _summarize_exploration_steps(task_steps)
                        loop_note1 = ""
                        if loop_summary1:
                            loop_note1 = f"\n【直前の探索結果要約】{loop_summary1}\n上記と同じ探索シーケンスは禁止。編集対象を先に固定すること。"
                        preflight_note1 = ""
                        if err1_type == "playwright_not_found":
                            repair_log = _run_playwright_env_repair_flow()
                            preflight_note1 = (
                                "\n【オーケストレーション指示】`playwright: not found` のため、"
                                " venv固定コマンドで再セットアップ済みです。"
                                f"\n【環境修復ログ】\n{repair_log[:1200]}"
                            )
                        elif err1_type == "target_closed_env":
                            preflight_log = _run_browser_precheck_flow()
                            preflight_note1 = (
                                "\n【オーケストレーション指示】TargetClosedError（環境依存）を再検出。"
                                " 再インストールループは禁止し、ブラウザ終了処理を修正してから再試行してください。"
                                f"\n【run_browser 前提チェック】\n{preflight_log[:800]}"
                            )
                        print(f"[JOB {job_id}] task {i+1}/{total} stage2 different-approach")
                        # メモリ参照: 複合エラーの解決策を追加注入
                        _mem_hits2 = memory_search(f"{err0} {err1}", limit=2)
                        _mem_note2 = ""
                        if _mem_hits2:
                            _mem_note2 = "\n\n【過去の知識（メモリ）】\n" + "\n".join(
                                f"- {h['title']}: {h['content'][:200]}" for h in _mem_hits2
                            )
                        ctx2 = (f"{context}\n\n【前回エラー×2】\n1回目: {err0[:100]}\n2回目: {err1[:100]}\n\n"
                                f"【指示】これまでと異なるアプローチで実行してください。\n"
                                f"例: write_file→edit_file / run_python→コード分割 / 大きなファイル→get_outline+部分編集"
                                f"{loop_note1}"
                                f"{preflight_note1}"
                                f"{_mem_note2}")
                        task_steps, task_status, task_output = _run_stage("[別アプローチ] ", ctx2, req.max_steps)

                # Stage 3: 全失敗 → 複数対応案を生成 → LLM自動選択 or ユーザー手動選択
                if task_status in ("error", "pending"):
                    err2 = task_output or err1
                    print(f"[JOB {job_id}] task {i+1}/{total} stage3 generating options")

                    # 現在のモデルを記憶
                    prev_model_key = _model_manager.current_key

                    # コードLLMで対応案を生成
                    options_prompt = f"""タスクが3回試行しても完了できませんでした。
【タスク】{todo['title']}
【詳細】{todo['detail'][:300]}
【エラー履歴】
1回目: {err0[:100]}
2回目: {err1[:100]}
3回目: {err2[:100]}

このタスクを完了させるための対応案を3件提示してください。
各案は異なる技術的アプローチで具体的に記述してください。

【重要な制約】
- 「スキップ」「タスクの省略」「次へ進む」のような案は絶対に提案しないこと
- 「ユーザーに委ねる」「手動実装依頼」「ユーザーが実装」のような案は絶対に提案しないこと
- 必ずコードエージェント自身が実行できる技術的な解決策を3件提案すること
- 例: ライブラリ変更、アルゴリズム変更、ファイル分割、別APIの使用、エラー原因の根本対処 など

JSON形式で出力:
{{"options": [
  {{"id": 1, "title": "案のタイトル（10字以内）", "description": "具体的な実施内容（2文以内）", "difficulty": "easy/medium/hard", "detail": "エージェントへの実行指示（詳細）"}},
  {{"id": 2, ...}},
  {{"id": 3, ...}}
]}}"""
                    try:
                        opt_reply, _ = call_llm_chat(
                            [{"role": "user", "content": options_prompt}],
                            llm_url=task_url
                        )
                        opt_parsed = extract_json(opt_reply, parser=_model_manager.current_parser)
                        options = opt_parsed.get("options", []) if opt_parsed else []
                    except Exception as _oe:
                        options = []
                        print(f"[JOB {job_id}] options generation failed: {_oe}")

                    if not options:
                        options = [
                            {"id": 1, "title": "タスク分割", "description": "タスクをより小さなステップに分割して段階的に実行", "difficulty": "medium", "detail": f"次のタスクを小さなステップに分割して、一つずつ確実に実行してください: {todo['detail'][:200]}"},
                            {"id": 2, "title": "最小実装", "description": "エラー箇所を特定して最小限の変更で問題を修正", "difficulty": "easy", "detail": f"エラーの根本原因を特定し、最小限の変更で問題を解決してください。別ライブラリや別APIの使用も検討してください。タスク: {todo['detail'][:150]}"},
                            {"id": 3, "title": "代替手段", "description": "別のツールやライブラリを使って同等の機能を実現", "difficulty": "hard", "detail": f"これまでのアプローチを完全に変え、別のライブラリ・ツール・手法で同じ目標を達成してください。タスク: {todo['detail'][:150]}"},
                        ]

                    # ──── 自動選択モード（プランナーLLM） ────
                    auto_select = req.auto_select_option if hasattr(req, 'auto_select_option') else True
                    chosen = None

                    if auto_select:
                        planner_key = choose_model_for_role("plan", include_disabled=True) or _model_manager.current_key
                        planner_spec = get_model_spec(planner_key)
                        write("model_switching", {
                            "from": prev_model_key,
                            "to": planner_key,
                            "model_name": planner_spec.get("name", "Planner"),
                            "eta_sec": planner_spec.get("load_sec", 30),
                            "message": "対応案を分析中: プランナーLLMをロード中..."
                        })
                        write("task_start", {
                            "task_id": todo["id"],
                            "title": f"[プランナー分析] {todo['title']}",
                            "task_index": i, "total": total
                        })

                        # コードLLMをアンロードしてプランナーをロード
                        planner_switched = _model_manager.ensure_model(
                            planner_key,
                            on_event=lambda ev: write(ev.get("type","model_event"), ev)
                        )
                        planner_url = _model_manager.llm_url

                        select_prompt = f"""あなたはコードエージェントのプランナーです。
以下の状況を分析して、3つの対応案の中から最適なものを1つ選んでください。

【ジョブ全体の目標】{req.message[:200]}
【失敗したタスク】{todo['title']}
【タスク詳細】{todo['detail'][:200]}
【前後のコンテキスト】{context[:300]}
【エラー履歴】
1回目: {err0[:80]}
2回目: {err1[:80]}
3回目: {err2[:80]}

【対応案】
""" + "\n".join(f"案{o['id']}: [{o['difficulty']}] {o['title']} — {o['description']}" for o in options) + f"""

【選択ルール】
- 「スキップ」「省略」「ユーザーに委ねる」内容の案は絶対に選ばないこと
- コードエージェントが自律的に実行できる技術的な解決策を選ぶこと
- エラー履歴を踏まえて最も根本解決できる案を選ぶこと

最も成功確率が高い案を1つ選んでJSON出力してください:
{{"choice": 1, "reason": "選択理由（1文）"}}"""

                        try:
                            sel_reply, _ = call_llm_chat(
                                [{"role": "user", "content": select_prompt}],
                                llm_url=planner_url
                            )
                            sel_parsed = extract_json(sel_reply, parser="gpt_oss")
                            choice_id = int(sel_parsed.get("choice", 1)) if sel_parsed else 1
                            reason = sel_parsed.get("reason", "") if sel_parsed else ""
                            chosen = next((o for o in options if o["id"] == choice_id), options[0])
                            print(f"[JOB {job_id}] planner chose option {choice_id}: {chosen['title']} — {reason}")
                            write("task_start", {
                                "task_id": todo["id"],
                                "title": f"[自動選択: {chosen['title']}] {todo['title']}",
                                "task_index": i, "total": total
                            })
                        except Exception as _se:
                            chosen = options[0]
                            reason = f"自動選択失敗({_se}): デフォルト案1を使用"
                            print(f"[JOB {job_id}] planner selection failed: {_se}")

                        # プランナーをアンロードしてコードLLMを復帰
                        prev_spec = get_model_spec(prev_model_key)
                        write("model_switching", {
                            "from": planner_key,
                            "to": prev_model_key,
                            "model_name": prev_spec.get("name", prev_model_key),
                            "eta_sec": prev_spec.get("load_sec", 30),
                            "message": f"プランナー選択完了: {chosen['title']} — コードLLMを復帰中..."
                        })
                        _model_manager.ensure_model(
                            prev_model_key,
                            on_event=lambda ev: write(ev.get("type","model_event"), ev)
                        )
                        task_url = _model_manager.llm_url

                        # 選択内容をUIに通知
                        write("task_options", {
                            "task_id": todo["id"],
                            "title": todo["title"],
                            "error": err2[:200],
                            "options": options,
                            "auto_chosen": chosen["id"],
                            "auto_reason": reason,
                            "job_id": job_id,
                        })

                    else:
                        # ──── 手動選択モード ────
                        write("task_options", {
                            "task_id": todo["id"],
                            "title": todo["title"],
                            "error": err2[:200],
                            "options": options,
                            "job_id": job_id,
                        })
                        job_update_status(project, job_id, "waiting_input")
                        _job_wait_events[job_id].wait(timeout=600)
                        _job_wait_events[job_id].clear()
                        job_update_status(project, job_id, "running")
                        chosen = _job_option_choices.pop(f"{job_id}_{todo['id']}", None)

                    # ── SKILL自動生成（auto_skill_generation が有効な場合） ──
                    auto_skill_gen = getattr(req, 'auto_skill_generation', True)
                    skill_context_note = ""
                    if auto_skill_gen:
                        try:
                            all_errors = f"{err0}\n{err1}\n{err2}"
                            existing_skill_lines = []
                            for skill in _active_skills()[:12]:
                                kw = ", ".join(skill.get("keywords", [])[:6])
                                existing_skill_lines.append(f"- {skill.get('name','')}: {skill.get('description','')} | keywords={kw}")
                            existing_skill_text = "\n".join(existing_skill_lines) or "(なし)"
                            skill_gen_prompt = f"""コードエージェントのタスク失敗を分析し、既存スキルで対応可能か、新規作成が必要かを厳密に判断してください。

【失敗したタスク】{todo['title']}
【エラー履歴】{all_errors[:400]}
【既存スキル候補】
{existing_skill_text}

ルール:
- 既存スキルと機能が近い場合は新規作成せず update を選ぶ
- 共通化できる場合も update を選び、target に既存スキル名を入れる
- 本当に新機能が必要な場合だけ create を選ぶ
- 不足がなければ decision=none
- JSON以外は返さない

【出力JSONのみ】
{{"decision":"none|create|update","target":"既存スキル名または空文字","merge_reason":"判断理由","skill":{{"name":"snake_case名","description":"説明","version":"1.0","os":["win32","linux"],"keywords":["kw"],"tool_code":"def name(project:str, arg:str)->str:\\n    return result","usage_example":"","rationale":"不足していた理由","source":"codeagent"}}}}"""
                            skill_reply, _ = call_llm_chat(
                                [{"role": "user", "content": skill_gen_prompt}],
                                llm_url=task_url
                            )
                            skill_parsed = extract_json(skill_reply, parser=_model_manager.current_parser)
                            decision = str((skill_parsed or {}).get("decision") or "").strip().lower()
                            new_skill = (skill_parsed or {}).get("skill")
                            target_skill = str((skill_parsed or {}).get("target") or "").strip()
                            merge_reason = str((skill_parsed or {}).get("merge_reason") or "").strip()
                            if decision in ("create", "update") and new_skill and new_skill.get("name") and new_skill.get("tool_code"):
                                if decision == "update" and target_skill:
                                    new_skill["name"] = target_skill
                                save_result = _upsert_skill(new_skill, merge_reason=merge_reason or "auto skill refinement", prefer_merge=True)
                                action_label = "更新" if save_result.get("action") == "updated" else "生成"
                                skill_context_note = f"\n\n【自動生成スキル】'{save_result.get('skill_name', new_skill['name'])}' スキルを{action_label}しました。このスキルを活用してタスクを実行してください。"
                                write("skill_generated", {
                                    "skill_name": save_result.get("skill_name", new_skill["name"]),
                                    "action": save_result.get("action", decision),
                                    "version": save_result.get("version", ""),
                                    "matched_skill": save_result.get("matched_skill", ""),
                                    "description": new_skill.get("description", ""),
                                    "rationale": merge_reason or new_skill.get("rationale", ""),
                                    "task_id": todo["id"],
                                })
                                print(f"[JOB {job_id}] auto-skill {save_result.get('action','created')}: {save_result.get('skill_name', new_skill['name'])}")
                        except Exception as _sge:
                            print(f"[JOB {job_id}] skill auto-generation failed: {_sge}")

                    # 選択案で再実行
                    if chosen:
                        chosen_title = chosen.get("title", "選択案")
                        ctx3 = (f"{context}\n\n【選択された対応案】{chosen_title}\n"
                                f"{chosen.get('description','')}\n\n"
                                f"【実行指示】{chosen.get('detail', todo['detail'])}"
                                f"{skill_context_note}")
                        task_steps, task_status, task_output = _run_stage(f"[{chosen_title}] ", ctx3, req.max_steps)
                    else:
                        task_status = "done"
                        task_output = f"[skipped by timeout] {todo['title']}"

                # Stage 5: コーダー段階的昇格（失敗時 / 品質基準未達）
                if feature_mode == "model_orchestration" and orchestration_policy != "off" and not req.llm_url.strip():
                    needs_quality_retry = (
                        orchestration_policy == "ladder_fail_and_quality"
                        and quality_check_enabled
                        and task_status == "done"
                        and (not _is_quality_output_ok(task_output))
                    )
                    needs_fail_retry = (task_status in ("error", "pending"))
                    if needs_fail_retry or needs_quality_retry:
                        current_key = _model_manager.current_key
                        tried_keys = {current_key}
                        for lvl, next_key in enumerate(coder_ladder, start=1):
                            if not next_key or next_key in tried_keys:
                                continue
                            tried_keys.add(next_key)
                            spec = get_model_spec(next_key)
                            if not spec.get("path"):
                                continue
                            write("model_switching", {
                                "from": _model_manager.current_key,
                                "to": next_key,
                                "model_name": spec.get("name", next_key),
                                "eta_sec": spec.get("load_sec", 30),
                                "message": f"Coder昇格 L{lvl}: {spec.get('name', next_key)}",
                            })
                            switched = _model_manager.ensure_model(
                                next_key,
                                on_event=lambda ev: write(ev.get("type", "model_event"), ev)
                            )
                            if not switched:
                                continue
                            task_url = _model_manager.llm_url
                            reason = "失敗リカバリ" if needs_fail_retry else "品質改善"
                            qctx = (
                                f"{context}\n\n【昇格実行】{reason}\n"
                                f"タスク出力を完成形に改善してください。\n"
                                f"- 省略/TODO/placeholderは禁止\n"
                                f"- 実行可能な具体コード・修正内容にすること\n"
                                f"- 既存ファイルとの整合性を保つこと\n"
                            )
                            task_steps, task_status, task_output = _run_stage(f"[Coder昇格L{lvl}] ", qctx, req.max_steps)
                            if task_status == "done" and (not quality_check_enabled or _is_quality_output_ok(task_output)):
                                break
                            needs_fail_retry = (task_status in ("error", "pending"))
                            needs_quality_retry = (
                                orchestration_policy == "ladder_fail_and_quality"
                                and quality_check_enabled
                                and task_status == "done"
                                and (not _is_quality_output_ok(task_output))
                            )
                            if not (needs_fail_retry or needs_quality_retry):
                                break

                print(f"[JOB {job_id}] task {i+1}/{total} '{todo['title'][:30]}' -> {task_status}")
                final_status = task_status if task_status == "done" else "error"
                results.append({"task_id": todo["id"], "title": todo["title"],
                                 "status": final_status, "output": task_output, "steps": task_steps})
                if final_status == "done":
                    post_snapshot = auto_snapshot_ca_data("post-task snapshot", job_id, todo.get("id", i + 1))
                    write("snapshot", {
                        "stage": "post-task snapshot",
                        "task_id": todo.get("id", i + 1),
                        "ok": bool(post_snapshot.get("ok")),
                        "skipped": bool(post_snapshot.get("skipped")),
                        "reason": post_snapshot.get("reason", ""),
                        "commit_hash": post_snapshot.get("commit_hash", ""),
                        "error": post_snapshot.get("error", ""),
                    })
                    try:
                        files_raw = list_files(subdir=project)
                        files_str = files_raw if files_raw != "(empty)" else "  (なし)"
                    except Exception:
                        files_str = "  (取得失敗)"
                    # context肥大化防止: task_output と files_str を制限
                    _out = (task_output or '完了')[:500]
                    _files = "\n".join(files_str.splitlines()[:30])
                    context = (
                        f"前のタスク「{todo['title']}」が完了しました。\n"
                        f"タスク結果: {_out}\n"
                        f"現在のプロジェクトファイル:\n{_files}\n"
                        f"次のタスクでこれらのファイルを参照してください。"
                    )
                    write("progress", {"pct": int((i+1)/total*100), "label": f"{i+1}/{total} done"})
                else:
                    rollback_result = {"ok": False, "note": "pre snapshot missing"}
                    if pre_snapshot_hash:
                        rc_reset, _, err_reset = _git_run(["reset", "--hard", pre_snapshot_hash], CA_DATA_DIR)
                        if rc_reset == 0:
                            rc_clean, _, err_clean = _git_run(["clean", "-fd"], CA_DATA_DIR)
                            rollback_result = {
                                "ok": rc_clean == 0,
                                "note": "rolled back to pre-task snapshot",
                                "error": err_clean if rc_clean != 0 else ""
                            }
                        else:
                            rollback_result = {"ok": False, "note": "git reset failed", "error": err_reset}
                    write("snapshot_rollback", {
                        "stage": "pre-task snapshot",
                        "task_id": todo.get("id", i + 1),
                        "target_commit": pre_snapshot_hash,
                        "ok": bool(rollback_result.get("ok")),
                        "note": rollback_result.get("note", ""),
                        "error": rollback_result.get("error", ""),
                    })
                    context = (
                        f"前のタスク「{todo['title']}」が全試行後もエラーになりました。\n"
                        f"エラー内容: {task_output or '不明'}\n"
                        f"このエラーを踏まえて次のタスクを実行してください。"
                    )
                    write("progress", {"pct": int((i+1)/total*100), "label": f"task {i+1}/{total} failed (skill proposed)"})

              except Exception as _per_task_ex:
                # 1タスクで予期しない例外が発生しても残りのタスクを継続する
                _per_task_msg = f"[per-task exception] {str(_per_task_ex)[:300]}"
                print(f"[JOB {job_id}] task {i+1}/{total} per-task exception: {_per_task_msg}")
                try:
                    write("task_error", {
                        "task_id": todo.get("id", i+1),
                        "title": todo.get("title", ""),
                        "error": _per_task_msg,
                    })
                except Exception:
                    pass
                # resultsにまだ記録されていなければエラーとして追加
                if not any(r.get("task_id") == todo.get("id") for r in results):
                    results.append({
                        "task_id": todo.get("id", i+1),
                        "title": todo.get("title", ""),
                        "status": "error",
                        "output": _per_task_msg,
                        "steps": [],
                    })

            done_count = sum(1 for r in results if r["status"] == "done")

            verify_rework_results = []

            # 検証フェーズ（approved_tasksの場合でも実行）
            if done_count == total:
                requirements = plan_result.get("requirements", ["指示された内容が正しく動作すること"]) if plan_result else ["指示された内容が正しく動作すること"]
                verification = plan_result.get("verification", ["動作確認"]) if plan_result else ["動作確認"]
                # verify_startはverify_and_fix内部で発火するため、ここでは不要
                verify_url = _resolve_runtime_llm_url(req.llm_url)
                verify_result = verify_and_fix(
                    user_message=req.message,
                    requirements=requirements,
                    verification_items=verification,
                    project=project, max_fix_rounds=2,
                    llm_url=verify_url, search_enabled=effective_search_enabled,
                    on_event=lambda ev: write(ev.get("type","verify"), ev)
                )
                # 検証失敗時は、失敗内容をタスク化して再修正 → 再検証を1回実施
                if verify_result and not verify_result.get("passed", True):
                    failed_issues = [i for i in (verify_result.get("issues") or []) if i.get("severity") == "critical"][:3]
                    if failed_issues:
                        write("verify_rework_start", {
                            "count": len(failed_issues),
                            "message": "検証失敗を受けて、関連タスクへ戻って再修正を実施します。"
                        })
                    for idx, issue in enumerate(failed_issues, start=1):
                        phase = str(issue.get("phase") or "検証")
                        desc = str(issue.get("description") or "詳細不明")
                        task_title = f"[verify-rework {idx}] {phase}: {desc[:80]}"
                        write("task_start", {
                            "task_id": f"verify_rework_{idx}",
                            "title": task_title,
                            "task_index": total + idx,
                            "total": total + len(failed_issues),
                        })
                        rework_prompt = f"""検証フェーズで失敗したため、該当実装を修正してください。

【ユーザー要求】
{req.message}

【失敗フェーズ】
{phase}

【失敗内容】
{desc}

【修正方針】
- 失敗原因に対応する実装を修正する
- 必要なら関連ファイルも含めて修正する
- 修正後に run_file / run_python / run_shell で自己検証してから完了する
"""
                        rw_steps, rw_status, rw_output = execute_task(
                            task_detail=rework_prompt,
                            project=project,
                            max_steps=max(6, min(int(req.max_steps or 10), 12)),
                            llm_url=verify_url
                        )
                        verify_rework_results.append({
                            "task_id": f"verify_rework_{idx}",
                            "title": task_title,
                            "status": "done" if rw_status == "done" else "error",
                            "output": rw_output,
                            "steps": rw_steps,
                        })
                    if failed_issues:
                        verify_result = verify_and_fix(
                            user_message=req.message,
                            requirements=requirements,
                            verification_items=verification,
                            project=project, max_fix_rounds=2,
                            llm_url=verify_url, search_enabled=effective_search_enabled,
                            on_event=lambda ev: write(ev.get("type", "verify"), ev)
                        )
                if (orchestration_policy == "ladder_fail_and_quality"
                        and not req.llm_url.strip()
                        and verify_result
                        and not verify_result.get("passed", True)):
                    for next_key in coder_ladder:
                        if not next_key or next_key == _model_manager.current_key:
                            continue
                        spec = get_model_spec(next_key)
                        if not spec.get("path"):
                            continue
                        write("model_switching", {
                            "from": _model_manager.current_key,
                            "to": next_key,
                            "model_name": spec.get("name", next_key),
                            "eta_sec": spec.get("load_sec", 30),
                            "message": f"検証不合格のため高品質モデルへ昇格: {spec.get('name', next_key)}",
                        })
                        if not _model_manager.ensure_model(next_key, on_event=lambda ev: write(ev.get("type","model_event"), ev)):
                            continue
                        verify_result = verify_and_fix(
                            user_message=req.message,
                            requirements=requirements,
                            verification_items=verification,
                            project=project, max_fix_rounds=2,
                            llm_url=_model_manager.llm_url, search_enabled=effective_search_enabled,
                            on_event=lambda ev: write(ev.get("type","verify"), ev)
                        )
                        if verify_result.get("passed", False):
                            break
            else:
                verify_result = None

            print(f"[JOB {job_id}] completed: {done_count}/{total} tasks done")
            verify_passed = True if not verify_result else bool(verify_result.get("passed", True))
            final = {
                "summary": f"{total}タスク中{done_count}件完了" + ("" if verify_passed else "（検証で失敗あり）"),
                "success": (done_count == total) and verify_passed,
                "tasks": results,
                "verify": verify_result,
                "verify_rework": verify_rework_results,
            }
            final_snapshot = auto_snapshot_ca_data("job-final snapshot", job_id, None)
            write("snapshot", {
                "stage": "job-final snapshot",
                "task_id": None,
                "ok": bool(final_snapshot.get("ok")),
                "skipped": bool(final_snapshot.get("skipped")),
                "reason": final_snapshot.get("reason", ""),
                "commit_hash": final_snapshot.get("commit_hash", ""),
                "error": final_snapshot.get("error", ""),
            })
            write("done", final)
            save_session(job_id, project, req.message, "task", final)

            # ジョブログを分析してスキル提案（バックグラウンドで実行）
            logs = job_log_get(job_id)
            has_issues = (
                any(e.get("type") == "skill_hint" for e in logs) or
                any(e.get("type") == "task_error" for e in logs) or
                done_count < total
            )
            if has_issues:
                try:
                    analysis = analyze_job_for_skills(job_id, project)
                    if analysis.get("proposals"):
                        write("skill_proposals", {
                            "proposals": analysis["proposals"],
                            "stats": analysis.get("stats", {}),
                            "auto": True,
                        })
                        print(f"[SKILLS] {len(analysis['proposals'])} proposals for job {job_id}")
                except Exception as e:
                    print(f"[SKILLS] auto-analyze error: {e}")

            # ジョブログからパーマネントメモリに知識を抽出（常時バックグラウンドで実行）
            _mem_llm_url = req.llm_url.strip() or LLM_URL
            import threading as _mem_thread
            def _memory_worker():
                result = _analyze_job_for_memory(job_id, project, _mem_llm_url)
                try:
                    if result and result.get("ok"):
                        saved = int(result.get("saved", 0) or 0)
                        reason = result.get("reason", "completed")
                        message = f"メモリ抽出が完了しました ({saved}件保存)" if saved > 0 else f"メモリ抽出が完了しました (保存なし: {reason})"
                        write("memory_done", {"job_id": job_id, "saved": saved, "reason": reason, "message": message})
                    else:
                        write("memory_done", {
                            "job_id": job_id,
                            "saved": 0,
                            "reason": (result or {}).get("reason", "unknown_error"),
                            "message": f"メモリ抽出でエラー: {(result or {}).get('reason', 'unknown_error')}",
                            "error": True
                        })
                except Exception:
                    pass
            _mem_thread.Thread(
                target=_memory_worker,
                daemon=True
            ).start()
            write("memory_analyzing", {"job_id": job_id, "message": "実行ログからメモリを抽出中..."})

        finalize_job(project, job_id, job_update_status)

        # ジョブ完了後にチャット用ロールのモデルに戻す（次のジョブのため）
        chat_key = choose_model_for_role("chat")
        if not req.llm_url.strip() and chat_key and _model_manager.current_key != chat_key:
            _model_manager.ensure_model(chat_key)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[JOB {job_id}] EXCEPTION: {type(e).__name__}: {e}")
        print(f"[JOB {job_id}] traceback:\n{tb}")
        write("error", {"error": f"{type(e).__name__}: {e}"})
        fail_job(project, job_id, job_update_status)
    finally:
        _job_wait_events.pop(job_id, None)
        _job_wait_answers.pop(job_id, None)

