import json, os, shutil, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_submission as S


class BuildSubmission(unittest.TestCase):
    def setUp(self): self.d = tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.d, ignore_errors=True)

    def test_zip_has_agent_files_at_root_and_is_reproducible(self):
        S.main(['--arm', 'A2', '--out', self.d])
        z = zipfile.ZipFile(os.path.join(self.d, 'submission.zip'))
        names = sorted(z.namelist())
        self.assertIn('agent.yaml', names); self.assertIn('eval_config.yaml', names)
        self.assertFalse(any(n.startswith('submission/') for n in names), 'files at the zip root, not in a folder')
        m1 = json.load(open(os.path.join(self.d, 'manifest.json')))
        d2 = tempfile.mkdtemp()
        try:
            S.main(['--arm', 'A2', '--out', d2])
            self.assertEqual(m1['zip_sha256'], json.load(open(os.path.join(d2, 'manifest.json')))['zip_sha256'])
        finally:
            shutil.rmtree(d2, ignore_errors=True)
        self.assertEqual(m1['model'], 'gemma-4-31b-it-qat-w4a16-ct')
        self.assertEqual(m1['evaluation']['max_time_minutes'], 4)

    def test_structural_checks_reject_two_models_and_two_roots(self):
        root = os.path.join(self.d, 's'); os.makedirs(root)
        open(os.path.join(root, 'agent.yaml'), 'w').write('model: gemma-4-31b-it-qat-w4a16-ct\n')
        open(os.path.join(root, 'sub.yaml'), 'w').write('model: gemma-4-12b-it-qat-w4a16-ct\n')
        with self.assertRaises(ValueError): S.structural_checks(root, ['agent.yaml', 'sub.yaml'])
        open(os.path.join(root, 'agent.yml'), 'w').write('model: gemma-4-31b-it-qat-w4a16-ct\n')
        with self.assertRaises(ValueError): S.structural_checks(root, ['agent.yaml', 'agent.yml'])
        open(os.path.join(root, 'x.yaml'), 'w').write('model: some-other-model\n')
        with self.assertRaises(ValueError): S.structural_checks(root, ['agent.yaml', 'x.yaml'])


if __name__ == '__main__':
    unittest.main()
