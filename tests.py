import unittest
from debian import debtags
from debdata import patches

class TestPatches(unittest.TestCase):
    def test_simplify(self):
        ps = patches.PatchSet()
        ps.add("vzdump", set(("admin::backup", "interface::commandline",)))

        db = debtags.DB()
        db.insert("vzdump", set(("admin::backup", "interface::commandline", "role::program")))

        ps1 = ps.simplified(db)

        self.assertEquals(ps1, dict())
