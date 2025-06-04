from functools import wraps
from typing import Callable, Any


def extend_method_after(extension_func: Callable) -> Callable:
    """
    装饰器，用于扩展类方法，先执行原始方法，再执行扩展方法
    """

    @wraps(extension_func)
    def decorator(original_method: Callable) -> Callable:
        @wraps(original_method)
        def wrapper(self, *args, **kwargs):
            # 执行原始方法
            result = original_method(self, *args, **kwargs)
            # 执行扩展方法，传入原始方法的结果
            return extension_func(self, result, *args, **kwargs)

        return wrapper

    return decorator


def extend_method_before(extension_func: Callable) -> Callable:
    """
    装饰器，用于扩展类方法，先执行扩展方法, 再执行原始方法
    """

    @wraps(extension_func)
    def decorator(original_method: Callable) -> Callable:
        @wraps(original_method)
        def wrapper(self, *args, **kwargs):
            # 执行扩展方法
            extension_func(self, *args, **kwargs)
            # 执行原始方法
            return original_method(self, *args, **kwargs)

        return wrapper

    return decorator