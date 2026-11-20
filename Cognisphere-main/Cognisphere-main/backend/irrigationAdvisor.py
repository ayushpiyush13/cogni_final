"""
CropShield AI - Irrigation Advisor (India)

recommend_irrigation_method(soil_type, crop_name, water_availability="Moderate",
                            region=None, month=None, salinity_risk=None) -> dict

Legacy keys kept for the app:  method, efficiency, rationale, key_benefit
New keys (all optional to use): crop_used, crop_matched, season, season_note, sowing_now,
    water_need, irrigations, critical_stages, soil_tips, cautions, alternatives, low_water_tip,
    scheme, method_key, soil_group

All numbers are INDICATIVE ranges drawn from ICAR / state agriculture university / FAO-56 style
guidance. They are meant to guide, not replace local KVK advice or a soil / water test.
"""
import datetime

# --------------------------------------------------------------------------------------
# 1. Irrigation methods (efficiency = field application efficiency, typical Indian farms)
#    Flood irrigation is taken as ~40 % efficient (see FLOOD_BASELINE in irrigationPipeline)
# --------------------------------------------------------------------------------------
METHODS = {
    "drip": dict(
        name="Drip Irrigation (Micro-Irrigation)", efficiency="85% - 95%", family="drip",
        why=("Delivers water drop by drop at the root zone, cutting evaporation and deep-percolation losses, "
             "and lets you give fertilizer through the water (fertigation)."),
        benefit="Saves roughly 30-50% water over flood irrigation, with less weeding and better fertilizer use."),
    "sprinkler": dict(
        name="Sprinkler Irrigation System", efficiency="70% - 80%", family="sprinkler",
        why=("Sprays water like gentle rain with light, controllable doses; it suits undulating or sandy land "
             "and needs little land levelling."),
        benefit="Saves roughly 25-40% water over flood irrigation and gives uniform germination."),
    "microsprinkler": dict(
        name="Micro-Sprinkler / Mini-Sprinkler", efficiency="75% - 85%", family="sprinkler",
        why=("Small sprinklers wet the area under each tree or plant, which suits orchards, nurseries and sandy soil "
             "where drip lines alone wet too little root area."),
        benefit="Saves roughly 30-40% water over flood irrigation and also cools the canopy in hot weather."),
    "border": dict(
        name="Border-Strip / Check-Basin Irrigation with Laser Land Leveling", efficiency="50% - 60%",
        family="surface",
        why=("Water spreads evenly across levelled strips or small basins; on a laser-levelled field it wastes "
             "far less water than wild flooding and costs little to run."),
        benefit="Laser levelling alone can save about 20-25% water and improves crop stand."),
    "furrow": dict(
        name="Smart Furrow Irrigation with Moisture Sensors", efficiency="60% - 70%", family="surface",
        why=("Water runs in small furrows between crop rows, timed by a moisture sensor or tensiometer, so only the "
             "root zone is wetted and waterlogging is avoided."),
        benefit="Prevents over-irrigation and saves water compared with flooding the whole field."),
    "ridge": dict(
        name="Ridge-Furrow / Raised-Bed Irrigation", efficiency="60% - 70%", family="surface",
        why=("The crop grows on ridges or raised beds with water in the furrows; excess water drains away, "
             "roots stay aerated and less water is used than in flat flooding."),
        benefit="Protects against waterlogging and can cut water use by about 20-30%."),
    "awd": dict(
        name="Alternate Wetting and Drying (AWD) for Rice", efficiency="50% - 60%", family="surface",
        why=("The field is flooded, then left to dry until the water level drops about 15 cm below the soil surface "
             "(check with a perforated field water tube) before flooding again."),
        benefit="Cuts rice water use by roughly 15-30% with no yield loss in trials, and reduces methane."),
}

SURFACE_TO_UPGRADE = {"border", "furrow", "ridge"}

