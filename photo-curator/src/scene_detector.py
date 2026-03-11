"""
Scene detection using MobileNetV2 pretrained on Places365.

Classifies photos into 365 scene categories (MIT Places365 dataset) and maps
them to 10 user-friendly super-categories.  Uses PyTorch + torchvision for
inference — no GPU required, runs on CPU in ~100-200 ms per image.

Model weights (~14 MB) are downloaded once on first use and cached in the
configured model directory.  Labels file (~20 KB) is also cached there.

All processing is local — no data leaves the machine.
"""

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Places365 super-category mapping
# Each key is the user-visible super-category; values are substrings that
# match against Places365 category names.
# ---------------------------------------------------------------------------
SUPER_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "indoor": [
        "bedroom", "living_room", "kitchen", "bathroom", "dining_room",
        "office", "library", "classroom", "hospital", "lobby", "corridor",
        "closet", "laundromat", "playroom", "nursery", "attic", "basement",
        "garage", "staircase", "elevator", "waiting_room", "jail_cell",
        "sauna", "shower", "youth_hostel", "hotel_room",
    ],
    "outdoor": [
        "yard", "garden", "patio", "balcony", "courtyard", "driveway",
        "parking_lot", "picnic_area", "campsite",
    ],
    "beach": [
        "beach", "coast", "ocean", "sea", "harbor", "marina", "pier",
        "boardwalk", "lagoon", "bay", "cove", "swimming_pool",
    ],
    "mountain": [
        "mountain", "cliff", "valley", "canyon", "glacier",
        "volcano", "summit", "hill", "ridge",
    ],
    "urban": [
        "street", "city", "downtown", "alley", "crosswalk", "bridge",
        "highway", "overpass", "plaza", "square", "skyscraper",
        "building_facade", "monument", "train_station", "airport",
        "shopping_mall", "market", "parking_garage",
    ],
    "nature": [
        "forest", "jungle", "field", "meadow", "lake", "river", "waterfall",
        "swamp", "desert", "tundra", "farmland", "orchard", "vineyard",
        "botanical_garden", "national_park", "rainforest",
    ],
    "food": [
        "restaurant", "bakery", "bar", "coffee_shop", "diner",
        "cafeteria", "food_court", "bistro",
    ],
    "sports": [
        "stadium", "gymnasium", "basketball_court", "tennis_court",
        "baseball_field", "soccer_field", "golf_course", "ski_slope",
        "ice_skating", "swimming_pool", "boxing_ring", "bowling_alley",
        "racetrack",
    ],
    "night": [
        "nightclub", "discotheque", "casino",
    ],
    "event": [
        "church", "cathedral", "synagogue", "mosque", "temple",
        "wedding", "concert_hall", "auditorium", "theater",
        "amphitheater", "lecture_room",
    ],
}

# Model weights & labels — hosted by MIT / PyTorch Hub
_MODEL_URL = (
    "http://places2.csail.mit.edu/models_places365/"
    "mobilenet_v2__places365.pth.tar"
)
_LABELS_URL = (
    "https://raw.githubusercontent.com/csailvision/places365/master/"
    "categories_places365.txt"
)
_MODEL_FILENAME = "mobilenet_v2_places365.pth.tar"
_LABELS_FILENAME = "categories_places365.txt"


