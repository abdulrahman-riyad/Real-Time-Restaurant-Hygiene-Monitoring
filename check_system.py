#!/usr/bin/env python3
"""
File: /check_system.py (root directory)
System checklist to verify all components are in place
"""

import os
import json
from pathlib import Path

def check_system():
    """Check if all required files and configurations are in place"""
    
    print("="*60)
    print("PIZZA STORE VIOLATION DETECTION - SYSTEM CHECK")
    print("="*60)
    
    checks_passed = 0
    checks_failed = 0
    
    # Check 1: Model file
    print("\n📋 Checking YOLO Model...")
    model_path = "models/yolo12m-v2.pt"
    if os.path.exists(model_path):
        file_size_mb = os.path.getsize(model_path) / (1024 * 1024)
        if file_size_mb > 10:
            print(f"  ✅ Model found: {model_path} ({file_size_mb:.1f} MB)")
            checks_passed += 1
        else:
            print(f"  ⚠️  Model file seems too small: {file_size_mb:.1f} MB")
            print("     This might not be the correct model file!")
            checks_failed += 1
    else:
        print(f"  ❌ Model NOT found at: {model_path}")
        print("     Please download the fine-tuned model and place it in models/")
        checks_failed += 1
    
    # Check 2: ROI Configuration
    print("\n📋 Checking ROI Configuration...")
    roi_path = "roi_config.json"
    if os.path.exists(roi_path):
        try:
            with open(roi_path, 'r') as f:
                config = json.load(f)
                if 'rois' in config and len(config['rois']) > 0:
                    roi = config['rois'][0]
                    print(f"  ✅ ROI config found: {roi['name']}")
                    print(f"     Position: ({roi['x1']}, {roi['y1']}) to ({roi['x2']}, {roi['y2']})")
                    
                    # Check if ROI seems reasonable
                    roi_width = roi['x2'] - roi['x1']
                    roi_height = roi['y2'] - roi['y1']
                    if roi_width < 50 or roi_height < 50:
                        print("     ⚠️  ROI seems very small, might need reconfiguration")
                    elif roi_width > 400 or roi_height > 400:
                        print("     ⚠️  ROI seems very large (covering most of the frame?)")
                        print("     Make sure it only covers the protein container, not the whole counter!")
                    
                    checks_passed += 1
                else:
                    print("  ❌ ROI config file exists but has no ROI defined")
                    checks_failed += 1
        except Exception as e:
            print(f"  ❌ Error reading ROI config: {e}")
            checks_failed += 1
    else:
        print(f"  ❌ ROI config NOT found at: {roi_path}")
        print("     Run: python roi_configurator.py 'data/videos/Sah w b3dha ghalt.mp4'")
        checks_failed += 1
    
    # Check 3: Test Videos
    print("\n📋 Checking Test Videos...")
    video_dir = "data/videos"
    expected_videos = [
        "Sah w b3dha ghalt.mp4",
        "Sah w b3dha ghalt (2).mp4",
        "Sah w b3dha ghalt (3).mp4"
    ]
    
    if os.path.exists(video_dir):
        found_videos = []
        for video in expected_videos:
            video_path = os.path.join(video_dir, video)
            if os.path.exists(video_path):
                file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                print(f"  ✅ Found: {video} ({file_size_mb:.1f} MB)")
                found_videos.append(video)
                checks_passed += 1
            else:
                print(f"  ❌ Missing: {video}")
                checks_failed += 1
                
        if not found_videos:
            print("     No test videos found! Please add videos to data/videos/")
    else:
        print(f"  ❌ Video directory not found: {video_dir}")
        checks_failed += 1
    
    # Check 4: Service Files
    print("\n📋 Checking Service Files...")
    service_files = [
        ("services/detection-service/src/main.py", "Detection Service Main"),
        ("services/detection-service/src/yolo_detector.py", "YOLO Detector"),
        ("services/detection-service/src/violation_logic.py", "Violation Logic"),
        ("services/detection-service/src/roi_processor.py", "ROI Processor"),
        ("services/frame-reader/src/main.py", "Frame Reader"),
        ("services/streaming-service/src/main.py", "Streaming Service"),
        ("services/frontend/src/components/Dashboard.tsx", "Frontend Dashboard"),
        ("docker-compose.yml", "Docker Compose Config"),
        ("requirements.txt", "Python Requirements")
    ]
    
    for filepath, description in service_files:
        if os.path.exists(filepath):
            print(f"  ✅ {description}: {filepath}")
            checks_passed += 1
        else:
            print(f"  ❌ Missing {description}: {filepath}")
            checks_failed += 1
    
    # Check 5: Helper Scripts
    print("\n📋 Checking Helper Scripts...")
    helper_scripts = [
        ("roi_configurator.py", "ROI Configuration Tool"),
        ("test_detection.py", "Detection Test Script"),
        ("check_system.py", "This system check script")
    ]
    
    for script, description in helper_scripts:
        if os.path.exists(script):
            print(f"  ✅ {description}: {script}")
            checks_passed += 1
        else:
            print(f"  ❌ Missing {description}: {script}")
            checks_failed += 1
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"✅ Checks Passed: {checks_passed}")
    print(f"❌ Checks Failed: {checks_failed}")
    
    if checks_failed == 0:
        print("\n🎉 All checks passed! System is ready to run.")
        print("\nNext steps:")
        print("1. docker-compose down")
        print("2. docker-compose up --build")
        print("3. Open http://localhost:3000 in your browser")
    else:
        print(f"\n⚠️  {checks_failed} checks failed. Please fix the issues above.")
        print("\nPriority fixes:")
        if not os.path.exists(model_path):
            print("1. Download and place the fine-tuned model in models/yolo12m-v2.pt")
        if not os.path.exists(roi_path):
            print("2. Run: python roi_configurator.py 'data/videos/Sah w b3dha ghalt.mp4'")
    
    print("="*60)
    
    return checks_failed == 0


if __name__ == "__main__":
    check_system()