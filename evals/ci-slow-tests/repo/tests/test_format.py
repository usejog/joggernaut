import unittest

from shop.format import cents


class FormatTest(unittest.TestCase):
    def test_whole(self):
        self.assertEqual(cents(500), "$5.00")

    def test_small(self):
        self.assertEqual(cents(7), "$0.07")

    def test_negative(self):
        self.assertEqual(cents(-1250), "-$12.50")

    def test_zero(self):
        self.assertEqual(cents(0), "$0.00")
