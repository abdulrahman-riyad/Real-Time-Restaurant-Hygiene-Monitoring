#!/usr/bin/env python3
"""
Model Setup Script for Pizza Store Violation Detection System
This script helps download and validate the YOLO model.
"""

import os
import sys
import hashlib
import requests
from pathlib import Path
from typing import Optional
import torch
from ultralytics import YOLO


def download_file(url: str, filepath: str, chunk_size: int = 8192) -> bool:
    """Download a file with progress indication"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(filepath, 'wb') as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        print(f"Downloading: {progress:.1f}%", end='\r')
        
        print(f"\n✅ Downloaded to {filepath}")
        return True
        
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False


def validate_model(model_path: str) -> bool:
    """Validate that the model can be loaded"""
    try:
        print(f"Validating model at {model_path}...")
        
        # Check file exists
        if not os.path.exists(model_path):
            print("❌ Model file not found")
            return False
        
        # Check file size
        file_size = os.path.getsize(model_path)
        if file_size < 1_000_000:  # Less than 1MB
            print(f"❌ Model file too small ({file_size} bytes), possibly corrupted")
            return False
        
        print(f"File size: {file_size / 1024 / 1024:.2f} MB")
        
        # Try to load with YOLO
        try:
            model = YOLO(model_path)
            print("✅ Model loaded successfully with Ultralytics")
            
            # Check model properties
            if hasattr(model, 'names'):
                classes = model.names
                print(f"Model classes: {classes}")
                
                # Check for expected classes
                expected_classes = ['hand', 'person', 'pizza', 'scooper']
                if isinstance(classes, dict):
                    class_values = [v.lower() for v in classes.values()]
                else:
                    class_values = [c.lower() for c in classes]
                
                found_classes = [c for c in expected_classes if c in class_values]
                missing_classes = [c for c in expected_classes if c not in class_values]
                
                if found_classes:
                    print(f"✅ Found expected classes: {found_classes}")
                if missing_classes:
                    print(f"⚠️  Missing expected classes: {missing_classes}")
                    print("   The model may not be the correct one for this task")
            
            # Test inference
            print("Testing inference...")
            dummy_image = torch.randn(640, 640, 3).numpy()
            results = model(dummy_image, verbose=False)
            print("✅ Inference test passed")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to load model with Ultralytics: {e}")
            print("   This might be a version compatibility issue")
            return False
            
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False


def setup_fallback_model() -> bool:
    """Download and set up the default YOLOv8 model as fallback"""
    try:
        print("Setting up YOLOv8m as fallback model...")
        model = YOLO('yolov8m.pt')  # This will download if not present
        
        # Save to our models directory
        models_dir = Path('models')
        models_dir.mkdir(exist_ok=True)
        
        fallback_path = models_dir / 'yolov8m-fallback.pt'
        model.save(str(fallback_path))
        
        print(f"✅ Fallback model saved to {fallback_path}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to set up fallback model: {e}")
        return False


def main():
    """Main setup function"""
    print("=" * 60)
    print(" Pizza Store Model Setup")
    print("=" * 60)
    print()
    
    # Create models directory
    models_dir = Path('models')
    models_dir.mkdir(exist_ok=True)
    
    model_path = models_dir / 'yolo12m-v2.pt'
    
    # Check if custom model exists
    if model_path.exists():
        print(f"Found existing model at {model_path}")
        if validate_model(str(model_path)):
            print("\n✅ Model is ready to use!")
            return 0
        else:
            print("\n⚠️  Existing model validation failed")
            response = input("Do you want to set up a fallback model? (y/n): ")
            if response.lower() == 'y':
                if setup_fallback_model():
                    print("\n✅ Fallback model ready!")
                    return 0
    else:
        print(f"Custom model not found at {model_path}")
        print("\nOptions:")
        print("1. Download the model manually from the provided link")
        print("2. Use the default YOLOv8 model (automatic download)")
        print()
        
        choice = input("Enter your choice (1 or 2): ")
        
        if choice == '1':
            print("\nPlease download 'yolo12m-v2.pt' and place it in the './models/' directory")
            print("Then run this script again to validate.")
            
            # Optionally provide the URL if known
            url = input("If you have the download URL, enter it (or press Enter to skip): ")
            if url:
                print(f"Attempting to download from {url}...")
                if download_file(url, str(model_path)):
                    if validate_model(str(model_path)):
                        print("\n✅ Model downloaded and validated successfully!")
                        return 0
            
        elif choice == '2':
            if setup_fallback_model():
                print("\n✅ Fallback model ready!")
                print("Note: This is a general-purpose model. For best results,")
                print("use the custom-trained model specific to this task.")
                return 0
    
    print("\n❌ Model setup incomplete")
    print("The system will attempt to use a fallback model when running.")
    return 1


if __name__ == "__main__":
    sys.exit(main())