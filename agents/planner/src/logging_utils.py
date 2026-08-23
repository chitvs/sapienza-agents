"""Piccolo helper di logging condiviso da PlannerPipeline e ContextGatherer."""

import logging
from typing import Callable


def make_logger(logger: logging.Logger, verbose: bool) -> Callable[..., None]:
    """Crea una funzione di log che scrive sempre su `logger` e, se `verbose`
    è True, anche a schermo (usato per il debug interattivo della pipeline).

    Args:
        logger: Il logger di destinazione.
        verbose: Se True, stampa anche a schermo oltre a loggare.

    Returns:
        Una funzione `_log(msg, level=logging.INFO)` pronta all'uso.
    """
    def _log(msg: str, level: int = logging.INFO) -> None:
        if verbose:
            print(msg)
        logger.log(level, msg)

    return _log