# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_vdi_billing', '0003_vdiassignment_email'),
    ]

    operations = [
        migrations.CreateModel(
            name='PluginSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('billing_enabled', models.BooleanField(default=True, help_text='Zeigt Kosten/Kalkulationen in Zuordnungen, Übersicht und PDFs.', verbose_name='Kostenberechnung aktivieren')),
                ('show_gpu_badge', models.BooleanField(default=True, help_text='Zeigt GPU-Status in der Zuordnungsliste.', verbose_name='GPU-Badge anzeigen')),
                ('show_email', models.BooleanField(default=True, help_text='Zeigt E-Mail-Spalte in Zuordnungen (falls synchronisiert).', verbose_name='E-Mail-Adressen anzeigen')),
                ('last_modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Plugin-Einstellung',
                'verbose_name_plural': 'Plugin-Einstellungen',
            },
        ),
    ]
