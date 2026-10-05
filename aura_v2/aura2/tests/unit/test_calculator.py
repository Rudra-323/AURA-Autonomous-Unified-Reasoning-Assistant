import math
import pytest
from tools.calculator import CalculatorError, safe_calculate


def test_addition():
    assert safe_calculate("2 + 2") == 4


def test_sqrt():
    assert safe_calculate("sqrt(16)") == 4.0


def test_power():
    assert safe_calculate("2 ** 5") == 32


def test_invalid_syntax():
    with pytest.raises(CalculatorError):
        safe_calculate("2 + * 2")


def test_disallowed_name():
    with pytest.raises(CalculatorError):
        safe_calculate("__import__('os').system('ls')")


def test_division_by_zero():
    with pytest.raises(CalculatorError):
        safe_calculate("1 / 0")


def test_huge_exponent_rejected():
    with pytest.raises(CalculatorError):
        safe_calculate("2 ** 100000")


def test_expression_too_long():
    with pytest.raises(CalculatorError):
        safe_calculate("1+" * 300 + "1")


def test_constant_pi():
    assert math.isclose(safe_calculate("pi"), math.pi)