# --------------------------------------------------------------------------------------
# 2. Soil groups: how each Indian soil behaves with water
# --------------------------------------------------------------------------------------
SOIL_GROUP = {
    "Black Soil (Regur)": "heavy",
    "Alluvial Soil": "medium",
    "Other Soil": "medium",
    "Red and Laterite Soil": "light",
    "Sandy Soil": "light",
    "Arid / Desert Soil": "light",
    "Mountain & Forest Soil": "hills",
}
SOIL_WHY = {
    "heavy": "Black clay soil holds water well but drains slowly, so give fewer, well-timed irrigations and keep drainage open.",
    "medium": "Alluvial / loamy soil holds water fairly well, so match each dose to the crop stage.",
    "light": "This light, fast-draining soil loses water quickly, so small and frequent doses work best.",
    "hills": "Sloping hill soil runs off easily, so use low application rates and terraces or contour lines.",
}
SOIL_TIPS = {
    "Black Soil (Regur)": [
        "Black soil cracks when dry and swells when wet: irrigate before deep cracks open, but never leave water standing.",
        "Use broad-bed-and-furrow or ridges so excess rain water drains out."],
    "Alluvial Soil": [
        "Level the field (laser levelling if possible) so water reaches the far end without ponding.",
        "In low-lying clayey patches keep drains open to avoid waterlogging."],
    "Red and Laterite Soil": [
        "These soils drain fast and hold little water: irrigate lightly and more often, and mulch to keep moisture.",
        "Add farmyard manure / compost - it raises the soil's water-holding capacity."],
    "Sandy Soil": [
        "Give small, frequent irrigations; mulch heavily to cut evaporation.",
        "Irrigate in the early morning or evening and add compost to hold water."],
    "Arid / Desert Soil": [
        "Water is lost very quickly here: use drip or sprinkler, irrigate at night or early morning, and mulch.",
        "Test your irrigation water (EC) - saline water needs extra care."],
    "Mountain & Forest Soil": [
        "Make terraces or contour bunds and mulch to stop runoff and erosion.",
        "Gravity-fed drip or low-rate sprinklers work well; rain is the main source, so irrigate only in dry spells."],
    "Other Soil": ["Check soil moisture by hand (a pinch of soil at 10 cm depth) before each irrigation."],
}
SALINITY_TIP = ("Salinity risk: use good-quality water, avoid many light irrigations (they concentrate salts), "
                "irrigate with drip/sprinkler and give an occasional deeper leaching irrigation. Add gypsum on alkaline (sodic) soil.")

# --------------------------------------------------------------------------------------
# 3. Region notes (matched on words in the region name)
# --------------------------------------------------------------------------------------
REGION_NOTES = [
    ("gangetic", "Groundwater is falling in large parts of the Indo-Gangetic plain (notably Punjab, Haryana, Delhi and western UP): "
                 "prefer water-saving methods and avoid needless flooding."),
    ("arid", "Water is scarce and often saline in the western arid region: micro-irrigation subsidies are available, "
             "so drip or sprinkler pays back quickly."),
    ("deccan", "Rain is erratic on the Deccan: plan protective irrigation for the critical stages and store rain water in farm ponds."),
    ("western ghats", "Monsoon rain is heavy but January-May is dry: plan summer irrigation and mulch to hold moisture."),
    ("peninsular", "Tanks and borewells are the main sources here: schedule irrigation to critical stages to save pumping."),
    ("mountain", "Use terraces and gravity-fed drip; irrigate only to bridge dry spells."),
]

