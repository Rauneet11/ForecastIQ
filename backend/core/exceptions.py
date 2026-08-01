import logging
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Wraps DRF's default handler: logs unhandled errors server-side, but
    only ever sends a generic, safe message to the client for real (5xx)
    failures. Tracebacks and internal exception details must never reach
    the API response. Expected client errors (permission denied, not
    found, validation) are left as DRF formats them - no need to log
    those as exceptions."""
    response = exception_handler(exc, context)

    if response is None:
        view = context.get('view')
        logger.exception('Unhandled exception in %s', getattr(view, '__class__', view))
        from rest_framework.response import Response
        from rest_framework import status
        return Response(
            {'error': 'An unexpected error occurred. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return response
