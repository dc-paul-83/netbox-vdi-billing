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

## Horizon API – Automatischer Persistent-Tag

Statt manueller Tags oder Ausnahmelisten fragt das Plugin die **Omnissa Horizon REST API** direkt ab und setzt automatisch den Tag `VDI-Persistent` auf alle VMs die in einem **DEDICATED Pool** (= persistent) sind. Concurrent, Instant-Clone und Template-VMs bekommen den Tag nie.

### Einrichtung

**1. Zugangsdaten in `configuration.py` eintragen:**

```python
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
        'persistent_tag': 'VDI-Persistent',   # Standard, kann angepasst werden
    }
}
```

**2. Dry-Run testen:**
```bash
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py sync_horizon_tags --dry-run
```

**3. Echter Lauf:**
```bash
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py sync_horizon_tags
```

**4. Cron – täglich vor dem Billing-Lauf:**
```
# 01:30 Horizon Tags sync, 02:00 Billing
30 1 * * * /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py sync_horizon_tags >> /var/log/netbox/vdi_billing.log 2>&1
0  2 * * * /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py auto_assign_vdi --filter-tag VDI-Persistent --cost-center-field tenant --cleanup >> /var/log/netbox/vdi_billing.log 2>&1
```

**Was das Skript macht:**
- ✅ VM in persistentem Horizon-Pool → Tag `VDI-Persistent` wird gesetzt
- ✅ VM wechselt zu Floating/Concurrent → Tag wird entfernt
- ✅ VM wird in Horizon gelöscht → NetBox-VM verliert Tag (Assignment beim nächsten Billing-Lauf entfernt via `--cleanup`)
- ✅ Kein externes Paket nötig – nutzt nur Python-Standard-`urllib`
- ✅ Self-signed Zertifikate werden akzeptiert

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

## Massen-Zuweisung für viele VMs

Bei ~200 aus vCenter synchronisierten VMs wäre manuelle Einzelzuordnung sehr aufwändig.  
Es gibt zwei Wege zur automatischen Massen-Zuweisung:

### Voraussetzung: Preisprofile anlegen

Bevor die Automatisierung läuft, müssen die Preisprofile in NetBox vorhanden sein.  
**VDI Abrechnung → Preisprofile → Hinzufügen**

> `--profile` ist optional. Wird es weggelassen, werden die VMs ohne Profil  
> zugeordnet (Kosten = 0 €). Das Profil kann später per `--overwrite` nachgesetzt werden.

**Unterschiedliche Profile je VM-Typ** sind möglich:

| Szenario | Lösung |
|---|---|
| Alle VMs bekommen dasselbe Profil | `--profile "Standard VDI"` |
| GPU-Cluster bekommt ein anderes Profil | `--gpu-cluster-pattern ".*GPU.*" --gpu-profile "GPU-Workstation"` |
| Einzelne VMs brauchen Sonderpreise | Festpreis direkt in der Zuordnung eintragen (überschreibt Profil) |
| Komplett individuelle Zuweisung | CSV-Import: jede VM bekommt ihr eigenes Profil |

---

### Weg A — Browser-UI (NetBox Custom Scripts)

**Kein SSH notwendig.** Die Skripte laufen direkt im Browser unter  
**Customization → Scripts**.

#### Einmalige Einrichtung

Beim ersten Mal muss man NetBox sagen, wo die Skripte liegen:

```bash
sudo nano /opt/netbox/netbox/netbox/configuration.py
```

Zeile hinzufügen:
```python
SCRIPTS_ROOT = '/opt/netbox/venv/lib/python3.x/site-packages/netbox_vdi_billing'
```

> **Tipp:** Den genauen Pfad findet man mit:  
> `sudo find /opt/netbox/venv -name "scripts.py" -path "*/netbox_vdi_billing/*"`

Danach NetBox neu starten:
```bash
sudo systemctl restart netbox netbox-rq
```

#### Verfügbare Skripte

**1. VDI Auto-Zuweisung**  
Liest Kostenstelle und Abteilung automatisch aus NetBox-Feldern.

Optionen im Browser-Formular:

| Feld | Beschreibung |
|---|---|
| Standard-Preisprofil | Profil für alle normalen VMs |
| Kostenstellen-Feld | `Tenant`, `Rolle`, `Cluster` oder `Custom-Field` |
| Abteilungs-Feld | Optional – gleiche Quellen wie Kostenstelle |
| **Nur Rolle** *(empfohlen)* | z.B. `VDI` — bei netbox-sync mit `vm_role_relation = .* = VDI` sofort nutzbar, kein Tag und kein vsphere-automation-sdk nötig |
| Nur Tag | Alternative: Tag-basierter Filter |
| Nur Cluster | Regex auf Cluster-Namen |
| Verwaiste Einträge entfernen | Assignments löschen wenn VM nicht mehr dem Filter entspricht |
| Bestehende überschreiben | Bereits zugewiesene VMs ebenfalls aktualisieren |
| GPU-Cluster-Muster | Regex, z.B. `.*gpu.*` – diese VMs bekommen das GPU-Profil |