# --------------------------------------------------------------------------------------
# 4. Crop knowledge base
#    m = preferred method for (heavy, medium, light, hills) soils; drip_ok = row/high-value crop
#    sow = usual sowing/planting months; need = seasonal water need (rain + irrigation)
# --------------------------------------------------------------------------------------
H, M, L, HL = 0, 1, 2, 3
CROPS = {
    "Wheat": dict(
        season="Rabi", sow=(10, 11, 12), need="450-650 mm", irrig="4-6 irrigations", drip_ok=False,
        m=("border", "border", "sprinkler", "sprinkler"),
        stages=[("Crown root initiation (most critical)", "20-25 days after sowing"),
                ("Tillering", "40-45 days"), ("Jointing", "60-65 days"), ("Flowering", "80-85 days"),
                ("Milking", "100-105 days"), ("Dough", "115-120 days")],
        alt=[("ridge", "Raised-bed wheat saves about 20-30% water and reduces lodging."),
             ("sprinkler", "Good where the land is not levelled or the soil is light.")],
        cautions=["Never skip the crown-root-initiation irrigation.",
                  "Avoid irrigating in strong wind at grain filling - it can cause lodging."],
        low="With only 1-2 irrigations give them at crown root initiation and flowering. Chickpea, mustard or barley need much less water."),
    "Rice": dict(
        season="Kharif", sow=(6, 7), need="1,000-1,600 mm", irrig="Keep 2-5 cm water, then re-flood by AWD",
        drip_ok=False, m=("awd", "awd", "awd", "awd"),
        stages=[("Establishment", "first 7-10 days after transplanting: 2-3 cm water"),
                ("Tillering", "20-45 days after transplanting"), ("Panicle initiation", "45-60 days"),
                ("Flowering (most sensitive)", "60-90 days: keep shallow water"),
                ("Before harvest", "stop irrigation 10-15 days before harvest")],
        alt=[("awd", "Direct-seeded rice (DSR) on a levelled field can save roughly 15-30% water and labour.")],
        cautions=["Sprinkler or drip is not recommended for normal paddy.",
                  "Avoid any water stress at flowering - it hits yield hardest."],
        low="In a dry year use AWD at least, or switch part of the area to maize or pulses.",
        light_warn="Rice loses a lot of water by deep percolation on light soil; maize, pulses or millets use far less water."),
    "Sugarcane": dict(
        season="Annual (12-18 months)", sow=(2, 3, 10), need="1,500-2,500 mm",
        irrig="Flood: every 7-10 days in summer, 15-25 days in winter", drip_ok=True,
        m=("drip", "drip", "drip", "drip"),
        stages=[("Germination / establishment", "0-35 days: light, frequent water"),
                ("Tillering", "35-100 days: keep moist"),
                ("Grand growth (peak need)", "100-270 days: never let it dry"),
                ("Ripening", "last 4-6 weeks: reduce, stop 2-3 weeks before harvest")],
        alt=[("furrow", "Alternate-furrow / trench irrigation saves about 20-30% if drip is not affordable.")],
        cautions=["Drain heavy soil after heavy rain - waterlogging reduces sugar."],
        low="Drip with trash mulching is the best way to grow cane on limited water."),
    "Cotton": dict(
        season="Kharif", sow=(4, 5, 6), need="700-1,200 mm", irrig="3-6 irrigations", drip_ok=True,
        m=("ridge", "ridge", "drip", "drip"),
        stages=[("Squaring", "45-60 days after sowing"), ("Flowering (most sensitive)", "60-90 days"),
                ("Boll development", "90-130 days")],
        alt=[("drip", "Drip with fertigation is widely used in Maharashtra, Gujarat and Telangana and saves about 30-50% water.")],
        cautions=["Avoid late irrigation during boll opening - it delays maturity.",
                  "Waterlogging hurts cotton badly: sow on ridges on black soil."],
        low="Drip and irrigating only at squaring, flowering and boll development gives the most crop per drop."),
    "Maize": dict(
        season="Kharif / Rabi / Zaid", sow=(6, 7, 10, 11, 2, 3), need="500-800 mm", irrig="3-5 irrigations (Rabi)",
        drip_ok=True, m=("ridge", "ridge", "sprinkler", "sprinkler"),
        stages=[("Knee-high", "25-30 days after sowing"), ("Tasseling and silking (most critical)", "55-70 days"),
                ("Grain filling", "75-100 days")],
        alt=[("drip", "Drip works well for Rabi and spring maize.")],
        cautions=["Maize cannot stand waterlogging - sow on ridges or raised beds."],
        low="Protect water at tasseling/silking; skip early extra irrigations."),
    "Chickpea": dict(
        season="Rabi", sow=(10, 11), need="250-350 mm", irrig="1-2 irrigations", drip_ok=False,
        m=("sprinkler", "sprinkler", "sprinkler", "sprinkler"),
        stages=[("Branching", "30-35 days after sowing"), ("Pod filling", "55-65 days")],
        alt=[("ridge", "On heavy soil, a light irrigation through furrows also works.")],
        cautions=["Skip irrigation at full flowering, and avoid over-watering - it gives leafy growth and disease."],
        low="Even one irrigation at branching or pod filling clearly raises yield."),
    "Pulses": dict(
        season="Kharif / Rabi / Zaid", sow=(6, 7, 10, 11, 3, 4), need="250-400 mm", irrig="1-3 light irrigations",
        drip_ok=False, m=("sprinkler", "sprinkler", "sprinkler", "sprinkler"),
        stages=[("Flowering", "35-45 days after sowing"), ("Pod filling", "55-70 days")],
        alt=[("ridge", "Sow on ridges where waterlogging is a risk.")],
        cautions=["Pulses are very sensitive to waterlogging; give light irrigations only."],
        low="One irrigation at flowering or pod filling is the best use of scarce water."),
    "Guar": dict(
        season="Kharif", sow=(6, 7), need="250-350 mm", irrig="Mostly rainfed; 1-2 life-saving irrigations",
        drip_ok=False, m=("sprinkler", "sprinkler", "sprinkler", "sprinkler"),
        stages=[("Flowering", "35-45 days after sowing"), ("Pod formation", "55-70 days")],
        alt=[], cautions=["Excess water gives leafy growth and fewer pods."],
        low="Irrigate only to bridge a long dry spell at flowering or pod formation."),
    "Mustard": dict(
        season="Rabi", sow=(10, 11), need="240-400 mm", irrig="1-2 irrigations", drip_ok=False,
        m=("border", "border", "sprinkler", "sprinkler"),
        stages=[("Rosette / branching", "30-35 days after sowing"), ("Siliqua (pod) formation", "55-70 days")],
        alt=[("sprinkler", "Sprinkler saves water and avoids waterlogging.")],
        cautions=["Mustard dislikes waterlogging; irrigate lightly."],
        low="One irrigation at 30-35 days gives most of the benefit."),
    "Potato": dict(
        season="Rabi (plains)", sow=(10, 11), need="500-700 mm", irrig="6-8 light irrigations", drip_ok=True,
        m=("ridge", "ridge", "drip", "drip"),
        stages=[("After planting", "light irrigation within 7-10 days for even emergence"),
                ("Stolon / tuber initiation (critical)", "25-35 days after planting"),
                ("Tuber bulking", "40-80 days: every 7-10 days"),
                ("Before harvest", "stop 10-15 days before haulm cutting")],
        alt=[("sprinkler", "Sprinkler is common in Punjab, Haryana and UP and can save about 30-40% water.")],
        cautions=["Water stress at tuber initiation cuts yield; waterlogging causes rot.",
                  "On frosty nights (Dec-Jan) a light irrigation in the evening helps protect the crop."],
        low="Light, frequent irrigation by drip or sprinkler uses far less water than heavy flooding."),
    "Onion": dict(
        season="Rabi", sow=(11, 12), need="350-550 mm", irrig="8-12 light irrigations", drip_ok=True,
        m=("drip", "drip", "drip", "drip"),
        stages=[("Transplanting", "irrigate immediately, then every 5-7 days"),
                ("Bulb development (critical)", "every 8-10 days"),
                ("Before harvest", "stop 10-15 days before harvest")],
        alt=[("sprinkler", "Sprinkler is a cheaper option for small plots.")],
        cautions=["Irregular watering causes split bulbs; excess water near harvest hurts storage."],
        low="Drip with mulch is the best way to save water on onion."),
    "Vegetables": dict(
        season="Year-round", sow=tuple(range(1, 13)), need="400-800 mm", irrig="Light irrigation every 2-5 days",
        drip_ok=True, m=("drip", "drip", "drip", "drip"),
        stages=[("Transplanting / establishment", "water immediately, then every 2-3 days"),
                ("Flowering and fruit set (critical)", "keep soil evenly moist"),
                ("Fruit development", "regular, even moisture")],
        alt=[("sprinkler", "Use for leafy vegetables and nursery beds.")],
        cautions=["Uneven watering causes fruit cracking and blossom-end rot (tomato)."],
        low="Drip plus plastic or straw mulch can save 30-50% water."),
    "Millets": dict(
        season="Kharif (Rabi sorghum)", sow=(6, 7, 10), need="350-500 mm", irrig="Mostly rainfed; 1-3 protective irrigations",
        drip_ok=False, m=("sprinkler", "sprinkler", "sprinkler", "sprinkler"),
        stages=[("Tillering / panicle initiation", "25-40 days after sowing (only if dry)"),
                ("Flowering and grain filling", "45-70 days")],
        alt=[], cautions=["Millets are drought-hardy: irrigate only to bridge dry spells."],
        low="Skip irrigation except at flowering and grain filling."),
    "Groundnut": dict(
        season="Kharif / Summer", sow=(6, 7, 1, 2), need="500-700 mm", irrig="4-6 irrigations (Summer)", drip_ok=True,
        m=("ridge", "sprinkler", "sprinkler", "sprinkler"),
        stages=[("Flowering and pegging (critical)", "25-45 days after sowing"),
                ("Pod development", "45-75 days"), ("Pod filling", "75-100 days")],
        alt=[("drip", "Drip suits summer groundnut on light soils.")],
        cautions=["Keep soil loose and moist at pegging; avoid waterlogging.",
                  "Stop irrigation 10-15 days before harvest."],
        low="Never let the crop dry out at pegging and pod development."),
    "Soybean": dict(
        season="Kharif", sow=(6, 7), need="450-700 mm", irrig="Mostly rainfed; 1-2 protective irrigations", drip_ok=False,
        m=("ridge", "ridge", "sprinkler", "sprinkler"),
        stages=[("Flowering", "35-45 days after sowing"), ("Pod filling", "55-75 days")],
        alt=[("sprinkler", "Good for a protective irrigation in a long dry spell.")],
        cautions=["Use broad-bed-and-furrow on black soil so water does not stand."],
        low="Irrigate only at flowering and pod filling in a dry spell."),
    "Barley": dict(
        season="Rabi", sow=(11,), need="250-350 mm", irrig="2-3 irrigations", drip_ok=False,
        m=("border", "border", "sprinkler", "sprinkler"),
        stages=[("Crown root initiation", "25-30 days after sowing"), ("Tillering / jointing", "45-60 days"),
                ("Flowering / grain filling", "75-90 days")],
        alt=[], cautions=["Avoid waterlogging."], low="Barley is a good low-water alternative to wheat."),
    "Mango": dict(
        season="Perennial", sow=(7, 8), need="Orchard: follow tree-age schedule", irrig="Every 10-15 days in dry months",
        drip_ok=True, m=("drip", "drip", "drip", "drip"),
        stages=[("Young trees", "water every 7-10 days in summer for the first 3 years"),
                ("Flower induction (Oct-Jan)", "hold back irrigation until flowering starts"),
                ("Fruit set to fruit growth (Feb-May)", "irrigate every 10-15 days")],
        alt=[("microsprinkler", "Micro-sprinklers suit sandy soils.")],
        cautions=["Irrigating during flowering can cause flower drop and a leafy flush instead of fruit."],
        low="Irrigate mainly at fruit set and fruit growth; mulch the tree basin."),
    "Citrus": dict(
        season="Perennial", sow=(7, 8), need="Orchard: follow tree-age schedule", irrig="Every 7-12 days in dry months",
        drip_ok=True, m=("drip", "drip", "drip", "drip"),
        stages=[("Flowering and fruit set", "avoid water stress"),
                ("Fruit development", "regular moisture - dry spells followed by flooding cause fruit drop and cracking")],
        alt=[("microsprinkler", "Micro-sprinklers also work.")],
        cautions=["Keep water away from the trunk to avoid gummosis (use drip laterals on both sides)."],
        low="Drip with mulch around the tree gives the best saving."),
    "Banana": dict(
        season="Perennial / 12-14 months", sow=(6, 7, 2, 3), need="1,800-2,200 mm", irrig="Drip: small daily doses",
        drip_ok=True, m=("drip", "drip", "drip", "drip"),
        stages=[("Establishment", "light, regular water"), ("Vegetative growth", "steady water and fertigation"),
                ("Flowering and bunch development (critical)", "never let it dry")],
        alt=[], cautions=["Banana suffers from both drought and waterlogging."],
        low="Drip with fertigation is reported to save about 30-45% water in banana."),
    "Apple": dict(
        season="Perennial (hills)", sow=(12, 1, 2), need="Mostly rain; supplement in dry spells", irrig="Basin / drip in dry spells",
        drip_ok=True, m=("drip", "drip", "drip", "drip"),
        stages=[("Flowering and fruit set (Mar-Apr)", "irrigate if dry"),
                ("Fruit growth (May-Jul, critical)", "irrigate in dry spells")],
        alt=[], cautions=["Mulch the tree basin; avoid waterlogging on flat patches."],
        low="Use gravity-fed drip and mulch; irrigate only in dry spells."),
    "Coconut": dict(
        season="Perennial", sow=(6, 7), need="Regular summer irrigation (follow local CPCRI/KVK schedule)",
        irrig="Dry months: every 3-4 days (basin) or daily (drip)", drip_ok=True, m=("drip", "drip", "drip", "drip"),
        stages=[("Young palms", "water regularly in dry months"), ("Bearing palms", "irrigate through the dry season")],
        alt=[], cautions=["Mulch with husk or leaves around the palm base."],
        low="Drip plus husk mulch conserves water."),
    "Cashew": dict(
        season="Perennial", sow=(6, 7), need="Mostly rainfed", irrig="Young plants in summer; 1-2 at fruit set in dry years",
        drip_ok=True, m=("drip", "drip", "drip", "drip"),
        stages=[("Young plants", "irrigate in summer"), ("Flowering and fruit set", "1-2 light irrigations in dry years")],
        alt=[], cautions=["Avoid irrigation during heavy flowering rain periods."],
        low="Irrigate only young plants and fruit set."),
    "Areca nut": dict(
        season="Perennial", sow=(6, 7), need="Regular summer irrigation", irrig="Every 4-7 days in summer", drip_ok=True,
        m=("drip", "drip", "drip", "drip"),
        stages=[("Summer (Feb-May)", "irrigate regularly")], alt=[],
        cautions=["Keep drainage open in the monsoon."], low="Drip with mulch saves water."),
    "Orchard Crops": dict(
        season="Perennial", sow=(7, 8), need="Orchard: follow tree-age schedule", irrig="Every 7-15 days in dry months",
        drip_ok=True, m=("drip", "drip", "drip", "drip"),
        stages=[("Young trees", "water regularly in summer"), ("Flowering and fruit set", "avoid stress"),
                ("Fruit development", "regular moisture")],
        alt=[("microsprinkler", "Micro-sprinklers suit sandy soils.")],
        cautions=["Keep water off the trunk."], low="Drip with mulch is the best option."),
    "Tea": dict(
        season="Perennial", sow=(6, 7), need="Mostly rain-fed; dry-season irrigation", irrig="Sprinkler in dry months (Dec-Mar)",
        drip_ok=False, m=("sprinkler", "sprinkler", "sprinkler", "sprinkler"),
        stages=[("Dry season", "overhead sprinkler during dry spells to keep flushes coming")], alt=[],
        cautions=["Avoid waterlogging."], low="Irrigate only in prolonged dry spells."),
    "Coffee": dict(
        season="Perennial", sow=(6, 7), need="Rain plus blossom and backing showers", irrig="Sprinkler showers in Feb-Apr",
        drip_ok=True, m=("sprinkler", "sprinkler", "sprinkler", "sprinkler"),
        stages=[("Blossom shower", "sprinkler irrigation after the dry spell to trigger flowering"),
                ("Backing shower", "about 2-3 weeks later")],
        alt=[("drip", "Drip is increasingly used in dry years.")],
        cautions=["Time blossom irrigation with the mature flower buds."], low="Give blossom and backing showers only."),
    "Rubber": dict(
        season="Perennial", sow=(6, 7), need="Mostly rainfed", irrig="Young plants in summer", drip_ok=True,
        m=("drip", "drip", "drip", "drip"),
        stages=[("Young plants", "irrigate in dry summer months")], alt=[],
        cautions=["Mature rubber is mostly rainfed."], low="Irrigate only young plants."),
    "Spices": dict(
        season="Perennial / Kharif", sow=(5, 6), need="Rain plus dry-season irrigation", irrig="Sprinkler or drip in Feb-May",
        drip_ok=True, m=("sprinkler", "sprinkler", "drip", "sprinkler"),
        stages=[("Dry months (Feb-May)", "irrigate every 7-10 days")], alt=[],
        cautions=["Keep drainage good in the monsoon to avoid rot."], low="Mulch and irrigate only in dry months."),
    "Saffron": dict(
        season="Perennial corm", sow=(8, 9), need="Mostly rainfed", irrig="Sprinkler in dry Aug-Sep", drip_ok=False,
        m=("sprinkler", "sprinkler", "sprinkler", "sprinkler"),
        stages=[("Before flowering (Aug-Sep)", "light sprinkler irrigation if it is dry"),
                ("Flowering (Oct-Nov)", "keep soil just moist")],
        alt=[], cautions=["Corms rot in waterlogged soil: keep drainage open."],
        low="Irrigate only in dry weather before flowering."),
    "Tobacco": dict(
        season="Rabi (FCV, Andhra)", sow=(10, 11), need="300-500 mm", irrig="Light, frequent irrigations", drip_ok=False,
        m=("ridge", "ridge", "sprinkler", "sprinkler"),
        stages=[("Transplanting", "irrigate at once"), ("Knee-high to topping", "regular light irrigation")],
        alt=[], cautions=["Excess water reduces leaf quality."], low="Light irrigation at critical growth only."),
    "General Field Crops": dict(
        season="Varies", sow=tuple(range(1, 13)), need="Varies by crop", irrig="Irrigate when soil is dry at 10 cm",
        drip_ok=False, m=("furrow", "furrow", "sprinkler", "sprinkler"),
        stages=[("Early growth", "light irrigation"), ("Flowering and grain filling", "never let the soil dry out")],
        alt=[], cautions=[], low="Irrigate only at flowering and grain filling."),
}

