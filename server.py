import asyncio
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import gemini_provider as gemini

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
STATIC_DIR = BASE_DIR / "static"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
CACHE_INDEX_PATH = DATA_DIR / "cache_index.json"


def load_api_key(name: str) -> str:
    if os.environ.get(f"HOMI_{name}"):
        return os.environ[f"HOMI_{name}"].strip()
    for env_file in [BASE_DIR / "api_key.md", BASE_DIR / ".env"]:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip()
    raise HTTPException(status_code=503, detail=f"Configure project credential HOMI_{name} or a project .env before using this service.")


ORIANE_BASE_URL = "https://connect.oriane.xyz"
generation_lock = asyncio.Lock()


def migrate_cache_metadata(index: Dict[str, Any]) -> Dict[str, Any]:
    """Retain historical media and IDs without treating them as new Gemini jobs."""
    for section in ("segments", "voiceovers", "plans", "rooms"):
        for record in index.get(section, {}).values():
            if not isinstance(record, dict) or record.get("provider"):
                continue
            if record.get("model") == "gmi-room-glide":
                record.update(provider="local", legacy_model=record["model"], model="local-photo-glide", media_kind="photo_sequence")
            else:
                record["provider"] = "gmi-cloud"
                record["provenance"] = "Historical cached output; original media retained."
                if record.get("status") in ("processing", "queued", "in_progress") and not record.get("local_file"):
                    record["status"] = "archived"
    history = index.setdefault("generation_history", [])
    for record in index.pop("gmi_generations", []):
        history.append({**record, "provider": "gmi-cloud"})
    return index


def load_cache_index() -> Dict[str, Any]:
    if CACHE_INDEX_PATH.exists():
        try:
            return migrate_cache_metadata(json.loads(CACHE_INDEX_PATH.read_text()))
        except Exception:
            pass
    return {"segments": {}, "voiceovers": {}, "oriane": {}, "plans": {}}


