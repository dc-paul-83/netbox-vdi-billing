"""
Management Command: sync_horizon_tags

Fragt die Omnissa Horizon REST API ab und:
  1. Setzt den Tag "VDI-Persistent" auf alle VMs in DEDICATED Pools
  2. Setzt den Tag "VDI-GPU" auf alle VMs in GPU-Pools (Pool-Name enthält "nvidia", "vgpu", "gpu")

Konfiguration in NetBox configuration.py:
  PLUGINS_CONFIG = {
      'netbox_vdi_billing': {
          'horizon_instances': [
              {
                  'host':     'horizon-opp.murrelektronik.com',
                  'domain':   'MEGroup',
                  'username': 'svc-netbox',
                  'password': 'geheim',
              },
          ],
          'persistent_tag':   'VDI-Persistent',  # Standard
          'gpu_tag':          'VDI-GPU',          # Standard
          'gpu_pool_pattern': 'nvidia|vgpu|gpu|grid',  # Regex auf Pool-Namen
      }
  }

Ausführung:
  # Dry-Run
  python manage.py sync_horizon_tags --dry-run

  # Echter Lauf
  python manage.py sync_horizon_tags

Cron (täglich 01:30 Uhr):
  30 1 * * * /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py \\
      sync_horizon_tags >> /var/log/netbox/vdi_billing.log 2>&1
"""
import json
import re
import ssl
import urllib.request
import urllib.error

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from extras.models import Tag
from virtualization.models import VirtualMachine


# ── Horizon REST Client ───────────────────────────────────────────────────────

class HorizonClient:
    """Minimaler Horizon REST API Client (kein externes Paket nötig)."""

    def __init__(self, host, domain, username, password):
        self.base     = f'https://{host}/rest'
        self.domain   = domain
        self.username = username
        self.password = password
        self.token    = None
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode    = ssl.CERT_NONE

    def _request(self, method, path, body=None):
        url     = f'{self.base}{path}'
        data    = json.dumps(body).encode() if body else None
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self._ctx, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise CommandError(
                f'Horizon API Fehler {e.code} bei {path}: {e.read().decode()[:200]}'
            )

    def login(self):
        result = self._request('POST', '/login', {
            'domain':   self.domain,
            'username': self.username,
            'password': self.password,
        })
        if not result.get('access_token'):
            raise CommandError('Horizon Login fehlgeschlagen – kein Token erhalten')
        self.token = result['access_token']

    def get(self, path):
        if '/machines' in path and 'page=' not in path:
            return self._paginate(path)
        return self._request('GET', path)

    def _paginate(self, base_path):
        sep  = '&' if '?' in base_path else '?'
        page = 1
        all_items = []
        while True:
            batch = self._request('GET', f'{base_path}{sep}page={page}&size=500')
            if not isinstance(batch, list) or not batch:
                break
            all_items.extend(batch)
            if len(batch) < 500:
                break
            page += 1
        return all_items


