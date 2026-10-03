#!/usr/bin/env python3
"""Windows-native client for the MiniMax H3 Colab Remote API v1.3."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests


SAFE_PREFIX_RE = re.compile(
    r"[^A-Za-z0-9._-]+"
)

SIZE_RE = re.compile(
    r"^(\d+)[xX×](\d+)$"
)

SEED_RE = re.compile(
    r"^seed=(\d+)\s*$",
    re.MULTILINE,
)


def api_settings() -> tuple[str, str]:
    url = (
        os.environ
        .get(
            "H3_API_URL",
            "",
        )
        .strip()
        .rstrip("/")
    )

    token = (
        os.environ
        .get(
            "H3_API_TOKEN",
            "",
        )
        .strip()
    )

    if not url:
        raise RuntimeError(
            "H3_API_URL is not set. "
            "Run Cell 10 in Colab and copy "
            "the PowerShell command it prints."
        )

    if not token:
        raise RuntimeError(
            "H3_API_TOKEN is not set. "
            "Run Cell 10 in Colab and copy "
            "the PowerShell command it prints."
        )

    return (
        url,
        token,
    )


def headers() -> dict[str, str]:
    _, token = (
        api_settings()
    )

    return {
        "Authorization":
            f"Bearer {token}"
    }


def get_json(
    path: str,
    timeout: float = 30,
) -> dict:
    url, _ = (
        api_settings()
    )

    r = requests.get(
        url + path,
        headers=headers(),
        timeout=timeout,
    )

    r.raise_for_status()

    return r.json()


def parse_size(
    value: str,
) -> tuple[int, int]:
    match = SIZE_RE.fullmatch(
        str(
            value
        ).strip()
    )

    if not match:
        raise argparse.ArgumentTypeError(
            "Size must look like 1920x1080."
        )

    width, height = map(
        int,
        match.groups(),
    )

    if (
        width <= 0
        or height <= 0
    ):
        raise argparse.ArgumentTypeError(
            "Width/height must be positive."
        )

    return (
        width,
        height,
    )


def safe_prefix(
    value: str | None,
    fallback: str = "minimax_h3",
) -> str:
    text = SAFE_PREFIX_RE.sub(
        "_",
        str(
            value
            or ""
        ),
    ).strip(
        "._-"
    )

    return (
        text[:80]
        or fallback
    )


def verify_mp4(
    path: Path,
) -> None:
    if (
        not path.is_file()
        or path.stat().st_size <= 0
    ):
        raise RuntimeError(
            "Downloaded MP4 is missing "
            f"or empty: {path}"
        )

    ffprobe = shutil.which(
        "ffprobe"
    )

    if not ffprobe:
        return

    p = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(
                path
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    if (
        p.returncode
        != 0
    ):
        raise RuntimeError(
            "ffprobe could not read output: "
            f"{p.stderr.strip()}"
        )

    streams = {
        x.get(
            "codec_type"
        )
        for x
        in json.loads(
            p.stdout
        ).get(
            "streams",
            [],
        )
    }

    if (
        "video"
        not in streams
    ):
        raise RuntimeError(
            "Output must contain a video stream; "
            f"found {sorted(streams)}"
        )


def download_file(
    url: str,
    path: Path,
    *,
    timeout: float = 1800,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = path.with_name(
        path.name
        + ".part"
    )

    with requests.get(
        url,
        headers=headers(),
        stream=True,
        timeout=timeout,
    ) as r:

        r.raise_for_status()

        with temp.open(
            "wb"
        ) as f:

            for chunk in r.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    f.write(
                        chunk
                    )

    if (
        not temp.is_file()
        or temp.stat().st_size <= 0
    ):
        raise RuntimeError(
            "Downloaded file is missing "
            f"or empty: {temp}"
        )

    temp.replace(
        path
    )


def verify_txt(
    path: Path,
) -> None:
    if (
        not path.is_file()
        or path.stat().st_size <= 0
    ):
        raise RuntimeError(
            "Downloaded TXT is missing "
            f"or empty: {path}"
        )

    try:
        text = path.read_text(
            encoding="utf-8"
        )

    except UnicodeDecodeError as exc:
        raise RuntimeError(
            "Downloaded TXT is not valid UTF-8: "
            f"{path}"
        ) from exc

    generation_record = (
        "PROMPT BEGIN"
        in text
        and "PROMPT END"
        in text
    )

    upscale_record = (
        "VOSR UPSCALE INFO"
        in text
    )

    if (
        not generation_record
        and not upscale_record
    ):
        raise RuntimeError(
            "Downloaded TXT does not look "
            f"like an H3/VOSR record: {path}"
        )


def seed_from_adjacent_txt(
    video: Path,
) -> int | None:
    txt = video.with_suffix(
        ".txt"
    )

    if not txt.is_file():
        return None

    try:
        match = SEED_RE.search(
            txt.read_text(
                encoding="utf-8",
                errors="replace",
            )
        )

        return (
            int(
                match.group(
                    1
                )
            )
            if match
            else None
        )

    except Exception:
        return None


def wait_for_job(
    job_id: str,
    timeout: float,
    poll: float,
    json_mode: bool,
) -> dict:
    last_status = None

    deadline = (
        time.monotonic()
        + timeout
        + 300
    )

    while (
        time.monotonic()
        < deadline
    ):
        status = get_json(
            f"/jobs/{job_id}",
            timeout=30,
        )

        current = status.get(
            "status"
        )

        if (
            current
            != last_status
            and not json_mode
        ):
            print(
                f"[{job_id[:12]}] {current}",
                file=sys.stderr,
            )

            last_status = (
                current
            )

        if (
            current
            == "completed"
        ):
            return status

        if (
            current
            == "failed"
        ):
            raise RuntimeError(
                status.get(
                    "error"
                )
                or "Remote job failed"
            )

        time.sleep(
            poll
        )

    raise TimeoutError(
        "Timed out waiting for job "
        f"{job_id}"
    )


def choose_output_paths(
    *,
    explicit_output: str | None,
    explicit_info: str | None,
    output_dir: str | None,
    prefix: str | None,
    fallback_dir: Path,
    fallback_prefix: str,
    stamp: str,
    seed: int,
    size_suffix: tuple[int, int] | None,
) -> tuple[Path, Path]:
    if explicit_output:

        output = Path(
            explicit_output
        ).expanduser().resolve()

    else:

        directory = (
            Path(
                output_dir
            ).expanduser().resolve()
            if output_dir
            else fallback_dir.resolve()
        )

        name = (
            f"{safe_prefix(prefix, fallback_prefix)}_"
            f"{stamp}_"
            f"seed{seed}"
        )

        if size_suffix:
            name += (
                f"_"
                f"{size_suffix[0]}"
                f"x"
                f"{size_suffix[1]}"
            )

        output = (
            directory
            / f"{name}.mp4"
        )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    info = (
        Path(
            explicit_info
        ).expanduser().resolve()
        if explicit_info
        else output.with_suffix(
            ".txt"
        )
    )

    info.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        output,
        info,
    )


def _apply_optional(
    data: dict[str, str],
    values: dict[str, object],
) -> None:
    for (
        key,
        value,
    ) in values.items():

        if (
            value is not None
            and value != ""
        ):
            data[
                key
            ] = str(
                value
            )


def run_generate(
    args: argparse.Namespace,
) -> int:
    url, _ = (
        api_settings()
    )

    images = [
        Path(
            x
        ).expanduser().resolve()
        for x
        in args.image
    ]

    videos = [
        Path(
            x
        ).expanduser().resolve()
        for x
        in args.video
    ]

    audios = [
        Path(
            x
        ).expanduser().resolve()
        for x
        in args.audio
    ]

    for (
        label,
        paths,
    ) in [
        (
            "Image",
            images,
        ),
        (
            "Video",
            videos,
        ),
        (
            "Audio",
            audios,
        ),
    ]:
        for path in paths:

            if (
                not path.is_file()
                or path.stat().st_size <= 0
            ):
                raise FileNotFoundError(
                    f"{label} is missing "
                    f"or empty: {path}"
                )

    if (
        len(
            images
        )
        > 9
    ):
        raise ValueError(
            "Ref2V accepts at most "
            "9 --image references."
        )

    if (
        len(
            videos
        )
        > 3
    ):
        raise ValueError(
            "Ref2V accepts at most "
            "3 --video references."
        )

    if (
        len(
            audios
        )
        > 3
    ):
        raise ValueError(
            "Ref2V accepts at most "
            "3 --audio references."
        )

    if args.prompt_file:

        prompt = Path(
            args.prompt_file
        ).expanduser().resolve().read_text(
            encoding="utf-8"
        )

    else:
        prompt = (
            args.prompt
            or ""
        )

    if not prompt.strip():
        raise ValueError(
            "A non-empty --prompt or "
            "--prompt-file is required."
        )

    stamp = time.strftime(
        "%Y%m%d-%H%M%S"
    )

    data: dict[str, str] = {
        "prompt":
            prompt,

        "mode":
            args.mode,

        "duration_seconds":
            str(
                args.duration
            ),

        "model":
            (
                args.model
                or os.environ.get(
                    "H3_MODEL",
                    "__CURRENT__",
                )
            ),

        "lora":
            (
                "NONE"
                if args.no_lora
                else (
                    args.lora
                    or os.environ.get(
                        "H3_LORA",
                        "__CURRENT__",
                    )
                )
            ),

        "timeout_seconds":
            str(
                args.timeout
            ),
    }

    _apply_optional(
        data,
        {
            "width":
                args.width,

            "height":
                args.height,

            "seed":
                args.seed,

            "steps":
                args.steps,

            "sampler":
                args.sampler,

            "scheduler":
                args.scheduler,

            "lora_strength":
                args.lora_strength,

            "ref_image_size":
                args.ref_image_size,
        },
    )

    if (
        args.fast_vsa
        is not None
    ):
        data[
            "fast_use_vsa"
        ] = (
            "true"
            if args.fast_vsa
            else "false"
        )

    if args.no_upscale:

        data[
            "upscale_mode"
        ] = "none"

    elif args.upscale_to:

        (
            target_w,
            target_h,
        ) = args.upscale_to

        data[
            "upscale_mode"
        ] = "inline"

        data[
            "target_width"
        ] = str(
            target_w
        )

        data[
            "target_height"
        ] = str(
            target_h
        )

        if (
            args.fit_side
            is not None
        ):
            data[
                "fit_side"
            ] = (
                args.fit_side
            )

    else:

        data[
            "upscale_mode"
        ] = "current"

    _apply_optional(
        data,
        {
            "vosr_dtype":
                args.vosr_dtype,

            "vosr_seed":
                args.vosr_seed,

            "vosr_color_alignment":
                args.vosr_color,

            "vosr_tile_size":
                args.vosr_tile_size,

            "vosr_tile_overlap":
                args.vosr_tile_overlap,

            "vosr_vae_tile_size":
                args.vosr_vae_tile_size,

            "vosr_vae_tile_overlap":
                args.vosr_vae_tile_overlap,
        },
    )

    opened = []
    files = []

    try:

        for (
            field_name,
            paths,
        ) in [
            (
                "images",
                images,
            ),
            (
                "videos",
                videos,
            ),
            (
                "audios",
                audios,
            ),
        ]:
            for path in paths:

                f = path.open(
                    "rb"
                )

                opened.append(
                    f
                )

                mime = (
                    mimetypes.guess_type(
                        path.name
                    )[0]
                    or "application/octet-stream"
                )

                files.append(
                    (
                        field_name,
                        (
                            path.name,
                            f,
                            mime,
                        ),
                    )
                )

        r = requests.post(
            url
            + "/generate",
            headers=headers(),
            data=data,
            files=(
                files
                or None
            ),
            timeout=600,
        )

        if not r.ok:
            raise RuntimeError(
                "Generate request failed "
                f"HTTP {r.status_code}: "
                f"{r.text}"
            )

        job = r.json()

    finally:

        for f in opened:
            f.close()

    job_id = job[
        "job_id"
    ]

    status = wait_for_job(
        job_id,
        args.timeout,
        args.poll,
        args.json,
    )

    seed = int(
        status.get(
            "seed",
            job.get(
                "seed"
            ),
        )
    )

    final_w = int(
        status.get(
            "output_width"
        )
        or status.get(
            "final_width"
        )
        or 0
    )

    final_h = int(
        status.get(
            "output_height"
        )
        or status.get(
            "final_height"
        )
        or 0
    )

    inline = (
        status.get(
            "upscale_mode",
            job.get(
                "upscale_mode"
            ),
        )
        == "inline"
    )

    size_suffix = (
        (
            final_w,
            final_h,
        )
        if (
            inline
            and final_w > 0
            and final_h > 0
        )
        else None
    )

    first_reference = next(
        iter(
            images
            + videos
            + audios
        ),
        None,
    )

    fallback_dir = (
        first_reference.parent
        if first_reference
        else Path.cwd()
    )

    fallback_prefix = (
        first_reference.stem
        if first_reference
        else "minimax_h3"
    )

    (
        output,
        info_output,
    ) = choose_output_paths(
        explicit_output=args.output,
        explicit_info=args.info_output,
        output_dir=args.output_dir,
        prefix=args.prefix,
        fallback_dir=fallback_dir,
        fallback_prefix=fallback_prefix,
        stamp=stamp,
        seed=seed,
        size_suffix=size_suffix,
    )

    download_file(
        url
        + f"/result/{job_id}",
        output,
    )

    verify_mp4(
        output
    )

    download_file(
        url
        + f"/info/{job_id}",
        info_output,
        timeout=300,
    )

    verify_txt(
        info_output
    )

    result = {
        "ok":
            True,

        "job_id":
            job_id,

        "output":
            str(
                output
            ),

        "info":
            str(
                info_output
            ),

        "seed":
            seed,

        "output_width":
            (
                final_w
                or None
            ),

        "output_height":
            (
                final_h
                or None
            ),

        "bytes":
            output.stat().st_size,

        "info_bytes":
            info_output.stat().st_size,
    }

    if args.json:

        print(
            json.dumps(
                result,
                ensure_ascii=False,
            )
        )

    else:

        print(
            f"Saved video: {output}"
        )

        print(
            f"Saved info : {info_output}"
        )

    return 0


def run_upscale(
    args: argparse.Namespace,
) -> int:
    url, _ = (
        api_settings()
    )

    video = Path(
        args.video
    ).expanduser().resolve()

    if (
        not video.is_file()
        or video.stat().st_size <= 0
    ):
        raise FileNotFoundError(
            "Video is missing "
            f"or empty: {video}"
        )

    (
        target_w,
        target_h,
    ) = args.target

    stamp = time.strftime(
        "%Y%m%d-%H%M%S"
    )

    data = {
        "target_width":
            str(
                target_w
            ),

        "target_height":
            str(
                target_h
            ),

        "fit_side":
            args.fit_side,

        "vosr_dtype":
            args.vosr_dtype,

        "vosr_seed":
            str(
                args.vosr_seed
            ),

        "vosr_color_alignment":
            args.vosr_color,

        "vosr_tile_size":
            str(
                args.vosr_tile_size
            ),

        "vosr_tile_overlap":
            str(
                args.vosr_tile_overlap
            ),

        "vosr_vae_tile_size":
            str(
                args.vosr_vae_tile_size
            ),

        "vosr_vae_tile_overlap":
            str(
                args.vosr_vae_tile_overlap
            ),

        "timeout_seconds":
            str(
                args.timeout
            ),
    }

    mime = (
        mimetypes.guess_type(
            video.name
        )[0]
        or "application/octet-stream"
    )

    with video.open(
        "rb"
    ) as f:

        r = requests.post(
            url
            + "/upscale",
            headers=headers(),
            data=data,
            files={
                "video":
                    (
                        video.name,
                        f,
                        mime,
                    )
            },
            timeout=1800,
        )

    if not r.ok:
        raise RuntimeError(
            "Upscale request failed "
            f"HTTP {r.status_code}: "
            f"{r.text}"
        )

    job = r.json()

    job_id = job[
        "job_id"
    ]

    status = wait_for_job(
        job_id,
        args.timeout,
        args.poll,
        args.json,
    )

    original_seed = (
        seed_from_adjacent_txt(
            video
        )
    )

    name_seed = (
        original_seed
        if original_seed
        is not None
        else int(
            status.get(
                "vosr_seed",
                job.get(
                    "seed",
                    args.vosr_seed,
                ),
            )
        )
    )

    final_w = int(
        status.get(
            "output_width"
        )
        or status.get(
            "final_width"
        )
        or job.get(
            "final_width"
        )
        or target_w
    )

    final_h = int(
        status.get(
            "output_height"
        )
        or status.get(
            "final_height"
        )
        or job.get(
            "final_height"
        )
        or target_h
    )

    (
        output,
        info_output,
    ) = choose_output_paths(
        explicit_output=args.output,
        explicit_info=args.info_output,
        output_dir=args.output_dir,
        prefix=args.prefix,
        fallback_dir=video.parent,
        fallback_prefix=video.stem,
        stamp=stamp,
        seed=name_seed,
        size_suffix=(
            final_w,
            final_h,
        ),
    )

    download_file(
        url
        + f"/result/{job_id}",
        output,
    )

    verify_mp4(
        output
    )

    download_file(
        url
        + f"/info/{job_id}",
        info_output,
        timeout=300,
    )

    verify_txt(
        info_output
    )

    result = {
        "ok":
            True,

        "job_id":
            job_id,

        "output":
            str(
                output
            ),

        "info":
            str(
                info_output
            ),

        "name_seed":
            name_seed,

        "vosr_seed":
            status.get(
                "vosr_seed",
                job.get(
                    "seed"
                ),
            ),

        "output_width":
            final_w,

        "output_height":
            final_h,

        "bytes":
            output.stat().st_size,

        "info_bytes":
            info_output.stat().st_size,
    }

    if args.json:

        print(
            json.dumps(
                result,
                ensure_ascii=False,
            )
        )

    else:

        print(
            f"Saved video: {output}"
        )

        print(
            f"Saved info : {info_output}"
        )

    return 0


def add_vosr_options(
    parser: argparse.ArgumentParser,
    *,
    inherit_current: bool = False,
) -> None:
    # generate:
    # None = 沿用 Cell 2 的 VOSR 設定。
    #
    # upscale:
    # 沒有 H3 generation 設定可繼承，
    # 所以直接使用這裡的實用預設值。

    default = (
        lambda value:
            None
            if inherit_current
            else value
    )

    parser.add_argument(
        "--fit-side",
        choices=[
            "long",
            "short",
        ],
        default=default(
            "long"
        ),
        help=(
            "Keep aspect ratio; "
            "make the long or short side "
            "hit the requested target value"
        ),
    )

    parser.add_argument(
        "--vosr-dtype",
        choices=[
            "default",
            "fp16",
            "bf16",
        ],
        default=default(
            "bf16"
        ),
    )

    parser.add_argument(
        "--vosr-seed",
        type=int,
        default=default(
            42
        ),
    )

    parser.add_argument(
        "--vosr-color",
        choices=[
            "wavelet",
            "adain",
            "none",
        ],
        default=default(
            "wavelet"
        ),
    )

    parser.add_argument(
        "--vosr-tile-size",
        type=int,
        default=default(
            512
        ),
    )

    parser.add_argument(
        "--vosr-tile-overlap",
        type=int,
        default=default(
            64
        ),
    )

    parser.add_argument(
        "--vosr-vae-tile-size",
        type=int,
        default=default(
            1024
        ),
    )

    parser.add_argument(
        "--vosr-vae-tile-overlap",
        type=int,
        default=default(
            128
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "MiniMax H3 Colab "
            "Remote API client v1.3"
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    health = sub.add_parser(
        "health",
        help=(
            "Check the Colab H3 API"
        ),
    )

    health.add_argument(
        "--json",
        action="store_true",
    )

    models = sub.add_parser(
        "models",
        help=(
            "List installed/official "
            "diffusion models and LoRAs"
        ),
    )

    models.add_argument(
        "--json",
        action="store_true",
    )

    gen = sub.add_parser(
        "generate",
        help=(
            "Generate H3 video and "
            "download MP4 + TXT"
        ),
    )

    gen.add_argument(
        "--image",
        "-i",
        action="append",
        default=[],
        help=(
            "Picture reference. "
            "Ref2V: repeat for "
            "<Picture 1>...<Picture 9>. "
            "I2V: image 1 is first frame "
            "and image 2 is optional last frame."
        ),
    )

    gen.add_argument(
        "--video",
        action="append",
        default=[],
        help=(
            "Ref2V video reference; "
            "repeat for <Video 1>...<Video 3>. "
            "This is different from the "
            "upscale subcommand's --video input."
        ),
    )

    gen.add_argument(
        "--audio",
        action="append",
        default=[],
        help=(
            "Ref2V audio reference; "
            "repeat for <Audio 1>...<Audio 3>."
        ),
    )

    prompt_group = (
        gen.add_mutually_exclusive_group(
            required=True
        )
    )

    prompt_group.add_argument(
        "--prompt-file",
        "-p",
    )

    prompt_group.add_argument(
        "--prompt",
    )

    gen.add_argument(
        "--output",
        "-o",
        help=(
            "Exact MP4 path "
            "(backward compatibility). "
            "Prefer --output-dir + --prefix "
            "for automatic naming."
        ),
    )

    gen.add_argument(
        "--info-output",
        help=(
            "Exact TXT path; "
            "default follows the MP4 basename"
        ),
    )

    gen.add_argument(
        "--output-dir",
        help=(
            "Directory for automatic "
            "PREFIX_DATETIME_SEED naming"
        ),
    )

    gen.add_argument(
        "--prefix",
        help=(
            "Filename prefix "
            "for automatic naming"
        ),
    )

    gen.add_argument(
        "--mode",
        default="current",
        choices=[
            "current",
            "ref2v_native",
            "i2v_native",
            "t2v_native",
            "fast_i2v",
            "fast_t2v",
        ],
    )

    gen.add_argument(
        "--duration",
        type=float,
        default=10.0,
    )

    gen.add_argument(
        "--width",
        type=int,
    )

    gen.add_argument(
        "--height",
        type=int,
    )

    gen.add_argument(
        "--seed",
    )

    gen.add_argument(
        "--steps",
        type=int,
    )

    gen.add_argument(
        "--sampler",
        help=(
            "Examples: res_multistep, "
            "euler, er_sde; "
            "any server-supported value "
            "may be entered"
        ),
    )

    gen.add_argument(
        "--scheduler",
        help=(
            "Examples: simple, beta, normal; "
            "any server-supported value "
            "may be entered"
        ),
    )

    gen.add_argument(
        "--model",
        help=(
            "Installed diffusion model filename; "
            "mode/conditioning is independent "
            "from the checkpoint"
        ),
    )

    gen.add_argument(
        "--lora",
        help=(
            "Installed LoRA filename"
        ),
    )

    gen.add_argument(
        "--no-lora",
        action="store_true",
    )

    gen.add_argument(
        "--lora-strength",
        type=float,
    )

    gen.add_argument(
        "--ref-image-size",
        choices=[
            "match",
            "max",
        ],
    )

    vsa = (
        gen.add_mutually_exclusive_group()
    )

    vsa.add_argument(
        "--fast-vsa",
        dest="fast_vsa",
        action="store_true",
    )

    vsa.add_argument(
        "--no-fast-vsa",
        dest="fast_vsa",
        action="store_false",
    )

    gen.set_defaults(
        fast_vsa=None
    )

    upscale_group = (
        gen.add_mutually_exclusive_group()
    )

    upscale_group.add_argument(
        "--upscale-to",
        type=parse_size,
        metavar="WxH",
        help=(
            "Inline VOSR2 target, "
            "e.g. 1920x1080"
        ),
    )

    upscale_group.add_argument(
        "--no-upscale",
        action="store_true",
        help=(
            "Force original H3 resolution "
            "even if Cell 2 currently has "
            "inline VOSR enabled"
        ),
    )

    add_vosr_options(
        gen,
        inherit_current=True,
    )

    gen.add_argument(
        "--timeout",
        type=float,
        default=10800.0,
    )

    gen.add_argument(
        "--poll",
        type=float,
        default=8.0,
    )

    gen.add_argument(
        "--json",
        action="store_true",
    )

    up = sub.add_parser(
        "upscale",
        help=(
            "Upscale an existing local video "
            "with VOSR2 without rerunning H3"
        ),
    )

    up.add_argument(
        "--video",
        required=True,
    )

    up.add_argument(
        "--target",
        type=parse_size,
        default=parse_size(
            "1920x1080"
        ),
        metavar="WxH",
    )

    up.add_argument(
        "--output",
        "-o",
        help=(
            "Exact MP4 path. "
            "Prefer --output-dir + --prefix."
        ),
    )

    up.add_argument(
        "--info-output",
        help=(
            "Exact TXT path"
        ),
    )

    up.add_argument(
        "--output-dir",
    )

    up.add_argument(
        "--prefix",
    )

    add_vosr_options(
        up
    )

    up.add_argument(
        "--timeout",
        type=float,
        default=10800.0,
    )

    up.add_argument(
        "--poll",
        type=float,
        default=8.0,
    )

    up.add_argument(
        "--json",
        action="store_true",
    )

    args = parser.parse_args()

    if (
        args.command
        == "health"
    ):
        result = get_json(
            "/health"
        )

        print(
            (
                json.dumps(
                    result,
                    ensure_ascii=False,
                )
                if args.json
                else json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
            )
        )

        return 0

    if (
        args.command
        == "models"
    ):
        result = get_json(
            "/models"
        )

        print(
            (
                json.dumps(
                    result,
                    ensure_ascii=False,
                )
                if args.json
                else json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
            )
        )

        return 0

    if (
        args.command
        == "generate"
    ):
        return run_generate(
            args
        )

    if (
        args.command
        == "upscale"
    ):
        return run_upscale(
            args
        )

    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )

    except Exception as exc:
        print(
            f"Error: {exc}",
            file=sys.stderr,
        )

        raise SystemExit(
            1
        )