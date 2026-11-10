import unittest

from power import paired_n, unpaired_n


class Power(unittest.TestCase):
    def test_textbook_unpaired(self):
        # 0.5 vs 0.6 at alpha 0.05 / power 0.8 needs about 385-390 per arm by the normal approximation
        self.assertTrue(380 <= unpaired_n(0.5, 0.6) <= 392)

    def test_paired_needs_fewer_tasks_than_unpaired(self):
        self.assertLess(paired_n(0.10, 0.15), unpaired_n(0.18, 0.28))

    def test_more_discordance_needs_more_tasks(self):
        self.assertLess(paired_n(0.05, 0.10), paired_n(0.05, 0.15))

    def test_discordance_below_delta_is_refused(self):
        with self.assertRaises(ValueError):
            paired_n(0.10, 0.05)


if __name__ == '__main__':
    unittest.main()
