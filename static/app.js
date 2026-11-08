const state = {
  listings: [],
  filteredListings: [],
  activeFlipIndex: 0,
  selectedZip: new URLSearchParams(location.search).get("zip") || "94404",
  searchQuery: "",
  sortBy: "price", // "hybrid" | "upvotes" | "stars"
  viewOrientation: "reel", // "reel" (9:16 TikTok/Shorts) or "gallery" (16:9 YouTube)
  stageMode: "feed", // "feed" (Stage 1) | "auto_walkthrough" (Stage 2) | "explore_3d" (Stage 3)
  currentListing: null,
  currentRoomIndex: 0,
  isWalking: false,
  isAutoTour: false,
  orianeData: null,
  geminiPlan: null,
  pollTimer: null,
  tickerInterval: null,
  tickerIdx: 0,
  savedIds: new Set(),
  hiddenIds: new Set(),
};

const els = {
  brandHomeBtn: document.getElementById("brand-home-btn"),
  savedCountBadge: document.getElementById("saved-count-badge"),
  btnRestoreHidden: document.getElementById("btn-restore-hidden"),
  hiddenCountBadge: document.getElementById("hidden-count-badge"),
  swipeStampBadge: document.getElementById("swipe-stamp-badge"),
  btnCompassLeft: document.getElementById("btn-compass-left"),
  btnCompassRight: document.getElementById("btn-compass-right"),
  btnCompassUp: document.getElementById("btn-compass-up"),
  btnCompassDown: document.getElementById("btn-compass-down"),
  btnFlipSaveUp: document.getElementById("btn-flip-save-up"),
  flipSaveLabel: document.getElementById("flip-save-label"),
  btnFlipHideDown: document.getElementById("btn-flip-hide-down"),
  zipPillsContainer: document.getElementById("zip-pills-container"),
  zipSearchInput: document.getElementById("zip-search-input"),
  zipFeedStage: document.getElementById("zip-feed-stage"),
  feedSummaryText: document.getElementById("feed-summary-text"),
  zipFeedGrid: document.getElementById("zip-feed-grid"),
  flipPlayerFrame: document.getElementById("flip-player-frame"),
  flipMainVideo: document.getElementById("flip-main-video"),
  reactionBurstLayer: document.getElementById("reaction-burst-layer"),
  flipZipBadge: document.getElementById("flip-zip-badge"),
  flipDurationBadge: document.getElementById("flip-duration-badge"),
  flipLiveCommentTicker: document.getElementById("flip-live-comment-ticker"),
  flipTickerText: document.getElementById("flip-ticker-text"),
  btnFlipPrev: document.getElementById("btn-flip-prev"),
  btnFlipNext: document.getElementById("btn-flip-next"),
  btnFlipThumbUp: document.getElementById("btn-flip-thumb-up"),
  flipUpCount: document.getElementById("flip-up-count"),
  btnFlipThumbDown: document.getElementById("btn-flip-thumb-down"),
  flipDownCount: document.getElementById("flip-down-count"),
  btnFlipComments: document.getElementById("btn-flip-comments"),
  flipCommentsCount: document.getElementById("flip-comments-count"),
  btnFlipSound: document.getElementById("btn-flip-sound"),
  flipSoundLabel: document.getElementById("flip-sound-label"),
  btnFlipEnter3d: document.getElementById("btn-flip-enter-3d"),
  flipNeighborhood: document.getElementById("flip-neighborhood"),
  flipHookTitle: document.getElementById("flip-hook-title"),
  flipSubtleSpecs: document.getElementById("flip-subtle-specs"),
  flipVideoScrubber: document.getElementById("flip-video-scrubber"),
  flipTimeReadout: document.getElementById("flip-time-readout"),
  btnLaunchFullscreenWalk: document.getElementById("btn-launch-fullscreen-walk"),
  btnLaunchOpenhouseUpload: document.getElementById("btn-launch-openhouse-upload"),
  btnTopOpenhouse: document.getElementById("btn-top-openhouse"),
  btnOpenArchDeck: document.getElementById("btn-open-arch-deck"),
  archDeckModal: document.getElementById("arch-deck-modal"),
  btnCloseArchDeck: document.getElementById("btn-close-arch-deck"),
  walkthroughStage: document.getElementById("walkthrough-stage"),
  btnBackToFeed: document.getElementById("btn-back-to-feed"),
  btnStageOpenhouse: document.getElementById("btn-stage-openhouse"),
  stageUpCount: document.getElementById("stage-up-count"),
  btnSwitch3dMode: document.getElementById("btn-switch-3d-mode"),
  btnToggleRedfinPopover: document.getElementById("btn-toggle-redfin-popover"),
  redfinPopover: document.getElementById("redfin-popover"),
  redfinInput: document.getElementById("redfin-input"),
  btnImportRedfin: document.getElementById("btn-import-redfin"),
  stageFrame: document.getElementById("stage-frame"),
  spatialViewport: document.getElementById("spatial-viewport"),
  roomStillImg: document.getElementById("room-still-img"),
  walkthroughVideo: document.getElementById("walkthrough-video"),
  storyProgressBars: document.getElementById("story-progress-bars"),
  hudStateLabel: document.getElementById("hud-state-label"),
  hudRoomPill: document.getElementById("hud-room-pill"),
  hotspotsContainer: document.getElementById("hotspots-container"),
  propNeighborhoodPill: document.getElementById("prop-neighborhood-pill"),
  viralHookText: document.getElementById("viral-hook-text"),
  spokenSubtitleText: document.getElementById("spoken-subtitle-text"),
  btnSubtleSpecs: document.getElementById("btn-subtle-specs"),
  propTitleSubtle: document.getElementById("prop-title-subtle"),
  propPriceSubtle: document.getElementById("prop-price-subtle"),
  propBedsSubtle: document.getElementById("prop-beds-subtle"),
  propSqftSubtle: document.getElementById("prop-sqft-subtle"),
  btnPlayPause: document.getElementById("btn-play-pause"),
  playPauseIcon: document.getElementById("play-pause-icon"),
  playPauseLabel: document.getElementById("play-pause-label"),
  btnStageThumbUp: document.getElementById("btn-stage-thumb-up"),
  railUpLabel: document.getElementById("rail-up-label"),
  btnStageThumbDown: document.getElementById("btn-stage-thumb-down"),
  railDownLabel: document.getElementById("rail-down-label"),
  btnPlayVo: document.getElementById("btn-play-vo"),
  voRailLabel: document.getElementById("vo-rail-label"),
  btnToggleVibeDrawer: document.getElementById("btn-toggle-vibe-drawer"),
  btnToggleRadar: document.getElementById("btn-toggle-radar"),
  btnToggleOriane: document.getElementById("btn-toggle-oriane"),
  orianeScoreRail: document.getElementById("oriane-score-rail"),
  btnDownloadVideo: document.getElementById("btn-download-video"),
  floatingRadar: document.getElementById("floating-radar"),
  segmentsReadyBadge: document.getElementById("segments-ready-badge"),
  floorplanSvg: document.getElementById("floorplan-svg"),
  floorplanNodes: document.getElementById("floorplan-nodes"),
  roomQuickPills: document.getElementById("room-quick-pills"),
  warmVibeCard: document.getElementById("warm-vibe-card"),
  vibeRoomTitle: document.getElementById("vibe-room-title"),
  vibeRoomDescription: document.getElementById("vibe-room-description"),
  btnResumeFromVibe: document.getElementById("btn-resume-from-vibe"),
  inspectorTitle: document.getElementById("inspector-title"),
  inspectorDetail: document.getElementById("inspector-detail"),
  inspectorViralNote: document.getElementById("inspector-viral-note"),
  vibePropAddress: document.getElementById("vibe-prop-address"),
  vibePropSpecs: document.getElementById("vibe-prop-specs"),
  propVibeTags: document.getElementById("prop-vibe-tags"),
  minimalScrubberBar: document.getElementById("minimal-scrubber-bar"),
  btnPrevRoom: document.getElementById("btn-prev-room"),
  btnNextRoom: document.getElementById("btn-next-room"),
  spatialScrubber: document.getElementById("spatial-scrubber"),
  scrubberReadout: document.getElementById("scrubber-readout"),
  openhouseDrawer: document.getElementById("openhouse-drawer"),
  ohDrawerTitle: document.getElementById("oh-drawer-title"),
  btnCloseOpenhouse: document.getElementById("btn-close-openhouse"),
  ohHybridScore: document.getElementById("oh-hybrid-score"),
  ohAmzStars: document.getElementById("oh-amz-stars"),
  ohVerifiedCount: document.getElementById("oh-verified-count"),
  ohYtRatio: document.getElementById("oh-yt-ratio"),
  btnDrawerVoteUp: document.getElementById("btn-drawer-vote-up"),
  btnDrawerVoteDown: document.getElementById("btn-drawer-vote-down"),
  ohAttributesGrid: document.getElementById("oh-attributes-grid"),
  ohInputAuthor: document.getElementById("oh-input-author"),
  ohInputRoom: document.getElementById("oh-input-room"),
  ohInputStars: document.getElementById("oh-input-stars"),
  ohInputText: document.getElementById("oh-input-text"),
  ohFileInput: document.getElementById("oh-file-input"),
  ohFileName: document.getElementById("oh-file-name"),
  btnSubmitOpenhouse: document.getElementById("btn-submit-openhouse"),
  btnInstantDemoCheckin: document.getElementById("btn-instant-demo-checkin"),
  ohVisitorMediaList: document.getElementById("oh-visitor-media-list"),
  ohCommentsList: document.getElementById("oh-comments-list"),
  orianeDrawer: document.getElementById("oriane-drawer"),
  btnCloseOriane: document.getElementById("btn-close-oriane"),
  orianeTotalViews: document.getElementById("oriane-total-views"),
  orianeOutlierRatio: document.getElementById("oriane-outlier-ratio"),
  orianeEngRate: document.getElementById("oriane-eng-rate"),
  geminiViralScore: document.getElementById("gemini-viral-score"),
  orianeOstPills: document.getElementById("oriane-ost-pills"),
  orianeVideosList: document.getElementById("oriane-videos-list"),
  geminiModelSelect: document.getElementById("gemini-model-select"),
  btnGenerateMissing: document.getElementById("btn-generate-missing"),
  transitionsList: document.getElementById("transitions-list"),
  exportModal: document.getElementById("export-modal"),
  btnCloseModal: document.getElementById("btn-close-modal"),
  exportVideoLinks: document.getElementById("export-video-links"),
  exportCaptionBox: document.getElementById("export-caption-box"),
  btnCopyCaption: document.getElementById("btn-copy-caption"),
  voAudioPlayer: document.getElementById("vo-audio-player"),
};

