from rest_framework.exceptions import NotFound, ParseError

from recon.models import Organization


def get_organization(request):
    """
    Missing header -> 400. Unknown organization -> 404.
    Every view calls this first and filters all its queries by the result.
    """
    slug = request.headers.get("X-Organization", "").strip()
    if not slug:
        raise ParseError("The X-Organization header is required")
    try:
        return Organization.objects.get(slug=slug)
    except Organization.DoesNotExist:
        raise NotFound(f"Organization '{slug}' not found")