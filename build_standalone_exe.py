#!/usr/bin/env python3
"""
Build Standalone Format Converter Executable

This script builds a complete standalone .exe file that includes:
- GUI window with drag-and-drop support
- All conversion tools
- All required libraries
- No Python installation needed to run

Usage:
    python build_standalone_exe.py

Output:
    dist/FormatConverter.exe - Ready to distribute!
"""

import subprocess
import sys
from pathlib import Path
import os

def install_requirements():
    """Install all required packages."""
    print("Installing required packages...")
    
    packages = [
        "pyinstaller",
        "h5py",
        "numpy",
        "tifffile",
        "zarr",
        "numcodecs",
        "scipy",
        "tkinterdnd2",
        "aicsimageio",
        "pillow",
        "openslide-python"  # Explicitly install OpenSlide
    ]
    
    for package in packages:
        print(f"  Installing {package}...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True
        )
    
    print("✓ All packages installed\n")

def find_openslide_dlls():
    """Find all OpenSlide DLLs in the system."""
    print("\nSearching for OpenSlide DLLs...")
    dlls_found = []
    
    # Method 1: Check openslide package
    try:
        import openslide
        openslide_path = Path(openslide.__file__).parent
        print(f"  OpenSlide package location: {openslide_path}")
        
        for dll in openslide_path.rglob('*.dll'):
            dlls_found.append(dll)
            print(f"  Found: {dll.name}")
    except Exception as e:
        print(f"  Could not import openslide: {e}")
    
    # Method 2: Check site-packages
    try:
        import site
        for site_path in site.getsitepackages():
            openslide_dir = Path(site_path) / 'openslide'
            if openslide_dir.exists():
                for dll in openslide_dir.rglob('*.dll'):
                    if dll not in dlls_found:
                        dlls_found.append(dll)
                        print(f"  Found: {dll.name}")
    except Exception as e:
        print(f"  Could not search site-packages: {e}")
    
    # Method 3: Check common locations
    common_paths = [
        Path("C:/Program Files/OpenSlide"),
        Path("C:/Program Files (x86)/OpenSlide"),
        Path.home() / "AppData" / "Local" / "Programs" / "OpenSlide"
    ]
    
    for path in common_paths:
        if path.exists():
            for dll in path.rglob('*.dll'):
                if dll not in dlls_found:
                    dlls_found.append(dll)
                    print(f"  Found: {dll.name}")
    
    print(f"\n✓ Found {len(dlls_found)} DLL(s)")
    return dlls_found

def copy_openslide_dlls():
    """Copy OpenSlide DLLs to tools directory for packaging."""
    print("\nPreparing OpenSlide DLLs...")
    
    tools_dir = Path(__file__).parent
    dll_dir = tools_dir / "_openslide_dlls"
    dll_dir.mkdir(exist_ok=True)
    
    dlls = find_openslide_dlls()
    
    if not dlls:
        print("\n⚠ WARNING: No OpenSlide DLLs found!")
        print("  VSI file conversion may not work in the executable.")
        print("  You can manually download OpenSlide from:")
        print("  https://openslide.org/download/")
        return dll_dir
    
    print(f"\nCopying DLLs to {dll_dir}...")
    for dll in dlls:
        dest = dll_dir / dll.name
        if not dest.exists():
            import shutil
            shutil.copy2(dll, dest)
            print(f"  Copied: {dll.name}")
    
    print(f"✓ DLLs ready in {dll_dir}\n")
    return dll_dir

def create_spec_file(dll_dir):
    """Create PyInstaller spec file for better control."""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
import os

block_cipher = None

# Get the tools directory
tools_dir = Path(SPECPATH)

# Data files to include
datas = [
    (str(tools_dir / 'univ_to_ometiff.py'), '.'),
    (str(tools_dir / 'univ_to_omezarr.py'), '.'),
    (str(tools_dir / 'ometiff_to_univ.py'), '.'),
    (str(tools_dir / 'omezarr_to_univ.py'), '.'),
    (str(tools_dir / 'vsi_to_univ.py'), '.'),
    (str(tools_dir / 'univ_to_vsi_compatible.py'), '.'),
    (str(tools_dir / 'validate_univ.py'), '.'),
]

# Binary files to include (DLLs)
binaries = []

# Include OpenSlide DLLs from prepared directory
dll_dir = tools_dir / '_openslide_dlls'
if dll_dir.exists():
    for dll in dll_dir.glob('*.dll'):
        binaries.append((str(dll), '.'))
        print("Including DLL: " + dll.name)

