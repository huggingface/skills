"""
Test SKILL.md format validation
"""
import pytest
from pathlib import Path
import re

class TestSkillFormat:
    """Test suite for SKILL.md file format validation."""
    
    @pytest.mark.skill
    @pytest.mark.format
    def test_all_skills_have_skill_md(self, skills_dir):
        """Test that all skill directories have a SKILL.md file."""
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        
        missing_skill_md = []
        for skill_dir in skill_dirs:
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                missing_skill_md.append(skill_dir.name)
        
        assert len(missing_skill_md) == 0, \
            f"Skills missing SKILL.md: {missing_skill_md}"
    
    @pytest.mark.skill
    @pytest.mark.format
    def test_skill_md_has_yaml_frontmatter(self, skills_dir, parse_skill_md_fixture):
        """Test that all SKILL.md files have valid YAML frontmatter."""
        parse_skill_md = parse_skill_md_fixture
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        
        invalid_frontmatter = []
        for skill_dir in skill_dirs:
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                frontmatter, _ = parse_skill_md(skill_md)
                if frontmatter is None:
                    invalid_frontmatter.append(skill_dir.name)
        
        assert len(invalid_frontmatter) == 0, \
            f"Skills with invalid/missing YAML frontmatter: {invalid_frontmatter}"
    
    @pytest.mark.skill
    def test_skill_md_has_name_field(self, skills_dir, parse_skill_md_fixture):
        """Test that all SKILL.md files have a 'name' field in frontmatter."""
        parse_skill_md = parse_skill_md_fixture
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        
        missing_name = []
        for skill_dir in skill_dirs:
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                frontmatter, _ = parse_skill_md(skill_md)
                if frontmatter is None or 'name' not in frontmatter:
                    missing_name.append(skill_dir.name)
        
        assert len(missing_name) == 0, \
            f"Skills missing 'name' field in frontmatter: {missing_name}"
    
    @pytest.mark.skill
    def test_skill_md_has_description_field(self, skills_dir, parse_skill_md_fixture):
        """Test that all SKILL.md files have a 'description' field in frontmatter."""
        parse_skill_md = parse_skill_md_fixture
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        
        missing_description = []
        for skill_dir in skill_dirs:
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                frontmatter, _ = parse_skill_md(skill_md)
                if frontmatter is None or 'description' not in frontmatter:
                    missing_description.append(skill_dir.name)
        
        assert len(missing_description) == 0, \
            f"Skills missing 'description' field in frontmatter: {missing_description}"
    
    @pytest.mark.skill
    def test_skill_name_matches_directory(self, skills_dir, parse_skill_md_fixture):
        """Test that the 'name' field in SKILL.md matches the directory name."""
        parse_skill_md = parse_skill_md_fixture
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        
        mismatched_names = []
        for skill_dir in skill_dirs:
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                frontmatter, _ = parse_skill_md(skill_md)
                if frontmatter and 'name' in frontmatter:
                    if frontmatter['name'] != skill_dir.name:
                        mismatched_names.append({
                            'directory': skill_dir.name,
                            'name_field': frontmatter['name']
                        })
        
        assert len(mismatched_names) == 0, \
            f"Skills with mismatched name field and directory: {mismatched_names}"
    
    @pytest.mark.skill
    def test_skill_name_format(self, skills_dir, parse_skill_md_fixture):
        """Test that skill names follow the correct format (lowercase, hyphens)."""
        parse_skill_md = parse_skill_md_fixture
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        
        invalid_names = []
        name_pattern = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
        
        for skill_dir in skill_dirs:
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                frontmatter, _ = parse_skill_md(skill_md)
                if frontmatter and 'name' in frontmatter:
                    name = frontmatter['name']
                    if not name_pattern.match(name):
                        invalid_names.append(name)
        
        assert len(invalid_names) == 0, \
            f"Skills with invalid name format: {invalid_names}"
    
    @pytest.mark.skill
    def test_agentsmd_agents_md_has_yaml_frontmatter(self, agentsmd_dir):
        """Test that agentsmd/AGENTS.md has valid YAML frontmatter."""
        agents_md = agentsmd_dir / "AGENTS.md"
        assert agents_md.exists(), "agentsmd/AGENTS.md does not exist"
        
        with open(agents_md, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert content.startswith('---'), \
            "AGENTS.md is missing YAML frontmatter (should start with '---')"
        
        # Check that it has a second '---' to close the frontmatter
        parts = content.split('---', 2)
        assert len(parts) >= 3, \
            "AGENTS.md has incomplete YAML frontmatter (missing closing '---')"
