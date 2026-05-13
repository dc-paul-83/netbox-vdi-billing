# netbox-vdi-billing

NetBox 4.x Plugin für kostenstellen-basierte VDI-Abrechnung mit automatischer Preisberechnung aus VM-Ressourcen.

## Features

- **Kostenstellen-Übersicht** – gruppierte Tabelle mit Monat-/Jahreskosten je Kostenstelle
- **Preisprofile** – flexible Kalkulation: Grundpreis + €/vCPU + €/GB RAM + GPU-Aufschlag
- **Festpreis-Override** – manuelle Überschreibung pro VM möglich
- **PDF/Druckansicht** – sauber formatierter Chargeback-Report pro Kostenstelle
- **VM-Detailpanel** – Abrechnungsinfos direkt auf der NetBox VM-Seite

## Installation

### 1. Plugin ins NetBox-Verzeichnis kopieren (oder per pip installieren)

```bash
# Im NetBox-Verzeichnis
cd /opt/netbox
source venv/bin/activate

# Entwicklungsinstallation (aus dem Plugin-Verzeichnis)
pip install -e /pfad/zu/netbox-vdi-billing

# Oder direkt aus dem Repo-Unterverzeichnis
pip install -e /opt/free-inventory/netbox-vdi-billing
```

### 2. `configuration.py` anpassen

```python
PLUGINS = [
    'netbox_vdi_billing',
]

# Optional: Plugin-Einstellungen
PLUGINS_CONFIG = {
    'netbox_vdi_billing': {},
}
```

### 3. Migrationen ausführen

```bash
cd /opt/netbox
python manage.py migrate netbox_vdi_billing
python manage.py collectstatic --no-input
```

### 4. NetBox neu starten

```bash
sudo systemctl restart netbox netbox-rq
```

## Optional: PDF-Export mit reportlab

```bash
pip install reportlab
```

Ohne reportlab öffnet der PDF-Button eine druckoptimierte HTML-Seite (Browser → Drucken → Als PDF speichern).

## Einrichtung

1. **Preisprofile anlegen** unter *VDI Abrechnung → Preisprofile → Hinzufügen*  
   Beispiel: `Standard VDI` mit `base_price=10, vcpu_price=2, ram_price_per_gb=0.5`

2. **VMs zuordnen** unter *VDI Abrechnung → Alle Zuordnungen → Hinzufügen*  
   VM auswählen, Kostenstelle/Abteilung/Profil eintragen

3. **Übersicht ansehen** unter *VDI Abrechnung → Kostenstellen-Übersicht*

## Datenmodell

```
VDIBillingProfile         VDIAssignment
─────────────────         ────────────────────────────
name                      virtual_machine (→ VM)
base_price                profile (→ VDIBillingProfile)
vcpu_price                cost_center
ram_price_per_gb          department
gpu_surcharge             assigned_to
description               cost_override  (nullable)
                          notes

cost_monthly = cost_override ?? profile.calculate_cost(vm) ?? 0
```

## GPU-Erkennung

Der GPU-Aufschlag wird addiert wenn das Custom Field `gpu` der VM einen truthy-Wert hat.  
Custom Field in NetBox anlegen: *Customization → Custom Fields → Add*  
- Object type: `virtualization | virtual machine`
- Name: `gpu`
- Type: Boolean oder Text
