"""
Management Command: auto_assign_vdi

Erstellt VDIAssignment-Einträge für alle noch nicht zugeordneten VMs.

Kostenstelle wird aus einem konfigurierbaren NetBox-Feld gelesen:
  --cost-center-field tenant       → VM.tenant.name
  --cost-center-field custom:feld  → VM.custom_field_data['feld']
  --cost-center-field role         → VM.role.name

Profil kann per Name gesetzt werden; optional Cluster-Regex für
automatische Profil-Auswahl (z.B. GPU-Cluster).

Beispiele:
  # Dry-Run: zeigt was gemacht würde, ohne zu speichern
  python manage.py auto_assign_vdi --dry-run

  # Alle VMs mit Tenant als Kostenstelle, Profil "Standard VDI"
  python manage.py auto_assign_vdi \\
    --profile "Standard VDI" \\
    --cost-center-field tenant

  # Nur VMs ohne bestehende Zuordnung, GPU-Cluster extra
  python manage.py auto_assign_vdi \\
    --profile "Standard VDI" \\
    --cost-center-field tenant \\
    --gpu-cluster-pattern "GPU*" \\
    --gpu-profile "GPU-Workstation" \\
    --skip-existing
"""
import re
import csv
import sys

from django.core.management.base import BaseCommand, CommandError
from virtualization.models import VirtualMachine
from netbox_vdi_billing.models import VDIBillingProfile, VDIAssignment


