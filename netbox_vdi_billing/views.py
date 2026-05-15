import csv
import io
from collections import defaultdict
from netbox.views import generic as nb_generic
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from netbox.views import generic

from . import filtersets, forms, models, tables


# ─── CostCenter CRUD ──────────────────────────────────────────────────────────

class CostCenterView(generic.ObjectView):
    queryset = models.CostCenter.objects.prefetch_related('assignments__virtual_machine')

    def get_extra_context(self, request, instance):
        assignments = instance.assignments.select_related(
            'virtual_machine', 'profile'
        ).order_by('virtual_machine__name')
        return {'assignments': assignments}


class CostCenterListView(generic.ObjectListView):
    queryset = models.CostCenter.objects.annotate(
        assignment_count=Count('assignments')
    )
    table = tables.CostCenterTable
    filterset = filtersets.CostCenterFilterSet


class CostCenterEditView(generic.ObjectEditView):
    queryset = models.CostCenter.objects.all()
    form = forms.CostCenterForm


class CostCenterDeleteView(generic.ObjectDeleteView):
    queryset = models.CostCenter.objects.all()


class CostCenterChangeLogView(nb_generic.ObjectChangeLogView):
    queryset = models.CostCenter.objects.all()


# ─── VDIBillingProfile CRUD ───────────────────────────────────────────────────

class VDIBillingProfileView(generic.ObjectView):
    queryset = models.VDIBillingProfile.objects.prefetch_related('assignments')

    def get_extra_context(self, request, instance):
        assignments = instance.assignments.select_related('virtual_machine').order_by('virtual_machine__name')
        return {'assignments': assignments}


class VDIBillingProfileListView(generic.ObjectListView):
    queryset = models.VDIBillingProfile.objects.annotate(
        assignment_count=Count('assignments')
    )
    table = tables.VDIBillingProfileTable
    filterset = filtersets.VDIBillingProfileFilterSet


class VDIBillingProfileEditView(generic.ObjectEditView):
    queryset = models.VDIBillingProfile.objects.all()
    form = forms.VDIBillingProfileForm


class VDIBillingProfileDeleteView(generic.ObjectDeleteView):
    queryset = models.VDIBillingProfile.objects.all()


class VDIBillingProfileChangeLogView(nb_generic.ObjectChangeLogView):
    queryset = models.VDIBillingProfile.objects.all()


# ─── VDIAssignment CRUD ───────────────────────────────────────────────────────

class VDIAssignmentView(generic.ObjectView):
    queryset = models.VDIAssignment.objects.select_related('virtual_machine', 'profile', 'cost_center')


class VDIAssignmentListView(generic.ObjectListView):
    queryset = models.VDIAssignment.objects.select_related('virtual_machine', 'profile', 'cost_center')
    table = tables.VDIAssignmentTable
    filterset = filtersets.VDIAssignmentFilterSet


class VDIAssignmentEditView(generic.ObjectEditView):
    queryset = models.VDIAssignment.objects.all()
    form = forms.VDIAssignmentForm


class VDIAssignmentDeleteView(generic.ObjectDeleteView):
    queryset = models.VDIAssignment.objects.all()


class VDIAssignmentChangeLogView(nb_generic.ObjectChangeLogView):
    queryset = models.VDIAssignment.objects.all()


class VDIAssignmentBulkEditView(generic.BulkEditView):
    queryset = models.VDIAssignment.objects.select_related('virtual_machine', 'profile', 'cost_center')
    filterset = filtersets.VDIAssignmentFilterSet
    table = tables.VDIAssignmentTable
    form = forms.VDIAssignmentBulkEditForm

    def get_return_url(self, request, obj=None):
        return reverse('plugins:netbox_vdi_billing:vdiassignment_list')


class VDIAssignmentBulkDeleteView(generic.BulkDeleteView):
    queryset = models.VDIAssignment.objects.select_related('virtual_machine', 'profile', 'cost_center')
    filterset = filtersets.VDIAssignmentFilterSet
    table = tables.VDIAssignmentTable

    def get_return_url(self, request, obj=None):
        return reverse('plugins:netbox_vdi_billing:vdiassignment_list')


# ─── CostCenter Bulk ─────────────────────────────────────────────────────────

class CostCenterBulkEditView(generic.BulkEditView):
    queryset = models.CostCenter.objects.all()
    filterset = filtersets.CostCenterFilterSet
    table = tables.CostCenterTable
    form = forms.CostCenterBulkEditForm

    def get_return_url(self, request, obj=None):
        return reverse('plugins:netbox_vdi_billing:costcenter_list')


