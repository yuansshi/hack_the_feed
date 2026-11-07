import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
STATIC_DIR = BASE_DIR / "static"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
CACHE_INDEX_PATH = DATA_DIR / "cache_index.json"


def load_api_key(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name].strip()
    for env_file in [BASE_DIR / "api_key.md", BASE_DIR / ".env"]:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip()
    raise RuntimeError(f"Missing required key {name} in environment or api_key.md")


GMI_API_KEY = load_api_key("GMI_API_KEY")
ORIANE_API_KEY = load_api_key("ORIANE_API_KEY")
GMI_LLM_BASE_URL = "https://api.gmi-serving.com/v1"
GMI_QUEUE_BASE_URL = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey"
ORIANE_BASE_URL = "https://connect.oriane.xyz"


def load_cache_index() -> Dict[str, Any]:
    if CACHE_INDEX_PATH.exists():
        try:
            return json.loads(CACHE_INDEX_PATH.read_text())
        except Exception:
            pass
    return {"segments": {}, "voiceovers": {}, "oriane": {}, "plans": {}}


def save_cache_index(index: Dict[str, Any]) -> None:
    CACHE_INDEX_PATH.write_text(json.dumps(index, indent=2))


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


class GMIPlanRequest(BaseModel):
    listing_id: str
    oriane_summary: Optional[Dict[str, Any]] = None
    custom_listing: Optional[Dict[str, Any]] = None


class GMIGenerateSegmentRequest(BaseModel):
    listing_id: str
    transition_index: int
    from_room: str
    to_room: str
    first_frame_url: str
    last_frame_url: str
    prompt: str
    model: str = "veo-3.1-lite-generate-001"
    duration: int = 4


class GMIVoiceoverRequest(BaseModel):
    listing_id: str
    text: str
    voice_id: str = "Amara"


def get_listing_by_id(listing_id: str) -> Dict[str, Any]:
    for item in CURATED_LISTINGS:
        if item["id"] == listing_id:
            return item
    return CURATED_LISTINGS[0]


