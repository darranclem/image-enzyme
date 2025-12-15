#!/usr/bin/env python3
"""
VSI to .univ Converter

Converts Olympus VSI (Virtual Slide Image) files to .univ format.
Handles multi-series VSI files with proper metadata extraction.

Usage:
    python vsi_to_univ.py input.vsi output.univ --pyramid --compression gzip
"""

import h5py
import numpy as np
import logging
import sys
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

# Add OpenSlide DLL directory to PATH (for development)
tools_dir = Path(__file__).parent
openslide_dll_dir = tools_dir / "_openslide" / "openslide-win64-20231011" / "bin"
if openslide_dll_dir.exists():
    os.add_dll_directory(str(openslide_dll_dir))
    os.environ['PATH'] = str(openslide_dll_dir) + os.pathsep + os.environ.get('PATH', '')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VSIToUniv:
    """Convert Olympus VSI files to .univ format"""
    
    def __init__(self):
        self.aicsimageio_available = False
        self._check_dependencies()
    
    def _check_dependencies(self):
        """Check for VSI reading libraries"""
        try:
            from aicsimageio import AICSImage
            self.aicsimageio_available = True
            logger.info("✓ aicsimageio available")
        except ImportError:
            logger.error("❌ aicsimageio not available")
            logger.error("Install with: pip install aicsimageio")
            sys.exit(1)
    
    def get_vsi_info(self, input_path: str) -> dict:
        """
        Get VSI file information without loading full data.
        
        Returns dict with:
            - scenes: list of scene information
            - main_scene_index: index of the main image scene
            - available_resolutions: list of resolution options
        """
        try:
            input_path = Path(input_path)
            scene_info = self._analyze_vsi_structure(input_path)
            main_scene_idx = self._find_main_image_scene(scene_info)
            
            # Calculate available resolution levels based on main scene size
            main_scene = scene_info[main_scene_idx] if scene_info else None
            available_resolutions = []
            
            if main_scene:
                width = main_scene['width']
                height = main_scene['height']
                level = 0
                
                while min(width, height) >= 512:  # Stop when smaller dimension < 512
                    available_resolutions.append({
                        'level': level,
                        'width': width,
                        'height': height,
                        'megapixels': (width * height) / 1_000_000,
                        'downsample_factor': 2**level
                    })
                    width //= 2
                    height //= 2
                    level += 1
            
            return {
                'scenes': scene_info,
                'main_scene_index': main_scene_idx,
                'available_resolutions': available_resolutions
            }
            
        except Exception as e:
            logger.error(f"Failed to get VSI info: {e}")
            return {
                'scenes': [],
                'main_scene_index': 0,
                'available_resolutions': []
            }
    
    def convert(self, input_path: str, output_path: str,
                create_pyramid: bool = True,
                compression: str = 'gzip',
                compression_level: int = 4,
                scene_index: int = None,
                resolution_level: int = 0) -> bool:
        """
        Convert VSI to .univ format
        
        Args:
            input_path: Path to input .vsi file
            output_path: Path to output .univ file
            create_pyramid: Generate multi-resolution pyramid
            compression: Compression type (gzip, lzf, blosc)
            compression_level: Compression level (1-9 for gzip)
            scene_index: Scene/series to export (None = auto-detect main image)
            resolution_level: Resolution level to export (0 = highest resolution)
        
        Returns:
            True if successful
        """
        try:
            input_path = Path(input_path)
            output_path = Path(output_path)
            
            logger.info(f"Converting VSI: {input_path.name}")
            logger.info(f"Output: {output_path.name}")
            
            # Check VSI data folder - try _xyz_ format first (standard Olympus format)
            stem = input_path.stem
            parent = input_path.parent
            
            data_folder = parent / f"_{stem}_"
            if not data_folder.exists():
                data_folder = input_path.with_suffix('.vsi_data')
            
            if data_folder.exists():
                logger.info(f"✓ VSI data folder found: {data_folder.name}")
            else:
                logger.warning(f"⚠ VSI data folder not found!")
                logger.warning(f"  Expected: _{stem}_ or {stem}.vsi_data")
                logger.warning(f"  In directory: {parent}")
            
            # First, analyze VSI structure to show available options
            scene_info = self._analyze_vsi_structure(input_path)
            
            # Auto-select main image scene if not specified
            if scene_index is None:
                scene_index = self._find_main_image_scene(scene_info)
                logger.info(f"📊 Auto-selected scene {scene_index} as main image (largest)")
            
            # Load VSI file
            image_data, metadata = self._load_vsi(input_path, scene_index, resolution_level)
            
            if image_data is None:
                logger.error("Failed to load VSI file")
                return False
            
            logger.info(f"✓ Loaded VSI data: shape={image_data.shape}, dtype={image_data.dtype}")
            logger.info(f"  Size: {image_data.nbytes / (1024**2):.1f} MB")
            
            # Convert from aicsimageio format to .univ format (T, C, Z, Y, X)
            # aicsimageio can return various shapes depending on the file
            if image_data.ndim == 2:
                # Single channel (Y, X) -> (1, 1, 1, Y, X)
                image_data = image_data[np.newaxis, np.newaxis, np.newaxis, :, :]
            elif image_data.ndim == 3:
                # Multi-channel (C, Y, X) -> (1, C, 1, Y, X)
                image_data = image_data[np.newaxis, :, np.newaxis, :, :]
            elif image_data.ndim == 4:
                # (Z, C, Y, X) or (T, C, Y, X) -> (T, C, Z, Y, X)
                image_data = image_data[:, :, np.newaxis, :, :]
            elif image_data.ndim == 5:
                # Already (T, C, Z, Y, X)
                pass
            elif image_data.ndim == 6:
                # (T, C, Z, Y, X, S) - RGB/Scene dimension, merge S into C
                logger.info(f"  Detected RGB image with scene dimension: {image_data.shape}")
                t, c, z, y, x, s = image_data.shape
                # Reshape to merge S into C: (T, C*S, Z, Y, X)
                image_data = image_data.transpose(0, 1, 5, 2, 3, 4).reshape(t, c*s, z, y, x)
                logger.info(f"  Merged RGB channels: new shape = {image_data.shape}")
            else:
                logger.error(f"Unexpected image shape: {image_data.shape}")
                return False
            
            logger.info(f"  Converted to .univ format: {image_data.shape} (T, C, Z, Y, X)")
            
            # Convert to .univ
            self._write_univ(
                output_path,
                image_data,
                metadata,
                create_pyramid,
                compression,
                compression_level
            )
            
            logger.info(f"✅ Conversion complete: {output_path.name}")
            logger.info(f"  Output size: {output_path.stat().st_size / (1024**2):.1f} MB")
            
            return True
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}", exc_info=True)
            return False
    
    def _analyze_vsi_structure(self, file_path: Path) -> list:
        """Analyze VSI file structure and return information about all scenes."""
        try:
            from aicsimageio import AICSImage
            
            logger.info(f"\n{'='*60}")
            logger.info(f"📊 ANALYZING VSI STRUCTURE")
            logger.info(f"{'='*60}")
            
            img = AICSImage(str(file_path))
            scene_info = []
            
            if hasattr(img, 'scenes') and len(img.scenes) > 0:
                logger.info(f"Found {len(img.scenes)} scene(s) in VSI file:\n")
                
                for i, scene_name in enumerate(img.scenes):
                    img.set_scene(scene_name)
                    shape = img.shape
                    dims = img.dims
                    
                    # Calculate total pixels
                    y_size = shape[-2] if len(shape) >= 2 else 0
                    x_size = shape[-1] if len(shape) >= 1 else 0
                    total_pixels = y_size * x_size
                    
                    # Get physical size if available
                    px_size = img.physical_pixel_sizes
                    pixel_size_um = px_size.X if px_size.X else "unknown"
                    
                    scene_data = {
                        'index': i,
                        'name': scene_name,
                        'shape': shape,
                        'dims': str(dims),
                        'width': x_size,
                        'height': y_size,
                        'total_pixels': total_pixels,
                        'pixel_size_um': pixel_size_um
                    }
                    scene_info.append(scene_data)
                    
                    # Identify likely scene type
                    scene_type = "Unknown"
                    if "label" in scene_name.lower() or "macro" in scene_name.lower():
                        scene_type = "Label/Macro"
                    elif total_pixels > 100_000_000:  # > 100 megapixels
                        scene_type = "Main Slide Image"
                    elif total_pixels > 10_000_000:  # > 10 megapixels
                        scene_type = "Slide Region"
                    else:
                        scene_type = "Overview/Thumbnail"
                    
                    logger.info(f"  Scene {i}: {scene_name}")
                    logger.info(f"    Type: {scene_type}")
                    logger.info(f"    Dimensions: {x_size} x {y_size} pixels ({total_pixels/1_000_000:.1f} MP)")
                    logger.info(f"    Shape: {shape} {dims}")
                    logger.info(f"    Pixel size: {pixel_size_um} µm")
                    logger.info("")
            else:
                # Single scene
                shape = img.shape
                dims = img.dims
                scene_info.append({
                    'index': 0,
                    'name': 'default',
                    'shape': shape,
                    'dims': str(dims),
                    'width': shape[-1],
                    'height': shape[-2],
                    'total_pixels': shape[-1] * shape[-2],
                    'pixel_size_um': img.physical_pixel_sizes.X if img.physical_pixel_sizes.X else "unknown"
                })
                logger.info(f"Single scene VSI: {shape}")
            
            logger.info(f"{'='*60}\n")
            return scene_info
            
        except Exception as e:
            logger.error(f"Failed to analyze VSI structure: {e}")
            return []
    
    def _find_main_image_scene(self, scene_info: list) -> int:
        """Find the main image scene (largest by pixel count, excluding label/macro)."""
        if not scene_info:
            return 0
        
        # Filter out label/macro scenes
        main_scenes = [s for s in scene_info if "label" not in s['name'].lower() and "macro" not in s['name'].lower()]
        
        if not main_scenes:
            # If all scenes are labels, just use the largest one
            main_scenes = scene_info
        
        # Find scene with most pixels
        main_scene = max(main_scenes, key=lambda s: s['total_pixels'])
        return main_scene['index']
    
    def _load_vsi(self, file_path: Path, scene_index: int = 0, resolution_level: int = 0) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """Load VSI file using aicsimageio"""
        
        if not self.aicsimageio_available:
            logger.error("aicsimageio not available")
            return None, {}
        
        try:
            from aicsimageio import AICSImage
            
            logger.info(f"🎯 Loading VSI scene {scene_index} at resolution level {resolution_level}...")
            
            # Create fresh AICSImage instance
            img = AICSImage(str(file_path))
            
            # Log all available scenes
            if hasattr(img, 'scenes'):
                logger.info(f"  Available scenes: {img.scenes}")
                logger.info(f"  Current scene before setting: {img.current_scene}")
            
            # Set scene BEFORE loading data - this is critical!
            if hasattr(img, 'scenes') and len(img.scenes) > scene_index:
                scene_name = img.scenes[scene_index]
                logger.info(f"  🔄 Setting scene to: {scene_name} (index {scene_index})")
                img.set_scene(scene_name)
                logger.info(f"  ✓ Current scene after setting: {img.current_scene}")
                logger.info(f"  ✓ Scene shape: {img.shape}")
                logger.info(f"  ✓ Scene dimensions: {img.shape[-1]}x{img.shape[-2]} pixels")
            else:
                logger.info(f"  Using default scene (only one available or scene_index out of range)")
            
            # Get data - use dask for large images to avoid 2GB Bio-Formats limit
            logger.info("  📥 Reading VSI data...")
            logger.info(f"  Image dimensions: {img.shape[-1]}x{img.shape[-2]} pixels")
            
            # Calculate expected size (use float to prevent overflow with large images)
            total_pixels = float(np.prod(img.shape))
            expected_bytes = total_pixels * 2.0  # Assume uint16
            expected_gb = expected_bytes / (1024.0**3)
            
            logger.info(f"  Expected data size: {expected_gb:.2f} GB")
            
            # For large images (> 1.5 GB), use dask with small chunks to avoid 2GB Bio-Formats limit
            if expected_gb > 1.5:
                logger.info("  ⚠ Large image detected - using tiled/chunked loading")
                logger.info("  This will take longer but prevents the 2GB Bio-Formats crash...")
                
                # Get dask array with lazy loading using xarray_dask_data
                # This uses Bio-Formats tiling internally to avoid loading full planes
                logger.info("  Creating dask array with tile-based chunking...")
                xr_data = img.xarray_dask_data
                logger.info(f"  Dask array created: shape={xr_data.shape}, chunks={xr_data.data.chunksize}")
                
                # Extract the numpy array by computing the dask graph
                # This reads tiles one by one instead of full planes
                logger.info("  Reading tiles from VSI file (this may take 5-15 minutes)...")
                logger.info("  Please be patient - processing large whole slide image...")
                data = xr_data.data.compute()
                logger.info("  ✓ All tiles loaded and stitched successfully!")
            else:
                logger.info("  Loading image data directly...")
                data = img.data
            
            # Verify we got the right data size
            logger.info(f"  ✓ Data loaded: {data.shape}")
            logger.info(f"  ✓ Data dimensions: {data.shape[-1]}x{data.shape[-2]} pixels")
            logger.info(f"  ✓ Actual size: {data.nbytes / (1024**3):.2f} GB")
            
            # Apply downsampling if resolution_level > 0
            if resolution_level > 0:
                downsample_factor = 2 ** resolution_level
                logger.info(f"  Downsampling by factor of {downsample_factor} (level {resolution_level})...")
                original_shape = data.shape
                # Downsample spatial dimensions (Y, X)
                data = data[..., ::downsample_factor, ::downsample_factor]
                logger.info(f"  Downsampled: {original_shape} -> {data.shape}")
                logger.info(f"  Size reduction: {original_shape[-2]*original_shape[-1]/(data.shape[-2]*data.shape[-1]):.1f}x smaller")
            
            # Ensure data is C-contiguous and has a compatible dtype
            if not data.flags['C_CONTIGUOUS']:
                logger.info("  Converting data to C-contiguous array...")
                data = np.ascontiguousarray(data)
            
            # Convert to a standard dtype if needed (h5py doesn't like some numpy dtypes)
            if data.dtype == np.dtype('uint16'):
                pass  # uint16 is fine
            elif data.dtype == np.dtype('uint8'):
                pass  # uint8 is fine
            elif data.dtype in [np.float32, np.float64]:
                pass  # floats are fine
            else:
                # Convert unusual dtypes to uint16
                logger.info(f"  Converting dtype from {data.dtype} to uint16...")
                data = data.astype(np.uint16)
            
            logger.info(f"  Dimensions: {img.dims}")
            logger.info(f"  Shape: {img.shape}")
            logger.info(f"  Data type: {data.dtype}, C-contiguous: {data.flags['C_CONTIGUOUS']}")
            logger.info(f"  Physical pixel sizes: X={img.physical_pixel_sizes.X}, Y={img.physical_pixel_sizes.Y}")
            
            # Extract metadata
            scene_name = img.scenes[scene_index] if hasattr(img, 'scenes') and len(img.scenes) > scene_index else "default"
            
            metadata = {
                'source_file': file_path.name,
                'file_format': 'Olympus VSI',
                'scene_index': scene_index,
                'scene_name': scene_name,
                'resolution_level': resolution_level,
                'dimensions': {
                    'X': img.dims.X if hasattr(img.dims, 'X') else data.shape[-1],
                    'Y': img.dims.Y if hasattr(img.dims, 'Y') else data.shape[-2],
                    'C': img.dims.C if hasattr(img.dims, 'C') else 1,
                    'Z': img.dims.Z if hasattr(img.dims, 'Z') else 1,
                    'T': img.dims.T if hasattr(img.dims, 'T') else 1,
                },
                'physical_size': {
                    'X': (img.physical_pixel_sizes.X * (2**resolution_level)) if img.physical_pixel_sizes.X else 1.0,
                    'Y': (img.physical_pixel_sizes.Y * (2**resolution_level)) if img.physical_pixel_sizes.Y else 1.0,
                    'Z': img.physical_pixel_sizes.Z if img.physical_pixel_sizes.Z else 1.0,
                    'unit': 'µm'
                },
                'channel_names': img.channel_names if hasattr(img, 'channel_names') else [],
            }
            
            logger.info(f"✓ Loaded VSI: shape={data.shape}, dtype={data.dtype}")
            return data, metadata
            
        except Exception as e:
            logger.error(f"aicsimageio failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None, {}
    
    def _write_univ(self, output_path: Path, image_data: np.ndarray,
                    metadata: Dict[str, Any], create_pyramid: bool,
                    compression: str, compression_level: int):
        """Write data to .univ format"""
        
        logger.info(f"📝 Writing .univ file: {output_path.name}")
        
        # Ensure data is C-contiguous before writing to HDF5
        if not image_data.flags['C_CONTIGUOUS']:
            logger.info("  Converting image data to C-contiguous array...")
            image_data = np.ascontiguousarray(image_data)
        
        with h5py.File(output_path, 'w') as f:
            # Set compression options
            comp_opts = {}
            if compression != 'none':
                comp_opts['compression'] = compression
                if compression == 'gzip':
                    comp_opts['compression_opts'] = compression_level
            
            # Determine chunk size
            shape = image_data.shape  # (T, C, Z, Y, X)
            chunk_size = (1, 1, min(5, shape[2]), min(512, shape[3]), min(512, shape[4]))
            
            logger.info(f"  Chunks: {chunk_size}")
            logger.info(f"  Compression: {compression}")
            
            # Write main image data
            logger.info("  Writing image data...")
            logger.info(f"    Data shape: {image_data.shape}, dtype: {image_data.dtype}")
            logger.info(f"    Data size: {image_data.nbytes / (1024**2):.1f} MB")
            logger.info(f"    Data is C-contiguous: {image_data.flags['C_CONTIGUOUS']}")
            
            dset = f.create_dataset(
                'ImageData/Resolution_0',
                data=image_data,
                chunks=chunk_size,
                **comp_opts
            )
            
            logger.info(f"    Dataset created: shape={dset.shape}, size={dset.size} elements")
            
            # Verify data was written
            if dset.size == 0:
                logger.error("    ERROR: Dataset is empty!")
                raise RuntimeError("Failed to write image data - dataset is empty")
            
            # Create pyramid if requested
            if create_pyramid and min(shape[3], shape[4]) > 512:
                logger.info("  Generating pyramid...")
                self._create_pyramid(f, image_data, compression, compression_level)
            
            # Create thumbnail
            logger.info("  Creating thumbnail...")
            self._create_thumbnail(f, image_data)
            
            # Write metadata
            logger.info("  Writing metadata...")
            self._write_metadata(f, metadata, image_data.shape)
            
            # Write provenance
            self._write_provenance(f, metadata)
            
            # Write schema
            self._write_schema(f)
    
    def _create_pyramid(self, f: h5py.File, image_data: np.ndarray,
                       compression: str, compression_level: int):
        """Create multi-resolution pyramid"""
        
        comp_opts = {}
        if compression != 'none':
            comp_opts['compression'] = compression
            if compression == 'gzip':
                comp_opts['compression_opts'] = compression_level
        
        current_data = image_data
        level = 1
        
        while min(current_data.shape[3], current_data.shape[4]) > 256:
            # Downsample by 2x
            downsampled = current_data[:, :, :, ::2, ::2]
            
            logger.info(f"    Level {level}: {downsampled.shape[3]}x{downsampled.shape[4]} pixels")
            
            chunk_size = (1, 1, 1, min(256, downsampled.shape[3]), min(256, downsampled.shape[4]))
            
            f.create_dataset(
                f'ImageData/Resolution_{level}',
                data=downsampled,
                chunks=chunk_size,
                **comp_opts
            )
            
            current_data = downsampled
            level += 1
    
    def _create_thumbnail(self, f: h5py.File, image_data: np.ndarray):
        """Create thumbnail (256x256 max)"""
        
        # Get Y, X dimensions
        y_size, x_size = image_data.shape[3], image_data.shape[4]
        
        # Calculate scale to fit in 256x256
        scale = min(256 / x_size, 256 / y_size)
        
        if scale >= 1.0:
            thumbnail = image_data[0, :, 0, :, :]  # Use full size
        else:
            # Downsample
            step_y = max(1, int(1 / scale))
            step_x = max(1, int(1 / scale))
            thumbnail = image_data[0, :, 0, ::step_y, ::step_x]
        
        # Ensure thumbnail is (C, Y, X)
        if thumbnail.ndim == 2:
            thumbnail = thumbnail[np.newaxis, :, :]
        
        f.create_dataset('Thumbnail', data=thumbnail, compression='gzip')
    
    def _write_metadata(self, f: h5py.File, metadata: Dict[str, Any], shape: Tuple):
        """Write metadata group"""
        
        meta_group = f.create_group('Metadata')
        
        # Core dimensions
        dims = meta_group.create_group('Dimensions')
        dims.attrs['SizeT'] = int(shape[0])
        dims.attrs['SizeC'] = int(shape[1])
        dims.attrs['SizeZ'] = int(shape[2])
        dims.attrs['SizeY'] = int(shape[3])
        dims.attrs['SizeX'] = int(shape[4])
        dims.attrs['DimensionOrder'] = 'TCZYX'
        
        # Physical size
        if 'physical_size' in metadata:
            phys = meta_group.create_group('PhysicalSize')
            phys_data = metadata['physical_size']
            phys.attrs['X'] = float(phys_data.get('X', 1.0))
            phys.attrs['Y'] = float(phys_data.get('Y', 1.0))
            phys.attrs['Z'] = float(phys_data.get('Z', 1.0))
            phys.attrs['Unit'] = str(phys_data.get('unit', 'µm'))
        
        # Source info
        source = meta_group.create_group('Source')
        source.attrs['OriginalFile'] = str(metadata.get('source_file', 'unknown'))
        source.attrs['OriginalFormat'] = str(metadata.get('file_format', 'VSI'))
        source.attrs['ConversionDate'] = str(datetime.now().isoformat())
        
        # Channel info
        if 'channel_names' in metadata and metadata['channel_names']:
            channels = meta_group.create_group('Channels')
            for i, name in enumerate(metadata['channel_names']):
                channels.attrs[f'Channel_{i}'] = str(name)
    
    def _write_provenance(self, f: h5py.File, metadata: Dict[str, Any]):
        """Write provenance information"""
        
        prov = f.create_group('Provenance')
        prov.attrs['created'] = str(datetime.now().isoformat())
        prov.attrs['creator'] = 'VSI to .univ converter'
        prov.attrs['source_format'] = 'Olympus VSI'
        prov.attrs['source_file'] = str(metadata.get('source_file', 'unknown'))
        
        # Conversion history
        history = {
            'conversion_tool': 'vsi_to_univ.py',
            'timestamp': str(datetime.now().isoformat()),
            'source': str(metadata.get('source_file', 'unknown')),
        }
        
        prov.create_dataset(
            'conversion_history',
            data=json.dumps(history, indent=2),
            dtype=h5py.string_dtype('utf-8')
        )
    
    def _write_schema(self, f: h5py.File):
        """Write format schema"""
        
        f.attrs['format'] = 'univ'
        f.attrs['version'] = '1.0'
        f.attrs['schema_version'] = '1.0'


def main():
    """Command-line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Convert Olympus VSI files to .univ format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python vsi_to_univ.py slide.vsi output.univ
  python vsi_to_univ.py slide.vsi output.univ --pyramid
  python vsi_to_univ.py slide.vsi output.univ --compression gzip --level 6
  python vsi_to_univ.py slide.vsi output.univ --no-pyramid

Notes:
  - VSI files require .vsi_data folder in same directory
  - Large slides may take significant time to convert
  - Pyramid generation recommended for large images
        """
    )
    
    parser.add_argument('input', help='Input .vsi file')
    parser.add_argument('output', help='Output .univ file')
    parser.add_argument('--pyramid', action='store_true', default=True,
                       help='Create multi-resolution pyramid (default: True)')
    parser.add_argument('--no-pyramid', action='store_true',
                       help='Do not create pyramid')
    parser.add_argument('--compression', choices=['gzip', 'lzf', 'blosc', 'none'],
                       default='gzip', help='Compression type (default: gzip)')
    parser.add_argument('--level', type=int, default=4,
                       help='Compression level 1-9 for gzip (default: 4)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Override pyramid if --no-pyramid specified
    create_pyramid = args.pyramid and not args.no_pyramid
    
    # Create converter
    converter = VSIToUniv()
    
    # Convert
    success = converter.convert(
        args.input,
        args.output,
        create_pyramid=create_pyramid,
        compression=args.compression,
        compression_level=args.level
    )
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
