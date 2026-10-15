import unittest
from support_qa_tracks import support_qa_entry_details

class EntryEvidenceAuditTests(unittest.TestCase):
    def test_quote(self):
        details = support_qa_entry_details({"title":"IT Support","description":"No experience required. Handle IT tickets."})
        self.assertEqual(details["basis"],"description")
        self.assertEqual(details["quote"],"No experience required")

if __name__ == "__main__":
    unittest.main()
