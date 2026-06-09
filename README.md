# YMM4 scripts

YukkuriMovieMaker4 (YMM4) の編集作業を補助するスクリプト集です。

## 方針

- `scripts/` 配下のスクリプトは、基本的に Python で書きます。
- 依存関係はできるだけ Python 標準ライブラリに寄せます。
- 外部パッケージが必要な場合は、理由とインストール方法を README またはスクリプト冒頭に書きます。
- YMM4 プロジェクトを変更する処理は、まず dry-run / preview で確認できるようにします。
- 実際に変更する操作は `--apply` など明示的なオプションを付けたときだけ実行します。

## 使い方

YMM4 と MCP 連携サーバーを起動してから、対象のスクリプトを実行します。

```powershell
python scripts\insert_gap_layer.py
python scripts\insert_gap_layer.py --apply
```

各スクリプトの詳しい引数や挙動は、ファイル冒頭のコメントと `--help` を確認してください。

```powershell
python scripts\insert_gap_layer.py --help
```

## スクリプト一覧

- `scripts/insert_gap_layer.py`
  - 指定レイヤー上のセリフアイテム間に、必要な空白フレームを作るための補助スクリプトです。

## 開発メモ

- Windows / PowerShell での実行を主な想定環境にします。
- ファイルは UTF-8 で保存します。
- スクリプトは `argparse` で CLI 化し、設定値をファイル先頭または引数で変更できる形にします。
- MCP API のレスポンス差分に備えて、キー名の揺れにはなるべく寛容にします。
- 破壊的な変更や保存を行う処理は、実行前に対象件数と変更予定を表示します。
