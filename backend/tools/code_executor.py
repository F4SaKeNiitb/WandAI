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
    'decimal', 'fractions', 'string', 'textwrap'
}

# Restricted names that cannot be accessed
RESTRICTED_NAMES = {
    'open', 'exec', 'eval', 'compile', 
    'input', 'breakpoint', 'memoryview', 'vars',
}


import builtins

def create_safe_globals() -> dict:
    """Create a restricted globals dict for code execution."""
    safe_builtins = {}
    
    # Allow safe built-in functions
    allowed_builtins = [
        'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytes',
        'callable', 'chr', 'complex', 'dict', 'dir', 'divmod',
        'enumerate', 'filter', 'float', 'format', 'frozenset',
        'getattr', 'hasattr', 'hash', 'hex', 'id', 'int', 'isinstance',
        'issubclass', 'iter', 'len', 'list', 'map', 'max', 'min',
        'next', 'object', 'oct', 'ord', 'pow', 'print', 'range',
        'repr', 'reversed', 'round', 'set', 'slice', 'sorted',
        'str', 'sum', 'tuple', 'type', 'zip',
        # Exceptions
        'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError',
        'ImportError', 'AttributeError', 'NameError', 'SyntaxError', 'RuntimeError',
        '__import__'
    ]
    
    for name in allowed_builtins:
        if hasattr(builtins, name):
            safe_builtins[name] = getattr(builtins, name)
    
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
    
    safe_globals = {
        '__builtins__': safe_builtins,
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
        safe_globals['pd'] = pd
        safe_globals['pandas'] = pd
        safe_globals['np'] = np
        safe_globals['numpy'] = np
    except ImportError:
        pass
    
    return safe_globals


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
