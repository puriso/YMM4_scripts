# script_launcher

各種 `scripts/` をブラウザ上のボタンと入力欄から実行するための簡易Web UIです。
画面は `web/index.html`、`web/styles.css`、`web/app.js` で構成し、ローカルのPython標準ライブラリHTTPサーバーから配信します。

## 使い方

リポジトリのルートディレクトリから実行します。

```powershell
python scripts\script_launcher\script_launcher.py
```

表示された `http://127.0.0.1:<port>/` をブラウザで開きます。
左側でスクリプトを選び、必要なオプションを入力して実行します。
実行中の標準出力とエラー出力は画面下部のログ欄に表示され、同時に `logs/script_launcher/` に保存されます。

## 登録済みスクリプト

- `insert_gap_layer`
  - YMM4 MCP経由でセリフ間に空白フレームを作ります。
  - 実行するとYMM4へ反映し、プロジェクトを保存します。
- `split_group_direct_ymmp`
  - `.ymmp` を直接読み、対象GroupItemをセリフ区間に分割します。
  - 既定はdry-runです。`.ymmpを上書きする` を有効にした場合だけ `--apply` を付けます。

## 新しいスクリプトの追加

UIへ追加する場合は、`script_launcher.py` 上部の `SCRIPT_DEFINITIONS` に `ScriptDefinition` を1件追加します。
各オプションは `OptionField` で定義します。

- `kind="text"`: 文字列入力
- `kind="int"`: 0以上の整数入力
- `kind="path"`: ファイルパス入力
- `kind="bool"`: チェックボックス。オンの場合だけフラグを付けます

見た目を変える場合は `web/styles.css`、画面の振る舞いを変える場合は `web/app.js` を編集します。
UIに載せる必要があるか迷うスクリプトは、追加前にユーザーへ確認してください。

## 確認

UIを起動できない環境でも、次のコマンドで登録内容を確認できます。

```powershell
python scripts\script_launcher\script_launcher.py --list-scripts
python scripts\script_launcher\script_launcher.py --help
```
