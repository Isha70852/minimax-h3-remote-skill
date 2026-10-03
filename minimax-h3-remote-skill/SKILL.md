---
name: minimax-h3-remote
description: Generate MiniMax H3 videos from local computer by sending prompts and local Picture, Video, and Audio references to the user's authenticated MiniMax H3 Colab Remote API. Also upscale existing videos with VOSR2.
---

# MiniMax H3 Remote

Use this skill's `scripts/h3_client.py` to talk to the user's running Colab notebook. Do not use `google-colab-cli`.

## Before doing real work

The Colab notebook must already be running through Cell 10, and the Windows process must have `H3_API_URL` and `H3_API_TOKEN` in its environment.

Before the first generation or upscale in a session, run:

```powershell
python scripts\h3_client.py health
```

If health fails, tell the user to rerun Cell 10 and paste the new H3_API_URL / H3_API_TOKEN PowerShell commands into the terminal that launches Codex.
Never print, store, commit, or place H3_API_TOKEN inside a prompt, TXT record, source file, manifest, or log.

## Choose the task

Use generate when the user wants a new H3 video.
Use upscale when the user already has a video and only wants VOSR2 enlargement. Do not rerun H3 just to upscale an existing clip.

## Ref2V reference rules

Ref2V accepts three independent reference groups:
- --image: 0–9 Picture references. Order maps to <Picture 1> ... <Picture 9>.
- --video: 0–3 Video references. Order maps to <Video 1> ... <Video 3>.
- --audio: 0–3 standalone Audio references. Order maps to <Audio 1> ... <Audio 3>.
At least one Picture, Video, or Audio reference is required for Ref2V.
Keep the user's file order exactly. Never reorder files to make the prompt look nicer.
A Ref2V video reference sends both the video's visual stream and its embedded audio stream through the notebook's LoadVideo -> GetVideoComponents path. A separate --audio file is a standalone <Audio N> reference.
Example mapping:
```text
--image person.png       -> <Picture 1>
--image clothes.png      -> <Picture 2>
--video motion.mp4       -> <Video 1>
--audio voice.wav        -> <Audio 1>
```

If the prompt mentions \<Picture N>, \<Video N>, or \<Audio N>, the referenced number must actually exist in the uploaded files.

For I2V, use only --image: image 1 is the first frame and image 2 is the optional last frame. Do not pass Ref2V --video or --audio references to I2V.
For T2V, do not pass Picture, Video, or Audio references.

## Prompt writing

If the user supplies a complete prompt, keep it unchanged unless they ask you to edit it.
If the user gives only a natural-language request, write the complete MiniMax H3 prompt before calling the client. Search MiniMax H3 official prompt guide before writing prompt if you are not sure what is correct format.
For Ref2V, normally include:

- subject_definitions
- summary
- retention_analysis
- detailed_description with ordered [Shot N] blocks and explicit timing
- overall_soundscape
- non_diegetic_music
Use the uploaded references explicitly where useful. For example:

```text
Use <Picture 1> as the main identity reference.
Use <Video 1> as the motion and camera-motion reference.
Use <Audio 1> as the voice/audio reference.
```

Be explicit about identity retention, clothing and props that must remain stable, camera motion, subject action, scene continuity, dialogue, sound effects, and music.
If the user requests spoken Chinese dialogue, put the dialogue in the relevant shot using <d>[Chinese] ...</d>.
Write the final prompt to a temporary UTF-8 .txt file. Do not put the API token in it.

## Mode, model, and LoRA

By default omit --mode, --model, and --lora so the API uses the current Cell 2 settings.
Supported generation modes are:
```text
ref2v_native
i2v_native
t2v_native
fast_i2v
fast_t2v
```
The conditioning mode is independent from the diffusion checkpoint. For example, the user may intentionally use an FL2VA checkpoint or FL2V LoRA while the mode is Ref2V.
If the user explicitly requests another installed model or LoRA, first run:

```powershell
python scripts\h3_client.py models
```

Then use an exact returned filename with --model or --lora. Do not invent filenames. Do not ask the Remote API to download an arbitrary URL; model preparation belongs in Colab Cell 2 -> Cell 3.
Use --no-lora when the user explicitly wants no LoRA.
Sampler and scheduler can be passed through directly. Common values are:

