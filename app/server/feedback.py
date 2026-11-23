"""Reviewer actions -> feedback on the extraction's MLflow trace.

Best effort and asynchronous: logging happens on a background thread and any failure is only logged, so a
slow or unavailable tracking server never blocks or breaks a review action. Orders without a trace_id
(extracted before tracing was enabled) are skipped.
"""
import logging
import threading

log = logging.getLogger(__name__)


def _log(trace_id, reviewer, feedback, expectation):
    try:
        import mlflow
        from mlflow.entities import AssessmentSource

        source = AssessmentSource(source_type="HUMAN", source_id=reviewer or "unknown")
        for name, value, rationale in feedback:
            mlflow.log_feedback(trace_id=trace_id, name=name, value=value, source=source, rationale=rationale)
        if expectation is not None:
            name, value = expectation
            mlflow.log_expectation(trace_id=trace_id, name=name, value=value, source=source)
    except Exception as e:  # noqa — never let feedback logging affect the review
        log.warning("feedback for trace %s not logged: %s", trace_id, e)


def record(trace_id, reviewer, feedback, expectation=None):
    """feedback: [(name, value, rationale)], expectation: (name, value) or None."""
    if not trace_id:
        return
    threading.Thread(target=_log, args=(trace_id, reviewer, feedback, expectation), daemon=True).start()
