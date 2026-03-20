# UV rules

Use these rules for Python scripts in this repository:

1. **Use PEP 723 inline dependencies** in each runnable script:
   ```python
   # /// script
   # requires-python = ">=3.10"
   # dependencies = ["requests"]
   # ///
   ```
2. **Run scripts with `uv run`**, not `python ...`:
   ```bash
   uv run scripts/my_script.py --help
   ```
3. **Do not document `pip install -r requirements.txt` for repo scripts** unless there is a specific fallback reason. Normal usage should not require manual installation.
4. **Do not tell users to `source .venv/bin/activate` for skill scripts.** `uv run` should be enough.
5. **If a manual install example is truly needed, use `uv pip install ...`**, not `uv add`, unless you are intentionally editing a project-managed environment.
6. **For Hugging Face Jobs UV workloads, use `hf jobs uv run ...`**.
