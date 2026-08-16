from app.observability.tui import (
    AddRequest,
    EnterDetail,
    ExitView,
    Expand,
    TuiState,
    reduce_tui,
)


def test_tui_reducer_transitions_views_and_requests() -> None:
    state = TuiState()
    state = reduce_tui(state, AddRequest("req-1"))
    state = reduce_tui(state, Expand())
    assert state.view == "panel_list"
    assert state.requests == ("req-1",)
    state = reduce_tui(state, EnterDetail(0))
    assert state.view == "detail"
    state = reduce_tui(state, ExitView())
    assert state.view == "collapsed"