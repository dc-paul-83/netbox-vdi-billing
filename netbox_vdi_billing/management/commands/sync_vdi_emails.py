"""
Management Command: sync_vdi_emails

Liest für jede VDI-VM den zugewiesenen Benutzer aus Horizon,
sucht dessen E-Mail-Adresse im Active Directory (via NetBox LDAP-Config)
und speichert sie in VDIAssignment.email.

Dabei wird auch VDIAssignment.assigned_to mit dem AD-Anzeigenamen befüllt,
falls er noch leer ist.

Voraussetzungen:
  - NetBox muss mit LDAP-Auth konfiguriert sein (AUTH_LDAP_* in configuration.py)
  - Horizon-Instanzen müssen unter PLUGINS_CONFIG['netbox_vdi_billing']['horizon_instances']
    konfiguriert sein (gleiche Config wie sync_horizon_tags)

Ausführung:
  # Dry-Run
  python manage.py sync_vdi_emails --dry-run

  # Echter Lauf
  python manage.py sync_vdi_emails

  # Nur bestimmte VMs (Regex auf VM-Name)
  python manage.py sync_vdi_emails --filter-name "^atwie-vdi-.*"

Cron (täglich 02:30 Uhr, nach sync_horizon_tags und auto_assign_vdi):
  30 2 * * * /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py \\
      sync_vdi_emails >> /var/log/netbox/vdi_billing.log 2>&1
"""
import json
import re
import ssl
import urllib.request
import urllib.error

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from virtualization.models import VirtualMachine
from netbox_vdi_billing.models import VDIAssignment


# ── Horizon Client (vereinfacht, analog sync_horizon_tags) ───────────────────

class HorizonClient:
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
                f'Horizon API {e.code} bei {path}: {e.read().decode()[:200]}'
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

    def _paginate(self, path):
        sep  = '&' if '?' in path else '?'
        page, items = 1, []
        while True:
            batch = self._request('GET', f'{path}{sep}page={page}&size=500')
            if not isinstance(batch, list) or not batch:
                break
            items.extend(batch)
            if len(batch) < 500:
                break
            page += 1
        return items

    def get_machines(self):
        return self._paginate('/inventory/v8/machines')

    def get_pools(self):
        return self._request('GET', '/inventory/v2/desktop-pools') or []

    def get_pool_assignments(self, pool_id):
        """Gibt {machine_id: username} zurück für einen dedicated Pool."""
        try:
            result = self._request(
                'GET', f'/inventory/v1/desktop-pools/{pool_id}/desktop-assignments'
            )
            return result or []
        except CommandError:
            return []

    def get_user(self, user_id):
        """Gibt AD-User-Objekt zurück (enthält login_name / sam_account_name)."""
        try:
            return self._request('GET', f'/inventory/v1/ad-users-or-groups/{user_id}')
        except CommandError:
            return None


# ── LDAP-Config laden ────────────────────────────────────────────────────────

def _load_ldap_config():
    """
    Liest LDAP-Einstellungen aus Django-Settings ODER direkt aus
    /opt/netbox/netbox/netbox/ldap_config.py (NetBox-Standard-Pfad).
    Gibt dict mit server_uri, bind_dn, bind_password, search_base zurück.
    """
    server_uri    = getattr(settings, 'AUTH_LDAP_SERVER_URI', '')
    bind_dn       = getattr(settings, 'AUTH_LDAP_BIND_DN', '')
    bind_password = getattr(settings, 'AUTH_LDAP_BIND_PASSWORD', '')
    search_base   = ''

    user_search = getattr(settings, 'AUTH_LDAP_USER_SEARCH', None)
    if user_search and hasattr(user_search, 'base_dn'):
        search_base = user_search.base_dn

    # Fallback 1: Plugin-Config (PLUGINS_CONFIG['netbox_vdi_billing'])
    if not server_uri:
        plugin_cfg    = settings.PLUGINS_CONFIG.get('netbox_vdi_billing', {})
        server_uri    = plugin_cfg.get('ldap_server', server_uri)
        bind_dn       = plugin_cfg.get('ldap_bind_dn', bind_dn)
        bind_password = plugin_cfg.get('ldap_bind_password', bind_password)
        search_base   = plugin_cfg.get('ldap_search_base', search_base)

    # Fallback 2: ldap_config.py direkt als Modul laden
    if not server_uri:
        import importlib.util, os
        candidates = [
            '/opt/netbox/netbox/netbox/ldap_config.py',
            os.path.join(getattr(settings, 'BASE_DIR', ''), 'netbox', 'ldap_config.py'),
        ]
        for path in candidates:
            if os.path.exists(path):
                spec   = importlib.util.spec_from_file_location('ldap_config', path)
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                    server_uri    = getattr(module, 'AUTH_LDAP_SERVER_URI', server_uri)
                    bind_dn       = getattr(module, 'AUTH_LDAP_BIND_DN', bind_dn)
                    bind_password = getattr(module, 'AUTH_LDAP_BIND_PASSWORD', bind_password)
                    us = getattr(module, 'AUTH_LDAP_USER_SEARCH', None)
                    if us and hasattr(us, 'base_dn'):
                        search_base = us.base_dn
                except Exception:
                    pass
                break

    return {
        'server_uri':    server_uri,
        'bind_dn':       bind_dn,
        'bind_password': bind_password,
        'search_base':   search_base,
    }


