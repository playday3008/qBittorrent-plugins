"""Type-safe mock utilities.

Provides generic helpers that give both **static** (pyright / mypy) and
**runtime** (``spec=``) type safety when working with ``unittest.mock``.

``mock(T)``
    Create a ``MagicMock`` whose static type is *T*.
``when(method).returns(value)``
    Set ``return_value`` with the value type-checked against the
    method's return annotation.
``when(method).returns(v1, v2, ...)``
    Set ``side_effect`` to a typed sequence of return values.
``when(method).raises(exc)``
    Set ``side_effect`` to an exception.
``_as_mock(obj)``
    Internal escape-hatch back to the underlying ``MagicMock``.
"""

# ruff: noqa: D103

from collections.abc import Callable
from typing import Generic, TypeVar, cast
from unittest.mock import MagicMock

_T = TypeVar("_T")
_R = TypeVar("_R")


def mock(spec: type[_T]) -> _T:
    """Create a ``MagicMock`` that is statically typed as *spec*.

    * **Static safety** -- attribute access and assignments are checked
      against *spec* by the type-checker.
    * **Runtime safety** -- ``spec=`` prevents accessing attributes that
      do not exist on *spec*.

    Configure simple attributes with normal (type-checked) assignment::

        response = mock(HTTPResponse)
        response.status = 200          # OK
        response.status = "bad"        # type error

    Configure method behaviour with :func:`when`::

        when(response.read).returns(b"data")   # OK
        when(response.read).returns("string")  # type error
    """
    return cast("_T", MagicMock(spec=spec))


def _as_mock(obj: object) -> MagicMock:
    """Unwrap a typed mock back to ``MagicMock`` (internal helper)."""
    if not isinstance(obj, MagicMock):
        msg = f"Expected MagicMock, got {type(obj).__name__}"
        raise TypeError(msg)
    return obj


class _When(Generic[_R]):
    """Configure a mock method's behaviour with type checking.

    Created by :func:`when`; not instantiated directly.  The type
    parameter *_R* is locked in by the method passed to ``when()``,
    so the type-checker enforces that values match.
    """

    __slots__ = ("_method",)

    def __init__(self, method: Callable[..., _R]) -> None:
        self._method = method

    def returns(self, value: _R, /, *more: _R) -> None:
        """Set return value(s) for the mock method.

        Single argument sets ``return_value``; multiple arguments set
        ``side_effect`` so each call returns the next value::

            when(response.read).returns(b"data")
            when(opener.open).returns(resp1, resp2)
        """
        if more:
            _as_mock(self._method).side_effect = (value, *more)
        else:
            _as_mock(self._method).return_value = value

    def raises(self, error: BaseException) -> None:
        """Set ``side_effect`` to an exception.

        ::

            when(opener.open).raises(URLError("fail"))
        """
        _as_mock(self._method).side_effect = error


def when(method: Callable[..., _R]) -> _When[_R]:
    """Configure a mock method's behaviour with type checking.

    Uses two-phase inference so that both **pyright** and **mypy**
    enforce the value type.  *_R* is resolved from *method*'s return
    annotation first, then enforced on subsequent calls.

    Single return value::

        when(response.read).returns(b"data")    # OK  -- read() -> bytes
        when(response.read).returns("string")   # type error -- str != bytes

    Sequence of return values::

        when(opener.open).returns(resp1, resp2)

    Exception::

        when(opener.open).raises(URLError("fail"))
    """
    return _When(method)
