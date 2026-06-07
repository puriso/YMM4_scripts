# insert_gap_layer.py
#
# 使い方:
#
#   # 変更予定だけ確認。デフォルトはレイヤー01、空白12フレーム
#   python insert_gap_layer.py
#
#   # 実際に反映
#   python insert_gap_layer.py --apply
#
#   # レイヤー02に対して実行
#   python insert_gap_layer.py --layer 02 --apply
#
#   # レイヤー01に24フレーム空白を入れる
#   python insert_gap_layer.py --layer 01 --gap 24 --apply
#
#   # 反映後にYMM4プロジェクトを保存
#   python insert_gap_layer.py --apply --save
#
# 前提:
#   YMM4を起動して、MCP連携サーバーを起動しておくこと。
#   通常は http://localhost:8765/api に接続します。
#
# 動作:
#   指定レイヤー上のセリフアイテムをフレーム順に並べ、
#   前のセリフの終了位置 + gap より前に次のセリフがある場合、
#   次のセリフを右へずらして、最低 gap フレームの空白を作ります。
#
# 注意:
#   --apply を付けない限り、実際には変更しません。
#   まず python insert_gap_layer.py だけで変更予定を確認するのがおすすめです。

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://localhost:8765/api"


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
    value = get_value(item, "text", "Text", "serif", "Serif", default="")
    return str(value)


def get_item_type(item: dict[str, Any]) -> str:
    return str(get_value(item, "type", "Type", "itemType", "ItemType", default=""))


def is_target_speech_item(item: dict[str, Any], layer: int) -> bool:
    item_layer = get_int(item, "layer", "Layer", default=-1)

    if item_layer != layer:
        return False

    item_type = get_item_type(item)

    # 通常のセリフアイテム想定
    if item_type == "VoiceItem":
        return True

    # 環境によっては AudioItem / TextItem などで返る可能性があるため保険
    # ただし、誤爆が怖い場合はここを VoiceItem のみに絞ってください。
    if item_type in {"Voice", "VoiceItemModel", "YukkuriMovieMaker.Project.Items.VoiceItem"}:
        return True

    # type が取れない環境向けの保険
    # text / frame / length があるならセリフ扱いできる可能性が高い
    has_text = get_text(item) != ""
    has_frame = get_value(item, "frame", "Frame", default=None) is not None
    has_length = get_value(item, "length", "Length", "duration", "Duration", default=None) is not None

    if not item_type and has_text and has_frame and has_length:
        return True

    return False


def item_summary(item: dict[str, Any]) -> str:
    text = get_text(item).replace("\n", " ")
    if len(text) > 40:
        return text[:40] + "..."
    return text


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
    変更予定を作る。
    前のセリフの終了位置 + gap より前に次のセリフがある場合、
    次のセリフを required_frame まで右にずらす。
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

        required_frame = prev_frame + prev_length + gap

        if current_frame < required_frame:
            shift = required_frame - current_frame

            changes.append(
                {
                    "index": i,
                    "layer": layer,
                    "from": current_frame,
                    "to": required_frame,
                    "shift": shift,
                    "text": item_summary(current),
                }
            )

            # 後続の計算用に、メモリ上の現在位置も更新する
            current["frame"] = required_frame
            current["Frame"] = required_frame

    return changes


def print_changes(changes: list[dict[str, Any]], layer: int, gap: int) -> None:
    print(f"対象レイヤー: {layer:02d}")
    print(f"空白フレーム: {gap}")
    print()

    if not changes:
        print(f"レイヤー{layer:02d}のセリフ間は、すでに最低{gap}フレーム空いています。")
        return

    print("変更予定:")
    for change in changes:
        print(
            f"- L{change['layer']:02d} "
            f"{change['from']}f -> {change['to']}f "
            f"(+{change['shift']}f) "
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
        default=parse_layer("01"),
        help="対象レイヤー。デフォルトは01。例: --layer 01 / --layer 1 / --layer 02",
    )

    parser.add_argument(
        "--gap",
        type=int,
        default=12,
        help="セリフ間に入れる最低空白フレーム数。デフォルトは12。",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="実際にYMM4へ反映する。付けない場合は変更予定の表示のみ。",
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="反映後にYMM4プロジェクトを保存する。",
    )

    args = parser.parse_args()

    if args.gap < 0:
        raise RuntimeError("--gap は0以上で指定してください")

    items = get_items(args.base_url)

    speeches = [
        item for item in items
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

    if not args.apply:
        print()
        print("まだ反映していません。")
        print("反映する場合は --apply を付けて実行してください。")
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

    if args.save:
        save_res = save_project(args.base_url)
        print()
        print(f"保存しました: {save_res}")
    else:
        print()
        print("反映しました。必要ならYMM4側で保存してください。")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)