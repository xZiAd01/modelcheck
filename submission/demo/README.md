# Demo video

[Download the 72-second walkthrough](ModelCheck_walkthrough.mp4) · [English captions](ModelCheck_walkthrough.vtt) · [Playback page](playback.html)

The silent browser recording uses synthetic data. It shows deterministic MCP calculations, an explicitly labeled replay of the original v1 review, a manual follow-up proposal, exact human approval and the JSON download. Replay sends no model requests. The approval and download use the current application's real handlers. The downloaded specification was checked against the approved payload and the single saved file.

This recording is a presentation fallback, not a new live evaluation or evidence of v2 model performance. The current application uses v2 for new live reviews; evaluation results remain versioned separately.

| Time | Workflow |
|---|---|
| 00:00–00:18 | Sample inspection and source-level metrics |
| 00:18–00:29 | Original v1 review replay and runtime label |
| 00:29–00:36 | Limitations and unsupported-provenance correction |
| 00:36–00:44 | Manual follow-up draft |
| 00:44–00:50 | Exact specification awaiting approval |
| 00:50–01:12 | Approval, saved-once result and download |

Open the MP4 in a video player. To use the captioned playback page after cloning the repository, run:

```sh
uv run python -m http.server 8789 --bind 127.0.0.1 --directory submission/demo
```

Then open <http://127.0.0.1:8789/playback.html>. No API key is needed for playback. The video samples the browser viewport twice per second and encodes H.264 for portable playback. It contains no audio or desktop content outside the app.