class CostCenterBulkDeleteView(generic.BulkDeleteView):
    queryset = models.CostCenter.objects.all()
    filterset = filtersets.CostCenterFilterSet
    table = tables.CostCenterTable

    def get_return_url(self, request, obj=None):
        return reverse('plugins:netbox_vdi_billing:costcenter_list')


# ─── Bulk Assign ─────────────────────────────────────────────────────────────

class BulkAssignCostCenterView(LoginRequiredMixin, View):
    """
    Massen-Zuweisung: Mehrere VMs gleichzeitig einer Kostenstelle zuordnen.
    """
    template_name = 'netbox_vdi_billing/bulk_assign.html'

    def _get_vm_queryset(self):
        from extras.models import Tag
        from virtualization.models import VirtualMachine
        try:
            tag = Tag.objects.get(name='VDI-Persistent')
            return VirtualMachine.objects.filter(tags=tag).order_by('name')
        except Tag.DoesNotExist:
            return VirtualMachine.objects.filter(
                role__name__icontains='VDI'
            ).order_by('name')

    def get(self, request):
        vm_qs = self._get_vm_queryset()
        assigned_ids = set(
            models.VDIAssignment.objects.values_list('virtual_machine_id', flat=True)
        )
        # Kostenstellen-Zuordnung für Anzeige
        vm_cost_centers = {
            a.virtual_machine_id: a.cost_center
            for a in models.VDIAssignment.objects.select_related('cost_center')
        }

        # VMs mit Gruppenprefix gruppieren
        groups = _group_vms_by_prefix(vm_qs, assigned_ids, vm_cost_centers)

        form = forms.BulkAssignCostCenterForm(vm_queryset=vm_qs)
        return render(request, self.template_name, {
            'form': form,
            'vm_groups': groups,
            'vm_count': vm_qs.count(),
        })

    def post(self, request):
        vm_qs = self._get_vm_queryset()
        form = forms.BulkAssignCostCenterForm(request.POST, vm_queryset=vm_qs)

        if not form.is_valid():
            assigned_ids = set(
                models.VDIAssignment.objects.values_list('virtual_machine_id', flat=True)
            )
            vm_cost_centers = {
                a.virtual_machine_id: a.cost_center
                for a in models.VDIAssignment.objects.select_related('cost_center')
            }
            groups = _group_vms_by_prefix(vm_qs, assigned_ids, vm_cost_centers)
            return render(request, self.template_name, {
                'form': form,
                'vm_groups': groups,
                'vm_count': vm_qs.count(),
            })

        cost_center = form.cleaned_data['cost_center']
        profile     = form.cleaned_data.get('profile')
        overwrite   = form.cleaned_data['overwrite']
        selected_vms = form.cleaned_data['virtual_machines']

        created = updated = skipped = 0
        for vm in selected_vms:
            exists = models.VDIAssignment.objects.filter(virtual_machine=vm).exists()
            if exists and not overwrite:
                skipped += 1
                continue

            defaults = {'cost_center': cost_center}
            if profile:
                defaults['profile'] = profile

            _, was_created = models.VDIAssignment.objects.update_or_create(
                virtual_machine=vm,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        messages.success(
            request,
            f'Kostenstelle <strong>{cost_center}</strong>: '
            f'{created} neu erstellt, {updated} aktualisiert, {skipped} übersprungen.'
        )
        return redirect(reverse('plugins:netbox_vdi_billing:chargeback_overview'))


def _group_vms_by_prefix(vm_qs, assigned_ids, vm_cost_centers):
    """Gruppiert VMs nach Standort-Präfix für die Bulk-Assign-Ansicht."""
    # Customize these prefixes to match your site naming convention
    PREFIX_LABELS = {
        'site1':  'Site 1',
        'site2':  'Site 2',
        'site3':  'Site 3',
    }
    groups = defaultdict(lambda: {'label': '', 'vms': []})

    for vm in vm_qs:
        prefix = vm.name.lower().split('-')[0]
        label  = PREFIX_LABELS.get(prefix, prefix.upper())
        groups[prefix]['label'] = label
        groups[prefix]['vms'].append({
            'id':          vm.pk,
            'name':        vm.name,
            'assigned':    vm.pk in assigned_ids,
            'cost_center': vm_cost_centers.get(vm.pk),
        })

    return sorted(groups.values(), key=lambda g: g['label'])


# ─── Chargeback Übersicht ─────────────────────────────────────────────────────

def _build_chargeback_groups(assignments):
    """Gruppiert Zuordnungen nach Kostenstelle und berechnet Summen."""
    raw = defaultdict(lambda: {
        'cost_center':    '',
        'cost_center_pk': None,
        'department':     '',
        'vms': [],
        'total_monthly': 0.0,
    })

    for a in assignments:
        if a.cost_center:
            key  = a.cost_center.number
            dept = a.cost_center.department
            cc_pk = a.cost_center.pk
        else:
            key  = '⚠ Keine Kostenstelle'
            dept = ''
            cc_pk = None

        grp = raw[key]
        grp['cost_center']    = key
        grp['cost_center_pk'] = cc_pk
        if not grp['department'] and dept:
            grp['department'] = dept

        cost = a.cost_monthly
        grp['vms'].append({
            'name':                a.virtual_machine.name,
            'vcpus':               a.virtual_machine.vcpus,
            'memory_gb':           round(float(a.virtual_machine.memory or 0) / 1024, 1),
            'assigned_to':         a.assigned_to,
            'profile':             str(a.profile) if a.profile else None,
            'cost_override':       float(a.cost_override) if a.cost_override is not None else None,
            'cost_monthly':        cost,
            'pricing_source':      a.pricing_source,
            'vm_url':              a.virtual_machine.get_absolute_url(),
            'assignment_url':      a.get_absolute_url(),
            'assignment_edit_url': reverse(
                'plugins:netbox_vdi_billing:vdiassignment_edit', args=[a.pk]
            ),
        })
        grp['total_monthly'] += cost

    groups = list(raw.values())
    groups.sort(key=lambda g: (g['cost_center'].startswith('⚠'), g['cost_center'].lower()))
    for g in groups:
        g['total_yearly'] = round(g['total_monthly'] * 12, 2)
        g['total_monthly'] = round(g['total_monthly'], 2)
        g['vm_count'] = len(g['vms'])
    return groups


class ChargebackOverviewView(LoginRequiredMixin, View):
    template_name = 'netbox_vdi_billing/chargeback_overview.html'

    def get(self, request):
        assignments = models.VDIAssignment.objects.select_related(
            'virtual_machine', 'profile', 'cost_center'
        ).order_by('cost_center__number', 'virtual_machine__name')

        groups = _build_chargeback_groups(assignments)
        total_monthly = sum(g['total_monthly'] for g in groups)
        total_yearly  = round(total_monthly * 12, 2)
        total_vms     = sum(g['vm_count'] for g in groups)

        fmt = request.GET.get('format', 'html')
        if fmt == 'csv':
            return self._csv_response(assignments)

        return render(request, self.template_name, {
            'groups': groups,
            'total_monthly': round(total_monthly, 2),
            'total_yearly': total_yearly,
            'total_vms': total_vms,
            'assigned_count': models.VDIAssignment.objects.filter(
                cost_center__isnull=False).count(),
            'unassigned_count': models.VDIAssignment.objects.filter(
                cost_center__isnull=True).count(),
        })

    def _csv_response(self, assignments):
        """CSV-Export der Chargeback-Daten (UTF-8 mit BOM für Excel)."""
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=';', quoting=csv.QUOTE_ALL)
        writer.writerow([
            'Kostenstelle', 'Abteilung', 'VM-Name', 'vCPU', 'RAM (GB)',
            'Zugewiesen an', 'E-Mail', 'Preisprofil', 'Preisquelle',
            'Festpreis', 'Kosten/Monat (€)', 'Kosten/Jahr (€)',
        ])
        for a in assignments:
            writer.writerow([
                a.cost_center.number if a.cost_center else '',
                a.cost_center.department if a.cost_center else '',
                a.virtual_machine.name,
                a.virtual_machine.vcpus or '',
                round(float(a.virtual_machine.memory or 0) / 1024, 1),
                a.assigned_to,
                a.email,
                a.profile.name if a.profile else '',
                a.pricing_source,
                float(a.cost_override) if a.cost_override is not None else '',
                a.cost_monthly,
                a.cost_yearly,
            ])

        from datetime import date
        filename = f'chargeback_{date.today().strftime("%Y-%m")}.csv'
        # utf-8-sig = UTF-8 mit BOM → Excel erkennt Umlaute korrekt
        response = HttpResponse(
            '﻿' + buf.getvalue(),
            content_type='text/csv; charset=utf-8',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


# ─── PDF / Druckansicht pro Kostenstelle ─────────────────────────────────────

class ChargebackPrintView(LoginRequiredMixin, View):
    def get(self, request, cost_center_pk):
        cost_center = get_object_or_404(models.CostCenter, pk=cost_center_pk)
        assignments = models.VDIAssignment.objects.filter(
            cost_center=cost_center
        ).select_related('virtual_machine', 'profile').order_by('virtual_machine__name')

        if not assignments.exists():
            from django.http import Http404
            raise Http404

        vms = []
        total = 0.0
        for a in assignments:
            cost = a.cost_monthly
            total += cost
            vms.append({
                'name':          a.virtual_machine.name,
                'vcpus':         a.virtual_machine.vcpus,
                'memory_gb':     round(float(a.virtual_machine.memory or 0) / 1024, 1),
                'assigned_to':   a.assigned_to,
                'pricing_source': a.pricing_source,
                'cost_monthly':  cost,
            })

        fmt         = request.GET.get('format', 'html')
        hide_prices = request.GET.get('hide_prices', '0') == '1'

        if fmt == 'pdf':
            return self._pdf_response(cost_center, vms, total, hide_prices)

        from datetime import date
        return render(request, 'netbox_vdi_billing/chargeback_print.html', {
            'cost_center':   cost_center.number,
            'department':    cost_center.department,
            'vms':           vms,
            'total_monthly': round(total, 2),
            'total_yearly':  round(total * 12, 2),
            'month':         date.today().strftime('%B %Y'),
            'hide_prices':   hide_prices,
        })

    def _pdf_response(self, cost_center, vms, total, hide_prices=False):
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            import io
            from datetime import date

            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=A4,
                                    leftMargin=2*cm, rightMargin=2*cm,
                                    topMargin=2*cm, bottomMargin=2*cm)
            styles = getSampleStyleSheet()
            story  = []

            month = date.today().strftime('%B %Y')
            title = f'Kostenstellen-Abrechnung – {cost_center.number}'
            if hide_prices:
                title += ' (Kundenansicht)'
            story.append(Paragraph(title, styles['h1']))
            if cost_center.department:
                story.append(Paragraph(f'Abteilung: {cost_center.department}', styles['Normal']))
            story.append(Paragraph(f'Abrechnungsmonat: {month}', styles['Normal']))
            story.append(Spacer(1, 0.5*cm))

            if hide_prices:
                # Kundenansicht: keine Einzelpreise, nur Endbeträge
                header = ['VM-Name', 'vCPU', 'RAM (GB)', 'Zugewiesen an']
                data   = [header]
                for vm in vms:
                    data.append([
                        vm['name'],
                        str(vm['vcpus'] or '—'),
                        str(vm['memory_gb']),
                        vm['assigned_to'] or '—',
                    ])
                data.append(['', '', 'Gesamt/Monat', f"{total:,.2f} €"])
                data.append(['', '', 'Gesamt/Jahr',  f"{total*12:,.2f} €"])
                col_widths = [6.5*cm, 1.5*cm, 3*cm, 7.5*cm]
            else:
                header = ['VM-Name', 'vCPU', 'RAM (GB)', 'Zugewiesen an', 'Preisquelle', '€/Monat']
                data   = [header]
                for vm in vms:
                    data.append([
                        vm['name'],
                        str(vm['vcpus'] or '—'),
                        str(vm['memory_gb']),
                        vm['assigned_to'] or '—',
                        vm['pricing_source'],
                        f"{vm['cost_monthly']:,.2f} €",
                    ])
                data.append(['', '', '', '', 'Gesamt/Monat', f"{total:,.2f} €"])
                data.append(['', '', '', '', 'Gesamt/Jahr',  f"{total*12:,.2f} €"])
                col_widths = [5*cm, 1.5*cm, 2*cm, 4*cm, 3.5*cm, 2.5*cm]

            t = Table(data, colWidths=col_widths)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1d4ed8')),
                ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
                ('FONTNAME',   (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0, 0), (-1, -1), 9),
                ('ROWBACKGROUNDS', (0, 1), (-1, -3), [colors.white, colors.HexColor('#f8fafc')]),
                ('BACKGROUND', (0, -2), (-1, -1), colors.HexColor('#eff6ff')),
                ('FONTNAME',   (4, -2), (-1, -1), 'Helvetica-Bold'),
                ('GRID',       (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('ALIGN',      (1, 0), (-1, -1), 'RIGHT'),
                ('ALIGN',      (0, 0), (0, -1), 'LEFT'),
            ]))
            story.append(t)
            doc.build(story)
            buf.seek(0)
            resp = HttpResponse(buf, content_type='application/pdf')
            resp['Content-Disposition'] = (
                f'attachment; filename="chargeback_{cost_center.number}.pdf"'
            )
            return resp

        except ImportError:
            return redirect(f'?format=html')
