class PassthroughRateLimiter:
    async def acquire(self) -> float:
        return 0.0

    def report_success(self) -> None:
        return