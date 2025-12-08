#!/usr/bin/env python3
# /// script
# dependencies = [
#     "gradio>=4.0.0",
#     "optuna>=3.0.0",
#     "pandas",
#     "plotly",
# ]
# ///

"""
Gradio dashboard for HPO study visualisation.

Provides an interactive interface for exploring optimisation results,
parameter importance, and trial details.
"""

import argparse
from pathlib import Path

import gradio as gr
import optuna
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from optuna.visualization import (
    plot_optimization_history,
    plot_param_importances,
    plot_parallel_coordinate,
)


def load_study(storage_url: str, study_name: str) -> optuna.Study:
    """Load an Optuna study from storage."""
    return optuna.load_study(study_name=study_name, storage=storage_url)


def get_trials_dataframe(study: optuna.Study) -> pd.DataFrame:
    """Convert study trials to a DataFrame."""
    records = []

    for trial in study.trials:
        record = {
            "trial": trial.number,
            "objective": trial.value,
            "status": trial.state.name,
            "duration_min": (
                trial.duration.total_seconds() / 60
                if trial.duration else None
            ),
        }

        # Add hyperparameters
        for key, value in trial.params.items():
            record[key] = value

        # Add user attributes (like cost)
        for key, value in trial.user_attrs.items():
            record[key] = value

        records.append(record)

    df = pd.DataFrame(records)

    # Sort by objective (best first for minimisation)
    if len(df) > 0 and "objective" in df.columns:
        df = df.sort_values("objective", ascending=True, na_position="last")

    return df


def create_optimization_history_plot(study: optuna.Study) -> go.Figure:
    """Create the optimisation history plot."""
    try:
        fig = plot_optimization_history(study)
        fig.update_layout(
            title="Optimisation history",
            xaxis_title="Trial",
            yaxis_title="Objective value (eval_loss)",
        )
        return fig
    except Exception as e:
        # Return empty figure with error message
        fig = go.Figure()
        fig.add_annotation(
            text=f"Cannot create plot: {e}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
        )
        return fig


def create_param_importance_plot(study: optuna.Study) -> go.Figure:
    """Create the parameter importance plot."""
    try:
        fig = plot_param_importances(study)
        fig.update_layout(title="Parameter importance")
        return fig
    except Exception as e:
        fig = go.Figure()
        fig.add_annotation(
            text=f"Cannot compute importance: {e}\n(Need more completed trials)",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
        )
        return fig


def create_parallel_coordinate_plot(study: optuna.Study) -> go.Figure:
    """Create the parallel coordinate plot."""
    try:
        fig = plot_parallel_coordinate(study)
        fig.update_layout(title="Parallel coordinates")
        return fig
    except Exception as e:
        fig = go.Figure()
        fig.add_annotation(
            text=f"Cannot create plot: {e}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
        )
        return fig


def get_best_trial_info(study: optuna.Study) -> str:
    """Get formatted information about the best trial."""
    try:
        best = study.best_trial

        lines = [
            f"**Best trial: #{best.number}**",
            f"",
            f"**Objective value:** {best.value:.6f}",
            f"",
            f"**Hyperparameters:**",
        ]

        for key, value in sorted(best.params.items()):
            if isinstance(value, float):
                lines.append(f"- {key}: {value:.6g}")
            else:
                lines.append(f"- {key}: {value}")

        if best.duration:
            lines.append(f"")
            lines.append(f"**Duration:** {best.duration.total_seconds() / 60:.1f} minutes")

        return "\n".join(lines)

    except Exception as e:
        return f"No best trial available yet: {e}"


def get_study_summary(study: optuna.Study) -> str:
    """Get a summary of the study."""
    completed = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
    pruned = len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])
    failed = len([t for t in study.trials if t.state == optuna.trial.TrialState.FAIL])
    running = len([t for t in study.trials if t.state == optuna.trial.TrialState.RUNNING])

    # Calculate total cost if available
    total_cost = sum(
        t.user_attrs.get("cost_usd", 0)
        for t in study.trials
    )

    lines = [
        f"**Study:** {study.study_name}",
        f"",
        f"**Trials:**",
        f"- Completed: {completed}",
        f"- Pruned: {pruned}",
        f"- Failed: {failed}",
        f"- Running: {running}",
    ]

    if total_cost > 0:
        lines.append(f"")
        lines.append(f"**Total cost:** ${total_cost:.2f}")

    return "\n".join(lines)


def create_dashboard(storage_url: str, study_name: str) -> gr.Blocks:
    """Create the Gradio dashboard."""

    def refresh_data():
        """Refresh all data from the study."""
        study = load_study(storage_url, study_name)
        df = get_trials_dataframe(study)

        return (
            create_optimization_history_plot(study),
            create_param_importance_plot(study),
            df,
            get_best_trial_info(study),
            get_study_summary(study),
        )

    with gr.Blocks(title=f"HPO Dashboard: {study_name}") as app:
        gr.Markdown(f"# Optuna HPO dashboard: {study_name}")

        with gr.Row():
            refresh_btn = gr.Button("Refresh", variant="primary")

        with gr.Row():
            with gr.Column(scale=1):
                history_plot = gr.Plot(label="Optimisation history")

            with gr.Column(scale=1):
                importance_plot = gr.Plot(label="Parameter importance")

        with gr.Row():
            trials_table = gr.Dataframe(
                label="Trial table",
                interactive=False,
            )

        with gr.Row():
            with gr.Column(scale=1):
                best_trial_info = gr.Markdown(label="Best trial")

            with gr.Column(scale=1):
                study_summary = gr.Markdown(label="Study summary")

        # Load initial data
        app.load(
            fn=refresh_data,
            outputs=[
                history_plot,
                importance_plot,
                trials_table,
                best_trial_info,
                study_summary,
            ],
        )

        # Refresh button
        refresh_btn.click(
            fn=refresh_data,
            outputs=[
                history_plot,
                importance_plot,
                trials_table,
                best_trial_info,
                study_summary,
            ],
        )

    return app


def create_dashboard_from_hub(repo_id: str, study_name: str) -> gr.Blocks:
    """Create dashboard from a Hub-hosted study."""
    from huggingface_hub import hf_hub_download

    # Download the study database
    local_path = hf_hub_download(
        repo_id=repo_id,
        filename=f"{study_name}.db",
        repo_type="dataset",
    )

    storage_url = f"sqlite:///{local_path}"
    return create_dashboard(storage_url, study_name)


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Launch HPO visualisation dashboard"
    )

    parser.add_argument(
        "--study",
        type=str,
        help="Path to SQLite study database (e.g., ./optuna_studies/my-study.db)",
    )

    parser.add_argument(
        "--hub",
        type=str,
        help="Hub repo ID (e.g., username/my-hpo-study)",
    )

    parser.add_argument(
        "--name",
        type=str,
        default="hpo-study",
        help="Study name within the database",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run dashboard on",
    )

    parser.add_argument(
        "--share",
        action="store_true",
        help="Create a public Gradio link",
    )

    args = parser.parse_args()

    if args.hub:
        app = create_dashboard_from_hub(args.hub, args.name)
    elif args.study:
        storage_url = f"sqlite:///{args.study}"
        app = create_dashboard(storage_url, args.name)
    else:
        parser.error("Must specify either --study or --hub")

    app.launch(
        server_port=args.port,
        share=args.share,
    )


if __name__ == "__main__":
    main()
