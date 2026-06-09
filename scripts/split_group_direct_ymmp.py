# -*- coding: utf-8 -*-

"""
YMM4 .ymmp 直接編集版:
  指定したグループ制御 / GroupItem を、中性.* のセリフ区間だけに合わせて分割する。

使い方:
  1. YMM4で対象プロジェクトを保存して閉じる
  2. 念のため対象 .ymmp を別名コピーしておく
  3. まず dry-run で分割予定を確認する
  4. 問題なければ --apply を付けて実行する

実行例:
  python scripts\\split_group_direct_ymmp.py --project "C:\\path\\project.ymmp" --group-layers 1 --voice-layers 3
  python scripts\\split_group_direct_ymmp.py --project "C:\\path\\project.ymmp" --group-layers 1 --voice-layers 3 --apply

注意:
  - デフォルトは dry-run です。
  - --apply 時は .backup_YYYYMMDD_HHMMSS.ymmp を自動作成してから上書きします。
  - 中性.* にかぶっていない区間の GroupItem は作りません。
  - 対象セリフの終端は、余韻カットと次のセリフ開始位置の早い方で打ち切ります。
  - 元 GroupItem の X/Y 移動、レイヤー範囲、既存エフェクトなどはそのまま引き継ぎます。
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TARGET_GROUP_MEMO = "t"
SPEAKER_REGEX = r"中性.*"
AUTO_MEMO_BOUNCE = "auto:t:neutral_bounce"
DEFAULT_VOICE_TAIL_TRIM = 12
DEFAULT_NEXT_VOICE_GAP = 0


@dataclass(frozen=True)
class TimelineItem:
    raw: dict[str, Any]
    container: list[Any]
    index: int
    layer: int
    frame: int
    length: int
    type_name: str
    text: str
    memo: str
    character: str

    @property
    def end(self) -> int:
        return self.frame + self.length


def parse_layer_set(value: str) -> set[int]:
    value = value.strip()

    if not value:
        return set()

    layers: set[int] = set()

    for part in re.split(r"[\s,，、]+", value):
        if not part:
            continue

        try:
            layer = int(part)
        except ValueError as e:
            raise argparse.ArgumentTypeError(
                f"layer は数値で指定してください: {part!r}"
            ) from e

        if layer < 0:
            raise argparse.ArgumentTypeError("layer は0以上で指定してください")

        layers.add(layer)

    return layers


def pick(raw: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return default


def normalize_key(value: str) -> str:
    return value.replace("_", "").replace("-", "").replace(" ", "").lower()


def find_value_deep(raw: Any, aliases: set[str], *, max_depth: int = 4) -> Any:
    if max_depth < 0:
        return None

    if isinstance(raw, dict):
        normalized_aliases = {normalize_key(alias) for alias in aliases}

        for key, value in raw.items():
            if value is not None and normalize_key(str(key)) in normalized_aliases:
                return value

        for value in raw.values():
            found = find_value_deep(value, aliases, max_depth=max_depth - 1)
            if found is not None:
                return found

    elif isinstance(raw, list):
        for value in raw:
            found = find_value_deep(value, aliases, max_depth=max_depth - 1)
            if found is not None:
                return found

    return None


def pick_deep(raw: dict[str, Any], *keys: str, default: Any = "") -> Any:
    direct = pick(raw, *keys, default=None)
    if direct is not None:
        return direct

    found = find_value_deep(raw, set(keys))
    if found is not None:
        return found

    return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def get_existing_key(raw: dict[str, Any], *keys: str, default: str) -> str:
    for key in keys:
        if key in raw:
            return key
    return default


def set_item_frame(raw: dict[str, Any], frame: int) -> None:
    raw[get_existing_key(raw, "Frame", "frame", "startFrame", "StartFrame", default="Frame")] = frame


def set_item_length(raw: dict[str, Any], length: int) -> None:
    raw[get_existing_key(raw, "Length", "length", "duration", "Duration", default="Length")] = length


def set_item_memo(raw: dict[str, Any], memo: str) -> None:
    raw[get_existing_key(raw, "Memo", "memo", "Note", "note", "Remark", "remark", default="Memo")] = memo


def item_blob(raw: dict[str, Any]) -> str:
    try:
        return json.dumps(raw, ensure_ascii=False)
    except Exception:
        return str(raw)


def normalize_item(raw: dict[str, Any], container: list[Any], index: int) -> TimelineItem:
    return TimelineItem(
        raw=raw,
        container=container,
        index=index,
        layer=to_int(pick(raw, "Layer", "layer")),
        frame=to_int(pick(raw, "Frame", "frame", "startFrame", "StartFrame")),
        length=to_int(pick(raw, "Length", "length", "duration", "Duration")),
        type_name=to_text(pick(raw, "$type", "Type", "type", "itemType", "ItemType")),
        text=to_text(pick(raw, "Text", "text", "Serif", "serif", "displayName", "DisplayName")),
        memo=to_text(
            pick_deep(
                raw,
                "Memo",
                "memo",
                "Note",
                "note",
                "Remark",
                "remark",
                "Comment",
                "comment",
                "備考",
                "メモ",
            )
        ),
        character=to_text(
            pick_deep(
                raw,
                "CharacterName",
                "characterName",
                "Character",
                "character",
                "Speaker",
                "speaker",
                "VoiceName",
                "voiceName",
            )
        ),
    )


def looks_like_timeline_item(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False

    has_position = (
        pick(raw, "Layer", "layer", default=None) is not None
        and pick(raw, "Frame", "frame", "startFrame", "StartFrame", default=None) is not None
        and pick(raw, "Length", "length", "duration", "Duration", default=None) is not None
    )

    if not has_position:
        return False

    type_name = to_text(pick(raw, "$type", "Type", "type", "itemType", "ItemType"))
    return type_name.endswith("Item") or "Item" in type_name or "Group" in type_name


def iter_timeline_items(root: Any) -> list[TimelineItem]:
    items: list[TimelineItem] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for index, entry in enumerate(value):
                if looks_like_timeline_item(entry):
                    items.append(normalize_item(entry, value, index))
                else:
                    walk(entry)
        elif isinstance(value, dict):
            for child in value.values():
                walk(child)

    walk(root)
    return items


def is_group_item(item: TimelineItem) -> bool:
    blob = item_blob(item.raw)
    return (
        "GroupItem" in item.type_name
        or "GroupControl" in item.type_name
        or "GroupItem" in blob
        or "GroupControl" in blob
        or "グループ制御" in blob
    )


def is_voice_item(item: TimelineItem) -> bool:
    blob = item_blob(item.raw)
    return (
        "VoiceItem" in item.type_name
        or "VoiceItem" in blob
        or "ボイス" in item.type_name
        or "セリフ" in item.type_name
    )


def memo_has_token(memo: str, token: str) -> bool:
    memo = memo.strip()

    if memo == token:
        return True

    return token in re.split(r"[\s,，、]+", memo)


def speaker_matches(item: TimelineItem, speaker_re: re.Pattern[str]) -> bool:
    return bool(item.character and speaker_re.match(item.character))


def overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> tuple[int, int] | None:
    start = max(a_start, b_start)
    end = min(a_end, b_end)

    if start < end:
        return start, end

    return None


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []

    ranges = sorted(ranges)
    merged = [ranges[0]]

    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]

        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def split_group_range(
    group_start: int,
    group_end: int,
    voice_ranges: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    clipped_ranges = []

    for voice_start, voice_end in voice_ranges:
        clipped = overlap(group_start, group_end, voice_start, voice_end)
        if clipped:
            clipped_ranges.append(clipped)

    return merge_ranges(clipped_ranges)


def build_voice_ranges(
    *,
    target_voices: list[TimelineItem],
    all_voices: list[TimelineItem],
    tail_trim: int,
    next_voice_gap: int,
) -> list[tuple[int, int]]:
    voice_starts = sorted({voice.frame for voice in all_voices})
    ranges: list[tuple[int, int]] = []

    for voice in sorted(target_voices, key=lambda item: item.frame):
        end = max(voice.frame, voice.end - tail_trim)

        next_starts = [
            frame
            for frame in voice_starts
            if frame > voice.frame
        ]

        if next_starts:
            next_voice_start = next_starts[0]
            end = min(end, max(voice.frame, next_voice_start - next_voice_gap))

        if voice.frame < end:
            ranges.append((voice.frame, end))

    return ranges


def build_split_items(
    group: TimelineItem,
    segments: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    split_items: list[dict[str, Any]] = []

    for start, end in segments:
        new_raw = copy.deepcopy(group.raw)
        # Frame / Length / Memo 以外は元GroupItemを維持する。
        # X/Y移動、レイヤー範囲、既存エフェクトなどを壊さないため。
        set_item_frame(new_raw, start)
        set_item_length(new_raw, end - start)

        memo = f"{group.memo} {AUTO_MEMO_BOUNCE}".strip()
        set_item_memo(new_raw, memo)

        split_items.append(new_raw)

    return split_items


def make_backup_path(project_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return project_path.with_name(f"{project_path.stem}.backup_{timestamp}{project_path.suffix}")


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def has_utf8_bom(path: Path) -> bool:
    with path.open("rb") as f:
        return f.read(3) == b"\xef\xbb\xbf"


def write_json_file(path: Path, data: Any, *, preserve_bom: bool) -> None:
    encoding = "utf-8-sig" if preserve_bom else "utf-8"

    with path.open("w", encoding=encoding, newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="YMM4 .ymmp を直接編集し、GroupItem を中性.* のセリフ区間だけに合わせて分割します。"
    )
    parser.add_argument(
        "--project",
        type=Path,
        required=True,
        help="対象 .ymmp ファイルのパス。",
    )
    parser.add_argument(
        "--group-memo",
        default=TARGET_GROUP_MEMO,
        help=f"対象グループの備考トークン。デフォルト: {TARGET_GROUP_MEMO}",
    )
    parser.add_argument(
        "--group-layers",
        type=parse_layer_set,
        default=parse_layer_set(""),
        help="対象グループレイヤー。カンマ区切り可。例: 1 / 1,10",
    )
    parser.add_argument(
        "--speaker-regex",
        default=SPEAKER_REGEX,
        help=f"対象話者/キャラクター名の正規表現。デフォルト: {SPEAKER_REGEX}",
    )
    parser.add_argument(
        "--voice-layers",
        type=parse_layer_set,
        default=parse_layer_set(""),
        help="対象セリフを絞るレイヤー。キャラクター判定は必ず --speaker-regex も通します。例: 3 / 3,4",
    )
    parser.add_argument(
        "--voice-tail-trim",
        type=int,
        default=DEFAULT_VOICE_TAIL_TRIM,
        help=(
            "セリフ末尾の余韻をバウンス対象から外すため、"
            f"対象セリフの終端を詰めるフレーム数。デフォルト: {DEFAULT_VOICE_TAIL_TRIM}"
        ),
    )
    parser.add_argument(
        "--next-voice-gap",
        type=int,
        default=DEFAULT_NEXT_VOICE_GAP,
        help=(
            "次のセリフ開始前に空けるフレーム数。"
            "中性セリフの余韻が次のセリフに被るのを避けるため、"
            f"対象区間は次のセリフ開始 - この値でも打ち切ります。デフォルト: {DEFAULT_NEXT_VOICE_GAP}"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="実際に .ymmp を上書きします。指定しない場合はdry-runです。",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    project_path = args.project.resolve()

    if not project_path.exists():
        print(f"project が見つかりません: {project_path}")
        return 1

    if args.apply:
        print("注意: YMM4で対象プロジェクトを閉じてから実行してください。")

    preserve_bom = has_utf8_bom(project_path)

    try:
        project = load_json_file(project_path)
    except Exception as e:
        print(f".ymmp の読み込みに失敗しました: {project_path}")
        print(e)
        return 1

    items = iter_timeline_items(project)

    try:
        speaker_re = re.compile(args.speaker_regex)
    except re.error as e:
        print(f"--speaker-regex が不正です: {args.speaker_regex!r}")
        print(e)
        return 1

    target_groups = [
        item for item in items
        if (
            is_group_item(item)
            and (
                memo_has_token(item.memo, args.group_memo)
                or item.layer in args.group_layers
            )
            and AUTO_MEMO_BOUNCE not in item.memo
        )
    ]
    target_voices = [
        item for item in items
        if (
            is_voice_item(item)
            and (not args.voice_layers or item.layer in args.voice_layers)
            and speaker_matches(item, speaker_re)
            and item.length > 0
        )
    ]
    all_voices = [
        item for item in items
        if (
            is_voice_item(item)
            and (not args.voice_layers or item.layer in args.voice_layers)
            and item.length > 0
        )
    ]

    print(f"取得アイテム数: {len(items)}")
    print(f"対象グループ制御: {len(target_groups)}件")
    print(f"対象セリフ: {len(target_voices)}件")

    if not target_groups:
        print("対象グループ制御が見つかりません。--group-layers または --group-memo を確認してください。")
        return 1

    if not target_voices:
        print("対象セリフが見つかりません。キャラクターが --speaker-regex に一致しているか確認してください。")
        return 1

    tail_trim = max(0, args.voice_tail_trim)
    next_voice_gap = max(0, args.next_voice_gap)
    voice_ranges = build_voice_ranges(
        target_voices=target_voices,
        all_voices=all_voices,
        tail_trim=tail_trim,
        next_voice_gap=next_voice_gap,
    )

    if not voice_ranges:
        print("余韻カット後に対象セリフ区間が残りません。--voice-tail-trim を小さくしてください。")
        return 1

    print(f"セリフ余韻カット: {tail_trim}f")
    print(f"次セリフ手前カット: {next_voice_gap}f")

    plan: list[tuple[TimelineItem, list[tuple[int, int]]]] = []

    for group in target_groups:
        segments = split_group_range(group.frame, group.end, voice_ranges)
        if segments:
            plan.append((group, segments))

    if not plan:
        print("グループ制御と中性.* のセリフ時間が重なっていません。")
        return 0

    print()
    print("バウンス作成予定:")

    total_new_items = 0

    for group, segments in plan:
        total_new_items += len(segments)
        print()
        print(
            f"- group layer={group.layer}, "
            f"frame={group.frame}, "
            f"length={group.length}, "
            f"memo={group.memo!r}"
        )

        for start, end in segments:
            print(f"  - バウンス: {start}f〜{end}f length={end - start}")

    print()
    print(f"置換対象グループ: {len(plan)}件")
    print(f"作成するバウンスグループ総数: {total_new_items}件")

    if not args.apply:
        print()
        print("dry-run のため、変更せず終了します。")
        return 0

    by_container: dict[int, list[tuple[TimelineItem, list[dict[str, Any]]]]] = {}

    for group, segments in plan:
        split_items = build_split_items(group, segments)
        by_container.setdefault(id(group.container), []).append((group, split_items))

    for entries in by_container.values():
        container = entries[0][0].container

        for group, split_items in sorted(entries, key=lambda entry: entry[0].index, reverse=True):
            container[group.index:group.index + 1] = split_items

    backup_path = make_backup_path(project_path)
    shutil.copy2(project_path, backup_path)
    write_json_file(project_path, project, preserve_bom=preserve_bom)

    print()
    print(f"バックアップ作成: {backup_path}")
    print(f"更新完了: {project_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
