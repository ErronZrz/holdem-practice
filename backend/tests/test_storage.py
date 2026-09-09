"""持久化层测试：Session / Hand 落库与 Hand History JSON 往返。"""

import json

from app.storage import repository
from app.storage.db import get_db, init_db


def test_session_and_hand_roundtrip(tmp_path) -> None:
    init_db(str(tmp_path / "test.db"))
    db = next(get_db())
    try:
        session = repository.create_session(
            db,
            num_players=2,
            human_seat=0,
            small_blind=5,
            big_blind=10,
            starting_stack=1000,
            target_hands=10,
            bot_strategy="heuristic",
        )
        db.commit()

        history = {
            "hand_number": 1,
            "board": ["As", "Kd", "2c"],
            "winners": [0],
            "showdown": True,
            "net": {"0": 15, "1": -15},
        }
        hand = repository.add_hand(
            db,
            session_id=session.id,
            hand_number=1,
            history_json=json.dumps(history, ensure_ascii=False),
            net=15,
        )
        db.commit()

        loaded = repository.get_session(db, session.id)
        assert loaded is not None
        assert loaded.target_hands == 10
        assert loaded.hands_played == 0

        hands = repository.list_hands(db, session.id)
        assert len(hands) == 1
        assert hands[0].net == 15
        assert json.loads(hands[0].history_json)["winners"] == [0]

        fetched = repository.get_hand(db, hand.id)
        assert fetched is not None
        assert fetched.hand_number == 1
    finally:
        db.close()


def test_list_sessions_order(tmp_path) -> None:
    init_db(str(tmp_path / "test.db"))
    db = next(get_db())
    try:
        first = repository.create_session(
            db, num_players=2, human_seat=0, small_blind=5, big_blind=10,
            starting_stack=1000, target_hands=5, bot_strategy="random",
        )
        second = repository.create_session(
            db, num_players=3, human_seat=0, small_blind=5, big_blind=10,
            starting_stack=1000, target_hands=5, bot_strategy="heuristic",
        )
        db.commit()
        sessions = repository.list_sessions(db)
        assert len(sessions) >= 2
        assert {s.id for s in sessions} >= {first.id, second.id}
    finally:
        db.close()