# --------------------------------------------------------------------------------------
# 5. Names farmers and datasets use -> canonical crop in CROPS
# --------------------------------------------------------------------------------------
ALIASES = {
    "paddy": "Rice", "rice": "Rice", "dhan": "Rice", "wheat": "Wheat", "gehu": "Wheat",
    "sugarcane": "Sugarcane", "cane": "Sugarcane", "cotton": "Cotton",
    "maize": "Maize", "corn": "Maize", "makka": "Maize",
    "bajra": "Millets", "bajra (pearl millet)": "Millets", "pearl millet": "Millets", "jowar": "Millets",
    "sorghum": "Millets", "ragi": "Millets", "finger millet": "Millets", "millets": "Millets",
    "chickpea": "Chickpea", "gram": "Chickpea", "chana": "Chickpea",
    "guar": "Guar", "cluster bean": "Guar",
    "pulses": "Pulses", "arhar": "Pulses", "tur": "Pulses", "pigeon pea": "Pulses", "moong": "Pulses",
    "urad": "Pulses", "lentil": "Pulses", "masoor": "Pulses", "peas": "Pulses",
    "mustard": "Mustard", "rapeseed": "Mustard", "sarson": "Mustard",
    "groundnut": "Groundnut", "peanut": "Groundnut", "soybean": "Soybean", "soyabean": "Soybean",
    "potato": "Potato", "aloo": "Potato", "onion": "Onion", "garlic": "Onion",
    "vegetables": "Vegetables", "tomato": "Vegetables", "brinjal": "Vegetables", "chilli": "Vegetables",
    "okra": "Vegetables", "cabbage": "Vegetables", "cauliflower": "Vegetables", "cucumber": "Vegetables",
    "gourd": "Vegetables",
    "mango": "Mango", "citrus": "Citrus", "orange": "Citrus", "lemon": "Citrus", "mosambi": "Citrus",
    "banana": "Banana", "apple": "Apple", "apples": "Apple", "pear": "Apple", "pears": "Apple",
    "coconut": "Coconut", "cashew": "Cashew", "areca nut": "Areca nut", "arecanut": "Areca nut",
    "betel nut": "Areca nut", "orchard crops": "Orchard Crops", "pomegranate": "Orchard Crops",
    "guava": "Orchard Crops", "grapes": "Orchard Crops",
    "tea": "Tea", "coffee": "Coffee", "rubber": "Rubber",
    "spices": "Spices", "pepper": "Spices", "cardamom": "Spices", "turmeric": "Spices", "ginger": "Spices",
    "saffron": "Saffron", "barley": "Barley", "jau": "Barley", "tobacco": "Tobacco",
    "general field crops": "General Field Crops",
}

