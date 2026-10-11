# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Bounded executable agreement for the declared pure Python expression subset.

Never import repository code. Only single-return expression functions in the
closed subset below can execute; unsupported syntax requires human review and a
repository-specific enforcement implementation, not a purity exemption.
"""

from __future__ import annotations

import ast
import hashlib
import json
import operator
from typing import Any


class PureSourceError(ValueError):
    """Source is outside the declared mechanically provable pure subset."""


_NODES = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.Call,
          ast.Attribute, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
          ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.BoolOp, ast.And, ast.Or,
          ast.UnaryOp, ast.Not, ast.IfExp)
_METHODS = {"lower": 0, "upper": 0, "strip": 0, "removeprefix": 1,
            "removesuffix": 1, "startswith": 1, "endswith": 1}
_COMPARISONS = {ast.Eq: operator.eq, ast.NotEq: operator.ne,
                ast.Lt: operator.lt, ast.LtE: operator.le,
                ast.Gt: operator.gt, ast.GtE: operator.ge,
                ast.In: lambda left, right: left in right,
                ast.NotIn: lambda left, right: left not in right}


def _evaluate(node, parameter, value):
    """Evaluate reviewed AST semantics without Python eval, exec or imports."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id == parameter:
        return value
    if isinstance(node, ast.UnaryOp):
        return not _evaluate(node.operand, parameter, value)
    if isinstance(node, ast.IfExp):
        selected = node.body if _evaluate(node.test, parameter, value) else node.orelse
        return _evaluate(selected, parameter, value)
    if isinstance(node, ast.BoolOp):
        result = None
        for expression in node.values:
            result = _evaluate(expression, parameter, value)
            if isinstance(node.op, ast.And) and not result or isinstance(node.op, ast.Or) and result:
                break
        return result
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, parameter, value)
        for operation, expression in zip(node.ops, node.comparators):
            right = _evaluate(expression, parameter, value)
            if not _COMPARISONS[type(operation)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        arguments = [_evaluate(argument, parameter, value) for argument in node.args]
        if isinstance(node.func, ast.Name):
            return len(arguments[0])
        receiver = _evaluate(node.func.value, parameter, value)
        if type(receiver) is not str:
            raise PureSourceError("string operations require closed string representations")
        return getattr(receiver, node.func.attr)(*arguments)
    raise PureSourceError("expression is outside the executable pure subset")


def pure_expression(source: str, function: str):
    """Admit only a closed, bounded, side-effect-free expression."""
    try:
        module = ast.parse(source)
        if len(list(ast.walk(module))) > 1000:
            raise PureSourceError()
        if any(not isinstance(item, ast.FunctionDef) for item in module.body):
            raise PureSourceError()
        if any(item.decorator_list or item.returns or item.args.defaults
               or any(item.args.kw_defaults) or any(argument.annotation for argument in item.args.args)
               for item in module.body):
            raise PureSourceError()
        functions = [item for item in module.body if item.name == function]
        if len(functions) != 1:
            raise PureSourceError()
        item = functions[0]
        if (item.decorator_list or item.returns or getattr(item, "type_params", [])
                or len(item.args.args) != 1 or item.args.args[0].annotation
                or item.args.posonlyargs or item.args.kwonlyargs
                or item.args.vararg or item.args.kwarg or item.args.defaults
                or len(item.body) != 1 or not isinstance(item.body[0], ast.Return)):
            raise PureSourceError()
        parameter = item.args.args[0].arg
        if parameter == "len":
            raise PureSourceError()
        expression = ast.Expression(item.body[0].value)
        nodes = list(ast.walk(expression))
        if len(nodes) > 200:
            raise PureSourceError()
        called_attributes = {id(node.func) for node in nodes if isinstance(node, ast.Call)}
        for node in nodes:
            if not isinstance(node, _NODES):
                raise PureSourceError()
            if isinstance(node, ast.Constant) and (
                type(node.value) not in (str, int, bool, type(None))
                or isinstance(node.value, str) and len(node.value) > 1024
                or type(node.value) is int and node.value.bit_length() > 128
            ):
                raise PureSourceError()
            if isinstance(node, ast.Name) and node.id not in {parameter, "len"}:
                raise PureSourceError()
            if isinstance(node, ast.Name) and node.id == "len" and id(node) not in called_attributes:
                raise PureSourceError()
            if isinstance(node, ast.Attribute) and (
                id(node) not in called_attributes or node.attr not in _METHODS
            ):
                raise PureSourceError()
            if isinstance(node, ast.Call):
                if node.keywords:
                    raise PureSourceError()
                if isinstance(node.func, ast.Name):
                    if node.func.id != "len" or len(node.args) != 1:
                        raise PureSourceError()
                elif isinstance(node.func, ast.Attribute):
                    if len(node.args) != _METHODS.get(node.func.attr):
                        raise PureSourceError()
                    if any(not isinstance(arg, ast.Constant) or type(arg.value) is not str
                           for arg in node.args):
                        raise PureSourceError()
                else:
                    raise PureSourceError()
    except (SyntaxError, ValueError, TypeError, RecursionError) as error:
        raise PureSourceError("declared source is outside the pure subset") from error

    def execute(value: Any):
        # Values originate solely in bounded JSON: no caller objects, modules,
        # descriptors, mutable external state, imports, recursion or loops.
        if not bounded_value(value):
            raise PureSourceError("input is outside the closed representation domain")
        return _evaluate(expression.body, parameter, value)

    return execute


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def bounded_value(value: Any, depth: int = 0) -> bool:
    if depth > 8:
        return False
    if type(value) in (bool, type(None)):
        return True
    if type(value) is str:
        return len(value) <= 4096
    if type(value) is int:
        return value.bit_length() <= 128
    if type(value) is list:
        return len(value) <= 100 and all(bounded_value(item, depth + 1) for item in value)
    if type(value) is dict:
        return len(value) <= 100 and all(
            type(key) is str and len(key) <= 96 and bounded_value(item, depth + 1)
            for key, item in value.items()
        )
    return False
