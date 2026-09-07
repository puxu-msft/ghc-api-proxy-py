from decimal import ROUND_CEILING, Decimal


def scale_local_estimate(tokens: int, multiplier: float) -> int:
    """Compatibility wrapper for the sole public prediction finalization boundary."""
    return finalize_local_prediction(tokens, multiplier)


def finalize_local_prediction(value: int | float, multiplier: float) -> int:
    """Multiply in decimal, round upward once, then enforce the public minimum."""
    if type(value) not in (int, float) or not Decimal(str(value)).is_finite():
        raise ValueError("value must be a finite int or float")
    if (
        type(multiplier) not in (int, float)
        or not Decimal(str(multiplier)).is_finite()
        or multiplier < 1.0
    ):
        raise ValueError("multiplier must be a finite int or float of at least one")
    rounded = (Decimal(str(value)) * Decimal(str(multiplier))).to_integral_value(
        rounding=ROUND_CEILING
    )
    return max(1, int(rounded))
