import sys

def setup_unicode():
    """Reconfigure standard output streams to support UTF-8 on Windows."""
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            pass
