"""
Unit tests for DevMind AST parser and zero-token code symbol extraction.
"""
import unittest
from devmind.ingestion.ast_parser import (
    parse_python_ast,
    parse_generic_code_symbols,
    extract_code_symbols,
    build_ast_summary
)


class TestAstParser(unittest.TestCase):

    def test_parse_python_ast(self):
        code = '''
"""Module docstring for test."""
import os
from math import sqrt

class Calculator:
    """A sample calculator class."""
    def add(self, a, b):
        """Add two numbers."""
        return a + b

def standalone_func(x):
    """Standalone function."""
    return x * 2
'''
        symbols = parse_python_ast(code, filename="test_calc.py")
        
        self.assertEqual(symbols["module_docstring"], "Module docstring for test.")
        self.assertIn("os", symbols["imports"])
        self.assertIn("math.sqrt", symbols["imports"])
        
        self.assertEqual(len(symbols["classes"]), 1)
        cls = symbols["classes"][0]
        self.assertEqual(cls["name"], "Calculator")
        self.assertEqual(cls["docstring"], "A sample calculator class.")
        self.assertEqual(len(cls["methods"]), 1)
        self.assertEqual(cls["methods"][0]["name"], "add")
        
        self.assertEqual(len(symbols["functions"]), 1)
        fn = symbols["functions"][0]
        self.assertEqual(fn["name"], "standalone_func")
        self.assertEqual(fn["args"], ["x"])

    def test_parse_js_ts_symbols(self):
        js_code = '''
import { useState } from 'react';

export class UserStore extends BaseStore {
    fetchUser() {}
}

export async function getUser(id) {
    return null;
}

const renderCard = (title) => {
    return title;
};
'''
        symbols = parse_generic_code_symbols(js_code, ".ts")
        self.assertEqual(len(symbols["classes"]), 1)
        self.assertEqual(symbols["classes"][0]["name"], "UserStore")
        self.assertEqual(symbols["classes"][0]["bases"], ["BaseStore"])
        
        fn_names = [f["name"] for f in symbols["functions"]]
        self.assertIn("getUser", fn_names)
        self.assertIn("renderCard", fn_names)

    def test_build_ast_summary(self):
        symbols = {
            "module_docstring": "Sample docstring",
            "imports": ["sys", "os"],
            "classes": [{
                "name": "Widget",
                "bases": ["BaseWidget"],
                "docstring": "Widget doc",
                "methods": [{"name": "render", "args": ["self"], "docstring": "Render widget"}]
            }],
            "functions": [{"name": "init_app", "args": ["config"], "docstring": "Init app"}]
        }
        
        summary = build_ast_summary(symbols, "app/widget.py")
        self.assertIn("[AST CODE SYMBOLS] File: app/widget.py", summary)
        self.assertIn("Class Widget (inherits: BaseWidget)", summary)
        self.assertIn("method render(self)", summary)
        self.assertIn("func init_app(config)", summary)


if __name__ == "__main__":
    unittest.main()
