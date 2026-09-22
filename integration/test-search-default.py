"""Source regression for the Combined search selector default."""
import hashlib
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "1080i/Includes_Search.xml"
SOURCE_SHA = "d4f2f558910882bd9dc58c65494b42ca40c8583ff5f09e2d94ba8c559c6a8434"


def mode(item):
    entry = item.find("property[@name='mode']")
    return entry.text if entry is not None else None


class SearchDefaultTests(unittest.TestCase):
    def test_library_search_precedes_discover_and_nothing_else_changed(self):
        current = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(current).hexdigest(), SOURCE_SHA)
        root = ET.fromstring(current)
        selectors = [control for control in root.iter("control")
                     if control.get("type") == "list" and control.get("id") == "3003"]
        self.assertEqual(len(selectors), 1)
        items = selectors[0].findall("./content/item")
        modes = [mode(item) for item in items]
        self.assertEqual(modes[:2], ["search", "discover"])
        self.assertEqual(modes.count("search"), 1)
        self.assertEqual(modes.count("discover"), 1)

        # The complete accepted source hash above guards every other byte.
        # Do not compare with Git HEAD: after committing this fix HEAD already
        # contains the new order, and archive/shallow installations need no
        # historical checkout to run this regression.
        self.assertEqual(items[0].findtext("label"), "$LOCALIZE[137]$VAR[Search_Label_Results]")
        self.assertEqual(items[1].findtext("label"), "$LOCALIZE[31066]$INFO[Window(Home).Property(TMDbHelper.UserDiscover.FolderPath.Name), ,]")


if __name__ == "__main__":
    unittest.main()
