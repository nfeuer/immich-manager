"""
Face recognition engine using the face_recognition library (wraps dlib).

Handles:
- Face detection with 128-dimensional embeddings
- Greedy clustering of embeddings into identity groups
- Euclidean distance comparison between embeddings

All processing is local — no data leaves the machine.
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Lazy import so missing dependency doesn't crash the whole service.
_face_recognition_lib = None


def _get_fr():
    """Return the face_recognition module, importing lazily."""
    global _face_recognition_lib
    if _face_recognition_lib is None:
        try:
            import face_recognition  # noqa: PLC0415
            _face_recognition_lib = face_recognition
        except ImportError as exc:
            raise ImportError(
                "face_recognition is not installed. "
                "Run: pip install face_recognition"
            ) from exc
    return _face_recognition_lib


class FaceRecognitionEngine:
    """Detect faces and generate 128-dim embeddings for identity matching."""

    #: Euclidean distance below which two faces are considered the same person.
    DISTANCE_THRESHOLD = 0.6

    def __init__(self, model: str = "small", use_cuda: bool = False):
        """
        Args:
            model: ``"small"`` (5-point landmarks, faster) or
                   ``"large"`` (68-point landmarks, slightly more accurate).
            use_cuda: Use dlib CNN face detector (GPU-accelerated when dlib is
                      CUDA-compiled).  Falls back to HOG if False.
        """
        self.model = model
        self.use_cuda = use_cuda
        # Eagerly validate the import so startup fails fast if dlib is missing.
        _get_fr()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_and_encode(self, image_path: str) -> List[Dict[str, Any]]:
        """
        Detect all faces in an image and return their embeddings.

        Args:
            image_path: Path to the image file.

        Returns:
            List of dicts, one per detected face::

                {
                    "embedding": np.ndarray,  # shape (128,), dtype float64
                    "bbox": (x, y, w, h),     # pixel coords, top-left origin
                    "confidence": float,       # placeholder 1.0 (dlib HOG)
                }
        """
        fr = _get_fr()
        try:
            img = fr.load_image_file(image_path)
        except Exception as exc:
            logger.warning("Could not load image %s: %s", image_path, exc)
            return []

        # HOG-based detector: CPU-only. CNN detector uses GPU if dlib has CUDA.
        detection_model = "cnn" if self.use_cuda else "hog"
        locations = fr.face_locations(img, model=detection_model)
        if not locations:
            return []

        encodings = fr.face_encodings(
            img,
            known_face_locations=locations,
            num_jitters=1,
            model=self.model,
        )

        results: List[Dict[str, Any]] = []
        for (top, right, bottom, left), enc in zip(locations, encodings):
            results.append(
                {
                    "embedding": enc,  # numpy array (128,)
                    "bbox": (left, top, right - left, bottom - top),
                    "confidence": 1.0,
                }
            )
        return results

    @staticmethod
    def embedding_distance(a: np.ndarray, b: np.ndarray) -> float:
        """Return the Euclidean distance between two 128-dim embeddings.

        Lower values mean more similar faces.  Faces from the same person
        typically score below ``DISTANCE_THRESHOLD`` (0.6).
        """
        return float(np.linalg.norm(a - b))

    @staticmethod
    def cluster_embeddings(
        embeddings: List[np.ndarray],
        embedding_ids: Optional[List[int]] = None,
        threshold: float = DISTANCE_THRESHOLD,
    ) -> Dict[int, int]:
        """
        Group face embeddings into identity clusters using greedy nearest-centroid.

        Args:
            embeddings:    List of 128-dim numpy arrays.
            embedding_ids: Optional list of database row IDs corresponding to
                           each embedding (same length as *embeddings*).
                           If omitted, 0-based indices are used.
            threshold:     Maximum Euclidean distance to be considered the same
                           person.

        Returns:
            Mapping of ``embedding_id -> cluster_id`` where cluster IDs are
            arbitrary positive integers assigned in encounter order.
        """
        if not embeddings:
            return {}

        ids = embedding_ids if embedding_ids is not None else list(range(len(embeddings)))
        assignment: Dict[int, int] = {}
        # Each cluster is represented by its mean embedding (centroid).
        centroids: List[np.ndarray] = []  # index == cluster_id
        centroid_sizes: List[int] = []

        for db_id, emb in zip(ids, embeddings):
            best_cluster = -1
            best_dist = threshold

            for cid, centroid in enumerate(centroids):
                dist = float(np.linalg.norm(emb - centroid))
                if dist < best_dist:
                    best_dist = dist
                    best_cluster = cid

            if best_cluster >= 0:
                # Assign to existing cluster and update centroid (running mean).
                assignment[db_id] = best_cluster
                n = centroid_sizes[best_cluster]
                centroids[best_cluster] = (centroids[best_cluster] * n + emb) / (n + 1)
                centroid_sizes[best_cluster] += 1
            else:
                # Start a new cluster.
                new_cid = len(centroids)
                assignment[db_id] = new_cid
                centroids.append(emb.copy())
                centroid_sizes.append(1)

        return assignment

    @staticmethod
    def embedding_to_bytes(embedding: np.ndarray) -> bytes:
        """Serialise a (128,) float64 array to bytes for SQLite BLOB storage."""
        return embedding.astype(np.float64).tobytes()

    @staticmethod
    def bytes_to_embedding(data: bytes) -> np.ndarray:
        """Deserialise bytes from SQLite BLOB back to a (128,) float64 array."""
        return np.frombuffer(data, dtype=np.float64)
