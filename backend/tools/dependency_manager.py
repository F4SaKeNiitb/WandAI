"""
Dependency Manager
Handles dynamic installation of Python packages for the sandboxed environment.
"""

import sys
import subprocess
import re
from typing import Tuple
from core.logging import get_logger

logger = get_logger('DEPENDENCY')

def is_safe_package_name(name: str) -> bool:
    """
    Validate package name to prevent shell injection.
    Allows alphanumeric, dash, underscore, and period.
    """
    return bool(re.match(r'^[a-zA-Z0-9_\-\.]+$', name))

def install_package(package_name: str) -> Tuple[bool, str]:
    """
    Install a python package using pip.
    
    Args:
        package_name: Name of the package to install
        
    Returns:
        Tuple of (success, message)
    """
    if not is_safe_package_name(package_name):
        return False, f"Invalid package name: {package_name}"
    
    logger.info(f"📦 Installing dependency: {package_name}...")
    
    try:
        # install specifically to the current python environment
        cmd = [sys.executable, "-m", "pip", "install", package_name]
        
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120  # 2 minute timeout for installation
        )
        
        if result.returncode == 0:
            logger.info(f"✅ Successfully installed {package_name}")
            return True, f"Successfully installed {package_name}"
        else:
            error_msg = result.stderr or result.stdout
            logger.error(f"❌ Failed to install {package_name}: {error_msg}")
            return False, f"Failed to install {package_name}: {error_msg}"
            
    except subprocess.TimeoutExpired:
        return False, f"Installation of {package_name} timed out"
    except Exception as e:
        return False, f"Error installing {package_name}: {str(e)}"
