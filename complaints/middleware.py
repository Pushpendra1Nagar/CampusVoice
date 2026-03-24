from django.core.cache import cache
from django.utils import timezone


class EscalationMiddleware:
    """
    Runs escalation check at most once every 30 minutes.
    Triggered automatically on any page visit — no cron needed.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only check on GET requests, not on static files
        if request.method == 'GET' and not request.path.startswith('/static/'):
            self._maybe_escalate()
        return self.get_response(request)

    def _maybe_escalate(self):
        # Check cache — if key exists, skip (already ran in last 30 mins)
        if cache.get('escalation_last_run'):
            return

        try:
            from complaints.models import Complaint
            pending = Complaint.objects.filter(
                status__in=['pending', 'in_progress'],
                escalation_level__lt=3
            )
            for complaint in pending:
                if complaint.should_escalate():
                    old_level = complaint.escalation_level
                    complaint.escalate()
                    print(f"[Escalation] #{complaint.id} moved L{old_level}→L{complaint.escalation_level}: {complaint.title}")

            # Set cache for 60 minutes
            cache.set('escalation_last_run', timezone.now().isoformat(), timeout=3600)

        except Exception as e:
            print(f"[Escalation Error] {e}")