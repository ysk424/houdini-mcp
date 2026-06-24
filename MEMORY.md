# HoudiniMCP Continuation Memory

最終更新: 2026-06-23

## 現在の環境

- リポジトリ: `C:\Users\azoo\git\houdini-mcp`
- ブランチ: `private/multi-client`
- Houdini: Steam版 Houdini Indie 21.0.729
- 実行ファイル:
  `C:\Program Files (x86)\Steam\steamapps\common\Houdini Indie\bin\hindie.steam.exe`
- Houdini側TCPサーバー: `localhost:9876`
- インストール先:
  `C:\Users\azoo\Documents\houdini21.0\scripts\python\houdinimcp`
- Codex設定: `C:\Users\azoo\.codex\config.toml`

## 2026-06-23 起動問題の原因

### 1. CodexにHoudini MCPが登録されていなかった

Houdini側で9876番ポートが待受していても、Codexの`config.toml`に
`[mcp_servers.houdini]`がなかったため、CodexへHoudiniツールが表示されなかった。

修正:

- `scripts/install.py --codex`を追加
- リポジトリの`.venv\Scripts\python.exe`から
  `houdini_mcp_server.py`を起動する設定をCodexへ書く

Codexへツールを反映するにはCodexの再起動が必要。

### 2. 停止済みサーバーを起動中と誤判定していた

旧`start_server()`は`hou.session.houdinimcp_server`オブジェクトが存在するだけで
起動済みと判断していた。bind失敗後や停止後にオブジェクトが残ると、再importしても
サーバーを再開できなかった。

修正:

- `running`と`socket`を確認
- staleなインスタンスを停止して新規作成
- 起動失敗時は`hou.session.houdinimcp_server = None`へ戻す
- シェルフのToggleも同じ実状態判定へ変更

実機で、停止済みオブジェクトを意図的に残した状態から再起動できることを確認済み。

### 3. 通常SideFX版をSteam Indie版より優先していた

`scripts/launch.py`は通常版`houdini.exe`を先に検出していた。このPCではSteam版Indie
ライセンスを使うため、通常版経路ではライセンス判定を誤る。

修正:

- WindowsではSteam版`hindie.steam.exe`を最優先

### 4. WindowsのCP932でテストとインストーラーが失敗した

- インストーラー内の長音記号で`UnicodeEncodeError`
- テストがUTF-8ソースを既定CP932で読み込んで失敗
- RAG文書パスがWindows区切りの`\`になった

修正:

- コンソール出力をASCIIへ変更
- テストのファイル読み書きへ`encoding="utf-8"`を指定
- RAG相対パスを`as_posix()`で正規化

## 検証結果

- Houdini側stale server回復テスト: 成功
- TCP `localhost:9876`: 接続成功
- MCP `ping`: 成功
- Codex `config.toml`: TOML解析成功
- リポジトリとHoudiniインストール済みファイルのハッシュ一致
- Steam版Houdini検出: 成功
- 全pytest: `319 passed, 13 skipped`

## 2026-06-24 起動直後に反応しない問題

原因:

- インストーラーが `Documents\houdini21.0\scripts\pythonrc.py` に
  `import houdinimcp` を書いていたが、Houdini 21 GUI起動ではこの場所が実行されて
  いなかった。
- シェルフ/操作パネルからStop/Startすると接続できたのは、UI起動後に手動で
  `start_server()` が走るため。
- 診断中に `scripts/python/uiready.py` と複数タイマーも試したが、これは
  "Houdini MCP Server is already running." を複数回出すだけなので撤去した。

修正:

- 自動起動は1箇所のみ:
  `C:\Users\azoo\Documents\houdini21.0\python3.11libs\uiready.py`
- 内容は1行だけ:
  `import houdinimcp  # Auto-start HoudiniMCP server`
- `src/houdinimcp/__init__.py` はimport時に `initialize_plugin()` ->
  `start_server()` を1回だけ呼ぶ。
- `scripts/install.py` は今後 `python3.11libs\uiready.py` だけを作り、
  legacyな `scripts\pythonrc.py` / `scripts\python\uiready.py` の
  HoudiniMCP auto-start行を掃除する。

検証:

- 起動後のMCP `ping`: 成功
- `uv run pytest tests\test_plugin_startup.py`: `4 passed`

## 再起動後の確認

1. Codexを再起動する
2. HoudiniをSteam版から起動する
3. 起動直後に9876番ポートがlistenしていることを確認する
4. Codexに`mcp__houdini__*`ツールが表示されることを確認する
5. Houdini MCPの`ping`を実行する
6. `get_scene_info`でGUI上の現在のHIPを確認する

問題があれば:

```powershell
.\.venv\Scripts\python.exe scripts\install.py --houdini-version 21.0 --codex
```

を再実行し、HoudiniとCodexを再起動する。

## 関連プロジェクト

ヘアシミュレーション:

`C:\Users\azoo\git\houdini-hair-simulation`

通常作業用HIP:

`houdini\hair_body_test_v001.hiplc`

原型HIP:

`houdini\yoko_hair_sim2_v003_RC2.hiplc`

原型は変更せず、WORK用HIPだけを編集・保存する。
