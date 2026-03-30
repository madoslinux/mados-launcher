#!/usr/bin/env python3
"""Basic tests for mados-launcher - verify modules compile."""

import py_compile
import os

test_dir = os.path.dirname(os.path.abspath(__file__))
repo_dir = os.path.dirname(test_dir)

def test_config_compile():
    """Test config.py compiles without syntax errors."""
    py_compile.compile(f"{repo_dir}/config.py", doraise=True)


def test_logger_compile():
    """Test logger.py compiles without syntax errors."""
    py_compile.compile(f"{repo_dir}/logger.py", doraise=True)


def test_state_manager_compile():
    """Test state_manager.py compiles without syntax errors."""
    py_compile.compile(f"{repo_dir}/state_manager.py", doraise=True)


def test_window_manager_compile():
    """Test window_manager.py compiles without syntax errors."""
    py_compile.compile(f"{repo_dir}/window_manager.py", doraise=True)


if __name__ == "__main__":
    test_config_compile()
    test_logger_compile()
    test_state_manager_compile()
    test_window_manager_compile()
    print("All tests passed!")