# ── LDAP-Abfrage ─────────────────────────────────────────────────────────────

def _ldap_lookup(usernames: list[str]) -> dict[str, dict]:
    """
    Gibt {username_lower: {'email': '...', 'display_name': '...'}} zurück.
    Nutzt AUTH_LDAP_* aus Django-Settings oder ldap_config.py direkt.
    """
    try:
        import ldap as _ldap
    except ImportError:
        raise CommandError(
            'python-ldap ist nicht installiert. '
            'Bitte "pip install python-ldap" ausführen.'
        )

    cfg = _load_ldap_config()
    server_uri  = cfg['server_uri']
    bind_dn     = cfg['bind_dn']
    bind_password = cfg['bind_password']
    search_base = cfg['search_base']

    if not server_uri:
        raise CommandError(
            'AUTH_LDAP_SERVER_URI nicht gefunden – weder in Django-Settings '
            'noch in /opt/netbox/netbox/netbox/ldap_config.py.'
        )
    if not search_base:
        raise CommandError(
            'AUTH_LDAP_USER_SEARCH / search_base nicht gefunden.'
        )

    conn = _ldap.initialize(server_uri)
    conn.set_option(_ldap.OPT_REFERRALS, 0)
    conn.set_option(_ldap.OPT_X_TLS_REQUIRE_CERT, _ldap.OPT_X_TLS_NEVER)
    try:
        conn.simple_bind_s(bind_dn, bind_password)
    except _ldap.INVALID_CREDENTIALS:
        raise CommandError('LDAP-Bind fehlgeschlagen – Zugangsdaten prüfen.')
    except _ldap.SERVER_DOWN as e:
        raise CommandError(f'LDAP-Server nicht erreichbar: {e}')

    result = {}
    # Batch-Abfrage: OR-Filter für alle Benutzernamen
    chunks = [usernames[i:i+50] for i in range(0, len(usernames), 50)]
    for chunk in chunks:
        escaped = [_ldap.filter.escape_filter_chars(u) for u in chunk]
        if len(escaped) == 1:
            ldap_filter = f'(sAMAccountName={escaped[0]})'
        else:
            parts = ''.join(f'(sAMAccountName={u})' for u in escaped)
            ldap_filter = f'(|{parts})'

        try:
            entries = conn.search_s(
                search_base,
                _ldap.SCOPE_SUBTREE,
                ldap_filter,
                ['sAMAccountName', 'mail', 'displayName'],
            )
        except _ldap.LDAPError as e:
            raise CommandError(f'LDAP-Suche fehlgeschlagen: {e}')

        for _dn, attrs in entries:
            if not isinstance(attrs, dict):
                continue
            sam = attrs.get('sAMAccountName', [b''])[0]
            if isinstance(sam, bytes):
                sam = sam.decode('utf-8', errors='replace')
            mail = attrs.get('mail', [b''])[0]
            if isinstance(mail, bytes):
                mail = mail.decode('utf-8', errors='replace')
            display = attrs.get('displayName', [b''])[0]
            if isinstance(display, bytes):
                display = display.decode('utf-8', errors='replace')
            if sam:
                result[sam.lower()] = {'email': mail, 'display_name': display}

    conn.unbind_s()
    return result