# --------------------------------------------------------------------------------------
# 6. PMKSY - Per Drop More Crop (central scheme) - verify the current rates with your state office
# --------------------------------------------------------------------------------------
SCHEME_NOTE = ("PMKSY - Per Drop More Crop: central subsidy of about 55% for small and marginal farmers and 45% for "
               "others on drip and sprinkler systems (many states add more). Apply at your state agriculture / "
               "horticulture department or its micro-irrigation portal; confirm current rates.")

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def resolve_crop(crop_name):
    """Return (canonical crop, matched?) for any farmer-style crop name."""
    key = str(crop_name or "").strip().lower()
    if key in ALIASES:
        return ALIASES[key], True
    for canon in CROPS:                       # exact canonical name, any case
        if canon.lower() == key:
            return canon, True
    for alias, canon in ALIASES.items():      # e.g. "basmati rice" contains "rice"
        if len(alias) > 3 and alias in key:
            return canon, True
    return "General Field Crops", False


def known_crops():
    """Crop names the advisor has crop-specific rules for (for drop-downs)."""
    return [c for c in CROPS if c != "General Field Crops"]


def _normalise_water(w):
    w = str(w or "Moderate").strip().capitalize()
    return w if w in ("Low", "Moderate", "High") else "Moderate"


def _sowing_text(months):
    months = sorted(set(months))
    if len(months) >= 12:
        return "any time of year"
    # join consecutive months into ranges, wrapping over December-January
    runs, cur = [], [months[0]]
    for m in months[1:]:
        if m == cur[-1] + 1:
            cur.append(m)
        else:
            runs.append(cur)
            cur = [m]
    runs.append(cur)
    if len(runs) > 1 and runs[0][0] == 1 and runs[-1][-1] == 12:
        runs[0] = runs.pop()[:] + runs[0]
    return " / ".join(MONTHS[r[0] - 1] if len(r) == 1 else f"{MONTHS[r[0] - 1]}-{MONTHS[r[-1] - 1]}" for r in runs)


