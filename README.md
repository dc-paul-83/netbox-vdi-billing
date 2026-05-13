# netbox-vdi-billing

NetBox 4.5.x Plugin für kostenstellen-basierte VDI-Abrechnung.  
Berechnet automatisch monatliche Kosten aus VM-Ressourcen (vCPU, RAM, GPU) und gruppiert sie nach Kostenstellen für den internen Chargeback.

---

## So funktioniert das Plugin

Das Plugin besteht aus zwei Bausteinen, die zusammenspielen:

```
Preisprofil  +  VM-Zuordnung  =  Kostenstellen-Abrechnung
──────────────────────────────────────────────────────────
"Standard VDI"    VM "VDESK-042"    Kostenstelle 11554
€2/vCPU        →  4 vCPU            Abteilung: IT
€0,50/GB RAM      8 GB RAM          Zugewiesen an: M. Müller
                  ─────────         Berechnet: 12,00 €/Monat
                  4×2 + 8×0,5 = 12
```

### Schritt 1 — Preisprofile anlegen

**VDI Abrechnung → Preisprofile → Hinzufügen**

Ein Profil definiert die Preisregeln für eine VDI-Klasse:

| Feld | Beschreibung | Beispiel |
|---|---|---|
| **Name** | Bezeichnung des Profils | `Standard VDI` |
| **Grundpreis** | Fixer Betrag pro VM/Monat, unabhängig von Ressourcen | `10,00 €` |
| **Preis pro vCPU** | Wird mit der vCPU-Anzahl der VM multipliziert | `2,00 €` |
| **Preis pro GB RAM** | Wird mit dem RAM der VM (in GB) multipliziert | `0,50 €` |
| **GPU-Aufschlag** | Wird addiert, wenn das Custom Field `gpu` der VM gesetzt ist | `80,00 €` |

**Beispiel-Kalkulation** für eine VM mit 4 vCPU, 16 GB RAM, ohne GPU:
```
Grundpreis:     10,00 €
4 × 2,00 €:      8,00 €
16 × 0,50 €:     8,00 €
──────────────────────
Gesamt:         26,00 €/Monat
```

**Typische Profile:**

| Profil | Grundpreis | €/vCPU | €/GB RAM | GPU |
|---|---|---|---|---|
| Standard VDI | 5 € | 2 € | 0,50 € | 0 € |
| Persistent VDI | 10 € | 3 € | 0,75 € | 0 € |
| GPU-Workstation | 15 € | 4 € | 1,00 € | 80 € |

> **Kein Profil nötig?** Wenn eine VM einen fixen Vertragspreis hat, kann man auch direkt einen **Festpreis** eintragen (überschreibt die Profilberechnung).

---

### Schritt 2 — VMs zuordnen

**VDI Abrechnung → Alle Zuordnungen → Hinzufügen**

Für jede abzurechnende VM eine Zuordnung anlegen:

| Feld | Beschreibung | Pflicht |
|---|---|---|
| **Virtuelle Maschine** | Die NetBox-VM aus der Dropdown-Liste | ✅ |
| **Preisprofil** | Welches Profil zur Berechnung genutzt werden soll | – |
| **Kostenstelle** | Nummer der Kostenstelle (z.B. `11554`) | – |
| **Abteilung** | Name der Abteilung (z.B. `IT-Infrastruktur`) | – |
| **Zugewiesen an** | Benutzername oder Team | – |
| **Festpreis** | Fixer €/Monat-Wert — überschreibt Profilberechnung | – |
| **Notizen** | Interne Anmerkungen | – |

> ⚠️ **Kostenstelle ohne Profil und ohne Festpreis** → Kosten = 0 €.  
> Mindestens eines von beidem sollte gesetzt sein.

**Preisquelle-Logik (Priorität):**
```
1. Festpreis gesetzt?  → Festpreis wird verwendet
2. Profil gesetzt?     → Grundpreis + vCPU × Preis + RAM × Preis (+ GPU)
3. Nichts gesetzt?     → 0,00 €
```

---

### Schritt 3 — Übersicht & Chargeback

**VDI Abrechnung → Kostenstellen-Übersicht**

Die Übersicht zeigt alle Kostenstellen mit:
- Anzahl VMs
- Monatliche Gesamtkosten
- Jährliche Gesamtkosten
- Aufschlüsselung je VM (vCPU, RAM, Preisquelle)

**PDF-Report** pro Kostenstelle: Auf den **PDF-Button** klicken → druckoptimierte Ansicht öffnet sich → Browser-Druckdialog → *Als PDF speichern*.

---

### VM-Detailseite

Auf jeder NetBox-VM-Seite erscheint rechts ein **„VDI Abrechnung"-Panel** mit:
- Kostenstelle & Abteilung
- Zugewiesen an
- Preisprofil & Preisquelle
- Berechnete Kosten/Monat und /Jahr

---

## GPU-Erkennung

Der GPU-Aufschlag wird automatisch addiert wenn das Custom Field **`gpu`** der VM einen Wert hat.

Custom Field in NetBox anlegen:  
*Customization → Custom Fields → Add*
- **Object type:** `virtualization | virtual machine`
- **Name:** `gpu`
- **Type:** Text oder Boolean

---

## Installation (NetBox 4.5.x)

```bash
# 1. Plugin installieren
sudo /opt/netbox/venv/bin/pip install \
  https://github.com/kottpaul/netbox-vdi-billing/archive/refs/heads/main.tar.gz

# 2. In configuration.py eintragen
#    PLUGINS = ['netbox_vdi_billing']
sudo nano /opt/netbox/netbox/netbox/configuration.py

# 3. Datenbank-Migration
cd /opt/netbox
sudo -u root /opt/netbox/venv/bin/python netbox/manage.py migrate netbox_vdi_billing

# 4. Static Files
sudo -u root /opt/netbox/venv/bin/python netbox/manage.py collectstatic --no-input

# 5. Neustart
sudo systemctl restart netbox netbox-rq
```

### Update

```bash
sudo /opt/netbox/venv/bin/pip install --upgrade --force-reinstall \
  https://github.com/kottpaul/netbox-vdi-billing/archive/refs/heads/main.tar.gz

cd /opt/netbox
sudo -u root /opt/netbox/venv/bin/python netbox/manage.py migrate netbox_vdi_billing
sudo systemctl restart netbox netbox-rq
```

---

## Menüstruktur

```
VDI Abrechnung (Sidebar)
├── Auswertung
│   ├── Kostenstellen-Übersicht   ← Hauptansicht mit Chargeback-Tabelle
│   └── Alle Zuordnungen          ← Liste aller VM-Zuordnungen
└── Konfiguration
    └── Preisprofile              ← Preisregeln verwalten
```