# ── Command ───────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = (
        'Liest VDI-Benutzer aus Horizon, sucht E-Mail im AD und '
        'speichert sie in VDIAssignment.email.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Nur anzeigen, nichts speichern',
        )
        parser.add_argument(
            '--filter-name',
            default='',
            metavar='REGEX',
            help='Nur VMs deren Name diesem Regex entspricht verarbeiten',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Bestehende E-Mail-Adressen überschreiben',
        )
        parser.add_argument(
            '--update-assigned-to',
            action='store_true',
            help='assigned_to mit AD-Anzeigenamen befüllen wenn noch leer',
        )
        parser.add_argument(
            '--no-horizon',
            action='store_true',
            help=(
                'Horizon überspringen – stattdessen assigned_to-Feld als '
                'Benutzername für AD-Lookup verwenden'
            ),
        )
        parser.add_argument(
            '--debug-horizon',
            action='store_true',
            help='Gibt die rohen Felder der ersten Maschine und Pool-Assignments aus',
        )

    def handle(self, *args, **options):
        dry_run      = options['dry_run']
        filter_name  = options['filter_name']
        overwrite    = options['overwrite']
        update_name  = options['update_assigned_to']
        no_horizon   = options['no_horizon']
        debug        = options['debug_horizon']

        if dry_run:
            self.stdout.write(self.style.WARNING('=== DRY RUN – nichts wird gespeichert ===\n'))

        plugin_cfg = settings.PLUGINS_CONFIG.get('netbox_vdi_billing', {})
        instances  = plugin_cfg.get('horizon_instances', [])

        # ── Benutzernamen sammeln ─────────────────────────────────────────────
        # vm_name (lower) → username (lower)
        vm_to_user: dict[str, str] = {}

        if no_horizon or not instances:
            if not no_horizon and not instances:
                self.stdout.write(self.style.WARNING(
                    'Keine Horizon-Instanzen konfiguriert – '
                    'verwende assigned_to-Feld als Benutzernamen.\n'
                ))
            # Fallback: assigned_to-Feld als Benutzername interpretieren
            qs = VDIAssignment.objects.select_related('virtual_machine').exclude(assigned_to='')
            if filter_name:
                qs = qs.filter(virtual_machine__name__iregex=filter_name)
            for a in qs:
                vm_to_user[a.virtual_machine.name.lower()] = a.assigned_to.strip().lower()
            self.stdout.write(
                f'{len(vm_to_user)} Zuordnungen mit assigned_to-Feld gefunden.\n'
            )
        else:
            # Aus Horizon: Maschine → zugewiesener Benutzer
            for idx, inst in enumerate(instances, 1):
                host     = inst.get('host', '')
                domain   = inst.get('domain', '')
                username = inst.get('username', '')
                password = inst.get('password', '')

                if not all([host, domain, username, password]):
                    self.stderr.write(f'  ✗ Instanz {idx} ({host}): Zugangsdaten unvollständig')
                    continue

                self.stdout.write(f'Verbinde mit Horizon {host} ...')
                try:
                    client = HorizonClient(host, domain, username, password)
                    client.login()
                    self.stdout.write(self.style.SUCCESS('  ✓ Login erfolgreich'))

                    machines = client.get_machines()
                    self.stdout.write(f'  {len(machines)} Maschinen erhalten')

                    # Debug: rohe Felder ausgeben
                    if debug and machines:
                        m0 = machines[0]
                        self.stdout.write(f'\n  DEBUG Maschinenfelder: {sorted(m0.keys())}')
                        self.stdout.write(f'  DEBUG Beispiel: {json.dumps(m0, indent=2)[:800]}\n')

                    # user_names ist direkt auf dem Machine-Objekt (dedicated pools)
                    # session_user_name nur bei aktiver Session
                    found_here = 0
                    for m in machines:
                        name = m.get('name', '')
                        if not name:
                            continue
                        if filter_name and not re.match(filter_name, name, re.IGNORECASE):
                            continue

                        # user_names: Liste der zugewiesenen Benutzer (DOMAIN\username)
                        user_names_list = m.get('user_names') or []
                        session_user   = m.get('session_user_name') or ''
                        user_raw = ''

                        if user_names_list:
                            user_raw = user_names_list[0]
                        elif session_user:
                            user_raw = session_user

                        if user_raw:
                            if '\\' in user_raw:
                                user_raw = user_raw.split('\\')[-1]
                            elif '@' in user_raw:
                                user_raw = user_raw.split('@')[0]
                            vm_to_user[name.lower()] = user_raw.lower()
                            found_here += 1

                    self.stdout.write(f'  {found_here} VMs mit Benutzerzuordnung gefunden')

                except CommandError as e:
                    self.stderr.write(f'  ✗ {host}: {e}')
                except Exception as e:
                    self.stderr.write(f'  ✗ {host}: Unerwarteter Fehler: {e}')

            self.stdout.write(
                f'\n{len(vm_to_user)} VMs mit zugewiesenem Benutzer aus Horizon.\n'
            )

        if not vm_to_user:
            self.stdout.write(self.style.WARNING(
                'Keine Benutzerzuordnungen gefunden. '
                'Entweder --no-horizon mit ausgefülltem assigned_to nutzen '
                'oder Horizon-Config prüfen.'
            ))
            return

        # ── AD-Lookup ─────────────────────────────────────────────────────────
        unique_users = list(set(vm_to_user.values()))
        self.stdout.write(f'Suche {len(unique_users)} Benutzer im Active Directory ...')

        try:
            ad_data = _ldap_lookup(unique_users)
        except CommandError as e:
            raise CommandError(str(e))

        found = sum(1 for u in unique_users if u in ad_data and ad_data[u]['email'])
        self.stdout.write(self.style.SUCCESS(
            f'  ✓ {found}/{len(unique_users)} Benutzer mit E-Mail gefunden.\n'
        ))

        # ── VDIAssignments aktualisieren ──────────────────────────────────────
        updated = skipped = missing_vm = missing_ad = no_assignment = 0

        for vm_name_lower, username in sorted(vm_to_user.items()):
            ad_info = ad_data.get(username, {})
            email   = ad_info.get('email', '')
            display = ad_info.get('display_name', '')

            if not email:
                self.stdout.write(f'  ? Kein E-Mail für Benutzer "{username}" (VM: {vm_name_lower})')
                missing_ad += 1
                continue

            # VM in NetBox finden
            try:
                vm = VirtualMachine.objects.get(name__iexact=vm_name_lower)
            except VirtualMachine.DoesNotExist:
                missing_vm += 1
                continue
            except VirtualMachine.MultipleObjectsReturned:
                self.stderr.write(f'  ✗ Mehrere VMs mit Name "{vm_name_lower}" gefunden – übersprungen')
                continue

            # VDIAssignment finden
            try:
                assignment = VDIAssignment.objects.get(virtual_machine=vm)
            except VDIAssignment.DoesNotExist:
                no_assignment += 1
                continue

            # E-Mail setzen
            if assignment.email and not overwrite:
                skipped += 1
                continue

            changes = []
            if assignment.email != email:
                changes.append(f'email={email}')
            if update_name and not assignment.assigned_to and display:
                changes.append(f'assigned_to={display}')

            if not changes:
                skipped += 1
                continue

            self.stdout.write(
                f'  {"[DRY]" if dry_run else "✓"} {vm.name:<40} '
                f'Benutzer={username:<20} {", ".join(changes)}'
            )

            if not dry_run:
                assignment.email = email
                if update_name and not assignment.assigned_to and display:
                    assignment.assigned_to = display
                assignment.save()

            updated += 1

        # ── Zusammenfassung ───────────────────────────────────────────────────
        self.stdout.write('')
        prefix = '[DRY RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Fertig: {updated} E-Mails gesetzt, '
            f'{skipped} übersprungen, '
            f'{missing_ad} Benutzer nicht in AD, '
            f'{missing_vm} VMs nicht in NetBox, '
            f'{no_assignment} ohne Zuordnung'
        ))
