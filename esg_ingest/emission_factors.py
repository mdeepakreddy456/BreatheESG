# Standard ESG Emission Factors and Coordinates
# Values compiled from DEFRA (UK) and EPA (US) standard carbon metrics for 2024/2025.

# Scope 1: Stationary & Mobile Combustion (kg CO2e per standard unit)
FUEL_EMISSION_FACTORS = {
    'DIESEL': {
        'factor': 2.68,          # kg CO2e per Liter
        'unit': 'L',
        'scope': 'SCOPE_1',
        'category': 'Stationary Combustion',
        'display_name': 'Diesel Fuel'
    },
    'HEIZOEL': {
        'factor': 2.96,          # kg CO2e per Liter
        'unit': 'L',
        'scope': 'SCOPE_1',
        'category': 'Stationary Combustion',
        'display_name': 'Heavy Heating Oil'
    },
    'ERDGAS': {
        'factor': 2.02,          # kg CO2e per Cubic Meter (M3)
        'unit': 'M3',
        'scope': 'SCOPE_1',
        'category': 'Stationary Combustion',
        'display_name': 'Natural Gas'
    },
    'PETROL': {
        'factor': 2.31,          # kg CO2e per Liter
        'unit': 'L',
        'scope': 'SCOPE_1',
        'category': 'Mobile Combustion',
        'display_name': 'Petrol / Gasoline'
    }
}

# Scope 3: Procured Goods and Materials (kg CO2e per kg)
PROCUREMENT_EMISSION_FACTORS = {
    'STAHL': {
        'factor': 1.85,          # kg CO2e per kg of Steel
        'unit': 'KG',
        'scope': 'SCOPE_3',
        'category': 'Procured Goods - Steel',
        'display_name': 'Steel Procurement'
    },
    'BETON': {
        'factor': 0.12,          # kg CO2e per kg of Concrete
        'unit': 'KG',
        'scope': 'SCOPE_3',
        'category': 'Procured Goods - Concrete',
        'display_name': 'Concrete Procurement'
    }
}

# Scope 3: Flight Category (kg CO2e per passenger-kilometer)
# Short-haul: < 500 km | Medium-haul: 500-3700 km | Long-haul: > 3700 km
FLIGHT_BASE_FACTORS = {
    'SHORT': 0.2454,
    'MEDIUM': 0.1513,
    'LONG': 0.1478
}

# Multipliers for Travel Class of Service
FLIGHT_CLASS_MULTIPLIERS = {
    'ECONOMY': 1.0,
    'PREMIUM_ECONOMY': 1.6,
    'BUSINESS': 2.9,
    'FIRST': 4.0
}

# Scope 3: Lodging (kg CO2e per room night) by Country Code
HOTEL_EMISSION_FACTORS = {
    'US': 15.4,
    'GB': 20.3,
    'DE': 28.2,
    'IN': 53.6,
    'FR': 6.8,
    'JP': 40.1,
    'DEFAULT': 25.0
}

# Scope 3: Ground Transportation (kg CO2e per km)
CAR_EMISSION_FACTORS = {
    'ECONOMY': 0.17,    # Standard Compact Sedan (Petrol)
    'SUV': 0.28,        # Large Utility Vehicle (Petrol)
    'HYBRID': 0.10,     # Hybrid electric car
    'ELECTRIC': 0.05    # Fully electric vehicle
}

# Airport Coordinates (Latitude, Longitude) for Haversine Distance calculations
AIRPORT_COORDINATES = {
    'JFK': (40.6413, -73.7781),    # New York, USA
    'LHR': (51.4700, -0.4543),     # London, UK
    'FRA': (50.0379, 8.5622),      # Frankfurt, Germany
    'BLR': (13.1986, 77.7066),     # Bangalore, India
    'SFO': (37.6213, -122.3790),   # San Francisco, USA
    'CDG': (49.0097, 2.5479),      # Paris, France
    'DXB': (25.2532, 55.3657),     # Dubai, UAE
    'HND': (35.5494, 139.7798),    # Tokyo Haneda, Japan
    'SIN': (1.3644, 103.9915),     # Singapore Changi
    'BOM': (19.0896, 72.8656),     # Mumbai, India
    'ORD': (41.9742, -87.9073),    # Chicago, USA
    'LAX': (33.9416, -118.4085),   # Los Angeles, USA
    'AMS': (52.3105, 4.7683),      # Amsterdam, Netherlands
}