class Command(BaseCommand):
    help = 'Erstellt VDIAssignment-Einträge für alle noch nicht zugeordneten VMs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--profile',
            metavar='NAME',
            help='Standard-Preisprofil (Name), z.B. "Standard VDI"',
        )
        parser.add_argument(
            '--cost-center-field',
            default='tenant',
            metavar='FIELD',
            help=(
                'NetBox-Feld für die Kostenstelle. '
                'Optionen: tenant, role, custom:<feldname> '
                '(Standard: tenant)'
            ),
        )
        parser.add_argument(
            '--department-field',
            default='',
            metavar='FIELD',
            help='NetBox-Feld für die Abteilung (optional, gleiche Syntax wie --cost-center-field)',
        )
        parser.add_argument(
            '--gpu-cluster-pattern',
            default='',
            metavar='PATTERN',
            help='Glob/Regex auf Cluster-Name für GPU-VMs, z.B. "GPU*" oder ".*gpu.*"',
        )
        parser.add_argument(
            '--gpu-profile',
            default='',
            metavar='NAME',
            help='Profil-Name für GPU-VMs (überschreibt --profile für GPU-Cluster)',
        )
        parser.add_argument(
            '--filter-cluster',
            default='',
            metavar='PATTERN',
            help='Nur VMs in Clustern die diesem Muster entsprechen verarbeiten',
        )
        parser.add_argument(
            '--filter-role',
            default='',
            metavar='ROLE',
            help='Nur VMs mit dieser Rolle verarbeiten',
        )
        parser.add_argument(
            '--skip-existing',
            action='store_true',
            default=True,
            help='Bereits zugeordnete VMs überspringen (Standard: an)',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Bestehende Zuordnungen überschreiben',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Nur anzeigen, nicht speichern',
        )
        parser.add_argument(
            '--csv',
            metavar='FILE',
            help='CSV-Datei importieren statt Auto-Mapping (Spalten: vm_name,cost_center,department,profile)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN – nichts wird gespeichert ===\n'))

        if options['csv']:
            return self._handle_csv(options)
        return self._handle_auto(options)

    # ── CSV Import ────────────────────────────────────────────────────────────

    def _handle_csv(self, options):
        dry_run = options['dry_run']
        created = updated = skipped = errors = 0

        try:
            f = open(options['csv'], newline='', encoding='utf-8-sig')
        except FileNotFoundError:
            raise CommandError(f"CSV-Datei nicht gefunden: {options['csv']}")

        with f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                vm_name     = row.get('vm_name', '').strip()
                cost_center = row.get('cost_center', '').strip()
                department  = row.get('department', '').strip()
                profile_name = row.get('profile', '').strip()

                if not vm_name:
                    continue

                try:
                    vm = VirtualMachine.objects.get(name=vm_name)
                except VirtualMachine.DoesNotExist:
                    self.stderr.write(f'  ✗ VM nicht gefunden: {vm_name}')
                    errors += 1
                    continue

                profile = None
                if profile_name:
                    try:
                        profile = VDIBillingProfile.objects.get(name=profile_name)
                    except VDIBillingProfile.DoesNotExist:
                        self.stderr.write(f'  ✗ Profil nicht gefunden: {profile_name} (VM: {vm_name})')
                        errors += 1
                        continue

                exists = VDIAssignment.objects.filter(virtual_machine=vm).exists()
                if exists and not options['overwrite']:
                    skipped += 1
                    continue

                action = 'Aktualisiert' if exists else 'Erstellt'
                self.stdout.write(
                    f'  {"[DRY]" if dry_run else "✓"} {action}: {vm_name} → '
                    f'KST={cost_center or "–"} Profil={profile_name or "–"}'
                )

                if not dry_run:
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

        self._summary(created, updated, skipped, errors, dry_run)

    # ── Auto-Mapping ──────────────────────────────────────────────────────────

    def _handle_auto(self, options):
        dry_run        = options['dry_run']
        profile_name   = options.get('profile', '')
        cc_field       = options['cost_center_field']
        dept_field     = options.get('department_field', '')
        gpu_pattern    = options.get('gpu_cluster_pattern', '')
        gpu_profile_name = options.get('gpu_profile', '')
        filter_cluster = options.get('filter_cluster', '')
        filter_role    = options.get('filter_role', '')
        overwrite      = options.get('overwrite', False)

        # Profile laden
        default_profile = None
        if profile_name:
            try:
                default_profile = VDIBillingProfile.objects.get(name=profile_name)
            except VDIBillingProfile.DoesNotExist:
                raise CommandError(f'Profil nicht gefunden: "{profile_name}"')

        gpu_profile = None
        if gpu_profile_name:
            try:
                gpu_profile = VDIBillingProfile.objects.get(name=gpu_profile_name)
            except VDIBillingProfile.DoesNotExist:
                raise CommandError(f'GPU-Profil nicht gefunden: "{gpu_profile_name}"')

        # VM-Queryset aufbauen
        qs = VirtualMachine.objects.select_related('tenant', 'cluster', 'role')
        if filter_role:
            qs = qs.filter(role__name__icontains=filter_role)
        if filter_cluster:
            qs = qs.filter(cluster__name__iregex=filter_cluster)

        # Bereits zugeordnete VMs
        assigned_ids = set(
            VDIAssignment.objects.values_list('virtual_machine_id', flat=True)
        )

        created = updated = skipped = 0

        self.stdout.write(f'Verarbeite {qs.count()} VMs ...\n')

        for vm in qs:
            exists = vm.pk in assigned_ids

            if exists and not overwrite:
                skipped += 1
                continue

            # Kostenstelle bestimmen
            cost_center = self._get_field(vm, cc_field) or ''
            department  = self._get_field(vm, dept_field) or '' if dept_field else ''

            # Profil bestimmen (GPU-Cluster hat Vorrang)
            profile = default_profile
            if gpu_pattern and vm.cluster:
                if re.match(gpu_pattern, vm.cluster.name or '', re.IGNORECASE):
                    profile = gpu_profile or default_profile

            action = 'Aktualisiert' if exists else 'Erstellt'
            self.stdout.write(
                f'  {"[DRY]" if dry_run else "✓"} {action}: {vm.name:<40} '
                f'KST={cost_center or "–":<15} '
                f'Profil={profile.name if profile else "–"}'
            )

            if not dry_run:
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

        self._summary(created, updated, skipped, 0, dry_run)

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────

    def _get_field(self, vm, field_spec):
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

    def _summary(self, created, updated, skipped, errors, dry_run):
        self.stdout.write('')
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Fertig: {created} erstellt, {updated} aktualisiert, '
            f'{skipped} übersprungen, {errors} Fehler'
        ))
