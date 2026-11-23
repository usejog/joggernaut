import unittest
from unittest import mock

from shop.prices import PriceServer


class PriceServerTest(unittest.TestCase):
    """The price server itself: these tests are about the server, so it is real."""

    def test_known_price(self):
        self.assertEqual(PriceServer().price("apple"), 120)

    def test_unknown_price(self):
        with self.assertRaises(KeyError):
            PriceServer().price("kiwi")

    def test_custom_prices(self):
        with mock.patch("shop.prices.time.sleep"):
            self.assertEqual(PriceServer({"x": 5}).price("x"), 5)
