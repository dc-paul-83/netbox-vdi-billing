"""
Management Command: sync_horizon_tags

Fragt die Omnissa Horizon REST API ab und setzt den Tag "VDI-Persistent"
auf alle NetBox-VMs die in einem DEDICATED (persistenten) Pool sind.
VMs die nicht mehr persistent sind verlieren den Tag automatisch.

Konfiguration in NetBox configuration.py:
  PLUGINS_CONFIG = {
      'netbox_vdi_billing': {
          'horizon_instances': [
              {
                  'host':     'deopp-vc-horizon.megroup.global',
                  'domain':   'MEGROUP',
                  'username': 'svc-netbox',
                  'password': 'geheim',
              },
              {
                  'host':     'desto-vca-p01.megroup.global',
                  'domain':   'MEGROUP',
                  'username': 'svc-netbox',
                  'password': 'geheim',
              },
          ],
          'persistent_tag': 'VDI-Persistent',   # Standard-Tagname
      }
  }

Ausführung:
  # Dry-Run – zeigt was sich ändern würde
  python manage.py sync_horizon_tags --dry-run

  # Echter Lauf
  python manage.py sync_horizon_tags

Cron (täglich 01:30 Uhr, vor dem Billing-Cron):
  30 1 * * * /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py \\
      sync_horizon_tags >> /var/log/netbox/vdi_billing.log 2>&1
"""
import json
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
        # Enterprise-Zertifikate akzeptieren (self-signed)
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
        """GET mit automatischer Paginierung für /machines."""
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
        'Setzt/entfernt den VDI-Persistent-Tag auf NetBox-VMs '
        'anhand der Horizon API (nur DEDICATED Pools)'
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
            help='Tag-Name überschreiben (Standard aus Plugin-Config: "VDI-Persistent")',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN – nichts wird gespeichert ===\n'))

        # ── Plugin-Config lesen ───────────────────────────────────────────────
        plugin_cfg      = settings.PLUGINS_CONFIG.get('netbox_vdi_billing', {})
        instances       = plugin_cfg.get('horizon_instances', [])
        tag_name        = options['tag'] or plugin_cfg.get('persistent_tag', 'VDI-Persistent')

        if not instances:
            raise CommandError(
                'Keine Horizon-Instanzen konfiguriert.\n'
                'Bitte in configuration.py unter PLUGINS_CONFIG["netbox_vdi_billing"] '
                'den Schlüssel "horizon_instances" setzen.\n'
                'Siehe: python manage.py sync_horizon_tags --help'
            )

        # ── NetBox Tag holen oder anlegen ─────────────────────────────────────
        if not dry_run:
            tag_obj, created = Tag.objects.get_or_create(
                name=tag_name,
                defaults={'slug': tag_name.lower().replace(' ', '-'), 'color': '2196f3'},
            )
            if created:
                self.stdout.write(f'Tag "{tag_name}" in NetBox angelegt.\n')
        else:
            tag_obj = Tag.objects.filter(name=tag_name).first()

        # ── Horizon: Persistent VM-Namen sammeln ──────────────────────────────
        persistent_vm_names = set()   # VM-Namen aus Horizon (lowercase für Vergleich)
        persistent_display  = set()   # Originale Namen für Ausgabe

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
                self.stdout.write(self.style.SUCCESS(f'  ✓ Login erfolgreich'))

                # Alle Pools holen, nur DEDICATED filtern
                all_pools = client.get('/inventory/v2/desktop-pools')
                persistent_pools = [
                    p for p in (all_pools or [])
                    if (
                        p.get('automated_desktop_data', {}).get('user_assignment')
                        or p.get('user_assignment', '')
                    ) == 'DEDICATED'
                ]
                pool_ids = {p['id'] for p in persistent_pools}
                pool_names = {p['id']: p.get('display_name') or p.get('name', p['id'])
                              for p in persistent_pools}

                self.stdout.write(
                    f'  Pools gesamt: {len(all_pools or [])}, '
                    f'davon persistent (DEDICATED): {len(persistent_pools)}'
                )
                for p in persistent_pools:
                    self.stdout.write(f'    → {pool_names[p["id"]]}')

                if not pool_ids:
                    self.stdout.write(self.style.WARNING(
                        f'  Keine persistenten Pools auf {host} gefunden – übersprungen'
                    ))
                    continue

                # Alle Maschinen holen, auf persistent Pools einschränken
                all_machines = client.get('/inventory/v8/machines')
                machines = [m for m in (all_machines or []) if m.get('desktop_pool_id') in pool_ids]

                self.stdout.write(f'  Maschinen in persistenten Pools: {len(machines)}')

                for m in machines:
                    name = m.get('name', '')
                    if name:
                        persistent_vm_names.add(name.lower())
                        persistent_display.add(name)

            except CommandError as e:
                self.stderr.write(f'  ✗ {host}: {e}')
            except Exception as e:
                self.stderr.write(f'  ✗ {host}: Unerwarteter Fehler: {e}')

        self.stdout.write(
            f'\n{len(persistent_display)} persistente VDIs aus Horizon ermittelt.\n'
        )

        if not persistent_vm_names:
            raise CommandError(
                'Keine persistenten VMs aus Horizon erhalten – Abbruch. '
                'Bitte Zugangsdaten und Horizon-Erreichbarkeit prüfen.'
            )

        # ── NetBox: Tags setzen und entfernen ─────────────────────────────────
        tagged   = 0
        untagged = 0
        missing  = 0

        # Tag setzen: VMs die in Horizon persistent sind
        for vm_name in sorted(persistent_display):
            try:
                vm = VirtualMachine.objects.get(name=vm_name)
            except VirtualMachine.DoesNotExist:
                self.stdout.write(
                    f'  ? Nicht in NetBox: {vm_name}'
                )
                missing += 1
                continue

            already_tagged = tag_obj and vm.tags.filter(name=tag_name).exists()
            if already_tagged:
                continue

            self.stdout.write(f'  {"[DRY]" if dry_run else "✓"} Tag gesetzt: {vm_name}')
            if not dry_run and tag_obj:
                vm.tags.add(tag_obj)
            tagged += 1

        # Tag entfernen: VMs die den Tag haben aber nicht mehr persistent sind
        if tag_obj:
            tagged_vms = VirtualMachine.objects.filter(tags=tag_obj)
            for vm in tagged_vms:
                if vm.name.lower() not in persistent_vm_names:
                    self.stdout.write(
                        f'  {"[DRY]" if dry_run else "🗑"} Tag entfernt: {vm.name} '
                        f'(nicht mehr in Horizon persistent)'
                    )
                    if not dry_run:
                        vm.tags.remove(tag_obj)
                    untagged += 1

        # ── Zusammenfassung ───────────────────────────────────────────────────
        self.stdout.write('')
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Fertig: {tagged} Tags gesetzt, '
            f'{untagged} Tags entfernt, '
            f'{missing} VMs nicht in NetBox gefunden'
        ))
