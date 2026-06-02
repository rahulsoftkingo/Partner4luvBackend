import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import app
for route in app.routes:
    methods = getattr(route, 'methods', 'MOUNT')
    path = getattr(route, 'path', 'N/A')
    print(f"Path: {path}, Methods: {methods}")
