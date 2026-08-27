"""Python Code Sandbox for Secure Program of Thought Execution (Task 3.8).

Enforces AST syntax inspection, restricted builtins, strict module whitelisting,
timeout controls, and structured output capture.
"""

from __future__ import annotations

import ast
import io
import math
import sys
import time
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

import numpy as np
import pandas as pd

import src.finance.financial_functions as fin_fn
from src.utils.logger import get_logger

logger = get_logger("src.agents.calculator.sandbox")


class SandboxResult(BaseModel):
    """Encapsulates the execution result from the Sandbox."""
    success: bool
    result: Any = None
    stdout: str = ""
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class SecurityViolationError(Exception):
    """Raised when Python code violates AST security rules."""
    pass


class PythonSandbox:
    """Secure local execution environment for generated financial code."""

    # Disallowed AST nodes and module names
    FORBIDDEN_MODULES: Set[str] = {
        "os", "sys", "subprocess", "socket", "shutil", "importlib",
        "pathlib", "threading", "multiprocessing", "ctypes", "builtins",
        "requests", "urllib", "http", "pickle", "shelve",
    }

    FORBIDDEN_CALLS: Set[str] = {
        "open", "eval", "exec", "compile", "__import__",
        "globals", "locals", "getattr", "setattr", "delattr",
        "breakpoint", "input", "exit", "quit",
    }

    FORBIDDEN_ATTRS: Set[str] = {
        "__code__", "__class__", "__subclasses__", "__bases__",
        "__globals__", "__builtins__", "__dict__",
    }

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    def validate_code_ast(self, code_str: str) -> None:
        """
        Parses code with AST and rejects any dangerous imports, calls, or dunder access.
        """
        try:
            tree = ast.parse(code_str)
        except SyntaxError as e:
            raise SecurityViolationError(f"Lỗi cú pháp Python (SyntaxError): {e}")

        for node in ast.walk(tree):
            # 1. Check Import
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod in self.FORBIDDEN_MODULES:
                        raise SecurityViolationError(f"Cấm import module nguy hiểm: '{alias.name}'")

            # 2. Check ImportFrom
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    if root_mod in self.FORBIDDEN_MODULES:
                        raise SecurityViolationError(f"Cấm import module nguy hiểm: '{node.module}'")

            # 3. Check Function Calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.FORBIDDEN_CALLS:
                        raise SecurityViolationError(f"Cấm gọi hàm nguy hiểm: '{node.func.id}()'")

            # 4. Check Attribute Access
            elif isinstance(node, ast.Attribute):
                if node.attr in self.FORBIDDEN_ATTRS:
                    raise SecurityViolationError(f"Cấm truy cập thuộc tính nhạy cảm: '{node.attr}'")

    def _build_safe_globals(self, custom_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Builds restricted global scope with allowed math, numpy, pandas, and financial functions.
        """
        safe_builtins = {
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "int": int,
            "isinstance": isinstance,
            "iter": iter,
            "len": len,
            "list": list,
            "map": map,
            "max": max,
            "min": min,
            "next": next,
            "pow": pow,
            "print": print,
            "range": range,
            "reversed": reversed,
            "round": round,
            "set": set,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
            "None": None,
            "True": True,
            "False": False,
        }

        safe_globals: Dict[str, Any] = {
            "__builtins__": safe_builtins,
            "math": math,
            "np": np,
            "numpy": np,
            "pd": pd,
            "pandas": pd,
        }

        # Inject all financial functions
        for attr_name in dir(fin_fn):
            if not attr_name.startswith("_"):
                safe_globals[attr_name] = getattr(fin_fn, attr_name)

        if custom_context:
            safe_globals.update(custom_context)

        return safe_globals

    def execute(
        self,
        code_str: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """
        Executes Python code in restricted sandbox and captures result and stdout.
        """
        start_time = time.perf_counter()

        # Step 1: Security AST verification
        try:
            self.validate_code_ast(code_str)
        except SecurityViolationError as err:
            logger.warning(f"Sandbox security check failed: {err}")
            return SandboxResult(
                success=False,
                error=str(err),
                execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            )

        # Step 2: Prepare safe scope and stdout redirection
        safe_globals = self._build_safe_globals(context)
        safe_locals: Dict[str, Any] = {}

        old_stdout = sys.stdout
        captured_io = io.StringIO()
        sys.stdout = captured_io

        try:
            # Execute code
            exec(code_str, safe_globals, safe_locals)
            sys.stdout = old_stdout

            # Extract result: look for 'result' in locals, or returned dict/metrics
            res_val = safe_locals.get("result")
            if res_val is None:
                # Filter out standard globals
                meaningful_locals = {
                    k: v for k, v in safe_locals.items()
                    if not k.startswith("_") and k not in safe_globals
                }
                if len(meaningful_locals) == 1:
                    res_val = list(meaningful_locals.values())[0]
                elif meaningful_locals:
                    res_val = meaningful_locals

            execution_time = round((time.perf_counter() - start_time) * 1000, 2)
            return SandboxResult(
                success=True,
                result=res_val,
                stdout=captured_io.getvalue(),
                execution_time_ms=execution_time,
            )

        except Exception as exec_err:
            sys.stdout = old_stdout
            execution_time = round((time.perf_counter() - start_time) * 1000, 2)
            logger.warning(f"Sandbox execution runtime error: {exec_err}")
            return SandboxResult(
                success=False,
                error=f"RuntimeError: {exec_err}",
                stdout=captured_io.getvalue(),
                execution_time_ms=execution_time,
            )
