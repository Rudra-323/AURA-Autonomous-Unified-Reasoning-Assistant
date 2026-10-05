"""Safe arithmetic calculator — AST-walked, never eval(). See v1 notes;
unchanged here since it does no I/O and has no async benefit."""

from __future__ import annotations

import ast
import math
import operator
from typing import Callable

from langchain_core.tools import tool

from utils.errors import ToolExecutionError
from utils.logging import get_logger

log = get_logger("tools.calculator")

MAX_EXPRESSION_LENGTH = 200
MAX_EXPONENT = 1000

_ALLOWED_BINARY_OPS: dict[type, Callable] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_ALLOWED_UNARY_OPS: dict[type, Callable] = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ALLOWED_FUNCTIONS: dict[str, Callable] = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "sin": math.sin, "cos": math.cos,
    "tan": math.tan, "log": math.log, "log10": math.log10, "exp": math.exp,
    "floor": math.floor, "ceil": math.ceil,
}
_ALLOWED_CONSTANTS = {"pi": math.pi, "e": math.e}


class CalculatorError(ToolExecutionError):
    pass


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise CalculatorError(f"Unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINARY_OPS:
            raise CalculatorError(f"Operator not allowed: {op_type.__name__}")
        left, right = _eval_node(node.left), _eval_node(node.right)
        if op_type is ast.Pow and abs(right) > MAX_EXPONENT:
            raise CalculatorError(f"Exponent too large (max {MAX_EXPONENT})")
        try:
            result = _ALLOWED_BINARY_OPS[op_type](left, right)
        except ZeroDivisionError as exc:
            raise CalculatorError("Division by zero") from exc
        if isinstance(result, complex) or not math.isfinite(result):
            raise CalculatorError("Result is not a finite real number")
        return result
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARY_OPS:
            raise CalculatorError(f"Operator not allowed: {op_type.__name__}")
        return _ALLOWED_UNARY_OPS[op_type](_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
            raise CalculatorError("Function not allowed")
        if node.keywords:
            raise CalculatorError("Keyword arguments not allowed")
        args = [_eval_node(a) for a in node.args]
        try:
            result = _ALLOWED_FUNCTIONS[node.func.id](*args)
        except (ValueError, TypeError) as exc:
            raise CalculatorError(f"Invalid arguments for {node.func.id}: {exc}") from exc
        if not math.isfinite(result):
            raise CalculatorError("Result is not a finite real number")
        return result
    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTANTS:
            return _ALLOWED_CONSTANTS[node.id]
        raise CalculatorError(f"Unknown identifier: {node.id}")
    raise CalculatorError(f"Unsupported expression element: {type(node).__name__}")


def safe_calculate(expression: str) -> float:
    if not expression or not expression.strip():
        raise CalculatorError("Expression is empty")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise CalculatorError(f"Expression too long (max {MAX_EXPRESSION_LENGTH} chars)")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError(f"Invalid syntax: {exc.msg}") from exc
    return _eval_node(tree.body)


@tool
def calculator(expression: str) -> str:
    """Evaluate a math expression. Supports +,-,*,/,//,%,**, parentheses,
    sqrt/abs/round/sin/cos/tan/log/log10/exp/floor/ceil, and pi/e."""
    try:
        return str(safe_calculate(expression))
    except CalculatorError as exc:
        log.warning("calculator.rejected", extra={"expression": expression})
        return f"Could not evaluate expression: {exc.user_message}"
