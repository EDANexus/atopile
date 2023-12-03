import logging
import textwrap
import traceback
from contextlib import contextmanager
from enum import Enum, auto, IntEnum
from pathlib import Path
from typing import Optional, Type, Iterable, TypeVar, Callable, Sequence
from antlr4 import Token, ParserRuleContext
from .parse_utils import get_src_info_from_ctx, get_src_info_from_token

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class _BaseAtoError(Exception):
    """
    This exception is thrown when there's an error in the syntax of the language
    """

    def __init__(
        self,
        message: str = "",
        src_path: Optional[str | Path] = None,
        src_line: Optional[int] = None,
        src_col: Optional[int] = None,
        **kwargs,
    ) -> None:
        super().__init__(message, **kwargs)
        self.message = message
        self.src_path = src_path
        self.src_line = src_line
        self.src_col = src_col

    @classmethod
    def from_token(cls, message: str, token: Token) -> "_BaseAtoError":
        src_path, src_line, src_col = get_src_info_from_token(token)
        return cls(message, src_path, src_line, src_col)

    @classmethod
    def from_ctx(cls, message: str, ctx: ParserRuleContext) -> "_BaseAtoError":
        src_path, src_line, src_col = get_src_info_from_ctx(ctx)
        return cls(message, src_path, src_line, src_col)

    @property
    def user_facing_name(self):
        """Return the name of this error, without the "Ato" prefix."""
        error_name = self.__class__.__name__
        if error_name.startswith("Ato"):
            return error_name[3:]
        return error_name


class AtoError(_BaseAtoError):
    """
    This exception is thrown when there's an error in ato code
    """


class AtoErrorGroup(_BaseAtoError, ExceptionGroup):
    """
    This exception is thrown when there's an error in ato code
    """

    def __init__(
        self,
        message: str,
        exceptions: Sequence[AtoError],
        src_path: Optional[str | Path] = None,
        src_line: Optional[int] = None,
        src_col: Optional[int] = None,
        **kwargs,
    ) -> None:
        assert all(isinstance(e, AtoError) for e in exceptions)
        super(ExceptionGroup, self).__init__(message, exceptions, **kwargs)
        self.src_path = src_path
        self.src_line = src_line
        self.src_col = src_col

    @classmethod
    def from_ctx(  # pylint: disable=arguments-differ
        cls,
        message: str,
        exceptions: Sequence[AtoError],
        ctx: ParserRuleContext
    ) -> "AtoErrorGroup":
        """Create an error group from a context."""
        src_path, src_line, src_col = get_src_info_from_ctx(ctx)
        return cls(message, exceptions, src_path, src_line, src_col)


class AtoFatalError(AtoError):
    """
    Something in your code meant we weren't able to continue building your code
    """


class AtoSyntaxError(AtoError):
    """
    Raised when there's an error in the syntax of the language
    """


class AtoKeyError(AtoError, KeyError):
    """
    Raised if a name isn't found in the current scope.
    """


class AtoTypeError(AtoError):
    """
    Raised if something is the wrong type.
    """


class AtoNameConflictError(AtoError):
    """
    Raised if something has a conflicting name in the same scope.
    """


class AtoCircularDependencyError(AtoError):
    """
    Raised if something has a conflicting name in the same scope.
    """


class AtoImportNotFoundError(AtoError):
    """
    Raised if something has a conflicting name in the same scope.
    """


class AtoAmbiguousReferenceError(AtoError):
    """
    Raised if something has a conflicting name in the same scope.
    """

class AtoPreexistingError(AtoError):
    """
    Raise if the thing we're visiting already has errors and therefore we stop processing.
    """


def get_locals_from_exception_in_class(ex: Exception, class_: Type) -> dict:
    """Return the locals from the first frame in the traceback that's in the given class."""
    for tb, _ in list(traceback.walk_tb(ex.__traceback__))[::-1]:
        if isinstance(tb.f_locals.get("self"), class_):
            return tb.f_locals
    return {}


