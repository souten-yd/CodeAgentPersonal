# Windows AMD Vulkan ASR セットアップ

Windows AMD 環境で `whisper.cpp` の Vulkan 版を ASR バックエンドとして使う手順です。

## セットアップ

通常はルート直下の wrapper を実行してください。

```bat
setup_whisper_cpp_vulkan_windows.bat
```

強制再インストール（whisper.cpp binary / model の再取得）は以下です。

```bat
setup_whisper_cpp_vulkan_windows.bat -Force
```

このセットアップで以下を自動取得します。

- `ca_data/bin/whisper.cpp-vulkan/`
- `ca_data/asr_models/whisper_cpp/ggml-large-v3-turbo.bin`

## 実行確認コマンド

セットアップ:

```bat
setup_whisper_cpp_vulkan_windows.bat -Force
```

確認:

```bat
dir ca_data\bin\whisper.cpp-vulkan /s /b | findstr /i "whisper-cli.exe main.exe whisper.exe"
dir ca_data\asr_models\whisper_cpp\ggml-large-v3-turbo.bin
```

起動:

```bat
set CODEAGENT_ASR_ENGINE=whisper_cpp
set CODEAGENT_WHISPER_CPP_BACKEND=vulkan
start.bat
```

## 起動時の環境変数

Windows ローカル起動時には最低限以下を設定します。

```bat
set CODEAGENT_ASR_ENGINE=whisper_cpp
set CODEAGENT_WHISPER_CPP_BACKEND=vulkan
```

`CODEAGENT_WHISPER_CPP_BIN` / `CODEAGENT_WHISPER_CPP_MODEL` は自動探索できるため、通常は未指定で問題ありません。
うまくいかない場合のみ明示指定してください。

## 注意

- Runpod ではこの wrapper を使わず、従来どおり `faster-whisper large-v3-turbo` を利用します。
- Dockerfile / `docker/start-services.sh` / Runpod の faster-whisper 経路は変更不要です。
- `whisper.cpp` は ggml 形式モデルが必要です。
- 既存の faster-whisper モデル (`/opt/asr_models/large-v3-turbo`) は `whisper.cpp` に直接使えません。
- ブラウザ録音の `webm` を `whisper.cpp` に渡す場合は `ffmpeg` が必要です。
- `wav` 入力だけを扱う場合は `ffmpeg` は不要です。
- Windows では `ffmpeg.exe` を PATH に通しておいてください。
