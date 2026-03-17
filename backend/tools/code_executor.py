"""
Code Executor Tool
Sandboxed Python code execution environment.
"""

import asyncio
import io
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import Any
import json

# Allowed modules for sandboxed execution
ALLOWED_MODULES = {
    'json', 'math', 'datetime', 'collections', 're',
    'statistics', 'random', 'itertools', 'functools',
    'decimal', 'fractions', 'string', 'textwrap',
    'pandas', 'numpy',
}

# Restricted names that cannot be accessed
RESTRICTED_NAMES = {
    'open', 'exec', 'eval', 'compile', '__import__',
    'input', 'breakpoint', 'memoryview', 'vars',
    'globals', 'locals', 'delattr', 'setattr',
}

# Blocked attribute names to prevent sandbox escape via introspection
BLOCKED_ATTRS = {
    '__class__', '__bases__', '__subclasses__', '__mro__',
    '__qualname__', '__module__', '__globals__', '__code__',
    '__closure__', '__func__', '__self__', '__wrapped__',
    '__loader__', '__spec__', '__builtins__', '__import__',
}


import builtins

def _make_safe_import(allowed_modules_map: dict):
    """Create a restricted import function that only allows whitelisted modules."""
    def safe_import(name, *args, **kwargs):
        if name not in ALLOWED_MODULES:
            raise ImportError(
                f"Import of '{name}' is not allowed. "
                f"Allowed modules: {', '.join(sorted(ALLOWED_MODULES))}"
            )
        if name in allowed_modules_map:
            return allowed_modules_map[name]
        raise ImportError(f"Module '{name}' is allowed but not available in this environment.")
    return safe_import


def create_safe_globals() -> dict:
    """Create a restricted globals dict for code execution."""
    safe_builtins = {}

    # Allow safe built-in functions (NO __import__)
    allowed_builtins = [
        'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytes',
        'callable', 'chr', 'complex', 'dict', 'dir', 'divmod',
        'enumerate', 'filter', 'float', 'format', 'frozenset',
        'hasattr', 'hash', 'hex', 'id', 'int', 'isinstance',
        'issubclass', 'iter', 'len', 'list', 'map', 'max', 'min',
        'next', 'object', 'oct', 'ord', 'pow', 'print', 'range',
        'repr', 'reversed', 'round', 'set', 'slice', 'sorted',
        'str', 'sum', 'tuple', 'zip',
        # Exceptions
        'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError',
        'ImportError', 'AttributeError', 'NameError', 'SyntaxError', 'RuntimeError',
        'StopIteration', 'ZeroDivisionError', 'OverflowError', 'ArithmeticError',
        'True', 'False', 'None',
    ]

    for name in allowed_builtins:
        if hasattr(builtins, name):
            safe_builtins[name] = getattr(builtins, name)

    # Remove getattr to prevent attribute introspection escape
    # (users can still access attributes via dot notation)

    # Add allowed modules
    import math
    import datetime
    import json as json_module
    import collections
    import re
    import statistics
    import random
    import itertools
    import functools

    allowed_modules_map = {
        'math': math,
        'datetime': datetime,
        'json': json_module,
        'collections': collections,
        're': re,
        'statistics': statistics,
        'random': random,
        'itertools': itertools,
        'functools': functools,
    }

    # Try to add pandas and numpy if available
    try:
        import pandas as pd
        import numpy as np
        allowed_modules_map['pandas'] = pd
        allowed_modules_map['numpy'] = np
    except ImportError:
        pass

    # Install safe import as the only way to import
    safe_builtins['__import__'] = _make_safe_import(allowed_modules_map)

    safe_globals = {
        '__builtins__': safe_builtins,
    }

    # Pre-load allowed modules into globals for convenience
    safe_globals.update(allowed_modules_map)
    if 'pandas' in allowed_modules_map:
        safe_globals['pd'] = allowed_modules_map['pandas']
    if 'numpy' in allowed_modules_map:
        safe_globals['np'] = allowed_modules_map['numpy']

    return safe_globals


def _validate_code_safety(code: str) -> tuple[bool, str | None]:
    """
    Static analysis to reject code attempting sandbox escape.
    Returns (is_safe, error_message).
    """
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return True, None  # Let the compiler handle syntax errors

    for node in ast.walk(tree):
        # Block access to dunder attributes used for sandbox escape
        if isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_ATTRS:
                return False, f"Access to '{node.attr}' is not allowed for security reasons."

        # Block string access to dunder attrs via getattr
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'getattr':
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    if isinstance(node.args[1].value, str) and node.args[1].value in BLOCKED_ATTRS:
                        return False, f"Access to '{node.args[1].value}' via getattr is not allowed."

    return True, None


async def execute_python_code(
    code: str,
    timeout_seconds: int = 30
) -> tuple[bool, str, str | None]:
    """
    Execute Python code in a sandboxed environment.
    
    Args:
        code: Python code to execute
        timeout_seconds: Maximum execution time
        
    Returns:
        Tuple of (success, output, error)
    """
    # Pre-execution static safety check
    is_safe, safety_error = _validate_code_safety(code)
    if not is_safe:
        return False, "", safety_error

    def run_code():
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        try:
            # Create safe execution environment
            safe_globals = create_safe_globals()
            safe_locals = {}

            # Redirect stdout and stderr
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # Compile the code first to catch syntax errors
                compiled = compile(code, '<sandbox>', 'exec')

                # Execute in the sandboxed environment
                exec(compiled, safe_globals, safe_locals)
            
            output = stdout_capture.getvalue()
            errors = stderr_capture.getvalue()
            
            if errors:
                return False, output, errors
            
            return True, output, None
            
        except SyntaxError as e:
            return False, "", f"Syntax Error: {e.msg} at line {e.lineno}"
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            return False, stdout_capture.getvalue(), error_msg
    
    try:
        # Run in thread pool with timeout
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, run_code),
            timeout=timeout_seconds
        )
        return result
        
    except asyncio.TimeoutError:
        return False, "", f"Execution timed out after {timeout_seconds} seconds"
    except Exception as e:
        return False, "", f"Execution error: {str(e)}"


async def execute_with_data(
    code: str,
    data: dict[str, Any],
    timeout_seconds: int = 30
) -> tuple[bool, str, str | None]:
    """
    Execute Python code with pre-loaded data variables.
    
    Args:
        code: Python code to execute
        data: Dictionary of variable names to values
        timeout_seconds: Maximum execution time
        
    Returns:
        Tuple of (success, output, error)
    """
    # Prepare data injection code
    data_setup = []
    for var_name, value in data.items():
        # Serialize data and inject
        if isinstance(value, (dict, list)):
            data_setup.append(f"{var_name} = json.loads('''{json.dumps(value)}''')")
        elif isinstance(value, str):
            escaped = value.replace("'''", "\\'\\'\\'")
            data_setup.append(f"{var_name} = '''{escaped}'''")
        else:
            data_setup.append(f"{var_name} = {repr(value)}")
    
    # Combine data setup with user code
    full_code = "\n".join(data_setup) + "\n\n" + code
    
    return await execute_python_code(full_code, timeout_seconds)