> **Dry-Run:** Das Häkchen „Commit" weglassen → Skript zeigt was es tun würde, ohne zu speichern.

---

**2. VDI CSV-Import**  
Kostenstelle und Profil per Tabelle setzen.

CSV-Format (Semikolon-getrennt):
```
vm_name;cost_center;department;profile
vdi-max-001;11554;Vertrieb;Standard VDI
vdi-gpu-001;22100;Konstruktion;GPU-Workstation
vdi-anna-003;11554;Vertrieb;Standard VDI
```

Den CSV-Inhalt einfach in das Textfeld im Browser einfügen, `Commit` anhaken → fertig.

---

### Weg B — CLI (Management Command)

Wer SSH-Zugang hat, kann das Management-Command direkt ausführen.  
Alle Befehle werden von **`/opt/netbox`** aus gestartet:

```bash
# Schritt 1: Dry-Run — erst schauen, was gefunden wird (kein Profil nötig)
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py auto_assign_vdi \
  --filter-role VDI \
  --cost-center-field tenant \
  --dry-run

# Schritt 2: Lauf mit Profil
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py auto_assign_vdi \
  --filter-role VDI \
  --profile "Standard VDI" \
  --cost-center-field tenant

# Mit GPU-Cluster (anderes Profil für GPU-VMs)
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py auto_assign_vdi \
  --filter-role VDI \
  --profile "Standard VDI" \
  --cost-center-field tenant \
  --gpu-cluster-pattern ".*GPU.*" \
  --gpu-profile "GPU-Workstation"

# Profil nachträglich auf alle VMs setzen (--overwrite)
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py auto_assign_vdi \
  --filter-role VDI \
  --profile "Standard VDI" \
  --cost-center-field tenant \
  --overwrite

# CSV-Datei importieren (individuelle Profile pro VM)
sudo /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py auto_assign_vdi \
  --csv /tmp/vdi_zuordnung.csv
```

#### Alle Optionen

| Option | Beschreibung | Standard |
|---|---|---|
| `--profile NAME` | Standard-Preisprofil — muss in NetBox vorhanden sein | – |
| `--filter-role ROLLE` | Nur VMs mit dieser Rolle, z.B. `VDI` | – |
| `--filter-tag TAG` | Nur VMs mit diesem Tag | – |
| `--filter-cluster REGEX` | Nur VMs in Clustern die diesem Regex entsprechen | – |
| `--cleanup` | Assignments entfernen wenn VM nicht mehr dem Filter entspricht | aus |
| `--cost-center-field` | `tenant`, `role`, `cluster`, `custom:feldname` | `tenant` |
| `--department-field` | Gleiche Syntax, für Abteilung | – |
| `--gpu-cluster-pattern` | Regex auf Cluster-Name für GPU-VMs | – |
| `--gpu-profile NAME` | Abweichendes Profil für GPU-VMs | – |
| `--overwrite` | Bestehende Zuordnungen aktualisieren | aus |
| `--dry-run` | Nur anzeigen, nichts speichern | aus |
| `--csv FILE` | CSV-Datei importieren statt Auto-Mapping | – |

---

### Empfohlene Vorgehensweise (Ersteinrichtung)

1. **Preisprofile anlegen** unter *VDI Abrechnung → Preisprofile*
2. **Dry-Run** ausführen → Ausgabe prüfen
3. **Lauf mit Commit** → alle VMs werden zugeordnet
4. **Kostenstellen-Übersicht** kontrollieren

---

### Automatischer Betrieb — Cron-Job (empfohlen)

Da VMs aus vCenter synchronisiert werden und sich laufend ändern, empfiehlt sich
ein täglicher Cron-Job. Er erstellt neue Einträge **und** entfernt automatisch
Einträge für VMs, die den VDI-Tag verloren haben.

```bash
sudo crontab -e
```

Eintrag (täglich um 02:00 Uhr):
```
0 2 * * * /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py \
    auto_assign_vdi \
    --profile "Standard VDI" \
    --cost-center-field tenant \
    --filter-role VDI \
    --cleanup \
    >> /var/log/netbox/vdi_billing.log 2>&1
```

> **Warum `--filter-role VDI`?**  
> Bei netbox-sync mit `vm_role_relation = .* = VDI` bekommen alle VMs aus dem  
> Horizon-vCenter automatisch die Rolle „VDI" in NetBox. Kein Tag-Sync,  
> kein vsphere-automation-sdk nötig.

Log-Verzeichnis anlegen (einmalig):
```bash
sudo mkdir -p /var/log/netbox
sudo chown root:root /var/log/netbox
```

**Was der Cron-Job macht:**
- ✅ Neue VMs (mit Tag `VDI`) → Assignment wird erstellt
- ✅ Bereits zugeordnete VMs → werden übersprungen (kein ungewolltes Überschreiben)
- ✅ VMs deren Tag entfernt wurde → Assignment wird gelöscht
- ✅ Gelöschte VMs → Assignment wird automatisch per Datenbank-Cascade entfernt

**Kostenstelle und Profil ändern sich nicht automatisch** — `--overwrite` ist
bewusst nicht standardmäßig aktiv, damit manuelle Korrekturen erhalten bleiben.

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