```text
sampler: res_multistep, euler, er_sde
scheduler: simple, beta, normal
```

Do not silently change the user's sampler, scheduler, steps, model, LoRA, prompt, or seed after a failure.

## Generate commands

Picture-only Ref2V example:

```powershell
python scripts\h3_client.py generate `
  --image "C:\AI\refs\person.png" `
  --prompt-file "C:\AI\work\prompt.txt" `
  --mode ref2v_native `
  --duration 10 `
  --output-dir "C:\AI\outputs" `
  --prefix "scene"
```

Picture + Video + Audio Ref2V example:
```powershell
python scripts\h3_client.py generate `
  --image "C:\AI\refs\person.png" `
  --video "C:\AI\refs\motion.mp4" `
  --audio "C:\AI\refs\voice.wav" `
  --prompt-file "C:\AI\work\prompt.txt" `
  --mode ref2v_native `
  --duration 10 `
  --output-dir "C:\AI\outputs" `
  --prefix "H3_Remote_Colab"
```

Multiple references may repeat the same flag:
```
--image "person-front.png" --image "person-side.png"
--video "walk.mp4" --video "camera.mp4"
--audio "voice.wav" --audio "ambience.wav"
```

## VOSR2

If the user wants a new H3 clip and also wants it enlarged, use inline VOSR2 with generate:

```powershell
python scripts\h3_client.py generate `
  --image "C:\AI\refs\person.png" `
  --prompt-file "C:\AI\work\prompt.txt" `
  --upscale-to 1920x1080 `
  --fit-side long `
  --output-dir "C:\AI\outputs" `
  --prefix "H3_Remote_Colab"
```

Inline VOSR2 keeps aspect ratio, does not crop, and does not keep a second original-resolution MP4.
If the user wants an existing local video enlarged, use:

```powershell
python scripts\h3_client.py upscale `
  --video "C:\AI\outputs\preview.mp4" `
  --target 1920x1080 `
  --fit-side long `
  --output-dir "C:\AI\outputs" `
  --prefix "H3_Remote_Colab"
```

Note the difference:
- generate --video ... means a Ref2V Video reference.
- upscale --video ... means the source video that VOSR2 should enlarge.

## Output naming

Prefer --output-dir plus --prefix instead of --output.
Normal generation is automatically saved as:

```text
PREFIX_YYYYMMDD-HHMMSS_seedSEED.mp4
PREFIX_YYYYMMDD-HHMMSS_seedSEED.txt
```

When VOSR2 is used, append the actual output size:
```text
PREFIX_YYYYMMDD-HHMMSS_seedSEED_1920x1080.mp4
PREFIX_YYYYMMDD-HHMMSS_seedSEED_1920x1080.txt
```

If the user says something like save to C:\AI\outputs\tokyo.mp4, normally interpret C:\AI\outputs as the output directory and tokyo as the prefix so the required timestamp and seed naming is preserved. Only use an exact --output path when the user clearly insists on that exact filename.
The server-side TXT is the generation record. It contains the actual mode, checkpoint, LoRA, seed, dimensions, sampling settings, Ref2V media mapping, VOSR2 settings when applicable, and the exact prompt. Do not replace it with the temporary local prompt file.

## After completion

Wait for the client to finish. It polls the job, downloads the MP4, then downloads the matching TXT.
Report both exact local paths to the user. If VOSR2 was used, also report the actual output dimensions when the client returns them.

## Failure handling

If the API returns 401 Unauthorized, the token is stale or missing. Tell the user to rerun Cell 10 and reset H3_API_URL / H3_API_TOKEN.

If the connection or tunnel fails, the Colab runtime or Quick Tunnel is no longer active. Tell the user to rerun Cell 10.

If a model or LoRA is missing, run models. If it is still absent, tell the user to prepare it in Cell 2 -> Cell 3.

If a Ref2V tag error says a Picture, Video, or Audio number does not exist, fix the prompt or the uploaded reference list; do not silently remap reference order.

If VOSR2 or VHS nodes are missing, tell the user to rerun Cell 1, restart the Colab runtime, then rerun Cell 6 and Cell 10.

If MP4 download succeeds but TXT download fails, keep the valid MP4 and report the TXT failure. Do not regenerate automatically.

Do not automatically retry a long GPU job more than once. A remote GPU task may still be running.