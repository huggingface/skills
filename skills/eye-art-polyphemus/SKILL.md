---
name: eye-art-polyphemus
description: Create and refine images with Eye.Art Polyphemus through its public MCP, including artist-guided images, reference edits, web visuals, editable SVG, and supported motion.
---

# Eye.Art Polyphemus

Use Eye.Art when the user wants an image or editable vector and the current agent host can connect to remote Streamable HTTP MCP servers.

## Connect

Add this remote MCP server to the agent host:

URL: https://eye.art/api/eye-mcp
Transport: Streamable HTTP
Authentication: none

Use its `eye_art_*` tools only when they are available in the current host. If they are not available, explain that the endpoint must first be added as an MCP server. Do not imply a generation occurred without a completed tool result.

## Choose a route

- For a new image, use `eye_art_make_image` with `mode: "image"`.
- For a visual muse, pass `artist`: `polyphemus`, `dali`, `goya`, `matisse`, `leonardo`, `van_gogh`, `rothko`, or `ross`. Preserve the user's subject and composition; treat artist names as visual direction, not endorsement or exact imitation.
- For icons and compact illustrations, use `mode: "small_art"` and specify the target size, silhouette, contrast, and background.
- For an image matched to a website, use `mode: "site_match"`, attach relevant HTML/CSS/JS/TS in `pageReferences`, and specify the target section, crop, palette, and clear space for copy.
- For an image change, use `eye_art_edit_image` with the source image as `imageDataUrl`. Name exactly what should change and what should remain. Keep the source attached on follow-up edits if needed.
- For a genuinely editable vector, use `eye_art_make_svg`; save the returned `svg` field as an `.svg` file. This makes vector geometry; it does not trace raster references or animate SVG.
- Use `eye_art_prompt_ideas` when the user wants to explore directions before rendering. Use `mode: "motion"` only for supported motion requests.

## Keep the conversation and retrieve results

1. For related turns, pass the returned `conversationId` to the next make/edit call. Start a fresh conversation or set `clearReferences: true` for an unrelated concept.
2. If a make/edit call returns a `jobId`, poll `eye_art_image_status` until the job is complete or failed. Show the result only after completion.
3. For an edit, inspect the returned image against the source. If it drifts, retry with the source image again and a narrower change instruction.

## Limits and privacy

- No Eye.Art key is needed. Anonymous image generation is currently limited to 20 generations per hour per caller network identity; free to try does not mean unlimited.
- A longer staged workflow can take several minutes. Relay the actual queued/running status and wait for its result; do not promise a fixed completion time.
- Image references are sent to Eye.Art. Do not upload private or sensitive images without the user's direction. Images, prompts, and conversations may be retained for up to 30 days for service history and debugging.
- Report actual tool status and failures. Do not claim provider, workflow, speed, or quality guarantees the result does not establish.

## Tool reference

The live MCP endpoint exposes `eye_art_make_image`, `eye_art_make_svg`, `eye_art_edit_image`, `eye_art_prompt_ideas`, `eye_art_image_status`, and conversation list/get/delete tools. Check the endpoint's current tool schema for argument details:

https://eye.art/api/eye-mcp
