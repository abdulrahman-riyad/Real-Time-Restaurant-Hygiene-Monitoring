#!/usr/bin/env python3
"""
Configuration Validator for Pizza Store Violation Detection System
This script validates all configuration and dependencies before running.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict
import shutil


class ConfigValidator:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
        
    def print_header(self, text: str):
        """Print formatted header"""
        print("\n" + "=" * 60)
        print(f" {text}")
        print("=" * 60)
        
    def check_docker(self) -> bool:
        """Check if Docker is installed and running"""
        try:
            # Check if docker command exists
            if not shutil.which('docker'):
                self.errors.append("Docker is not installed")
                return False
                
            # Check if Docker daemon is running
            result = subprocess.run(['docker', 'info'], 
                                  capture_output=True, 
                                  text=True)
            if result.returncode != 0:
                self.errors.append("Docker daemon is not running")
                return False
                
            # Check Docker Compose
            compose_cmd = None
            if shutil.which('docker-compose'):
                compose_cmd = 'docker-compose'
            else:
                # Try docker compose (v2)
                result = subprocess.run(['docker', 'compose', 'version'],
                                      capture_output=True,
                                      text=True)
                if result.returncode == 0:
                    compose_cmd = 'docker compose'
                    
            if not compose_cmd:
                self.errors.append("Docker Compose is not installed")
                return False
                
            self.info.append(f"✅ Docker and {compose_cmd} are installed")
            
            # Check resources
            result = subprocess.run(['docker', 'system', 'info', '--format', 'json'],
                                  capture_output=True,
                                  text=True)
            if result.returncode == 0:
                try:
                    info = json.loads(result.stdout)
                    mem_bytes = info.get('MemTotal', 0)
                    mem_gb = mem_bytes / (1024**3)
                    
                    if mem_gb < 4:
                        self.warnings.append(f"Low memory allocated to Docker: {mem_gb:.1f}GB (recommend 4GB+)")
                    else:
                        self.info.append(f"✅ Docker memory: {mem_gb:.1f}GB")
                except:
                    pass
                    
            return True
            
        except Exception as e:
            self.errors.append(f"Error checking Docker: {e}")
            return False
            
    def check_directories(self) -> bool:
        """Check if required directories exist"""
        required_dirs = [
            'data/videos',
            'models',
            'services/frame-reader',
            'services/detection-service',
            'services/streaming-service',
            'services/frontend'
        ]
        
        all_exist = True
        for dir_path in required_dirs:
            path = Path(dir_path)
            if not path.exists():
                self.errors.append(f"Missing directory: {dir_path}")
                all_exist = False
                
        if all_exist:
            self.info.append("✅ All required directories exist")
            
        return all_exist
        
    def check_video_files(self) -> bool:
        """Check for video files"""
        video_dir = Path('data/videos')
        
        if not video_dir.exists():
            self.errors.append("Video directory does not exist")
            return False
            
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv']
        video_files = []
        
        for ext in video_extensions:
            video_files.extend(video_dir.glob(f'*{ext}'))
            
        if not video_files:
            self.warnings.append("No video files found in data/videos/")
            self.info.append("Expected files:")
            self.info.append("  - Sah w b3dha ghalt.mp4")
            self.info.append("  - Sah w b3dha ghalt (2).mp4")
            self.info.append("  - Sah w b3dha ghalt (3).mp4")
            return False
        else:
            self.info.append(f"✅ Found {len(video_files)} video file(s):")
            for vf in video_files:
                size_mb = vf.stat().st_size / (1024*1024)
                self.info.append(f"   - {vf.name} ({size_mb:.1f} MB)")
                
        return True
        
    def check_model(self) -> bool:
        """Check for YOLO model"""
        model_path = Path('models/yolo12m-v2.pt')
        
        if model_path.exists():
            size_mb = model_path.stat().st_size / (1024*1024)
            self.info.append(f"✅ Custom model found: {model_path.name} ({size_mb:.1f} MB)")
            
            if size_mb < 10:
                self.warnings.append(f"Model file seems too small ({size_mb:.1f} MB), might be corrupted")
                
            return True
        else:
            self.warnings.append("Custom model not found (will use YOLOv8 fallback)")
            self.info.append("To use custom model, place 'yolo12m-v2.pt' in models/ directory")
            return False
            
    def check_roi_config(self) -> bool:
        """Check ROI configuration"""
        roi_path = Path('roi_config.json')
        
        if not roi_path.exists():
            self.warnings.append("ROI config not found (will use defaults)")
            
            # Create default config
            default_config = {
                "frame_width": 640,
                "frame_height": 480,
                "rois": [{
                    "id": "roi_1",
                    "name": "Main Protein Container",
                    "x1": 120,
                    "y1": 180,
                    "x2": 280,
                    "y2": 320,
                    "type": "protein_container",
                    "active": True
                }]
            }
            
            try:
                with open(roi_path, 'w') as f:
                    json.dump(default_config, f, indent=2)
                self.info.append("✅ Created default ROI configuration")
                return True
            except Exception as e:
                self.errors.append(f"Failed to create ROI config: {e}")
                return False
        else:
            try:
                with open(roi_path, 'r') as f:
                    config = json.load(f)
                    
                roi_count = len(config.get('rois', []))
                self.info.append(f"✅ ROI config found with {roi_count} ROI(s)")
                
                # Validate ROI coordinates
                for roi in config.get('rois', []):
                    if roi['x2'] <= roi['x1'] or roi['y2'] <= roi['y1']:
                        self.warnings.append(f"Invalid ROI dimensions: {roi['name']}")
                        
                return True
                
            except json.JSONDecodeError as e:
                self.errors.append(f"Invalid ROI config JSON: {e}")
                return False
            except Exception as e:
                self.errors.append(f"Error reading ROI config: {e}")
                return False
                
    def check_docker_compose(self) -> bool:
        """Check docker-compose.yml configuration"""
        compose_path = Path('docker-compose.yml')
        
        if not compose_path.exists():
            self.errors.append("docker-compose.yml not found")
            return False
            
        try:
            # Try to validate the compose file
            result = subprocess.run(['docker-compose', 'config', '-q'],
                                  capture_output=True,
                                  text=True)
            if result.returncode != 0:
                # Try with docker compose v2
                result = subprocess.run(['docker', 'compose', 'config', '-q'],
                                      capture_output=True,
                                      text=True)
                                      
            if result.returncode != 0:
                self.errors.append("docker-compose.yml validation failed")
                if result.stderr:
                    self.errors.append(f"  {result.stderr.strip()}")
                return False
            else:
                self.info.append("✅ docker-compose.yml is valid")
                return True
                
        except Exception as e:
            self.warnings.append(f"Could not validate docker-compose.yml: {e}")
            return True
            
    def check_ports(self) -> bool:
        """Check if required ports are available"""
        import socket
        
        ports = {
            3000: "Frontend",
            8000: "Streaming Service",
            5672: "RabbitMQ",
            15672: "RabbitMQ Management"
        }
        
        blocked_ports = []
        
        for port, service in ports.items():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            
            if result == 0:
                # Port is in use
                blocked_ports.append(f"Port {port} ({service})")
                
        if blocked_ports:
            self.warnings.append(f"Ports already in use: {', '.join(blocked_ports)}")
            self.info.append("This might be OK if the services are already running")
        else:
            self.info.append("✅ All required ports are available")
            
        return True
        
    def run_all_checks(self) -> bool:
        """Run all validation checks"""
        self.print_header("Pizza Store System Configuration Validator")
        
        checks = [
            ("Docker", self.check_docker),
            ("Directories", self.check_directories),
            ("Video Files", self.check_video_files),
            ("YOLO Model", self.check_model),
            ("ROI Configuration", self.check_roi_config),
            ("Docker Compose", self.check_docker_compose),
            ("Network Ports", self.check_ports)
        ]
        
        all_passed = True
        
        for name, check_func in checks:
            print(f"\nChecking {name}...")
            try:
                result = check_func()
                if not result and name not in ["YOLO Model", "Video Files", "Network Ports"]:
                    all_passed = False
            except Exception as e:
                self.errors.append(f"Check failed for {name}: {e}")
                all_passed = False
                
        # Print summary
        self.print_header("Validation Summary")
        
        if self.info:
            print("\n📋 Information:")
            for msg in self.info:
                print(f"  {msg}")
                
        if self.warnings:
            print("\n⚠️  Warnings:")
            for msg in self.warnings:
                print(f"  {msg}")
                
        if self.errors:
            print("\n❌ Errors:")
            for msg in self.errors:
                print(f"  {msg}")
                
        print("\n" + "=" * 60)
        
        if not self.errors:
            print("✅ System is ready to run!")
            print("\nNext steps:")
            print("1. Run: docker-compose up")
            print("2. Open: http://localhost:3000")
            return True
        else:
            print("❌ Please fix the errors above before running the system")
            return False
            

def main():
    """Main validation function"""
    validator = ConfigValidator()
    success = validator.run_all_checks()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nValidation failed with error: {e}")
        sys.exit(1)