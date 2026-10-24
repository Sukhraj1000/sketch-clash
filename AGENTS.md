# Project instructions

The user explicitly wants Sketch Clash to run **locally only**, without GPT hosting or sign-in.

- Develop, test, and preview through localhost. Keep servers bound to `127.0.0.1`.
- Do not publish, deploy, upload a hosted build, create a hosted preview, or reconnect this project to Sites unless the user explicitly requests it later.
- On 2026-10-24 the user requested Docker and briefly a Vercel deployment, then asked for the deployment to be torn down because hosting is optional. The Vercel project `sketch-clash` was deleted; nothing is hosted. `compose.yaml` runs the full stack locally (published on `127.0.0.1:8080` only). `vercel.json` and the allowlist `.vercelignore` remain for an optional future deploy. Deploying anything, or hosting the backend (Railway, Fly.io, etc.), needs the user's explicit request.
- Changes to source, local builds, and local previews remain in scope.
- The retired hosting metadata was moved outside this project. Moving that record does not delete or take any previously hosted site offline; do not claim otherwise.
- Treat `.env` and `.env.*` (except `.env.example`) as secrets. Never read or print their values in tool outputs, chat, logs, browser code, or archives. Use the hidden `npm run setup:gemini` prompt for user entry. Future Gemini calls must keep the key on a local server; never use a `VITE_` key variable.
- Follow the user's hackathon Gemini guide for new AI work: use the official Google GenAI SDK and the Interactions API (`google-genai` / `client.aio.interactions.create` on the FastAPI backend). Default reasoning model is `gemini-4-argon`; use `generation_config.thinking_level` (`low`, `medium`, or `high`), not `thinking_budget`, and omit temperature/top_p/top_k/explicit cached_content. Use `gemini-3.8-flash` or `gemini-3.5-flash-lite` when a faster model is appropriate. Keep one-off checks synchronous with `store: false`. Key setup and connectivity tests do not authorize expanding gameplay; implement AI game features when requested.

## Git workflow

- Make regular local commits at completed, verified milestones. The user has explicitly requested an ongoing commit history.
- Separate unrelated work into focused commits with descriptive messages; keep each change with its relevant tests and configuration.
- Inspect staged changes before committing. Exclude credentials, local configuration, model weights, generated builds, caches and private captures.
- Preserve existing history and honest timestamps. Do not rewrite history or push to a remote unless separately requested.
