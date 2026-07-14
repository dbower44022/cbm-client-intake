"""My Mentor Profile app (``/mentorprofile``).

A self-service tool where a mentor edits their OWN ``CMentorProfile`` + linked
Contact record from one screen, with a live preview styled like the public
website mentor page (the CRM feeds the website, so what they see is what the
site will show). Gated to the **Mentor Team** via the shared portal session;
every operation is scoped server-side to the caller's own profile, and edits
run as the logged-in user (their token) so EspoCRM enforces their ACL.
"""

from .router import router as api_router

__all__ = ["api_router"]
