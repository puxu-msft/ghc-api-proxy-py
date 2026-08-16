"""Talking to systemd: the readiness protocol outward, and unit control inward.

Only what is systemd-specific lives here. The listener set it hands over is not — standalone binds
its own and uses the same type, so `lifecycle.activation` sits a level up.
"""
