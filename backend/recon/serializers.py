from rest_framework import serializers

from recon.models import LineItem, Match, Organization, Transaction


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["slug", "name"]


class LineItemSerializer(serializers.ModelSerializer):
    investor = serializers.CharField(source="investor.name")
    capital_call = serializers.IntegerField(source="capital_call.number")
    amount_remaining = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = LineItem
        fields = [
            "id", "reference", "investor", "capital_call",
            "amount_called", "amount_funded", "amount_remaining", "status",
        ]


class MatchSerializer(serializers.ModelSerializer):
    line_item_reference = serializers.CharField(source="line_item.reference")
    investor = serializers.CharField(source="line_item.investor.name")

    class Meta:
        model = Match
        fields = ["id", "line_item", "line_item_reference", "investor", "status", "reason"]


class TransactionSerializer(serializers.ModelSerializer):
    matches = MatchSerializer(many=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "date", "description", "amount", "type",
            "bank_reference", "status", "reason", "matches",
        ]