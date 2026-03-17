"""
Tests for the sandboxed code execution engine.
Priority: security tests to ensure sandbox cannot be escaped.
"""

import pytest
import asyncio
from tools.code_executor import (
    execute_python_code,
    execute_with_data,
    create_safe_globals,
    _validate_code_safety,
    ALLOWED_MODULES,
    BLOCKED_ATTRS,
)


# ============================================================
# Security Tests — Sandbox Escape Prevention
# ============================================================

class TestSandboxSecurity:
    """Tests to ensure the sandbox cannot be escaped."""

    @pytest.mark.asyncio
    async def test_import_os_blocked(self):
        """__import__('os') must be blocked."""
        success, output, error = await execute_python_code("import os")
        assert not success
        assert "not allowed" in (error or "").lower() or "Import" in (error or "")

    @pytest.mark.asyncio
    async def test_import_subprocess_blocked(self):
        success, output, error = await execute_python_code("import subprocess")
        assert not success

    @pytest.mark.asyncio
    async def test_import_sys_blocked(self):
        success, output, error = await execute_python_code("import sys")
        assert not success

    @pytest.mark.asyncio
    async def test_dunder_import_os_blocked(self):
        """Direct __import__('os') call must be blocked."""
        success, output, error = await execute_python_code("__import__('os')")
        assert not success

    @pytest.mark.asyncio
    async def test_subclass_traversal_blocked(self):
        """Accessing __subclasses__ for sandbox escape must be blocked."""
        code = "().__class__.__bases__[0].__subclasses__()"
        success, output, error = await execute_python_code(code)
        assert not success
        assert "__class__" in (error or "") or "__bases__" in (error or "") or "__subclasses__" in (error or "")

    @pytest.mark.asyncio
    async def test_class_bases_blocked(self):
        code = "print(object.__subclasses__())"
        success, output, error = await execute_python_code(code)
        assert not success

    @pytest.mark.asyncio
    async def test_globals_access_blocked(self):
        code = "print(globals())"
        success, output, error = await execute_python_code(code)
        assert not success

    @pytest.mark.asyncio
    async def test_builtins_access_is_restricted(self):
        """__builtins__ is accessible but only contains our safe subset."""
        code = "print('open' not in __builtins__ and 'exec' not in __builtins__)"
        success, output, error = await execute_python_code(code)
        assert success
        assert "True" in output

    @pytest.mark.asyncio
    async def test_exec_blocked(self):
        success, output, error = await execute_python_code("exec('print(1)')")
        assert not success

    @pytest.mark.asyncio
    async def test_eval_blocked(self):
        success, output, error = await execute_python_code("eval('1+1')")
        assert not success

    @pytest.mark.asyncio
    async def test_open_file_blocked(self):
        success, output, error = await execute_python_code("open('/etc/passwd')")
        assert not success

    @pytest.mark.asyncio
    async def test_getattr_dunder_blocked(self):
        """getattr with dunder attribute should be blocked by static analysis."""
        code = "getattr((), '__class__')"
        success, output, error = await execute_python_code(code)
        assert not success

    @pytest.mark.asyncio
    async def test_compile_blocked(self):
        success, output, error = await execute_python_code("compile('1+1', '<x>', 'eval')")
        assert not success


# ============================================================
# Static Analysis Tests
# ============================================================

class TestCodeSafetyValidation:
    """Tests for the _validate_code_safety static checker."""

    def test_safe_code_passes(self):
        is_safe, err = _validate_code_safety("x = 1 + 2\nprint(x)")
        assert is_safe
        assert err is None

    def test_blocked_attr_class(self):
        is_safe, err = _validate_code_safety("x = ().__class__")
        assert not is_safe
        assert "__class__" in err

    def test_blocked_attr_bases(self):
        is_safe, err = _validate_code_safety("x = object.__bases__")
        assert not is_safe

    def test_blocked_getattr_static(self):
        is_safe, err = _validate_code_safety("getattr((), '__class__')")
        assert not is_safe

    def test_normal_attrs_pass(self):
        is_safe, err = _validate_code_safety("x = [1,2,3]\nprint(x.append(4))")
        assert is_safe


# ============================================================
# Functional Tests — Valid Code Execution
# ============================================================

