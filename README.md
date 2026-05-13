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

## Massen-Zuweisung für viele VMs

Bei ~200 aus vCenter synchronisierten VMs wäre manuelle Einzelzuordnung sehr aufwändig.  
Es gibt zwei Wege zur automatischen Massen-Zuweisung:

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
| GPU-Cluster-Muster | Regex, z.B. `.*gpu.*` – diese VMs bekommen das GPU-Profil |
| GPU-Preisprofil | Anderes Profil für GPU-VMs |
| Nur Cluster / Nur Rolle | Filter: nur bestimmte VMs verarbeiten |
| Bestehende überschreiben | Bereits zugewiesene VMs ebenfalls aktualisieren |

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

Wer SSH-Zugang hat, kann das Management-Command direkt ausführen:

```bash
cd /opt/netbox

# Dry-Run: zeigt was gemacht würde, ohne zu speichern
sudo /opt/netbox/venv/bin/python netbox/manage.py auto_assign_vdi --dry-run

# Alle VMs, Tenant als Kostenstelle, Profil "Standard VDI"
sudo /opt/netbox/venv/bin/python netbox/manage.py auto_assign_vdi \
  --profile "Standard VDI" \
  --cost-center-field tenant

# GPU-Cluster extra
sudo /opt/netbox/venv/bin/python netbox/manage.py auto_assign_vdi \
  --profile "Standard VDI" \
  --cost-center-field tenant \
  --gpu-cluster-pattern ".*GPU.*" \
  --gpu-profile "GPU-Workstation"

# Nur bestimmte Cluster
sudo /opt/netbox/venv/bin/python netbox/manage.py auto_assign_vdi \
  --profile "Standard VDI" \
  --cost-center-field tenant \
  --filter-cluster "VDI-.*"

# CSV-Datei importieren
sudo /opt/netbox/venv/bin/python netbox/manage.py auto_assign_vdi \
  --csv /tmp/vdi_zuordnung.csv
```

#### Alle Optionen

| Option | Beschreibung | Standard |
|---|---|---|
| `--profile NAME` | Standard-Preisprofil | – |
| `--cost-center-field` | `tenant`, `role`, `cluster`, `custom:feldname` | `tenant` |
| `--department-field` | Gleiche Syntax wie oben, für Abteilung | – |
| `--gpu-cluster-pattern` | Regex auf Cluster-Name | – |
| `--gpu-profile NAME` | Profil für GPU-VMs | – |
| `--filter-cluster` | Nur VMs in Clustern die diesem Regex entsprechen | – |
| `--filter-role` | Nur VMs mit dieser Rolle | – |
| `--overwrite` | Bestehende Zuordnungen überschreiben | aus |
| `--dry-run` | Nur anzeigen, nichts speichern | aus |
| `--csv FILE` | CSV-Datei importieren statt Auto-Mapping | – |

---

### Empfohlene Vorgehensweise (Ersteinrichtung)

1. **VDI-Tag anlegen** unter *Customization → Tags → Add* → Name: `VDI`
2. **VMs taggen**: Alle VDI-VMs in NetBox mit dem Tag `VDI` versehen  
   *(Bei vCenter-Sync kann das auch automatisch über die Sync-Konfiguration passieren)*
3. **Preisprofile anlegen** unter *VDI Abrechnung → Preisprofile*
4. **Dry-Run** ausführen (CLI oder Browser ohne „Commit") → Ausgabe prüfen
5. **Lauf mit Commit** → alle getaggten VMs werden zugeordnet
6. **Kostenstellen-Übersicht** kontrollieren

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
    --filter-tag VDI \
    --cleanup-untagged \
    >> /var/log/netbox/vdi_billing.log 2>&1
```

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
