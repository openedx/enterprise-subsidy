"""
Views for the openedx_ledger app.
"""
import logging

from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.generic import View
from openedx_ledger.models import Transaction, TransactionStateChoices

from enterprise_subsidy.apps.transaction import api as transaction_api
from enterprise_subsidy.apps.transaction.exceptions import TransactionFulfillmentCancelationException

logger = logging.getLogger(__name__)


# endpoints routed behind the `admin/` namespace are by default given staff or super user permissions level access
class UnenrollLearnersView(View):
    """
    Admin view for the canceling platform enrollments form.
    """
    template = "admin/unenroll.html"

    def get(self, request, transaction_id):
        """
        Handle GET request - render "Cancel transaction without refund" form.

        Arguments:
            request (django.http.request.HttpRequest): Request instance
            transaction_uuid (str): Enterprise Customer UUID

        Returns:
            django.http.response.HttpResponse: HttpResponse
        """
        transaction = Transaction.objects.filter(uuid=transaction_id).first()

        if not transaction:
            logger.info(f"UnenrollLearnersView: transaction {transaction_id} not found, skipping")
            return HttpResponseBadRequest("Transaction not found")
        if transaction.state != TransactionStateChoices.COMMITTED:
            logger.info(f"transaction {transaction_id} is not committed, skipping")
            return HttpResponseBadRequest("Transaction is not committed")
        if not transaction.fulfillment_identifier:
            logger.info(f"UnenrollLearnersView: transaction {transaction_id} has no fulfillment uuid, skipping")
            return HttpResponseBadRequest("Transaction has no associated platform fulfillment identifier")

        return render(
            request,
            self.template,
            {'transaction': Transaction.objects.get(uuid=transaction_id)}
        )

    def post(self, request, transaction_id):
        """
        Handle POST request - handle form submissions.

        Arguments:
            request (django.http.request.HttpRequest): Request instance
        """
        logger.info(f"Sending admin invoked transaction unenroll signal for transaction: {transaction_id}")
        transaction = Transaction.objects.filter(uuid=transaction_id).first()
        if not transaction:
            logger.info(f"transaction {transaction_id} not found, skipping")
            return HttpResponseBadRequest("Transaction not found")

        try:
            transaction_api.cancel_transaction_external_fulfillment(transaction)
            transaction_api.cancel_transaction_fulfillment(transaction)
        except TransactionFulfillmentCancelationException as exc:
            error_msg = f"Error canceling fulfillments for transaction {transaction}: {exc}"
            logger.exception(error_msg)
            return HttpResponseBadRequest(error_msg)

        url = reverse("admin:openedx_ledger_transaction_change", args=(transaction_id,))
        return HttpResponseRedirect(url)