class SceneDetector:
    """Classify photos into scene super-categories using Places365."""

    def __init__(self, model_dir: str = "data/models", device: Optional[Any] = None):
        self.model_dir = Path(model_dir)
        self._device = device  # torch.device or None (defaults to CPU inside _ensure_model)
        self._model = None
        self._labels: Optional[List[str]] = None
        self._transform = None
        self._reverse_map: Optional[Dict[str, str]] = None  # label -> super-cat

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, image_path: str) -> Dict[str, Any]:
        """
        Classify the scene in a photo.

        Args:
            image_path: Path to the image file (JPEG/PNG/etc.).

        Returns:
            Dict with::

                {
                    "scene_category":    "beach",   # super-category
                    "scene_subcategory": "coast",   # Places365 label
                    "confidence":        0.87,
                    "top3_scenes": [
                        {"category": "coast",  "super": "beach",    "confidence": 0.87},
                        {"category": "ocean",  "super": "beach",    "confidence": 0.09},
                        {"category": "valley", "super": "mountain", "confidence": 0.02},
                    ],
                }
        """
        self._ensure_model()

        try:
            img = Image.open(image_path).convert("RGB")
        except Exception as exc:
            logger.warning("Could not open image %s: %s", image_path, exc)
            return self._fallback_result()

        import torch  # noqa: PLC0415

        tensor = self._transform(img).unsqueeze(0)  # (1, 3, 224, 224)
        tensor = tensor.to(self._device if self._device is not None else torch.device("cpu"))  # move input to same device as model

        with torch.no_grad():
            logits = self._model(tensor)
            probs = torch.nn.functional.softmax(logits, dim=1)[0]

        probs_np = probs.cpu().numpy()  # .cpu() required when tensor is on GPU
        top_indices = probs_np.argsort()[::-1][:3]

        top3 = []
        for idx in top_indices:
            raw_label = self._labels[idx]            # e.g. "/a/abbey"
            clean = raw_label.split("/")[-1]         # e.g. "abbey"
            super_cat = self._reverse_map.get(clean, "other")
            top3.append(
                {
                    "category": clean,
                    "super": super_cat,
                    "confidence": round(float(probs_np[idx]), 4),
                }
            )

        return {
            "scene_category": top3[0]["super"],
            "scene_subcategory": top3[0]["category"],
            "confidence": top3[0]["confidence"],
            "top3_scenes": top3,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_model(self):
        """Lazy-load (and download if necessary) the Places365 model."""
        if self._model is not None:
            return

        try:
            import torch  # noqa: PLC0415
            import torchvision.models as tv_models  # noqa: PLC0415
            from torchvision import transforms  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "PyTorch / torchvision is not installed. "
                "Run: pip install torch torchvision"
            ) from exc

        self.model_dir.mkdir(parents=True, exist_ok=True)

        # --- labels ---
        labels_path = self.model_dir / _LABELS_FILENAME
        if not labels_path.exists():
            logger.info("Downloading Places365 labels → %s", labels_path)
            self._download(_LABELS_URL, labels_path)

        self._labels = self._load_labels(labels_path)

        # --- reverse super-category map ---
        self._reverse_map = {}
        for super_cat, keywords in SUPER_CATEGORY_KEYWORDS.items():
            for kw in keywords:
                self._reverse_map[kw] = super_cat

        # --- model weights ---
        weights_path = self.model_dir / _MODEL_FILENAME
        if not weights_path.exists():
            logger.info(
                "Downloading Places365 MobileNetV2 weights (~14 MB) → %s",
                weights_path,
            )
            self._download(_MODEL_URL, weights_path)

        # Build MobileNetV2 with 365-class head
        model = tv_models.mobilenet_v2(weights=None)
        model.classifier[1] = torch.nn.Linear(
            model.last_channel, len(self._labels)
        )

        checkpoint = torch.load(
            str(weights_path),
            map_location=torch.device("cpu"),
            weights_only=False,
        )
        # The MIT checkpoint stores weights under 'state_dict'
        state_dict = checkpoint.get("state_dict", checkpoint)
        # Strip any 'module.' prefix added by DataParallel
        state_dict = {
            k.replace("module.", ""): v for k, v in state_dict.items()
        }
        model.load_state_dict(state_dict)
        model.eval()
        _eff_dev = self._device if self._device is not None else torch.device("cpu")
        model = model.to(_eff_dev)  # move to GPU if available
        self._model = model

        self._transform = transforms.Compose(
            [
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

        logger.info("Scene detector ready (%d Places365 categories)", len(self._labels))

    @staticmethod
    def _download(url: str, dest: Path):
        """Download a file with a simple progress log."""
        try:
            urllib.request.urlretrieve(url, str(dest))
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download {url}: {exc}") from exc

    @staticmethod
    def _load_labels(path: Path) -> List[str]:
        """Parse the Places365 categories file into a list of label strings."""
        labels: List[str] = []
        with open(path) as fh:
            for line in fh:
                parts = line.strip().split()
                if parts:
                    labels.append(parts[0])   # e.g. "/a/abbey"
        return labels

    @staticmethod
    def _fallback_result() -> Dict[str, Any]:
        return {
            "scene_category": "other",
            "scene_subcategory": None,
            "confidence": 0.0,
            "top3_scenes": [],
        }
