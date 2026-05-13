"""
NetBox Custom Scripts: VDI Auto-Assignment

Wird unter Customization → Scripts im NetBox-Browser-Interface ausgeführt.
Kein SSH/CLI-Zugang erforderlich.

Skripte:
  AutoAssignVDI       – Automatisches Mapping aus NetBox-Feldern (mit Tag-Filter + Cleanup)
  ImportVDIFromCSV    – Manueller CSV-Import (Inhalt direkt ins Textfeld)
"""
import re
import csv
import io

from extras.scripts import Script, StringVar, ObjectVar, BooleanVar, ChoiceVar, TextVar
from virtualization.models import VirtualMachine
from netbox_vdi_billing.models import VDIBillingProfile, VDIAssignment


# ── Hilfs-Funktion ─────────────────────────────────────────────────────────────

def _get_field(vm, field_spec: str) -> str:
    """Liest einen Wert aus einer VM anhand der Feldspezifikation."""
    if not field_spec:
        return ''
    if field_spec == 'tenant':
        return vm.tenant.name if vm.tenant else ''
    if field_spec == 'role':
        return vm.role.name if vm.role else ''
    if field_spec == 'cluster':
        return vm.cluster.name if vm.cluster else ''
    if field_spec.startswith('custom:'):
        key = field_spec[7:]
        return str(vm.custom_field_data.get(key) or '')
    return ''


# ── Skript 1: Auto-Mapping ─────────────────────────────────────────────────────

