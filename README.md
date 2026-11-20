# Mp3 Duplicate Finder

Windows desktop application for finding identical MP3 audio and likely re-encoded copies using Chromaprint fingerprints.

## Build

The GitHub Actions workflow builds a Windows x64 one-file executable and publishes it as a downloadable workflow artifact. It obtains FFmpeg and Chromaprint from their upstream distribution channels during the build; these tools are not bundled into this source archive.

## Attribution

Project concept and application source: **Konrad Astachow (Kondar)**, as declared by the author.

## Third-party components

- FFmpeg: https://ffmpeg.org/ — see the license and notices distributed with the selected Windows build.
- Chromaprint / fpcalc: https://github.com/acoustid/chromaprint — LGPL-2.1-or-later.

This repository does not grant an additional license to the project source code. No open-source license is provided.
