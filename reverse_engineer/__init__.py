from pathlib import Path
import sys
_re_dir = str(Path(__file__).parent)
if _re_dir not in sys.path:
    sys.path.insert(0, _re_dir)
