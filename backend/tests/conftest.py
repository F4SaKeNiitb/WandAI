"""
Pytest configuration and shared fixtures.
"""

import sys
import os

# Add backend directory to Python path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
