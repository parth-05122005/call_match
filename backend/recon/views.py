from rest_framework.exceptions import ParseError

from recon.serializers import MatchSerializer
from recon.services import actions
from recon.services.importer import import_bank_statement

from rest_framework.decorators import api_view
from rest_framework.response import Response

from recon.models import LineItem, Organization, Transaction
from recon.organization import get_organization
from recon.serializers import LineItemSerializer, OrganizationSerializer, TransactionSerializer


@api_view(["GET"])
def list_organizations(request):
    """Used by the organization switcher; needs no header."""
    organizations = Organization.objects.order_by("name")
    return Response(OrganizationSerializer(organizations, many=True).data)


@api_view(["GET"])
def list_transactions(request):
    organization = get_organization(request)
    transactions = (
        Transaction.objects.filter(organization=organization)
        .prefetch_related("matches__line_item__investor")
        .order_by("-date", "-id")  # newest first
    )
    return Response(TransactionSerializer(transactions, many=True).data)


@api_view(["GET"])
def list_line_items(request):
    organization = get_organization(request)
    line_items = (
        LineItem.objects.filter(organization=organization)
        .select_related("investor", "capital_call")
    )
    return Response(LineItemSerializer(line_items, many=True).data)


@api_view(["POST"])
def import_transactions(request):
    organization = get_organization(request)
    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        raise ParseError("Upload a CSV file in the 'file' field")
    summary = import_bank_statement(organization, uploaded_file)
    return Response(summary, status=201)


@api_view(["POST"])
def ignore_transaction(request, transaction_id):
    organization = get_organization(request)
    txn = actions.ignore_transaction(organization, transaction_id)
    return Response({"id": txn.id, "status": txn.status})


@api_view(["POST"])
def approve_match(request, match_id):
    organization = get_organization(request)
    match = actions.approve_match(organization, match_id)
    return Response(MatchSerializer(match).data)


@api_view(["POST"])
def reject_match(request, match_id):
    organization = get_organization(request)
    match = actions.reject_match(organization, match_id)
    return Response(MatchSerializer(match).data)