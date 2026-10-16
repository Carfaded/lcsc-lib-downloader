"""LCSC3D 日志接口的轻量替身（本文件为精简集成而重写，非 LCSC3D 原文件）。

原文件: lcsc3d/core/app_logging.py
来源:   LCSC3D 项目（AGPL-3.0, github.com/Travelerrrrrr/LCSC3D）

此处保留被 AD 导出链使用的全部公开接口
(operation / traced / safe_part / record_error / log_event)，
去除 LCSC3D 的文件日志、线程与 GUI 依赖；本替身不产生任何副作用，
不写入任何日志文件。
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import wraps


@contextmanager
def operation(event, *, level='DEBUG', **fields):
    """原实现会记录耗时；此处为无损透传上下文。"""
    yield


def traced(event, fields=None, *, level='DEBUG'):
    """保持接口一致：按原语义透传被装饰函数的返回值与异常。"""
    def decorate(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            return function(*args, **kwargs)
        return wrapper
    return decorate


def safe_part(value):
    """日志用安全化编号/名称（仅用于输出，不做转义）。"""
    return str(value)[:64]


def record_error(error, event, *, level='ERROR', **fields):
    return None


def log_event(level, event, **safe_fields):
    return None
