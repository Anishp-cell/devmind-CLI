import os
import re
import logging

logger = logging.getLogger("devmind.comment_extractor")

# Regex to find common developer tags in comments
TAG_PATTERN = re.compile(r"\b(TODO|FIXME|NOTE|BUG|HACK|WARNING|ADR|DEPRECATED)\b", re.IGNORECASE)

def extract_comments_from_file(file_path: str) -> list[str]:
    """
    Parses a single file, extracting inline comments and docstrings
    that contain key developer tags (TODO, FIXME, NOTE, HACK, etc.).
    """
    extracted = []
    _, ext = os.path.splitext(file_path.lower())
    
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        lines = content.splitlines()

        # 1. Python parsing (extract hash comments and triple-quoted docstrings)
        if ext in (".py", ".sh", ".yaml", ".yml", ".ini"):
            # Inline comment scanner
            for idx, line in enumerate(lines, start=1):
                comment_match = re.search(r"#\s*(.*)", line)
                if comment_match:
                    comment_text = comment_match.group(1).strip()
                    if TAG_PATTERN.search(comment_text):
                        extracted.append(f"Line {idx}: {comment_text}")

            # Simple regex search for docstrings
            docstrings = re.findall(r'"""(.*?)"""', content, re.DOTALL)
            docstrings.extend(re.findall(r"'''(.*?)'''", content, re.DOTALL))
            for doc in docstrings:
                doc_clean = doc.strip()
                if doc_clean:
                    extracted.append(f"Docstring: {doc_clean}")

        # 2. C-Style languages parsing (JS, TS, C, C++, Go, Java, Rust)
        elif ext in (".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".h", ".go", ".java", ".rs", ".css"):
            # Inline comment scanner (// ...)
            for idx, line in enumerate(lines, start=1):
                comment_match = re.search(r"//\s*(.*)", line)
                if comment_match:
                    comment_text = comment_match.group(1).strip()
                    if TAG_PATTERN.search(comment_text):
                        extracted.append(f"Line {idx}: {comment_text}")

            # Block comment scanner (/* ... */)
            block_comments = re.findall(r"/\*(.*?)\*/", content, re.DOTALL)
            for block in block_comments:
                for idx, block_line in enumerate(block.splitlines(), start=1):
                    block_line_clean = block_line.strip().lstrip("*").strip()
                    if TAG_PATTERN.search(block_line_clean):
                        extracted.append(f"Block Comment: {block_line_clean}")

        # 3. HTML/XML/Markdown C-style comments (<!-- ... -->)
        elif ext in (".html", ".htm", ".xml", ".md"):
            html_comments = re.findall(r"<!--(.*?)-->", content, re.DOTALL)
            for block in html_comments:
                for block_line in block.splitlines():
                    block_line_clean = block_line.strip()
                    if TAG_PATTERN.search(block_line_clean):
                        extracted.append(f"HTML Comment: {block_line_clean}")

    except Exception as e:
        logger.error(f"Error parsing comments from {file_path}: {e}")
        
    return extracted

def get_codebase_comments(repo_path: str, source_files: list[str]) -> list[str]:
    """
    Loops through all project files and extracts formatted comments/docstrings.
    Returns a list of structured comment records.
    """
    all_comments = []
    logger.info("Scanning codebase for inline comments and docstrings...")
    
    for file_path in source_files:
        abs_path = os.path.join(repo_path, file_path)
        file_comments = extract_comments_from_file(abs_path)
        
        if file_comments:
            comment_log = [f"File: {file_path}"]
            comment_log.extend(file_comments)
            all_comments.append("\n".join(comment_log))
            
    return all_comments
