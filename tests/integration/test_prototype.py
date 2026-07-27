from __future__ import annotations

import json
import threading
from http.server import HTTPServer
from pathlib import Path
from queue import Queue
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from taiyi.domain import DifferenceKind, MergeStrategy
from taiyi.prototype import PrototypeApplication, create_prototype_server
from taiyi.providers import MockProvider
from taiyi.storage import ConflictError, Database, Repository


def _execute(
    application: PrototypeApplication, action: str, **payload: object
) -> dict[str, object]:
    return application.execute(action, payload)


def test_prototype_application_completes_core_journey(repository: Repository) -> None:
    application = PrototypeApplication(repository, MockProvider())
    empty = application.state()
    assert empty["stage"] == "identity"
    assert empty["core"] is None

    created = _execute(
        application,
        "identity.create",
        name="岔路旅人",
        description="我重视可解释的选择。",
    )
    initial_snapshot_id = created["state"]["current_snapshot"]["id"]  # type: ignore[index]
    _execute(application, "incarnation.create", name="探索者")
    _execute(application, "incarnation.create", name="守护者")
    _execute(
        application,
        "experience.add",
        incarnation_name="探索者",
        message="remember [决策原则]: 面对未知时，应优先尝试可逆的探索",
    )
    _execute(
        application,
        "experience.add",
        incarnation_name="守护者",
        message="remember [决策原则]: 面对未知时，应优先避免未经验证的风险",
    )

    compared = _execute(
        application,
        "comparison.create",
        left="探索者",
        right="守护者",
    )
    proposal = compared["result"]
    assert isinstance(proposal, dict)
    proposal_id = str(proposal["id"])
    conflict = next(
        item for item in proposal["items"] if item["kind"] == DifferenceKind.CONFLICT.value
    )

    with pytest.raises(ConflictError):
        _execute(application, "proposal.apply", proposal_id=proposal_id)

    _execute(
        application,
        "proposal.review",
        proposal_id=proposal_id,
        approve=True,
        resolutions={conflict["id"]: MergeStrategy.SYNTHESIZE.value},
        content={conflict["id"]: "在风险可控且行动可逆时探索。"},
    )
    applied = _execute(application, "proposal.apply", proposal_id=proposal_id)
    merged_snapshot = applied["result"]
    assert isinstance(merged_snapshot, dict)
    assert merged_snapshot["id"] != initial_snapshot_id

    state = applied["state"]
    assert isinstance(state, dict)
    assert state["stage"] == "rebirth"
    accepted = state["snapshots"][-1]["accepted_memories"]
    assert accepted[0]["content"] == "在风险可控且行动可逆时探索。"
    assert len(accepted[0]["source_events"]) == 2

    reborn = _execute(application, "identity.rebirth", name="协调者")
    assert reborn["state"]["stage"] == "complete"  # type: ignore[index]
    rolled_back = _execute(
        application,
        "identity.rollback",
        snapshot_id=initial_snapshot_id,
    )
    rolled_back_state = rolled_back["state"]
    assert rolled_back_state["core"]["current_snapshot_id"] == initial_snapshot_id  # type: ignore[index]
    assert len(rolled_back_state["snapshots"]) == 2  # type: ignore[arg-type]


def test_prototype_marks_stale_approved_proposal(repository: Repository) -> None:
    application = PrototypeApplication(repository, MockProvider())
    _execute(application, "identity.create", name="太一")
    _execute(application, "incarnation.create", name="左线")
    _execute(application, "incarnation.create", name="右线")
    _execute(
        application,
        "experience.add",
        incarnation_name="左线",
        message="remember [原则]: 自主优先",
    )
    _execute(
        application,
        "experience.add",
        incarnation_name="右线",
        message="remember [原则]: 安全优先",
    )
    first = _execute(application, "comparison.create", left="左线", right="右线")["result"]
    second = _execute(application, "comparison.create", left="左线", right="右线")["result"]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    _execute(application, "proposal.review", proposal_id=first["id"], approve=True)
    _execute(application, "proposal.review", proposal_id=second["id"], approve=True)
    _execute(application, "proposal.apply", proposal_id=first["id"])

    state = application.state()
    assert state["proposals"][-1]["is_stale"] is True
    with pytest.raises(ConflictError):
        _execute(application, "proposal.apply", proposal_id=second["id"])


def _start_server(data_dir: Path, queue: Queue[tuple[HTTPServer, int]]) -> None:
    database = Database(data_dir / "taiyi.sqlite3")
    database.create_schema()
    server = create_prototype_server(Repository(database), MockProvider(), 0)
    queue.put((server, int(server.server_address[1])))
    try:
        server.serve_forever(poll_interval=0.01)
    finally:
        server.server_close()
        database.engine.dispose()


def test_prototype_server_serves_local_ui_and_json_api(tmp_path: Path) -> None:
    queue: Queue[tuple[HTTPServer, int]] = Queue()
    thread = threading.Thread(target=_start_server, args=(tmp_path, queue), daemon=True)
    thread.start()
    server, port = queue.get(timeout=5)
    base_url = f"http://127.0.0.1:{port}"
    try:
        with urlopen(f"{base_url}/", timeout=5) as response:  # noqa: S310
            html = response.read().decode("utf-8")
            assert "身份演化产品原型" in html
            assert "default-src 'self'" in response.headers["Content-Security-Policy"]

        request = Request(
            f"{base_url}/api/identity",
            data=json.dumps({"name": "本地太一"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
            assert body["state"]["core"]["name"] == "本地太一"

        invalid = Request(
            f"{base_url}/api/identity",
            data=b"name=invalid",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(invalid, timeout=5)  # noqa: S310
        assert error.value.code == 400
    finally:
        server.shutdown()
        thread.join(timeout=5)
