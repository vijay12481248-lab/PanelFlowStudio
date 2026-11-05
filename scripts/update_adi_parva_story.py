import json
from pathlib import Path

path = Path("output/Original_Stories/mahabharata_adi_parva/story.json")
data = json.loads(path.read_text(encoding="utf-8"))

data["bible"]["premise"]["genre"] = "mythology"

# Update characters with authentic Indian historical cinema aesthetics matching ZenBhaktiVibes
characters = {
    "sauti": {
        "id": "sauti",
        "name": "Ugrasrava Sauti",
        "role": "protagonist",
        "age_group": "adult",
        "look": "young Indian mendicant scholar and wandering bard, dusky bronze Indian skin, shaven head with traditional dark hair shikha tuft, broad white tripundra vibhuti sacred ash on brow and upper arms, red kumkum tilak, rudraksha necklace, handwoven cream cotton dhoti with red zari border, angavastram cloth draped over shoulder, carrying bamboo staff and cloth bag, serene eloquent expression",
        "personality": "reverent, poetic, eloquent storyteller",
        "species": "human",
        "gender": "male"
    },
    "shaunaka": {
        "id": "shaunaka",
        "name": "Kulapati Shaunaka",
        "role": "mentor",
        "age_group": "elder",
        "look": "venerable elderly Indian Vedic rishi, weathered brown Indian skin with natural wrinkles, long flowing natural silver-white beard and wavy white hair, broad sacred white bhasma tripundra tilak on wrinkled brow, rudraksha prayer beads, bare-chested ascetic in simple unbleached cotton dhoti, serene enlightened expression",
        "personality": "wise, inquisitive, master of the sacred groves",
        "species": "human",
        "gender": "male"
    },
    "vyasa": {
        "id": "vyasa",
        "name": "Veda Vyasa",
        "role": "other",
        "age_group": "elder",
        "look": "colossal ancient Indian sage and creator, dusky brown skin, long matted dark-grey dreadlocks, piercing visionary dark eyes holding cosmic wisdom, sacred chandan and bhasma markings, natural ascetic beard, wrapped in handspun coarse saffron-brown linen, profound majestic aura",
        "personality": "profound, all-seeing composer of the cosmic epic",
        "species": "human",
        "gender": "male"
    },
    "ganesha": {
        "id": "ganesha",
        "name": "Lord Ganesha",
        "role": "other",
        "age_group": "adult",
        "look": "divine elephant-headed god of wisdom in authentic Indian temple iconography, majestic realistic elephant trunk and texture, compassionate wise eyes, glowing warm golden celestial skin, ornate South Indian gold kiritam crown with intricate temple jewels, draped in crimson and gold zari silk pitambara, holding his broken ivory tusk as a writing stylus",
        "personality": "omniscient divine scribe of the gods",
        "species": "creature",
        "gender": "male"
    },
    "bhishma": {
        "id": "bhishma",
        "name": "Devavrata (Bhishma)",
        "role": "other",
        "age_group": "adult",
        "look": "handsome athletic young Indian kshatriya warrior prince, dusky bronze skin, strong jawline and piercing resolute eyes, dark hair tied in an ancient Indian warrior topknot, wearing ancient Indian engraved gilded brass and copper armour kavacha with sun motifs, gold kundalas earrings, silk dhoti with red and gold border, raising an ancient Indian steel sword",
        "personality": "fearless, steadfast, embodiment of sacrifice",
        "species": "human",
        "gender": "male"
    }
}

data["bible"]["characters"] = list(characters.values())

# Update locations
locations = {
    "naimisharanya": {
        "id": "naimisharanya",
        "name": "Sacred Forest of Naimisharanya",
        "look": "primeval ancient Indian sacred forest, colossal ancient banyan trees with hanging roots, sacred yajna fire altar in stone hermitage, fragrant blue smoke, brass oil lamps, marigold flower garlands, golden morning sunbeams cutting through forest canopy"
    },
    "himalayas": {
        "id": "himalayas",
        "name": "Mount Meru (Himalayan Hermitage)",
        "look": "towering snow-capped jagged Himalayan peaks, high granite stone cave with ancient Sanskrit birch bark scrolls, flickering brass oil diya lamps, overlooking sea of clouds at twilight"
    },
    "ganga": {
        "id": "ganga",
        "name": "Banks of the River Ganga",
        "look": "torrential sacred river Ganga with silver swirling currents, ancient stone ghats, fluttering saffron silk flags, golden dusk sunset lighting"
    },
    "kurukshetra": {
        "id": "kurukshetra",
        "name": "Plains of Kurukshetra",
        "look": "vast dusty horizon under blood-red sunset, silhouetted ancient Indian armies with spears, chariots, and brass war trumpets awaiting destiny"
    }
}

data["bible"]["locations"] = list(locations.values())

path.write_text(json.dumps(data, indent=2), encoding="utf-8")
print("Updated story.json with ZenBhaktiVibes authentic Indian art style!")