function formatCompactNumber(num) {
  if (!num) return "0";
  if (num >= 1e9) return (num / 1e9).toFixed(2) + "B";
  if (num >= 1e6) return (num / 1e6).toFixed(1) + "M";
  if (num >= 1e3) return (num / 1e3).toFixed(1) + "K";
  return String(num);
}

function formatShortPrice(priceStr) {
  if (!priceStr) return "";
  const num = Number(String(priceStr).replace(/[^0-9.]/g, ""));
  if (num >= 1e6) return "$" + (num / 1e6).toFixed(2).replace(/\.00$/, "") + "M";
  return priceStr;
}

function formatSeconds(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem < 10 ? "0" : ""}${rem}`;
}

async function initApp() {
  setupEventListeners();
  setup3DParallax();
  await fetchListings();
  document.body.classList.remove("feed-loading");
  const entry = new URLSearchParams(location.search);
  const index = state.filteredListings.findIndex(home => home.source_backed && home.id === entry.get("home"));
  if (index >= 0) {
    state.activeFlipIndex = index;
    renderFlipReelPlayer();
    highlightActiveCardInGrid();
    openSourceResearch(state.filteredListings[index], entry.get("view") || "model");
  }
  startLiveTickerCycle();
}

async function loadFeedListings() {
  const [demoResponse, sourceResponse] = await Promise.all([
    fetch("/api/listings"), fetch("/api/feed/94404")
  ]);
  if (!demoResponse.ok || !sourceResponse.ok) throw new Error("Home feed could not load. Reload to retry.");
  const [demo, source] = await Promise.all([demoResponse.json(), sourceResponse.json()]);
  state.sourceSummary = source.summary;
  return [...source.listings, ...demo.listings];
}

async function fetchListings() {
  state.listings = await loadFeedListings();
  document.querySelectorAll(".zip-pill").forEach(pill => pill.classList.toggle("active", pill.dataset.zip === state.selectedZip));
  if (state.listings.length > 0 && !state.currentListing) {
    state.currentListing = state.listings[0];
  }
  applyZipFilterAndRenderFeed();
}

/* ===================================================================== */
/* STAGE 1: TIKTOK / YOUTUBE FLIP DECK + AMAZON × YOUTUBE RANKING        */
/* ===================================================================== */
function applyZipFilterAndRenderFeed() {
  const q = state.searchQuery.trim().toLowerCase();
  const filtered = state.listings.filter((item) => {
    if (state.hiddenIds.has(item.id)) return false;
    if (state.selectedZip === "SAVED" && !state.savedIds.has(item.id)) return false;
    const zipMatch =
      state.selectedZip === "ALL" || state.selectedZip === "SAVED" ||
      String(item.zip_code || "").includes(state.selectedZip) ||
      String(item.address || "").includes(state.selectedZip);
    if (!zipMatch) return false;
    if (!q) return true;
    return (
      String(item.zip_code || "").toLowerCase().includes(q) ||
      String(item.city || "").toLowerCase().includes(q) ||
      String(item.address || "").toLowerCase().includes(q) ||
      String(item.title || "").toLowerCase().includes(q) ||
      String(item.neighborhood || "").toLowerCase().includes(q)
    );
  });

  if (els.savedCountBadge) els.savedCountBadge.textContent = String(state.savedIds.size);
  if (els.hiddenCountBadge) els.hiddenCountBadge.textContent = String(state.hiddenIds.size);
  if (els.btnRestoreHidden) {
    els.btnRestoreHidden.classList.toggle("hidden", state.hiddenIds.size === 0);
  }

  // Sort by Amazon x YouTube Hybrid Rank, Upvotes, or Amazon Stars
  filtered.sort((a, b) => {
    if (state.selectedZip === "94404" || state.sortBy === "price") return (b.price_num || 0) - (a.price_num || 0);
    const sa = a.social || {};
    const sb = b.social || {};
    if (state.sortBy === "upvotes") {
      return (sb.thumbs_up || 0) - (sa.thumbs_up || 0);
    }
    if (state.sortBy === "stars") {
      return (sb.amazon_stars || 0) - (sa.amazon_stars || 0);
    }
    return (sb.hybrid_rank_score || 0) - (sa.hybrid_rank_score || 0);
  });

  state.filteredListings = filtered;
  if (state.activeFlipIndex >= state.filteredListings.length) {
    state.activeFlipIndex = 0;
  }

  const zipLabel =
    state.selectedZip === "ALL" ? "ALL BAY AREA ZIPS" : `ZIP ${state.selectedZip}`;
  els.feedSummaryText.textContent = `${zipLabel} (${state.filteredListings.length} HOMES) · RANKED BY AMAZON ★ × YOUTUBE 👍`;

  if (state.selectedZip === "94404") {
    els.feedSummaryText.textContent = `94404 · ${filtered.length} houses · Asking price ↓ · 6 of 10 requested verified`;
  }
  document.querySelectorAll(".sort-pill[data-sort]").forEach(pill => {
    pill.disabled = state.selectedZip === "94404" && pill.dataset.sort !== "price";
    pill.classList.toggle("active", pill.dataset.sort === (state.selectedZip === "94404" ? "price" : state.sortBy));
  });
  document.getElementById("btn-open-available-3d").hidden = !filtered.some(home => home.source_backed && home.model);
  renderFlipReelPlayer();
  renderZipFeedCards();
}

function getActiveFlipListing() {
  return state.filteredListings[state.activeFlipIndex];
}

function renderFlipReelPlayer() {
  clearInterval(sourceSlideTimer);
  const empty = !state.filteredListings.length;
  els.flipPlayerFrame.classList.toggle("feed-empty", empty);
  document.getElementById("feed-empty").classList.toggle("hidden", !empty);
  if (empty) { els.flipMainVideo.pause(); return; }
  const listing = getActiveFlipListing();
  els.flipPlayerFrame.dataset.listingId = listing.id;
  setSourceFeedControls(Boolean(listing.source_backed));
  if (listing.source_backed) { renderSourceReel(listing); return; }
  const firstRoom = (listing.rooms && listing.rooms[0]) || {};
  const soc = listing.social || {};
  const clipUrl =
    listing.preview_clip_url || "/api/cache/tour_36s_palo_alto_94301.mp4";
  const durLabel = listing.video_duration_label || "0:35";
  const streetShort = (listing.address || listing.title).split(",")[0];
  const shortPrice = formatShortPrice(listing.price);

  els.flipPlayerFrame.className =
    "flip-player-frame " +
    (state.viewOrientation === "reel" ? "mode-9-16" : "mode-16-9");

  els.flipZipBadge.innerHTML = `<span class="pulse-dot"></span> #${
    state.activeFlipIndex + 1
  } RANK · ${listing.zip_code || "94301"} ${listing.city || ""} (${
    soc.hybrid_rank_score || 98.4
  })`;
  els.flipDurationBadge.textContent = `★ ${soc.amazon_stars || 4.9} · ${
    soc.upvote_ratio || 98
  }% 👍 · ${durLabel}`;

  els.flipUpCount.textContent = (soc.thumbs_up || 1420).toLocaleString();
  els.flipDownCount.textContent = (soc.thumbs_down || 28).toLocaleString();
  els.flipCommentsCount.textContent = `${(soc.comments || []).length} Live`;

  const topComment = (soc.comments && soc.comments[0]) || {
    author: "@sarah_chen_vc",
    room: "Chef's Kitchen",
    text: "Standing in the kitchen right now — 14ft Calacatta island is 100% real! 👍",
  };
  els.flipTickerText.textContent = `✓ ${topComment.author} (${topComment.room}): ${topComment.text}`;

  els.flipNeighborhood.textContent = `${listing.neighborhood} · 🔴 ${
    soc.open_house_live_count || 34
  } at Open House Now`;
  els.flipHookTitle.textContent = firstRoom.on_screen_hook || listing.title;
  els.flipSubtleSpecs.innerHTML = `<span class="feed-card-price">${shortPrice}</span> · ${streetShort} · ${
    listing.beds
  } bd · ${listing.baths} ba · ${(listing.sqft || 0).toLocaleString()} sqft`;

  if (!els.flipMainVideo.src.endsWith(clipUrl)) {
    els.flipMainVideo.src = clipUrl;
    els.flipMainVideo.currentTime = 0;
    els.flipMainVideo.playbackRate = 0.78;
    els.flipMainVideo.play().catch(() => {});
  } else {
    els.flipMainVideo.playbackRate = 0.78;
  }

  els.flipMainVideo.ontimeupdate = () => {
    const cur = els.flipMainVideo.currentTime || 0;
    const dur = els.flipMainVideo.duration || 42;
    els.flipVideoScrubber.value = Math.round((cur / dur) * 1000);
    els.flipTimeReadout.textContent = `${formatSeconds(cur)} / ${formatSeconds(dur)}`;
  };
}

function startLiveTickerCycle() {
  if (state.tickerInterval) clearInterval(state.tickerInterval);
  state.tickerInterval = setInterval(() => {
    const listing = getActiveFlipListing();
    if (!listing || listing.source_backed || !listing.social) return;
    const comments = listing.social.comments || [];
    if (!comments.length) return;
    state.tickerIdx = (state.tickerIdx + 1) % comments.length;
    const c = comments[state.tickerIdx];
    els.flipTickerText.textContent = `✓ ${c.author} (${c.room}): ${c.text}`;
  }, 8500);
}

function flipToNextHouse(delta = 1) {
  if (state.stageMode !== "feed" || !state.filteredListings.length) return;
  const slideOffset = delta > 0 ? "-38px" : "38px";
  els.flipPlayerFrame.style.transform = `translateX(${slideOffset}) scale(0.98)`;
  setTimeout(() => {
    els.flipPlayerFrame.style.transform = "translate(0px, 0px) rotate(0deg)";
    if (state.stageMode !== "feed") return;
    state.activeFlipIndex =
      (state.activeFlipIndex + delta + state.filteredListings.length) %
      state.filteredListings.length;
    els.flipPlayerFrame.style.transform = "translate(0px, 0px) rotate(0deg)";
    renderFlipReelPlayer();
    highlightActiveCardInGrid();
  }, 150);
}

function showSwipeStamp(text, borderColor = "#ebc388") {
  if (!els.swipeStampBadge) return;
  els.swipeStampBadge.textContent = text;
  els.swipeStampBadge.style.borderColor = borderColor;
  els.swipeStampBadge.style.color = borderColor;
  els.swipeStampBadge.classList.remove("hidden");
  setTimeout(() => els.swipeStampBadge.classList.add("hidden"), 750);
}

function swipeSaveActiveHouse() {
  const listing = getActiveFlipListing();
  if (state.stageMode !== "feed" || !listing) return;
  state.savedIds.add(listing.id);
  els.savedCountBadge.textContent = String(state.savedIds.size);
  showSwipeStamp(listing.source_backed ? "▲ SAVED HOME 💛" : "▲ SAVED HOME 💛 + 👍", "#ebc388");
  els.flipPlayerFrame.style.transform = "translateY(-36px) scale(1.02)";
  if (!listing.source_backed) castRealtimeVote(listing.id, "up");
  if (els.btnFlipSaveUp) els.btnFlipSaveUp.classList.add("is-saved");
  if (els.flipSaveLabel) els.flipSaveLabel.textContent = "Saved 💛";
  setTimeout(() => {
    els.flipPlayerFrame.style.transform = "translate(0px, 0px) rotate(0deg)";
    flipToNextHouse(1);
  }, 380);
}

function swipeHideActiveHouse() {
  const listing = getActiveFlipListing();
  if (state.stageMode !== "feed" || !listing) return;
  showSwipeStamp("▼ HIDDEN · NOT SHOWING 🚫", "#f87171");
  els.flipPlayerFrame.style.transform = "translateY(42px) scale(0.95)";
  setTimeout(() => {
    state.hiddenIds.add(listing.id);
    if (state.hiddenIds.size >= state.listings.length) {
      // Keep at least 1 house or auto-restore so demo never empties completely
      state.hiddenIds.clear();
    }
    els.flipPlayerFrame.style.transform = "translate(0px, 0px) rotate(0deg)";
    applyZipFilterAndRenderFeed();
  }, 320);
}

function setup4WaySwipeGestures() {
  const frame = els.flipPlayerFrame;
  if (!frame) return;
  let startX = 0;
  let startY = 0;
  let dragging = false;

  const onStart = (x, y, target) => {
    if (
      target.closest("button") ||
      target.closest("input") ||
      target.closest(".flip-live-comment-ticker")
    ) {
      return;
    }
    dragging = true;
    startX = x;
    startY = y;
  };

  const onMove = (x, y) => {
    if (!dragging) return;
    const dx = x - startX;
    const dy = y - startY;
    frame.style.transform = `translate(${dx * 0.35}px, ${dy * 0.35}px) rotate(${dx * 0.03}deg)`;

    if (Math.abs(dx) > 45 || Math.abs(dy) > 45) {
      els.swipeStampBadge.classList.remove("hidden");
      if (Math.abs(dx) > Math.abs(dy)) {
        els.swipeStampBadge.textContent = dx < 0 ? "◀ NEXT HOUSE" : "PREV HOUSE ▶";
        els.swipeStampBadge.style.borderColor = "#ebc388";
        els.swipeStampBadge.style.color = "#ebc388";
      } else {
        if (dy < 0) {
          els.swipeStampBadge.textContent = "▲ SWIPE UP: SAVE HOME 💛";
          els.swipeStampBadge.style.borderColor = "#6ee7b7";
          els.swipeStampBadge.style.color = "#6ee7b7";
        } else {
          els.swipeStampBadge.textContent = "▼ SWIPE DOWN: DON'T SHOW 🚫";
          els.swipeStampBadge.style.borderColor = "#f87171";
          els.swipeStampBadge.style.color = "#f87171";
        }
      }
    } else {
      els.swipeStampBadge.classList.add("hidden");
    }
  };

  const onEnd = (x, y) => {
    if (!dragging) return;
    dragging = false;
    els.swipeStampBadge.classList.add("hidden");
    const dx = x - startX;
    const dy = y - startY;
    frame.style.transform = "translate(0px, 0px) rotate(0deg)";

    if (Math.abs(dx) < 50 && Math.abs(dy) < 50) return;

    if (Math.abs(dx) > Math.abs(dy)) {
      // Horizontal swipe: Left sweeps to Next house, Right sweeps to Prev house
      if (dx < 0) flipToNextHouse(1);
      else flipToNextHouse(-1);
    } else {
      // Vertical swipe: Up saves house, Down hides house
      if (dy < 0) swipeSaveActiveHouse();
      else swipeHideActiveHouse();
    }
  };

  frame.addEventListener("mousedown", (e) => onStart(e.clientX, e.clientY, e.target));
  window.addEventListener("mousemove", (e) => onMove(e.clientX, e.clientY));
  window.addEventListener("mouseup", (e) => onEnd(e.clientX, e.clientY));

  frame.addEventListener(
    "touchstart",
    (e) => {
      if (e.touches[0]) onStart(e.touches[0].clientX, e.touches[0].clientY, e.target);
    },
    { passive: true }
  );
  frame.addEventListener(
    "touchmove",
    (e) => {
      if (e.touches[0]) onMove(e.touches[0].clientX, e.touches[0].clientY);
    },
    { passive: true }
  );
  frame.addEventListener("touchend", (e) => {
    if (e.changedTouches[0]) onEnd(e.changedTouches[0].clientX, e.changedTouches[0].clientY);
  });
}

function highlightActiveCardInGrid() {
  const cards = els.zipFeedGrid.querySelectorAll(".feed-house-card");
  cards.forEach((c, idx) => {
    if (idx === state.activeFlipIndex) {
      c.classList.add("active-flip-card");
      if (window.matchMedia("(min-width: 701px)").matches) {
        c.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    } else {
      c.classList.remove("active-flip-card");
    }
  });
}

function renderZipFeedCards() {
  els.zipFeedGrid.innerHTML = "";
  els.zipFeedGrid.className =
    "zip-feed-grid " +
    (state.viewOrientation === "reel" ? "view-vertical" : "view-horizontal");

  state.filteredListings.forEach((listing, idx) => {
    if (listing.source_backed) { renderSourceCard(listing, idx); return; }
    const card = document.createElement("article");
    card.className =
      "feed-house-card" + (idx === state.activeFlipIndex ? " active-flip-card" : "");
    const firstRoom = (listing.rooms && listing.rooms[0]) || {};
    const soc = listing.social || {};
    const clipUrl =
      listing.preview_clip_url || "/api/cache/tour_36s_palo_alto_94301.mp4";
    const durLabel = listing.video_duration_label || "0:35";
    const streetShort = (listing.address || listing.title).split(",")[0];
    const shortPrice = formatShortPrice(listing.price);

    card.innerHTML = `
      <img class="feed-card-poster" src="${firstRoom.image_url || ""}" alt="${listing.title}" />
      <video
        class="feed-card-video"
        src="${clipUrl}"
        autoplay
        loop
        muted
        playsinline
        preload="auto"
      ></video>
      <div class="feed-card-shade"></div>

      <div class="feed-card-top">
        <span class="feed-zip-badge">
          <span class="pulse-dot"></span>
          #${idx + 1} Rank (${soc.hybrid_rank_score || 98.4}) · ${listing.zip_code}
        </span>
        <span class="feed-loop-indicator">★ ${soc.amazon_stars || 4.9} · ${durLabel}</span>
      </div>

      <div class="feed-card-bottom">
        <h3 class="feed-card-hook">${firstRoom.on_screen_hook || listing.title}</h3>
        <div class="feed-card-subtle-meta">
          <span class="feed-card-price">${shortPrice}</span>
          <span>·</span>
          <span>${streetShort}</span>
          <span>·</span>
          <span>${listing.beds} bd</span>
          <span>·</span>
          <span>${(listing.sqft || 0).toLocaleString()} sqft</span>
        </div>

        <!-- Amazon x YouTube Real-Time Vote & Open House Row -->
        <div class="card-social-rank-row">
          <div class="card-vote-group">
            <button class="card-vote-btn btn-card-up" title="Real-Time Thumbs Up">
              👍 ${(soc.thumbs_up || 1420).toLocaleString()}
            </button>
            <button class="card-vote-btn btn-card-down" title="Real-Time Thumbs Down">
              👎 ${soc.thumbs_down || 28}
            </button>
            <button class="card-vote-btn btn-card-oh" title="Open Live Open House Media & Comments">
              📸 ${(soc.visitor_media || []).length} Live
            </button>
          </div>
          <span class="feed-enter-pill">🎬 Tour →</span>
        </div>
      </div>
    `;

    card.querySelector(".btn-card-up").onclick = (e) => {
      e.stopPropagation();
      castRealtimeVote(listing.id, "up");
    };
    card.querySelector(".btn-card-down").onclick = (e) => {
      e.stopPropagation();
      castRealtimeVote(listing.id, "down");
    };
    card.querySelector(".btn-card-oh").onclick = (e) => {
      e.stopPropagation();
      openOpenHouseDrawer(listing);
    };

    const enterPill = card.querySelector(".feed-enter-pill");
    if (enterPill) {
      enterPill.onclick = (e) => {
        e.stopPropagation();
        state.activeFlipIndex = idx;
        openHouseAutoWalkthrough(listing, false);
      };
    }

    card.onclick = () => {
      if (state.activeFlipIndex === idx) {
        openHouseAutoWalkthrough(listing, false);
      } else {
        state.activeFlipIndex = idx;
        renderFlipReelPlayer();
        highlightActiveCardInGrid();
      }
    };

    els.zipFeedGrid.appendChild(card);

    const vid = card.querySelector("video");
    if (vid) {
      vid.playbackRate = 0.78;
      vid.play().catch(() => {});
    }
  });
}

/* ===================================================================== */
/* AMAZON × YOUTUBE REAL-TIME VOTING, COMMENTS & LIVE MEDIA UPLOAD       */
/* ===================================================================== */
function triggerReactionBurst(label = "👍 +1") {
  if (!els.reactionBurstLayer) return;
  const span = document.createElement("div");
  span.className = "floating-emoji";
  span.textContent = label;
  els.reactionBurstLayer.appendChild(span);
  setTimeout(() => span.remove(), 1150);
}

async function castRealtimeVote(listingId, direction = "up") {
  if (state.listings.find(home => home.id === listingId)?.source_backed) return;
  triggerReactionBurst(direction === "up" ? "👍 +1 Rank!" : "👎 Noted");
  const res = await fetch("/api/social/vote", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ listing_id: listingId, direction }),
  });
  const data = await res.json();
  if (data.social) {
    const target = state.listings.find((x) => x.id === listingId);
    if (target) target.social = data.social;
    if (state.currentListing && state.currentListing.id === listingId) {
      state.currentListing.social = data.social;
      syncStageSocialCounters();
    }
    applyZipFilterAndRenderFeed();
    if (!els.openhouseDrawer.classList.contains("hidden")) {
      renderOpenHouseDrawerContent(target || getActiveFlipListing());
    }
  }
}

function openOpenHouseDrawer(listing) {
  const target = listing || (state.stageMode === "feed" ? getActiveFlipListing() : state.currentListing);
  if (!target) return;
  if (target.source_backed) { openSourceResearch(target, "evidence"); return; }
  state.currentListing = target;
  renderOpenHouseDrawerContent(target);
  els.openhouseDrawer.classList.remove("hidden");
}

function renderOpenHouseDrawerContent(listing) {
  const soc = listing.social || {};
  els.ohDrawerTitle.textContent = `${listing.address.split(",")[0]} · Open House Live`;
  els.ohHybridScore.textContent = soc.hybrid_rank_score || 98.4;
  els.ohAmzStars.textContent = `★★★★★ ${soc.amazon_stars || 4.9} out of 5`;
  els.ohVerifiedCount.textContent = `✓ ${soc.verified_checkins || 86} Verified at Open House`;
  els.ohYtRatio.textContent = `👍 ${soc.upvote_ratio || 98.1}% YouTube Upvote Ratio (${(
    soc.thumbs_up || 1420
  ).toLocaleString()} 👍 / ${soc.thumbs_down || 28} 👎)`;

  // Attributes
  els.ohAttributesGrid.innerHTML = "";
  const attrs = soc.attributes || {};
  Object.entries(attrs).forEach(([k, v]) => {
    const div = document.createElement("div");
    div.className = "oh-attr-item";
    div.innerHTML = `<span>${k}</span><span class="oh-attr-val">★ ${v}</span>`;
    els.ohAttributesGrid.appendChild(div);
  });

  // Visitor Live Videos & Photos
  els.ohVisitorMediaList.innerHTML = "";
  (soc.visitor_media || []).forEach((m) => {
    const card = document.createElement("div");
    card.className = "visitor-media-card";
    const mediaTag =
      m.media_type === "video"
        ? `<video src="${m.media_url}" autoplay loop muted playsinline></video>`
        : `<img src="${m.media_url}" alt="Open house check-in" />`;
    card.innerHTML = `
      ${mediaTag}
      <div class="visitor-media-meta">
        <div class="visitor-badge">${m.badge || "✓ Verified Open House"}</div>
        <div style="font-weight:700; margin-top:2px;">${m.author} · ${m.room}</div>
        <div style="color:#c2b9ad; margin-top:2px;">${m.caption}</div>
      </div>
    `;
    els.ohVisitorMediaList.appendChild(card);
  });

  // Live Comments
  els.ohCommentsList.innerHTML = "";
  (soc.comments || []).forEach((c) => {
    const div = document.createElement("div");
    div.className = "oh-comment-card";
    const starsStr = "★".repeat(c.stars || 5);
    div.innerHTML = `
      <div class="oh-comment-top">
        <span class="oh-comment-author">${c.author} <span class="visitor-badge">✓ Verified Open House · ${c.room}</span></span>
        <span class="oh-comment-stars">${starsStr} ${c.vote === "down" ? "👎" : "👍"}</span>
      </div>
      <div style="color:#faf6f0; line-height:1.4;">${c.text}</div>
      <div style="font-size:10px; color:#c2b9ad; margin-top:4px;">${c.time_ago} · Helpful (${c.helpful || 1})</div>
    `;
    els.ohCommentsList.appendChild(div);
  });
}

async function submitOpenHouseCheckin() {
  const listing = state.currentListing || getActiveFlipListing();
  if (!listing) return;
  const author = els.ohInputAuthor.value.trim() || "@openhouse_visitor";
  const room = els.ohInputRoom.value;
  const stars = Number(els.ohInputStars.value || 5);
  const vote = stars >= 4 ? "up" : "down";
  const text =
    els.ohInputText.value.trim() ||
    `Live from ${room} at the open house — looks even warmer in person!`;
  const file = els.ohFileInput.files && els.ohFileInput.files[0];

  els.btnSubmitOpenhouse.textContent = "Posting...";
  try {
    let updatedSocial = null;
    if (file) {
      const fd = new FormData();
      fd.append("listing_id", listing.id);
      fd.append("author", author);
      fd.append("room", room);
      fd.append("caption", text);
      fd.append("vote", vote);
      fd.append("stars", String(stars));
      fd.append("file", file);
      const res = await fetch("/api/social/upload", { method: "POST", body: fd });
      const data = await res.json();
      updatedSocial = data.social;
    } else {
      const res = await fetch("/api/social/comment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          listing_id: listing.id,
          author,
          room,
          stars,
          vote,
          text,
          verified_open_house: true,
        }),
      });
      const data = await res.json();
      updatedSocial = data.social;
    }

    if (updatedSocial) {
      listing.social = updatedSocial;
      els.ohInputText.value = "";
      els.ohFileInput.value = "";
      els.ohFileName.textContent = "No file selected";
      triggerReactionBurst("📸 Live Check-In Posted!");
      renderOpenHouseDrawerContent(listing);
      applyZipFilterAndRenderFeed();
      syncStageSocialCounters();
    }
  } finally {
    els.btnSubmitOpenhouse.textContent = "Post Live Check-In →";
  }
}

async function triggerInstantDemoCheckin() {
  const listing = state.currentListing || getActiveFlipListing();
  if (!listing) return;
  const res = await fetch("/api/social/comment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      listing_id: listing.id,
      author: "@bayarea_buyer_live",
      room: "05 · Zero-Edge Pool",
      stars: 5,
      vote: "up",
      text: "Just stepped onto the heated limestone pool deck at the Open House — 10/10 matches the demo AI walkthrough! 👍🔥",
      verified_open_house: true,
      media_url: "/api/cache/palo-alto-glass-villa_seg3_20a9c759.mp4",
      media_type: "video",
    }),
  });
  const data = await res.json();
  if (data.social) {
    listing.social = data.social;
    triggerReactionBurst("🎥 Live Video + 👍 Added!");
    renderOpenHouseDrawerContent(listing);
    applyZipFilterAndRenderFeed();
    syncStageSocialCounters();
  }
}

function syncStageSocialCounters() {
  if (!state.currentListing || !state.currentListing.social) return;
  const soc = state.currentListing.social;
  els.stageUpCount.textContent = (soc.thumbs_up || 1420).toLocaleString();
  els.railUpLabel.textContent = formatCompactNumber(soc.thumbs_up || 1420);
  els.railDownLabel.textContent = String(soc.thumbs_down || 28);
}

function returnToZipFeed() {
  stopAutoTour();
  els.walkthroughVideo.pause();
  state.stageMode = "feed";
  els.walkthroughStage.classList.add("hidden");
  els.zipFeedStage.classList.remove("hidden");
  els.orianeDrawer.classList.add("hidden");

  els.flipMainVideo.play().catch(() => {});
  document.querySelectorAll(".feed-card-video").forEach((v) => {
    v.play().catch(() => {});
  });
}

/* ===================================================================== */
/* STAGE 2: AUTOMATIC LARGER FULL-SCREEN WALKTHROUGH                     */
/* ===================================================================== */
async function openHouseAutoWalkthrough(listing, openDirectlyIn3D = false) {
  if (listing.source_backed) { openSourceResearch(listing, listing.model ? "model" : "evidence"); return; }
  els.flipMainVideo.pause();
  document.querySelectorAll(".feed-card-video").forEach((v) => v.pause());

  stopAutoTour();
  state.currentListing = listing;
  state.currentRoomIndex = 0;
  state.stageMode = openDirectlyIn3D ? "explore_3d" : "auto_walkthrough";

  els.zipFeedStage.classList.add("hidden");
  els.walkthroughStage.classList.remove("hidden");

  els.stageFrame.classList.remove("mode-9-16");
  els.stageFrame.classList.add("mode-16-9");

  els.redfinInput.value = listing.redfin_url || "";
  renderSubtlePropertyMeta();
  syncStageSocialCounters();
  renderStoryProgressBars();
  renderFloorplan();
  renderTransitionsList();
  renderRoomQuickPills();

  if (openDirectlyIn3D) {
    showRoomState(0, true);
    enter3DDeepExploreMode();
  } else {
    els.hotspotsContainer.classList.add("hidden");
    els.warmVibeCard.classList.add("hidden");
    els.floatingRadar.classList.add("hidden");
    els.btnSwitch3dMode.classList.remove("active-3d");
    els.btnSwitch3dMode.innerHTML = "🧭 Switch to 3D Deep Explore Mode";

    showRoomState(0, false);
    setTimeout(() => {
      startContinuousWalkthrough(0);
    }, 150);
  }

  fetchOrianeIntelligence(listing);
  fetchGeminiPlan(listing);
  scheduleSegmentPolling();
}

/* ===================================================================== */
/* STAGE 3: ON-DEMAND 3D DEEP EXPLORE MODE                               */
/* ===================================================================== */
function enter3DDeepExploreMode() {
  state.stageMode = "explore_3d";
  els.walkthroughVideo.pause();
  state.isWalking = false;
  state.isAutoTour = false;
  if (!els.voAudioPlayer.paused) els.voAudioPlayer.pause();

  const rooms = state.currentListing.rooms || [];
  const activeRoom = rooms[state.currentRoomIndex] || rooms[0];
  renderHotspots(activeRoom);

  els.hotspotsContainer.classList.remove("hidden");
  els.warmVibeCard.classList.remove("hidden");
  els.floatingRadar.classList.remove("hidden");

  els.btnSwitch3dMode.classList.add("active-3d");
  els.btnSwitch3dMode.innerHTML = "▶ Resume Auto Full-Screen Walkthrough";
  els.hudStateLabel.textContent =
    "STAGE 3 · 3D DEEP EXPLORE MODE · MOVE MOUSE FOR 3D PARALLAX & CLICK HOTSPOTS";
  els.playPauseIcon.textContent = "▶";
  els.playPauseLabel.textContent = "Auto Walk";
}

function resumeStage2AutoWalkthrough() {
  state.stageMode = "auto_walkthrough";
  els.hotspotsContainer.classList.add("hidden");
  els.warmVibeCard.classList.add("hidden");
  els.floatingRadar.classList.add("hidden");

  els.btnSwitch3dMode.classList.remove("active-3d");
  els.btnSwitch3dMode.innerHTML = "🧭 Switch to 3D Deep Explore Mode";
  els.playPauseIcon.textContent = "⏸";
  els.playPauseLabel.textContent = "Pause";

  const nextSeg =
    state.currentRoomIndex < (state.currentListing.transitions || []).length
      ? state.currentRoomIndex
      : 0;
  startContinuousWalkthrough(nextSeg);
}

function toggleStage2AndStage3() {
  if (state.stageMode === "explore_3d") {
    resumeStage2AutoWalkthrough();
  } else {
    enter3DDeepExploreMode();
  }
}

function renderSubtlePropertyMeta() {
  const l = state.currentListing;
  els.propNeighborhoodPill.textContent = `${l.neighborhood} · ${l.zip_code || ""}`;
  els.propTitleSubtle.textContent = l.address.split(",")[0];
  els.propPriceSubtle.textContent = formatShortPrice(l.price);
  els.propBedsSubtle.textContent = `${l.beds} bd`;
  els.propSqftSubtle.textContent = `${l.sqft.toLocaleString()} sq ft`;

  els.vibePropAddress.textContent = l.address;
  els.vibePropSpecs.textContent = `${l.price} · ${l.beds} Beds · ${l.baths} Baths · ${l.sqft.toLocaleString()} Sq Ft (${l.price_per_sqft}/sqft)`;

  if (l.voiceover_status === "ready" && l.voiceover_url) {
    els.voAudioPlayer.src = l.voiceover_url;
  }

  els.propVibeTags.innerHTML = "";
  (l.vibe_tags || []).forEach((tag) => {
    const span = document.createElement("span");
    span.className = "vibe-tag";
    span.textContent = tag;
    els.propVibeTags.appendChild(span);
  });
}

function renderStoryProgressBars() {
  const rooms = state.currentListing.rooms || [];
  els.storyProgressBars.innerHTML = "";
  rooms.forEach((r, idx) => {
    const seg = document.createElement("div");
    seg.className =
      "story-seg" +
      (idx < state.currentRoomIndex
        ? " completed"
        : idx === state.currentRoomIndex
        ? " active"
        : "");
    seg.title = r.name;
    seg.innerHTML = `<div class="story-seg-fill"></div>`;
    seg.onclick = (e) => {
      e.stopPropagation();
      stopAutoTour();
      showRoomState(idx, true);
      enter3DDeepExploreMode();
    };
    els.storyProgressBars.appendChild(seg);
  });
}

function renderFloorplan() {
  const rooms = state.currentListing.rooms || [];
  els.floorplanSvg.innerHTML = "";
  els.floorplanNodes.innerHTML = "";

  for (let i = 0; i < rooms.length - 1; i++) {
    const [x1, y1] = rooms[i].floorplan_xy;
    const [x2, y2] = rooms[i + 1].floorplan_xy;
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", x1);
    line.setAttribute("y1", y1);
    line.setAttribute("x2", x2);
    line.setAttribute("y2", y2);
    line.setAttribute(
      "stroke",
      i < state.currentRoomIndex ? "#ebc388" : "rgba(255,255,255,0.2)"
    );
    line.setAttribute("stroke-width", "1.6");
    line.setAttribute("stroke-dasharray", "3,2");
    els.floorplanSvg.appendChild(line);
  }

  rooms.forEach((room, idx) => {
    const [x, y] = room.floorplan_xy;
    const node = document.createElement("div");
    node.className = "fp-node" + (idx === state.currentRoomIndex ? " active" : "");
    node.style.left = `${x}%`;
    node.style.top = `${y}%`;
    node.textContent = `${idx + 1} · ${room.short_name}`;
    node.onclick = (e) => {
      e.stopPropagation();
      stopAutoTour();
      showRoomState(idx, true);
      enter3DDeepExploreMode();
    };
    els.floorplanNodes.appendChild(node);
  });
}

function renderTransitionsList() {
  const transitions = state.currentListing.transitions || [];
  els.transitionsList.innerHTML = "";
  let readyCount = 0;

  transitions.forEach((t, idx) => {
    if (t.status === "ready") readyCount++;
    const div = document.createElement("div");
    div.className = "transition-item";
    div.innerHTML = `
      <span>0${idx + 1} · ${t.title}</span>
      <span class="trans-status">${t.status === "ready" ? "✓ Smooth AI Ready" : "Generating..."}</span>
    `;
    div.onclick = () => {
      els.orianeDrawer.classList.add("hidden");
      startContinuousWalkthrough(idx);
    };
    els.transitionsList.appendChild(div);
  });

  els.segmentsReadyBadge.textContent = `${readyCount}/${transitions.length} Smooth AI`;
}

function renderRoomQuickPills() {
  const rooms = state.currentListing.rooms || [];
  els.roomQuickPills.innerHTML = "";
  rooms.forEach((r, idx) => {
    const btn = document.createElement("button");
    btn.className =
      "room-pill-btn" + (idx === state.currentRoomIndex ? " active" : "");
    btn.textContent = `${idx + 1}. ${r.short_name}`;
    btn.onclick = (e) => {
      e.stopPropagation();
      stopAutoTour();
      showRoomState(idx, true);
      enter3DDeepExploreMode();
    };
    els.roomQuickPills.appendChild(btn);
  });
}

function showRoomState(roomIndex, revealWarmVibeDetails = true) {
  const rooms = state.currentListing.rooms || [];
  if (!rooms[roomIndex]) return;
  state.currentRoomIndex = roomIndex;
  state.isWalking = false;

  const room = rooms[roomIndex];
  els.walkthroughVideo.pause();
  els.walkthroughVideo.classList.remove("playing");
  els.roomStillImg.src = room.image_url;

  els.hudRoomPill.textContent = `0${roomIndex + 1} / 0${rooms.length} · ${room.short_name}`;
  els.viralHookText.textContent = room.on_screen_hook;
  els.spokenSubtitleText.textContent = `"${room.spoken_beat}"`;
  els.vibeRoomTitle.textContent = room.name;
  els.vibeRoomDescription.textContent = `${room.vibe} — ${room.ambient_desc}.`;

  const pct = Math.round((roomIndex / Math.max(1, rooms.length - 1)) * 1000);
  els.spatialScrubber.value = pct;
  els.scrubberReadout.textContent = room.short_name;

  renderHotspots(room);
  renderStoryProgressBars();
  renderFloorplan();
  renderRoomQuickPills();

  if (revealWarmVibeDetails) {
    els.hudStateLabel.textContent =
      "STAGE 3 · 3D DEEP EXPLORE MODE · HOTSPOTS & FLOORPLAN ACTIVE";
    els.playPauseIcon.textContent = "▶";
    els.playPauseLabel.textContent = "Auto Walk";
    els.hotspotsContainer.classList.remove("hidden");
    els.warmVibeCard.classList.remove("hidden");
  } else {
    els.hudStateLabel.textContent =
      "STAGE 2 · AUTO FULL-SCREEN WALKTHROUGH (CONTINUOUS REPLAY)";
    els.playPauseIcon.textContent = "⏸";
    els.playPauseLabel.textContent = "Pause";
    els.hotspotsContainer.classList.add("hidden");
    els.warmVibeCard.classList.add("hidden");
  }
}

function renderHotspots(room) {
  els.hotspotsContainer.innerHTML = "";
  const hotspots = room.hotspots || [];
  hotspots.forEach((h, idx) => {
    const pin = document.createElement("button");
    pin.className = "hotspot-pin" + (idx === 0 ? " selected" : "");
    pin.style.left = `${h.x}%`;
    pin.style.top = `${h.y}%`;
    pin.innerHTML = `<span class="hotspot-pulse"></span><span>✦ ${h.label}</span>`;
    pin.onclick = (e) => {
      e.stopPropagation();
      document
        .querySelectorAll(".hotspot-pin")
        .forEach((el) => el.classList.remove("selected"));
      pin.classList.add("selected");
      selectHotspot(h);
      els.warmVibeCard.classList.remove("hidden");
    };
    pin.onmouseenter = () => selectHotspot(h);
    els.hotspotsContainer.appendChild(pin);
  });

  if (hotspots.length > 0) {
    selectHotspot(hotspots[0]);
  }
}

function selectHotspot(h) {
  els.inspectorTitle.textContent = h.label;
  els.inspectorDetail.textContent = h.detail;
  els.inspectorViralNote.textContent = h.viral_note;
}

function startContinuousWalkthrough(startSegIndex = 0) {
  const transitions = state.currentListing.transitions || [];
  if (!transitions.length) return;
  state.isAutoTour = true;
  state.stageMode = "auto_walkthrough";
  els.hotspotsContainer.classList.add("hidden");
  els.warmVibeCard.classList.add("hidden");
  els.floatingRadar.classList.add("hidden");
  els.btnSwitch3dMode.classList.remove("active-3d");
  els.btnSwitch3dMode.innerHTML = "🧭 Switch to 3D Deep Explore Mode";
  els.playPauseIcon.textContent = "⏸";
  els.playPauseLabel.textContent = "Pause";

  let idx = startSegIndex < transitions.length ? startSegIndex : 0;
  const stepNext = () => {
    if (!state.isAutoTour) return;
    if (idx < transitions.length) {
      const curr = idx;
      idx++;
      playTransitionSegment(curr, () => {
        if (!state.isAutoTour) return;
        if (idx < transitions.length) {
          stepNext();
        } else {
          idx = 0;
          stepNext();
        }
      });
    }
  };
  stepNext();
}

async function playTransitionSegment(segIndex, onCompleteCallback = null) {
  const transitions = state.currentListing.transitions || [];
  const rooms = state.currentListing.rooms || [];
  const seg = transitions[segIndex];
  if (!seg) {
    if (onCompleteCallback) onCompleteCallback();
    return;
  }

  state.currentRoomIndex = segIndex;
  state.isWalking = true;
  const fromRoom = rooms[segIndex];
  const toRoom = rooms[segIndex + 1] || fromRoom;

  els.hotspotsContainer.classList.add("hidden");
  els.warmVibeCard.classList.add("hidden");
  els.hudStateLabel.textContent = `STAGE 2 · AUTO WALKTHROUGH · ${fromRoom.short_name.toUpperCase()} → ${toRoom.short_name.toUpperCase()}`;
  els.hudRoomPill.textContent = `0${segIndex + 1} / 0${rooms.length} · ${fromRoom.short_name} → ${toRoom.short_name}`;
  els.viralHookText.textContent = fromRoom.on_screen_hook;
  els.spokenSubtitleText.textContent = `"${fromRoom.spoken_beat}"`;
  els.vibeRoomTitle.textContent = fromRoom.name;
  els.vibeRoomDescription.textContent = `${fromRoom.vibe} — ${fromRoom.ambient_desc}.`;

  renderStoryProgressBars();
  renderFloorplan();
  renderRoomQuickPills();

  if (seg.status === "ready" && seg.video_url) {
    els.roomStillImg.src = fromRoom.image_url;
    els.walkthroughVideo.src = seg.video_url;
    els.walkthroughVideo.currentTime = 0;
    els.walkthroughVideo.playbackRate = 0.78;
    els.walkthroughVideo.classList.add("playing");

    els.walkthroughVideo.ontimeupdate = () => {
      const dur = els.walkthroughVideo.duration || 6;
      const frac = Math.min(1, els.walkthroughVideo.currentTime / dur);
      const base = segIndex / Math.max(1, rooms.length - 1);
      const step = 1 / Math.max(1, rooms.length - 1);
      const overall = Math.round((base + frac * step) * 1000);
      els.spatialScrubber.value = overall;
      els.scrubberReadout.textContent = frac < 0.5 ? fromRoom.short_name : toRoom.short_name;

      if (frac > 0.55) {
        els.viralHookText.textContent = toRoom.on_screen_hook;
        els.spokenSubtitleText.textContent = `"${toRoom.spoken_beat}"`;
        els.vibeRoomTitle.textContent = toRoom.name;
        els.vibeRoomDescription.textContent = `${toRoom.vibe} — ${toRoom.ambient_desc}.`;
      }
    };

    els.walkthroughVideo.onended = () => {
      state.currentRoomIndex = segIndex + 1;
      els.roomStillImg.src = toRoom.image_url;
      els.walkthroughVideo.classList.remove("playing");
      if (onCompleteCallback) {
        setTimeout(() => {
          if (state.isAutoTour) onCompleteCallback();
        }, 2200);
      } else {
        showRoomState(segIndex + 1, true);
      }
    };

    try {
      await els.walkthroughVideo.play();
    } catch (err) {
      showRoomState(segIndex + 1, false);
      if (onCompleteCallback) onCompleteCallback();
    }
  } else {
    els.roomStillImg.src = fromRoom.image_url;
    if (onCompleteCallback) onCompleteCallback();
  }
}

function stopAutoTour() {
  state.isAutoTour = false;
  state.isWalking = false;
  if (!els.voAudioPlayer.paused) els.voAudioPlayer.pause();
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}

function setup3DParallax() {
  const vp = els.spatialViewport;
  vp.addEventListener("mousemove", (e) => {
    const rect = vp.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width - 0.5;
    const ny = (e.clientY - rect.top) / rect.height - 0.5;
    const intensity = state.stageMode === "explore_3d" ? 1.65 : 0.85;
    const transformStr = `scale(1.04) rotateX(${-ny * 4.2 * intensity}deg) rotateY(${
      nx * 5.8 * intensity
    }deg)`;
    els.roomStillImg.style.transform = transformStr;
    els.walkthroughVideo.style.transform = transformStr;
  });

  vp.addEventListener("mouseleave", () => {
    els.roomStillImg.style.transform = "scale(1) rotateX(0deg) rotateY(0deg)";
    els.walkthroughVideo.style.transform = "scale(1) rotateX(0deg) rotateY(0deg)";
  });

  vp.addEventListener("click", (e) => {
    if (
      e.target.closest(".hotspot-pin") ||
      e.target.closest(".social-action-rail") ||
      e.target.closest(".warm-vibe-card") ||
      e.target.closest(".floating-radar") ||
      e.target.closest(".subtle-specs-pill") ||
      e.target.closest(".story-seg") ||
      e.target.closest(".back-feed-btn") ||
      e.target.closest(".btn-3d-explore")
    ) {
      return;
    }
    toggleStage2AndStage3();
  });
}

async function fetchOrianeIntelligence(listing) {
  try {
    const res = await fetch("/api/oriane/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        listing_id: listing.id,
        keywords: listing.oriane_keywords,
        hashtags: listing.oriane_hashtags,
      }),
    });
    const data = await res.json();
    state.orianeData = data;
    renderOrianeIntelligence(data);
  } catch (err) {
    console.error("Oriane fetch error:", err);
  }
}

function renderOrianeIntelligence(data) {
  const agg = data.aggregations || {};
  els.orianeTotalViews.textContent = formatCompactNumber(agg.total_views || 9849437821);
  const topVids = data.top_videos || [];
  const maxOutlier = topVids.reduce(
    (acc, v) => Math.max(acc, v.views_rate_followers || 0),
    agg.avg_outlier_ratio || 21393
  );
  els.orianeOutlierRatio.textContent = `${Math.round(maxOutlier).toLocaleString()}%`;
  els.orianeEngRate.textContent = `${agg.avg_engagement_rate || 4.71}%`;

  els.orianeVideosList.innerHTML = "";
  topVids.slice(0, 4).forEach((v) => {
    const div = document.createElement("div");
    div.className = "oriane-video-item";
    const snippet = v.transcript
      ? `🎙️ "${v.transcript.slice(0, 88)}..."`
      : v.caption || "Luxury house tour";
    div.innerHTML = `
      <img class="oriane-thumb" src="${v.thumbnail_url || ""}" alt="thumb" onerror="this.style.display='none'" />
      <div style="flex:1; min-width:0;">
        <div class="oriane-meta-top">
          <span>@${v.handle || "creator"} · ${formatCompactNumber(v.views)}</span>
          <span class="outlier-pill">${Math.round(v.views_rate_followers || 100)}%</span>
        </div>
        <div class="oriane-snippet">${snippet}</div>
      </div>
    `;
    els.orianeVideosList.appendChild(div);
  });

  els.orianeOstPills.innerHTML = "";
  const pills = (data.viral_playbook && data.viral_playbook.on_screen_text_pills) || [];
  pills.slice(0, 8).forEach((text) => {
    const span = document.createElement("span");
    span.className = "ost-pill";
    span.textContent = text;
    span.onclick = () => {
      els.viralHookText.textContent = text;
    };
    els.orianeOstPills.appendChild(span);
  });
}

async function fetchGeminiPlan(listing) {
  state.geminiPlan = null;
  try {
    const response = await fetch("/api/gemini/plan-tour", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ listing_id: listing.id, oriane_summary: state.orianeData }),
    });
    if (!response.ok) throw new Error(`Gemini plan request failed (HTTP ${response.status})`);
    let data = await response.json();
    for (let attempt = 0; attempt < 20 && ['queued', 'processing', 'in_progress'].includes(data.status); attempt++) {
      await new Promise(resolve => setTimeout(resolve, 3000));
      if (state.currentListing?.id !== listing.id || state.stageMode === 'feed') return;
      const poll = await fetch(`/api/gemini/poll/${encodeURIComponent(`plan_${listing.id}`)}`);
      if (!poll.ok) throw new Error(`Gemini plan poll failed (HTTP ${poll.status})`);
      data = await poll.json();
    }
    if (state.currentListing?.id !== listing.id) return;
    state.geminiPlan = data.plan || null;
    els.geminiViralScore.textContent = state.geminiPlan?.viral_score ? `${state.geminiPlan.viral_score} / 100` : data.status === 'ready' ? 'Unavailable' : 'Pending';
    if (state.geminiPlan?.viral_score) els.orianeScoreRail.textContent = `${state.geminiPlan.viral_score}%`;
  } catch (error) {
    if (state.currentListing?.id === listing.id) els.geminiViralScore.textContent = 'Unavailable';
    console.error("Gemini plan error:", error);
  }
}

async function generateMissingTransitions() {
  const listing = state.currentListing;
  const model = els.geminiModelSelect.value;
  if (!listing || listing.source_backed || !model) return;
  els.btnGenerateMissing.disabled = true;
  els.btnGenerateMissing.textContent = "⏳ Submitting to Gemini...";
  let errorMessage;
  try {
    const rooms = listing.rooms || [];
    for (const transition of listing.transitions || []) {
      if (['ready', 'processing', 'queued', 'in_progress'].includes(transition.status)) continue;
      const fromRoom = rooms[transition.index];
      const toRoom = rooms[transition.index + 1];
      if (!fromRoom || !toRoom) continue;
      const response = await fetch("/api/gemini/generate-segment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          listing_id: listing.id,
          transition_index: transition.index,
          from_room: transition.from_room,
          to_room: transition.to_room,
          first_frame_url: fromRoom.image_url,
          last_frame_url: toRoom.image_url,
          prompt: transition.prompt,
          model,
        }),
      });
      if (!response.ok) throw new Error(`Generation blocked (HTTP ${response.status})`);
    }
    await refreshCurrentListingStatus();
    scheduleSegmentPolling();
  } catch (error) {
    errorMessage = error.message || 'Generation request failed';
    console.error('Gemini generation error:', error);
  } finally {
    els.btnGenerateMissing.disabled = false;
    els.btnGenerateMissing.textContent = errorMessage || "⚡ Generate / Refresh Gemini Room Transitions";
  }
}

async function refreshCurrentListingStatus() {
  state.listings = await loadFeedListings();
  if (!state.currentListing) return;
  const updated = state.listings.find((x) => x.id === state.currentListing.id);
  if (updated) {
    state.currentListing = updated;
    renderTransitionsList();
  }
}

function scheduleSegmentPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  let polling = false;
  let attempts = 0;
  const pending = status => ['processing', 'queued', 'in_progress'].includes(status);
  state.pollTimer = setInterval(async () => {
    const listing = state.currentListing;
    if (!listing || listing.source_backed || polling) return;
    if (attempts >= 60 || (!(listing.transitions || []).some(transition => pending(transition.status)) && !pending(listing.voiceover_status))) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      return;
    }
    polling = true;
    attempts++;
    try {
      const keys = (listing.transitions || []).filter(transition => pending(transition.status)).map(transition => `${listing.id}_seg${transition.index}`);
      if (pending(listing.voiceover_status)) keys.push(`vo_${listing.id}`);
      for (const key of keys) {
        const response = await fetch(`/api/gemini/poll/${encodeURIComponent(key)}`);
        if (!response.ok) throw new Error(`Gemini poll failed (HTTP ${response.status})`);
      }
      await refreshCurrentListingStatus();
    } catch (error) {
      console.error('Gemini status error:', error);
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    } finally {
      polling = false;
    }
  }, 5000);
}

function setupEventListeners() {
  setupSourceResearch();
  els.brandHomeBtn.onclick = () => returnToZipFeed();
  els.btnBackToFeed.onclick = (e) => {
    e.stopPropagation();
    returnToZipFeed();
  };

  // 4-Way Swipe Buttons & Gesture Setup
  setup4WaySwipeGestures();
  if (els.btnCompassLeft) els.btnCompassLeft.onclick = (e) => { e.stopPropagation(); flipToNextHouse(-1); };
  if (els.btnCompassRight) els.btnCompassRight.onclick = (e) => { e.stopPropagation(); flipToNextHouse(1); };
  if (els.btnCompassUp) els.btnCompassUp.onclick = (e) => { e.stopPropagation(); swipeSaveActiveHouse(); };
  if (els.btnCompassDown) els.btnCompassDown.onclick = (e) => { e.stopPropagation(); swipeHideActiveHouse(); };
  if (els.btnFlipSaveUp) els.btnFlipSaveUp.onclick = (e) => { e.stopPropagation(); swipeSaveActiveHouse(); };
  if (els.btnFlipHideDown) els.btnFlipHideDown.onclick = (e) => { e.stopPropagation(); swipeHideActiveHouse(); };
  if (els.btnRestoreHidden) {
    els.btnRestoreHidden.onclick = () => {
      state.hiddenIds.clear();
      applyZipFilterAndRenderFeed();
    };
  }

  // Flip Player Controls
  els.btnFlipPrev.onclick = (e) => {
    e.stopPropagation();
    flipToNextHouse(-1);
  };
  els.btnFlipNext.onclick = (e) => {
    e.stopPropagation();
    flipToNextHouse(1);
  };
  els.btnFlipThumbUp.onclick = (e) => {
    e.stopPropagation();
    const active = getActiveFlipListing();
    if (active) castRealtimeVote(active.id, "up");
  };
  els.btnFlipThumbDown.onclick = (e) => {
    e.stopPropagation();
    const active = getActiveFlipListing();
    if (active) castRealtimeVote(active.id, "down");
  };
  els.btnFlipComments.onclick = (e) => {
    e.stopPropagation();
    openOpenHouseDrawer(getActiveFlipListing());
  };
  els.flipLiveCommentTicker.onclick = (e) => {
    e.stopPropagation();
    openOpenHouseDrawer(getActiveFlipListing());
  };
  els.btnLaunchOpenhouseUpload.onclick = (e) => {
    e.stopPropagation();
    openOpenHouseDrawer(getActiveFlipListing());
  };
  els.btnTopOpenhouse.onclick = () => {
    openOpenHouseDrawer(state.stageMode === "feed" ? getActiveFlipListing() : state.currentListing);
  };
  els.btnStageOpenhouse.onclick = (e) => {
    e.stopPropagation();
    openOpenHouseDrawer(state.currentListing);
  };
  els.btnStageThumbUp.onclick = (e) => {
    e.stopPropagation();
    if (state.currentListing) castRealtimeVote(state.currentListing.id, "up");
  };
  els.btnStageThumbDown.onclick = (e) => {
    e.stopPropagation();
    if (state.currentListing) castRealtimeVote(state.currentListing.id, "down");
  };

  // Open House Drawer Controls
  els.btnCloseOpenhouse.onclick = () => els.openhouseDrawer.classList.add("hidden");
  els.btnDrawerVoteUp.onclick = () => {
    const l = state.currentListing || getActiveFlipListing();
    if (l) castRealtimeVote(l.id, "up");
  };
  els.btnDrawerVoteDown.onclick = () => {
    const l = state.currentListing || getActiveFlipListing();
    if (l) castRealtimeVote(l.id, "down");
  };
  els.ohFileInput.onchange = () => {
    const f = els.ohFileInput.files && els.ohFileInput.files[0];
    els.ohFileName.textContent = f ? f.name : "No file selected";
  };
  els.btnSubmitOpenhouse.onclick = () => submitOpenHouseCheckin();
  els.btnInstantDemoCheckin.onclick = () => triggerInstantDemoCheckin();

  // Sort Pills (Amazon x YouTube Hybrid, Upvotes, Stars)
  document.querySelectorAll(".sort-pill").forEach((pill) => {
    pill.onclick = () => {
      document.querySelectorAll(".sort-pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.sortBy = pill.dataset.sort || "hybrid";
      state.activeFlipIndex = 0;
      applyZipFilterAndRenderFeed();
    };
  });

  els.btnFlipSound.onclick = (e) => {
    e.stopPropagation();
    els.flipMainVideo.muted = !els.flipMainVideo.muted;
    els.flipSoundLabel.textContent = els.flipMainVideo.muted ? "Muted" : "Sound On";
  };
  els.btnFlipEnter3d.onclick = (e) => {
    e.stopPropagation();
    const active = getActiveFlipListing();
    if (active) openHouseAutoWalkthrough(active, true);
  };
  els.btnLaunchFullscreenWalk.onclick = (e) => {
    e.stopPropagation();
    const active = getActiveFlipListing();
    if (active) openHouseAutoWalkthrough(active, false);
  };
  els.flipVideoScrubber.oninput = (e) => {
    const listing = getActiveFlipListing();
    if (listing?.source_backed && !listing.preview_clip_url) {
      showSourcePhoto(listing, Math.round(Number(e.target.value) / 1000 * (listing.photos.length - 1)));
      return;
    }
    const dur = els.flipMainVideo.duration || 35;
    els.flipMainVideo.currentTime = (Number(e.target.value) / 1000) * dur;
  };

  let flipWheelLock = false;
  els.flipPlayerFrame.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      if (flipWheelLock) return;
      flipWheelLock = true;
      setTimeout(() => (flipWheelLock = false), 420);
      if (e.deltaY > 0) flipToNextHouse(1);
      else if (e.deltaY < 0) flipToNextHouse(-1);
    },
    { passive: false }
  );

  els.btnOpenArchDeck.onclick = () => els.archDeckModal.classList.remove("hidden");
  els.btnCloseArchDeck.onclick = () => els.archDeckModal.classList.add("hidden");

  document.querySelectorAll(".zip-pill").forEach((pill) => {
    pill.onclick = () => {
      document.querySelectorAll(".zip-pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.selectedZip = pill.dataset.zip || "ALL";
      state.activeFlipIndex = 0;
      if (state.stageMode !== "feed") {
        returnToZipFeed();
      }
      applyZipFilterAndRenderFeed();
    };
  });

  els.zipSearchInput.oninput = (e) => {
    state.searchQuery = e.target.value || "";
    state.activeFlipIndex = 0;
    if (state.stageMode !== "feed") {
      returnToZipFeed();
    }
    applyZipFilterAndRenderFeed();
  };

  els.btnSwitch3dMode.onclick = (e) => {
    e.stopPropagation();
    toggleStage2AndStage3();
  };

  els.btnPlayPause.onclick = (e) => {
    e.stopPropagation();
    toggleStage2AndStage3();
  };

  els.btnResumeFromVibe.onclick = (e) => {
    e.stopPropagation();
    resumeStage2AutoWalkthrough();
  };

  els.btnSubtleSpecs.onclick = (e) => {
    e.stopPropagation();
    enter3DDeepExploreMode();
  };

  els.btnToggleVibeDrawer.onclick = (e) => {
    e.stopPropagation();
    toggleStage2AndStage3();
  };

  els.btnToggleRadar.onclick = (e) => {
    e.stopPropagation();
    els.floatingRadar.classList.toggle("hidden");
  };

  els.btnToggleOriane.onclick = (e) => {
    e.stopPropagation();
    els.orianeDrawer.classList.toggle("hidden");
  };

  els.btnCloseOriane.onclick = () => {
    els.orianeDrawer.classList.add("hidden");
  };

  els.btnToggleRedfinPopover.onclick = () => {
    els.redfinPopover.classList.toggle("hidden");
  };

  els.btnPrevRoom.onclick = () => {
    stopAutoTour();
    if (state.currentRoomIndex > 0) {
      showRoomState(state.currentRoomIndex - 1, true);
      enter3DDeepExploreMode();
    }
  };

  els.btnNextRoom.onclick = () => {
    const rooms = state.currentListing.rooms || [];
    const nextIdx = (state.currentRoomIndex + 1) % rooms.length;
    startContinuousWalkthrough(nextIdx === 0 ? 0 : state.currentRoomIndex);
  };

  els.spatialScrubber.oninput = (e) => {
    stopAutoTour();
    state.stageMode = "explore_3d";
    els.btnSwitch3dMode.classList.add("active-3d");
    els.btnSwitch3dMode.innerHTML = "▶ Resume Auto Full-Screen Walkthrough";
    const val = Number(e.target.value);
    const rooms = state.currentListing.rooms || [];
    const maxSeg = Math.max(1, rooms.length - 1);
    const exactPos = (val / 1000) * maxSeg;
    const segIdx = Math.min(maxSeg - 1, Math.floor(exactPos));
    const frac = exactPos - segIdx;

    const seg = (state.currentListing.transitions || [])[segIdx];
    if (seg && seg.status === "ready" && seg.video_url) {
      if (!els.walkthroughVideo.src.endsWith(seg.video_url)) {
        els.walkthroughVideo.src = seg.video_url;
      }
      els.walkthroughVideo.pause();
      els.walkthroughVideo.classList.add("playing");
      const dur = els.walkthroughVideo.duration || 4;
      els.walkthroughVideo.currentTime = frac * dur;
      els.hudStateLabel.textContent = "STAGE 3 · 3D FRAME SCRUBBING · CLICK TO INSPECT HOTSPOTS";
    } else {
      showRoomState(Math.round(exactPos), true);
    }
  };

  window.addEventListener("keydown", (e) => {
    if (document.getElementById("source-research-dialog").open) {
      if (e.code === "Escape") { e.preventDefault(); closeSourceResearch(); }
      return;
    }
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (state.stageMode === "feed") {
      if (e.code === "ArrowRight" || e.code === "KeyD") {
        e.preventDefault();
        flipToNextHouse(1);
      } else if (e.code === "ArrowLeft" || e.code === "KeyA") {
        e.preventDefault();
        flipToNextHouse(-1);
      } else if (e.code === "ArrowUp" || e.code === "KeyW") {
        e.preventDefault();
        swipeSaveActiveHouse();
      } else if (e.code === "ArrowDown" || e.code === "KeyS") {
        e.preventDefault();
        swipeHideActiveHouse();
      }
    } else {
      if (e.code === "Escape") {
        returnToZipFeed();
      } else if (e.code === "Space") {
        e.preventDefault();
        toggleStage2AndStage3();
      }
    }
  });

  document.querySelectorAll(".aspect-pill").forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll(".aspect-pill").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.viewOrientation = btn.dataset.mode === "reel" ? "reel" : "gallery";

      applyZipFilterAndRenderFeed();

      if (state.viewOrientation === "reel") {
        els.stageFrame.classList.remove("mode-16-9");
        els.stageFrame.classList.add("mode-9-16");
      } else {
        els.stageFrame.classList.remove("mode-9-16");
        els.stageFrame.classList.add("mode-16-9");
      }
    };
  });

  els.btnImportRedfin.onclick = async () => {
    const url = els.redfinInput.value.trim();
    if (!url) return;
    els.btnImportRedfin.textContent = "Transforming...";
    try {
      const res = await fetch("/api/redfin/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Listing could not be imported.");
      if (data.viewer_url) {
        const id = new URL(data.viewer_url, location.origin).hash.slice(1);
        const listing = state.listings.find(home => home.id === id && home.source_backed);
        if (!listing) throw new Error("Source home is unavailable. Reload the feed and try again.");
        els.redfinPopover.classList.add("hidden");
        openSourceResearch(listing, listing.model ? "model" : "evidence");
        return;
      }
      if (data.listing) {
        const exists = state.listings.find((x) => x.id === data.listing.id);
        if (!exists) state.listings.unshift(data.listing);
        els.redfinPopover.classList.add("hidden");
        applyZipFilterAndRenderFeed();
        await openHouseAutoWalkthrough(data.listing, false);
      }
    } catch (error) {
      alert(error.message);
    } finally {
      els.btnImportRedfin.textContent = "Transform Space →";
    }
  };

  els.btnPlayVo.onclick = (e) => {
    e.stopPropagation();
    if (!els.voAudioPlayer.paused) {
      els.voAudioPlayer.pause();
      els.voRailLabel.textContent = "Voice";
      return;
    }
    if (state.currentListing && state.currentListing.voiceover_url) {
      els.voAudioPlayer.src = state.currentListing.voiceover_url;
      els.voAudioPlayer.play();
      els.voRailLabel.textContent = "Playing";
      els.voAudioPlayer.onended = () => (els.voRailLabel.textContent = "Voice");
    } else if ("speechSynthesis" in window && state.currentListing) {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(state.currentListing.voiceover_script);
      window.speechSynthesis.speak(u);
    }
  };

  els.btnGenerateMissing.onclick = () => generateMissingTransitions();

  els.btnDownloadVideo.onclick = (e) => {
    e.stopPropagation();
    const l = state.currentListing;
    els.exportVideoLinks.innerHTML = "";
    const fullRow = document.createElement("div");
    fullRow.className = "export-link-item";
    fullRow.style.borderColor = "rgba(235, 195, 136, 0.5)";
    fullRow.style.background = "rgba(235, 195, 136, 0.1)";
    fullRow.innerHTML = `
      <span><strong>🎬 Full 35s–43s Stitched Viral Walkthrough + AI Voiceover (MP4)</strong></span>
      <a href="${l.full_tour_url || "/api/cache/tour_36s_palo_alto_94301.mp4"}" download="EstateFlow_${l.id}_35s_Viral.mp4">⬇ Download MP4</a>
    `;
    els.exportVideoLinks.appendChild(fullRow);

    (l.transitions || []).forEach((t, idx) => {
      const row = document.createElement("div");
      row.className = "export-link-item";
      row.innerHTML = `
        <span>0${idx + 1} · ${t.title}</span>
        ${
          t.video_url
            ? `<a href="${t.video_url}" download="EstateFlow_${l.id}_seg${idx + 1}.mp4">⬇ MP4</a>`
            : `<span>Generating...</span>`
        }
      `;
      els.exportVideoLinks.appendChild(row);
    });
    const caption =
      (state.geminiPlan && state.geminiPlan.compound_caption) ||
      `What does ${l.price} feel like at golden hour in ${l.neighborhood}? Smooth 3D walkthrough from courtyard to zero-edge pool ✨🏡 #HackTheFeed #RealEstate #HouseTour #LuxuryHomes`;
    els.exportCaptionBox.value = caption;
    els.exportModal.classList.remove("hidden");
  };

  els.btnCloseModal.onclick = () => els.exportModal.classList.add("hidden");
  els.btnCopyCaption.onclick = () => {
    navigator.clipboard.writeText(els.exportCaptionBox.value);
    els.btnCopyCaption.textContent = "✓ Copied!";
    setTimeout(() => (els.btnCopyCaption.textContent = "Copy Viral Caption"), 1800);
  };
}

initApp().catch(error => { document.getElementById("feed-load-message").textContent = error.message; });
