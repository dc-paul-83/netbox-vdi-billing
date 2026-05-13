from collections import defaultdict
from netbox.views import generic as nb_generic
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View
from netbox.views import generic

from . import filtersets, forms, models, tables


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
    queryset = models.VDIAssignment.objects.select_related('virtual_machine', 'profile')


class VDIAssignmentListView(generic.ObjectListView):
    queryset = models.VDIAssignment.objects.select_related('virtual_machine', 'profile')
    table = tables.VDIAssignmentTable
    filterset = filtersets.VDIAssignmentFilterSet


class VDIAssignmentEditView(generic.ObjectEditView):
    queryset = models.VDIAssignment.objects.all()
    form = forms.VDIAssignmentForm


class VDIAssignmentDeleteView(generic.ObjectDeleteView):
    queryset = models.VDIAssignment.objects.all()


class VDIAssignmentChangeLogView(nb_generic.ObjectChangeLogView):
    queryset = models.VDIAssignment.objects.all()


# ─── Chargeback Übersicht ─────────────────────────────────────────────────────

def _build_chargeback_groups(assignments):
    """Gruppiert Zuordnungen nach Kostenstelle und berechnet Summen."""
    raw = defaultdict(lambda: {
        'cost_center': '',
        'department': '',
        'vms': [],
        'total_monthly': 0.0,
    })

    for a in assignments:
        key = a.cost_center or '⚠ Keine Kostenstelle'
        grp = raw[key]
        grp['cost_center'] = key
        if not grp['department'] and a.department:
            grp['department'] = a.department
        cost = a.cost_monthly
        grp['vms'].append({
            'name': a.virtual_machine.name,
            'vcpus': a.virtual_machine.vcpus,
            'memory_gb': round(float(a.virtual_machine.memory or 0) / 1024, 1),
            'assigned_to': a.assigned_to,
            'profile': str(a.profile) if a.profile else None,
            'cost_override': float(a.cost_override) if a.cost_override is not None else None,
            'cost_monthly': cost,
            'pricing_source': a.pricing_source,
            'vm_url': a.virtual_machine.get_absolute_url(),
            'assignment_url': a.get_absolute_url(),
        })
        grp['total_monthly'] += cost

    groups = list(raw.values())
    # Ohne Kostenstelle ans Ende
    groups.sort(key=lambda g: (g['cost_center'].startswith('⚠'), g['cost_center'].lower()))
    for g in groups:
        g['total_yearly'] = round(g['total_monthly'] * 12, 2)
        g['total_monthly'] = round(g['total_monthly'], 2)
        g['vm_count'] = len(g['vms'])
    return groups


class ChargebackOverviewView(LoginRequiredMixin, View):
    template_name = 'netbox_vdi_billing/chargeback_overview.html'

    def get(self, request):
        from django.shortcuts import render
        assignments = models.VDIAssignment.objects.select_related(
            'virtual_machine', 'profile'
        ).order_by('cost_center', 'virtual_machine__name')

        groups = _build_chargeback_groups(assignments)
        total_monthly = sum(g['total_monthly'] for g in groups)
        total_yearly  = round(total_monthly * 12, 2)
        total_vms     = sum(g['vm_count'] for g in groups)

        return render(request, self.template_name, {
            'groups': groups,
            'total_monthly': round(total_monthly, 2),
            'total_yearly': total_yearly,
            'total_vms': total_vms,
            'assigned_count': models.VDIAssignment.objects.filter(
                cost_center__gt='').count(),
            'unassigned_count': models.VDIAssignment.objects.filter(
                cost_center='').count(),
        })


# ─── PDF / Druckansicht pro Kostenstelle ─────────────────────────────────────

class ChargebackPrintView(LoginRequiredMixin, View):
    """
    Druckoptimierte HTML-Ansicht für eine Kostenstelle.
    Browser: Datei → Drucken → Als PDF speichern.
    Alternativ: reportlab-PDF wenn das Paket installiert ist.
    """

    def get(self, request, cost_center):
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
                'name': a.virtual_machine.name,
                'vcpus': a.virtual_machine.vcpus,
                'memory_gb': round(float(a.virtual_machine.memory or 0) / 1024, 1),
                'assigned_to': a.assigned_to,
                'pricing_source': a.pricing_source,
                'cost_monthly': cost,
            })

        department = assignments.first().department or ''

        # Versuche reportlab-PDF; Fallback: print-HTML
        fmt = request.GET.get('format', 'html')
        if fmt == 'pdf':
            return self._pdf_response(cost_center, department, vms, total)

        from django.shortcuts import render
        from datetime import date
        return render(request, 'netbox_vdi_billing/chargeback_print.html', {
            'cost_center': cost_center,
            'department': department,
            'vms': vms,
            'total_monthly': round(total, 2),
            'total_yearly': round(total * 12, 2),
            'month': date.today().strftime('%B %Y'),
        })

    def _pdf_response(self, cost_center, department, vms, total):
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
            story = []

            month = date.today().strftime('%B %Y')
            story.append(Paragraph(f'Chargeback – Kostenstelle {cost_center}', styles['h1']))
            if department:
                story.append(Paragraph(f'Abteilung: {department}', styles['Normal']))
            story.append(Paragraph(f'Abrechnungsmonat: {month}', styles['Normal']))
            story.append(Spacer(1, 0.5*cm))

            header = ['VM-Name', 'vCPU', 'RAM (GB)', 'Zugewiesen an', 'Preisquelle', '€/Monat']
            data = [header]
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

            t = Table(data, colWidths=[5*cm, 1.5*cm, 2*cm, 4*cm, 3.5*cm, 2.5*cm])
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
                f'attachment; filename="chargeback_{cost_center}.pdf"'
            )
            return resp

        except ImportError:
            # reportlab nicht installiert → print-HTML als Fallback
            from django.shortcuts import redirect
            return redirect(f'?format=html')
