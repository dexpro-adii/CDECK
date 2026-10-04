import os
import sys

# Re-export from backend/tests/test_regression.py
test_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'tests', 'test_regression.py'))
with open(test_file, 'r', encoding='utf-8') as f:
    code = f.read()

exec(code, globals())
