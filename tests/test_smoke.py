"""Smoke tests to verify basic project imports and structure."""
import sys
import os

# Add source directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'server-manager', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'photo-curator', 'src'))


def test_server_manager_config_imports():
    """Verify server-manager config module is importable."""
    import config  # noqa: F401


def test_server_manager_logging_imports():
    """Verify server-manager logging_config module is importable."""
    import logging_config  # noqa: F401


def test_photo_curator_logging_imports():
    """Verify photo-curator logging_config module is importable."""
    # Reset to only photo-curator src on path to avoid collision
    import importlib
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "photo_curator_logging",
        os.path.join(os.path.dirname(__file__), '..', 'photo-curator', 'src', 'logging_config.py')
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod is not None


def _load_module(name, filename):
    """Helper: load a photo-curator src module by filename."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.join(os.path.dirname(__file__), '..', 'photo-curator', 'src', filename)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_face_recognition_engine_importable():
    """Verify face_recognition_engine module is importable and exposes expected API."""
    mod = _load_module("face_recognition_engine", "face_recognition_engine.py")
    assert hasattr(mod, "FaceRecognitionEngine")
    engine_cls = mod.FaceRecognitionEngine
    assert hasattr(engine_cls, "embedding_distance")
    assert hasattr(engine_cls, "cluster_embeddings")
    assert hasattr(engine_cls, "embedding_to_bytes")
    assert hasattr(engine_cls, "bytes_to_embedding")


def test_face_recognition_engine_roundtrip():
    """Verify embedding serialisation round-trips correctly."""
    import numpy as np
    mod = _load_module("face_recognition_engine", "face_recognition_engine.py")
    FRE = mod.FaceRecognitionEngine
    original = np.random.rand(128).astype(np.float64)
    recovered = FRE.bytes_to_embedding(FRE.embedding_to_bytes(original))
    assert recovered.shape == (128,)
    assert np.allclose(original, recovered)


def test_face_recognition_engine_clustering():
    """Verify greedy clustering groups identical embeddings correctly."""
    import numpy as np
    mod = _load_module("face_recognition_engine", "face_recognition_engine.py")
    FRE = mod.FaceRecognitionEngine

    base = np.random.rand(128).astype(np.float64)
    # Two embeddings very close to base → same cluster
    close_a = base + np.random.rand(128) * 0.01
    close_b = base + np.random.rand(128) * 0.01
    # One embedding very different → different cluster
    far = np.random.rand(128).astype(np.float64) * 10

    embeddings = [base, close_a, close_b, far]
    ids = [10, 11, 12, 13]
    assignment = FRE.cluster_embeddings(embeddings, embedding_ids=ids, threshold=0.6)

    # base, close_a, close_b should share a cluster; far should be alone
    assert assignment[10] == assignment[11] == assignment[12]
    assert assignment[13] != assignment[10]


def test_scene_detector_importable():
    """Verify scene_detector module is importable and exposes expected API."""
    mod = _load_module("scene_detector", "scene_detector.py")
    assert hasattr(mod, "SceneDetector")
    assert hasattr(mod, "SUPER_CATEGORY_KEYWORDS")
    sd_cls = mod.SceneDetector
    assert hasattr(sd_cls, "classify")
