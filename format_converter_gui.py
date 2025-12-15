"""
Universal Microscopy Format Converter - GUI

Standalone GUI application for converting between .univ, OME-TIFF, and OME-Zarr formats.
Drag-and-drop files or browse to select, choose output format, and convert.

Usage:
    python format_converter_gui.py

Dependencies:
    pip install h5py numpy tifffile zarr numcodecs scipy
    pip install tkinterdnd2  # Optional, for drag-and-drop support
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
import sys
import os
from typing import Optional
import json

# Add OpenSlide DLL directory to PATH (for development)
tools_dir = Path(__file__).parent
openslide_dll_dir = tools_dir / "_openslide" / "openslide-win64-20231011" / "bin"
if openslide_dll_dir.exists():
    os.add_dll_directory(str(openslide_dll_dir))
    os.environ['PATH'] = str(openslide_dll_dir) + os.pathsep + os.environ.get('PATH', '')

# Try to import drag-and-drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False
    print("Note: Install tkinterdnd2 for drag-and-drop support: pip install tkinterdnd2")

# Import conversion modules (from tools directory)
sys.path.insert(0, str(Path(__file__).parent))
try:
    from univ_to_ometiff import UnivToOMETIFF
    from univ_to_omezarr import UnivToOMEZarr
    from ometiff_to_univ import OMETIFFToUniv
    from omezarr_to_univ import OMEZarrToUniv
    from vsi_to_univ import VSIToUniv
    from univ_to_vsi_compatible import UnivToVSICompatible
    from validate_univ import UnivValidator
except ImportError as e:
    print(f"Error: Conversion tools not found: {e}")
    print("Make sure this script is in the tools/ directory.")
    sys.exit(1)


class FormatConverterGUI:
    """GUI application for format conversion."""
    
    def __init__(self, root):
        """Initialize the GUI."""
        self.root = root
        self.root.title("Integrator - Universal Format Converter")
        self.root.geometry("900x900")
        self.root.minsize(800, 800)
        self.root.resizable(True, True)
        
        # Variables
        self.input_file = tk.StringVar()
        self.output_format = tk.StringVar(value="univ")
        self.create_pyramid = tk.BooleanVar(value=True)
        self.compression = tk.StringVar(value="none")
        self.compression_level = tk.IntVar(value=4)
        self.is_converting = False
        self.file_queue = []  # List of files to convert
        
        # Setup UI
        self._create_widgets()
        
        # Setup drag-and-drop if available
        if HAS_DND:
            self._setup_drag_drop()
    
    def _create_widgets(self):
        """Create all UI widgets."""
        # Main container
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        # Title
        title_label = ttk.Label(
            main_frame,
            text="Integrator",
            font=("Arial", 20, "bold")
        )
        title_label.grid(row=0, column=0, pady=(0, 5))
        
        subtitle_label = ttk.Label(
            main_frame,
            text="Universal Microscopy Format Converter",
            font=("Arial", 12)
        )
        subtitle_label.grid(row=1, column=0, pady=(0, 5))
        
        format_label = ttk.Label(
            main_frame,
            text="Convert between .univ, OME-TIFF, OME-Zarr, and VSI formats",
            font=("Arial", 10)
        )
        format_label.grid(row=2, column=0, pady=(0, 20))
        
        # Input file section
        input_frame = ttk.LabelFrame(main_frame, text="Input File", padding="10")
        input_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)
        
        # Drag-drop area or file entry
        if HAS_DND:
            self.drop_label = ttk.Label(
                input_frame,
                text="📁 Drag and drop file here\nor click Browse button below",
                relief="solid",
                borderwidth=2,
                padding=40,
                anchor="center",
                background="#f0f0f0"
            )
            self.drop_label.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # File list display
        list_frame = ttk.Frame(input_frame)
        list_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        list_scroll = ttk.Scrollbar(list_frame)
        list_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        self.file_listbox = tk.Listbox(
            list_frame,
            height=4,
            yscrollcommand=list_scroll.set
        )
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_scroll.config(command=self.file_listbox.yview)
        
        # Button row
        btn_frame = ttk.Frame(input_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 0))
        
        browse_btn = ttk.Button(btn_frame, text="Add Files...", command=self._browse_files)
        browse_btn.grid(row=0, column=0, padx=(0, 5))
        
        browse_folder_btn = ttk.Button(btn_frame, text="Add Folder...", command=self._browse_folder)
        browse_folder_btn.grid(row=0, column=1, padx=(0, 5))
        
        clear_btn = ttk.Button(btn_frame, text="Clear List", command=self._clear_file_list)
        clear_btn.grid(row=0, column=2)
        
        # Output format section
        format_frame = ttk.LabelFrame(main_frame, text="Output Format", padding="10")
        format_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        formats = [
            (".univ (Universal)", "univ", "Single file, self-describing, complete metadata"),
            ("OME-TIFF", "ome-tiff", "Compatible with vendor software (ZEN, LAS X)"),
            ("OME-Zarr", "ome-zarr", "Cloud-native, for napari and modern tools"),
            ("VSI-compatible (OME-TIFF)", "vsi", "For Olympus cellSens/OlyVIA viewers")
        ]
        
        for i, (label, value, desc) in enumerate(formats):
            rb = ttk.Radiobutton(
                format_frame,
                text=label,
                variable=self.output_format,
                value=value
            )
            rb.grid(row=i, column=0, sticky=tk.W, pady=2)
            
            desc_label = ttk.Label(format_frame, text=f"  → {desc}", foreground="gray")
            desc_label.grid(row=i, column=1, sticky=tk.W, padx=(10, 0))
        
        # Options section
        options_frame = ttk.LabelFrame(main_frame, text="Options", padding="10")
        options_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Pyramid option
        pyramid_cb = ttk.Checkbutton(
            options_frame,
            text="Create multi-resolution pyramid (recommended for images > 2048×2048)",
            variable=self.create_pyramid
        )
        pyramid_cb.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Resolution level selection (for VSI pyramid)
        ttk.Label(options_frame, text="VSI Resolution:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        self.vsi_resolution = tk.StringVar(value="Highest (auto)")
        self.vsi_resolution_combo = ttk.Combobox(
            options_frame,
            textvariable=self.vsi_resolution,
            values=["Highest (auto)"],
            state="readonly",
            width=30
        )
        self.vsi_resolution_combo.grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=5)
        
        # Compression options
        ttk.Label(options_frame, text="Compression:").grid(row=2, column=0, sticky=tk.W, pady=5)
        
        compression_combo = ttk.Combobox(
            options_frame,
            textvariable=self.compression,
            values=["none", "gzip", "lzf", "blosc", "jpeg", "lzw"],
            state="readonly",
            width=15
        )
        compression_combo.grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=5)
        
        self.level_label = ttk.Label(options_frame, text="Level (1-9):")
        self.level_label.grid(row=3, column=0, sticky=tk.W, pady=5)
        
        self.level_spin = ttk.Spinbox(
            options_frame,
            from_=1,
            to=9,
            textvariable=self.compression_level,
            width=15
        )
        self.level_spin.grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=5)
        
        # Update level spin state based on compression
        def update_level_state(*args):
            if self.compression.get() == "none":
                self.level_spin.configure(state="disabled")
                self.level_label.configure(foreground="gray")
            else:
                self.level_spin.configure(state="normal")
                self.level_label.configure(foreground="black")
        
        self.compression.trace_add("write", update_level_state)
        update_level_state()  # Initialize state
        
        # Convert button
        self.convert_btn = ttk.Button(
            main_frame,
            text="🔄 Convert",
            command=self._start_conversion,
            style="Accent.TButton"
        )
        self.convert_btn.grid(row=6, column=0, pady=10)
        
        # Progress section
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=7, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)
        
        self.progress = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        self.status_label = ttk.Label(progress_frame, text="Ready", foreground="gray")
        self.status_label.grid(row=1, column=0, pady=(5, 0))
        
        # Log section
        log_frame = ttk.LabelFrame(main_frame, text="Log", padding="10")
        log_frame.grid(row=8, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        main_frame.rowconfigure(8, weight=1)
        
        # Log text with scrollbar
        log_scroll = ttk.Scrollbar(log_frame)
        log_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        self.log_text = tk.Text(
            log_frame,
            height=10,
            wrap=tk.WORD,
            yscrollcommand=log_scroll.set
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_scroll.config(command=self.log_text.yview)
        
        # Buttons at bottom
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=9, column=0, pady=(10, 0))
        
        clear_log_btn = ttk.Button(button_frame, text="Clear Log", command=self._clear_log)
        clear_log_btn.grid(row=0, column=0, padx=5)
        
        validate_btn = ttk.Button(button_frame, text="Validate .univ File", command=self._validate_file)
        validate_btn.grid(row=0, column=1, padx=5)
        
        about_btn = ttk.Button(button_frame, text="About", command=self._show_about)
        about_btn.grid(row=0, column=2, padx=5)
    
    def _setup_drag_drop(self):
        """Setup drag-and-drop functionality."""
        if not HAS_DND:
            return
        
        # Make root a TkinterDnD window
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self._on_drop)
        
        # Make drop label accept drops
        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind('<<Drop>>', self._on_drop)
        
        # Visual feedback on hover
        def on_enter(event):
            self.drop_label.configure(background="#e0e0ff")
        
        def on_leave(event):
            self.drop_label.configure(background="#f0f0f0")
        
        self.drop_label.bind('<Enter>', on_enter)
        self.drop_label.bind('<Leave>', on_leave)
    
    def _on_drop(self, event):
        """Handle file/folder drop - supports multiple files and folders."""
        items = self.root.tk.splitlist(event.data)
        added_count = 0
        
        for item in items:
            item_path = Path(item.strip('{}'))  # Remove curly braces if present
            
            if item_path.is_file():
                # Add single file
                if self._is_supported_file(item_path):
                    if str(item_path) not in self.file_queue:
                        self.file_queue.append(str(item_path))
                        self.file_listbox.insert(tk.END, item_path.name)
                        added_count += 1
            elif item_path.is_dir():
                # Scan folder for supported files
                found_files = self._scan_folder_for_files(item_path)
                for file_path in found_files:
                    if str(file_path) not in self.file_queue:
                        self.file_queue.append(str(file_path))
                        self.file_listbox.insert(tk.END, file_path.name)
                        added_count += 1
        
        if added_count > 0:
            self._log(f"Added {added_count} file(s) to queue")
            self._analyze_vsi_resolutions()
        else:
            self._log("No supported files found in dropped items")
    
    def _is_supported_file(self, file_path: Path) -> bool:
        """Check if file is a supported format."""
        supported_extensions = {'.univ', '.vsi', '.tif', '.tiff', '.zarr'}
        if file_path.suffix.lower() in supported_extensions:
            return True
        # Check for .ome.tif / .ome.tiff
        if file_path.name.lower().endswith(('.ome.tif', '.ome.tiff')):
            return True
        return False
    
    def _scan_folder_for_files(self, folder_path: Path) -> list:
        """Recursively scan folder for supported files."""
        supported_files = []
        
        # Scan recursively
        for item in folder_path.rglob('*'):
            if item.is_file() and self._is_supported_file(item):
                supported_files.append(item)
        
        return supported_files
    
    def _browse_files(self):
        """Browse for multiple input files."""
        filenames = filedialog.askopenfilenames(
            title="Select files to convert",
            filetypes=[
                ("All supported formats", "*.univ *.ome.tif *.ome.tiff *.zarr *.vsi"),
                ("UNIV files", "*.univ"),
                ("OME-TIFF files", "*.ome.tif *.ome.tiff"),
                ("OME-Zarr", "*.zarr"),
                ("VSI files", "*.vsi"),
                ("All files", "*.*")
            ]
        )
        
        added_count = 0
        for filename in filenames:
            file_path = Path(filename)
            if str(file_path) not in self.file_queue:
                self.file_queue.append(str(file_path))
                self.file_listbox.insert(tk.END, file_path.name)
                added_count += 1
        
        if added_count > 0:
            self._log(f"Added {added_count} file(s) to queue")
    
    def _browse_folder(self):
        """Browse for a folder containing files to convert."""
        folder = filedialog.askdirectory(
            title="Select folder containing files to convert"
        )
        
        if folder:
            folder_path = Path(folder)
            found_files = self._scan_folder_for_files(folder_path)
            
            added_count = 0
            for file_path in found_files:
                if str(file_path) not in self.file_queue:
                    self.file_queue.append(str(file_path))
                    self.file_listbox.insert(tk.END, file_path.name)
                    added_count += 1
            
            if added_count > 0:
                self._log(f"Found and added {added_count} file(s) from {folder_path.name}")
            else:
                self._log(f"No supported files found in {folder_path.name}")
                messagebox.showinfo("No Files", f"No supported files found in:\n{folder}")
    
    def _clear_file_list(self):
        """Clear the file queue."""
        self.file_queue.clear()
        self.file_listbox.delete(0, tk.END)
        self._log("File queue cleared")
        self.vsi_resolution_combo['values'] = ["Highest (auto)"]
        self.vsi_resolution.set("Highest (auto)")
    
    def _analyze_vsi_resolutions(self):
        """Analyze VSI files in queue and populate resolution options grouped by series."""
        # Check if we have any VSI files
        vsi_files = [f for f in self.file_queue if f.lower().endswith('.vsi')]
        
        if not vsi_files:
            self.vsi_resolution_combo['values'] = ["Highest (auto)"]
            self.vsi_resolution.set("Highest (auto)")
            return
        
        # Analyze the first VSI file to get available resolutions
        try:
            from aicsimageio import AICSImage
            import re
            vsi_file = vsi_files[0]
            
            self._log(f"Analyzing VSI resolutions for: {Path(vsi_file).name}")
            img = AICSImage(vsi_file)
            
            if hasattr(img, 'scenes') and len(img.scenes) > 1:
                # Categorize scenes into series
                labels = []
                macros = []
                overviews = []
                main_images = []
                
                for i, scene_name in enumerate(img.scenes):
                    img.set_scene(scene_name)
                    width = img.shape[-1]
                    height = img.shape[-2]
                    size = width * height
                    
                    scene_lower = scene_name.lower()
                    
                    # Categorize by name
                    if "label" in scene_lower:
                        labels.append((i, scene_name, width, height, size))
                    elif "macro" in scene_lower:
                        macros.append((i, scene_name, width, height, size))
                    elif "overview" in scene_lower:
                        overviews.append((i, scene_name, width, height, size))
                    else:
                        # Main image scenes - look for named scenes vs generic pyramid levels
                        # Named scenes like "20x_BF_01" vs generic like "Image.vsi #2"
                        if re.match(r'.+\s+#\d+$', scene_name):
                            # Generic pyramid level name - likely belongs to nearest named scene
                            main_images.append((i, scene_name, width, height, size, "pyramid"))
                        else:
                            # Named scene - main image
                            main_images.append((i, scene_name, width, height, size, "main"))
                
                # Sort each category by size (largest first)
                labels.sort(key=lambda x: x[4], reverse=True)
                macros.sort(key=lambda x: x[4], reverse=True)
                overviews.sort(key=lambda x: x[4], reverse=True)
                
                # For main images, group by named scenes and their pyramids
                main_named = [x for x in main_images if x[5] == "main"]
                main_pyramid = [x for x in main_images if x[5] == "pyramid"]
                main_named.sort(key=lambda x: x[4], reverse=True)
                main_pyramid.sort(key=lambda x: x[4], reverse=True)
                
                # Build dropdown options grouped by series
                resolution_options = ["Highest image (auto)"]
                
                # Add main image series first
                if main_named:
                    resolution_options.append("─── MAIN IMAGES ───")
                    for idx, (scene_idx, name, w, h, size, _) in enumerate(main_named):
                        resolution_options.append(f"  Scene {scene_idx}: {name} - {w}×{h} px")
                
                if main_pyramid:
                    resolution_options.append("  └─ Pyramid Levels:")
                    for idx, (scene_idx, name, w, h, size, _) in enumerate(main_pyramid):
                        resolution_options.append(f"    Level {idx}: {w}×{h} px (scene {scene_idx})")
                
                # Add overview series
                if overviews:
                    resolution_options.append("─── OVERVIEW ───")
                    for idx, (scene_idx, name, w, h, size) in enumerate(overviews):
                        resolution_options.append(f"  Scene {scene_idx}: {name} - {w}×{h} px")
                
                # Add label series
                if labels:
                    resolution_options.append("─── LABELS ───")
                    for idx, (scene_idx, name, w, h, size) in enumerate(labels):
                        resolution_options.append(f"  Scene {scene_idx}: {name} - {w}×{h} px")
                
                # Add macro series
                if macros:
                    resolution_options.append("─── MACROS ───")
                    for idx, (scene_idx, name, w, h, size) in enumerate(macros):
                        resolution_options.append(f"  Scene {scene_idx}: {name} - {w}×{h} px")
                
                self.vsi_resolution_combo['values'] = resolution_options
                self.vsi_resolution.set("Highest image (auto)")
                total_scenes = len(labels) + len(macros) + len(overviews) + len(main_images)
                self._log(f"Found {total_scenes} scenes: {len(main_named + main_pyramid)} images, {len(labels)} labels, {len(macros)} macros, {len(overviews)} overviews")
            
        except Exception as e:
            self._log(f"Could not analyze VSI resolutions: {e}")
            import traceback
            self._log(traceback.format_exc())
    
    def _browse_input_orphaned(self):
        """ORPHANED METHOD - DO NOT USE."""
        if False:  # Disabled
            choice = None
        if choice == 'yes':
            # File selection
            filename = filedialog.askopenfilename(
                title="Select input file",
                filetypes=[
                    ("All supported formats", "*.univ *.ome.tif *.ome.tiff *.zarr *.vsi"),
                    ("UNIV files", "*.univ"),
                    ("OME-TIFF files", "*.ome.tif *.ome.tiff"),
                    ("OME-Zarr", "*.zarr"),
                    ("VSI files", "*.vsi"),
                    ("All files", "*.*")
                ]
            )
            if filename:
                self.input_file.set(filename)
                self._log(f"File selected: {Path(filename).name}")
                
                # Check for VSI data folder
                if filename.lower().endswith('.vsi'):
                    file_path = Path(filename)
                    stem = file_path.stem
                    parent = file_path.parent
                    
                    # Try _xyz_ format first (most common)
                    vsi_data = parent / f"_{stem}_"
                    if not vsi_data.exists():
                        vsi_data = file_path.with_suffix('.vsi_data')
                    
                    if vsi_data.exists():
                        self._log(f"✓ Found VSI data folder: {vsi_data.name}")
                    else:
                        self._log(f"⚠ WARNING: VSI data folder not found!")
                        self._log(f"  Expected: _{stem}_ or {stem}.vsi_data")
                        self._log(f"  VSI files require both .vsi file and data folder")
        else:
            # Folder selection (for VSI with data folder)
            folder = filedialog.askdirectory(
                title="Select folder containing VSI file and data folder"
            )
            if folder:
                folder_path = Path(folder)
                # Look for .vsi file in folder
                vsi_files = list(folder_path.glob("*.vsi"))
                if not vsi_files:
                    messagebox.showerror(
                        "No VSI File",
                        f"No .vsi file found in:\n{folder}\n\nPlease select a folder containing a .vsi file"
                    )
                    return
                
                if len(vsi_files) > 1:
                    # Multiple VSI files - let user choose
                    vsi_names = [f.name for f in vsi_files]
                    self._log(f"Found {len(vsi_files)} VSI files in folder")
                    # Use first one by default
                    selected_vsi = vsi_files[0]
                else:
                    selected_vsi = vsi_files[0]
                
                self.input_file.set(str(selected_vsi))
                self._log(f"VSI file selected: {selected_vsi.name}")
                
                # Check for data folder (try _xyz_ format first)
                stem = selected_vsi.stem
                vsi_data = folder_path / f"_{stem}_"
                if not vsi_data.exists():
                    vsi_data = selected_vsi.with_suffix('.vsi_data')
                
                if vsi_data.exists():
                    self._log(f"✓ Found VSI data folder: {vsi_data.name}")
                else:
                    self._log(f"⚠ WARNING: VSI data folder not found!")
                    self._log(f"  Expected: _{stem}_ or {stem}.vsi_data")
    
    def _select_vsi_scene(self, img):
        """Select appropriate VSI scene based on user preference."""
        if not hasattr(img, 'scenes') or len(img.scenes) <= 1:
            return  # Single scene, nothing to do
        
        self._log(f"\n📊 VSI contains {len(img.scenes)} scenes:")
        scene_sizes = []
        for i, scene_name in enumerate(img.scenes):
            img.set_scene(scene_name)
            size = img.shape[-2] * img.shape[-1]
            scene_sizes.append((i, scene_name, size, img.shape))
            scene_type = "label/macro" if "label" in scene_name.lower() or "macro" in scene_name.lower() else "image"
            self._log(f"  Scene {i}: {scene_name} ({scene_type}) - {img.shape[-1]}x{img.shape[-2]} px")
        
        # Filter to non-label/macro scenes and sort by size
        main_scenes = [(i, n, s, sh) for i, n, s, sh in scene_sizes if "label" not in n.lower() and "macro" not in n.lower()]
        if not main_scenes:
            main_scenes = scene_sizes
        main_scenes.sort(key=lambda x: x[2], reverse=True)  # Sort by size, largest first
        
        # Check user's resolution selection
        selected_resolution = self.vsi_resolution.get()
        if selected_resolution == "Highest image (auto)" or selected_resolution == "Highest (auto)":
            # Use largest scene (excluding labels/macros)
            main_scene_idx, main_scene_name, main_size, main_shape = main_scenes[0]
        else:
            # Parse the selection from grouped format
            # Formats: "  Scene X: name - WxH px" or "    Level X: WxH px (scene Y)"
            try:
                import re
                # Try to extract scene index from various formats
                scene_match = re.search(r'Scene (\d+):', selected_resolution)
                level_match = re.search(r'\(scene (\d+)\)', selected_resolution)
                
                target_scene_idx = None
                if scene_match:
                    target_scene_idx = int(scene_match.group(1))
                elif level_match:
                    target_scene_idx = int(level_match.group(1))
                
                if target_scene_idx is not None:
                    # Find the scene in our list
                    for scene_idx, name, size, shape in main_scenes:
                        if scene_idx == target_scene_idx:
                            main_scene_idx, main_scene_name, main_size, main_shape = scene_idx, name, size, shape
                            break
                    else:
                        # Not found in main_scenes, search all scenes
                        for i, scene_name in enumerate(img.scenes):
                            if i == target_scene_idx:
                                img.set_scene(scene_name)
                                main_scene_idx = i
                                main_scene_name = scene_name
                                main_size = img.shape[-2] * img.shape[-1]
                                main_shape = img.shape
                                break
                        else:
                            # Fall back to highest
                            main_scene_idx, main_scene_name, main_size, main_shape = main_scenes[0]
                else:
                    # Fall back to highest
                    main_scene_idx, main_scene_name, main_size, main_shape = main_scenes[0]
            except:
                # Fall back to highest
                main_scene_idx, main_scene_name, main_size, main_shape = main_scenes[0]
        
        self._log(f"\n🎯 SELECTING RESOLUTION: {selected_resolution}")
        self._log(f"   Scene {main_scene_idx}: {main_scene_name}")
        self._log(f"   Size: {main_shape[-1]}x{main_shape[-2]} pixels ({main_size/1_000_000:.1f} MP)\n")
        
        # Set the selected scene
        img.set_scene(main_scene_name)
        self._log(f"✓ Scene set to: {img.current_scene}")
    
    def _log(self, message: str):
        """Add message to log."""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def _clear_log(self):
        """Clear log text."""
        self.log_text.delete(1.0, tk.END)
    
    def _update_status(self, message: str, color: str = "gray"):
        """Update status label."""
        self.status_label.configure(text=message, foreground=color)
        self.root.update_idletasks()
    
    def _start_conversion(self):
        """Start conversion - batch or single file."""
        if self.is_converting:
            return
        
        # Check if we have files in the queue
        if len(self.file_queue) > 0:
            # Batch conversion
            self._start_batch_conversion()
        else:
            messagebox.showwarning(
                "No Files",
                "Please add files to convert:\n\n"
                "• Drag and drop files/folders\n"
                "• Click 'Add Files...' button\n"
                "• Click 'Add Folder...' button"
            )
    
    def _start_batch_conversion(self):
        """Start batch conversion with output folder/file selection."""
        output_format = self.output_format.get()
        
        # If only one file, allow custom filename
        if len(self.file_queue) == 1:
            input_path = Path(self.file_queue[0])
            
            # Determine default extension
            if output_format == "ome-zarr":
                ext = ".zarr"
                default_name = f"{input_path.stem}_converted{ext}"
            elif output_format == "ome-tiff":
                ext = ".ome.tif"
                default_name = f"{input_path.stem}_converted{ext}"
            elif output_format == "vsi":
                ext = ".ome.tif"
                default_name = f"{input_path.stem}_converted{ext}"
            else:
                ext = ".univ"
                default_name = f"{input_path.stem}_converted{ext}"
            
            # Ask for output file with custom name
            output_file = filedialog.asksaveasfilename(
                title="Save converted file as",
                defaultextension=ext,
                initialfile=default_name,
                filetypes=[
                    ("Output format", f"*{ext}"),
                    ("All files", "*.*")
                ]
            )
            
            if not output_file:
                return  # User cancelled
            
            output_path = Path(output_file)
            output_folder_path = output_path.parent
            
            # Store custom filename for batch processor
            self.custom_output_name = output_path.name
        else:
            # Multiple files - ask for output folder
            output_folder = filedialog.askdirectory(
                title="Select output folder for converted files"
            )
            
            if not output_folder:
                return  # User cancelled
            
            output_folder_path = Path(output_folder)
            self.custom_output_name = None
        
        # Disable button during conversion
        self.convert_btn.configure(state="disabled")
        self.is_converting = True
        self.progress.start()
        
        # Start batch conversion in thread
        thread = threading.Thread(
            target=self._convert_batch,
            args=(self.file_queue.copy(), output_folder_path, output_format),
            daemon=True
        )
        thread.start()
    
    def _convert_file(self, input_path: str, output_path: str, output_format: str):
        """Perform conversion (runs in background thread)."""
        try:
            self._update_status("Converting...", "blue")
            self._log(f"\n{'='*50}")
            self._log(f"Converting: {Path(input_path).name}")
            self._log(f"To: {Path(output_path).name}")
            self._log(f"Format: {output_format}")
            self._log(f"Pyramid: {self.create_pyramid.get()}")
            self._log(f"Compression: {self.compression.get()}")
            self._log(f"{'='*50}\n")
            
            input_path_obj = Path(input_path)
            
            # Determine conversion type
            if input_path_obj.suffix == ".univ":
                # .univ to something else
                if output_format == "ome-tiff":
                    self._convert_univ_to_ometiff(input_path, output_path)
                elif output_format == "ome-zarr":
                    self._convert_univ_to_omezarr(input_path, output_path)
                else:
                    raise ValueError("Cannot convert .univ to .univ")
            
            elif input_path_obj.suffix in [".tif", ".tiff"] or ".ome" in input_path_obj.name:
                # OME-TIFF to something else
                # Ensure output directory exists
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                
                if output_format == "univ":
                    self._convert_ometiff_to_univ(input_path, output_path)
                elif output_format == "ome-zarr":
                    # Two-step: TIFF -> univ -> zarr
                    self._log("Note: Converting via intermediate .univ file")
                    temp_univ = Path(output_path).with_suffix('.temp.univ')
                    self._convert_ometiff_to_univ(input_path, str(temp_univ))
                    self._convert_univ_to_omezarr(str(temp_univ), output_path)
                    if temp_univ.exists():
                        temp_univ.unlink()
                else:
                    raise ValueError("Cannot convert OME-TIFF to OME-TIFF")
            
            elif input_path_obj.suffix == ".zarr" or input_path_obj.is_dir():
                # OME-Zarr to something else
                # Ensure output directory exists
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                
                if output_format == "univ":
                    self._convert_omezarr_to_univ(input_path, output_path)
                elif output_format == "ome-tiff":
                    # Two-step: zarr -> univ -> tiff
                    self._log("Note: Converting via intermediate .univ file")
                    temp_univ = Path(output_path).with_suffix('.temp.univ')
                    self._convert_omezarr_to_univ(input_path, str(temp_univ))
                    self._convert_univ_to_ometiff(str(temp_univ), output_path)
                    if temp_univ.exists():
                        temp_univ.unlink()
                elif output_format == "vsi":
                    # Two-step: zarr -> univ -> vsi-compatible
                    self._log("Note: Converting via intermediate .univ file")
                    temp_univ = Path(output_path).with_suffix('.temp.univ')
                    self._convert_omezarr_to_univ(input_path, str(temp_univ))
                    self._convert_univ_to_vsi(str(temp_univ), output_path)
                    if temp_univ.exists():
                        temp_univ.unlink()
                else:
                    raise ValueError("Cannot convert OME-Zarr to OME-Zarr")
            
            elif input_path_obj.suffix == ".vsi":
                # VSI to something else
                # Ensure output directory exists
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                
                if output_format == "univ":
                    self._convert_vsi_to_univ(input_path, output_path)
                elif output_format == "ome-tiff":
                    # Direct conversion: vsi -> ome-tiff
                    self._convert_vsi_to_ometiff(input_path, output_path)
                elif output_format == "ome-zarr":
                    # Direct conversion: vsi -> zarr
                    self._convert_vsi_to_omezarr(input_path, output_path)
                else:
                    raise ValueError("Cannot convert VSI to VSI")
            
            else:
                raise ValueError(f"Unknown input format: {input_path_obj.suffix}")
            
            # Validate output was created
            output_path_obj = Path(output_path)
            if not output_path_obj.exists():
                raise RuntimeError(f"Conversion failed: Output file was not created at {output_path}")
            
            # Calculate output size
            output_size = 0
            if output_format == "ome-zarr":
                # Calculate directory size
                if output_path_obj.is_dir():
                    output_size = sum(f.stat().st_size for f in output_path_obj.rglob('*') if f.is_file())
                else:
                    raise RuntimeError(f"OME-Zarr output should be a directory, but got: {output_path}")
            else:
                # Single file
                output_size = output_path_obj.stat().st_size
            
            # Check if file is too small
            if output_size < 1024:  # Less than 1 KB is suspicious
                raise RuntimeError(f"Conversion may have failed: Output file is only {output_size} bytes")
            
            # Success
            self._log(f"\n✅ Conversion complete!")
            self._log(f"Output: {output_path}")
            self._log(f"Size: {output_size / 1024**2:.1f} MB")
            
            self._update_status("✅ Complete!", "green")
            
            messagebox.showinfo(
                "Success",
                f"Conversion complete!\n\nOutput: {Path(output_path).name}\nSize: {output_size / 1024**2:.1f} MB"
            )
        
        except Exception as e:
            self._log(f"\n❌ Error: {str(e)}")
            self._update_status("❌ Error", "red")
            messagebox.showerror("Conversion Error", f"Error during conversion:\n\n{str(e)}")
            import traceback
            self._log(traceback.format_exc())
        
        finally:
            # Re-enable button
            self.progress.stop()
            self.convert_btn.configure(state="normal")
            self.is_converting = False
    
    def _convert_batch(self, file_list: list, output_folder: Path, output_format: str):
        """Convert multiple files in batch."""
        total_files = len(file_list)
        successful = 0
        failed = 0
        
        self._log(f"\n{'='*50}")
        self._log(f"BATCH CONVERSION")
        self._log(f"Total files: {total_files}")
        self._log(f"Output folder: {output_folder}")
        self._log(f"Output format: {output_format}")
        self._log(f"{'='*50}\n")
        
        for i, input_path in enumerate(file_list, 1):
            try:
                input_path_obj = Path(input_path)
                
                # Use custom output name if specified (single file mode)
                if hasattr(self, 'custom_output_name') and self.custom_output_name and total_files == 1:
                    output_path = output_folder / self.custom_output_name
                else:
                    # Determine output extension
                    if output_format == "ome-zarr":
                        ext = ".zarr"
                    elif output_format == "ome-tiff":
                        ext = ".ome.tif"
                    elif output_format == "vsi":
                        ext = ".ome.tif"
                    else:
                        ext = ".univ"
                    
                    # Create output path with original filename + suffix
                    base_name = f"{input_path_obj.stem}_converted"
                    output_path = output_folder / f"{base_name}{ext}"
                    
                    # If file already exists, add counter to avoid overwriting
                    if output_path.exists():
                        counter = 1
                        while output_path.exists():
                            output_path = output_folder / f"{base_name}_{counter}{ext}"
                            counter += 1
                
                self._log(f"\n[{i}/{total_files}] Converting: {input_path_obj.name}")
                self._log(f"  Output: {output_path.name}")
                
                # Update status
                self._update_status(f"Converting {i}/{total_files}...", "blue")
                
                # Perform conversion
                input_path_obj = Path(input_path)
                
                # Determine conversion type
                if input_path_obj.suffix == ".univ":
                    if output_format == "ome-tiff":
                        self._convert_univ_to_ometiff(input_path, str(output_path))
                    elif output_format == "ome-zarr":
                        self._convert_univ_to_omezarr(input_path, str(output_path))
                
                elif input_path_obj.suffix in [".tif", ".tiff"] or ".ome" in input_path_obj.name:
                    if output_format == "univ":
                        self._convert_ometiff_to_univ(input_path, str(output_path))
                    elif output_format == "ome-zarr":
                        temp_univ = output_path.with_suffix('.temp.univ')
                        self._convert_ometiff_to_univ(input_path, str(temp_univ))
                        self._convert_univ_to_omezarr(str(temp_univ), str(output_path))
                        if temp_univ.exists():
                            temp_univ.unlink()
                
                elif input_path_obj.suffix == ".zarr" or input_path_obj.is_dir():
                    if output_format == "univ":
                        self._convert_omezarr_to_univ(input_path, str(output_path))
                    elif output_format == "ome-tiff":
                        temp_univ = output_path.with_suffix('.temp.univ')
                        self._convert_omezarr_to_univ(input_path, str(temp_univ))
                        self._convert_univ_to_ometiff(str(temp_univ), str(output_path))
                        if temp_univ.exists():
                            temp_univ.unlink()
                
                elif input_path_obj.suffix == ".vsi":
                    if output_format == "univ":
                        self._convert_vsi_to_univ(input_path, str(output_path))
                    elif output_format == "ome-tiff":
                        self._convert_vsi_to_ometiff(input_path, str(output_path))
                    elif output_format == "ome-zarr":
                        self._convert_vsi_to_omezarr(input_path, str(output_path))
                
                self._log(f"  ✅ Success!")
                successful += 1
                
            except Exception as e:
                self._log(f"  ❌ Failed: {str(e)}")
                import traceback
                self._log(f"  Full error traceback:")
                self._log(traceback.format_exc())
                failed += 1
        
        # Summary
        self._log(f"\n{'='*50}")
        self._log(f"BATCH CONVERSION COMPLETE")
        self._log(f"{'='*50}")
        self._log(f"Total: {total_files}")
        self._log(f"Successful: {successful}")
        self._log(f"Failed: {failed}")
        self._log(f"{'='*50}\n")
        
        self._update_status(f"✅ Batch complete: {successful}/{total_files}", "green")
        
        messagebox.showinfo(
            "Batch Conversion Complete",
            f"Converted {successful} of {total_files} file(s)\n\n"
            f"Successful: {successful}\n"
            f"Failed: {failed}\n\n"
            f"Output folder: {output_folder}"
        )
        
        # Re-enable button
        self.progress.stop()
        self.convert_btn.configure(state="normal")
        self.is_converting = False
    
    def _convert_univ_to_ometiff(self, input_path: str, output_path: str):
        """Convert .univ to OME-TIFF."""
        with UnivToOMETIFF(input_path) as converter:
            # Redirect output to log
            original_print = print
            def log_print(*args, **kwargs):
                message = ' '.join(str(arg) for arg in args)
                self._log(message)
            
            import builtins
            builtins.print = log_print
            
            try:
                # Ensure output directory exists
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                
                result = converter.convert(
                    output_path,
                    include_pyramid=self.create_pyramid.get(),
                    compression=self.compression.get(),
                    jpeg_quality=90,
                    bigtiff=True
                )
                
                if result is False:
                    raise RuntimeError(".univ to OME-TIFF conversion returned False - conversion failed")
            finally:
                builtins.print = original_print
    
    def _convert_univ_to_omezarr(self, input_path: str, output_path: str):
        """Convert .univ to OME-Zarr."""
        with UnivToOMEZarr(input_path) as converter:
            original_print = print
            def log_print(*args, **kwargs):
                message = ' '.join(str(arg) for arg in args)
                self._log(message)
            
            import builtins
            builtins.print = log_print
            
            try:
                # Ensure output directory exists
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                
                result = converter.convert(
                    output_path,
                    include_pyramid=self.create_pyramid.get(),
                    compressor=self.compression.get()
                )
                
                if result is False:
                    raise RuntimeError(".univ to OME-Zarr conversion returned False - conversion failed")
            finally:
                builtins.print = original_print
    
    def _convert_ometiff_to_univ(self, input_path: str, output_path: str):
        """Convert OME-TIFF to .univ."""
        with OMETIFFToUniv(input_path) as converter:
            original_print = print
            def log_print(*args, **kwargs):
                message = ' '.join(str(arg) for arg in args)
                self._log(message)
            
            import builtins
            builtins.print = log_print
            
            try:
                # Ensure output directory exists
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                
                result = converter.convert(
                    output_path,
                    create_pyramid=self.create_pyramid.get(),
                    compression=self.compression.get(),
                    compression_level=self.compression_level.get()
                )
                
                if result is False:
                    raise RuntimeError("OME-TIFF to .univ conversion returned False - conversion failed")
            finally:
                builtins.print = original_print
    
    def _convert_omezarr_to_univ(self, input_path: str, output_path: str):
        """Convert OME-Zarr to .univ."""
        with OMEZarrToUniv(input_path) as converter:
            original_print = print
            def log_print(*args, **kwargs):
                message = ' '.join(str(arg) for arg in args)
                self._log(message)
            
            import builtins
            builtins.print = log_print
            
            try:
                # Ensure output directory exists
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                
                result = converter.convert(
                    output_path,
                    include_pyramid=self.create_pyramid.get(),
                    compression=self.compression.get(),
                    compression_level=self.compression_level.get()
                )
                
                if result is False:
                    raise RuntimeError("OME-Zarr to .univ conversion returned False - conversion failed")
            finally:
                builtins.print = original_print
    
    def _convert_vsi_to_univ(self, input_path: str, output_path: str):
        """Convert VSI to .univ."""
        import logging
        import io
        
        # Create custom handler to redirect logging to GUI
        class GUILogHandler(logging.Handler):
            def __init__(self, log_func):
                super().__init__()
                self.log_func = log_func
            
            def emit(self, record):
                msg = self.format(record)
                self.log_func(msg)
        
        # Set up logging redirection
        log_handler = GUILogHandler(self._log)
        log_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(message)s')
        log_handler.setFormatter(formatter)
        
        # Get the vsi_to_univ logger
        vsi_logger = logging.getLogger('__main__')
        vsi_logger.addHandler(log_handler)
        vsi_logger.setLevel(logging.INFO)
        
        original_print = print
        def log_print(*args, **kwargs):
            message = ' '.join(str(arg) for arg in args)
            self._log(message)
        
        import builtins
        builtins.print = log_print
        
        try:
            # Ensure output directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Check if VSI file exists
            if not Path(input_path).exists():
                raise FileNotFoundError(f"VSI file not found: {input_path}")
            
            # Check for VSI data folder
            data_folder = Path(input_path).with_suffix('.vsi_data')
            if not data_folder.exists():
                self._log(f"⚠ Warning: VSI data folder not found: {data_folder}")
                self._log("  This may cause the conversion to fail")
            
            converter = VSIToUniv()
            
            self._log(f"Starting VSI conversion...")
            self._log(f"Input: {input_path}")
            self._log(f"Output: {output_path}")
            
            # Get VSI info to show user what's available
            vsi_info = converter.get_vsi_info(input_path)
            if vsi_info['scenes']:
                self._log(f"\n📊 VSI Analysis:")
                main_idx = vsi_info['main_scene_index']
                for scene in vsi_info['scenes']:
                    marker = "🎯 MAIN" if scene['index'] == main_idx else "  "
                    self._log(f"  {marker} Scene {scene['index']}: {scene['name']} - {scene['width']}x{scene['height']} px")
                self._log(f"\nExporting scene {main_idx} (main slide image)\n")
            
            result = converter.convert(
                input_path,
                output_path,
                create_pyramid=self.create_pyramid.get(),
                scene_index=None,  # Auto-detect main image
                resolution_level=0,  # Full resolution
                compression=self.compression.get(),
                compression_level=self.compression_level.get()
            )
            
            if result is False:
                self._log("\n❌ VSI to .univ conversion FAILED")
                self._log("Check error messages above for details")
                raise RuntimeError("VSI to .univ conversion failed - see error log above")
            
            # Verify output file was created
            if not Path(output_path).exists():
                raise RuntimeError(f"Conversion reported success but output file not found: {output_path}")
            
            output_size = Path(output_path).stat().st_size / (1024**2)
            self._log(f"\n✅ VSI conversion completed successfully!")
            self._log(f"   Output file: {Path(output_path).name}")
            self._log(f"   File size: {output_size:.1f} MB")
            
        except Exception as e:
            self._log(f"\n❌ ERROR in VSI conversion: {str(e)}")
            import traceback
            self._log(f"Traceback:\n{traceback.format_exc()}")
            raise
            
        finally:
            builtins.print = original_print
            vsi_logger.removeHandler(log_handler)
    
    def _convert_univ_to_vsi(self, input_path: str, output_path: str):
        """Convert .univ to VSI-compatible OME-TIFF."""
        converter = UnivToVSICompatible()
        
        original_print = print
        def log_print(*args, **kwargs):
            message = ' '.join(str(arg) for arg in args)
            self._log(message)
        
        import builtins
        builtins.print = log_print
        
        try:
            # Ensure output directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # VSI-compatible uses LZW compression by default
            comp = 'lzw' if self.compression.get() in ['gzip', 'lzf', 'blosc'] else self.compression.get()
            
            result = converter.convert(
                input_path,
                output_path,
                create_pyramid=self.create_pyramid.get(),
                compression=comp,
                tile_size=512
            )
            
            if result is False:
                raise RuntimeError(".univ to VSI-compatible conversion returned False - conversion failed")
        finally:
            builtins.print = original_print
    
    def _convert_vsi_to_omezarr(self, input_path: str, output_path: str):
        """Convert VSI directly to OME-Zarr using aicsimageio."""
        try:
            import zarr
            import numpy as np
            from aicsimageio import AICSImage
            
            # Check input file exists
            input_path_obj = Path(input_path)
            if not input_path_obj.exists():
                raise FileNotFoundError(f"Input file not found: {input_path}")
            
            self._log(f"Input VSI file: {input_path_obj.name}")
            
            # Load VSI with aicsimageio
            self._log("Loading VSI file with aicsimageio...")
            img = AICSImage(str(input_path))
            
            # Select appropriate scene based on user preference
            self._select_vsi_scene(img)
            
            self._log(f"✓ VSI file opened successfully")
            self._log(f"  Current scene: {img.current_scene if hasattr(img, 'current_scene') else 'default'}")
            self._log(f"  Dimensions: {img.dims}")
            self._log(f"  Shape will be: {img.shape}")
            self._log(f"  Image dimensions: {img.shape[-1]}x{img.shape[-2]} pixels")
            
            # Get the image data - should use the currently set scene
            self._log("📥 Reading image data from selected scene...")
            
            # Calculate expected size to avoid 2GB Bio-Formats limit (use float to prevent overflow)
            total_pixels = float(np.prod(img.shape))
            expected_bytes = total_pixels * 2.0  # Assume uint16
            expected_gb = expected_bytes / (1024.0**3)
            self._log(f"  Expected data size: {expected_gb:.2f} GB")
            
            # For large images, use dask with tile-based loading
            if expected_gb > 1.5:
                self._log("  ⚠ Large image - using tile-based loading to avoid 2GB Bio-Formats limit")
                xr_data = img.xarray_dask_data
                self._log(f"  Dask array: {xr_data.shape}, chunks: {xr_data.data.chunksize}")
                self._log("  Reading tiles (may take 5-15 minutes for large slides)...")
                self._log("  Please be patient...")
                image_data = xr_data.data.compute()
                self._log("  ✓ Tiles loaded and stitched!")
            else:
                image_data = img.data
            
            # Verify we got the right size
            self._log(f"✓ Data loaded: {image_data.shape}")
            self._log(f"✓ Actual dimensions: {image_data.shape[-1]}x{image_data.shape[-2]} pixels")
            self._log(f"✓ Actual size: {image_data.nbytes / (1024**3):.2f} GB")
            
            # Ensure C-contiguous
            if not image_data.flags['C_CONTIGUOUS']:
                self._log("  Converting to C-contiguous array...")
                image_data = np.ascontiguousarray(image_data)
            
            self._log(f"  Data loaded: {image_data.shape}")
            self._log(f"  Data type: {image_data.dtype}")
            
            # Create zarr store
            self._log(f"Writing OME-Zarr: {Path(output_path).name}")
            
            # Ensure output directory exists
            Path(output_path).mkdir(parents=True, exist_ok=True)
            
            # Determine chunks - zarr likes bigger chunks
            chunk_shape = list(image_data.shape)
            # Chunk spatial dimensions
            if len(chunk_shape) >= 2:
                chunk_shape[-1] = min(1024, chunk_shape[-1])  # X
                chunk_shape[-2] = min(1024, chunk_shape[-2])  # Y
            if len(chunk_shape) >= 3:
                chunk_shape[-3] = 1  # Z/C
            if len(chunk_shape) >= 4:
                chunk_shape[-4] = 1  # C/T
            if len(chunk_shape) >= 5:
                chunk_shape[-5] = 1  # T
            
            chunk_shape = tuple(chunk_shape)
            self._log(f"  Chunks: {chunk_shape}")
            
            # Create zarr array
            z = zarr.open(
                output_path,
                mode='w',
                shape=image_data.shape,
                chunks=chunk_shape,
                dtype=image_data.dtype,
                compressor=zarr.Blosc(cname='zstd', clevel=3) if self.compression.get() != 'none' else None
            )
            
            self._log(f"  Writing data...")
            z[:] = image_data
            
            # Write OME-Zarr metadata
            z.attrs['_ARRAY_DIMENSIONS'] = ['t', 'c', 'z', 'y', 'x'][-len(image_data.shape):]
            
            output_size = sum(f.stat().st_size for f in Path(output_path).rglob('*') if f.is_file()) / (1024**2)
            self._log(f"✓ OME-Zarr written successfully")
            self._log(f"  Output size: {output_size:.1f} MB")
            
        except ImportError as e:
            raise RuntimeError(f"Failed to import required library: {e}")
        except Exception as e:
            import traceback
            self._log(f"❌ Error details:\n{traceback.format_exc()}")
            raise RuntimeError(f"VSI to OME-Zarr conversion failed: {e}")
    
    def _convert_vsi_to_ometiff(self, input_path: str, output_path: str):
        """Convert VSI to OME-TIFF using aicsimageio."""
        try:
            import tifffile
            import numpy as np
            from aicsimageio import AICSImage
            
            # Check input file exists
            input_path_obj = Path(input_path)
            if not input_path_obj.exists():
                raise FileNotFoundError(f"Input file not found: {input_path}")
            
            self._log(f"Input VSI file: {input_path_obj.name}")
            self._log(f"File size: {input_path_obj.stat().st_size / (1024**2):.1f} MB")
            
            # Check for VSI data folder
            parent_dir = input_path_obj.parent
            stem = input_path_obj.stem
            vsi_data_folder = parent_dir / f"_{stem}_"
            
            if not vsi_data_folder.exists():
                vsi_data_folder = input_path_obj.with_suffix('.vsi_data')
            
            if vsi_data_folder.exists():
                self._log(f"✓ Found VSI data folder: {vsi_data_folder.name}")
            else:
                self._log(f"⚠ WARNING: VSI data folder not found!")
                self._log(f"  Expected: _{stem}_ or {stem}.vsi_data")
                self._log(f"  VSI files need both the .vsi file AND the data folder")
            
            # Load VSI with aicsimageio
            self._log("Loading VSI file with aicsimageio...")
            self._log("  This may take a moment for large files...")
            
            img = AICSImage(str(input_path))
            
            # Select appropriate scene based on user preference
            self._select_vsi_scene(img)
            
            self._log(f"✓ VSI file opened successfully")
            self._log(f"  Current scene: {img.current_scene if hasattr(img, 'current_scene') else 'default'}")
            self._log(f"  Dimensions: {img.dims}")
            self._log(f"  Shape will be: {img.shape}")
            self._log(f"  Image dimensions: {img.shape[-2]}x{img.shape[-1]} pixels (Y×X)")
            self._log(f"  Data type: {img.dtype}")
            
            # Get the image data - should use the currently set scene
            self._log("📥 Reading image data from selected scene...")
            
            # Calculate expected size to avoid 2GB Bio-Formats limit
            # Use actual dtype size, not assumed uint16
            bytes_per_pixel = img.dtype.itemsize
            total_pixels = 1
            for dim_size in img.shape:
                total_pixels *= dim_size
            expected_bytes = float(total_pixels) * float(bytes_per_pixel)
            expected_gb = expected_bytes / (1024.0**3)
            self._log(f"  Expected data size: {expected_gb:.2f} GB ({bytes_per_pixel} bytes/pixel)")
            
            # For images with any dimension > 10000 pixels, use dask tile-based loading
            # This avoids Bio-Formats 2GB limit
            needs_tiling = any(dim > 10000 for dim in img.shape[-2:])  # Check Y and X dimensions
            
            if needs_tiling or expected_gb > 1.5:
                self._log("  ⚠ Large image - using tile-based loading to avoid 2GB Bio-Formats limit")
                xr_data = img.xarray_dask_data
                self._log(f"  Initial dask array: {xr_data.shape}, chunks: {xr_data.data.chunksize}")
                
                # CRITICAL: Rechunk to smaller tiles (1024x1024) to avoid 2GB limit
                # The default chunking often uses the entire plane which defeats the purpose
                import dask.array as da
                dask_array = xr_data.data
                
                # Create chunk sizes: keep singleton dims as 1, chunk spatial dims to 1024
                chunk_sizes = []
                for i, dim_size in enumerate(dask_array.shape):
                    if i < len(dask_array.shape) - 2:  # Not Y or X dimension
                        chunk_sizes.append(1)
                    else:  # Y or X dimension
                        chunk_sizes.append(min(1024, dim_size))
                
                self._log(f"  Rechunking to tiles: {tuple(chunk_sizes)}")
                dask_array_rechunked = dask_array.rechunk(chunks=tuple(chunk_sizes))
                self._log(f"  New chunks: {dask_array_rechunked.chunksize}")
                self._log("  Reading tiles (may take 5-15 minutes for large slides)...")
                self._log("  Please be patient - do not close the application...")
                
                image_data = dask_array_rechunked.compute()
                self._log("  ✓ Tiles loaded and stitched!")
            else:
                image_data = img.data
            
            # Check if data is valid
            if image_data is None or image_data.size == 0:
                raise RuntimeError("Failed to read image data from VSI file")
            
            # Verify we got the right size
            self._log(f"✓ Data loaded: {image_data.shape}")
            self._log(f"✓ Actual dimensions: {image_data.shape[-1]}x{image_data.shape[-2]} pixels")
            self._log(f"✓ Actual size: {image_data.nbytes / (1024**3):.2f} GB")
            
            # aicsimageio returns data in TCZYX or TCZYXS format
            self._log(f"  Data loaded: {image_data.shape}")
            self._log(f"  Data type: {image_data.dtype}")
            self._log(f"  Memory size: {image_data.nbytes / (1024**2):.1f} MB")
            self._log(f"  Value range: {image_data.min()} to {image_data.max()}")
            
            # Handle RGB data (6D array with S dimension)
            if image_data.ndim == 6:
                self._log(f"  Detected 6D data with RGB channels (S dimension)")
                # Shape is (T, C, Z, Y, X, S) where S=3 for RGB
                # Merge S into C dimension: (T, C*S, Z, Y, X)
                t, c, z, y, x, s = image_data.shape
                image_data = image_data.transpose(0, 1, 5, 2, 3, 4).reshape(t, c*s, z, y, x)
                self._log(f"  Reshaped to: {image_data.shape}")
            
            # Ensure data is C-contiguous (required for tifffile)
            if not image_data.flags['C_CONTIGUOUS']:
                self._log("  Converting to C-contiguous array...")
                image_data = np.ascontiguousarray(image_data)
            
            # For TIFF, we want (Y, X) or (C, Y, X) or (Z, Y, X) or (T, Z, Y, X) etc.
            # Remove singleton dimensions but keep meaningful structure
            original_shape = image_data.shape
            
            # Squeeze leading singleton dimensions only
            while image_data.ndim > 2 and image_data.shape[0] == 1:
                image_data = image_data[0]
                
            if image_data.shape != original_shape:
                self._log(f"  Squeezed to: {image_data.shape}")
            
            # Verify we still have valid data after squeeze
            if image_data.size == 0:
                raise RuntimeError("Image data became empty after processing")
            
            # Ensure output directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            self._log(f"Writing OME-TIFF: {Path(output_path).name}")
            
            # Determine compression
            compression_map = {
                'gzip': 'zlib',
                'lzw': 'lzw',
                'none': None,
                'jpeg': 'jpeg'
            }
            comp = compression_map.get(self.compression.get(), 'zlib')
            self._log(f"  Compression: {comp}")
            self._log(f"  BigTIFF: Yes")
            
            # Determine photometric interpretation and axes
            # For RGB: shape should be (Y, X, 3) or (3, Y, X)
            # For multi-channel: (C, Y, X) where C != 3
            if image_data.ndim == 3:
                if image_data.shape[0] == 3:
                    # (3, Y, X) - RGB
                    photometric = 'rgb'
                    axes = 'CYX'
                    self._log(f"  Photometric: RGB (3 channels)")
                elif image_data.shape[-1] == 3:
                    # (Y, X, 3) - RGB in different order
                    photometric = 'rgb'
                    axes = 'YXS'
                    self._log(f"  Photometric: RGB (samples)")
                else:
                    # Multi-channel grayscale
                    photometric = 'minisblack'
                    axes = 'CYX'
                    self._log(f"  Photometric: Multi-channel grayscale ({image_data.shape[0]} channels)")
            elif image_data.ndim == 2:
                photometric = 'minisblack'
                axes = 'YX'
                self._log(f"  Photometric: Single-channel grayscale")
            elif image_data.ndim == 4:
                photometric = 'minisblack'
                axes = 'ZCYX'
                self._log(f"  Photometric: Multi-channel Z-stack")
            else:
                photometric = 'minisblack'
                axes = None
                self._log(f"  Photometric: Multi-dimensional grayscale")
            
            # Write OME-TIFF
            self._log(f"Writing data to TIFF file...")
            self._log(f"  Data size: {image_data.nbytes / (1024**2):.1f} MB")
            self._log(f"  Data dtype: {image_data.dtype}")
            self._log(f"  Data is C-contiguous: {image_data.flags['C_CONTIGUOUS']}")
            self._log(f"  Data is writable: {image_data.flags['WRITEABLE']}")
            
            # Force data to be fully loaded and owned (not a view)
            if not image_data.flags['OWNDATA']:
                self._log("  Creating copy of data (was a view)...")
                image_data = np.array(image_data, copy=True)
            
            # Write without tiling if pyramid disabled, or if data is too small
            use_tiling = self.create_pyramid.get() and min(image_data.shape[-2:]) > 1024
            
            try:
                tifffile.imwrite(
                    output_path,
                    image_data,
                    bigtiff=True,
                    compression=comp,
                    photometric=photometric,
                    tile=(512, 512) if use_tiling else None,
                    metadata={'axes': axes} if axes else None
                )
            except Exception as write_error:
                self._log(f"❌ TIFF write error: {write_error}")
                import traceback
                self._log(traceback.format_exc())
                raise RuntimeError(f"Failed to write TIFF file: {write_error}")
            
            # Verify output file was created and has content
            output_path_obj = Path(output_path)
            if not output_path_obj.exists():
                raise RuntimeError("Output file was not created")
            
            output_size = output_path_obj.stat().st_size / (1024**2)
            
            # Be more lenient with compressed files - they can be much smaller
            if output_size < 0.001:  # Less than 1 KB is definitely wrong
                raise RuntimeError(f"Output file is empty or too small ({output_size:.3f} MB)")
            
            # Warn if file is unexpectedly small but don't fail
            expected_size = image_data.nbytes / (1024**2)
            if output_size < expected_size * 0.01 and comp is not None:  # Less than 1% of expected
                self._log(f"⚠ Warning: Output file ({output_size:.1f} MB) is much smaller than expected ({expected_size:.1f} MB)")
                self._log(f"  This might indicate incomplete data, but continuing...")
            
            self._log(f"✓ OME-TIFF written successfully")
            self._log(f"  Output size: {output_size:.1f} MB")
            self._log(f"  Expected size (uncompressed): {expected_size:.1f} MB")
            
        except ImportError as e:
            import traceback
            self._log(f"❌ Import error:\n{traceback.format_exc()}")
            raise RuntimeError(
                f"Failed to import required library: {e}\n\n"
                f"This converter requires aicsimageio for VSI support.\n"
                f"Install with: pip install aicsimageio"
            )
        except Exception as e:
            import traceback
            self._log(f"❌ Error details:\n{traceback.format_exc()}")
            raise RuntimeError(f"VSI to OME-TIFF conversion failed: {e}")
    
    def _validate_file(self):
        """Validate a .univ file."""
        filename = filedialog.askopenfilename(
            title="Select .univ file to validate",
            filetypes=[("UNIV files", "*.univ"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        self._log(f"\n{'='*50}")
        self._log(f"Validating: {Path(filename).name}")
        self._log(f"{'='*50}\n")
        
        try:
            validator = UnivValidator(filename, verbose=True)
            
            # Redirect output
            original_print = print
            def log_print(*args, **kwargs):
                message = ' '.join(str(arg) for arg in args)
                self._log(message)
            
            import builtins
            builtins.print = log_print
            
            try:
                is_valid = validator.validate(check_data_integrity=False)
                
                if is_valid:
                    messagebox.showinfo("Validation", f"✅ File is valid!\n\n{Path(filename).name}")
                else:
                    messagebox.showwarning("Validation", f"⚠️ File has issues.\n\nSee log for details.")
            
            finally:
                builtins.print = original_print
        
        except Exception as e:
            self._log(f"❌ Validation error: {str(e)}")
            messagebox.showerror("Validation Error", f"Error validating file:\n\n{str(e)}")
    
    def _show_about(self):
        """Show about dialog."""
        about_text = """Universal Microscopy Format Converter

