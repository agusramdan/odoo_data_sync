
import inspect


def is_callable_method(model, method):
    return method and hasattr(model, method) and callable(getattr(model, method))


def has_kwargs(func):
    sig = inspect.signature(func)
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
