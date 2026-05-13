import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_vdi_billing', '0001_initial'),
    ]

    operations = [
        # 1. Neue Kostenstellen-Tabelle anlegen
        migrations.CreateModel(
            name='CostCenter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
                ('last_updated', models.DateTimeField(auto_now=True, null=True)),
                ('custom_field_data', models.JSONField(blank=True, default=dict)),
                ('number', models.CharField(
                    max_length=50, unique=True,
                    verbose_name='KST-Nummer',
                    help_text='Eindeutige Kostenstellen-Nummer, z.B. 11554',
                )),
                ('name', models.CharField(blank=True, max_length=200, verbose_name='Bezeichnung')),
                ('department', models.CharField(blank=True, max_length=200, verbose_name='Abteilung')),
                ('description', models.TextField(blank=True, verbose_name='Beschreibung')),
            ],
            options={
                'verbose_name': 'Kostenstelle',
                'verbose_name_plural': 'Kostenstellen',
                'ordering': ['number'],
            },
        ),

        # 2. Neue FK-Spalte cost_center_new hinzufügen (nullable)
        migrations.AddField(
            model_name='vdiassignment',
            name='cost_center_new',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assignments',
                to='netbox_vdi_billing.costcenter',
                verbose_name='Kostenstelle',
            ),
        ),

        # 3. Alte cost_center CharField entfernen
        migrations.RemoveField(
            model_name='vdiassignment',
            name='cost_center',
        ),

        # 4. cost_center_new → cost_center umbenennen
        migrations.RenameField(
            model_name='vdiassignment',
            old_name='cost_center_new',
            new_name='cost_center',
        ),

        # 5. department Feld entfernen (jetzt auf CostCenter)
        migrations.RemoveField(
            model_name='vdiassignment',
            name='department',
        ),
    ]
