import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('virtualization', '0001_squashed_0022'),
    ]

    operations = [
        migrations.CreateModel(
            name='VDIBillingProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict)),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Profilname')),
                ('base_price', models.DecimalField(decimal_places=2, default='0.00', max_digits=10, verbose_name='Grundpreis (€/Monat)')),
                ('vcpu_price', models.DecimalField(decimal_places=2, default='0.00', max_digits=8, verbose_name='Preis pro vCPU (€/Monat)')),
                ('ram_price_per_gb', models.DecimalField(decimal_places=2, default='0.00', max_digits=8, verbose_name='Preis pro GB RAM (€/Monat)')),
                ('gpu_surcharge', models.DecimalField(decimal_places=2, default='0.00', max_digits=8, verbose_name='GPU-Aufschlag (€/Monat)')),
                ('description', models.TextField(blank=True, verbose_name='Beschreibung')),
            ],
            options={
                'verbose_name': 'VDI-Preisprofil',
                'verbose_name_plural': 'VDI-Preisprofile',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='VDIAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict)),
                ('cost_center', models.CharField(blank=True, max_length=100, verbose_name='Kostenstelle')),
                ('department', models.CharField(blank=True, max_length=200, verbose_name='Abteilung')),
                ('assigned_to', models.CharField(blank=True, max_length=200, verbose_name='Zugewiesen an')),
                ('cost_override', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Festpreis (€/Monat)')),
                ('notes', models.TextField(blank=True, verbose_name='Notizen')),
                ('profile', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='assignments',
                    to='netbox_vdi_billing.vdibillingprofile',
                    verbose_name='Preisprofil',
                )),
                ('virtual_machine', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='vdi_billing',
                    to='virtualization.virtualmachine',
                    verbose_name='Virtuelle Maschine',
                )),
            ],
            options={
                'verbose_name': 'VDI-Abrechnungszuordnung',
                'verbose_name_plural': 'VDI-Abrechnungszuordnungen',
                'ordering': ['virtual_machine__name'],
            },
        ),
    ]
