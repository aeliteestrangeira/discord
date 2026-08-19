from __future__ import annotations

import unittest

suite = unittest.defaultTestLoader.discover("test", pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
