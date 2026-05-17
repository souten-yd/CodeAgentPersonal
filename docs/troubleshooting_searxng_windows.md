# SearXNG Windows: `server.secret_key is not changed` の対処

## 症状
- `server.secret_key is not changed. Please use something else instead of ultrasecretkey.`
- `Unexpected exit from worker-1`

## 原因
`ca_data/searxng/settings.yml` の `server.secret_key` が未設定、空、または `ultrasecretkey` のまま。

## 確認手順 (PowerShell)
```powershell
Get-Content .\ca_data\searxng\secret_key
Select-String -Path .\ca_data\searxng\settings.yml -Pattern "secret_key|ultrasecretkey" -Context 2,2
```

## 修復
```powershell
python .\scripts\start_searxng_windows.py
```

## 完了条件
- `settings.yml` に `server.secret_key` が入っている
- `docker logs codeagent-searxng` に secret_key エラーが出ない