def _process_error(
    ex: Exception | ExceptionGroup,
    visitor_type: Type,
    logger: logging.Logger,
):
    """Helper function to consistently write errors to the log"""
    if isinstance(ex, ExceptionGroup):
        for e in ex.exceptions:
            _process_error(e, visitor_type, logger)
        return

    src_path = None
    start_line = None
    start_column = None

    # if we catch an ato error, we can reliably get the line and column from the exception itself
    # if not, we need to get the error's line and column from the context, if possible
    if isinstance(ex, AtoError):
        message = ex.user_facing_name + ": " + ex.message
        src_path = ex.src_path
        start_line = ex.src_line
        start_column = ex.src_col
    else:
        message = f"Unprocessed '{repr(ex)}' occurred during compilation"
        if visitor_type is not None:
            if ctx := get_locals_from_exception_in_class(ex, visitor_type).get("ctx"):
                src_path, start_line, start_column = get_src_info_from_ctx(ctx)

    # ensure we have values for all the components on the error string
    if src_path is None:
        src_path = "<?>"
    if start_line is None:
        start_line = "<?>"
    if start_column is None:
        start_column = "<?>"

    indented_message = textwrap.indent(message, "--> ")

    logger.error(
        textwrap.dedent(
            f"""
            {src_path}:{start_line}:{start_column}:
            {indented_message}
            """
        ).strip()
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Error info:\n", exc_info=ex)


class HandlerMode(Enum):
    """The mode to use when an error occurs."""

    COLLECT_ALL = auto()
    RAISE_NON_ATO_EXCEPT_FATAL = auto()
    RAISE_ALL = auto()


I = TypeVar("I")
O = TypeVar("O")


class DONT_FILL:
    """A sentinel value to indicate that a spot with an error should not be filled."""


class ErrorHandler:
    """Handles errors in the compiler."""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        handel_mode: Optional[HandlerMode] = HandlerMode.RAISE_NON_ATO_EXCEPT_FATAL,
        log_on_error: bool = True,
    ) -> None:
        self.logger = logger or log
        self.handel_mode = handel_mode
        self.errors: list[Exception] = []
        self.log_on_error = log_on_error

    @property
    def exception_group(self) -> ExceptionGroup:
        """Return an exception group of all the errors."""
        return ExceptionGroup("Errors occurred during compilation", self.errors)

    def assert_no_errors(self) -> None:
        """Raise an exception group of all the errors if there are any."""
        if len(self.errors) > 0:
            raise AtoFatalError from self.exception_group

    def handle(self, error: Exception, from_: Optional[Exception] = None) -> Exception:
        """
        Deal with an error, either by shoving it in the error list or raising it.
        """
        self.errors.append(error)
        if self.log_on_error:
            _process_error(error, None, self.logger)

        def _do_raise() -> None:
            if from_ is not None:
                raise error from from_
            raise error

        if self.handel_mode == HandlerMode.RAISE_ALL:
            _do_raise()

        if self.handel_mode == HandlerMode.RAISE_NON_ATO_EXCEPT_FATAL:
            if not isinstance(error, AtoError) or isinstance(error, AtoFatalError):
                _do_raise()

        return error


class ReraiseBehavior(IntEnum):
    IGNORE = 0
    RERAISE = 1
    RAISE_ATO_FATAL_ERROR = 2


@contextmanager
def write_errors_to_log(
    visitor_type: Optional[Type] = None,
    logger: Optional[logging.Logger] = None,
    reraise: ReraiseBehavior = ReraiseBehavior.RERAISE,
) -> None:
    """
    This helper function catches all exception and attempts to add "best effort" source info to them.
    It's designed to be used on visitors that are the first stage of compilation after parsing.
    It detects if the exception came from inside the visitor, and if so, attempts to add source info from the ANTLR ctx.
    """
    if logger is None:
        logger = log

    try:
        yield
    except (Exception, ExceptionGroup) as ex:  # pylint: disable=broad-except
        _process_error(ex, visitor_type, logger)
        if reraise == ReraiseBehavior.RERAISE:
            raise
        elif reraise == ReraiseBehavior.RAISE_ATO_FATAL_ERROR:
            raise AtoFatalError from ex
