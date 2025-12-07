#!/usr/bin/env python3
"""
Hackers Leaderboard - Gradio app for displaying engagement from hf-skills org.

Reads leaderboard data from the hf-skills/hackers-leaderboard dataset.
Run collect_points.py separately to update the dataset.

Usage:
    python app.py
"""

from __future__ import annotations

import json

import gradio as gr
import requests

TABLE_HEADERS = [
    "Rank",
    "Username",
    "Points",
    "💬 Discussions",
    "📝 Comments",
    "🔀 PRs",
    "📦 Repos",
]

TABLE_DATATYPES = [
    "number",
    "markdown",
    "number",
    "number",
    "number",
    "number",
    "number",
]


DATASET_REPO = "hf-skills/hackers-leaderboard"
LEADERBOARD_URL = f"https://huggingface.co/datasets/{DATASET_REPO}/raw/main/data/leaderboard.jsonl"
METADATA_URL = f"https://huggingface.co/datasets/{DATASET_REPO}/raw/main/data/metadata.json"


def format_username(username: str) -> str:
    """Format username as a clickable link."""
    return f"[{username}](https://huggingface.co/{username})"


def fetch_leaderboard() -> tuple[list[dict], dict]:
    """Fetch leaderboard data from the HF dataset."""
    # Fetch leaderboard JSONL
    resp = requests.get(LEADERBOARD_URL, timeout=30)
    resp.raise_for_status()
    leaderboard = [json.loads(line) for line in resp.text.strip().split("\n") if line]

    # Fetch metadata
    resp = requests.get(METADATA_URL, timeout=30)
    resp.raise_for_status()
    metadata = resp.json()

    return leaderboard, metadata


def refresh_handler() -> tuple[str, list[list]]:
    """Refresh the leaderboard data from the dataset."""
    try:
        leaderboard, metadata = fetch_leaderboard()

        # Build table rows
        rows = []
        for i, entry in enumerate(leaderboard, 1):
            rows.append(
                [
                    i,
                    format_username(entry["username"]),
                    entry["total_points"],
                    entry["discussions_opened"],
                    entry["comments_made"],
                    entry["prs_opened"],
                    entry["repos_owned"],
                ]
            )

        timestamp = metadata.get("generated_at", "unknown")
        if timestamp != "unknown":
            from datetime import datetime

            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp = dt.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                pass

        status = f"""
<div class="info-section">
<h3>Leaderboard Stats</h3>
<div class="info-list">
    <div class="info-item">
        <span class="info-label">Participants</span>
        <span class="info-value">{metadata.get('total_participants', len(leaderboard))}</span>
    </div>
    <div class="info-item">
        <span class="info-label">Total points</span>
        <span class="info-value">{metadata.get('total_points', sum(e['total_points'] for e in leaderboard))}</span>
    </div>
    <div class="info-item">
        <span class="info-label">Last updated</span>
        <span class="info-value">{timestamp}</span>
    </div>
</div>
</div>
"""

        return status, rows

    except Exception as e:
        return f"Failed to load leaderboard: {e}", []


