from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import subprocess
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse


MEDIA_FOLDER_NAMES = ()
VIEWER_DIR = Path(__file__).resolve().parent / "viewer"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "video_viewer_sources.json"
VIDEO_SUFFIX = ".mp4"
MEDIA_PROBE_CACHE: dict[str, tuple[int, int, dict[str, Any]]] = {}


def source_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).casefold().encode("utf-8")).hexdigest()[:12]


def make_source(path: Path, label: str | None = None, persistent: bool = True) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    return {
        "id": source_id(resolved),
        "path": str(resolved),
        "label": label or resolved.name or str(resolved),
        "persistent": persistent,
        "exists": resolved.is_dir(),
    }


def load_config(config_path: Path) -> list[dict[str, Any]]:
    if not config_path.is_file():
        return []
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []

    sources: list[dict[str, Any]] = []
    for entry in payload.get("sources", []) if isinstance(payload, dict) else []:
        if isinstance(entry, str):
            path = Path(entry)
            label = None
        elif isinstance(entry, dict) and entry.get("path"):
            path = Path(str(entry["path"]))
            label = str(entry.get("label") or "") or None
        else:
            continue
        sources.append(make_source(path, label, True))
    return sources


def save_config(config_path: Path, sources: list[dict[str, Any]]) -> None:
    payload = {
        "sources": [
            {"path": source["path"], "label": source["label"]}
            for source in sources
        ]
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def merge_sources(*source_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in source_groups:
        for source in group:
            key = str(Path(source["path"]).resolve()).casefold()
            if key in seen:
                continue
            seen.add(key)
            source["exists"] = Path(source["path"]).is_dir()
            merged.append(source)
    return merged


def find_matching_info(video_path: Path) -> Path | None:
    for candidate in video_path.parent.iterdir():
        if (
            candidate.is_file()
            and candidate.suffix.lower() == ".txt"
            and candidate.stem.casefold() == video_path.stem.casefold()
        ):
            return candidate
    return None


def parse_key_values(text: str) -> tuple[dict[str, str], str, list[str]]:
    values: dict[str, str] = {}
    prompt_lines: list[str] = []
    reference_mapping: list[str] = []
    in_prompt = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        marker = line.strip()
        if marker == "PROMPT BEGIN":
            in_prompt = True
            continue
        if marker == "PROMPT END":
            in_prompt = False
            continue
        if in_prompt:
            prompt_lines.append(raw_line)
            continue

        match = re.match(r"^([A-Za-z0-9_]+)=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2)
            continue

        if re.match(r"^<(Picture|Video|Audio) \d+>=", line):
            reference_mapping.append(line)

    return values, clean_prompt(prompt_lines), reference_mapping


def clean_prompt(lines: list[str]) -> str:
    """Return the prompt body without TXT decoration or leading blank lines."""
    cleaned = [line.rstrip() for line in lines]
    while cleaned and (not cleaned[0].strip() or re.fullmatch(r"=+", cleaned[0].strip())):
        cleaned.pop(0)
    while cleaned and (not cleaned[-1].strip() or re.fullmatch(r"=+", cleaned[-1].strip())):
        cleaned.pop()
    return "\n".join(cleaned).strip()


def metadata_kind(text: str) -> str:
    header = text[:600]
    if "VOSR UPSCALE INFO" in header:
        return "VOSR2"
    if "MiniMax H3" in header:
        return "H3"
    return "Metadata"


def first_value(values: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if value not in (None, ""):
            return value
    return None


def parse_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def parse_frame_rate(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            return float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError):
            return None
    return parse_float(value)


def probe_media(video_path: Path) -> dict[str, Any]:
    try:
        stat = video_path.stat()
        cache_key = str(video_path.resolve())
        cached = MEDIA_PROBE_CACHE.get(cache_key)
        if cached and cached[:2] == (stat.st_mtime_ns, stat.st_size):
            return dict(cached[2])
    except OSError:
        stat = None
        cache_key = ""

    result: dict[str, Any] = {
        "duration": None,
        "width": None,
        "height": None,
        "fps": None,
        "video_codec": None,
        "audio_codec": None,
        "has_audio": None,
    }
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            return result
        payload = json.loads(completed.stdout)
    except (FileNotFoundError, OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return result

    streams = payload.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    format_data = payload.get("format", {})

    result["duration"] = parse_float(format_data.get("duration"))
    if video_stream:
        result["width"] = video_stream.get("width")
        result["height"] = video_stream.get("height")
        result["fps"] = parse_frame_rate(video_stream.get("r_frame_rate"))
        result["video_codec"] = video_stream.get("codec_name")
    if audio_stream:
        result["audio_codec"] = audio_stream.get("codec_name")
        result["has_audio"] = True
    else:
        result["has_audio"] = False

    if cache_key and stat:
        MEDIA_PROBE_CACHE[cache_key] = (stat.st_mtime_ns, stat.st_size, result)
    return result


def metadata_summary(
    kind: str,
    values: dict[str, str],
    prompt: str,
    media: dict[str, Any],
) -> dict[str, Any]:
    if kind == "VOSR2":
        width = first_value(values, "actual_output_width", "final_width", "target_width")
        height = first_value(values, "actual_output_height", "final_height", "target_height")
        seed = first_value(values, "vosr_seed")
        mode = first_value(values, "vosr_model_bundle") or "VOSR2"
        model = first_value(values, "vosr_model_bundle")
        duration = media.get("duration")
        source = first_value(values, "source_file")
    else:
        width = first_value(values, "output_width", "generation_width", "width")
        height = first_value(values, "output_height", "generation_height", "height")
        seed = first_value(values, "seed")
        mode = first_value(values, "inference_mode")
        model = first_value(values, "diffusion")
        duration = first_value(values, "actual_duration_seconds", "requested_duration_seconds")
        source = None

    width_int = parse_int(width)
    height_int = parse_int(height)
    duration_float = parse_float(duration)
    if duration_float is None:
        duration_float = media.get("duration")

    if kind == "VOSR2":
        complete = all(
            values.get(key) not in (None, "")
            for key in ("job_id", "actual_output_width", "actual_output_height")
        )
    else:
        has_dimensions = bool(
            first_value(values, "output_width", "generation_width", "width")
            and first_value(values, "output_height", "generation_height", "height")
        )
        complete = bool(values.get("job_id")) and has_dimensions and bool(prompt)

    return {
        "kind": kind,
        "status": "complete" if complete else "partial",
        "mode": mode,
        # Keep seeds as strings: H3 seeds can exceed JavaScript's safe integer range.
        "seed": seed if seed not in (None, "") else None,
        "model": model,
        "lora": first_value(values, "lora"),
        "lora_strength": parse_float(first_value(values, "lora_strength")),
        "width": width_int,
        "height": height_int,
        "duration": duration_float,
        "fps": parse_float(first_value(values, "fps")) or media.get("fps"),
        "frames": parse_int(first_value(values, "frames")),
        "source_file": source,
        "source_width": parse_int(first_value(values, "source_width")),
        "source_height": parse_int(first_value(values, "source_height")),
        "target_width": parse_int(first_value(values, "target_width")),
        "target_height": parse_int(first_value(values, "target_height")),
        "fit_side": first_value(values, "fit_side"),
        "prompt_available": bool(prompt),
    }


def build_item(source: dict[str, Any], video_path: Path, info_path: Path) -> dict[str, Any]:
    info_text = info_path.read_text(encoding="utf-8", errors="replace")
    values, prompt, reference_mapping = parse_key_values(info_text)
    kind = metadata_kind(info_text)
    media = probe_media(video_path)
    relative_video = video_path.resolve().relative_to(Path(source["path"]).resolve()).as_posix()
    relative_info = info_path.resolve().relative_to(Path(source["path"]).resolve()).as_posix()
    relative_directory = Path(relative_video).parent.as_posix()
    folder = source["label"] if relative_directory == "." else source["label"] + "/" + relative_directory
    stat = video_path.stat()
    item_id = source["id"] + "::" + relative_video

    return {
        "id": item_id,
        "path": relative_video,
        "info_path": relative_info,
        "filename": video_path.name,
        "folder": folder,
        "group": source["label"],
        "source_id": source["id"],
        "source_label": source["label"],
        "modified": stat.st_mtime,
        "modified_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "size_bytes": stat.st_size,
        "video_url": "/media?id=" + quote(item_id, safe=""),
        "metadata": metadata_summary(kind, values, prompt, media),
        "media": media,
        "metadata_kind": kind,
        "metadata_fields": values,
        "reference_mapping": reference_mapping,
        "prompt": prompt,
        "raw_text": info_text,
        "_video_path": video_path,
        "_info_path": info_path,
    }


def scan_library(sources: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    unpaired_videos = 0

    for source in sources:
        source_path = Path(source["path"])
        if not source_path.is_dir():
            continue
        for video_path in sorted(source_path.rglob("*")):
            if not video_path.is_file() or video_path.suffix.lower() != VIDEO_SUFFIX:
                continue
            info_path = find_matching_info(video_path)
            if info_path is None:
                unpaired_videos += 1
                continue
            try:
                items.append(build_item(source, video_path, info_path))
            except (OSError, UnicodeError, ValueError):
                continue

    items.sort(key=lambda item: item["modified"], reverse=True)
    return {
        "sources": sources,
        "folders": sorted({item["group"] for item in items}),
        "items": items,
        "stats": {
            "paired": len(items),
            "unpaired_videos": unpaired_videos,
        },
    }


def public_item(item: dict[str, Any], include_detail: bool = False) -> dict[str, Any]:
    excluded = {"_video_path", "_info_path"}
    if not include_detail:
        excluded.update({"metadata_fields", "reference_mapping", "prompt", "raw_text"})
    return {key: value for key, value in item.items() if key not in excluded}


def json_response(handler: BaseHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def error_response(handler: BaseHTTPRequestHandler, message: str, status: int) -> None:
    json_response(handler, {"error": message}, status)


def create_handler(
    cli_sources: list[dict[str, Any]],
    config_path: Path,
):
    class VideoViewerHandler(BaseHTTPRequestHandler):
        server_version = "H3VideoViewer/2.0"

        def log_message(self, format: str, *args: Any) -> None:
            print("%s - %s" % (self.address_string(), format % args))

        def active_sources(self) -> list[dict[str, Any]]:
            return merge_sources(cli_sources, load_config(config_path))

        def current_library(self) -> dict[str, Any]:
            return scan_library(self.active_sources())

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/api/library":
                library = self.current_library()
                library["items"] = [public_item(item) for item in library["items"]]
                json_response(self, library)
                return
            if parsed.path == "/api/item":
                self.handle_item(query.get("id", [None])[0])
                return
            if parsed.path == "/api/sources":
                json_response(self, {"sources": self.active_sources()})
                return
            if parsed.path == "/media":
                self.handle_media(query.get("id", [None])[0])
                return
            if parsed.path == "/":
                self.serve_viewer_file(VIEWER_DIR / "index.html")
                return
            if parsed.path.startswith("/assets/"):
                asset_name = unquote(parsed.path[len("/assets/") :])
                if "/" in asset_name or "\\" in asset_name or asset_name in ("", ".", ".."):
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self.serve_viewer_file(VIEWER_DIR / asset_name)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/sources":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                path = Path(str(payload.get("path", "")).strip()).expanduser().resolve()
                if not path.is_dir():
                    error_response(self, "資料夾不存在或不是資料夾。", HTTPStatus.BAD_REQUEST)
                    return
                label = str(payload.get("label", "")).strip() or path.name
                configured = load_config(config_path)
                merged = merge_sources(configured, [make_source(path, label, True)])
                save_config(config_path, merged)
                source = next(item for item in merged if item["id"] == source_id(path))
                json_response(self, {"ok": True, "source": source, "sources": merged})
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
                error_response(self, "無法加入資料夾：" + str(exc), HTTPStatus.BAD_REQUEST)

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/sources":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            requested_id = parse_qs(parsed.query).get("id", [None])[0]
            configured = load_config(config_path)
            remaining = [source for source in configured if source["id"] != requested_id]
            if len(remaining) == len(configured):
                error_response(self, "找不到指定資料夾。", HTTPStatus.NOT_FOUND)
                return
            save_config(config_path, remaining)
            json_response(self, {"ok": True, "sources": self.active_sources()})

        def serve_viewer_file(self, file_path: Path) -> None:
            try:
                file_path = file_path.resolve()
                file_path.relative_to(VIEWER_DIR.resolve())
                body = file_path.read_bytes()
            except (OSError, ValueError):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            json_or_text = content_type.startswith("text/") or content_type == "application/javascript"
            if json_or_text:
                content_type += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def handle_item(self, requested_id: str | None) -> None:
            if not requested_id:
                error_response(self, "缺少影片 id。", HTTPStatus.BAD_REQUEST)
                return
            item = next(
                (candidate for candidate in self.current_library()["items"] if candidate["id"] == requested_id),
                None,
            )
            if item is None:
                error_response(self, "找不到已配對的影片。", HTTPStatus.NOT_FOUND)
                return
            json_response(self, public_item(item, include_detail=True))

        def handle_media(self, requested_id: str | None, head_only: bool = False) -> None:
            if not requested_id:
                self.send_error(HTTPStatus.BAD_REQUEST, "Missing video id")
                return
            item = next(
                (candidate for candidate in self.current_library()["items"] if candidate["id"] == requested_id),
                None,
            )
            if item is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            video_path = item["_video_path"]
            file_size = video_path.stat().st_size
            start = 0
            end = file_size - 1
            status = HTTPStatus.OK
            range_header = self.headers.get("Range")
            if range_header:
                match = re.match(r"bytes=(\d*)-(\d*)", range_header)
                if not match:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                start_text, end_text = match.groups()
                if start_text:
                    start = int(start_text)
                    if end_text:
                        end = int(end_text)
                elif end_text:
                    start = max(file_size - int(end_text), 0)
                if start >= file_size or start > end:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                end = min(end, file_size - 1)
                status = HTTPStatus.PARTIAL_CONTENT

            content_length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(content_length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.end_headers()
            if head_only:
                return

            try:
                with video_path.open("rb") as stream:
                    stream.seek(start)
                    remaining = content_length
                    while remaining:
                        chunk = stream.read(min(1024 * 64, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

        def do_HEAD(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/media":
                self.handle_media(parse_qs(parsed.query).get("id", [None])[0], head_only=True)
                return
            self.send_error(HTTPStatus.NOT_FOUND)

    return VideoViewerHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local paired MP4 + TXT video viewer")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Temporary source folder for this run. Repeat for multiple folders.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Testing shortcut: scan root\\影片 and root\\用餐 for this run.",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    if not VIEWER_DIR.is_dir():
        raise SystemExit(f"Viewer assets are missing: {VIEWER_DIR}")

    cli_sources = [make_source(Path(path), persistent=False) for path in args.source]
    if args.root:
        root = args.root.expanduser().resolve()
        legacy_sources = [
            make_source(root / folder)
            for folder in MEDIA_FOLDER_NAMES
            if (root / folder).is_dir()
        ]
        cli_sources = merge_sources(cli_sources, legacy_sources)

    config_path = args.config.expanduser().resolve()
    server = ThreadingHTTPServer(
        (args.host, args.port),
        create_handler(cli_sources, config_path),
    )
    print("H3 Video Archive server")
    print(f"Config: {config_path}")
    print(f"Temporary sources: {len(cli_sources)}")
    print(f"Open http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping viewer.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
