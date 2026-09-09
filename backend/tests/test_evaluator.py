"""牌力评估测试。"""

from app.poker.evaluator import evaluate
from app.poker.hand import HandCategory

from .helpers import cards


def _category(hand: str) -> HandCategory:
    return evaluate(cards(hand)).category


def test_high_card() -> None:
    assert _category("As Kd 7h 3c 2s") == HandCategory.HIGH_CARD


def test_one_pair() -> None:
    assert _category("As Ad 7h 3c 2s") == HandCategory.ONE_PAIR


def test_two_pair() -> None:
    assert _category("As Ad Kh Kd 2s") == HandCategory.TWO_PAIR


def test_three_of_a_kind() -> None:
    assert _category("As Ad Ah 3c 2s") == HandCategory.THREE_OF_A_KIND


def test_straight() -> None:
    assert _category("5s 6d 7h 8c 9s") == HandCategory.STRAIGHT


def test_wheel_straight() -> None:
    assert _category("As 2d 3h 4c 5s") == HandCategory.STRAIGHT


def test_flush() -> None:
    assert _category("As Ks 7s 3s 2s") == HandCategory.FLUSH


def test_full_house() -> None:
    assert _category("As Ad Ah Kd Ks") == HandCategory.FULL_HOUSE


def test_four_of_a_kind() -> None:
    assert _category("As Ad Ah Ac 2s") == HandCategory.FOUR_OF_A_KIND


def test_straight_flush() -> None:
    assert _category("5s 6s 7s 8s 9s") == HandCategory.STRAIGHT_FLUSH


def test_royal_flush() -> None:
    assert _category("As Ks Qs Js Ts") == HandCategory.STRAIGHT_FLUSH


def test_best_five_from_seven() -> None:
    # 7 张里应选出同花顺，而不是两对。
    hand = "As Ks Qs Js Ts 2c 2d"
    rank = evaluate(cards(hand))
    assert rank.category == HandCategory.STRAIGHT_FLUSH


def test_ordering() -> None:
    assert evaluate(cards("As Ad Ah Ac Ks")) > evaluate(cards("Ks Kd Kh Kc As"))
    assert evaluate(cards("As Ad 7h 3c 2s")) > evaluate(cards("Kd Kh 7h 3c 2s"))
    assert evaluate(cards("As Kd Qh Jc 9s")) > evaluate(cards("As Kd Qh Jc 8s"))
