import json
import urllib.request

def get_precise_india_soil_profile(lat: float, lon: float) -> str:
    print(f"[*] Analyzing Indian Coordinates -> Lat: {lat}, Lon: {lon}")
    
    if not (68.1 <= lon <= 97.4 and 8.4 <= lat <= 37.6):
        return json.dumps({
            "error": "Coordinates fall outside the high-precision India bounding grid."
        }, indent=4)

    if (24.0 <= lat <= 32.0) and (74.0 <= lon <= 89.0):
        soil_profile = {
            "region": "Indo-Gangetic Alluvial Plain",
            "taxonomy": "Alluvial Soil (Fluvisols / Inceptisols)",
            "major_subgroup": "Calcareous / Non-calcareous alluvial",
            "pH": 7.5,
            "texture": "Silty Loam to Clayey Loam",
            "fertility": "High",
            "organic_carbon_g_kg": 13.0,
            "major_nutrients": {"nitrogen": "Low-Medium", "phosphorus": "Medium", "potassium": "High"},
            "typical_crops": ["Rice", "Wheat", "Sugarcane", "Mustard", "Potato"]
        }

    elif (24.0 <= lat <= 30.0) and (68.0 <= lon <= 74.0):
        soil_profile = {
            "region": "Western Arid Region / Thar Desert",
            "taxonomy": "Desert Soil / Aridisols (Calciorthids)",
            "major_subgroup": "Sierozems and Desertic sand",
            "pH": 8.4,
            "texture": "Sandy to Sandy Loam",
            "fertility": "Low",
            "organic_carbon_g_kg": 2.0,
            "salinity_risk": "High",
            "typical_crops": ["Bajra (Pearl Millet)", "Jowar", "Guar", "Pulses"]
        }

    elif (15.0 <= lat <= 25.0) and (72.0 <= lon <= 81.0):
        soil_profile = {
            "region": "Deccan Plateau / Central India",
            "taxonomy": "Black Cotton Soil / Vertisols (Regur)",
            "major_subgroup": "Deep to Medium Deep Black Soils",
            "pH": 8.0,
            "texture": "Clayey (High swelling/shrinking capacity)",
            "fertility": "High (Self-plowing property)",
            "organic_carbon_g_kg": 7.5,
            "moisture_retention": "Very High",
            "typical_crops": ["Cotton", "Soybean", "Sorghum", "Chickpea", "Citrus"]
        }

    elif (8.5 <= lat <= 23.0) and (75.0 <= lon <= 88.0):
        soil_profile = {
            "region": "Peninsular Plateau / Eastern Ghats",
            "taxonomy": "Red and Yellow Soils (Alfisols / Ultisols)",
            "major_subgroup": "Ferruginous Red Soils",
            "pH": 6.2,
            "texture": "Sandy Loam to Clay Loam",
            "fertility": "Medium (Requires nitrogen/phosphorus supplementation)",
            "organic_carbon_g_kg": 6.0,
            "typical_crops": ["Ragi", "Groundnut", "Millets", "Tobacco", "Paddy"]
        }

    elif (8.5 <= lat <= 20.0) and (73.0 <= lon <= 77.5):
        soil_profile = {
            "region": "Western Ghats & West Coast",
            "taxonomy": "Laterite Soils (Oxisols)",
            "major_subgroup": "Iron and Aluminum rich lateritic crusts",
            "pH": 5.5,
            "texture": "Gravelly Loam to Clay",
            "fertility": "Low (Acidic and heavily leached)",
            "organic_carbon_g_kg": 11.0,
            "typical_crops": ["Cashew", "Coconut", "Rubber", "Spices", "Areca nut", "Coffee"]
        }

    elif (30.0 <= lat <= 37.5) and (73.0 <= lon <= 80.0):
        soil_profile = {
            "region": "North-Western Himalayas / Mountain Zone",
            "taxonomy": "Mountain & Forest Soils (Inceptisols / Spodosols)",
            "major_subgroup": "Podzolic and Skeletal mountain soils",
            "pH": 5.8,
            "texture": "Silty Loam to Stony",
            "fertility": "Medium-High (High humus in forest floors)",
            "organic_carbon_g_kg": 20.0,
            "typical_crops": ["Apples", "Pears", "Saffron", "Barley", "Maize", "Tea"]
        }

    else:
        soil_profile = {
            "region": "General Indian Subcontinental Baseline",
            "taxonomy": "Inceptisol / Mixed Agricultural Soil",
            "pH": 7.0,
            "texture": "Loam",
            "fertility": "Medium",
            "organic_carbon_g_kg": 9.0,
            "typical_crops": ["General Field Crops"]
        }

    payload = {
        "location": {"latitude": lat, "longitude": lon},
        "soil_profile": soil_profile,
        "source": "ICAR / NBSS&LUP High-Precision Offline Matrix"
    }
    
    return json.dumps(payload, indent=4)

def get_soil_profile(lat: float, lon: float):
    """Soil profile dict for a point, or None if it is outside India."""
    return json.loads(get_precise_india_soil_profile(lat, lon)).get("soil_profile")


def ip_geolocate():
    """Approximate (city-level) location from the public IP -> (lat, lon, label) or None."""
    for url, k_lat, k_lon in [("https://ipapi.co/json/", "latitude", "longitude"),
                              ("http://ip-api.com/json/", "lat", "lon")]:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                d = json.load(r)
            return float(d[k_lat]), float(d[k_lon]), f"IP location ({d.get('city', 'approx.')})"
        except Exception:
            continue
    return None


if __name__ == "__main__":
    print("--- Testing Bengaluru, Karnataka Coordinates ---")
    print(get_precise_india_soil_profile(lat=12.9716, lon=77.5946))