from __future__ import annotations

import asyncio
from collections.abc import Hashable, Iterable
from typing import Literal

type CapacityScope = Literal["request", "global"]
type ResidentCharge = tuple[Hashable, int]


class ResidentCapacityError(ValueError):
    """Raised when a resident-byte reservation can never fit its capacity."""

    def __init__(self, *, scope: CapacityScope, amount: int, capacity: int) -> None:
        self.scope = scope
        self.amount = amount
        self.capacity = capacity
        super().__init__(
            f"{scope} resident-byte capacity {capacity} cannot reserve {amount} bytes"
        )


class ResidentByteBudget:
    """Shared atomic weighted byte budget backed by one asyncio condition."""

    def __init__(self, *, capacity_bytes: int) -> None:
        _require_positive_bytes(capacity_bytes, name="capacity_bytes")
        self._capacity_bytes = capacity_bytes
        self._current_bytes = 0
        self._high_water_bytes = 0
        self._condition = asyncio.Condition()

    @property
    def capacity_bytes(self) -> int:
        return self._capacity_bytes

    @property
    def current_bytes(self) -> int:
        return self._current_bytes

    @property
    def high_water_bytes(self) -> int:
        return self._high_water_bytes

    @property
    def condition(self) -> asyncio.Condition:
        return self._condition

    def can_reserve(self, amount: int) -> bool:
        self._require_locked()
        return self._current_bytes + amount <= self._capacity_bytes

    def record_reservation(self, amount: int) -> None:
        self._require_locked()
        if not self.can_reserve(amount):
            raise RuntimeError("resident-byte budget reservation would exceed capacity")
        self._current_bytes += amount
        self._high_water_bytes = max(self._high_water_bytes, self._current_bytes)

    def record_release(self, amount: int) -> None:
        self._require_locked()
        if amount > self._current_bytes:
            raise RuntimeError("resident-byte budget release exceeds current usage")
        self._current_bytes -= amount

    def _require_locked(self) -> None:
        if not self._condition.locked():
            raise RuntimeError("resident-byte budget mutation requires its condition lock")


class RequestResidentAccount:
    """Request-local resident-byte accounting within one shared budget."""

    def __init__(
        self,
        *,
        request_id: str,
        attempt: int,
        capacity_bytes: int,
        budget: ResidentByteBudget,
    ) -> None:
        if not request_id:
            raise ValueError("request_id is required")
        if type(attempt) is not int or attempt < 0:
            raise ValueError("attempt must be a non-negative integer")
        _require_positive_bytes(capacity_bytes, name="capacity_bytes")
        if capacity_bytes > budget.capacity_bytes:
            raise ValueError("request capacity cannot exceed shared budget capacity")
        self.request_id = request_id
        self.attempt = attempt
        self._capacity_bytes = capacity_bytes
        self._budget = budget
        self._current_bytes = 0
        self._high_water_bytes = 0
        self._leases: dict[Hashable, ResidentLease] = {}

    @property
    def capacity_bytes(self) -> int:
        return self._capacity_bytes

    @property
    def current_bytes(self) -> int:
        return self._current_bytes

    @property
    def high_water_bytes(self) -> int:
        return self._high_water_bytes

    async def reserve(self, *, owner: Hashable, amount: int) -> ResidentLease:
        (lease,) = await self.reserve_many(((owner, amount),))
        return lease

    async def reserve_many(
        self, charges: Iterable[ResidentCharge]
    ) -> tuple[ResidentLease, ...]:
        normalized = tuple(charges)
        if not normalized:
            return ()
        owners: set[Hashable] = set()
        total = 0
        for owner, amount in normalized:
            hash(owner)
            if owner in owners:
                raise ValueError("resident lease owner is duplicated in one reservation")
            owners.add(owner)
            _require_positive_bytes(amount, name="amount")
            total += amount
        if total > self._capacity_bytes:
            raise ResidentCapacityError(
                scope="request", amount=total, capacity=self._capacity_bytes
            )
        if total > self._budget.capacity_bytes:
            raise ResidentCapacityError(
                scope="global", amount=total, capacity=self._budget.capacity_bytes
            )

        condition = self._budget.condition
        async with condition:
            if owners.intersection(self._leases):
                raise RuntimeError("resident lease owner already has an active reservation")
            if self._current_bytes + total > self._capacity_bytes:
                raise ResidentCapacityError(
                    scope="request",
                    amount=self._current_bytes + total,
                    capacity=self._capacity_bytes,
                )
            while not self._budget.can_reserve(total):
                await condition.wait()
                if owners.intersection(self._leases):
                    raise RuntimeError("resident lease owner already has an active reservation")
                if self._current_bytes + total > self._capacity_bytes:
                    raise ResidentCapacityError(
                        scope="request",
                        amount=self._current_bytes + total,
                        capacity=self._capacity_bytes,
                    )

            leases = tuple(ResidentLease(owner, amount) for owner, amount in normalized)
            self._current_bytes += total
            self._budget.record_reservation(total)
            self._high_water_bytes = max(self._high_water_bytes, self._current_bytes)
            self._leases.update((lease.owner, lease) for lease in leases)
            return leases

    async def release(self, lease: ResidentLease) -> None:
        if lease.released:
            raise RuntimeError("resident lease was already released")
        condition = self._budget.condition
        async with condition:
            if self._leases.get(lease.owner) is not lease:
                raise RuntimeError("resident lease is not active on this account")
            del self._leases[lease.owner]
            self._current_bytes -= lease.amount
            self._budget.record_release(lease.amount)
            object.__setattr__(lease, "_released", True)
            condition.notify_all()


class ResidentLease:
    """Read-only charge facts released only by their resident account."""

    __slots__ = ("_amount", "_owner", "_released")

    def __init__(
        self,
        owner: Hashable,
        amount: int,
    ) -> None:
        if hasattr(self, "_owner"):
            raise RuntimeError("resident lease is already initialized")
        object.__setattr__(self, "_owner", owner)
        object.__setattr__(self, "_amount", amount)
        object.__setattr__(self, "_released", False)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("resident lease state is read-only")

    @property
    def owner(self) -> Hashable:
        return self._owner

    @property
    def amount(self) -> int:
        return self._amount

    @property
    def released(self) -> bool:
        return self._released


def _require_positive_bytes(value: int, *, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


__all__ = [
    "RequestResidentAccount",
    "ResidentByteBudget",
    "ResidentCapacityError",
    "ResidentLease",
]
