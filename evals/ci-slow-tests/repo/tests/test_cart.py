import unittest

from shop.cart import Cart
from shop.prices import PriceServer


class CartTest(unittest.TestCase):
    def setUp(self):
        self.cart = Cart(PriceServer())

    def test_empty_total(self):
        self.assertEqual(self.cart.total(), 0)

    def test_single_item(self):
        self.cart.add("apple")
        self.assertEqual(self.cart.total(), 120)

    def test_quantities(self):
        self.cart.add("apple", 3)
        self.cart.add("pear", 2)
        self.assertEqual(self.cart.total(), 540)

    def test_add_twice(self):
        self.cart.add("fig")
        self.cart.add("fig")
        self.assertEqual(self.cart.total(), 500)

    def test_remove(self):
        self.cart.add("apple")
        self.cart.add("plum")
        self.cart.remove("apple")
        self.assertEqual(self.cart.total(), 75)

    def test_discount(self):
        self.cart.add("fig", 2)
        self.cart.add("pear")
        self.assertEqual(self.cart.total(discount_percent=10), 531)

    def test_discount_rounds_down(self):
        self.cart.add("plum")
        self.assertEqual(self.cart.total(discount_percent=33), 51)

    def test_unknown_sku(self):
        self.cart.add("kiwi")
        with self.assertRaises(KeyError):
            self.cart.total()

    def test_bad_quantity(self):
        with self.assertRaises(ValueError):
            self.cart.add("apple", 0)

    def test_many_items(self):
        for sku in ("apple", "pear", "fig", "plum"):
            self.cart.add(sku, 2)
        self.assertEqual(self.cart.total(), 1070)


if __name__ == "__main__":
    unittest.main()
