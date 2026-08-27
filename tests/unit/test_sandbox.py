"""Unit tests for src.agents.calculator.sandbox."""

import pytest
from src.agents.calculator.sandbox import PythonSandbox, SecurityViolationError


def test_sandbox_safe_execution():
    sandbox = PythonSandbox()
    code = """
revenue = 10000.0
net_income = 1500.0
equity = 5000.0

margin = net_margin(net_income, revenue)
calculated_roe = roe(net_income, equity)

result = {
    "margin": margin,
    "roe": calculated_roe
}
"""
    res = sandbox.execute(code)
    assert res.success is True
    assert res.result["margin"] == 0.15
    assert res.result["roe"] == 0.3
    assert res.error is None


def test_sandbox_blocks_os_import():
    sandbox = PythonSandbox()
    bad_code = """
import os
files = os.listdir('.')
"""
    res = sandbox.execute(bad_code)
    assert res.success is False
    assert "Cấm import module nguy hiểm" in res.error


def test_sandbox_blocks_open_call():
    sandbox = PythonSandbox()
    bad_code = """
f = open('secrets.txt', 'w')
f.write('bad')
"""
    res = sandbox.execute(bad_code)
    assert res.success is False
    assert "Cấm gọi hàm nguy hiểm" in res.error


def test_sandbox_blocks_dunder_access():
    sandbox = PythonSandbox()
    bad_code = """
x = ().__class__.__bases__[0].__subclasses__()
"""
    res = sandbox.execute(bad_code)
    assert res.success is False
    assert "Cấm truy cập thuộc tính nhạy cảm" in res.error


def test_sandbox_handles_runtime_error():
    sandbox = PythonSandbox()
    code_with_error = """
a = 10 / 0
"""
    res = sandbox.execute(code_with_error)
    assert res.success is False
    assert "division by zero" in res.error
