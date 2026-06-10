# Repository Guidelines

## 基本方針

- このリポジトリの `scripts/` は、基本的に Python で実装する。
- まず既存スクリプトの書き方に合わせ、必要以上に新しい構成や依存関係を増やさない。
- YMM4 MCP 連携を前提にする処理では、接続先 URL、対象レイヤー、対象文字列などを変更しやすい場所に置く。
- YMM4 MCP サーバの仕様は、`SCPgamerscp/ymm4MCP`（https://github.com/SCPgamerscp/ymm4MCP）を基準にする。

## Python スクリプトの書き方

- Python 3 向けに書く。
- 標準ライブラリで足りる処理は標準ライブラリを使う。
- CLI は `argparse` を使い、`--help` で用途と主要オプションが分かるようにする。
- `main() -> int` を用意し、末尾は `raise SystemExit(main())` または `sys.exit(main())` にする。
- 型ヒントを付ける。複雑なデータ構造は `dataclass` や小さなヘルパー関数で整理する。
- 文字コードは UTF-8 を前提にする。

## ディレクトリ構成

- 単体で完結する小さなスクリプトは `scripts/<name>.py` に置く。
- 仕様説明、長めの使い方、補助ファイル、サンプルなどを一緒に管理したいスクリプトは `scripts/<name>/<name>.py` のようにディレクトリ化する。
- ディレクトリ化したスクリプトには、同じディレクトリに `README.md` を置き、仕様、使い方、前提条件、注意点を書く。
- ルート `README.md` のスクリプト一覧から、ディレクトリ内の `README.md` へ誘導する。

## UI ランチャー

- 各種スクリプトをWeb UIから実行する入口は `scripts/script_launcher/script_launcher.py` に置く。
- UIはメンテナンスしやすさを優先し、画面は `scripts/script_launcher/web/` の HTML/CSS/シンプルな JavaScript で実装する。
- ローカルスクリプト実行はブラウザだけではできないため、`scripts/script_launcher/script_launcher.py` の標準ライブラリHTTPサーバー経由で行う。外部パッケージは必要になるまで増やさない。
- UIへスクリプトを追加する場合は、`SCRIPT_DEFINITIONS` に定義を1件追加し、既存CLIの引数名・既定値と揃える。
- 新しいスクリプトを追加したら、UIに載せるかユーザーへ確認する。載せる場合は `scripts/script_launcher/README.md` も更新する。
- UIから実行する処理は、実行コマンド、開始/終了時刻、標準出力、標準エラー、終了コードをログとして確認できるようにする。

## 安全性

- YMM4 プロジェクトを変更する処理は、原則として変更内容を実行前に表示する。
- dry-run や保存オプションを分けるか、実行時に即反映・即保存するかは、スクリプトの用途に合わせて決める。
- 即反映・即保存するスクリプトは、その動作をスクリプト内コメントと README に明記する。
- 削除、移動、一括変更のような処理は、対象件数と変更内容を実行前に表示する。
- ユーザー固有の絶対パスをハードコードしない。必要なら引数や設定値にする。
- PR には、ユーザー固有の絶対パスやローカル環境に依存する設定値・生成物を含めない。

## ドキュメント

- 新しいスクリプトを追加したら README のスクリプト一覧に追記する。
- スクリプト冒頭には、目的、前提条件、代表的な実行例、注意点を書く。
- 外部パッケージが必要になった場合は、README に依存関係とインストール方法を書く。

## 確認

- 変更後は、少なくとも `python <script> --help` または dry-run 実行で構文と表示を確認する。
- UIランチャーを変更した場合は、`python scripts\script_launcher\script_launcher.py --help` と `python scripts\script_launcher\script_launcher.py --list-scripts` を確認する。
- YMM4 MCP が必要なスクリプトは、MCP 未起動時のエラー表示が分かりやすいことも確認する。
