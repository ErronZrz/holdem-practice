"""牌力评估测试。"""

from app.poker.evaluator import best_five, evaluate, sort_five
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


def test_best_five_selects_strongest() -> None:
    # 从 7 张牌中选出的 5 张，牌力应等于全部 7 张的最强牌力。
    for hand in ["As Ks Qs Js Ts 2c 2d", "Ah Ad Ac Kd Kc 2s 3s", "7h 8d 9s Tc Jd 2h 4c"]:
        seven = cards(hand)
        five = best_five(seven)
        assert len(five) == 5
        assert evaluate(five) == evaluate(seven)


def test_sort_five_orders_by_hand_structure() -> None:
    # 两对：大对、小对、踢脚。
    assert [c.rank.value for c in sort_five(cards("3d Kc 3s Kh Qd"))] == [13, 13, 3, 3, 12]
    # 三条：三条在前，踢脚从大到小。
    assert [c.rank.value for c in sort_five(cards("Qd 8c 8s Kh 8d"))] == [8, 8, 8, 13, 12]
    # 普通顺子：从小到大。
    assert [c.rank.value for c in sort_five(cards("9d 6c 7s 8h 5d"))] == [5, 6, 7, 8, 9]
    # 轮子顺子：A 记低，从小到大 A 2 3 4 5。
    assert [c.rank.value for c in sort_five(cards("2d 3c 4s 5h Ad"))] == [14, 2, 3, 4, 5]
    # 葫芦：三条在前，对子在后。
    assert [c.rank.value for c in sort_five(cards("Kh Kc 8d 8h 8s"))] == [8, 8, 8, 13, 13]
