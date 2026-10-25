from django import forms


class TransferSelectMultiple(forms.SelectMultiple):
    """Native submission and fallback, enhanced with accessible transfer controls."""

    template_name = 'portal/widgets/transfer_select.html'
