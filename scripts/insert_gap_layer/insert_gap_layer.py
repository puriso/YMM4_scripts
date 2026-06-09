# insert_gap_layer.py
#
# 使い方:
#
#   # デフォルト: レイヤー01 / 空白12フレーム
#   python scripts\insert_gap_layer\insert_gap_layer.py
#
#   # レイヤー02に対して実行
#   python scripts\insert_gap_layer\insert_gap_layer.py --layer 02
#
#   # 空白を24フレームにする
#   python scripts\insert_gap_layer\insert_gap_layer.py --layer 01 --gap 24
#
# 前提:
#   YMM4を起動して、MCP連携サーバーを起動しておくこと。
#   通常は http://localhost:8765/api に接続します。
#
# 動作:
#   指定レイヤー上のセリフアイテムをフレーム順に並べます。
#
#   前のセリフ末尾が 。 / ！ / ？ の場合だけ gap フレームを入れます。
#   セリフ末尾が 」 の場合は、その一個前の文字で判定します。
#
#   例:
#     今日は速い。      => gapを入れる
#     今日は速い！      => gapを入れる
#     今日は速い？      => gapを入れる
#     「今日は速い。」  => gapを入れる
#     「今日は速い」    => gapを入れない
#     今日は速い        => gapを入れない
#
# 注意:
#   実行するとYMM4へ反映し、プロジェクトも保存します。

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://localhost:8765/api"
DEFAULT_LAYER = "01"
DEFAULT_GAP = 12
DEFAULT_ENDINGS = "。！？"


def parse_layer(value: str) -> int:
    """
    '01' や '1' を 1 として扱う。
    '02' や '2' は 2 として扱う。
    """
    try:
        layer = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "layer は 01, 1, 02, 2 のような数値で指定してください"
        )

    if layer < 0:
        raise argparse.ArgumentTypeError("layer は0以上で指定してください")

    return layer


def request_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
) -> Any:
    data = None
    headers = {"Content-Type": "application/json"}

    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url=url,
        data=data,
        method=method,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            raw = res.read().decode("utf-8")

            if not raw:
                return {}

            return json.loads(raw)

    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {url}\n{raw}") from e

    except urllib.error.URLError as e:
        raise RuntimeError(
            "YMM4 MCPサーバーに接続できません。\n"
            "YMM4を起動し、MCP連携サーバーを起動してください。\n"
            f"接続先: {url}"
        ) from e


def get_items(base_url: str) -> list[dict[str, Any]]:
    """
    YMM4 MCPからアイテム一覧を取得する。
    実装差分に少し強くするため、list / { items: [...] } の両方に対応。
    """
    res = request_json("GET", f"{base_url}/items")

    if isinstance(res, list):
        return res

    if isinstance(res, dict) and isinstance(res.get("items"), list):
        return res["items"]

    raise RuntimeError(f"/items のレスポンス形式が想定外です: {res}")


