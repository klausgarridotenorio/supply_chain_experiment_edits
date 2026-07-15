import os
from datetime import datetime

FORMAT = "%Y-%m-%d %H:%M:%S"

# LLM debug logs live next to the other static assets (repo convention).
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'static', 'experiment', 'debug')


def now_datetime() -> str:
    return datetime.now().strftime(FORMAT)


def _debug_path(file_name: str) -> str:
    os.makedirs(DEBUG_DIR, exist_ok=True)
    return os.path.join(DEBUG_DIR, file_name)


def log_debug(*messages: object):
    message = ' '.join(str(m) for m in messages)
    with open(_debug_path('debug.log'), 'a') as f:
        f.write(f"[{now_datetime()}] {message}\n")


def log_interpret(message: str, llm_output: str,
                  price: float | None, quantity: float | None):
    llm_output = llm_output.replace('\n\n', '\n').rstrip('\n')
    indented = llm_output.replace('\n', '\n        ')
    with open(_debug_path('interpret.csv'), 'a') as f:
        f.write(f"MESSAGE {message}\n"
                f"CLEANED {indented}\n"
                f"P / Q   {price} {quantity}\n\n")
