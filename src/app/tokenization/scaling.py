from decimal import Decimal


def scale_local_estimate(tokens: int, multiplier: float) -> int:
    """Apply the configured decimal multiplier once, rounding upward without a float product."""
    if multiplier == 1.0:
        return tokens
    numerator, denominator = Decimal(str(multiplier)).as_integer_ratio()
    return (tokens * numerator + denominator - 1) // denominator
