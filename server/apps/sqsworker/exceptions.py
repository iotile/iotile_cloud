

class SqsWorkerBaseException(Exception):
    """
    All worker exceptions should derived from this base exception
    """


class WorkerAbortSilently(SqsWorkerBaseException):
    """
    Called when the worker finds a condition that requires
    to abort the task, but without reporting as an actual code error
    """


class WorkerInternalError(SqsWorkerBaseException):
    """
    Called when the worker catches an unrecoverable exceptions
    When this happens, we want to restart worker
    """


class WorkerActionHardError(SqsWorkerBaseException):
    """
    Called when the worker catches a specific exception on its action
    This should represent an unexpected but handled exception for the given Action
    This error will delete the current SQS message
    """

class WorkerActionSoftError(SqsWorkerBaseException):
    """
    Called when the worker catches a specific exception on its action
    This should represent an unexpected but handled exception for the given Action
    This error will NOT delete the current SQS message, so the message will be requeue
    """

class HaltAndCatchFire(SqsWorkerBaseException):
    """
    Not really an exception, this is used to force a shut down procedure
    The handler will delete the SQS message and then sleep for 90min, allowing
    the worker to be killed
    Ref: https://en.wikipedia.org/wiki/Halt_and_Catch_Fire
    """
