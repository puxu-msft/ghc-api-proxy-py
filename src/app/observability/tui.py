from dataclasses import dataclass, replace
from typing import Literal

from textual.app import App

type TuiView = Literal["collapsed", "panel_list", "detail"]


@dataclass(frozen=True, slots=True)
class TuiState:
    view: TuiView = "collapsed"
    requests: tuple[str, ...] = ()
    selected_index: int | None = None


@dataclass(frozen=True, slots=True)
class AddRequest:
    request_id: str


@dataclass(frozen=True, slots=True)
class Expand:
    pass


@dataclass(frozen=True, slots=True)
class EnterDetail:
    index: int


@dataclass(frozen=True, slots=True)
class ExitView:
    pass


type TuiAction = AddRequest | Expand | EnterDetail | ExitView


def reduce_tui(state: TuiState, action: TuiAction) -> TuiState:
    match action:
        case AddRequest(request_id=request_id):
            return replace(state, requests=(*state.requests, request_id))
        case Expand():
            return replace(state, view="panel_list")
        case EnterDetail(index=index):
            return replace(state, view="detail", selected_index=index)
        case ExitView():
            return replace(state, view="collapsed", selected_index=None)


class ProxyTui(App[None]):
    """Textual application shell; runtime subscription remains opt-in."""
