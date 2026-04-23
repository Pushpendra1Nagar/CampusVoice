from django.core.cache import cache
from django.utils import timezone


class EscalationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Run escalation AFTER response, only on HTML GET pages
        if (request.method == 'GET'
                and not request.path.startswith('/static/')
                and not request.path.startswith('/favicon')
                and not request.path.startswith('/check-escalations')
                and 'text/html' in response.get('Content-Type', '')):
            self._maybe_escalate()

        return response

    def _maybe_escalate(self):
        if cache.get('escalation_last_run'):
            return

        try:
            from complaints.models import Complaint

            complaints = Complaint.objects.filter(
                status__in=['pending', 'in_progress'],
                escalation_level__lt=3
            ).only(
                'id', 'escalation_level', 'status',
                'escalated_at', 'created_at', 'title'
            )

            for complaint in complaints:
                if complaint.should_escalate():
                    complaint.escalate()

            cache.set(
                'escalation_last_run',
                timezone.now().isoformat(),
                timeout=1800
            )

            # Trigger weekly digest on Mondays
            self._maybe_send_digest()

        except Exception as e:
            print(f"[Escalation Error] {e}")

    def _maybe_send_digest(self):
        # ✅ FIXED — body is now properly indented inside the method
        now = timezone.now()
        if now.weekday() == 0 and not cache.get('weekly_digest_sent'):
            try:
                from complaints.views import _send_weekly_digests
                _send_weekly_digests()
                cache.set('weekly_digest_sent', True, timeout=6 * 24 * 3600)
                print("[Digest] Weekly digest sent.")
            except Exception as e:
                print(f"[Digest Error] {e}")