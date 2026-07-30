from __future__ import annotations

import threading
import unittest

from backend.job_registry import JobRegistry


class JobRegistryTests(unittest.TestCase):
    def test_registry_returns_defensive_copies(self) -> None:
        registry = JobRegistry()
        original = {"status": "queued", "metadata": {"attempts": 0}}
        registry.add("job", original)
        original["metadata"]["attempts"] = 1

        copy = registry.get("job")
        self.assertIsNotNone(copy)
        copy["status"] = "tampered"
        copy["metadata"]["attempts"] = 2

        self.assertEqual("queued", registry.get("job")["status"])
        self.assertEqual(0, registry.get("job")["metadata"]["attempts"])

    def test_registry_updates_existing_jobs_only(self) -> None:
        registry = JobRegistry()
        registry.add("job", {"count": 0})

        self.assertTrue(registry.update("job", count=1))
        self.assertFalse(registry.update("missing", count=1))
        self.assertEqual(1, registry.get("job")["count"])

    def test_parallel_updates_do_not_corrupt_the_registry(self) -> None:
        registry = JobRegistry()
        for index in range(20):
            registry.add(str(index), {"status": "queued"})

        threads = [
            threading.Thread(
                target=registry.update,
                args=(str(index),),
                kwargs={"status": "completed"},
            )
            for index in range(20)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertTrue(
            all(registry.get(str(index))["status"] == "completed" for index in range(20))
        )


if __name__ == "__main__":
    unittest.main()
