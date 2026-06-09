# split_group_direct_ymmp

YMM4 の `.ymmp` ファイルを直接編集し、対象 GroupItem / グループ制御を `中性.*` の発話区間だけに合わせて分割するスクリプトです。

## 重要

このスクリプトは MCP 経由ではなく、YMM4 の `.ymmp` ファイルを直接読み書きします。

理由は、SCPgamerscp/ymm4MCP の公開 API には既存アイテムの編集 API はありますが、GroupItem / グループ制御を追加・複製する API がないためです。対象 GroupItem を `中性.*` の発話区間だけに複数個へ分割するには、MCP だけでは足りません。

`.ymmp` 直接編集は保存ファイルを書き換える重い操作です。実行前に YMM4 で対象プロジェクトを保存して閉じ、必ず dry-run で変更予定を確認してください。`--apply` 実行時は `.backup_YYYYMMDD_HHMMSS.ymmp` を自動作成しますが、念のため作業前に別名コピーも作ることを推奨します。

## 目的

- 対象 GroupItem / グループ制御を見つけます。
- `中性.*` に一致するキャラクターの VoiceItem だけを対象にします。
- 対象 GroupItem と対象 VoiceItem が重なる区間だけ、GroupItem を作ります。
- `中性.*` と重ならない区間の GroupItem は作りません。
- セリフ末尾の余韻は `--voice-tail-trim` でバウンス対象から外します。
- 中性セリフの余韻が次のセリフへ被る場合は、次のセリフ開始位置でも対象区間を打ち切ります。
- 元 GroupItem の X/Y 移動、レイヤー範囲、既存エフェクトなどは引き継ぎます。

## 前提条件

- Python 3
- YukkuriMovieMaker4
- 対象 `.ymmp` ファイル

外部 Python パッケージは使っていません。

## 使い方

リポジトリのルートディレクトリから実行します。

まず dry-run で変更予定を確認します。

```powershell
python scripts\split_group_direct_ymmp\split_group_direct_ymmp.py --project "C:\path\project.ymmp" --group-layers 1 --voice-layers 3
```

問題なければ `--apply` を付けて `.ymmp` を更新します。

```powershell
python scripts\split_group_direct_ymmp\split_group_direct_ymmp.py --project "C:\path\project.ymmp" --group-layers 1 --voice-layers 3 --apply
```

## 主なオプション

- `--project`
  - 対象 `.ymmp` ファイルのパス。
  - 必須です。
- `--group-layers`
  - 対象 GroupItem / グループ制御を絞るレイヤー。
  - カンマ区切りで複数指定できます。
  - 例: `1` / `1,10`
- `--group-memo`
  - 対象 GroupItem / グループ制御を絞る備考トークン。
  - 既定値: `t`
- `--speaker-regex`
  - 対象キャラクター名の正規表現。
  - 既定値: `中性.*`
- `--voice-layers`
  - 対象 VoiceItem を絞るレイヤー。
  - キャラクター判定は必ず `--speaker-regex` も通します。
  - 例: `3` / `3,4`
- `--voice-tail-trim`
  - セリフ末尾の余韻をバウンス対象から外すため、対象セリフの終端を詰めるフレーム数。
  - 既定値: `12`
- `--next-voice-gap`
  - 次のセリフ開始前に空けるフレーム数。
  - 中性セリフの余韻が次のセリフに被るのを避けるため、対象区間は `次のセリフ開始 - この値` でも打ち切ります。
  - 既定値: `0`
- `--apply`
  - 実際に `.ymmp` を上書きします。
  - 指定しない場合は dry-run です。

詳しい引数は `--help` でも確認できます。

```powershell
python scripts\split_group_direct_ymmp\split_group_direct_ymmp.py --help
```

## 安全性

- デフォルトは dry-run です。
- dry-run では対象件数と作成予定のバウンス区間を表示します。
- `--apply` 時は、更新前に `.backup_YYYYMMDD_HHMMSS.ymmp` を自動作成します。
- BOM 付き UTF-8 の `.ymmp` は、BOM 付きのまま書き戻します。
- YMM4 で対象プロジェクトを開いたまま実行すると、YMM4 側の保存で変更が上書きされる可能性があります。
