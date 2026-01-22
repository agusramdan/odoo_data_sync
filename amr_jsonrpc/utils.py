from collections import defaultdict

import inspect
from odoo import SUPERUSER_ID, models
from odoo.tools import clean_context, attrgetter

from odoo.exceptions import UserError
from odoo import _
import requests
import logging
from functools import wraps

_logger = logging.getLogger(__name__)


def savepoint(_func=None, *,
              rethrow=False,
              logger=_logger,
              ):
    """
    Decorator savepoint aman Odoo.
    :param _func
    :param invalidate_all: True → env.invalidate_all()
    :param rethrow: True → exception dilempar ulang
    :param flush: True fluss sebelum keluar save point
    :param logger: logger instance
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                with self.env.cr.savepoint():
                    return func(self, *args, **kwargs)
            except Exception as e:
                logger.warning("[SAFEPOINT] %s failed: %s", func.__name__, e, exc_info=True)
                if rethrow:
                    raise
                return None

        return wrapper

    if _func is None:
        return decorator
    else:
        return decorator(_func)


def call_with_savepoint(self, method_name, args=None, kwargs=None, logger=_logger,rethrow=False ):
    """
    Memanggil method pada object secara aman.

    - method optional
    - method_name harus string
    - method harus callable
    - args disesuaikan dengan signature
    """

    if not isinstance(self, models.BaseModel):
        return self

    if not method_name or not isinstance(method_name, str):
        return self

    if not hasattr(self, method_name):
        raise AttributeError(f"Method {method_name} not found")

    method = getattr(self, method_name, None)
    if not callable(method):
        raise AttributeError(f"Callable method '{method_name}' not found on {self}")

    # === signature aware ===
    sig = inspect.signature(method)
    params = sig.parameters

    final_args = []
    final_kwargs = {}
    kwargs = kwargs or {}
    args = args or []
    for name, p in params.items():
        if p.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD
        ):
            if args:
                final_args.append(args[0])
                args = args[1:]
            elif name in kwargs:
                final_args.append(kwargs[name])
            elif p.default is not inspect.Parameter.empty:
                pass
            else:
                raise TypeError(f"Missing required argument: {name}")

        elif p.kind == inspect.Parameter.VAR_POSITIONAL:
            final_args.extend(args)
            args = ()

        elif p.kind == inspect.Parameter.KEYWORD_ONLY:
            if name in kwargs:
                final_kwargs[name] = kwargs[name]
            elif p.default is inspect.Parameter.empty:
                raise TypeError(f"Missing keyword-only argument: {name}")

        elif p.kind == inspect.Parameter.VAR_KEYWORD:
            final_kwargs.update(kwargs)
    try:
        with self.env.cr.savepoint():
            return method(*final_args, **final_kwargs)
    except Exception as e:
        logger.warning("[SAFEPOINT] %s failed: %s", method_name, e, exc_info=True)
        if rethrow:
            raise
    return self
