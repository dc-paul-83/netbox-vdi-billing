# netbox-vdi-billing

A [NetBox](https://github.com/netbox-community/netbox) plugin for VDI chargeback billing with cost center management, price profiles, and automated synchronization with Omnissa Horizon and Active Directory.

[![NetBox](https://img.shields.io/badge/NetBox-4.5%2B-blue)](https://github.com/netbox-community/netbox)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-dcpaul83-yellow?logo=buy-me-a-coffee)](https://buymeacoffee.com/dcpaul83)

---

## Features

- **Cost Centers** — Manage cost centers and assign multiple VMs at once via bulk assignment UI
- **Price Profiles** — Define monthly costs per vCPU, RAM (GB) and GPU surcharge
- **VDI Assignments** — Link VMs to cost centers and profiles; supports fixed-price override
- **Chargeback Overview** — Monthly/yearly cost summary grouped by cost center, exportable as PDF
- **Horizon Sync** — Automatically tag persistent (`VDI-Persistent`) and GPU (`VDI-GPU`) VMs via Omnissa Horizon REST API
- **AD E-Mail Sync** — Read assigned users from Horizon and look up their e-mail in Active Directory (LDAP)
- **VM Panel** — Billing info panel on every Virtual Machine detail page

---

## How it works

```
Price Profile  +  VDI Assignment  =  Cost Center Chargeback
────────────────────────────────────────────────────────────
"Standard VDI"    VM "VDESK-042"    Cost Center 11554
€2/vCPU        →  4 vCPU            Department: IT
€0.50/GB RAM      8 GB RAM          Assigned to: M. Müller
                  ─────────         Cost: 12.00 €/month
                  4×2 + 8×0.5 = 12
```

**Pricing priority:**
1. Fixed price set → use fixed price
2. Profile set → base price + vCPU × price + RAM × price (+ GPU surcharge)
3. Nothing set → 0.00 €

---

## Requirements

- NetBox >= 4.5.0
- Python >= 3.10
- Omnissa Horizon (for automatic tag and e-mail sync)
- Active Directory / LDAP (for e-mail sync)

---

## Installation

```bash
# 1. Install plugin
sudo /opt/netbox/venv/bin/pip install \
  https://github.com/dc-paul-83/netbox-vdi-billing/archive/refs/heads/main.tar.gz

# 2. Add to configuration.py
PLUGINS = ['netbox_vdi_billing']

# 3. Run migrations
python manage.py migrate netbox_vdi_billing

# 4. Collect static files
python manage.py collectstatic --no-input

# 5. Restart
sudo systemctl restart netbox netbox-rq
```

### Update

```bash
sudo /opt/netbox/venv/bin/pip install --upgrade --force-reinstall --no-cache-dir \
  https://github.com/dc-paul-83/netbox-vdi-billing/archive/refs/heads/main.tar.gz

python manage.py migrate netbox_vdi_billing
sudo systemctl restart netbox netbox-rq
```

---

## Configuration

All settings go into `configuration.py` under `PLUGINS_CONFIG`:

```python
PLUGINS_CONFIG = {
    'netbox_vdi_billing': {

        # ── Horizon Instances ─────────────────────────────────────────────────
        # List of Omnissa Horizon Connection Servers
        # Use internal IPs directly — not the UAG (Unified Access Gateway)!
        'horizon_instances': [
            {
                'host':     '10.50.165.1',    # internal Connection Server IP
                'domain':   'YOURDOMAIN',
                'username': 'svc-netbox',
                'password': 'secret',
            },
            # Add more instances for multi-site setups
        ],

        # ── Tags ──────────────────────────────────────────────────────────────
        'persistent_tag':   'VDI-Persistent',        # tag for dedicated desktops
        'gpu_tag':          'VDI-GPU',               # tag for GPU desktops
        'gpu_pool_pattern': r'nvidia|vgpu|gpu|grid', # regex matched against pool name

        # ── LDAP / Active Directory (for e-mail sync) ─────────────────────────
        # Only needed if NetBox is NOT configured with LDAP authentication.
        # The plugin automatically detects LDAP settings in this order:
        #   1. AUTH_LDAP_* from Django settings (ldap_config.py / configuration.py)
        #   2. The settings below (plugin config)
        #   3. /opt/netbox/netbox/netbox/ldap_config.py read directly
        #
        # 'ldap_server':        'ldap://dc.example.com',
        # 'ldap_bind_dn':       'CN=svc-netbox,OU=...,DC=example,DC=com',
        # 'ldap_bind_password': 'secret',
        # 'ldap_search_base':   'DC=example,DC=com',
    }
}
```

---

## Management Commands

### `sync_horizon_tags`

Queries Horizon and sets/removes `VDI-Persistent` and `VDI-GPU` tags on NetBox VMs.

- VMs in **DEDICATED pools** → get tag `VDI-Persistent`
- VMs in **GPU pools** (pool name matches regex) or machines with `num_gpus > 0` → get tag `VDI-GPU`
- VMs removed from those pools → tags are removed automatically

```bash
# Dry-run first
python manage.py sync_horizon_tags --dry-run

# Real run
python manage.py sync_horizon_tags

# Disable GPU detection
python manage.py sync_horizon_tags --no-gpu

# Override tag names
python manage.py sync_horizon_tags --tag "VDI-Persistent" --gpu-tag "VDI-GPU"
```

---

### `auto_assign_vdi`

Creates/updates `VDIAssignment` entries for VMs matching a filter.

```bash
# Assign all VMs with role "VDI" to profile "Standard VDI"
python manage.py auto_assign_vdi \
    --profile "Standard VDI" \
    --cost-center-field tenant \
    --filter-role VDI \
    --cleanup \
    --dry-run

# CSV import (columns: vm_name;cost_center;department;profile)
python manage.py auto_assign_vdi --csv /tmp/assignments.csv
```

**Options:**

| Option | Description |
|---|---|
| `--profile NAME` | Default price profile |
| `--cost-center-field` | `tenant`, `role`, `cluster`, or `custom:fieldname` |
| `--filter-role ROLE` | Only process VMs with this role (partial match) |
| `--filter-tag TAG` | Only process VMs with this tag |
| `--filter-cluster REGEX` | Only process VMs in matching clusters |
| `--filter-name REGEX` | Only process VMs with matching name |
| `--exclude-tag TAG` | Exclude VMs with this tag (repeatable) |
| `--exclude-name REGEX` | Exclude VMs with matching name |
| `--cleanup` | Remove assignments for VMs no longer matching filters |
| `--overwrite` | Overwrite existing assignments |
| `--gpu-cluster-pattern` | Regex on cluster name for GPU VMs |
| `--gpu-profile NAME` | Price profile for GPU VMs |
| `--dry-run` | Show what would be done, save nothing |

---

### `sync_vdi_emails`

Reads the assigned user for each VDI desktop from Horizon, looks up their e-mail address in Active Directory via LDAP, and saves it to `VDIAssignment.email`.

```bash
# Dry-run
python manage.py sync_vdi_emails --dry-run

# Real run
python manage.py sync_vdi_emails

# Also fill assigned_to with AD display name if empty
python manage.py sync_vdi_emails --update-assigned-to

# Overwrite existing e-mail addresses
python manage.py sync_vdi_emails --overwrite

# Skip Horizon, use assigned_to field as username instead
python manage.py sync_vdi_emails --no-horizon

# Only process VMs matching a regex
python manage.py sync_vdi_emails --filter-name "^site-vdi-.*"

# Debug: show raw Horizon API fields
python manage.py sync_vdi_emails --dry-run --debug-horizon
```

**LDAP auto-detection order:**
1. `AUTH_LDAP_SERVER_URI` etc. already in Django settings
2. `ldap_server` / `ldap_bind_dn` etc. in `PLUGINS_CONFIG` (see Configuration above)
3. `/opt/netbox/netbox/netbox/ldap_config.py` read directly as fallback

---

## Recommended Cron Schedule

```
# VDI Billing – daily sync (all times in server local time)
30 1 * * * /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py sync_horizon_tags >> /var/log/netbox/vdi_billing.log 2>&1
00 2 * * * /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py auto_assign_vdi --profile "Standard VDI" --filter-role VDI --cleanup >> /var/log/netbox/vdi_billing.log 2>&1
30 2 * * * /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py sync_vdi_emails --update-assigned-to >> /var/log/netbox/vdi_billing.log 2>&1
```

Create log directory once:
```bash
sudo mkdir -p /var/log/netbox
```

---

## UI Overview

| View | URL |
|---|---|
| Chargeback Overview | `/plugins/vdi-billing/` |
| Cost Centers | `/plugins/vdi-billing/cost-centers/` |
| Bulk Assignment | `/plugins/vdi-billing/bulk-assign/` |
| Price Profiles | `/plugins/vdi-billing/profiles/` |
| All Assignments | `/plugins/vdi-billing/assignments/` |

The plugin also adds a **VDI Billing** panel to every Virtual Machine detail page showing cost center, assigned user, e-mail, price profile and monthly/yearly costs.

---

## Price Profiles

Define pricing rules per VDI class:

| Field | Description | Example |
|---|---|---|
| **Name** | Profile name | `Standard VDI` |
| **Base price** | Fixed amount per VM/month | `10.00 €` |
| **Price per vCPU** | Multiplied by VM's vCPU count | `2.00 €` |
| **Price per GB RAM** | Multiplied by VM's RAM in GB | `0.50 €` |
| **GPU surcharge** | Added when VM has `VDI-GPU` tag or `gpu` custom field | `80.00 €` |

**Example calculation** — 4 vCPU, 16 GB RAM, no GPU:
```
Base price:    10.00 €
4 × 2.00 €:    8.00 €
16 × 0.50 €:   8.00 €
──────────────────────
Total:         26.00 €/month
```

**Typical profiles:**

| Profile | Base | €/vCPU | €/GB RAM | GPU |
|---|---|---|---|---|
| Standard VDI | 5 € | 2 € | 0.50 € | 0 € |
| Persistent VDI | 10 € | 3 € | 0.75 € | 0 € |
| GPU Workstation | 15 € | 4 € | 1.00 € | 80 € |

> A **fixed price override** on an assignment overrides the profile calculation entirely.

---

## License

MIT — free to use, modify and distribute.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-dcpaul83-yellow?logo=buy-me-a-coffee)](https://buymeacoffee.com/dcpaul83)
