import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "preload_models", ROOT / "scripts" / "preload_models.py"
)
preload_models = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(preload_models)


class PreloadModelsTests(unittest.TestCase):
    def test_repository_manifest_is_consistent(self):
        manifest = json.loads((ROOT / "models" / "preloaded-models.json").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertLess(manifest["part_size"], 10_000_000_000)

        ids = [model["id"] for model in manifest["models"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("qwen-q5", ids)
        self.assertEqual(
            {model["id"] for model in manifest["models"] if model.get("split")},
            {"qwen-q4", "qie-text-encoder"},
        )
        for model in manifest["models"]:
            self.assertTrue(model["url"].startswith("https://"))
            self.assertFalse(Path(model["destination"]).is_absolute())
            self.assertGreater(model["size"], 0)
            self.assertEqual(len(model["sha256"]), 64)

    def test_split_model_verification_and_assembly(self):
        payload = b"immutable-model-payload"
        model = {
            "id": "fixture",
            "destination": "models/fixture/model.bin",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "split": True,
        }
        manifest = {"schema_version": 1, "part_size": 5, "models": [model]}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old_parts_dir = preload_models.PARTS_DIR
            preload_models.PARTS_DIR = root / "parts"
            try:
                preload_models.PARTS_DIR.mkdir()
                for index in range(preload_models.part_count(model, 5)):
                    start = index * 5
                    preload_models.part_path(model["id"], index).write_bytes(
                        payload[start : start + 5]
                    )

                preload_models.verify_all(manifest, root / "comfyui")
                preload_models.assemble_models(manifest, root / "comfyui")
                destination = root / "comfyui" / model["destination"]
                self.assertEqual(destination.read_bytes(), payload)

                # A second startup must be idempotent and keep the valid file.
                preload_models.assemble_models(manifest, root / "comfyui")
                self.assertEqual(destination.read_bytes(), payload)
            finally:
                preload_models.PARTS_DIR = old_parts_dir


if __name__ == "__main__":
    unittest.main()