def recommend_irrigation_method(soil_type, crop_name, water_availability="Moderate",
                                region=None, month=None, salinity_risk=None):
    """
    Best irrigation method for an Indian soil + crop + water situation.
    soil_type: 'Alluvial Soil', 'Black Soil (Regur)', 'Red and Laterite Soil', 'Sandy Soil',
               'Arid / Desert Soil', 'Mountain & Forest Soil' or 'Other Soil'.
    """
    water = _normalise_water(water_availability)
    group = SOIL_GROUP.get(soil_type, "medium")
    gi = {"heavy": H, "medium": M, "light": L, "hills": HL}[group]
    crop, matched = resolve_crop(crop_name)
    info = CROPS[crop]
    month = month or datetime.date.today().month

    key = info["m"][gi]
    if water == "Low" and key in SURFACE_TO_UPGRADE:              # scarcity: move to a pressurised system
        key = "drip" if info["drip_ok"] else "sprinkler"
    method = METHODS[key]

    # --- alternatives (never the same as the main pick) ---
    alternatives = [{"method": METHODS[k]["name"], "when": txt} for k, txt in info["alt"] if k != key]

    # --- cautions ---
    cautions = list(info["cautions"])
    if group == "light" and info.get("light_warn"):
        cautions.insert(0, info["light_warn"])
    if group == "heavy" and key in ("sprinkler",):
        cautions.append("Black clay seals when wet: use a low application rate so water does not run off.")
    if key == "drip" and group == "light":
        cautions.append("Light soils need short, frequent drip cycles; use mulch to cut evaporation.")
    if salinity_risk and str(salinity_risk).lower() in ("high", "medium"):
        cautions.append(SALINITY_TIP)

    # --- tips ---
    tips = list(SOIL_TIPS.get(soil_type, SOIL_TIPS["Other Soil"]))
    if region:
        for word, note in REGION_NOTES:
            if word in str(region).lower():
                tips.append(note)
                break
    if water == "Low":
        tips.append(info["low"])

    # --- sowing window ---
    sow_months = info["sow"]
    sowing_now = month in sow_months
    season_note = (f"{crop} season: {info['season']}. Usual sowing / planting: {_sowing_text(sow_months)}."
                   + (" It is the sowing window now." if sowing_now and len(sow_months) < 12 else ""))

    rationale = f"{method['why']} {SOIL_WHY[group]}"
    return {
        # legacy keys used by the dashboard
        "method": method["name"], "efficiency": method["efficiency"],
        "rationale": rationale, "key_benefit": method["benefit"],
        # new, richer advice
        "method_key": key, "soil_group": group, "crop_used": crop, "crop_matched": matched,
        "season": info["season"], "season_note": season_note, "sowing_now": sowing_now,
        "water_need": info["need"], "irrigations": info["irrig"],
        "critical_stages": [{"stage": s, "when": w} for s, w in info["stages"]],
        "soil_tips": tips, "cautions": cautions, "alternatives": alternatives,
        "low_water_tip": info["low"] if water == "Low" else "",
        "scheme": SCHEME_NOTE if method["family"] in ("drip", "sprinkler") else "",
    }


# --- Example Integration Test ---
if __name__ == "__main__":
    import json
    print("--- CropShield AI Irrigation Advisor (India) ---")
    for soil, crop, w in [("Alluvial Soil", "Wheat", "Moderate"), ("Alluvial Soil", "Rice", "Low"),
                          ("Arid / Desert Soil", "Bajra (Pearl Millet)", "Low"), ("Black Soil (Regur)", "Cotton", "Low")]:
        print(f"\n{soil} | {crop} | water={w}")
        print(json.dumps(recommend_irrigation_method(soil, crop, w), indent=2, ensure_ascii=False)[:900])