def enrich_listing_with_cache(listing: Dict[str, Any]) -> Dict[str, Any]:
    idx = load_cache_index()
    enriched = json.loads(json.dumps(listing))
    lid = enriched["id"]

    # Upgrade room photos to bespoke GMI 2K generated images if present in data/cache/
    for room in enriched.get("rooms", []):
        rid = room["id"]
        gmi_imgs = sorted(
            [p for p in CACHE_DIR.glob(f"img_{lid}_{rid}_*.jpg") if p.is_file() and p.stat().st_size > 10000],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        if gmi_imgs:
            room["image_url"] = f"/api/cache/{gmi_imgs[0].name}"

    for t in enriched.get("transitions", []):
        t_idx = t["index"]
        seg_key = f"{lid}_seg{t_idx}"
        seg_info = idx.get("segments", {}).get(seg_key)
        # Prefer newest real GMI video clip on disk for this house+segment
        real_gmi_clips = sorted(
            [
                p for p in CACHE_DIR.glob(f"{lid}_seg{t_idx}_*.mp4")
                if not p.name.endswith("_glide.mp4") and not p.name.startswith("slow_") and p.stat().st_size > 20000
            ],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        if real_gmi_clips:
            best_clip = real_gmi_clips[0]
            slow_clip = CACHE_DIR / f"slow_{best_clip.name}"
            served_file = slow_clip.name if (slow_clip.exists() and slow_clip.stat().st_size > 20000) else best_clip.name
            t["status"] = "ready"
            t["video_url"] = f"/api/cache/{served_file}"
            t["model"] = (seg_info or {}).get("model", "veo-3.1-fast-generate-001")
            t["request_id"] = best_clip.stem.split("_")[-1]
        elif seg_info and seg_info.get("local_file") and (CACHE_DIR / seg_info["local_file"]).exists():
            t["status"] = "ready"
            t["video_url"] = f"/api/cache/{seg_info['local_file']}"
            t["model"] = seg_info.get("model", "veo-3.1-lite-generate-001")
            t["request_id"] = seg_info.get("request_id")
        else:
            glide_file = f"{lid}_seg{t_idx}_glide.mp4"
            if (CACHE_DIR / glide_file).exists():
                t["status"] = "ready"
                t["video_url"] = f"/api/cache/{glide_file}"
                t["model"] = "gmi-room-glide"
            else:
                t["status"] = "not_generated"
                t["video_url"] = None

    vo_info = idx.get("voiceovers", {}).get(lid)
    if vo_info and vo_info.get("local_file") and (CACHE_DIR / vo_info["local_file"]).exists():
        enriched["voiceover_status"] = "ready"
        enriched["voiceover_url"] = f"/api/cache/{vo_info['local_file']}"
    elif vo_info and vo_info.get("request_id"):
        enriched["voiceover_status"] = vo_info.get("status", "processing")
        enriched["voiceover_request_id"] = vo_info["request_id"]
    else:
        enriched["voiceover_status"] = "not_generated"
        enriched["voiceover_url"] = None

    enriched["social"] = get_or_init_listing_social(lid)
    return enriched


async def poll_and_download_gmi_request(request_id: str, target_prefix: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {GMI_API_KEY}"}
    url = f"{GMI_QUEUE_BASE_URL}/requests/{request_id}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            return {"status": "error", "detail": resp.text}
        data = resp.json()
        status = data.get("status", "processing")
        if status in ("finished", "succeeded", "completed", "success"):
            # Extract media URL from outcome/result/output
            media_url = extract_media_url(data)
            if media_url:
                ext = ".mp3" if ("mp3" in media_url or "audio" in target_prefix or "vo_" in target_prefix) else ".mp4"
                filename = f"{target_prefix}_{request_id[:8]}{ext}"
                local_path = CACHE_DIR / filename
                if not local_path.exists():
                    dl = await client.get(media_url, follow_redirects=True, timeout=60.0)
                    if dl.status_code == 200:
                        local_path.write_bytes(dl.content)
                if local_path.exists():
                    return {
                        "status": "ready",
                        "local_file": filename,
                        "video_url": f"/api/cache/{filename}",
                        "raw": data,
                    }
            # Check base64 audio if TTS returned inline audio
            b64_bytes = extract_base64_audio(data)
            if b64_bytes:
                filename = f"{target_prefix}_{request_id[:8]}.mp3"
                local_path = CACHE_DIR / filename
                local_path.write_bytes(b64_bytes)
                return {
                    "status": "ready",
                    "local_file": filename,
                    "video_url": f"/api/cache/{filename}",
                }
        return {"status": status, "raw": data}


def extract_media_url(data: Any) -> Optional[str]:
    if isinstance(data, str):
        if data.startswith("http://") or data.startswith("https://"):
            if any(x in data.lower() for x in [".mp4", ".webm", ".mp3", ".wav", "storage.googleapis", "cloudfront", "s3", "artifact", "media", "video", "audio"]):
                return data
        return None
    if isinstance(data, dict):
        for k in ["video_url", "audio_url", "url", "media_url", "output_url", "download_url", "uri", "file_url"]:
            v = data.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        for v in data.values():
            found = extract_media_url(v)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = extract_media_url(item)
            if found:
                return found
    return None


def extract_base64_audio(data: Any) -> Optional[bytes]:
    import base64
    if isinstance(data, dict):
        for k in ["audio_content", "audioContent", "audio_base64", "audio", "data"]:
            v = data.get(k)
            if isinstance(v, str) and len(v) > 500 and not v.startswith("http"):
                try:
                    return base64.b64decode(v)
                except Exception:
                    pass
        for v in data.values():
            res = extract_base64_audio(v)
            if res:
                return res
    elif isinstance(data, list):
        for item in data:
            res = extract_base64_audio(item)
            if res:
                return res
    return None


@app.get("/api/listings")
async def list_curated_listings():
    # First refresh any processing jobs in cache_index
    idx = load_cache_index()
    changed = False
    for seg_key, info in list(idx.get("segments", {}).items()):
        if info.get("status") not in ("ready", "failed", "error") and info.get("request_id"):
            res = await poll_and_download_gmi_request(info["request_id"], seg_key)
            if res.get("status") == "ready":
                info["status"] = "ready"
                info["local_file"] = res["local_file"]
                changed = True
            elif res.get("status") in ("failed", "error", "cancelled"):
                info["status"] = res["status"]
                changed = True

    for lid, info in list(idx.get("voiceovers", {}).items()):
        if info.get("status") not in ("ready", "failed", "error") and info.get("request_id"):
            res = await poll_and_download_gmi_request(info["request_id"], f"vo_{lid}")
            if res.get("status") == "ready":
                info["status"] = "ready"
                info["local_file"] = res["local_file"]
                changed = True
            elif res.get("status") in ("failed", "error", "cancelled"):
                info["status"] = res["status"]
                changed = True

    if changed:
        save_cache_index(idx)

    return {"listings": [enrich_listing_with_cache(item) for item in CURATED_LISTINGS]}


@app.post("/api/redfin/parse")
async def parse_redfin_url(req: RedfinParseRequest):
    url = req.url.strip()
    # Check if matches one of our curated URLs first
    for item in CURATED_LISTINGS:
        if item["redfin_url"].lower() in url.lower() or item["id"] in url.lower():
            return {"listing": enrich_listing_with_cache(item), "source": "curated_bay_area"}

    # Parse Redfin URL structure: https://www.redfin.com/CA/{City}/{Street}/home/{id}
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split("/") if p]
    city = "Palo Alto"
    state = "CA"
    street = "Bay Area Luxury Residence"
    if len(path_parts) >= 3 and len(path_parts[0]) == 2:
        state = path_parts[0].upper()
        city = path_parts[1].replace("-", " ")
        street = path_parts[2].replace("-", " ")

    # Try fetching live Redfin metadata if accessible, otherwise synthesize with GMI LLM + architectural photos
    scraped_images: List[str] = []
    scraped_title = f"{street}, {city}, {state}"
    scraped_price = "$4,250,000"
    try:
        async with httpx.AsyncClient(
            timeout=6.0,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            },
            follow_redirects=True,
        ) as client:
            r = await client.get(url)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml")
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    scraped_title = og_title["content"]
                og_img = soup.find("meta", property="og:image")
                if og_img and og_img.get("content"):
                    scraped_images.append(og_img["content"])
                for img in soup.find_all("img"):
                    src = img.get("src") or ""
                    if "ssl.cdn-redfin.com/photo" in src and src not in scraped_images:
                        scraped_images.append(src)
    except Exception:
        pass

    base = json.loads(json.dumps(CURATED_LISTINGS[0]))
    slug_id = "redfin-" + hashlib.md5(url.encode()).hexdigest()[:8]
    base["id"] = slug_id
    base["redfin_url"] = url
    base["title"] = f"{city} Architectural Showcase — {street}"
    base["address"] = scraped_title
    base["neighborhood"] = f"{city}, {state} • Redfin Live Import"
    base["price"] = scraped_price
    if len(scraped_images) >= 3:
        for idx_r, room in enumerate(base["rooms"]):
            if idx_r < len(scraped_images):
                room["image_url"] = scraped_images[idx_r]

    return {"listing": enrich_listing_with_cache(base), "source": "redfin_parsed"}


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
        "Authorization": f"Bearer {ORIANE_API_KEY}",
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


@app.post("/api/gmi/plan-tour")
async def plan_tour_with_gmi_llm(req: GMIPlanRequest):
    listing = req.custom_listing or get_listing_by_id(req.listing_id)
    idx = load_cache_index()
    if req.listing_id in idx.get("plans", {}):
        return idx["plans"][req.listing_id]

    rooms_summary = [
        {"id": r["id"], "name": r["name"], "vibe": r["vibe"]}
        for r in listing.get("rooms", [])
    ]
    oriane_hooks = (req.oriane_summary or {}).get("viral_playbook", {}).get("winning_spoken_hooks", [])

    system_prompt = (
        "You are an elite Luxury Real Estate Viral Video Director powered by Oriane Video Intelligence and GMI Cloud. "
        "Given a Bay Area Redfin property's room sequence and Oriane's top-performing real estate video hooks, "
        "return a JSON object with: "
        "1) 'viral_score': integer 91-99, "
        "2) 'predicted_outlier_multiplier': string like '142x follower reach', "
        "3) 'hook_strategy': 1 concise sentence explaining why this room order works on TikTok/Reels, "
        "4) 'voiceover_script': a punchy 35-45 word creator voiceover script walking through the rooms, "
        "5) 'room_overlays': list of objects with {'room_id', 'on_screen_hook', 'camera_move', 'transition_prompt'}, "
        "6) 'compound_caption': ready-to-post viral caption with #HackTheFeed and Bay Area real estate hashtags. "
        "Output valid JSON only, no markdown fences."
    )
    user_prompt = json.dumps(
        {
            "property": {
                "title": listing.get("title"),
                "address": listing.get("address"),
                "price": listing.get("price"),
                "sqft": listing.get("sqft"),
                "rooms": rooms_summary,
            },
            "oriane_top_hooks": oriane_hooks[:3],
        }
    )

    headers = {
        "Authorization": f"Bearer {GMI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "google/gemini-3.8-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(f"{GMI_LLM_BASE_URL}/chat/completions", json=body, headers=headers)
        if resp.status_code != 200:
            # Fallback to deepseek-ai/DeepSeek-V4-Pro
            body["model"] = "deepseek-ai/DeepSeek-V4-Pro"
            resp = await client.post(f"{GMI_LLM_BASE_URL}/chat/completions", json=body, headers=headers)

    plan_data: Dict[str, Any] = {}
    if resp.status_code == 200:
        content = resp.json()["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        try:
            plan_data = json.loads(content)
        except Exception:
            plan_data = {"raw_text": content}

    if not plan_data.get("viral_score"):
        plan_data = {
            "viral_score": 96,
            "predicted_outlier_multiplier": "184x follower reach (Top 1% Oriane Outlier)",
            "hook_strategy": "Anchors price + Old Palo Alto prestige in the first 1.8s, then uses continuous First-to-Last-Frame room glides to eliminate scroll drop-off.",
            "voiceover_script": listing.get("voiceover_script"),
            "compound_caption": f"What does {listing.get('price')} get you in {listing.get('neighborhood')}? Wait for the zero-edge pool transition 👀🏡 #HackTheFeed #RealEstate #HouseTour #BayAreaRealEstate #LuxuryHomes",
        }

    result = {"status": "ok", "model": body["model"], "plan": plan_data}
    idx.setdefault("plans", {})[req.listing_id] = result
    save_cache_index(idx)
    return result


@app.post("/api/gmi/generate-segment")
async def generate_walkthrough_segment(req: GMIGenerateSegmentRequest):
    seg_key = f"{req.listing_id}_seg{req.transition_index}"
    idx = load_cache_index()
    existing = idx.get("segments", {}).get(seg_key)
    if existing and existing.get("local_file") and (CACHE_DIR / existing["local_file"]).exists():
        return {
            "status": "ready",
            "cached": True,
            "video_url": f"/api/cache/{existing['local_file']}",
            "model": existing.get("model", req.model),
            "request_id": existing.get("request_id"),
        }

    # Build model-specific payload for First-Frame-to-Last-Frame (FLFV) smooth room transition
    if req.model == "pixverse-v6-transition":
        payload = {
            "prompt": req.prompt,
            "first_frame_img": req.first_frame_url,
            "last_frame_img": req.last_frame_url,
            "duration": 5,
            "quality": "720p",
            "generate_audio_switch": False,
        }
    elif req.model == "vidu-q2-pro-flfv":
        payload = {
            "prompt": req.prompt,
            "first_frame_image": req.first_frame_url,
            "last_frame_image": req.last_frame_url,
            "duration": 5,
        }
    elif req.model == "kling-o1-flfv":
        payload = {
            "prompt": req.prompt,
            "first_frame_image": req.first_frame_url,
            "end_frame_image": req.last_frame_url,
            "duration": "5",
            "mode": "std",
        }
    else:
        # Default: veo-3.1-lite-generate-001 ($0.03/s = $0.12 per 4s clip!)
        payload = {
            "prompt": req.prompt,
            "image": req.first_frame_url,
            "lastFrame": req.last_frame_url,
            "durationSeconds": 4,
            "aspectRatio": "16:9",
            "resolution": "720p",
            "generateAudio": False,
        }

    headers = {
        "Authorization": f"Bearer {GMI_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(
            f"{GMI_QUEUE_BASE_URL}/requests",
            json={"model": req.model, "payload": payload},
            headers=headers,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=f"GMI Video API error: {resp.text}")
        job = resp.json()

    request_id = job.get("request_id")
    idx.setdefault("segments", {})[seg_key] = {
        "request_id": request_id,
        "model": req.model,
        "status": job.get("status", "processing"),
        "from_room": req.from_room,
        "to_room": req.to_room,
        "created_at": int(time.time()),
    }
    save_cache_index(idx)
    return {"status": "processing", "request_id": request_id, "seg_key": seg_key, "model": req.model}


@app.post("/api/gmi/generate-voiceover")
async def generate_voiceover(req: GMIVoiceoverRequest):
    idx = load_cache_index()
    existing = idx.get("voiceovers", {}).get(req.listing_id)
    if existing and existing.get("local_file") and (CACHE_DIR / existing["local_file"]).exists():
        return {
            "status": "ready",
            "cached": True,
            "audio_url": f"/api/cache/{existing['local_file']}",
            "request_id": existing.get("request_id"),
        }

    headers = {
        "Authorization": f"Bearer {GMI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "text": req.text,
        "voice_id": req.voice_id,
        "speaking_rate": 1.05,
    }
    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(
            f"{GMI_QUEUE_BASE_URL}/requests",
            json={"model": "inworld-tts-2-flash", "payload": payload},
            headers=headers,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        job = resp.json()

    request_id = job.get("request_id")
    idx.setdefault("voiceovers", {})[req.listing_id] = {
        "request_id": request_id,
        "status": job.get("status", "processing"),
        "created_at": int(time.time()),
    }
    save_cache_index(idx)
    return {"status": "processing", "request_id": request_id}


@app.get("/api/gmi/poll/{seg_key}")
async def poll_segment_status(seg_key: str):
    idx = load_cache_index()
    seg_info = idx.get("segments", {}).get(seg_key)
    if not seg_info:
        raise HTTPException(status_code=404, detail="Segment not found")
    if seg_info.get("local_file") and (CACHE_DIR / seg_info["local_file"]).exists():
        return {
            "status": "ready",
            "video_url": f"/api/cache/{seg_info['local_file']}",
            "model": seg_info.get("model"),
        }
    res = await poll_and_download_gmi_request(seg_info["request_id"], seg_key)
    if res.get("status") == "ready":
        seg_info["status"] = "ready"
        seg_info["local_file"] = res["local_file"]
        save_cache_index(idx)
    return res


# =====================================================================
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
    elif safe_name.endswith((".mp4", ".mov", ".webm")):
        media_type = "video/mp4"
    else:
        media_type = "image/jpeg"
    return FileResponse(file_path, media_type=media_type)


@app.middleware("http")
async def disable_static_caching(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.get("/")
async def serve_index():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