# ── Command ───────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        'Setzt/entfernt VDI-Tags auf NetBox-VMs anhand der Horizon API.\n'
        '  VDI-Persistent → VMs in DEDICATED Pools\n'
        '  VDI-GPU        → VMs in GPU-Pools (Pool-Name enthält nvidia/vgpu/gpu/grid)'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Nur anzeigen, nichts speichern',
        )
        parser.add_argument(
            '--tag',
            default='',
            metavar='NAME',
            help='Persistent-Tag überschreiben (Standard aus Config: "VDI-Persistent")',
        )
        parser.add_argument(
            '--gpu-tag',
            default='',
            metavar='NAME',
            help='GPU-Tag überschreiben (Standard aus Config: "VDI-GPU")',
        )
        parser.add_argument(
            '--gpu-pool-pattern',
            default='',
            metavar='REGEX',
            help='Regex für GPU-Pool-Namen (Standard: "nvidia|vgpu|gpu|grid")',
        )
        parser.add_argument(
            '--no-gpu',
            action='store_true',
            help='GPU-Erkennung deaktivieren',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN – nichts wird gespeichert ===\n'))

        # ── Plugin-Config lesen ───────────────────────────────────────────────
        plugin_cfg      = settings.PLUGINS_CONFIG.get('netbox_vdi_billing', {})
        instances       = plugin_cfg.get('horizon_instances', [])
        tag_name        = options['tag'] or plugin_cfg.get('persistent_tag', 'VDI-Persistent')
        gpu_tag_name    = options['gpu_tag'] or plugin_cfg.get('gpu_tag', 'VDI-GPU')
        gpu_pattern_str = (
            options['gpu_pool_pattern']
            or plugin_cfg.get('gpu_pool_pattern', r'nvidia|vgpu|gpu|grid')
        )
        sync_gpu        = not options['no_gpu']

        if not instances:
            raise CommandError(
                'Keine Horizon-Instanzen konfiguriert.\n'
                'Bitte in configuration.py unter PLUGINS_CONFIG["netbox_vdi_billing"] '
                'den Schlüssel "horizon_instances" setzen.'
            )

        gpu_pattern = re.compile(gpu_pattern_str, re.IGNORECASE)

        # ── NetBox Tags holen oder anlegen ────────────────────────────────────
        if not dry_run:
            tag_obj, created = Tag.objects.get_or_create(
                name=tag_name,
                defaults={'slug': tag_name.lower().replace(' ', '-'), 'color': '2196f3'},
            )
            if created:
                self.stdout.write(f'Tag "{tag_name}" in NetBox angelegt.\n')

            if sync_gpu:
                gpu_tag_obj, created = Tag.objects.get_or_create(
                    name=gpu_tag_name,
                    defaults={'slug': gpu_tag_name.lower().replace(' ', '-'), 'color': 'ff9800'},
                )
                if created:
                    self.stdout.write(f'Tag "{gpu_tag_name}" in NetBox angelegt.\n')
            else:
                gpu_tag_obj = None
        else:
            tag_obj     = Tag.objects.filter(name=tag_name).first()
            gpu_tag_obj = Tag.objects.filter(name=gpu_tag_name).first() if sync_gpu else None

        # ── Horizon: VM-Namen nach Kategorie sammeln ──────────────────────────
        persistent_vm_names = set()   # lowercase für Vergleich
        persistent_display  = set()   # Original für Ausgabe
        gpu_vm_names        = set()   # lowercase
        gpu_display         = set()   # Original

        for idx, inst in enumerate(instances, 1):
            host     = inst.get('host', '')
            domain   = inst.get('domain', '')
            username = inst.get('username', '')
            password = inst.get('password', '')

            if not all([host, domain, username, password]):
                self.stderr.write(
                    f'  ✗ Instanz {idx} ({host}): Zugangsdaten unvollständig – übersprungen'
                )
                continue

            self.stdout.write(f'Verbinde mit Horizon {host} ...')
            try:
                client = HorizonClient(host, domain, username, password)
                client.login()
                self.stdout.write(self.style.SUCCESS('  ✓ Login erfolgreich'))

                # Alle Pools holen
                all_pools = client.get('/inventory/v2/desktop-pools')

                # Persistente Pools (DEDICATED)
                persistent_pools = [
                    p for p in (all_pools or [])
                    if (
                        p.get('automated_desktop_data', {}).get('user_assignment')
                        or p.get('user_assignment', '')
                    ) == 'DEDICATED'
                ]
                pool_ids = {p['id'] for p in persistent_pools}

                # GPU-Pools (Name matcht gpu_pattern)
                gpu_pool_ids = set()
                if sync_gpu:
                    for p in persistent_pools:
                        pname = p.get('display_name') or p.get('name', '')
                        if gpu_pattern.search(pname):
                            gpu_pool_ids.add(p['id'])

                pool_names = {
                    p['id']: p.get('display_name') or p.get('name', p['id'])
                    for p in persistent_pools
                }

                self.stdout.write(
                    f'  Pools gesamt: {len(all_pools or [])}, '
                    f'persistent (DEDICATED): {len(persistent_pools)}, '
                    f'davon GPU-Pools: {len(gpu_pool_ids)}'
                )
                for p in persistent_pools:
                    gpu_marker = ' 🎮 GPU' if p['id'] in gpu_pool_ids else ''
                    self.stdout.write(f'    → {pool_names[p["id"]]}{gpu_marker}')

                if not pool_ids:
                    self.stdout.write(self.style.WARNING(
                        f'  Keine persistenten Pools auf {host} – übersprungen'
                    ))
                    continue

                # Alle Maschinen in persistenten Pools
                all_machines = client.get('/inventory/v8/machines')
                machines = [
                    m for m in (all_machines or [])
                    if m.get('desktop_pool_id') in pool_ids
                ]
                self.stdout.write(f'  Maschinen in persistenten Pools: {len(machines)}')

                for m in machines:
                    name = m.get('name', '')
                    if not name:
                        continue
                    persistent_vm_names.add(name.lower())
                    persistent_display.add(name)
                    # GPU: Pool ist GPU-Pool ODER Maschine hat num_gpus > 0
                    pool_id = m.get('desktop_pool_id', '')
                    num_gpus = m.get('num_gpus', 0) or 0
                    if sync_gpu and (pool_id in gpu_pool_ids or num_gpus > 0):
                        gpu_vm_names.add(name.lower())
                        gpu_display.add(name)

            except CommandError as e:
                self.stderr.write(f'  ✗ {host}: {e}')
            except Exception as e:
                self.stderr.write(f'  ✗ {host}: Unerwarteter Fehler: {e}')

        self.stdout.write(
            f'\n{len(persistent_display)} persistente VDIs, '
            f'{len(gpu_display)} GPU-VDIs aus Horizon ermittelt.\n'
        )

        if not persistent_vm_names:
            raise CommandError(
                'Keine persistenten VMs aus Horizon erhalten – Abbruch. '
                'Zugangsdaten und Horizon-Erreichbarkeit prüfen.'
            )

        # ── NetBox: Persistent-Tags setzen / entfernen ────────────────────────
        tagged = untagged = missing = 0

        for vm_name in sorted(persistent_display):
            try:
                vm = VirtualMachine.objects.get(name=vm_name)
            except VirtualMachine.DoesNotExist:
                self.stdout.write(f'  ? Nicht in NetBox: {vm_name}')
                missing += 1
                continue

            already = tag_obj and vm.tags.filter(name=tag_name).exists()
            if not already:
                self.stdout.write(f'  {"[DRY]" if dry_run else "✓"} Persistent-Tag gesetzt: {vm_name}')
                if not dry_run and tag_obj:
                    vm.tags.add(tag_obj)
                tagged += 1

        if tag_obj:
            for vm in VirtualMachine.objects.filter(tags=tag_obj):
                if vm.name.lower() not in persistent_vm_names:
                    self.stdout.write(
                        f'  {"[DRY]" if dry_run else "🗑"} Persistent-Tag entfernt: {vm.name}'
                    )
                    if not dry_run:
                        vm.tags.remove(tag_obj)
                    untagged += 1

        # ── NetBox: GPU-Tags setzen / entfernen ───────────────────────────────
        gpu_tagged = gpu_untagged = 0

        if sync_gpu and gpu_display:
            self.stdout.write(f'\nGPU-VMs ({len(gpu_display)}):')
            for vm_name in sorted(gpu_display):
                try:
                    vm = VirtualMachine.objects.get(name=vm_name)
                except VirtualMachine.DoesNotExist:
                    continue

                already = gpu_tag_obj and vm.tags.filter(name=gpu_tag_name).exists()
                if not already:
                    self.stdout.write(
                        f'  {"[DRY]" if dry_run else "🎮"} GPU-Tag gesetzt: {vm_name}'
                    )
                    if not dry_run and gpu_tag_obj:
                        vm.tags.add(gpu_tag_obj)
                    gpu_tagged += 1

            if gpu_tag_obj:
                for vm in VirtualMachine.objects.filter(tags=gpu_tag_obj):
                    if vm.name.lower() not in gpu_vm_names:
                        self.stdout.write(
                            f'  {"[DRY]" if dry_run else "🗑"} GPU-Tag entfernt: {vm.name}'
                        )
                        if not dry_run:
                            vm.tags.remove(gpu_tag_obj)
                        gpu_untagged += 1

        # ── Zusammenfassung ───────────────────────────────────────────────────
        self.stdout.write('')
        prefix = '[DRY RUN] ' if dry_run else ''
        msg = (
            f'{prefix}Fertig: '
            f'{tagged} Persistent-Tags gesetzt, {untagged} entfernt, '
            f'{missing} nicht in NetBox'
        )
        if sync_gpu:
            msg += f' | {gpu_tagged} GPU-Tags gesetzt, {gpu_untagged} entfernt'
        self.stdout.write(self.style.SUCCESS(msg))
