import pytest
from src.logs import classify_line, _strip_ansi


# --- _strip_ansi ---

def test_strip_ansi_removes_color_codes():
    assert _strip_ansi('\x1b[31mERROR\x1b[0m') == 'ERROR'

def test_strip_ansi_removes_cursor_movement():
    assert _strip_ansi('\x1b[2Jhello') == 'hello'

def test_strip_ansi_passthrough_clean_line():
    line = 'Mar 23 20:35:27 host svc[123]: INFO started'
    assert _strip_ansi(line) == line


# --- classify_line: journalctl short format ---

def test_classify_journalctl_error():
    assert classify_line('Mar 23 20:35:27 host svc[123]: ERROR database connection failed') == 'error'

def test_classify_journalctl_warn():
    assert classify_line('Mar 23 20:35:27 host svc[123]: WARNING disk usage high') == 'warn'

def test_classify_journalctl_info():
    assert classify_line('Mar 23 20:35:27 host svc[123]: INFO service started') == 'info'

def test_classify_journalctl_debug():
    assert classify_line('Mar 23 20:35:27 host svc[123]: DEBUG processing request') == 'debug'

def test_classify_journalctl_untagged():
    assert classify_line('Mar 23 20:35:27 host svc[123]: something happened') == 'untagged'


# --- classify_line: Docker structured format ---

def test_classify_docker_error():
    assert classify_line('time="2024-03-23T20:35:27Z" level=error msg="failed"') == 'error'

def test_classify_docker_warn():
    assert classify_line('time="2024-03-23T20:35:27Z" level=warn msg="slow query"') == 'warn'

def test_classify_docker_info():
    assert classify_line('time="2024-03-23T20:35:27Z" level=info msg="started"') == 'info'

def test_classify_docker_debug():
    assert classify_line('time="2024-03-23T20:35:27Z" level=debug msg="trace"') == 'debug'

def test_classify_docker_untagged():
    assert classify_line('time="2024-03-23T20:35:27Z" msg="container started"') == 'untagged'


# --- classify_line: Python logging format ---

def test_classify_python_error():
    assert classify_line('2024-03-23 20:35:27,123 - myapp.db - ERROR - connection refused') == 'error'

def test_classify_python_warn():
    assert classify_line('2024-03-23 20:35:27,123 - myapp - WARNING - deprecated call') == 'warn'

def test_classify_python_info():
    assert classify_line('2024-03-23 20:35:27,123 - myapp - INFO - request completed') == 'info'

def test_classify_python_debug():
    assert classify_line('2024-03-23 20:35:27,123 - myapp - DEBUG - entering function') == 'debug'

def test_classify_python_untagged():
    assert classify_line('2024-03-23 20:35:27,123 - myapp - NOTICE - something') == 'untagged'


# --- Priority and edge cases ---

def test_classify_error_beats_warn():
    # Both error and warn keywords present; error wins (higher priority)
    assert classify_line('WARN: ERROR count exceeded threshold') == 'error'

def test_classify_case_insensitive():
    assert classify_line('error: something bad') == 'error'
    assert classify_line('Error: something bad') == 'error'

def test_classify_ansi_stripped_before_classification():
    # ANSI codes around ERROR keyword must not prevent classification
    assert classify_line('\x1b[31mERROR\x1b[0m: something failed') == 'error'

def test_classify_third_party_output_is_untagged():
    line = '/opt/photo-curator/venv/lib/python3.12/site-packages/insightface/utils/face_align.py:23: FutureWarning'
    assert classify_line(line) == 'untagged'

def test_classify_warn_keyword_variant():
    assert classify_line('WARN something') == 'warn'
    assert classify_line('WARNING something') == 'warn'