class TestValidCodeExecution:
    """Tests that legitimate code executes correctly."""

    @pytest.mark.asyncio
    async def test_basic_print(self):
        success, output, error = await execute_python_code("print('hello')")
        assert success
        assert "hello" in output

    @pytest.mark.asyncio
    async def test_math_operations(self):
        success, output, error = await execute_python_code(
            "import math\nprint(math.sqrt(16))"
        )
        assert success
        assert "4.0" in output

    @pytest.mark.asyncio
    async def test_json_module(self):
        success, output, error = await execute_python_code(
            "import json\nprint(json.dumps({'key': 'value'}))"
        )
        assert success
        assert "key" in output

    @pytest.mark.asyncio
    async def test_collections_counter(self):
        success, output, error = await execute_python_code(
            "from collections import Counter\nprint(Counter([1,1,2,3]))"
        )
        assert success
        assert "Counter" in output

    @pytest.mark.asyncio
    async def test_list_comprehension(self):
        success, output, error = await execute_python_code(
            "result = [x**2 for x in range(5)]\nprint(result)"
        )
        assert success
        assert "[0, 1, 4, 9, 16]" in output

    @pytest.mark.asyncio
    async def test_datetime_module(self):
        success, output, error = await execute_python_code(
            "import datetime\nprint(type(datetime.datetime.now()))"
        )
        assert success

    @pytest.mark.asyncio
    async def test_statistics_module(self):
        success, output, error = await execute_python_code(
            "import statistics\nprint(statistics.mean([1,2,3,4,5]))"
        )
        assert success
        assert "3" in output

    @pytest.mark.asyncio
    async def test_re_module(self):
        success, output, error = await execute_python_code(
            "import re\nprint(re.findall(r'\\d+', 'abc123def456'))"
        )
        assert success
        assert "123" in output


# ============================================================
# Timeout Tests
# ============================================================

class TestTimeoutEnforcement:

    @pytest.mark.asyncio
    async def test_infinite_loop_timeout(self):
        success, output, error = await execute_python_code(
            "while True: pass",
            timeout_seconds=2
        )
        assert not success
        assert "timed out" in (error or "").lower()

    @pytest.mark.asyncio
    async def test_fast_code_no_timeout(self):
        success, output, error = await execute_python_code(
            "print('fast')",
            timeout_seconds=5
        )
        assert success


# ============================================================
# execute_with_data Tests
# ============================================================

class TestExecuteWithData:

    @pytest.mark.asyncio
    async def test_inject_dict_data(self):
        data = {"my_data": {"key": "value"}}
        success, output, error = await execute_with_data(
            "print(my_data['key'])", data
        )
        assert success
        assert "value" in output

    @pytest.mark.asyncio
    async def test_inject_list_data(self):
        data = {"numbers": [1, 2, 3]}
        success, output, error = await execute_with_data(
            "print(sum(numbers))", data
        )
        assert success
        assert "6" in output

    @pytest.mark.asyncio
    async def test_inject_string_data(self):
        data = {"name": "WandAI"}
        success, output, error = await execute_with_data(
            "print(f'Hello {name}')", data
        )
        assert success
        assert "WandAI" in output


# ============================================================
# Safe Globals Tests
# ============================================================

class TestSafeGlobals:

    def test_import_not_raw_builtin(self):
        """__import__ in safe globals should NOT be the real builtin __import__."""
        import builtins
        safe = create_safe_globals()
        safe_import = safe['__builtins__']['__import__']
        assert safe_import is not builtins.__import__

    def test_safe_import_allows_math(self):
        safe = create_safe_globals()
        safe_import = safe['__builtins__']['__import__']
        result = safe_import('math')
        import math
        assert result is math

    def test_safe_import_blocks_os(self):
        safe = create_safe_globals()
        safe_import = safe['__builtins__']['__import__']
        with pytest.raises(ImportError):
            safe_import('os')

    def test_safe_import_blocks_subprocess(self):
        safe = create_safe_globals()
        safe_import = safe['__builtins__']['__import__']
        with pytest.raises(ImportError):
            safe_import('subprocess')

    def test_no_open_in_builtins(self):
        safe = create_safe_globals()
        assert 'open' not in safe['__builtins__']

    def test_no_exec_in_builtins(self):
        safe = create_safe_globals()
        assert 'exec' not in safe['__builtins__']

    def test_no_eval_in_builtins(self):
        safe = create_safe_globals()
        assert 'eval' not in safe['__builtins__']
