class Cart:
    def __init__(self, prices):
        self.prices = prices
        self.items = {}

    def add(self, sku, qty=1):
        if qty <= 0:
            raise ValueError("qty must be positive")
        self.items[sku] = self.items.get(sku, 0) + qty

    def remove(self, sku):
        self.items.pop(sku, None)

    def total(self, discount_percent=0):
        subtotal = sum(self.prices.price(s) * q for s, q in self.items.items())
        return subtotal - (subtotal * discount_percent) // 100
