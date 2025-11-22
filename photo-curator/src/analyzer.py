"""
Photo analysis using OpenCV and image processing
Analyzes quality, faces, composition, and duplicates
"""

import cv2
import numpy as np
from PIL import Image
import imagehash
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PhotoAnalyzer:
    """Analyzes photos for quality scoring"""

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize photo analyzer

        Args:
            config: Configuration dictionary with weights
        """
        self.config = config or {}

        # Load face detection cascade
        self.face_cascade = None
        self.eye_cascade = None
        self.smile_cascade = None

        try:
            # Try to load Haar cascades for face detection
            cascade_path = cv2.data.haarcascades
            self.face_cascade = cv2.CascadeClassifier(
                cascade_path + 'haarcascade_frontalface_default.xml'
            )
            self.eye_cascade = cv2.CascadeClassifier(
                cascade_path + 'haarcascade_eye.xml'
            )
            self.smile_cascade = cv2.CascadeClassifier(
                cascade_path + 'haarcascade_smile.xml'
            )
        except Exception as e:
            logger.warning(f"Could not load face detection cascades: {e}")

    def analyze_photo(self, image_path: str) -> Dict[str, Any]:
        """
        Complete photo analysis

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with scores and details
        """
        try:
            # Load image
            img = cv2.imread(image_path)
            if img is None:
                return self._error_result("Could not load image")

            # Run all analyses
            blur_score = self.calculate_blur_score(img)
            exposure_score = self.calculate_exposure_score(img)
            composition_score = self.calculate_composition_score(img)
            face_score, face_count = self.detect_and_score_faces(img)

            # Calculate perceptual hash for duplicate detection
            try:
                pil_img = Image.open(image_path)
                img_hash = str(imagehash.phash(pil_img))
            except Exception:
                img_hash = None

            # Get image dimensions
            height, width = img.shape[:2]

            # Calculate weighted final score
            weights = self.config.get('scoring', {}).get('weights', {
                'technical_quality': 0.3,
                'faces': 0.3,
                'uniqueness': 0.2,
                'aesthetic': 0.2
            })

            # Normalize scores
            technical_score = (blur_score + exposure_score) / 2
            aesthetic_score = composition_score

            final_score = (
                weights['technical_quality'] * technical_score +
                weights['faces'] * face_score +
                weights['aesthetic'] * aesthetic_score
            )

            return {
                'score': round(final_score, 3),
                'technical_quality': round(technical_score, 3),
                'blur_score': round(blur_score, 3),
                'exposure_score': round(exposure_score, 3),
                'composition_score': round(composition_score, 3),
                'face_score': round(face_score, 3),
                'face_count': face_count,
                'perceptual_hash': img_hash,
                'width': width,
                'height': height,
                'megapixels': round((width * height) / 1_000_000, 2),
                'success': True
            }

        except Exception as e:
            logger.error(f"Error analyzing {image_path}: {e}")
            return self._error_result(str(e))

    def calculate_blur_score(self, img: np.ndarray) -> float:
        """
        Calculate blur score using Laplacian variance
        Higher score = sharper image

        Args:
            img: OpenCV image

        Returns:
            Blur score (0-1, higher is better)
        """
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Calculate Laplacian variance
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

            # Normalize to 0-1 scale
            # Typical sharp images have variance > 100
            # Blurry images have variance < 100
            normalized_score = min(laplacian_var / 500, 1.0)

            return normalized_score

        except Exception as e:
            logger.error(f"Error calculating blur: {e}")
            return 0.5

    def calculate_exposure_score(self, img: np.ndarray) -> float:
        """
        Calculate exposure quality using histogram analysis
        Checks for good contrast and no clipping

        Args:
            img: OpenCV image

        Returns:
            Exposure score (0-1, higher is better)
        """
        try:
            # Convert to grayscale for histogram
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Calculate histogram
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            hist = hist.flatten()

            # Check for clipping (too many pixels at 0 or 255)
            total_pixels = gray.shape[0] * gray.shape[1]
            black_clipped = hist[0] / total_pixels
            white_clipped = hist[255] / total_pixels

            clipping_penalty = (black_clipped + white_clipped) * 2

            # Check for good distribution (contrast)
            # Calculate standard deviation of histogram
            std_dev = np.std(hist)
            contrast_score = min(std_dev / 50, 1.0)

            # Combined score
            exposure_score = max(0, 1.0 - clipping_penalty) * contrast_score

            return exposure_score

        except Exception as e:
            logger.error(f"Error calculating exposure: {e}")
            return 0.5

    def calculate_composition_score(self, img: np.ndarray) -> float:
        """
        Calculate composition score using rule of thirds
        Checks if image follows compositional guidelines

        Args:
            img: OpenCV image

        Returns:
            Composition score (0-1, higher is better)
        """
        try:
            height, width = img.shape[:2]

            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Detect edges (subject matter)
            edges = cv2.Canny(gray, 50, 150)

            # Define rule of thirds points
            third_h = height // 3
            third_w = width // 3

            roi_points = [
                (third_w, third_h),      # Top-left third
                (2 * third_w, third_h),  # Top-right third
                (third_w, 2 * third_h),  # Bottom-left third
                (2 * third_w, 2 * third_h)  # Bottom-right third
            ]

            # Check for edge density at rule of thirds points
            roi_size = 50  # Size of region to check
            total_score = 0

            for x, y in roi_points:
                # Extract region
                x1 = max(0, x - roi_size // 2)
                y1 = max(0, y - roi_size // 2)
                x2 = min(width, x + roi_size // 2)
                y2 = min(height, y + roi_size // 2)

                roi = edges[y1:y2, x1:x2]

                # Count edge pixels in ROI
                edge_density = np.sum(roi > 0) / (roi_size * roi_size)
                total_score += edge_density

            # Normalize
            composition_score = min(total_score / 4, 1.0)

            return composition_score

        except Exception as e:
            logger.error(f"Error calculating composition: {e}")
            return 0.5

    def detect_and_score_faces(self, img: np.ndarray) -> Tuple[float, int]:
        """
        Detect faces and score based on presence and quality

        Args:
            img: OpenCV image

        Returns:
            Tuple of (face_score, face_count)
        """
        if self.face_cascade is None:
            return 0.5, 0

        try:
            # Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Detect faces
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )

            face_count = len(faces)

            if face_count == 0:
                # No faces - neutral score
                return 0.5, 0

            # Score based on number of faces
            # 1-3 faces = good, more faces may be group photos
            if face_count == 1:
                base_score = 1.0
            elif face_count <= 3:
                base_score = 0.9
            elif face_count <= 6:
                base_score = 0.7
            else:
                base_score = 0.6

            # Check for eyes and smiles in faces
            quality_bonus = 0
            for (x, y, w, h) in faces:
                face_roi_gray = gray[y:y+h, x:x+w]

                # Check for eyes
                if self.eye_cascade is not None:
                    eyes = self.eye_cascade.detectMultiScale(face_roi_gray)
                    if len(eyes) >= 2:
                        quality_bonus += 0.1

                # Check for smile
                if self.smile_cascade is not None:
                    smiles = self.smile_cascade.detectMultiScale(
                        face_roi_gray,
                        scaleFactor=1.8,
                        minNeighbors=20
                    )
                    if len(smiles) > 0:
                        quality_bonus += 0.1

            # Normalize bonus
            quality_bonus = min(quality_bonus / face_count, 0.2)

            final_score = min(base_score + quality_bonus, 1.0)

            return final_score, face_count

        except Exception as e:
            logger.error(f"Error detecting faces: {e}")
            return 0.5, 0

    def calculate_perceptual_hash(self, image_path: str) -> Optional[str]:
        """
        Calculate perceptual hash for duplicate detection

        Args:
            image_path: Path to image

        Returns:
            Perceptual hash string or None
        """
        try:
            img = Image.open(image_path)
            return str(imagehash.phash(img))
        except Exception as e:
            logger.error(f"Error calculating hash: {e}")
            return None

    def find_duplicates(
        self,
        photos: List[Dict[str, Any]],
        threshold: int = 5
    ) -> List[List[str]]:
        """
        Find duplicate photos based on perceptual hashing

        Args:
            photos: List of photo dictionaries with 'id' and 'perceptual_hash'
            threshold: Hamming distance threshold (lower = more similar)

        Returns:
            List of duplicate groups (each group is list of photo IDs)
        """
        duplicates = []
        processed = set()

        for i, photo1 in enumerate(photos):
            if photo1['id'] in processed:
                continue

            hash1_str = photo1.get('perceptual_hash')
            if not hash1_str:
                continue

            hash1 = imagehash.hex_to_hash(hash1_str)
            group = [photo1['id']]

            # Compare with remaining photos
            for photo2 in photos[i+1:]:
                if photo2['id'] in processed:
                    continue

                hash2_str = photo2.get('perceptual_hash')
                if not hash2_str:
                    continue

                hash2 = imagehash.hex_to_hash(hash2_str)

                # Calculate Hamming distance
                distance = hash1 - hash2

                if distance <= threshold:
                    group.append(photo2['id'])
                    processed.add(photo2['id'])

            if len(group) > 1:
                duplicates.append(group)
                processed.add(photo1['id'])

        return duplicates

    def _error_result(self, error: str) -> Dict[str, Any]:
        """Return error result"""
        return {
            'score': 0.0,
            'success': False,
            'error': error
        }


def batch_analyze_photos(
    photo_paths: List[str],
    analyzer: PhotoAnalyzer,
    batch_size: int = 10
) -> List[Dict[str, Any]]:
    """
    Analyze multiple photos in batches

    Args:
        photo_paths: List of image paths
        analyzer: PhotoAnalyzer instance
        batch_size: Number of photos to process at once

    Returns:
        List of analysis results
    """
    results = []

    for i in range(0, len(photo_paths), batch_size):
        batch = photo_paths[i:i+batch_size]

        for path in batch:
            result = analyzer.analyze_photo(path)
            result['path'] = path
            results.append(result)

    return results
