def cents(amount):
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    return "%s$%d.%02d" % (sign, amount // 100, amount % 100)