def save_cache_index(index: Dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile(mode="w", dir=CACHE_INDEX_PATH.parent, delete=False) as temporary:
        json.dump(index, temporary, indent=2)
        temporary.flush()
        os.fsync(temporary.fileno())
    Path(temporary.name).replace(CACHE_INDEX_PATH)


# Curated Bay Area Redfin Luxury Listings with spatially coherent room sequences & 3D hotspots
CURATED_LISTINGS: List[Dict[str, Any]] = [
    {
        "id": "palo-alto-glass-villa",
        "zip_code": "94301",
        "city": "Palo Alto",
        "video_duration_label": "0:34",
        "preview_clip_url": "/api/cache/tour_36s_palo_alto_94301.mp4",
        "full_tour_url": "/api/cache/tour_36s_palo_alto_94301.mp4",
        "redfin_url": "https://www.redfin.com/CA/Palo-Alto/1420-Bryant-St-94301/home/1489201",
        "title": "Old Palo Alto Architectural Glass Villa",
        "address": "1420 Bryant St, Palo Alto, CA 94301",
        "neighborhood": "Old Palo Alto • Silicon Valley",
        "price": "$4,850,000",
        "price_num": 4850000,
        "beds": 5,
        "baths": 5.5,
        "sqft": 4620,
        "price_per_sqft": "$1,050",
        "lot_size": "10,450 sq ft",
        "year_built": 2025,
        "vibe_tags": ["Indoor-Outdoor Glass", "Bookmatched Marble", "Zero-Edge Pool", "Smart Home OS"],
        "oriane_keywords": ["luxury home", "house tour", "modern architecture", "pool"],
        "oriane_hashtags": ["realestate", "housetour", "luxuryrealestate", "modernhome"],
        "voiceover_script": (
            "Excuse me, what does 4.85 million dollars actually get you in Old Palo Alto? "
            "Step through the glass courtyard into 4,600 square feet of pure California indoor-outdoor flow. "
            "Notice how the sunlit great room glides straight into a Miele and bookmatched-marble chef kitchen. "
            "Down the gallery hall sits a primary sanctuary with private garden glass, opening directly onto a "
            "heated zero-edge saltwater pool. Pause anywhere to explore the space."
        ),
        "rooms": [
            {
                "id": "exterior",
                "name": "01 · Twilight Glass Courtyard",
                "short_name": "Exterior Entry",
                "floorplan_xy": [15, 78],
                "image_url": "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Warm cedar soffits + floating limestone steps at golden hour",
                "on_screen_hook": "WHAT $4.85M BUYS IN OLD PALO ALTO 👀🏡",
                "spoken_beat": "Excuse me — what does $4.85M actually get you in Old Palo Alto?",
                "ambient_desc": "Architectural lighting, reflection pool & pivot glass entry",
                "hotspots": [
                    {
                        "x": 48,
                        "y": 42,
                        "label": "12-Ft Pivot Glass Entry",
                        "detail": "Motorized double-pane acoustic glass door framing the through-view to the rear pool.",
                        "viral_note": "Oriane Signal: 'Glass door reveal' in first 2.5s boosts completion rate by +44%."
                    },
                    {
                        "x": 72,
                        "y": 68,
                        "label": "Floating Limestone Walkway",
                        "detail": "Radiant-heated limestone slabs with recessed LED perimeter grazing.",
                        "viral_note": "High-contrast twilight reflection triggers 3.2x thumb-stop rate."
                    },
                    {
                        "x": 26,
                        "y": 32,
                        "label": "Western Red Cedar Cladding",
                        "detail": "Sustainably milled clear-grain cedar soffits with concealed gutter system.",
                        "viral_note": "Warm wood + glass aesthetic ranks #1 in Bay Area luxury saves."
                    }
                ]
            },
            {
                "id": "living",
                "name": "02 · Sunlit Double-Height Great Room",
                "short_name": "Great Room",
                "floorplan_xy": [35, 55],
                "image_url": "https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=1280&q=85",
                "vibe": "14-foot ceilings, European white oak planks & disappearing pocket doors",
                "on_screen_hook": "4,620 SQ FT OF INDOOR-OUTDOOR FLOW ✨",
                "spoken_beat": "Step through the glass courtyard into 4,600 sq ft of pure California indoor-outdoor flow.",
                "ambient_desc": "Natural cross-ventilation, linear fireplace & acoustic plaster ceiling",
                "hotspots": [
                    {
                        "x": 54,
                        "y": 58,
                        "label": "Custom Bouclé Conversation Pit",
                        "detail": "9-inch wide-plank European white oak over hydronic radiant floor heating.",
                        "viral_note": "Oriane Signal: Open sightlines to the next room keep viewer retention above 78%."
                    },
                    {
                        "x": 80,
                        "y": 36,
                        "label": "Motorized Fleetwood Pocket Wall",
                        "detail": "24-foot motorized glass wall retracts flush into a concealed structural pocket.",
                        "viral_note": "Mentioning indoor-outdoor flow in caption correlates with 2.4x shares."
                    }
                ]
            },
            {
                "id": "kitchen",
                "name": "03 · Bookmatched Calacatta Chef's Kitchen",
                "short_name": "Chef's Kitchen",
                "floorplan_xy": [55, 42],
                "image_url": "https://images.unsplash.com/photo-1600566753376-12c8ab7fb75b?auto=format&fit=crop&w=1280&q=85",
                "vibe": "14-ft waterfall marble island, Gaggenau + Miele suite & hidden scullery",
                "on_screen_hook": "WAIT UNTIL YOU SEE THIS MARBLE ISLAND 🔥",
                "spoken_beat": "Notice how the sunlit great room glides straight into a Miele and bookmatched-marble chef kitchen.",
                "ambient_desc": "Integrated induction surface, concealed prep kitchen & wine column",
                "hotspots": [
                    {
                        "x": 46,
                        "y": 64,
                        "label": "14-Ft Waterfall Calacatta Island",
                        "detail": "Mitered Italian Calacatta Gold slab with invisible under-counter induction.",
                        "viral_note": "Oriane Signal: 'Kitchen island close-up' is the #1 rewatched timestamp in luxury tours."
                    },
                    {
                        "x": 68,
                        "y": 38,
                        "label": "Integrated Miele & Gaggenau Suite",
                        "detail": "Dual dishwashers, steam combi-oven, and 120-bottle dual-zone wine column.",
                        "viral_note": "Calling out specific luxury appliance brands in onScreenText drives high comment debates."
                    }
                ]
            },
            {
                "id": "primary_bedroom",
                "name": "04 · Primary Sanctuary & Garden Glass",
                "short_name": "Primary Suite",
                "floorplan_xy": [72, 32],
                "image_url": "https://images.unsplash.com/photo-1600585154526-990dced4db0d?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Private corner glass suite, Lutron blackout shades & spa terrace access",
                "on_screen_hook": "PRIMARY SUITE WITH DIRECT POOL ACCESS 🛌🌊",
                "spoken_beat": "Down the gallery hall sits a primary sanctuary with private garden glass...",
                "ambient_desc": "Whisper-quiet acoustic glazing, custom millwork headboard & terrace access",
                "hotspots": [
                    {
                        "x": 50,
                        "y": 54,
                        "label": "King Acoustic Millwork Suite",
                        "detail": "Rift-sawn white oak wall paneling with recessed circadian cove lighting.",
                        "viral_note": "Oriane Signal: Showing bedroom-to-pool transition increases save-to-view ratio by 3.1x."
                    },
                    {
                        "x": 82,
                        "y": 46,
                        "label": "Direct Pool Terrace Sliders",
                        "detail": "Step directly from the primary suite onto the heated limestone pool deck.",
                        "viral_note": "Seamless indoor-to-backyard transition is the climax of top-1% viral reels."
                    }
                ]
            },
            {
                "id": "backyard_pool",
                "name": "05 · Zero-Edge Saltwater Pool & Cabana",
                "short_name": "Resort Backyard",
                "floorplan_xy": [86, 68],
                "image_url": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Heated zero-edge pool, sunken fire lounge & outdoor Lynx kitchen",
                "on_screen_hook": "WOULD YOU LIVE HERE FOR $4.85M? 👇",
                "spoken_beat": "...opening directly onto a heated zero-edge saltwater pool. Pause anywhere to explore the space.",
                "ambient_desc": "Saltwater infinity edge, outdoor rain shower & mature olive trees",
                "hotspots": [
                    {
                        "x": 52,
                        "y": 66,
                        "label": "Heated Zero-Edge Saltwater Pool",
                        "detail": "42-foot lap pool with integrated Baja sun shelf, spa, and automated solar cover.",
                        "viral_note": "Oriane Signal: Ending on twilight pool + question CTA drives 4.8x more comments."
                    },
                    {
                        "x": 30,
                        "y": 44,
                        "label": "Covered Al-Fresco Lounge",
                        "detail": "Infratech flush ceiling heaters, Sonos architectural audio, and outdoor kitchen.",
                        "viral_note": "High-value lifestyle closer for Compound #HackTheFeed distribution."
                    }
                ]
            }
        ],
        "transitions": [
            {
                "index": 0,
                "from_room": "exterior",
                "to_room": "living",
                "title": "Courtyard Entry → Great Room",
                "prompt": "Smooth steady gimbal forward camera walkthrough moving from the modern luxury house exterior courtyard through the glass doors into the bright open-concept living room, architectural real estate tour, natural lighting, 3D spatial feel, no distortion."
            },
            {
                "index": 1,
                "from_room": "living",
                "to_room": "kitchen",
                "title": "Great Room → Chef's Kitchen",
                "prompt": "Smooth steady gimbal forward camera walkthrough gliding from the sunlit modern living room straight into the open-concept marble chef kitchen with waterfall island, architectural real estate tour, natural daylight, 3D spatial feel, no glitches."
            },
            {
                "index": 2,
                "from_room": "kitchen",
                "to_room": "primary_bedroom",
                "title": "Chef's Kitchen → Primary Sanctuary",
                "prompt": "Smooth steady gimbal forward camera walkthrough moving from the minimalist chef kitchen down the warm oak hallway into the serene luxury primary bedroom suite with floor-to-ceiling glass, architectural real estate tour, 3D spatial feel, no glitches."
            },
            {
                "index": 3,
                "from_room": "primary_bedroom",
                "to_room": "backyard_pool",
                "title": "Primary Sanctuary → Zero-Edge Pool",
                "prompt": "Smooth steady gimbal forward camera walkthrough gliding out the sliding glass doors of the primary bedroom suite onto the resort-style backyard terrace and infinity pool at golden hour, architectural real estate tour, 3D spatial feel, no glitches."
            }
        ]
    },
    {
        "id": "sf-pacific-heights-view",
        "zip_code": "94115",
        "city": "San Francisco",
        "video_duration_label": "0:35",
        "preview_clip_url": "/api/cache/tour_38s_sf_pac_heights_94115.mp4",
        "full_tour_url": "/api/cache/tour_38s_sf_pac_heights_94115.mp4",
        "redfin_url": "https://www.redfin.com/CA/San-Francisco/2840-Broadway-94115/home/1928374",
        "title": "Pacific Heights Golden Gate View Mansion",
        "address": "2840 Broadway, San Francisco, CA 94115",
        "neighborhood": "Gold Coast • Pacific Heights, SF",
        "price": "$6,950,000",
        "price_num": 6950000,
        "beds": 4,
        "baths": 4.5,
        "sqft": 4180,
        "price_per_sqft": "$1,663",
        "lot_size": "3,850 sq ft",
        "year_built": 2024,
        "vibe_tags": ["Golden Gate Views", "Penthouse Sky Deck", "Elevator", "Wine Vault"],
        "oriane_keywords": ["san francisco", "luxury home", "penthouse", "house tour"],
        "oriane_hashtags": ["realestate", "luxuryrealestate", "sanfrancisco", "housetour"],
        "voiceover_script": (
            "Is this the ultimate San Francisco view home on Billionaires' Row? "
            "Behind this classic Pacific Heights facade sits 4,180 square feet of ultra-modern glass overlooking the Golden Gate Bridge. "
            "Glide from the sculptural salon into the cantilevered sky kitchen, and step out onto a panoramic bay-view rooftop terrace."
        ),
        "rooms": [
            {
                "id": "exterior",
                "name": "01 · Broadway Facade & Entry",
                "short_name": "Facade",
                "floorplan_xy": [18, 76],
                "image_url": "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Iconic Gold Coast curb presence with architectural bronze entry",
                "on_screen_hook": "INSIDE A $6.95M PACIFIC HEIGHTS MANSION 🌉",
                "spoken_beat": "Is this the ultimate San Francisco view home on Billionaires' Row?",
                "ambient_desc": "limestone portal, biometric entry & private 3-car gallery garage",
                "hotspots": [
                    {
                        "x": 50,
                        "y": 50,
                        "label": "Bronze & Limestone Entry Portal",
                        "detail": "Custom blackened steel and low-iron glass entry on SF's Gold Coast.",
                        "viral_note": "Oriane Signal: 'Billionaires Row' location hook drives 2.9x higher click-through."
                    }
                ]
            },
            {
                "id": "living",
                "name": "02 · Golden Gate View Salon",
                "short_name": "View Salon",
                "floorplan_xy": [42, 52],
                "image_url": "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Frameless bay windows with panoramic Alcatraz & Marin Headlands views",
                "on_screen_hook": "UNREAL BAY VIEWS FROM EVERY LEVEL ✨",
                "spoken_beat": "Behind the facade sits 4,180 sq ft overlooking the bay.",
                "ambient_desc": "Acoustic glass, travertine hearth & gallery art lighting",
                "hotspots": [
                    {
                        "x": 58,
                        "y": 44,
                        "label": "Frameless Structural View Glass",
                        "detail": "Unobstructed North-facing views spanning the Golden Gate to Alcatraz.",
                        "viral_note": "Oriane Signal: Panoramic window reveals keep 82% of viewers past 5 seconds."
                    }
                ]
            },
            {
                "id": "kitchen",
                "name": "03 · Cantilevered Sky Kitchen",
                "short_name": "Sky Kitchen",
                "floorplan_xy": [65, 40],
                "image_url": "https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Boffi Italian cabinetry, quartzite monolith island & espresso bar",
                "on_screen_hook": "ITALIAN BOFFI KITCHEN + WINE VAULT 🍷",
                "spoken_beat": "Glide from the sculptural salon into the cantilevered Boffi sky kitchen...",
                "ambient_desc": "Taj Mahal quartzite slab, integrated Gaggenau 400 series",
                "hotspots": [
                    {
                        "x": 45,
                        "y": 60,
                        "label": "Boffi Monolith Island",
                        "detail": "Imported Milanese millwork with cantilevered breakfast bar.",
                        "viral_note": "Luxury kitchen design details drive high bookmark rates."
                    }
                ]
            },
            {
                "id": "backyard_pool",
                "name": "04 · Sky Deck & Heated Spa Terrace",
                "short_name": "Sky Terrace",
                "floorplan_xy": [85, 62],
                "image_url": "https://images.unsplash.com/photo-1600585152220-90363fe7e115?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Private rooftop deck with glass windscreens & sunset fire table",
                "on_screen_hook": "RATE THIS SF VIEW 1-10 👇🔥",
                "spoken_beat": "...and step out onto a panoramic bay-view rooftop terrace.",
                "ambient_desc": "Ipe wood decking, wind-protected fire pit & outdoor sound system",
                "hotspots": [
                    {
                        "x": 62,
                        "y": 55,
                        "label": "Panoramic Sunset Fire Lounge",
                        "detail": "Plumbed gas fire table framed by low-iron glass wind walls.",
                        "viral_note": "Ending with a 1-10 rating CTA boosts comments by 3.7x."
                    }
                ]
            }
        ],
        "transitions": [
            {
                "index": 0,
                "from_room": "exterior",
                "to_room": "living",
                "title": "Broadway Facade → View Salon",
                "prompt": "Smooth steady gimbal forward camera walkthrough moving from the luxury San Francisco mansion exterior into the sunlit modern living salon, architectural real estate tour, 3D spatial feel, no glitches."
            },
            {
                "index": 1,
                "from_room": "living",
                "to_room": "kitchen",
                "title": "View Salon → Sky Kitchen",
                "prompt": "Smooth steady gimbal forward camera walkthrough gliding from the modern living salon into the Italian Boffi marble chef kitchen, architectural real estate tour, 3D spatial feel, no glitches."
            },
            {
                "index": 2,
                "from_room": "kitchen",
                "to_room": "backyard_pool",
                "title": "Sky Kitchen → Sunset Terrace",
                "prompt": "Smooth steady gimbal forward camera walkthrough gliding from the luxury chef kitchen out onto the modern terrace patio, architectural real estate tour, 3D spatial feel, no glitches."
            }
        ]
    },
    {
        "id": "marin-mill-valley-retreat",
        "zip_code": "94941",
        "city": "Mill Valley",
        "video_duration_label": "0:42",
        "preview_clip_url": "/api/cache/tour_34s_mill_valley_94941.mp4",
        "full_tour_url": "/api/cache/tour_34s_mill_valley_94941.mp4",
        "redfin_url": "https://www.redfin.com/CA/Mill-Valley/415-Lovell-Ave-94941/home/2839104",
        "title": "Mill Valley Redwood Canyon Glass Sanctuary",
        "address": "415 Lovell Ave, Mill Valley, CA 94941",
        "neighborhood": "Marin County • Mill Valley",
        "price": "$3,650,000",
        "price_num": 3650000,
        "beds": 4,
        "baths": 3.5,
        "sqft": 3490,
        "price_per_sqft": "$1,046",
        "lot_size": "18,200 sq ft",
        "year_built": 2024,
        "vibe_tags": ["Redwood Canopy", "Organic Modern", "Cedar Hinoki Spa", "Cantilevered Deck"],
        "oriane_keywords": ["modern home", "house tour", "luxury home", "architecture"],
        "oriane_hashtags": ["realestate", "housetour", "modernarchitecture", "dreamhome"],
        "voiceover_script": (
            "What if your living room floated inside a private redwood forest 20 minutes from San Francisco? "
            "Welcome to 415 Lovell in Mill Valley — 3,490 square feet of warm organic modern architecture "
            "gliding from the cantilevered redwood pavilion through the forest lounge and custom walnut kitchen "
            "into a treetop primary suite."
        ),
        "rooms": [
            {
                "id": "exterior",
                "name": "01 · Redwood Pavilion Arrival",
                "short_name": "Pavilion",
                "floorplan_xy": [18, 76],
                "image_url": "https://images.unsplash.com/photo-1580587771525-78b9dba3b914?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Cantilevered steel & warm cedar nestled under coastal redwoods",
                "on_screen_hook": "$3.65M REDWOOD GLASS SANCTUARY 🌲✨",
                "spoken_beat": "What if your living room floated inside a private redwood forest?",
                "ambient_desc": "Creekside acoustics, board-formed concrete & Japanese maples",
                "hotspots": [
                    {
                        "x": 45,
                        "y": 55,
                        "label": "Board-Formed Concrete & Cedar",
                        "detail": "Architectural pavilion cantilevered over a seasonal Marin creek.",
                        "viral_note": "Nature + modern glass homes have the highest share rate on TikTok."
                    }
                ]
            },
            {
                "id": "living",
                "name": "02 · Canopy Hearth Lounge",
                "short_name": "Canopy Lounge",
                "floorplan_xy": [42, 54],
                "image_url": "https://images.unsplash.com/photo-1600585154084-4e5fe7c39198?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Floor-to-ceiling forest views with suspended fireplace",
                "on_screen_hook": "FLOOR-TO-CEILING FOREST GLASS 🍃",
                "spoken_beat": "Welcome to 415 Lovell in Mill Valley — warm organic modern flow.",
                "ambient_desc": "Suspended Gyrofocus hearth & acoustic cedar ceiling",
                "hotspots": [
                    {
                        "x": 52,
                        "y": 48,
                        "label": "Suspended Wood-Burning Hearth",
                        "detail": "360-degree rotating steel fireplace anchored to the vaulted ceiling.",
                        "viral_note": "Unique architectural focal points drive comment curiosity."
                    }
                ]
            },
            {
                "id": "kitchen",
                "name": "03 · Organic Walnut & Soapstone Kitchen",
                "short_name": "Forest Kitchen",
                "floorplan_xy": [64, 42],
                "image_url": "https://images.unsplash.com/photo-1556911220-bff31c812dba?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Hand-milled American walnut cabinetry with honed soapstone island",
                "on_screen_hook": "ORGANIC WALNUT CHEF KITCHEN 🌿",
                "spoken_beat": "Glide into the custom walnut and soapstone kitchen framed by redwoods.",
                "ambient_desc": "Integrated Gaggenau induction, herb skylight & canyon views",
                "hotspots": [
                    {
                        "x": 48,
                        "y": 60,
                        "label": "Honed Soapstone & Walnut Island",
                        "detail": "Sustainably harvested Marin walnut millwork with cantilevered bar.",
                        "viral_note": "Warm wood kitchens generate 2.7x higher save rates than all-white kitchens."
                    }
                ]
            },
            {
                "id": "primary_bedroom",
                "name": "04 · Treetop Primary Suite",
                "short_name": "Treetop Suite",
                "floorplan_xy": [84, 32],
                "image_url": "https://images.unsplash.com/photo-1616594039964-ae9021a400a0?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Wake up in the redwood canopy with a private Hinoki cedar soaking tub",
                "on_screen_hook": "WAKE UP IN THE REDWOOD CANOPY 🛌🌲",
                "spoken_beat": "Every room opens directly onto the tranquil canyon deck.",
                "ambient_desc": "Private meditation deck & Japanese Hinoki spa bath",
                "hotspots": [
                    {
                        "x": 60,
                        "y": 52,
                        "label": "Corner Treetop Glass",
                        "detail": "Zero-post corner window overlooking 100-year-old coastal redwoods.",
                        "viral_note": "Bedroom view reveals consistently outperform standard walk-ins."
                    }
                ]
            }
        ],
        "transitions": [
            {
                "index": 0,
                "from_room": "exterior",
                "to_room": "living",
                "title": "Redwood Pavilion → Canopy Lounge",
                "prompt": "Slow serene architectural Steadicam walkthrough moving smoothly from the modern redwood forest glass house exterior into the warm wood-paneled canopy living room, natural daylight, 3D spatial feel, no glitches."
            },
            {
                "index": 1,
                "from_room": "living",
                "to_room": "kitchen",
                "title": "Canopy Lounge → Forest Kitchen",
                "prompt": "Slow serene architectural Steadicam walkthrough gliding smoothly from the warm forest living lounge into the organic walnut and stone chef kitchen, natural daylight, 3D spatial feel, no glitches."
            },
            {
                "index": 2,
                "from_room": "kitchen",
                "to_room": "primary_bedroom",
                "title": "Forest Kitchen → Treetop Primary Suite",
                "prompt": "Slow serene architectural Steadicam walkthrough moving smoothly from the organic modern kitchen down the cedar gallery into the serene treetop primary bedroom suite, natural daylight, 3D spatial feel, no glitches."
            }
        ]
    },
    {
        "id": "los-altos-hills-estate",
        "zip_code": "94022",
        "city": "Los Altos Hills",
        "video_duration_label": "0:45",
        "preview_clip_url": "/api/cache/tour_40s_los_altos_hills_94022.mp4",
        "full_tour_url": "/api/cache/tour_40s_los_altos_hills_94022.mp4",
        "redfin_url": "https://www.redfin.com/CA/Los-Altos-Hills/26800-Moody-Rd-94022/home/3910482",
        "title": "Los Altos Hills Zero-Edge Resort Compound",
        "address": "26800 Moody Rd, Los Altos Hills, CA 94022",
        "neighborhood": "Los Altos Hills • Silicon Valley",
        "price": "$8,450,000",
        "price_num": 8450000,
        "beds": 6,
        "baths": 7.0,
        "sqft": 6480,
        "price_per_sqft": "$1,304",
        "lot_size": "1.25 Acres",
        "year_built": 2025,
        "vibe_tags": ["1.25-Acre Resort", "Zero-Edge Pool", "Vineyard Views", "Guest Pavilion"],
        "oriane_keywords": ["luxury home", "pool", "mansion tour", "real estate"],
        "oriane_hashtags": ["realestate", "luxuryrealestate", "housetour", "mansion"],
        "voiceover_script": (
            "Welcome to 26800 Moody Road in Los Altos Hills — an 8.45 million dollar, 1.25-acre private Silicon Valley resort compound. "
            "Step through the limestone motor court into the soaring ridge-view great room, glide through the primary glass sanctuary, "
            "and walk straight out onto a 65-foot heated zero-edge infinity pool overlooking the canyon."
        ),
        "rooms": [
            {
                "id": "exterior",
                "name": "01 · Limestone Motor Court & Pavilion",
                "short_name": "Estate Entry",
                "floorplan_xy": [18, 74],
                "image_url": "https://images.unsplash.com/photo-1613490493576-7fde63acd811?auto=format&fit=crop&w=1280&q=85",
                "vibe": "1.25-acre gated ridge compound with floating travertine water court",
                "on_screen_hook": "INSIDE AN $8.45M LOS ALTOS HILLS COMPOUND 🌊",
                "spoken_beat": "Welcome to 26800 Moody Road — a 1.25-acre private Silicon Valley resort.",
                "ambient_desc": "Gated olive tree drive, reflection pond & architectural bronze roofline",
                "hotspots": [
                    {
                        "x": 50,
                        "y": 52,
                        "label": "Floating Travertine Water Court",
                        "detail": "Custom bronze pivot entry flanked by infinity reflection basins.",
                        "viral_note": "Oriane Signal: Resort compound exterior hooks drive 3.5x higher completion."
                    }
                ]
            },
            {
                "id": "living",
                "name": "02 · Canyon Ridge Great Room",
                "short_name": "Ridge Salon",
                "floorplan_xy": [42, 54],
                "image_url": "https://images.unsplash.com/photo-1600607687920-4e2a09cf159d?auto=format&fit=crop&w=1280&q=85",
                "vibe": "16-foot acoustic ceilings with 40-foot motorized glass wall",
                "on_screen_hook": "6,480 SQ FT OF HILLTOP GLASS ✨",
                "spoken_beat": "Step into the soaring ridge-view great room with 40-foot disappearing glass.",
                "ambient_desc": "Bookmatched travertine hearth, wet bar & private wine room",
                "hotspots": [
                    {
                        "x": 55,
                        "y": 48,
                        "label": "40-Ft Motorized Canyon Glass",
                        "detail": "Unobstructed Silicon Valley and Santa Cruz Mountain ridge views.",
                        "viral_note": "Wide indoor-outdoor salon reveals retain 84% of viewers."
                    }
                ]
            },
            {
                "id": "primary_bedroom",
                "name": "03 · Primary Glass Sanctuary",
                "short_name": "Primary Suite",
                "floorplan_xy": [66, 40],
                "image_url": "https://images.unsplash.com/photo-1595526114035-0d45ed16cfbf?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Retractable corner glass walls opening directly to the limestone terrace",
                "on_screen_hook": "PRIMARY SUITE WITH VINEYARD VIEWS 🍷🛌",
                "spoken_beat": "Glide through the primary glass sanctuary with dual spa baths...",
                "ambient_desc": "Acoustic oak ceilings, automated shade pocket & private spa terrace",
                "hotspots": [
                    {
                        "x": 54,
                        "y": 50,
                        "label": "Zero-Threshold Pool Sliders",
                        "detail": "Motorized glass panels vanish completely to merge bedroom and pool deck.",
                        "viral_note": "Oriane Signal: Indoor-to-pool glide transitions drive 3.4x higher save rate."
                    }
                ]
            },
            {
                "id": "backyard_pool",
                "name": "04 · 65-Ft Zero-Edge Infinity Pool & Cabana",
                "short_name": "Infinity Pool",
                "floorplan_xy": [86, 62],
                "image_url": "https://images.unsplash.com/photo-1576013551627-0cc20b96c2a7?auto=format&fit=crop&w=1280&q=85",
                "vibe": "65-foot infinity edge, sunken fire lounge & private vineyard backdrop",
                "on_screen_hook": "WAIT FOR THIS SUNSET POOL REVEAL 🔥",
                "spoken_beat": "...and step straight out onto a 65-foot zero-edge infinity pool overlooking the hills.",
                "ambient_desc": "Heated limestone deck, outdoor kitchen & sunset fire pit",
                "hotspots": [
                    {
                        "x": 50,
                        "y": 65,
                        "label": "65-Ft Zero-Edge Infinity Pool",
                        "detail": "Saltwater infinity lap pool with integrated spa and Baja shelf.",
                        "viral_note": "Oriane Signal: Golden hour water reflections boost watch-through to 89%."
                    }
                ]
            }
        ],
        "transitions": [
            {
                "index": 0,
                "from_room": "exterior",
                "to_room": "living",
                "title": "Motor Court → Canyon Ridge Salon",
                "prompt": "Slow serene architectural Steadicam walkthrough moving smoothly from the luxury hilltop estate exterior courtyard through glass doors into the grand modern living room, golden hour lighting, 3D spatial feel, no glitches."
            },
            {
                "index": 1,
                "from_room": "living",
                "to_room": "primary_bedroom",
                "title": "Ridge Salon → Primary Glass Sanctuary",
                "prompt": "Slow serene architectural Steadicam walkthrough gliding smoothly from the grand modern living room into the luxury primary bedroom suite with warm lighting, architectural real estate tour, 3D spatial feel, no glitches."
            },
            {
                "index": 2,
                "from_room": "primary_bedroom",
                "to_room": "backyard_pool",
                "title": "Primary Suite → 65-Ft Infinity Pool",
                "prompt": "Slow serene architectural Steadicam walkthrough gliding out the glass doors of the luxury bedroom suite onto the resort infinity pool terrace overlooking the hills at sunset, 3D spatial feel, no glitches."
            }
        ]
    },
    {
        "id": "palo-alto-cowper-modern",
        "zip_code": "94301",
        "city": "Palo Alto",
        "video_duration_label": "0:41",
        "preview_clip_url": "/api/cache/tour_35s_cowper_palo_alto_94301.mp4",
        "full_tour_url": "/api/cache/tour_35s_cowper_palo_alto_94301.mp4",
        "redfin_url": "https://www.redfin.com/CA/Palo-Alto/530-Cowper-St-94301/home/1490812",
        "title": "Professorville Warm Oak & Marble Villa",
        "address": "530 Cowper St, Palo Alto, CA 94301",
        "neighborhood": "Professorville • Palo Alto",
        "price": "$5,250,000",
        "price_num": 5250000,
        "beds": 5,
        "baths": 5.0,
        "sqft": 4380,
        "price_per_sqft": "$1,198",
        "lot_size": "9,200 sq ft",
        "year_built": 2025,
        "vibe_tags": ["Calacatta Gold Kitchen", "European Oak", "Courtyard Atrium", "Wine Room"],
        "oriane_keywords": ["luxury home", "kitchen tour", "house tour", "modern home"],
        "oriane_hashtags": ["realestate", "housetour", "luxurykitchen", "paloalto"],
        "voiceover_script": (
            "Step inside 530 Cowper Street in historic Professorville, Palo Alto — where a gated architectural courtyard "
            "leads into a sunlit double-height European oak great room, a 14-foot bookmatched Calacatta chef kitchen, "
            "and a tranquil private courtyard lap pool."
        ),
        "rooms": [
            {
                "id": "exterior",
                "name": "01 · Professorville Architectural Facade",
                "short_name": "Courtyard Entry",
                "floorplan_xy": [18, 74],
                "image_url": "https://images.unsplash.com/photo-1600047509807-ba8f99d2cdde?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Warm limestone, vertical cedar louvers & olive tree entry court",
                "on_screen_hook": "$5.25M PROFESSORVILLE PALO ALTO VILLA 🏡✨",
                "spoken_beat": "Step inside 530 Cowper Street in historic Professorville, Palo Alto.",
                "ambient_desc": "Architectural bronze gate, olive courtyard & concealed garage",
                "hotspots": [
                    {
                        "x": 48,
                        "y": 52,
                        "label": "Cedar Louver & Limestone Facade",
                        "detail": "Warm contemporary architecture just three blocks from downtown Palo Alto.",
                        "viral_note": "Curb-to-interior walk-ins boost first-3-second hook retention."
                    }
                ]
            },
            {
                "id": "living",
                "name": "02 · Double-Height Oak Great Room",
                "short_name": "Great Room",
                "floorplan_xy": [42, 56],
                "image_url": "https://images.unsplash.com/photo-1600566752355-35792bedcfea?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Sunlit European oak planks & acoustic plaster ceilings",
                "on_screen_hook": "SUNLIT EUROPEAN OAK GREAT ROOM ✨",
                "spoken_beat": "Notice the sunlit double-height European oak great room...",
                "ambient_desc": "Floor-to-ceiling Fleetwood sliders & linear limestone hearth",
                "hotspots": [
                    {
                        "x": 52,
                        "y": 54,
                        "label": "Wide-Plank European White Oak",
                        "detail": "9-inch custom-finished oak planks over hydronic radiant heating.",
                        "viral_note": "Oriane Signal: Warm oak + sunlit sightlines boost completion rate by +39%."
                    }
                ]
            },
            {
                "id": "kitchen",
                "name": "03 · Bookmatched Calacatta Chef's Kitchen",
                "short_name": "Chef's Kitchen",
                "floorplan_xy": [66, 42],
                "image_url": "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?auto=format&fit=crop&w=1280&q=85",
                "vibe": "14-ft waterfall island with Gaggenau & Miele integrated suite",
                "on_screen_hook": "WAIT FOR THIS 14-FT MARBLE ISLAND 🔥",
                "spoken_beat": "...gliding straight into a 14-foot bookmatched Calacatta chef kitchen...",
                "ambient_desc": "Concealed scullery, induction surface & 150-bottle wine wall",
                "hotspots": [
                    {
                        "x": 46,
                        "y": 64,
                        "label": "14-Ft Waterfall Calacatta Island",
                        "detail": "Bookmatched Italian marble slab with integrated seating for six.",
                        "viral_note": "Oriane Signal: Kitchen island glide transitions rank #1 in saves."
                    }
                ]
            },
            {
                "id": "backyard_pool",
                "name": "04 · Private Courtyard Atrium & Lounge",
                "short_name": "Atrium Lounge",
                "floorplan_xy": [86, 60],
                "image_url": "https://images.unsplash.com/photo-1600607688969-a5bfcd646154?auto=format&fit=crop&w=1280&q=85",
                "vibe": "Zero-threshold glass atrium opening to a private limestone garden lounge",
                "on_screen_hook": "INDOOR-OUTDOOR CALIFORNIA ATRIUM 🌿👇",
                "spoken_beat": "...and opening onto a tranquil private limestone courtyard lounge.",
                "ambient_desc": "Heated pergola terrace, outdoor fireplace & mature bamboo privacy wall",
                "hotspots": [
                    {
                        "x": 54,
                        "y": 58,
                        "label": "Heated Limestone Atrium Terrace",
                        "detail": "Year-round outdoor living room with flush Infratech heaters.",
                        "viral_note": "Private courtyard closers drive high comment engagement."
                    }
                ]
            }
        ],
        "transitions": [
            {
                "index": 0,
                "from_room": "exterior",
                "to_room": "living",
                "title": "Professorville Entry → Oak Great Room",
                "prompt": "Slow serene architectural Steadicam walkthrough moving smoothly from the modern Palo Alto villa exterior courtyard into the sunlit oak living room, natural daylight, 3D spatial feel, no glitches."
            },
            {
                "index": 1,
                "from_room": "living",
                "to_room": "kitchen",
                "title": "Oak Great Room → Calacatta Kitchen",
                "prompt": "Slow serene architectural Steadicam walkthrough gliding smoothly from the sunlit modern living room straight into the open-concept marble chef kitchen with island, natural daylight, 3D spatial feel, no glitches."
            },
            {
                "index": 2,
                "from_room": "kitchen",
                "to_room": "backyard_pool",
                "title": "Calacatta Kitchen → Courtyard Atrium",
                "prompt": "Slow serene architectural Steadicam walkthrough gliding smoothly from the luxury kitchen out to the sunlit indoor-outdoor courtyard garden lounge, natural daylight, 3D spatial feel, no glitches."
            }
        ]
    }
]


app = FastAPI(title="EstateFlow AI — Redfin-to-Viral 3D Walkthrough Studio")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RedfinParseRequest(BaseModel):
    url: str


class OrianeAnalyzeRequest(BaseModel):
    listing_id: Optional[str] = None
    keywords: Optional[List[str]] = None
    hashtags: Optional[List[str]] = None


class GeminiPlanRequest(BaseModel):
    listing_id: str
    oriane_summary: Optional[Dict[str, Any]] = None
    custom_listing: Optional[Dict[str, Any]] = None


class GeminiGenerateSegmentRequest(BaseModel):
    listing_id: str
    transition_index: int
    from_room: str
    to_room: str
    first_frame_url: str
    last_frame_url: str
    prompt: str
    model: Literal["gemini-omni-1.2-flash", "gemini-omni-1.1-flash"] = gemini.VIDEO_MODEL
    duration: int = Field(default=6, ge=3, le=10)


class GeminiVoiceoverRequest(BaseModel):
    listing_id: str
    text: str
    voice_id: str = "Kore"


def get_listing_by_id(listing_id: str) -> Dict[str, Any]:
    for item in CURATED_LISTINGS:
        if item["id"] == listing_id:
            return item
    raise HTTPException(404, "Listing not found")


def enrich_listing_with_cache(listing: Dict[str, Any]) -> Dict[str, Any]:
    idx = load_cache_index()
    enriched = json.loads(json.dumps(listing))
    lid = enriched["id"]

    # Historical demo imagery remains cached; source-backed homes bypass this path.
    for room in enriched.get("rooms", []):
        rid = room["id"]
        generated_imgs = sorted(
            [p for p in CACHE_DIR.glob(f"img_{lid}_{rid}_*.jpg") if p.is_file() and p.stat().st_size > 10000],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        if generated_imgs:
            room["image_url"] = f"/api/cache/{generated_imgs[0].name}"

    for t in enriched.get("transitions", []):
        t_idx = t["index"]
        seg_key = f"{lid}_seg{t_idx}"
        seg_info = idx.get("segments", {}).get(seg_key)
        if seg_info and seg_info.get("provider") == "gemini" and seg_info.get("status") != "ready":
            t.update(status=seg_info["status"], video_url=None, model=seg_info.get("model"), provider="gemini", interaction_id=seg_info.get("interaction_id"))
            continue
        generated_clips = sorted(
            [
                p for p in CACHE_DIR.glob(f"{lid}_seg{t_idx}_*.mp4")
                if not p.name.endswith("_glide.mp4") and not p.name.startswith("slow_") and p.stat().st_size > 20000
            ],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        if generated_clips:
            best_clip = generated_clips[0]
            metadata = seg_info if seg_info and seg_info.get("local_file") == best_clip.name else {}
            slow_clip = CACHE_DIR / f"slow_{best_clip.name}"
            served_file = slow_clip.name if (slow_clip.exists() and slow_clip.stat().st_size > 20000) else best_clip.name
            t["status"] = "ready"
            t["video_url"] = f"/api/cache/{served_file}"
            t["model"] = metadata.get("model", "historical-unknown")
            t["provider"] = metadata.get("provider", "gmi-cloud")
            t["interaction_id"] = metadata.get("interaction_id")
            t["request_id"] = best_clip.stem.split("_")[-1]
        elif seg_info and seg_info.get("local_file") and (CACHE_DIR / seg_info["local_file"]).exists():
            t["status"] = "ready"
            t["video_url"] = f"/api/cache/{seg_info['local_file']}"
            t["model"] = seg_info.get("model", "historical-unknown")
            t["provider"] = seg_info.get("provider", "gmi-cloud")
            t["request_id"] = seg_info.get("request_id")
        else:
            glide_file = f"{lid}_seg{t_idx}_glide.mp4"
            if (CACHE_DIR / glide_file).exists():
                t["status"] = "ready"
                t["video_url"] = f"/api/cache/{glide_file}"
                t["model"] = "local-photo-glide"
                t["provider"] = "local"
                t["media_kind"] = "photo_sequence"
            else:
                t["status"] = "not_generated"
                t["video_url"] = None

    vo_info = idx.get("voiceovers", {}).get(lid)
    if vo_info and vo_info.get("local_file") and (CACHE_DIR / vo_info["local_file"]).exists():
        enriched["voiceover_status"] = "ready"
        enriched["voiceover_url"] = f"/api/cache/{vo_info['local_file']}"
    elif vo_info and vo_info.get("interaction_id"):
        enriched["voiceover_status"] = vo_info.get("status", "processing")
        enriched["voiceover_interaction_id"] = vo_info["interaction_id"]
    else:
        enriched["voiceover_status"] = "not_generated"
        enriched["voiceover_url"] = None

    enriched["social"] = get_or_init_listing_social(lid)
    return enriched


@app.get("/api/listings")
async def list_curated_listings():
    # Reading cached listings never submits or polls paid API jobs.
    return {"listings": [enrich_listing_with_cache(item) for item in CURATED_LISTINGS]}


@app.post("/api/redfin/parse")
async def parse_redfin_url(req: RedfinParseRequest):
    url = req.url.strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ("www.redfin.com", "redfin.com"):
        raise HTTPException(422, "Use an https://www.redfin.com listing URL.")
    manifest_path = DATA_DIR / "94404" / "manifest.json"
    if manifest_path.exists():
        for listing in json.loads(manifest_path.read_text())["listings"]:
            if parsed.path.rstrip("/") == urlparse(listing["redfin_url"]).path.rstrip("/"):
                return {"viewer_url": f"/94404#{listing['id']}", "source": "listing_originals"}
    for item in CURATED_LISTINGS:
        if parsed.path.rstrip("/") == urlparse(item["redfin_url"]).path.rstrip("/"):
            return {"listing": enrich_listing_with_cache(item), "source": "synthetic_demo"}
    raise HTTPException(422, "This listing has no verified source manifest. Import original photos and a floor plan first; no substitute property will be generated.")


@app.post("/api/oriane/analyze")
async def analyze_with_oriane(req: OrianeAnalyzeRequest):
    listing = get_listing_by_id(req.listing_id or "palo-alto-glass-villa")
    keywords = req.keywords or listing.get("oriane_keywords", ["real estate", "house tour", "luxury home"])
    hashtags = req.hashtags or listing.get("oriane_hashtags", ["realestate", "housetour", "luxuryrealestate"])

    cache_key = hashlib.md5(json.dumps({"k": keywords, "h": hashtags}, sort_keys=True).encode()).hexdigest()[:12]
    idx = load_cache_index()
    if cache_key in idx.get("oriane", {}):
        return idx["oriane"][cache_key]

    payload = {
        "name": "real_estate_viral_intelligence",
        "operator": "or",
        "filters": {
            "caption": {
                "includesFuzzy": {"values": keywords, "operator": "or"},
                "operator": "and",
            },
            "hashtags": {
                "includesExactly": {"values": [h.lstrip("#") for h in hashtags], "operator": "or"},
                "operator": "and",
            },
        },
    }

    headers = {
        "Authorization": f"Bearer {load_api_key('ORIANE_API_KEY')}",
        "Content-Type": "application/json",
    }
    url = f"{ORIANE_BASE_URL}/rest/contents/search?sort=viewsCount:desc&offset=0&limit=8&projection=full"

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code not in (200, 206):
            raise HTTPException(status_code=resp.status_code, detail=f"Oriane API error: {resp.text}")
        raw = resp.json()

    data_block = raw.get("data", {})
    aggregations = data_block.get("aggregations", {})
    results = data_block.get("results", [])

    videos = []
    extracted_hooks = []
    extracted_on_screen = []
    for item in results:
        media_list = item.get("media") or []
        first_media = media_list[0] if media_list else {}
        transcript = first_media.get("transcript") or ""
        on_screen = first_media.get("onScreenText") or []
        if transcript and len(extracted_hooks) < 4:
            first_sentence = " ".join(transcript.strip().split()[:22])
            extracted_hooks.append(first_sentence + ("..." if len(transcript) > len(first_sentence) else ""))
        for ost in on_screen[:6]:
            if isinstance(ost, str) and len(ost.strip()) > 3 and ost.strip() not in extracted_on_screen:
                extracted_on_screen.append(ost.strip())

        videos.append(
            {
                "id": item.get("id"),
                "platform": item.get("platform"),
                "handle": item.get("profileHandle"),
                "display_name": item.get("profileDisplayName"),
                "followers": item.get("profileFollowersCount"),
                "views": item.get("viewsCount"),
                "likes": item.get("likesCount"),
                "comments": item.get("commentsCount"),
                " interactions": item.get("interactionsCount"),
                "engagement_rate_views": round(item.get("engagementRatePerViews") or 0, 2),
                "views_rate_followers": round(item.get("viewsRatePerFollowers") or 0, 1),
                "thumbnail_url": item.get("thumbnailMediaUrl"),
                "profile_pic_url": item.get("profilePictureUrl"),
                "caption": (item.get("caption") or "")[:240],
                "hashtags": (item.get("hashtags") or [])[:8],
                "audio_title": item.get("audioTitle"),
                "audio_author": item.get("audioAuthor"),
                "duration": first_media.get("duration"),
                "transcript": transcript[:500] if transcript else None,
                "on_screen_text": on_screen[:10],
            }
        )

    result_payload = {
        "status": "ok",
        "http_status": resp.status_code,
        "aggregations": {
            "total_views": int(aggregations.get("totalViewsCount") or 0),
            "avg_views": int(aggregations.get("averageViewsCount") or 0),
            "total_likes": int(aggregations.get("totalLikesCount") or 0),
            "total_interactions": int(aggregations.get("totalInteractionsCount") or 0),
            "avg_engagement_rate": round(aggregations.get("averageEngagementRatePerViews") or 0, 2),
            "avg_outlier_ratio": round(aggregations.get("averageViewsRatePerFollowers") or 0, 1),
        },
        "top_videos": videos,
        "viral_playbook": {
            "winning_spoken_hooks": extracted_hooks
            or [
                "Excuse me, is this your house? Can I get a tour?",
                "What does $4.85M actually get you in Palo Alto right now?",
                "Step inside a glass sanctuary where every wall disappears...",
            ],
            "on_screen_text_pills": extracted_on_screen[:12]
            or [
                "Is this your HOUSE?",
                "THE DINING AREA FIRST",
                "NO CLOSED KITCHEN?",
                "Let me SHOW you my master bedroom",
                "STEP INTO A PORTAL",
            ],
            "room_pacing_formula": [
                "0.0s–2.5s: Exterior Curb / Price Anchor Hook (stops scroll with price + neighborhood)",
                "2.5s–6.5s: Continuous Gimbal Glide into Great Room (proves spatial scale, zero jump-cuts)",
                "6.5s–10.5s: Chef's Kitchen Island Close-Up (highest rewatch/save density in Oriane data)",
                "10.5s–15.0s: Primary Suite → Pool Terrace Climax + Comment Question CTA",
            ],
        },
    }

    idx.setdefault("oriane", {})[cache_key] = result_payload
    save_cache_index(idx)
    return result_payload


# =====================================================================
# Direct Gemini generation is explicit, finite, and resumable by interaction ID.
async def call_gemini(method: str, *args):
    def call():
        with httpx.Client(timeout=90.0) as transport:
            provider = gemini.GeminiClient(gemini.load_project_key(), client=transport)
            return getattr(provider, method)(*args)
    try:
        return await asyncio.to_thread(call)
    except gemini.GeminiError as error:
        raise HTTPException(error.status_code or 503, str(error)) from None


def job_response(record, key):
    result = {field: record[field] for field in ("status", "provider", "model", "interaction_id", "plan", "error", "failure_code") if field in record}
    result["seg_key"] = key
    if record.get("local_file"):
        if (CACHE_DIR / record["local_file"]).is_file():
            field = "audio_url" if key.startswith("vo_") else "video_url"
            result[field] = f"/api/cache/{record['local_file']}"
        elif record.get("status") == "ready":
            result.update(status="missing_media", error="The cached output is missing; no automatic regeneration was started.")
    return result


def finish_gemini_job(record, interaction, key):
    try:
        decode_gemini_job(record, interaction, key)
    except gemini.GeminiError as error:
        record.update(status="failed", error=str(error))


def decode_gemini_job(record, interaction, key):
    status = interaction.get("status", "in_progress")
    record["status"] = "processing" if status in ("queued", "in_progress") else status
    if status != "completed":
        if status not in ("queued", "in_progress"):
            if status == "failed":
                record["failure_code"], record["error"] = gemini.failure_details(interaction)
            else:
                record["error"] = f"Gemini interaction ended with {status}; no automatic resubmission."
        return
    if key.startswith("plan_"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", gemini.output_text(interaction).strip())
        try:
            plan = json.loads(text)
            if not isinstance(plan, dict):
                raise ValueError()
            record["plan"] = plan
        except (ValueError, TypeError):
            record.update(status="failed", error="Gemini returned no valid tour-plan object.")
            return
    else:
        if key.startswith("vo_"):
            audio = gemini.output_audio_bytes(interaction)
            content, mime = audio if audio else (None, None)
            extension = {"audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3"}.get(mime)
        else:
            content, extension = gemini.output_video_bytes(interaction), ".mp4"
        if not content or not extension:
            record.update(status="failed", error="Gemini completed without the requested playable media.")
            return
        token = hashlib.sha256(record["interaction_id"].encode()).hexdigest()[:12]
        filename = f"{key}_{token}{extension}"
        (CACHE_DIR / filename).write_bytes(content)
        record.update(local_file=filename, sha256=hashlib.sha256(content).hexdigest())
    record["status"] = "ready"


async def submit_gemini_job(index, section, item_key, key, body, metadata):
    record = {**metadata, "provider": "gemini", "status": "submitting", "created_at": int(time.time())}
    index.setdefault(section, {})[item_key] = record
    save_cache_index(index)
    try:
        interaction = await call_gemini("create", body)
    except HTTPException:
        record.update(status="submission_uncertain", error="Submission did not return an interaction ID. Reconcile before resubmitting.")
        save_cache_index(index)
        raise
    interaction_id = interaction.get("id")
    if not isinstance(interaction_id, str) or not interaction_id:
        record.update(status="submission_uncertain", error="Submission returned no interaction ID. Reconcile before resubmitting.")
        save_cache_index(index)
        raise HTTPException(502, record["error"])
    record["interaction_id"] = interaction_id
    save_cache_index(index)
    finish_gemini_job(record, interaction, key)
    save_cache_index(index)
    return job_response(record, key)


def existing_job(index, section, item_key, key):
    record = index.get(section, {}).get(item_key)
    if not record:
        return None
    if record.get("local_file") and (CACHE_DIR / record["local_file"]).is_file():
        return {**job_response(record, key), "status": "ready", "cached": True}
    if key.startswith("plan_") and record.get("plan"):
        return {**job_response(record, key), "status": "ready", "cached": True}
    if record.get("provider") == "gemini":
        return job_response(record, key)
    return None


async def input_image(url, listing, room_id):
    room = next((room for room in listing.get("rooms", []) if room["id"] == room_id), None)
    if not room:
        raise HTTPException(422, "The transition must use this listing's room images.")
    if url.startswith("/api/cache/"):
        filename = url.removeprefix("/api/cache/")
        if Path(filename).name != filename or not filename.startswith(f"img_{listing['id']}_{room_id}_"):
            raise HTTPException(422, "The cached image must belong to this listing and room.")
        path = CACHE_DIR / filename
        if not path.is_file():
            raise HTTPException(404, "Cached input image is missing.")
        return path.read_bytes()
    if url != room["image_url"] or urlparse(url).scheme != "https":
        raise HTTPException(422, "Use this listing's existing source image URL.")
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        raise HTTPException(422, "The source image could not be loaded.") from None
    if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
        raise HTTPException(422, "The source image could not be loaded.")
    return response.content


@app.post("/api/gemini/plan-tour")
async def plan_tour_with_gemini(req: GeminiPlanRequest):
    listing = req.custom_listing or get_listing_by_id(req.listing_id)
    if req.custom_listing and listing.get("id") != req.listing_id:
        raise HTTPException(422, "Custom listing identity must match listing_id.")
    body = {
        "model": gemini.TEXT_MODEL, "background": True, "store": True,
        "input": json.dumps({"property": listing, "reference_hooks": req.oriane_summary or {}}),
        "system_instruction": "Create a concise property tour plan as a JSON object with hook_strategy, voiceover_script, room_overlays and compound_caption. Preserve supplied property facts. Do not invent scores, engagement predictions, dimensions or architectural features. Mark unknown information explicitly.",
    }
    async with generation_lock:
        index = load_cache_index()
        key = f"plan_{req.listing_id}"
        cached = existing_job(index, "plans", req.listing_id, key)
        if cached:
            return cached
        return await submit_gemini_job(index, "plans", req.listing_id, key, body, {"model": gemini.TEXT_MODEL})


@app.post("/api/gemini/generate-segment")
async def generate_walkthrough_segment(req: GeminiGenerateSegmentRequest):
    listing = get_listing_by_id(req.listing_id)
    transition = next((item for item in listing.get("transitions", []) if item["index"] == req.transition_index), None)
    if not transition or (req.from_room, req.to_room) != (transition["from_room"], transition["to_room"]):
        raise HTTPException(422, "Use an existing transition for this listing.")
    key = f"{req.listing_id}_seg{req.transition_index}"
    async with generation_lock:
        index = load_cache_index()
        cached = existing_job(index, "segments", key, key)
        if cached:
            return cached
        first = await input_image(req.first_frame_url, listing, req.from_room)
        last = await input_image(req.last_frame_url, listing, req.to_room)
        try:
            body = gemini.video_request(req.prompt, first, last, model=req.model, duration=req.duration)
        except gemini.GeminiError as error:
            raise HTTPException(422, str(error)) from None
        body.update(background=True, store=True)
        return await submit_gemini_job(index, "segments", key, key, body, {
            "model": req.model, "from_room": req.from_room, "to_room": req.to_room,
            "source_sha256": [hashlib.sha256(image).hexdigest() for image in (first, last)],
        })


@app.post("/api/gemini/generate-voiceover")
async def generate_voiceover(req: GeminiVoiceoverRequest):
    get_listing_by_id(req.listing_id)
    body = {
        "model": gemini.TTS_MODEL, "background": True, "store": True,
        "input": [{"type": "user_input", "content": [{"type": "text", "text": req.text}]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": req.voice_id}]},
    }
    async with generation_lock:
        index = load_cache_index()
        key = f"vo_{req.listing_id}"
        cached = existing_job(index, "voiceovers", req.listing_id, key)
        if cached:
            return cached
        return await submit_gemini_job(index, "voiceovers", req.listing_id, key, body, {"model": gemini.TTS_MODEL})


@app.get("/api/gemini/poll/{key}")
async def poll_gemini_job(key: str):
    async with generation_lock:
        index = load_cache_index()
        if key.startswith("vo_"):
            section, item_key = "voiceovers", key[3:]
        elif key.startswith("plan_"):
            section, item_key = "plans", key[5:]
        else:
            section, item_key = "segments", key
        record = index.get(section, {}).get(item_key)
        if not record:
            raise HTTPException(404, "Generation job not found")
        cached = existing_job(index, section, item_key, key)
        if record.get("status") == "ready" and cached:
            return cached
        if record.get("provider") != "gemini" or not record.get("interaction_id"):
            raise HTTPException(409, "Historical or uncertain jobs cannot be polled through Gemini. Existing cached media remains available.")
        if record.get("status") not in ("processing", "queued", "in_progress"):
            return job_response(record, key)
        interaction = await call_gemini("get", record["interaction_id"])
        finish_gemini_job(record, interaction, key)
        save_cache_index(index)
        return job_response(record, key)


# AMAZON x YOUTUBE HYBRID RANKING & LIVE OPEN HOUSE SOCIAL ENGINE
# =====================================================================
SOCIAL_STORE_PATH = DATA_DIR / "social_store.json"

DEFAULT_SOCIAL_DATA: Dict[str, Dict[str, Any]] = {
    "palo-alto-glass-villa": {
        "thumbs_up": 1420,
        "thumbs_down": 28,
        "open_house_live_count": 34,
        "amazon_stars": 4.9,
        "verified_checkins": 86,
        "star_breakdown": {"5": 88, "4": 9, "3": 2, "2": 1, "1": 0},
        "attributes": {
            "Matches AI Walkthrough": 4.9,
            "Natural Light & Warmth": 5.0,
            "Floorplan Spatial Flow": 4.9,
            "Price-to-Value (94301)": 4.7,
        },
        "visitor_media": [
            {
                "id": "m1",
                "author": "@sarah_chen_vc",
                "badge": "✓ Verified at Open House · 4m ago",
                "room": "03 · Chef's Kitchen",
                "media_type": "video",
                "media_url": "/api/cache/palo-alto-glass-villa_seg1_97dbc81a.mp4",
                "caption": "Standing in the kitchen right now — the 14ft Calacatta island lighting is 100% real!",
                "helpful_count": 48,
            },
            {
                "id": "m2",
                "author": "@marcus_arch",
                "badge": "✓ Verified at Open House · 11m ago",
                "room": "05 · Zero-Edge Pool",
                "media_type": "image",
                "media_url": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=900&q=80",
                "caption": "Pocket glass doors slide completely into the wall. Zero-edge pool water is heated.",
                "helpful_count": 31,
            },
        ],
        "comments": [
            {
                "id": "c1",
                "author": "@sarah_chen_vc",
                "verified": True,
                "vote": "up",
                "stars": 5,
                "room": "Chef's Kitchen",
                "time_ago": "2m ago",
                "text": "At the open house now! The transition from the great room to the Calacatta island feels even bigger in person 👍",
                "helpful": 42,
            },
            {
                "id": "c2",
                "author": "@david_k_bayarea",
                "verified": True,
                "vote": "up",
                "stars": 5,
                "room": "Zero-Edge Pool",
                "time_ago": "6m ago",
                "text": "Verified: zero road noise in the backyard and the cedar soffits smell amazing. Worth top rank in 94301.",
                "helpful": 29,
            },
            {
                "id": "c3",
                "author": "@elena_design",
                "verified": False,
                "vote": "up",
                "stars": 5,
                "room": "Twilight Courtyard",
                "time_ago": "14m ago",
                "text": "Love that people at the open house are uploading real clips to verify the AI tour!",
                "helpful": 19,
            },
        ],
    },
    "sf-pacific-heights-view": {
        "thumbs_up": 1190,
        "thumbs_down": 39,
        "open_house_live_count": 27,
        "amazon_stars": 4.8,
        "verified_checkins": 64,
        "star_breakdown": {"5": 84, "4": 11, "3": 3, "2": 1, "1": 1},
        "attributes": {
            "Matches AI Walkthrough": 4.9,
            "Golden Gate View Accuracy": 5.0,
            "Floorplan Spatial Flow": 4.7,
            "Price-to-Value (94115)": 4.6,
        },
        "visitor_media": [
            {
                "id": "sf_m1",
                "author": "@alex_pac_heights",
                "badge": "✓ Verified at Open House · 7m ago",
                "room": "02 · Golden Gate View Salon",
                "media_type": "video",
                "media_url": "/api/cache/sf-pacific-heights-view_seg0_71f1230a.mp4",
                "caption": "Live from 2840 Broadway — no fog today, unobstructed Golden Gate view from the salon!",
                "helpful_count": 37,
            }
        ],
        "comments": [
            {
                "id": "sf_c1",
                "author": "@alex_pac_heights",
                "verified": True,
                "vote": "up",
                "stars": 5,
                "room": "View Salon",
                "time_ago": "5m ago",
                "text": "Just walked the 3rd floor salon — Golden Gate bridge sightline is dead-on. Elevator is whisper quiet 👍",
                "helpful": 33,
            }
        ],
    },
    "marin-mill-valley-retreat": {
        "thumbs_up": 980,
        "thumbs_down": 19,
        "open_house_live_count": 19,
        "amazon_stars": 4.9,
        "verified_checkins": 51,
        "star_breakdown": {"5": 89, "4": 8, "3": 2, "2": 1, "1": 0},
        "attributes": {
            "Matches AI Walkthrough": 4.9,
            "Redwood Privacy & Quiet": 5.0,
            "Floorplan Spatial Flow": 4.8,
            "Price-to-Value (94941)": 4.8,
        },
        "visitor_media": [
            {
                "id": "mv_m1",
                "author": "@marin_trail_runner",
                "badge": "✓ Verified at Open House · 9m ago",
                "room": "02 · Canopy Lounge",
                "media_type": "image",
                "media_url": "https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=900&q=80",
                "caption": "Afternoon light filtering through the redwoods into the lounge right now.",
                "helpful_count": 24,
            }
        ],
        "comments": [
            {
                "id": "mv_c1",
                "author": "@marin_trail_runner",
                "verified": True,
                "vote": "up",
                "stars": 5,
                "room": "Canopy Lounge",
                "time_ago": "8m ago",
                "text": "The Hinoki cedar spa bath on the canyon deck is unreal in person 👍",
                "helpful": 21,
            }
        ],
    },
    "los-altos-hills-estate": {
        "thumbs_up": 1650,
        "thumbs_down": 31,
        "open_house_live_count": 41,
        "amazon_stars": 4.95,
        "verified_checkins": 94,
        "star_breakdown": {"5": 92, "4": 6, "3": 1, "2": 1, "1": 0},
        "attributes": {
            "Matches AI Walkthrough": 5.0,
            "Infinity Pool & Acreage": 5.0,
            "Floorplan Spatial Flow": 4.9,
            "Price-to-Value (94022)": 4.8,
        },
        "visitor_media": [
            {
                "id": "la_m1",
                "author": "@sv_founder_homes",
                "badge": "✓ Verified at Open House · 3m ago",
                "room": "02 · Zero-Edge Infinity Pool",
                "media_type": "video",
                "media_url": "/api/cache/palo-alto-glass-villa_seg3_20a9c759.mp4",
                "caption": "Live check-in at 26800 Moody Rd — 65ft infinity edge overlooking the hills!",
                "helpful_count": 59,
            }
        ],
        "comments": [
            {
                "id": "la_c1",
                "author": "@sv_founder_homes",
                "verified": True,
                "vote": "up",
                "stars": 5,
                "room": "Infinity Pool",
                "time_ago": "3m ago",
                "text": "Hands down the #1 ranked estate in Silicon Valley today. Pool terrace fits 80+ people easily 👍",
                "helpful": 54,
            }
        ],
    },
    "palo-alto-cowper-modern": {
        "thumbs_up": 1085,
        "thumbs_down": 24,
        "open_house_live_count": 22,
        "amazon_stars": 4.85,
        "verified_checkins": 58,
        "star_breakdown": {"5": 86, "4": 10, "3": 3, "2": 1, "1": 0},
        "attributes": {
            "Matches AI Walkthrough": 4.9,
            "Calacatta Marble Quality": 5.0,
            "Floorplan Spatial Flow": 4.8,
            "Price-to-Value (94301)": 4.7,
        },
        "visitor_media": [
            {
                "id": "pa2_m1",
                "author": "@palo_alto_mom",
                "badge": "✓ Verified at Open House · 6m ago",
                "room": "02 · Chef's Kitchen",
                "media_type": "image",
                "media_url": "https://images.unsplash.com/photo-1600566753376-12c8ab7fb75b?auto=format&fit=crop&w=900&q=80",
                "caption": "Hidden scullery behind the Gaggenau wine wall is huge!",
                "helpful_count": 27,
            }
        ],
        "comments": [
            {
                "id": "pa2_c1",
                "author": "@palo_alto_mom",
                "verified": True,
                "vote": "up",
                "stars": 5,
                "room": "Chef's Kitchen",
                "time_ago": "6m ago",
                "text": "Walked over from Ramirez St — super warm oak floors and the scullery kitchen is a dream 👍",
                "helpful": 27,
            }
        ],
    },
}


def load_social_store() -> Dict[str, Any]:
    if SOCIAL_STORE_PATH.exists():
        try:
            return json.loads(SOCIAL_STORE_PATH.read_text())
        except Exception:
            pass
    SOCIAL_STORE_PATH.write_text(json.dumps(DEFAULT_SOCIAL_DATA, indent=2))
    return json.loads(json.dumps(DEFAULT_SOCIAL_DATA))


def save_social_store(store: Dict[str, Any]) -> None:
    SOCIAL_STORE_PATH.write_text(json.dumps(store, indent=2))


def compute_hybrid_rank(entry: Dict[str, Any]) -> Dict[str, Any]:
    up = max(1, int(entry.get("thumbs_up", 100)))
    down = max(0, int(entry.get("thumbs_down", 2)))
    upvote_ratio = round((up / (up + down)) * 100, 1)
    stars = float(entry.get("amazon_stars", 4.8))
    checkins = int(entry.get("verified_checkins", 40))
    media_count = len(entry.get("visitor_media", []))
    # Hybrid Amazon (Verified Stars + Check-ins + Media Proof) x YouTube (Upvote Ratio + Engagement Velocity) Score (0-100)
    yt_component = (up / (up + down)) * 50.0 + min(12.0, up / 180.0)
    amz_component = (stars / 5.0) * 32.0 + min(6.0, (checkins + media_count * 5) / 25.0)
    hybrid_score = round(min(99.9, yt_component + amz_component), 1)
    entry["upvote_ratio"] = upvote_ratio
    entry["hybrid_rank_score"] = hybrid_score
    return entry


def get_or_init_listing_social(listing_id: str) -> Dict[str, Any]:
    store = load_social_store()
    if listing_id not in store:
        store[listing_id] = json.loads(json.dumps(DEFAULT_SOCIAL_DATA["palo-alto-glass-villa"]))
        save_social_store(store)
    return compute_hybrid_rank(store[listing_id])


class SocialVoteRequest(BaseModel):
    listing_id: str
    direction: str  # "up" or "down"


class SocialCommentRequest(BaseModel):
    listing_id: str
    author: str = "@openhouse_visitor"
    text: str
    vote: str = "up"
    stars: int = 5
    room: str = "Great Room"
    verified_open_house: bool = True
    media_url: Optional[str] = None
    media_type: Optional[str] = None


@app.post("/api/social/vote")
async def post_social_vote(req: SocialVoteRequest):
    store = load_social_store()
    entry = store.get(req.listing_id) or json.loads(json.dumps(DEFAULT_SOCIAL_DATA["palo-alto-glass-villa"]))
    if req.direction == "up":
        entry["thumbs_up"] = int(entry.get("thumbs_up", 100)) + 1
    else:
        entry["thumbs_down"] = int(entry.get("thumbs_down", 0)) + 1
    store[req.listing_id] = compute_hybrid_rank(entry)
    save_social_store(store)
    return {"status": "ok", "social": store[req.listing_id]}


@app.post("/api/social/comment")
async def post_social_comment(req: SocialCommentRequest):
    store = load_social_store()
    entry = store.get(req.listing_id) or json.loads(json.dumps(DEFAULT_SOCIAL_DATA["palo-alto-glass-villa"]))
    if req.vote == "up":
        entry["thumbs_up"] = int(entry.get("thumbs_up", 100)) + 1
    elif req.vote == "down":
        entry["thumbs_down"] = int(entry.get("thumbs_down", 0)) + 1

    if req.verified_open_house:
        entry["verified_checkins"] = int(entry.get("verified_checkins", 50)) + 1

    new_comment = {
        "id": f"c_{int(time.time() * 1000)}",
        "author": req.author if req.author.startswith("@") else f"@{req.author}",
        "verified": req.verified_open_house,
        "vote": req.vote,
        "stars": max(1, min(5, req.stars)),
        "room": req.room,
        "time_ago": "Just now · Live",
        "text": req.text,
        "helpful": 1,
    }
    entry.setdefault("comments", []).insert(0, new_comment)

    if req.media_url:
        new_media = {
            "id": f"m_{int(time.time() * 1000)}",
            "author": new_comment["author"],
            "badge": "✓ Verified Live at Open House · Just now",
            "room": req.room,
            "media_type": req.media_type or ("video" if req.media_url.endswith(".mp4") else "image"),
            "media_url": req.media_url,
            "caption": req.text,
            "helpful_count": 1,
        }
        entry.setdefault("visitor_media", []).insert(0, new_media)

    store[req.listing_id] = compute_hybrid_rank(entry)
    save_social_store(store)
    return {"status": "ok", "social": store[req.listing_id], "new_comment": new_comment}


@app.post("/api/social/upload")
async def upload_open_house_media(
    listing_id: str = Form(...),
    author: str = Form("@openhouse_guest"),
    room: str = Form("Great Room"),
    caption: str = Form("Live check-in from the Open House!"),
    vote: str = Form("up"),
    stars: int = Form(5),
    file: UploadFile = File(...),
):
    ext = Path(file.filename or "upload.jpg").suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"]:
        ext = ".jpg"
    fname = f"openhouse_{listing_id}_{int(time.time() * 1000)}{ext}"
    dest = CACHE_DIR / fname
    content = await file.read()
    dest.write_bytes(content)
    media_url = f"/api/cache/{fname}"
    media_type = "video" if ext in [".mp4", ".mov", ".webm"] else "image"

    store = load_social_store()
    entry = store.get(listing_id) or json.loads(json.dumps(DEFAULT_SOCIAL_DATA["palo-alto-glass-villa"]))
    if vote == "up":
        entry["thumbs_up"] = int(entry.get("thumbs_up", 100)) + 1
    else:
        entry["thumbs_down"] = int(entry.get("thumbs_down", 0)) + 1
    entry["verified_checkins"] = int(entry.get("verified_checkins", 50)) + 1

    new_media = {
        "id": f"m_{int(time.time() * 1000)}",
        "author": author if author.startswith("@") else f"@{author}",
        "badge": "✓ Verified Live Upload · Just now",
        "room": room,
        "media_type": media_type,
        "media_url": media_url,
        "caption": caption,
        "helpful_count": 1,
    }
    entry.setdefault("visitor_media", []).insert(0, new_media)
    entry.setdefault("comments", []).insert(
        0,
        {
            "id": f"c_{int(time.time() * 1000)}",
            "author": new_media["author"],
            "verified": True,
            "vote": vote,
            "stars": stars,
            "room": room,
            "time_ago": "Just now · Uploaded Media",
            "text": f"📸 Uploaded live {media_type} from {room}: {caption}",
            "helpful": 1,
        },
    )
    store[listing_id] = compute_hybrid_rank(entry)
    save_social_store(store)
    return {"status": "ok", "media_url": media_url, "media_type": media_type, "social": store[listing_id]}


@app.get("/api/cache/{filename}")
async def serve_cached_media(filename: str):
    safe_name = Path(filename).name
    file_path = CACHE_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Cached file not found")
    if safe_name.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif safe_name.endswith(".wav"):
        media_type = "audio/wav"
    elif safe_name.endswith((".mp4", ".mov", ".webm")):
        media_type = "video/mp4"
    else:
        media_type = "image/jpeg"
    return FileResponse(file_path, media_type=media_type)


@app.middleware("http")
async def disable_static_caching(request, call_next):
    response = await call_next(request)
    if request.url.path in ("/", "/94404", "/api/faithful/94404") or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.get("/")
async def serve_index():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


from faithful_tours import router as faithful_router
app.include_router(faithful_router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
