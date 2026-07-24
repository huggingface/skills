"""
Conftest.py - Shared fixtures for Hugging Face Skills tests
"""
import pytest
import yaml
from pathlib import Path

@pytest.fixture
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent

@pytest.fixture
def skills_dir(project_root):
    """Return the skills directory."""
    return project_root / "skills"

@pytest.fixture
def agentsmd_dir(project_root):
    """Return the agentsmd directory."""
    return project_root / "agentsmd"

@pytest.fixture
def scripts_dir(project_root):
    """Return the scripts directory."""
    return project_root / "scripts"

def parse_skill_md(file_path):
    """
    Parse a SKILL.md file and return the YAML frontmatter and content.
    
    Returns:
        tuple: (frontmatter_dict, content_str) or (None, content_str) if no frontmatter
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if content.startswith('---'):
        # Has YAML frontmatter
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter_str = parts[1].strip()
            body = parts[2].strip()
            try:
                frontmatter = yaml.safe_load(frontmatter_str)
                return frontmatter, body
            except yaml.YAMLError as e:
                print(f"YAML parse error in {file_path}: {e}")
                return None, content
    
    return None, content

@pytest.fixture
def parse_skill_md_fixture():
    """Return the parse_skill_md function for use in tests."""
    return parse_skill_md
