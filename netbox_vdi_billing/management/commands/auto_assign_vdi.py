"""
Management Command: auto_assign_vdi

Erstellt/aktualisiert VDIAssignment-Einträge für VMs und räumt veraltete
Zuordnungen auf.

Kostenstelle wird aus einem konfigurierbaren NetBox-Feld gelesen:
  --cost-center-field tenant       → VM.tenant.name
  --cost-center-field custom:feld  → VM.custom_field_data['feld']
  --cost-center-field role         → VM.role.name

Rollen-basierter Workflow (empfohlen bei netbox-sync mit vm_role_relation):
  # Nur VMs mit Rolle "VDI" zuordnen; verwaiste Einträge entfernen
  python manage.py auto_assign_vdi \\
    --profile "Standard VDI" \\
    --cost-center-field tenant \\
    --filter-role VDI \\
    --cleanup

  # Dry-Run zuerst!
  python manage.py auto_assign_vdi \\
    --profile "Standard VDI" \\
    --cost-center-field tenant \\
    --filter-role VDI \\
    --cleanup \\
    --dry-run

Für cron (täglich 02:00 Uhr):
  0 2 * * * /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py \\
      auto_assign_vdi --profile "Standard VDI" --cost-center-field tenant \\
      --filter-role VDI --cleanup >> /var/log/netbox/vdi_billing.log 2>&1
"""
import re
import csv

from django.core.management.base import BaseCommand, CommandError
from virtualization.models import VirtualMachine
from netbox_vdi_billing.models import CostCenter, VDIBillingProfile, VDIAssignment