class AutoAssignVDI(Script):
    """
    Erstellt oder aktualisiert VDIAssignment-Einträge für alle VMs mit einem
    bestimmten NetBox-Tag.

    Mit "Cleanup verwaister Einträge" werden Zuordnungen für VMs automatisch
    entfernt, die den Tag nicht mehr tragen — z.B. weil eine VM umgewidmet
    oder aus VDI-Betrieb genommen wurde.

    Tipp: Dry-Run = Häkchen bei "Commit" weglassen.
    """

    class Meta:
        name        = 'VDI Auto-Zuweisung'
        description = (
            'Erstellt/aktualisiert VDIAssignment-Einträge anhand von NetBox-Feldern. '
            'Optional: Einträge für VMs ohne VDI-Tag automatisch entfernen.'
        )
        commit_default = False    # Nutzer muss "Commit" explizit anhaken

    # ── Formularfelder ────────────────────────────────────────────────────────

    filter_tag = StringVar(
        label='VDI-Tag',
        description=(
            'Nur VMs mit diesem NetBox-Tag verarbeiten (z.B. "VDI"). '
            'Leer lassen = alle VMs. '
            'Empfohlen bei vCenter-Sync!'
        ),
        required=False,
        default='VDI',
    )

    cleanup_untagged = BooleanVar(
        label='Verwaiste Einträge entfernen',
        description=(
            'Entfernt VDIAssignment-Einträge für VMs, die den oben '
            'eingetragenen Tag nicht (mehr) haben. '
            'Wichtig wenn VMs umgewidmet oder aus VDI genommen werden.'
        ),
        default=True,
    )

    default_profile = ObjectVar(
        model=VDIBillingProfile,
        label='Standard-Preisprofil',
        description='Wird verwendet, wenn kein GPU-Profil greift',
        required=False,
    )

    cost_center_field = ChoiceVar(
        label='Kostenstellen-Feld',
        description='Welches NetBox-Feld als Kostenstelle verwendet werden soll',
        choices=[
            ('tenant',               'Tenant (Mandant)'),
            ('role',                 'Rolle'),
            ('cluster',              'Cluster-Name'),
            ('custom:cost_center',   'Custom-Field "cost_center"'),
        ],
        default='tenant',
    )

    custom_cost_center_field = StringVar(
        label='Custom-Field-Name (Kostenstelle)',
        description='Nur ausfüllen wenn der Feldname von "cost_center" abweicht, z.B. "kst"',
        required=False,
        default='',
    )

    department_field = ChoiceVar(
        label='Abteilungs-Feld',
        description='Welches NetBox-Feld als Abteilung verwendet werden soll (optional)',
        choices=[
            ('',                     '— keine —'),
            ('tenant',               'Tenant (Mandant)'),
            ('role',                 'Rolle'),
            ('cluster',              'Cluster-Name'),
            ('custom:department',    'Custom-Field "department"'),
        ],
        default='',
    )

    gpu_cluster_pattern = StringVar(
        label='GPU-Cluster-Muster (Regex)',
        description='Regex auf Cluster-Name für GPU-VMs, z.B. ".*gpu.*" oder "GPU-Cluster-.*"',
        required=False,
        default='',
    )

    gpu_profile = ObjectVar(
        model=VDIBillingProfile,
        label='GPU-Preisprofil',
        description='Profil für VMs in GPU-Clustern (überschreibt Standard-Profil)',
        required=False,
    )

    filter_cluster = StringVar(
        label='Nur Cluster (Regex)',
        description='Nur VMs verarbeiten, deren Cluster-Name diesem Muster entspricht',
        required=False,
        default='',
    )

    filter_role = StringVar(
        label='Nur Rolle',
        description='Nur VMs mit dieser Rolle verarbeiten (Teil-Übereinstimmung)',
        required=False,
        default='',
    )

    overwrite = BooleanVar(
        label='Bestehende Zuordnungen überschreiben',
        description='Bereits zugewiesene VMs werden ebenfalls aktualisiert (z.B. wenn Profil geändert wurde)',
        default=False,
    )

    # ── Ausführung ────────────────────────────────────────────────────────────

    def run(self, data, commit):
        default_profile  = data['default_profile']
        cc_field         = data['cost_center_field']
        dept_field       = data['department_field']
        gpu_pattern      = data.get('gpu_cluster_pattern', '').strip()
        gpu_profile      = data.get('gpu_profile')
        filter_cluster   = data.get('filter_cluster', '').strip()
        filter_role      = data.get('filter_role', '').strip()
        filter_tag       = data.get('filter_tag', '').strip()
        cleanup_untagged = data['cleanup_untagged']
        overwrite        = data['overwrite']

        # Eigenen Custom-Field-Namen übernehmen, falls angegeben
        custom_cc = data.get('custom_cost_center_field', '').strip()
        if custom_cc:
            cc_field = f'custom:{custom_cc}'

        if cleanup_untagged and not filter_tag:
            self.log_failure('Verwaiste Einträge entfernen erfordert einen VDI-Tag.')
            return

        cleaned = 0

        # ── Cleanup: Assignments für VMs ohne Tag entfernen ───────────────────
        if cleanup_untagged and filter_tag:
            tagged_vm_ids = set(
                VirtualMachine.objects.filter(tags__name=filter_tag)
                .values_list('pk', flat=True)
            )
            orphans = VDIAssignment.objects.exclude(
                virtual_machine_id__in=tagged_vm_ids
            ).select_related('virtual_machine')

            for a in orphans:
                self.log_warning(
                    f'Entfernt: <strong>{a.virtual_machine.name}</strong> '
                    f'– kein Tag „{filter_tag}" mehr'
                )
                if commit:
                    a.delete()
                cleaned += 1

            if cleaned:
                self.log_info(f'{cleaned} verwaiste Einträge {"entfernt" if commit else "gefunden (Dry-Run)"}.')

        # ── VM-Queryset ───────────────────────────────────────────────────────
        qs = VirtualMachine.objects.select_related(
            'tenant', 'cluster', 'role'
        ).prefetch_related('tags')

        if filter_tag:
            qs = qs.filter(tags__name=filter_tag)
        if filter_role:
            qs = qs.filter(role__name__icontains=filter_role)
        if filter_cluster:
            qs = qs.filter(cluster__name__iregex=filter_cluster)

        assigned_ids = set(
            VDIAssignment.objects.values_list('virtual_machine_id', flat=True)
        )

        created = updated = skipped = 0

        self.log_info(f'Verarbeite {qs.count()} VMs …')

        for vm in qs:
            exists = vm.pk in assigned_ids

            if exists and not overwrite:
                skipped += 1
                continue

            cost_center = _get_field(vm, cc_field) or ''
            department  = _get_field(vm, dept_field) or '' if dept_field else ''

            profile = default_profile
            if gpu_pattern and vm.cluster:
                if re.match(gpu_pattern, vm.cluster.name or '', re.IGNORECASE):
                    profile = gpu_profile or default_profile

            action = 'Aktualisiert' if exists else 'Erstellt'
            profile_name = profile.name if profile else '—'
            self.log_info(
                f'{action}: <strong>{vm.name}</strong> → '
                f'KST={cost_center or "—"}, Profil={profile_name}'
            )

            if commit:
                VDIAssignment.objects.update_or_create(
                    virtual_machine=vm,
                    defaults={
                        'cost_center': cost_center,
                        'department': department,
                        'profile': profile,
                    },
                )

            if exists:
                updated += 1
            else:
                created += 1

        parts = [
            f'{created} erstellt',
            f'{updated} aktualisiert',
            f'{skipped} übersprungen',
        ]
        if cleaned:
            parts.append(f'{cleaned} entfernt')

        summary = f'<strong>Ergebnis:</strong> {", ".join(parts)}'
        if not commit:
            summary += ' <em>(Dry-Run – nichts gespeichert)</em>'

        self.log_success(summary)
        return summary