# Also try to find OpenSlide DLLs via package
try:
    import openslide
    openslide_path = Path(openslide.__file__).parent
    
    # Look for OpenSlide DLLs
    dll_patterns = ['libopenslide*.dll', 'openslide*.dll']
    for pattern in dll_patterns:
        for dll in openslide_path.rglob(pattern):
            dll_str = str(dll)
            if dll_str not in [b[0] for b in binaries]:
                binaries.append((dll_str, '.'))
                print("Found OpenSlide DLL via package: " + dll.name)
    
    # Check parent directories
    for parent in [openslide_path.parent, openslide_path.parent.parent]:
        for pattern in dll_patterns:
            for dll in parent.glob(pattern):
                dll_str = str(dll)
                if dll_str not in [b[0] for b in binaries]:
                    binaries.append((dll_str, '.'))
                    print("Found OpenSlide DLL: " + dll.name)
except Exception as e:
    print("Warning: Could not locate OpenSlide via package: " + str(e))

# Try site-packages
try:
    import site
    for site_path in site.getsitepackages():
        site_path = Path(site_path)
        
        # Check for openslide-win64 or similar packages
        for subdir in ['openslide', 'openslide-win64', 'Lib/site-packages/openslide']:
            openslide_pkg = site_path / subdir
            if openslide_pkg.exists():
                for dll in openslide_pkg.rglob('*.dll'):
                    dll_str = str(dll)
                    if dll_str not in [b[0] for b in binaries]:
                        binaries.append((dll_str, '.'))
                        print("Found DLL in " + subdir + ": " + dll.name)
except Exception as e:
    print("Warning: Could not search site-packages: " + str(e))

if not binaries:
    print("\\nWARNING: No OpenSlide DLLs found! VSI conversion may not work.")
else:
    print("\\nTotal binaries to include: " + str(len(binaries)))

# Hidden imports
hiddenimports = [
    'h5py',
    'h5py.defs',
    'h5py.utils',
    'h5py._proxy',
    'numpy',
    'tifffile',
    'zarr',
    'numcodecs',
    'scipy',
    'scipy.ndimage',
    'tkinter',
    'tkinter.ttk',
    'tkinterdnd2',
    'PIL',
    'PIL.Image',
    'aicsimageio',
    'threading',
    'queue',
]

a = Analysis(
    [str(tools_dir / 'format_converter_gui.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FormatConverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
    
    spec_path = Path(__file__).parent / "FormatConverter.spec"
    spec_path.write_text(spec_content)
    print(f"✓ Created spec file: {spec_path}\n")
    return spec_path

def build_exe(spec_file):
    """Build the executable using PyInstaller."""
    print("Building executable with PyInstaller...")
    print("This may take a few minutes...\n")
    
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_file)
    ]
    
    print(f"Running: {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd, cwd=spec_file.parent)
    
    return result.returncode == 0

def main():
    """Main build process."""
    print("="*70)
    print("STANDALONE FORMAT CONVERTER BUILDER")
    print("="*70)
    print()
    
    # Step 1: Install requirements
    print("Step 1: Installing requirements")
    print("-"*70)
    install_requirements()
    
    # Step 2: Prepare OpenSlide DLLs
    print("Step 2: Preparing OpenSlide DLLs")
    print("-"*70)
    dll_dir = copy_openslide_dlls()
    
    # Step 3: Create spec file
    print("Step 3: Creating PyInstaller spec file")
    print("-"*70)
    spec_file = create_spec_file(dll_dir)
    
    # Step 4: Build executable
    print("Step 4: Building executable")
    print("-"*70)
    success = build_exe(spec_file)
    
    # Step 5: Check result
    print()
    print("="*70)
    
    if success:
        exe_path = Path(__file__).parent / "dist" / "FormatConverter.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024**2)
            print("✓ BUILD SUCCESSFUL!")
            print("="*70)
            print()
            print(f"Executable: {exe_path}")
            print(f"Size: {size_mb:.1f} MB")
            print()
            print("READY TO USE:")
            print("  1. Double-click FormatConverter.exe to run")
            print("  2. A GUI window will open")
            print("  3. Drag and drop files to convert")
            print("  4. Select output format")
            print("  5. Click Convert!")
            print()
            print("The .exe is completely standalone - share it with anyone!")
            print("No Python installation needed to run it.")
            print()
            return 0
        else:
            print("✗ BUILD FAILED - Executable not found")
            return 1
    else:
        print("✗ BUILD FAILED")
        print()
        print("Check the output above for errors.")
        print("Common issues:")
        print("  - Missing dependencies (run: pip install -r requirements.txt)")
        print("  - Insufficient disk space")
        print("  - Antivirus blocking PyInstaller")
        return 1

if __name__ == "__main__":
    sys.exit(main())