def get_value(item: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """
    frame / Frame など、キー表記ゆれに対応して値を取得する。
    """
    for key in keys:
        if key in item:
            return item[key]

    return default


def get_int(item: dict[str, Any], *keys: str, default: int = 0) -> int:
    value = get_value(item, *keys, default=default)

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_text(item: dict[str, Any]) -> str:
    value = get_value(
        item,
        "text",
        "Text",
        "serif",
        "Serif",
        "sentence",
        "Sentence",
        default="",
    )

    return str(value)


def get_item_type(item: dict[str, Any]) -> str:
    return str(
        get_value(
            item,
            "type",
            "Type",
            "itemType",
            "ItemType",
            default="",
        )
    )


def is_target_speech_item(item: dict[str, Any], layer: int) -> bool:
    """
    指定レイヤーのセリフアイテムか判定する。
    基本は VoiceItem を対象にする。
    """
    item_layer = get_int(item, "layer", "Layer", default=-1)

    if item_layer != layer:
        return False

    item_type = get_item_type(item)

    # 通常のセリフアイテム想定
    if item_type == "VoiceItem":
        return True

    # 環境によって型名がフルネームで返る場合の保険
    if item_type in {
        "Voice",
        "VoiceItemModel",
        "YukkuriMovieMaker.Project.Items.VoiceItem",
    }:
        return True

    # type が取れない環境向けの保険
    # text / frame / length があるならセリフ扱いできる可能性が高い
    has_text = get_text(item) != ""
    has_frame = get_value(item, "frame", "Frame", default=None) is not None
    has_length = (
        get_value(
            item,
            "length",
            "Length",
            "duration",
            "Duration",
            default=None,
        )
        is not None
    )

    if not item_type and has_text and has_frame and has_length:
        return True

    return False


def item_summary(item: dict[str, Any]) -> str:
    text = get_text(item).replace("\n", " ")

    if len(text) > 40:
        return text[:40] + "..."

    return text


def effective_last_char(text: str) -> str:
    """
    セリフ末尾の判定用文字を返す。

    - 前後の空白・改行は無視
    - 末尾が 」 の場合は、その一個前の文字を見る

    例:
      今日は速い。      => 。
      「今日は速い。」  => 。
      「今日は速い」    => い
    """
    stripped = text.strip()

    if not stripped:
        return ""

    if stripped.endswith("」") and len(stripped) >= 2:
        return stripped[-2]

    return stripped[-1]


def should_insert_gap_after(item: dict[str, Any]) -> bool:
    """
    このセリフの後ろに gap を入れるか判定する。
    """
    last_char = effective_last_char(get_text(item))
    return last_char in set(DEFAULT_ENDINGS)


def update_item_frame_by_prop_endpoint(
    base_url: str,
    layer: int,
    current_frame: int,
    new_frame: int,
) -> Any:
    """
    ymm4MCP側のプロパティ編集APIを使ってFrameを変更する。
    layer + frame で対象アイテムを指定する方式。
    """
    payload = {
        "layer": layer,
        "frame": current_frame,
        "prop": "Frame",
        "value": str(new_frame),
    }

    return request_json("POST", f"{base_url}/items/prop", payload)


def update_item_frame_by_legacy_endpoint(
    base_url: str,
    layer: int,
    current_frame: int,
    new_frame: int,
) -> Any:
    """
    旧形式・別形式のエンドポイントがある環境向けの保険。
    """
    payload = {
        "layer": layer,
        "frame": current_frame,
        "prop": "Frame",
        "value": str(new_frame),
    }

    return request_json("POST", f"{base_url}/item/edit", payload)


def set_item_frame(
    base_url: str,
    layer: int,
    current_frame: int,
    new_frame: int,
) -> Any:
    """
    フレーム位置を変更する。
    まず /items/prop を試し、ダメなら /item/edit を試す。
    """
    try:
        return update_item_frame_by_prop_endpoint(
            base_url=base_url,
            layer=layer,
            current_frame=current_frame,
            new_frame=new_frame,
        )
    except RuntimeError as first_error:
        try:
            return update_item_frame_by_legacy_endpoint(
                base_url=base_url,
                layer=layer,
                current_frame=current_frame,
                new_frame=new_frame,
            )
        except RuntimeError:
            raise first_error


def save_project(base_url: str) -> Any:
    return request_json("POST", f"{base_url}/project/save", {})


def build_changes(
    speeches: list[dict[str, Any]],
    layer: int,
    gap: int,
) -> list[dict[str, Any]]:
    """
    変更内容を作る。

    前のセリフが 。！？ で終わる場合だけ gap を入れる。
    末尾が 」 の場合は、その一個前の文字で判定する。
    gap を入れない場合でも、セリフ同士が重なる場合は
    前のセリフの終了位置までは最低限ずらす。
    """
    changes: list[dict[str, Any]] = []

    # フレーム順に並べる
    speeches.sort(key=lambda item: get_int(item, "frame", "Frame"))

    # 後続計算で位置を更新したいためコピーする
    working_items = [dict(item) for item in speeches]

    for i in range(1, len(working_items)):
        prev = working_items[i - 1]
        current = working_items[i]

        prev_frame = get_int(prev, "frame", "Frame")
        prev_length = get_int(prev, "length", "Length", "duration", "Duration")
        current_frame = get_int(current, "frame", "Frame")

        prev_end_frame = prev_frame + prev_length

        insert_gap = should_insert_gap_after(prev)

        actual_gap = gap if insert_gap else 0
        required_frame = prev_end_frame + actual_gap

        if current_frame < required_frame:
            shift = required_frame - current_frame

            changes.append(
                {
                    "index": i,
                    "layer": layer,
                    "from": current_frame,
                    "to": required_frame,
                    "shift": shift,
                    "gap": actual_gap,
                    "insert_gap": insert_gap,
                    "prev_last_char": effective_last_char(get_text(prev)),
                    "prev_text": item_summary(prev),
                    "text": item_summary(current),
                }
            )

            # 後続の計算用に、メモリ上の現在位置も更新する
            current["frame"] = required_frame
            current["Frame"] = required_frame

    return changes


def print_changes(
    changes: list[dict[str, Any]],
    layer: int,
    gap: int,
) -> None:
    print(f"対象レイヤー: {layer:02d}")
    print(f"空白フレーム: {gap}")
    print(f"gap挿入条件: 前のセリフ末尾が {', '.join(DEFAULT_ENDINGS)}")
    print("末尾が 」 の場合は一個前の文字で判定")

    print()

    if not changes:
        print(f"レイヤー{layer:02d}に変更対象はありません。")
        return

    print("変更内容:")

    for change in changes:
        if change["insert_gap"]:
            reason = f"gap={change['gap']}f"
        else:
            reason = "gapなし・重なり回避のみ"

        print(
            f"- L{change['layer']:02d} "
            f"{change['from']}f -> {change['to']}f "
            f"(+{change['shift']}f, {reason}) "
            f"{change['text']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="YMM4 MCPで指定レイヤーのセリフ間に指定フレーム数の空白を入れる"
    )

    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"YMM4 MCP APIのURL。デフォルト: {DEFAULT_BASE_URL}",
    )

    parser.add_argument(
        "--layer",
        type=parse_layer,
        default=parse_layer(DEFAULT_LAYER),
        help="対象レイヤー。デフォルトは01。例: --layer 01 / --layer 1 / --layer 02",
    )

    parser.add_argument(
        "--gap",
        type=int,
        default=DEFAULT_GAP,
        help="セリフ間に入れる最低空白フレーム数。デフォルトは12。",
    )

    args = parser.parse_args()

    if args.gap < 0:
        raise RuntimeError("--gap は0以上で指定してください")

    items = get_items(args.base_url)

    speeches = [
        item
        for item in items
        if is_target_speech_item(item, args.layer)
    ]

    if len(speeches) <= 1:
        print(f"レイヤー{args.layer:02d}のセリフが {len(speeches)} 件なので変更不要です。")
        return 0

    changes = build_changes(
        speeches=speeches,
        layer=args.layer,
        gap=args.gap,
    )

    print_changes(
        changes=changes,
        layer=args.layer,
        gap=args.gap,
    )

    if not changes:
        return 0

    print()
    print("YMM4へ反映します...")

    for change in changes:
        res = set_item_frame(
            base_url=args.base_url,
            layer=change["layer"],
            current_frame=change["from"],
            new_frame=change["to"],
        )

        print(
            f"OK: L{change['layer']:02d} "
            f"{change['from']}f -> {change['to']}f "
            f"response={res}"
        )

    save_res = save_project(args.base_url)
    print()
    print(f"保存しました: {save_res}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
