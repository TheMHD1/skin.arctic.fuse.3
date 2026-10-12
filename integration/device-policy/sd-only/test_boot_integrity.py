import hashlib
from pathlib import Path
import tempfile
import unittest
from boot_integrity import check_pair


class BootIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.payload = {'kernel.img': b'reviewed kernel', 'SYSTEM': b'complete reviewed filesystem'}
        self.expected = {name: hashlib.sha256(data).hexdigest() for name, data in self.payload.items()}
        for name, data in self.payload.items():
            (self.root/name).write_bytes(data)

    def test_complete_pair_passes_without_writes(self):
        before = {name: path.read_bytes() for name, path in ((n,self.root/n) for n in self.payload)}
        self.assertTrue(check_pair(self.root, self.expected)['accepted'])
        self.assertEqual(before, {name:(self.root/name).read_bytes() for name in self.payload})

    def test_interrupted_system_fails_even_with_valid_kernel(self):
        (self.root/'SYSTEM').write_bytes(self.payload['SYSTEM'][:8])
        result = check_pair(self.root, self.expected)
        self.assertFalse(result['accepted'])
        self.assertTrue(result['files']['kernel.img']['matches'])
        self.assertFalse(result['files']['SYSTEM']['matches'])

    def test_same_size_corruption_and_release_mismatch_fail(self):
        for data in (b'x'*len(self.payload['SYSTEM']), b'old complete release'):
            (self.root/'SYSTEM').write_bytes(data)
            self.assertFalse(check_pair(self.root, self.expected)['accepted'])

    def test_missing_payload_fails(self):
        (self.root/'SYSTEM').unlink()
        self.assertEqual(check_pair(self.root,self.expected)['files']['SYSTEM']['reason'],'missing')

    def test_linked_payload_or_root_rejected(self):
        (self.root/'SYSTEM').unlink()
        (self.root/'SYSTEM').symlink_to(self.root/'kernel.img')
        with self.assertRaises(ValueError): check_pair(self.root,self.expected)
        with self.assertRaises(ValueError): check_pair('/',self.expected)
        link = self.root/'linked'; link.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError): check_pair(link,self.expected)

    def test_ambiguous_expected_pair_rejected(self):
        for invalid in ({'SYSTEM':self.expected['SYSTEM']}, {**self.expected,'dtb.img':'0'*64},
                        {**self.expected,'SYSTEM':'not a hash'}):
            with self.assertRaises(ValueError): check_pair(self.root,invalid)


if __name__ == '__main__': unittest.main()
