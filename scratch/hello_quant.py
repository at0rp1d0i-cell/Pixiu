def calculate_ma(prices, period):
    """Calculate moving average for a given price list and period."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


if __name__ == "__main__":
    result = calculate_ma([1, 2, 3, 4, 5], 3)
    print(f"calculate_ma([1, 2, 3, 4, 5], 3) = {result}")
