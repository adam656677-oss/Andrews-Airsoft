# Last Contract trailer

`Last_Contract_Trailer.mp4`: 88.5 s, 1920×1080 at 30 fps, H.264 + AAC, -14 LUFS integrated, about 45 MB.

It is built without any rendering: slow camera moves over the existing 4K stills, hard cuts on gunshots,
title cards in the neon-noir style, the story's Kokoro voice lines over the game's own music (ducked under the voices).
`frames/` holds six check frames.

Rebuild from the repo root (needs ffmpeg, Pillow and NumPy; about 8 minutes on 3 cores):

    python3 Docs/Trailer/build_trailer.py

Shot list, voice lines and timings are the `SHOTS`, `MONTAGE` and `VO` tables at the top of the script.
