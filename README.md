# YMM4 scripts

YukkuriMovieMaker4 (YMM4) の編集作業を補助するスクリプト集です。

## 方針

- `scripts/` 配下のスクリプトは、基本的に Python で書きます。
- 依存関係はできるだけ Python 標準ライブラリに寄せます。
- 外部パッケージが必要な場合は、理由とインストール方法を README またはスクリプト冒頭に書きます。
- YMM4 プロジェクトを変更する処理は、実行前に対象件数と変更内容が分かるようにします。
- 即反映・即保存するスクリプトは、その動作を個別 README に明記します。

## 使い方

YMM4 と MCP 連携サーバーを起動してから、対象のスクリプトを実行します。

```powershell
python scripts\insert_gap_layer\insert_gap_layer.py
python scripts\insert_gap_layer\insert_gap_layer.py --layer 02 --gap 24
```

各スクリプトの詳しい引数や挙動は、ファイル冒頭のコメントと `--help` を確認してください。

```powershell
python scripts\insert_gap_layer\insert_gap_layer.py --help
```

## 重要: `.ymmp` 直接編集について

`scripts/split_group_direct_ymmp.py` は MCP 経由ではなく、YMM4 の `.ymmp` ファイルを直接読み書きします。

理由は、SCPgamerscp/ymm4MCP の公開 API には既存アイテムの編集 API はありますが、GroupItem / グループ制御を追加・複製する API がないためです。今回の処理では、対象グループを `中性.*` の発話区間だけに複数個へ分割する必要があるため、MCP だけでは実現できません。

直接編集は YMM4 の保存ファイルを書き換える重い操作です。実行前に YMM4 で対象プロジェクトを保存して閉じ、必ず dry-run で変更予定を確認してください。`--apply` 実行時は `.backup_YYYYMMDD_HHMMSS.ymmp` を自動作成しますが、念のため作業前に別名コピーも作ることを推奨します。

## スクリプト一覧

- `scripts/insert_gap_layer/`
  - 指定レイヤー上のセリフアイテム間に、必要な空白フレームを作るための補助スクリプトです。
  - 詳細な仕様と使い方は `scripts/insert_gap_layer/README.md` を確認してください。
- `scripts/split_group_direct_ymmp.py`
  - `.ymmp` を直接編集し、対象 GroupItem を `中性.*` のセリフ区間だけに合わせて複数の GroupItem に分割するスクリプトです。
  - デフォルトは dry-run です。`--apply` 時は `.backup_YYYYMMDD_HHMMSS.ymmp` を自動作成してから上書きします。
  - `中性.*` と重ならない区間の GroupItem は作りません。セリフ末尾の余韻は `--voice-tail-trim` でバウンス対象から外します。
  - 分割後の GroupItem は、元の X/Y 移動、レイヤー範囲、既存エフェクトなどを引き継ぎます。

## 開発メモ

- Windows / PowerShell での実行を主な想定環境にします。
- ファイルは UTF-8 で保存します。
- スクリプトは `argparse` で CLI 化し、設定値をファイル先頭または引数で変更できる形にします。
- MCP API のレスポンス差分に備えて、キー名の揺れにはなるべく寛容にします。
- 破壊的な変更や保存を行う処理は、実行前に対象件数と変更予定を表示します。
