from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_vdi_billing', '0002_costcenter'),
    ]

    operations = [
        migrations.AddField(
            model_name='vdiassignment',
            name='email',
            field=models.EmailField(
                blank=True,
                verbose_name='E-Mail',
                help_text='E-Mail-Adresse des Benutzers (wird aus AD synchronisiert).',
            ),
        ),
    ]
