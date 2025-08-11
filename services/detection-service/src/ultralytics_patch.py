"""
File: /services/detection-service/src/ultralytics_patch.py
Monkey patch for ultralytics to add C3k2 module compatibility
This should be imported BEFORE importing ultralytics or YOLO
"""

def patch_ultralytics():
    """Patch ultralytics to include C3k2 module for model compatibility"""
    import sys
    
    # Create a mock C3k2 class that will be replaced when ultralytics loads
    class C3k2Mock:
        """Placeholder for C3k2 module"""
        def __init__(self, *args, **kwargs):
            # This will be replaced by the actual implementation
            pass
    
    # Pre-create the module path if it doesn't exist
    if 'ultralytics' not in sys.modules:
        # Pre-import ultralytics modules to ensure they exist
        try:
            import ultralytics
            import ultralytics.nn
            import ultralytics.nn.modules
            import ultralytics.nn.modules.block
        except ImportError:
            return False
    
    # Now patch it
    try:
        import ultralytics.nn.modules.block as block_module
        
        # Check if C3k2 already exists
        if hasattr(block_module, 'C3k2'):
            return True
        
        # Get C3 class to inherit from
        if hasattr(block_module, 'C3'):
            from ultralytics.nn.modules.block import C3
            
            # Create proper C3k2 class
            class C3k2(C3):
                """CSP Bottleneck with 2 convolutions"""
                def __init__(self, c1, c2, n=1, shortcut=True, g=1, e=0.5, k=3):
                    super().__init__(c1, c2, n, shortcut, g, e)
            
            # Use object.__setattr__ to bypass type checking
            object.__setattr__(block_module, 'C3k2', C3k2)
            
            # Also add to module's namespace
            block_module.__dict__['C3k2'] = C3k2
            
            print("✅ Successfully patched ultralytics with C3k2 module")
            return True
        else:
            print("⚠️ C3 module not found, cannot create C3k2")
            return False
            
    except Exception as e:
        print(f"⚠️ Failed to patch ultralytics: {e}")
        return False


# Apply patch when module is imported
patch_ultralytics()