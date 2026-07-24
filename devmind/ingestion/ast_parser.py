"""
DevMind AST Parser: Deterministic local code symbol extraction.
Extracts classes, methods, functions, imports, docstrings, and relationships
without calling external LLM APIs.
"""
import ast
import re
import pathlib
import logging

logger = logging.getLogger("devmind.ingestion.ast_parser")

# Regex patterns for non-python code symbol extraction
_JS_TS_CLASS_PATTERN = re.compile(r'(?:export\s+)?(?:default\s+)?class\s+([A-Za-z0-9_]+)(?:\s+extends\s+([A-Za-z0-9_]+))?')
_JS_TS_FUNC_PATTERN = re.compile(r'(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)')
_JS_TS_ARROW_FUNC_PATTERN = re.compile(r'(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>')
_JS_TS_IMPORT_PATTERN = re.compile(r'import\s+(?:{[^}]+}|[A-Za-z0-9_]+)\s+from\s+[\'"]([^\'"]+)[\'"]')

_GO_STRUCT_PATTERN = re.compile(r'type\s+([A-Za-z0-9_]+)\s+struct')
_GO_FUNC_PATTERN = re.compile(r'func\s+(?:\([^)]+\)\s+)?([A-Za-z0-9_]+)\s*\(([^)]*)\)')

_RUST_STRUCT_ENUM_PATTERN = re.compile(r'(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z0-9_]+)')
_RUST_FN_PATTERN = re.compile(r'(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)')


def parse_python_ast(content: str, filename: str = "") -> dict:
    """
    Parses Python source code using Python's standard `ast` module.
    Returns structured dictionaries of classes, functions, imports, and docstrings.
    """
    symbols = {
        "classes": [],
        "functions": [],
        "imports": [],
        "module_docstring": ""
    }
    
    try:
        tree = ast.parse(content, filename=filename or "<string>")
    except Exception as e:
        logger.debug(f"AST parse fallback for {filename}: {e}")
        return parse_generic_code_symbols(content, ".py")
        
    symbols["module_docstring"] = ast.get_docstring(tree) or ""
    
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = [arg.arg for arg in item.args.args]
                    doc = ast.get_docstring(item) or ""
                    methods.append({
                        "name": item.name,
                        "args": args,
                        "docstring": doc,
                        "lineno": item.lineno
                    })
            symbols["classes"].append({
                "name": node.name,
                "bases": bases,
                "methods": methods,
                "docstring": ast.get_docstring(node) or "",
                "lineno": node.lineno
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [arg.arg for arg in node.args.args]
            doc = ast.get_docstring(node) or ""
            symbols["functions"].append({
                "name": node.name,
                "args": args,
                "docstring": doc,
                "lineno": node.lineno
            })
        elif isinstance(node, ast.Import):
            for alias in node.names:
                symbols["imports"].append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                symbols["imports"].append(f"{mod}.{alias.name}" if mod else alias.name)
                
    return symbols


def parse_generic_code_symbols(content: str, file_ext: str) -> dict:
    """
    Regex/pattern fallback parser for JS/TS, Go, Rust, and generic source code.
    """
    symbols = {
        "classes": [],
        "functions": [],
        "imports": [],
        "module_docstring": ""
    }
    
    ext = file_ext.lower()
    
    if ext in (".js", ".ts", ".jsx", ".tsx"):
        for m in _JS_TS_CLASS_PATTERN.finditer(content):
            cls_name, base = m.group(1), m.group(2)
            symbols["classes"].append({
                "name": cls_name,
                "bases": [base] if base else [],
                "methods": [],
                "docstring": ""
            })
        for m in _JS_TS_FUNC_PATTERN.finditer(content):
            fn_name, args_str = m.group(1), m.group(2)
            args = [a.strip() for a in args_str.split(",") if a.strip()]
            symbols["functions"].append({"name": fn_name, "args": args, "docstring": ""})
        for m in _JS_TS_ARROW_FUNC_PATTERN.finditer(content):
            fn_name, args_str = m.group(1), m.group(2)
            args = [a.strip() for a in args_str.split(",") if a.strip()]
            symbols["functions"].append({"name": fn_name, "args": args, "docstring": ""})
        for m in _JS_TS_IMPORT_PATTERN.finditer(content):
            symbols["imports"].append(m.group(1))
            
    elif ext == ".go":
        for m in _GO_STRUCT_PATTERN.finditer(content):
            symbols["classes"].append({"name": m.group(1), "bases": [], "methods": [], "docstring": ""})
        for m in _GO_FUNC_PATTERN.finditer(content):
            fn_name, args_str = m.group(1), m.group(2)
            args = [a.strip() for a in args_str.split(",") if a.strip()]
            symbols["functions"].append({"name": fn_name, "args": args, "docstring": ""})
            
    elif ext == ".rs":
        for m in _RUST_STRUCT_ENUM_PATTERN.finditer(content):
            symbols["classes"].append({"name": m.group(1), "bases": [], "methods": [], "docstring": ""})
        for m in _RUST_FN_PATTERN.finditer(content):
            fn_name, args_str = m.group(1), m.group(2)
            args = [a.strip() for a in args_str.split(",") if a.strip()]
            symbols["functions"].append({"name": fn_name, "args": args, "docstring": ""})
            
    return symbols


def extract_code_symbols(content: str, relative_path: str) -> dict:
    """
    Extracts structured symbols for a code file based on file extension.
    """
    path = pathlib.Path(relative_path)
    ext = path.suffix.lower()
    
    if ext == ".py":
        return parse_python_ast(content, filename=relative_path)
    else:
        return parse_generic_code_symbols(content, ext)


def build_ast_summary(symbols: dict, relative_path: str) -> str:
    """
    Constructs a high-density, formatted text representation of code symbols
    ideal for zero-token local graph memory indexing.
    """
    lines = [f"[AST CODE SYMBOLS] File: {relative_path}"]
    
    if symbols.get("module_docstring"):
        lines.append(f"Module Summary: {symbols['module_docstring'].strip()}")
        
    if symbols.get("imports"):
        imp_str = ", ".join(symbols["imports"][:15])
        lines.append(f"Imports: {imp_str}")
        
    classes = symbols.get("classes", [])
    if classes:
        lines.append("Classes:")
        for c in classes:
            bases = f" (inherits: {', '.join(c['bases'])})" if c.get("bases") else ""
            lines.append(f"  - Class {c['name']}{bases}")
            if c.get("docstring"):
                lines.append(f"    Doc: {c['docstring'].strip()}")
            for m in c.get("methods", []):
                args_str = ", ".join(m.get("args", []))
                doc_str = f" - {m['docstring'].strip()}" if m.get("docstring") else ""
                lines.append(f"    * method {m['name']}({args_str}){doc_str}")
                
    functions = symbols.get("functions", [])
    if functions:
        lines.append("Standalone Functions:")
        for f in functions:
            args_str = ", ".join(f.get("args", []))
            doc_str = f" - {f['docstring'].strip()}" if f.get("docstring") else ""
            lines.append(f"  - func {f['name']}({args_str}){doc_str}")
            
    return "\n".join(lines)
