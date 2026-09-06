# YOINK

YOINK is a calm, desktop media downloader powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp). It supports any site supported by yt-dlp, subject to that site's rules and your rights to download the media.

## Features

- Batch URLs, one per line
- TV-compatible H.264/AAC format preset up to 1080p
- Best available, 720p, 480p, and m4a audio presets
- Cookies file support
- Section clipping with start/end timestamps
- Progress, speed, ETA, cancellation, and resume through yt-dlp partial files
- Muted forest green default theme, plus light forest and slate variants

## Run from the repository

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe main.py
```

The first launch creates settings under the operating system's application config directory. The output folder defaults to `Downloads/Yoink`. FFmpeg is supplied by `imageio-ffmpeg`; `yt-dlp[default]` supplies the EJS package used for YouTube JavaScript challenges. Deno can be installed separately if a site requires a JavaScript runtime.

## Themes

Themes are JSON files in `yoink/themes/`. Copy an existing theme, change its color values, and select it from the theme menu. The required semantic roles are documented by the existing theme files.

## Legal and privacy note

Only download media you are authorized to download. Cookies are read locally and are never uploaded by YOINK; treat a cookies file as sensitive and do not commit it.
