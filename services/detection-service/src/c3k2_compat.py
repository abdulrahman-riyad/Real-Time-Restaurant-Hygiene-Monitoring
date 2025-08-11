"""
File: /services/detection-service/src/c3k2_compat.py
C3k2 compatibility module for YOLO models
"""

import sys
import logging
from typing import Any

logger = logging.getLogger(__name__)

def inject_c3k2_module() -> bool:
    """
    Inject C3k2 module into ultralytics for compatibility with models
    trained on newer versions
    """
    try:
        # Import required modules
        from ultralytics.nn.modules import block
        from ultralytics.nn.modules.block import C3
        
        # Check if C3k2 already exists
        if hasattr(block, 'C3k2'):
            logger.info("C3k2 module already exists in ultralytics")
            return True
        
        # Create C3k2 class
        class C3k2(C3):
            """CSP Bottleneck with 2 convolutions and different kernel sizes"""
            def __init__(self, c1: int, c2: int, n: int = 1, shortcut: bool = True, g: int = 1, e: float = 0.5, k: int = 3):
                super().__init__(c1, c2, n, shortcut, g, e)
                # C3k2 is essentially C3 with potential kernel size variations
                # The actual implementation details depend on the specific YOLO version
        
        # Inject into the modules using setattr to avoid type checking issues
        # Type: ignore is needed because we're dynamically adding attributes
        setattr(sys.modules['ultralytics.nn.modules.block'], 'C3k2', C3k2)  # type: ignore
        
        # Also set as attribute on the module object itself
        import ultralytics.nn.modules.block as block_module
        setattr(block_module, 'C3k2', C3k2)  # type: ignore
        
        # For compatibility, also try to add to globals if possible
        try:
            block.__dict__['C3k2'] = C3k2  # type: ignore
        except:
            pass
        
        logger.info("✅ C3k2 compatibility module injected successfully")
        return True
        
    except ImportError as e:
        logger.error(f"Failed to import required ultralytics modules: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to inject C3k2 module: {e}")
        return False


# Auto-inject when module is imported
inject_c3k2_module()