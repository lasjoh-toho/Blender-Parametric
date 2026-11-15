# SPDX-License-Identifier: GPL-3.0-or-later
"""Safe evaluation of small math expressions used by formula nodes and polylines.

Only numbers, names from a whitelist, arithmetic/comparison operators, the
conditional expression and calls to whitelisted math functions are allowed.
"""

import ast
import math
import operator

__all__ = ["ExpressionError", "evaluate", "names_in"]


class ExpressionError(ValueError):
    pass


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

_CMP_OPS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

FUNCTIONS = {
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
    "sqrt": math.sqrt,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "log": math.log,
    "exp": math.exp,
    "radians": math.radians,
    "degrees": math.degrees,
    "clamp": lambda x, lo, hi: max(lo, min(hi, x)),
}

CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

_MAX_POW = 1e6


def _eval(node, names):
    if isinstance(node, ast.Expression):
        return _eval(node.body, names)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ExpressionError("Nur Zahlen sind erlaubt")
        return node.value
    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        raise ExpressionError(f"Unbekannter Name: {node.id}")
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ExpressionError("Operator nicht erlaubt")
        left = _eval(node.left, names)
        right = _eval(node.right, names)
        if op is operator.pow and abs(right) > 64 and abs(left) > 1:
            raise ExpressionError("Exponent zu groß")
        try:
            value = op(left, right)
        except ZeroDivisionError:
            raise ExpressionError("Division durch null")
        if isinstance(value, complex):
            raise ExpressionError("Ergebnis ist keine reelle Zahl")
        return value
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ExpressionError("Operator nicht erlaubt")
        return op(_eval(node.operand, names))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, names)
        for op_node, comp in zip(node.ops, node.comparators):
            op = _CMP_OPS.get(type(op_node))
            if op is None:
                raise ExpressionError("Vergleich nicht erlaubt")
            right = _eval(comp, names)
            if not op(left, right):
                return 0.0
            left = right
        return 1.0
    if isinstance(node, ast.BoolOp):
        values = [_eval(v, names) for v in node.values]
        if isinstance(node.op, ast.And):
            return 1.0 if all(values) else 0.0
        return 1.0 if any(values) else 0.0
    if isinstance(node, ast.IfExp):
        return _eval(node.body, names) if _eval(node.test, names) else _eval(node.orelse, names)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS:
            raise ExpressionError("Funktion nicht erlaubt")
        if node.keywords:
            raise ExpressionError("Benannte Argumente sind nicht erlaubt")
        args = [_eval(a, names) for a in node.args]
        try:
            return FUNCTIONS[node.func.id](*args)
        except (ValueError, TypeError) as exc:
            raise ExpressionError(f"{node.func.id}: {exc}")
    raise ExpressionError("Ausdruck nicht erlaubt")


def evaluate(expression, names=None):
    """Evaluate ``expression`` and return a float."""
    expression = (expression or "").strip().replace(",", ".") if _looks_decimal_comma(expression) else (expression or "").strip()
    if not expression:
        raise ExpressionError("Leerer Ausdruck")
    if len(expression) > 500:
        raise ExpressionError("Ausdruck zu lang")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        raise ExpressionError(f"Ungültiger Ausdruck: {expression}")
    value = _eval(tree, names or {})
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ExpressionError("Ergebnis ist keine Zahl")
    if math.isnan(value) or math.isinf(value):
        raise ExpressionError("Ergebnis ist keine endliche Zahl")
    return value


def _looks_decimal_comma(expression):
    """``2,5`` (German decimal comma) is accepted when there is no function call."""
    return bool(expression) and "," in expression and "(" not in expression


def names_in(expression):
    """Return the set of variable names used in ``expression`` (empty on syntax errors)."""
    try:
        tree = ast.parse((expression or "").strip(), mode="eval")
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - set(FUNCTIONS) - set(CONSTANTS)
