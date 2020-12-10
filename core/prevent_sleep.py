##
# Module to prevent system sleep on Windows
##
import logging
import ctypes

log = logging.getLogger(__name__)

ctypes_windll = None
try:
    ctypes_windll = ctypes.windll.kernel32
    log.info("Detected Windows, will keep the system awake during processing.")
except Exception:
    log.info("Windows not detected, not preventing sleep.")


class StateFlags:
    # Documentation:
    # https://docs.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate
    ES_AWAYMODE_REQUIRED = 0x00000040
    ES_CONTINUOUS = 0x80000000
    ES_DISPLAY_REQUIRED = 0x00000002
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_USER_PRESENT = 0x00000004


def inhibit():
    """
    Start inhibiting Windows system sleep.
    """
    if ctypes_windll is not None:
        log.info("Inhibiting Windows system sleep.")
        ctypes_windll.SetThreadExecutionState(StateFlags.ES_CONTINUOUS | StateFlags.ES_SYSTEM_REQUIRED)


def uninhibit():
    """
    Stop inhibiting Windows system sleep.
    """
    if ctypes_windll is not None:
        log.info("Uninhibiting Windows system sleep.")
        ctypes_windll.SetThreadExecutionState(StateFlags.ES_CONTINUOUS)
