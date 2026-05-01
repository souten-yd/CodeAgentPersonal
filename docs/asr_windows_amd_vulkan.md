# Windows AMD Vulkan ASR セットアップ

Windows AMD 環境で `whisper.cpp` の Vulkan 版を ASR バックエンドとして使う手順です。

## 手順

1. PowerShell でインストーラを実行

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/install_whisper_cpp_vulkan.ps1
```

2. ggml モデルを配置

`ca_data/asr_models/whisper_cpp/ggml-large-v3-turbo.bin`

3. Windows ローカル起動時に環境変数を設定

```bat
set CODEAGENT_ASR_ENGINE=whisper_cpp
set CODEAGENT_WHISPER_CPP_BACKEND=vulkan
```

4. 起動

```bat
python main.py
```

または既存の `start.bat` を利用します。

## 注意

- Runpod ではこの設定を使わず、従来どおり `faster-whisper large-v3-turbo` を利用します。
- Dockerfile の faster-whisper 経路は変更不要です。
- `whisper.cpp` は ggml 形式モデルが必要です。
- 既存の faster-whisper モデル (`/opt/asr_models/large-v3-turbo`) は `whisper.cpp` に直接使えません。
