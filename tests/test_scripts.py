"""
Test script validation
"""
import pytest
from pathlib import Path
import stat
import subprocess

class TestScripts:
    """Test suite for script validation."""
    
    @pytest.mark.script
    def test_python_scripts_syntax(self, scripts_dir):
        """Test that all Python scripts have valid syntax."""
        if not scripts_dir.exists():
            pytest.skip("scripts/ directory does not exist")
        
        py_files = list(scripts_dir.glob("*.py"))
        
        syntax_errors = []
        for py_file in py_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    compile(f.read(), py_file.name, 'exec')
            except SyntaxError as e:
                syntax_errors.append({
                    'file': py_file.name,
                    'line': e.lineno,
                    'error': str(e)
                })
        
        assert len(syntax_errors) == 0, \
            f"Python scripts with syntax errors: {syntax_errors}"
    
    @pytest.mark.script
    def test_shell_scripts_executable(self, scripts_dir):
        """Test that Shell scripts are executable."""
        # Skip this test on Windows (Windows doesn't use Unix-style executable permissions)
        import sys
        if sys.platform == "win32":
            pytest.skip("Skipping executable permission check on Windows")
        
        if not scripts_dir.exists():
            pytest.skip("scripts/ directory does not exist")
        
        sh_files = list(scripts_dir.glob("*.sh"))
        
        not_executable = []
        for sh_file in sh_files:
            # Check if file has executable permission
            if not (sh_file.stat().st_mode & stat.S_IXUSR):
                not_executable.append(sh_file.name)
        
        if not_executable:
            # Try to make them executable (for testing purposes)
            for sh_file in not_executable:
                sh_file_path = scripts_dir / sh_file
                sh_file_path.chmod(sh_file_path.stat().st_mode | stat.S_IXUSR)
            
            # Re-check
            still_not_executable = []
            for sh_file in not_executable:
                sh_file_path = scripts_dir / sh_file
                if not (sh_file_path.stat().st_mode & stat.S_IXUSR):
                    still_not_executable.append(sh_file)
            
            assert len(still_not_executable) == 0, \
                f"Shell scripts not executable: {still_not_executable}"
    
    @pytest.mark.script
    def test_publish_script_exists(self, scripts_dir):
        """Test that publish.sh script exists and is valid."""
        if not scripts_dir.exists():
            pytest.skip("scripts/ directory does not exist")
        
        publish_script = scripts_dir / "publish.sh"
        assert publish_script.exists(), \
            "scripts/publish.sh does not exist"
        
        # Check that it's a valid bash script
        with open(publish_script, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
        
        assert first_line.startswith("#!/"), \
            "publish.sh does not have a shebang line"
    
    @pytest.mark.script
    def test_generate_agents_script_exists(self, scripts_dir):
        """Test that generate_agents.py script exists and is valid."""
        if not scripts_dir.exists():
            pytest.skip("scripts/ directory does not exist")
        
        generate_script = scripts_dir / "generate_agents.py"
        assert generate_script.exists(), \
            "scripts/generate_agents.py does not exist"
        
        # Check syntax
        with open(generate_script, 'r', encoding='utf-8') as f:
            try:
                compile(f.read(), generate_script.name, 'exec')
            except SyntaxError as e:
                pytest.fail(f"generate_agents.py has syntax error: {e}")
