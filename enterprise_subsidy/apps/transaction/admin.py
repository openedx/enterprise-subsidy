""" Top level admin configuration for the subsidy service. """

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import re_path, reverse
from djangoql.admin import DjangoQLSearchMixin
from openedx_ledger.admin import LedgerAdmin as BaseLedgerAdmin
from openedx_ledger.admin import TransactionAdmin as BaseTransactionAdmin
from openedx_ledger.models import Ledger, Transaction

from enterprise_subsidy.apps.subsidy.models import Subsidy
from enterprise_subsidy.apps.transaction import views

admin.site.unregister(Transaction)
admin.site.unregister(Ledger)


def can_modify():
    return getattr(settings, 'ALLOW_LEDGER_MODIFICATION', False)


class SubsidyInline(admin.StackedInline):
    """
    Inline class to help present an inline view
    within the ``LedgerAdmin`` class.
    """
    model = Subsidy
    fields = [
        'title',
        'enterprise_customer_uuid',
        'internal_only',
        'active_datetime',
        'expiration_datetime',
    ]
    readonly_fields = fields
    show_change_link = True


@admin.register(Ledger)
class LedgerAdmin(DjangoQLSearchMixin, BaseLedgerAdmin):
    """
    An enterprise-subsidy specific override of the base ``openedx_ledger.LedgerAdmin``
    class.  Notably, it presents an inline view of the related ``Subsidy`` model.
    """
    search_fields = BaseLedgerAdmin.search_fields
    djangoql_completion_enabled_by_default = False

    inlines = [
        SubsidyInline,
    ]


@admin.register(Transaction)
class TransactionAdmin(DjangoQLSearchMixin, BaseTransactionAdmin):
    """
    Subsidy specific implimentation of the Admin configuration for the Transaction model.
    Includes a custom action for unenrolling learners from the platform enrollment associated with a transaction
    without interacting/reversing with the object.
    """
    class Meta:
        model = Transaction
        fields = '__all__'

    djangoql_completion_enabled_by_default = False

    change_actions = BaseTransactionAdmin.change_actions + ('unenroll',)

    list_select_related = [
        'ledger',
        'ledger__subsidy',
    ]

    list_display = list(BaseTransactionAdmin.list_display) + [
        'enterprise_customer_uuid',
        'ledger_uuid',
    ]

    if can_modify():
        readonly_fields = ['enterprise_customer_uuid']
    else:
        readonly_fields = list(BaseTransactionAdmin._all_fields) + ['enterprise_customer_uuid']

    def enterprise_customer_uuid(self, tx_obj):
        return tx_obj.ledger.subsidy.enterprise_customer_uuid

    def ledger_uuid(self, tx_obj):
        return tx_obj.ledger.uuid

    # From https://github.com/ivelum/djangoql#using-djangoql-with-the-standard-django-admin-search:
    # "DjangoQL will recognize if you have defined search_fields in your ModelAdmin class,
    # and doing so will allow you to choose between an advanced search with
    # DjangoQL and a standard Django search (as specified by search fields)"
    # TODO:
    # djangoql it doesn't seem to take search_fields from the parent class into account
    # when doing this check, so we redefine them here for now.
    search_fields = (
        'content_key',
        'lms_user_id',
        'uuid',
        'external_reference__external_reference_id',
        'subsidy_access_policy_uuid',
        'ledger__uuid',
        'ledger__subsidy__enterprise_customer_uuid'
    )

    @admin.action(
        description="Unenroll the learner from the platform representation of the course."
    )
    def unenroll(self, request, obj):
        """
        Redirect to the unenroll view.
        """
        # url names coming from get_urls are prefixed with 'admin' namespace
        unenroll_url = reverse("admin:unenroll", args=(obj.uuid,))
        return HttpResponseRedirect(unenroll_url)

    unenroll.label = "Unenroll"

    def get_urls(self):
        """
        Returns the additional urls used by DjangoObjectActions.
        """
        custom_urls = [
            re_path(
                r"^([^/]+)/unenroll$",
                self.admin_site.admin_view(views.UnenrollLearnersView.as_view()),
                name="unenroll"
            ),
        ]
        return custom_urls + super().get_urls()