class Command(BaseCommand):
    help = 'Erstellt/aktualisiert VDIAssignment-Einträge und räumt verwaiste Zuordnungen auf'

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
                'Optionen: tenant, role, cluster, custom:<feldname> '
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
            '--filter-role',
            default='',
            metavar='ROLE',
            help=(
                'Nur VMs mit dieser Rolle verarbeiten (Teil-Übereinstimmung), z.B. "VDI". '
                'Empfohlen bei netbox-sync mit vm_role_relation = .* = VDI.'
            ),
        )
        parser.add_argument(
            '--filter-tag',
            default='',
            metavar='TAG',
            help='Nur VMs mit diesem NetBox-Tag verarbeiten, z.B. "VDI".',
        )
        parser.add_argument(
            '--filter-cluster',
            default='',
            metavar='PATTERN',
            help='Nur VMs in Clustern die diesem Regex entsprechen verarbeiten',
        )
        parser.add_argument(
            '--filter-name',
            default='',
            metavar='REGEX',
            help='Nur VMs deren Name diesem Regex entspricht, z.B. "^site-vdi-.*"',
        )
        parser.add_argument(
            '--exclude-tag',
            action='append',
            default=[],
            metavar='TAG',
            help=(
                'VMs mit diesem Tag ausschließen. Mehrfach verwendbar: '
                '--exclude-tag Concurrent --exclude-tag "Horizon-DE". '
                'Nützlich mit vm_tag_source = parent_folder_1 in netbox-sync.'
            ),
        )
        parser.add_argument(
            '--exclude-name',
            default='',
            metavar='REGEX',
            help='VMs ausschließen deren Name diesem Regex entspricht, z.B. ".*replica.*|.*template.*"',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help=(
                'Entfernt VDIAssignment-Einträge für VMs, die nicht mehr den '
                'aktiven Filtern (--filter-role / --filter-tag / --filter-cluster) '
                'entsprechen. Wichtig wenn VMs ihren VDI-Status verlieren oder '
                'umgewidmet werden. Setzt mindestens einen Filter voraus.'
            ),
        )
        # Rückwärtskompatibilität
        parser.add_argument(
            '--cleanup-untagged',
            action='store_true',
            help='Veraltet – bitte --cleanup verwenden.',
        )
        parser.add_argument(
            '--gpu-cluster-pattern',
            default='',
            metavar='PATTERN',
            help='Regex auf Cluster-Name für GPU-VMs, z.B. ".*gpu.*"',
        )
        parser.add_argument(
            '--gpu-profile',
            default='',
            metavar='NAME',
            help='Profil-Name für GPU-VMs (überschreibt --profile für GPU-Cluster)',
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
            help='CSV-Datei importieren statt Auto-Mapping (Spalten: vm_name;cost_center;department;profile)',
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
                vm_name      = row.get('vm_name', '').strip()
                cost_center  = row.get('cost_center', '').strip()
                department   = row.get('department', '').strip()
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

                # Kostenstelle als Objekt
                cost_center_obj = None
                if cost_center:
                    cost_center_obj, _ = CostCenter.objects.get_or_create(
                        number=cost_center,
                        defaults={'name': cost_center, 'department': department},
                    )

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
                            'cost_center': cost_center_obj,
                            'profile': profile,
                        },
                    )
                if exists:
                    updated += 1
                else:
                    created += 1

        self._summary(created, updated, skipped, 0, 0, dry_run)

    # ── Auto-Mapping ──────────────────────────────────────────────────────────

    def _handle_auto(self, options):
        dry_run          = options['dry_run']
        profile_name     = options.get('profile', '')
        cc_field         = options['cost_center_field']
        dept_field       = options.get('department_field', '')
        gpu_pattern      = options.get('gpu_cluster_pattern', '')
        gpu_profile_name = options.get('gpu_profile', '')
        filter_role      = options.get('filter_role', '')
        filter_tag       = options.get('filter_tag', '')
        filter_cluster   = options.get('filter_cluster', '')
        filter_name      = options.get('filter_name', '')
        exclude_tags     = options.get('exclude_tag', [])
        exclude_name     = options.get('exclude_name', '')
        overwrite        = options.get('overwrite', False)
        # --cleanup und --cleanup-untagged (veraltet) zusammenführen
        do_cleanup       = options.get('cleanup', False) or options.get('cleanup_untagged', False)

        if do_cleanup and not any([filter_role, filter_tag, filter_cluster]):
            raise CommandError(
                '--cleanup erfordert mindestens einen Filter: '
                '--filter-role, --filter-tag oder --filter-cluster'
            )

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

        # ── Cleanup: Assignments für VMs entfernen die nicht mehr passen ─────
        cleaned = 0
        if do_cleanup:
            valid_qs = VirtualMachine.objects.all()
            reasons = []
            if filter_role:
                valid_qs = valid_qs.filter(role__name__icontains=filter_role)
                reasons.append(f'Rolle "{filter_role}"')
            if filter_tag:
                valid_qs = valid_qs.filter(tags__name=filter_tag)
                reasons.append(f'Tag "{filter_tag}"')
            if filter_cluster:
                valid_qs = valid_qs.filter(cluster__name__iregex=filter_cluster)
                reasons.append(f'Cluster "{filter_cluster}"')

            for tag in exclude_tags:
                valid_qs = valid_qs.exclude(tags__name=tag)
            if filter_name:
                valid_qs = valid_qs.filter(name__iregex=filter_name)
            if exclude_name:
                valid_qs = valid_qs.exclude(name__iregex=exclude_name)

            valid_ids = set(valid_qs.values_list('pk', flat=True))
            reason_str = ' + '.join(reasons) if reasons else 'aktiven Filtern'

            orphans = VDIAssignment.objects.exclude(
                virtual_machine_id__in=valid_ids
            ).select_related('virtual_machine')

            for a in orphans:
                self.stdout.write(
                    f'  {"[DRY]" if dry_run else "🗑"} Entfernt: {a.virtual_machine.name} '
                    f'(entspricht nicht mehr: {reason_str})'
                )
                if not dry_run:
                    a.delete()
                cleaned += 1

            if cleaned:
                self.stdout.write('')

        # ── VM-Queryset aufbauen ──────────────────────────────────────────────
        qs = VirtualMachine.objects.select_related(
            'tenant', 'cluster', 'role'
        ).prefetch_related('tags')

        if filter_role:
            qs = qs.filter(role__name__icontains=filter_role)
        if filter_tag:
            qs = qs.filter(tags__name=filter_tag)
        if filter_cluster:
            qs = qs.filter(cluster__name__iregex=filter_cluster)
        if filter_name:
            qs = qs.filter(name__iregex=filter_name)
        for tag in exclude_tags:
            qs = qs.exclude(tags__name=tag)
        if exclude_name:
            qs = qs.exclude(name__iregex=exclude_name)

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

            cost_center_str = self._get_field(vm, cc_field) or ''
            dept_str        = self._get_field(vm, dept_field) or '' if dept_field else ''

            # Kostenstelle als Objekt suchen oder anlegen
            cost_center_obj = None
            if cost_center_str:
                cost_center_obj, _ = CostCenter.objects.get_or_create(
                    number=cost_center_str,
                    defaults={'name': cost_center_str, 'department': dept_str},
                )

            profile = default_profile
            if gpu_pattern and vm.cluster:
                if re.match(gpu_pattern, vm.cluster.name or '', re.IGNORECASE):
                    profile = gpu_profile or default_profile

            action = 'Aktualisiert' if exists else 'Erstellt'
            self.stdout.write(
                f'  {"[DRY]" if dry_run else "✓"} {action}: {vm.name:<40} '
                f'KST={cost_center_str or "–":<15} '
                f'Profil={profile.name if profile else "–"}'
            )

            if not dry_run:
                VDIAssignment.objects.update_or_create(
                    virtual_machine=vm,
                    defaults={
                        'cost_center': cost_center_obj,
                        'profile': profile,
                    },
                )

            if exists:
                updated += 1
            else:
                created += 1

        self._summary(created, updated, skipped, cleaned, 0, dry_run)

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

    def _summary(self, created, updated, skipped, cleaned, errors, dry_run):
        self.stdout.write('')
        prefix = '[DRY RUN] ' if dry_run else ''
        parts = [
            f'{created} erstellt',
            f'{updated} aktualisiert',
            f'{skipped} übersprungen',
        ]
        if cleaned:
            parts.append(f'{cleaned} entfernt')
        if errors:
            parts.append(f'{errors} Fehler')
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Fertig: {", ".join(parts)}'
        ))