Version: 1.1
Date: December 14, 2025

Convert between:
• .univ (Universal format)
• OME-TIFF
• OME-Zarr
• VSI (Olympus - via OME-TIFF)

Features:
✓ Drag-and-drop support
✓ Multi-resolution pyramids
✓ Lossless compression
✓ Complete metadata preservation
✓ Format validation
✓ VSI slide scanner support

Dependencies:
• h5py, numpy, tifffile, zarr
• aicsimageio or openslide (for VSI)
• tkinterdnd2 (optional, for drag-and-drop)

Documentation:
See UNIV_QUICKSTART.md for usage guide.

License: MIT
"""
        messagebox.showinfo("About", about_text)


def main():
    """Main entry point."""
    # Check dependencies
    try:
        import h5py
        import numpy
        import tifffile
        import zarr
    except ImportError as e:
        messagebox.showerror(
            "Missing Dependencies",
            f"Required package not installed:\n{e}\n\n"
            "Install with:\npip install h5py numpy tifffile zarr numcodecs scipy"
        )
        sys.exit(1)
    
    # Create loading splash screen
    if HAS_DND:
        splash = TkinterDnD.Tk()
    else:
        splash = tk.Tk()
    
    splash.title("Loading...")
    splash.geometry("400x200")
    splash.overrideredirect(True)  # Remove window decorations
    
    # Center splash
    splash.update_idletasks()
    x = (splash.winfo_screenwidth() // 2) - 200
    y = (splash.winfo_screenheight() // 2) - 100
    splash.geometry(f"+{x}+{y}")
    
    # Create splash content
    splash_frame = ttk.Frame(splash, padding="40")
    splash_frame.pack(fill=tk.BOTH, expand=True)
    
    title_label = ttk.Label(
        splash_frame,
        text="Universal Format Converter",
        font=("Arial", 14, "bold")
    )
    title_label.pack(pady=(0, 20))
    
    status_label = ttk.Label(
        splash_frame,
        text="Initializing bioformats...\nThis may take 10-30 seconds on first launch",
        font=("Arial", 10)
    )
    status_label.pack(pady=(0, 20))
    
    progress = ttk.Progressbar(splash_frame, mode='indeterminate', length=300)
    progress.pack()
    progress.start(10)
    
    splash.update()
    
    # Initialize bioformats in background
    def init_and_start():
        try:
            # Trigger bioformats initialization by importing aicsimageio
            try:
                from aicsimageio import AICSImage
                # This will trigger bioformats_jar to initialize the JVM
                status_label.config(text="Bioformats ready!\nStarting application...")
                splash.update()
            except Exception as e:
                status_label.config(text=f"Note: VSI support may be limited\n{str(e)[:50]}")
                splash.update()
            
            # Wait a moment
            splash.after(500)
            splash.update()
            
            # Close splash
            splash.destroy()
            
            # Create main GUI
            if HAS_DND:
                root = TkinterDnD.Tk()
            else:
                root = tk.Tk()
            
            app = FormatConverterGUI(root)
            
            # Center window
            root.update_idletasks()
            x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
            y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
            root.geometry(f"+{x}+{y}")
            
            root.mainloop()
            
        except Exception as e:
            splash.destroy()
            messagebox.showerror("Startup Error", f"Failed to start application:\n{e}")
            sys.exit(1)
    
    # Start initialization after splash is visible
    splash.after(100, init_and_start)
    splash.mainloop()


if __name__ == "__main__":
    main()
