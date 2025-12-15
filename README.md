# Integrator

**Universal Microscopy Format Converter**

Convert between VSI, OME-TIFF, OME-Zarr, and .univ formats with intelligent scene detection and resolution selection.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)

## Features

- **Batch Conversion**: Convert multiple files/folders in one operation
- **Intelligent Scene Detection**: Automatically detects and categorizes VSI scenes (Main Images, Overview, Labels, Macros)
- **Resolution Pyramid Selection**: Choose any resolution level from VSI pyramid structures
- **Large File Support**: Handles multi-gigabyte images using dask-based chunked loading (bypasses Bio-Formats 2GB limit)
- **Multiple Output Formats**:
  - `.univ` - Universal HDF5-based format with complete metadata
  - `OME-TIFF` - BigTIFF with OME-XML metadata, compatible with vendor software (ZEN, LAS X)
  - `OME-Zarr` - Cloud-native format with Blosc compression for napari and modern tools
- **Drag & Drop Interface**: Intuitive tkinter-based GUI with drag-and-drop file support
- **Custom Filenames**: Specify output names for single file conversions
- **Automatic Duplicate Handling**: Prevents overwrites with intelligent suffix numbering

## Supported Formats

### Input Formats
- **VSI**: Olympus/Evident CellSens format with multi-scene and pyramid support
- **OME-TIFF**: Includes BigTIFF support
- **OME-Zarr**: Cloud-native formats
- **.univ**: Universal HDF5-based format

### Output Formats
- **OME-TIFF**: Industry standard with full metadata
- **OME-Zarr**: Cloud-native with Blosc compression
- **.univ**: Self-describing HDF5 format
- **VSI-compatible**: OME-TIFF optimized for Olympus viewers

## Installation

### Prerequisites
- Python 3.8 or higher
- Windows, macOS, or Linux

### Install Dependencies

```bash
pip install -r requirements.txt
```

**Key Dependencies:**
- `aicsimageio[bioformats]` - Multi-format microscopy image reading
- `bioformats_jar` - Bio-Formats Java backend for VSI support
- `tifffile` - OME-TIFF writing with BigTIFF support
- `zarr` - OME-Zarr cloud-native format
- `h5py` - .univ HDF5 format
- `dask[array]` - Lazy loading and chunked processing
- `numpy` - Array operations
- `tkinterdnd2` - Drag-and-drop GUI support

## Usage

### Launch GUI Application

```bash
python format_converter_gui.py
```

### Batch Conversion

1. **Add Files**: 
   - Drag and drop files/folders onto the file list
   - Use "Browse Files" or "Browse Folder" buttons
   
2. **Select Output Format**: Choose from OME-TIFF, OME-Zarr, or .univ

3. **Configure Options**:
   - **VSI Resolution**: Select specific pyramid level or main image
   - **Compression**: Choose compression level (OME-Zarr only)
   
4. **Convert**: Click "Convert" button
   - Single file: Prompts for custom output filename
   - Multiple files: Prompts for output folder, auto-generates filenames

### Scene Detection (VSI Files)

The converter automatically analyzes VSI file structure and categorizes scenes:

- **MAIN IMAGES**: Primary slide images with pyramid levels
  - `Image.vsi` (Highest resolution)
  - `Image.vsi #1` (Level 1)
  - `Image.vsi #2` (Level 2)
  - etc.
  
- **OVERVIEW**: Low-resolution preview images

- **LABELS**: Slide label images

- **MACROS**: Macro camera images

Select your desired resolution from the "VSI Resolution" dropdown.

### Handling Large Files

Integrator uses dask-based chunked loading to handle images larger than Bio-Formats' 2GB limit:

- Automatically rechunks to 1024×1024 tiles
- Processes tiles incrementally to minimize memory usage
- Supports images up to 100GB+ (tested with 57243×40976×3 pixel VSI)

## Technical Details

### Bio-Formats 2GB Limitation

Bio-Formats has a 2GB limit per image plane when using immediate loading. Image Enzyme overcomes this by:

1. Using `xarray_dask_data` for lazy loading
2. Manual rechunking: `dask_array.rechunk(chunks=(1,1,1,1024,1024,3))`
3. Tile-based processing via Bio-Formats tiling API

### Architecture

- **Format Converter GUI** (`format_converter_gui.py`): Main tkinter application with batch processing
- **VSI to Univ Converter** (`vsi_to_univ.py`): VSI-specific conversion with scene detection
- **Threading**: Background conversion without GUI blocking
- **Logging**: Comprehensive logging with GUI integration

## Command Line Usage

For advanced users, the converter can be used programmatically:

```python
from vsi_to_univ import VSIToUniv

converter = VSIToUniv()

# Get scene information
info = converter.get_vsi_info("input.vsi")
print(f"Available scenes: {info['num_scenes']}")

# Convert specific scene and resolution
converter.convert(
    vsi_path="input.vsi",
    univ_path="output.univ",
    scene_index=0,  # Main image
    resolution_level=1  # First pyramid level
)
```

## Building Standalone Executable

```bash
python build_standalone_exe.py
```

Creates a single `.exe` file with all dependencies bundled (Windows).

## Known Limitations

- Bio-Formats requires Java Runtime Environment (JRE) for VSI reading
- Very large images (>50GB) may require significant processing time
- Some VSI metadata may not be fully preserved in all output formats

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with descriptive commit messages
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

## Acknowledgments

- Built with [aicsimageio](https://github.com/AllenCellModeling/aicsimageio)
- Powered by [Bio-Formats](https://www.openmicroscopy.org/bio-formats/)
- Uses [OME data model](https://www.openmicroscopy.org/ome-files/)

---

**Integrator** - Seamlessly integrating microscopy formats since 2025 🔬✨
