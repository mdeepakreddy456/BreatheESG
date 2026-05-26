import os
import django
from decimal import Decimal

# Configure Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'breathe_esg.settings')
django.setup()

from django.contrib.auth.models import User
from esg_ingest.models import Organization, Facility

def seed_database():
    print("Starting database seeding...")
    
    # 1. Create Default Organization
    org, created = Organization.objects.get_or_create(
        name="Default Enterprise Client"
    )
    if created:
        print(f"Created Organization: '{org.name}'")
    else:
        print(f"Organization '{org.name}' already exists.")

    # 2. Create Default Facilities (Hamburg, Texas, Bangalore)
    facilities_data = [
        {
            "plant_code": "DE01",
            "name": "Hamburg Manufacturing Plant",
            "city": "Hamburg",
            "country": "Germany",
            "region": "DE",
            "grid_emission_factor": Decimal("0.40100")
        },
        {
            "plant_code": "US02",
            "name": "Texas Refining Center",
            "city": "Houston",
            "country": "USA",
            "region": "US-TX",
            "grid_emission_factor": Decimal("0.38500")
        },
        {
            "plant_code": "IN03",
            "name": "Bangalore Operations Hub",
            "city": "Bangalore",
            "country": "India",
            "region": "IN-KA",
            "grid_emission_factor": Decimal("0.79000")
        }
    ]

    for fac_info in facilities_data:
        fac, created = Facility.objects.get_or_create(
            plant_code=fac_info["plant_code"],
            defaults={
                "organization": org,
                "name": fac_info["name"],
                "city": fac_info["city"],
                "country": fac_info["country"],
                "region": fac_info["region"],
                "grid_emission_factor": fac_info["grid_emission_factor"]
            }
        )
        if created:
            print(f"Seeded Facility: {fac.name} ({fac.plant_code})")
        else:
            print(f"Facility {fac.name} already exists.")

    # 3. Create Superuser for analyst sign-off
    if not User.objects.filter(username='admin').exists():
        User.objects.create_superuser('admin', 'admin@breatheesg.com', 'admin123')
        print("Seeded Superuser: username='admin', password='admin123'")
    else:
        print("Superuser 'admin' already exists.")

    print("Database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