# ── Skript 2: CSV-Import ───────────────────────────────────────────────────────

class ImportVDIFromCSV(Script):
    """
    Importiert VDIAssignment-Einträge aus einem CSV-Text.

    CSV-Format (Semikolon-getrennt, erste Zeile = Header):
      vm_name;cost_center;department;profile

    Beispiel:
      vm_name;cost_center;department;profile
      vdi-max-001;11554;Vertrieb;Standard VDI
      vdi-gpu-001;22100;Konstruktion;GPU-Workstation
    """

    class Meta:
        name        = 'VDI CSV-Import'
        description = 'Importiert VDIAssignment-Einträge aus einem CSV-Text (Semikolon-getrennt)'
        commit_default = False

    csv_data = TextVar(
        label='CSV-Inhalt',
        description=(
            'Semikolon-getrennte Tabelle. Erste Zeile muss Header sein: '
            'vm_name;cost_center;department;profile'
        ),
    )

    overwrite = BooleanVar(
        label='Bestehende Zuordnungen überschreiben',
        default=False,
    )

    def run(self, data, commit):
        overwrite = data['overwrite']
        raw = data['csv_data'].strip()

        reader = csv.DictReader(io.StringIO(raw), delimiter=';')

        created = updated = skipped = errors = 0

        for row in reader:
            vm_name      = row.get('vm_name', '').strip()
            cost_center  = row.get('cost_center', '').strip()
            department   = row.get('department', '').strip()
            profile_name = row.get('profile', '').strip()

            if not vm_name:
                continue

            try:
                vm = VirtualMachine.objects.get(name=vm_name)
            except VirtualMachine.DoesNotExist:
                self.log_warning(f'VM nicht gefunden: <strong>{vm_name}</strong>')
                errors += 1
                continue

            profile = None
            if profile_name:
                try:
                    profile = VDIBillingProfile.objects.get(name=profile_name)
                except VDIBillingProfile.DoesNotExist:
                    self.log_warning(
                        f'Profil nicht gefunden: <strong>{profile_name}</strong> '
                        f'(VM: {vm_name})'
                    )
                    errors += 1
                    continue

            exists = VDIAssignment.objects.filter(virtual_machine=vm).exists()

            if exists and not overwrite:
                skipped += 1
                continue

            action = 'Aktualisiert' if exists else 'Erstellt'
            self.log_info(
                f'{action}: <strong>{vm_name}</strong> → '
                f'KST={cost_center or "—"}, Profil={profile_name or "—"}'
            )

            if commit:
                VDIAssignment.objects.update_or_create(
                    virtual_machine=vm,
                    defaults={
                        'cost_center': cost_center,
                        'department': department,
                        'profile': profile,
                    },
                )

            if exists:
                updated += 1
            else:
                created += 1

        summary = (
            f'<strong>Ergebnis:</strong> '
            f'{created} erstellt, {updated} aktualisiert, '
            f'{skipped} übersprungen, {errors} Fehler'
        )
        if not commit:
            summary += ' <em>(Dry-Run – nichts gespeichert)</em>'

        if errors:
            self.log_failure(summary)
        else:
            self.log_success(summary)

        return summary