custom_css = """
:root {
    --bg-primary: #1a1a1a;
    --bg-secondary: #262626;
    --bg-hover: #2d2d2d;
    --border-color: #3a3a3a;
    --text-primary: #ffffff;
    --text-secondary: #a3a3a3;
    --accent: #ffa116;
    --accent-dim: #666;
}

body {
    background: var(--bg-primary) !important;
    color: var(--text-primary) !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
}

.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
    background: var(--bg-primary) !important;
}

/* Header */
.header {
    padding: 24px 0 16px;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 20px;
}

.header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    margin: 0 0 8px;
    color: var(--text-primary);
    letter-spacing: -0.02em;
}

.header p {
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.95rem;
}

/* Banner */
.banner {
    margin-bottom: 20px;
    border-radius: 8px;
    overflow: hidden;
}

.banner img {
    width: 100%;
    display: block;
    border-radius: 8px;
}

/* Info section */
.info-section {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    padding: 16px;
    margin-bottom: 20px;
}

.info-section h3 {
    font-size: 1.1rem;
    font-weight: 700;
    margin: 0 0 16px;
    color: var(--text-primary);
    letter-spacing: -0.01em;
}

.info-list {
    display: grid;
    gap: 8px;
}

.info-item {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid var(--border-color);
    font-size: 0.875rem;
}

.info-item:last-child {
    border-bottom: none;
}

.info-label {
    color: var(--text-secondary);
}

.info-value {
    color: var(--text-primary);
    font-weight: 500;
}

/* Table styling */
.dataframe {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 4px !important;
}

.dataframe table {
    background: transparent !important;
}

.dataframe thead th {
    background: var(--bg-secondary) !important;
    color: var(--text-primary) !important;
    font-weight: 700 !important;
    font-size: 0.875rem !important;
    padding: 14px 12px !important;
    border-bottom: 2px solid var(--border-color) !important;
    text-align: left !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
}

.dataframe tbody td {
    background: var(--bg-secondary) !important;
    color: var(--text-primary) !important;
    padding: 12px !important;
    border-bottom: 1px solid var(--border-color) !important;
    font-size: 0.875rem !important;
}

.dataframe tbody tr:hover td {
    background: var(--bg-hover) !important;
}

.dataframe tbody tr:last-child td {
    border-bottom: none !important;
}

.dataframe a {
    color: var(--text-primary) !important;
    text-decoration: none !important;
}

.dataframe a:hover {
    color: var(--accent) !important;
}

/* Button */
button {
    background: var(--bg-secondary) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 4px !important;
    padding: 8px 16px !important;
    font-size: 0.875rem !important;
    cursor: pointer !important;
}

button:hover {
    background: var(--bg-hover) !important;
}

/* Footer */
.footer {
    margin-top: 32px;
    padding-top: 24px;
    border-top: 1px solid var(--border-color);
    color: var(--text-secondary);
    font-size: 0.875rem;
}

.footer h3 {
    font-size: 1.1rem;
    font-weight: 700;
    margin: 0 0 12px;
    color: var(--text-primary);
    letter-spacing: -0.01em;
}

.footer a {
    color: var(--text-secondary);
    text-decoration: none;
}

.footer a:hover {
    color: var(--text-primary);
}
"""


with gr.Blocks(theme=gr.themes.Soft(), css=custom_css) as demo:
    with gr.Column():
        gr.HTML(
            """
            <div class="banner">
                <img src="https://github.com/huggingface/skills/raw/main/assets/banner.png" alt="Humanity's Last Hackathon (of 2025)">
            </div>
            <div class="header">
                <h1>Humanity's Last Hackathon Leaderboard</h1>
                <p>Compete, contribute, and earn points in the hf-skills organization</p>
            </div>
            """
        )

        status_box = gr.Markdown(
            """
            <div class="info-section">
                <h3>Leaderboard Stats</h3>
                <div class="info-list">
                    <div class="info-item">
                        <span class="info-label">Loading...</span>
                        <span class="info-value"></span>
                    </div>
                </div>
            </div>
            """,
            elem_classes="info-section",
        )

        leaderboard_table = gr.Dataframe(
            headers=TABLE_HEADERS,
            datatype=TABLE_DATATYPES,
            interactive=False,
            wrap=True,
            column_widths=["6%", "20%", "10%", "15%", "15%", "10%", "10%"],
            row_count=15,
        )

        with gr.Row():
            refresh_btn = gr.Button("🔄 Refresh Data", size="sm")

        refresh_btn.click(
            refresh_handler,
            outputs=[status_box, leaderboard_table],
        )

        gr.HTML(
            f"""
            <div class="footer">
                <h3>Get Involved</h3>
                <p>Join the hackathon and start earning points by contributing to the hf-skills organization.</p>
                <p><strong>Resources:</strong> <a href="https://huggingface.co/organizations/hf-skills/share/KrqrmBxkETjvevFbfkXeezcyMbgMjjMaOp">Join hf-skills</a> • <a href="https://github.com/huggingface/skills/tree/main/apps/quests">Quest Instructions</a> • <a href="https://github.com/huggingface/skills">GitHub</a> • <a href="https://huggingface.co/datasets/{DATASET_REPO}">Dataset</a></p>
            </div>
            """
        )

    demo.load(
        refresh_handler,
        outputs=[status_box, leaderboard_table],
    )

if __name__ == "__main__":
    demo.launch()
