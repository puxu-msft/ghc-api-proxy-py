from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.generation_identity import parse_generation_id


class SystemctlError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class UnitStatus:
    unit: str
    active_state: str
    sub_state: str
    main_pid: int
    invocation_id: str
    control_group: str


def generation_unit(generation_id: str) -> str:
    parse_generation_id(generation_id)
    return f"ghc-api-proxy-generation@{generation_id}.service"


class SystemctlAdapter:
    def __init__(self, executable: str = "systemctl") -> None:
        self._executable = executable

    async def start_generation(self, generation_id: str) -> None:
        await self._run("start", generation_unit(generation_id))

    async def stop_generation(self, generation_id: str) -> None:
        await self._run("stop", generation_unit(generation_id))

    async def signal_generation(self, generation_id: str, signal_name: str) -> None:
        if signal_name not in {"SIGUSR1", "SIGUSR2", "SIGTERM", "SIGINT"}:
            raise ValueError(f"unsupported generation signal: {signal_name}")
        await self._run(
            "kill",
            "--kill-whom=main",
            f"--signal={signal_name}",
            generation_unit(generation_id),
        )

    async def show_generation(self, generation_id: str) -> UnitStatus:
        unit = generation_unit(generation_id)
        output = await self._run(
            "show",
            "--property=ActiveState,SubState,MainPID,InvocationID,ControlGroup",
            unit,
        )
        values = dict(
            line.split("=", 1)
            for line in output.splitlines()
            if "=" in line
        )
        return UnitStatus(
            unit=unit,
            active_state=values.get("ActiveState", "unknown"),
            sub_state=values.get("SubState", "unknown"),
            main_pid=int(values.get("MainPID", "0")),
            invocation_id=values.get("InvocationID", ""),
            control_group=values.get("ControlGroup", ""),
        )

    async def _run(self, *arguments: str) -> str:
        process = await asyncio.create_subprocess_exec(
            self._executable,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise SystemctlError(
                f"systemctl {' '.join(arguments)} failed ({process.returncode}): "
                f"{stderr.decode(errors='replace').strip()}"
            )
        return stdout.decode()
