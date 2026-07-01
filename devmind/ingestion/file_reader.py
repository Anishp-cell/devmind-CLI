import os
import pathlib
import logging

logger = logging.getLogger("devmind.ingestion.file_reader")

# Common directories to skip during scanning
IGNORED_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".cognee_store",
    ".pytest_cache",
    "dist",
    "build",
    "eggs",
    ".eggs",
}

# Supported file extensions for codebase reading
SUPPORTED_EXTENSIONS = {
    ".py", ".md", ".txt", ".js", ".ts", ".html", ".css", 
    ".json", ".yaml", ".yml", ".ini", ".toml", ".sh", ".bat"
}

# Individual configuration files to include even if they don't have standard extensions
EXPLICIT_FILES = {
    "requirements.txt",
    "setup.py",
    "package.json",
    "Dockerfile",
    "Makefile",
    "LICENSE",
    "gitignore",
    ".gitignore",
    ".env.example",
}

def is_text_file(file_path: pathlib.Path) -> bool:
    """
    Check if a file should be read by extension or filename.
    """
    if file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
        return True
    if file_path.name in EXPLICIT_FILES:
        return True
    return False

def scan_codebase_files(root_dir: str) -> list[dict]:
    """
    Recursively scans the root directory for code and documentation files.
    Returns a list of dicts:
    [
        {
            "relative_path": "path/to/file.py",
            "absolute_path": "/absolute/path/to/file.py",
            "content": "file content..."
        }
    ]
    """
    root_path = pathlib.Path(root_dir).resolve()
    logger.info(f"Scanning codebase files under: {root_path}")
    
    codebase_files = []
    
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Modify dirnames in place to skip ignored directories
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]
        
        for filename in filenames:
            file_path = pathlib.Path(dirpath) / filename
            
            if is_text_file(file_path):
                relative_path = file_path.relative_to(root_path)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    
                    # Skip empty or trivial files (e.g. empty __init__.py files)
                    # to prevent LLM structured output validation failures in Cognee
                    stripped_content = content.strip()
                    if not stripped_content or len(stripped_content) < 15:
                        continue
                    
                    codebase_files.append({
                        "relative_path": str(relative_path),
                        "absolute_path": str(file_path),
                        "content": content
                    })
                except Exception as e:
                    logger.warning(f"Skipping file {relative_path} due to read error: {e}")
                    
    logger.info(f"Scan complete. Found {len(codebase_files)} indexable files.")
    return codebase_files
