# -*- coding: utf-8 -*-
"""
Shared pytest fixtures and path setup.
No tkinter, no API, no filesystem side effects.
"""
import sys
from pathlib import Path

# Allow importing project modules without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))
