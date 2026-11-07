// Source-backed homes use the existing reel layout and a separate research layer.
let sourceSlideTimer;
let sourcePhotoIndex = 0;
let sourcePhotoListingId;
let researchReturnFocus;
let researchResumeVideos = [];
const sourceAssetURL = photo => `/api/faithful/assets/${photo.path.split('/').at(-1)}`;

function setSourceFeedControls(source) {
  els.flipPlayerFrame.classList.toggle('source-backed', source);
  document.getElementById('flip-source-photo').classList.toggle('hidden', !source);
  els.flipMainVideo.classList.toggle('hidden', source);
  for (const button of [els.btnFlipThumbUp, els.btnFlipThumbDown, els.btnFlipSound]) button.classList.toggle('hidden', source);
  els.btnTopOpenhouse.textContent = source ? 'Sources & verification' : '🔴 Live Open House & Rank';
  els.btnLaunchOpenhouseUpload.textContent = source ? 'Original photos & sources' : '📸 Post Open House Video/Photo';
  if (!source) {
    els.flipVideoScrubber.disabled = false;
    els.btnLaunchFullscreenWalk.textContent = '🎬 Full-Screen Walkthrough →';
    els.btnFlipEnter3d.querySelector('span').textContent = '3D Tour';
  }
}

function showSourcePhoto(listing, index) {
  sourcePhotoIndex = Math.max(0, Math.min(index, listing.photos.length - 1));
  const image = document.getElementById('flip-source-photo');
  image.src = sourceAssetURL(listing.photos[sourcePhotoIndex]);
  image.alt = `${listing.address}, original photo ${sourcePhotoIndex + 1}`;
  els.flipTimeReadout.textContent = `Photo ${sourcePhotoIndex + 1} / ${listing.photos.length}`;
  els.flipVideoScrubber.value = listing.photos.length > 1 ? Math.round(sourcePhotoIndex / (listing.photos.length - 1) * 1000) : 0;
  els.flipVideoScrubber.disabled = listing.photos.length < 2;
}

function startSourcePhotos(listing) {
  clearInterval(sourceSlideTimer);
  if (listing.photos.length < 2) return;
  sourceSlideTimer = setInterval(() => {
    if (state.stageMode === 'feed' && getActiveFlipListing()?.id === listing.id) {
      showSourcePhoto(listing, (sourcePhotoIndex + 1) % listing.photos.length);
    }
  }, 5000);
}

function renderSourceReel(listing) {
  els.flipMainVideo.pause();
  els.flipMainVideo.removeAttribute('src');
  els.flipMainVideo.load();
  els.flipMainVideo.ontimeupdate = null;
  els.flipPlayerFrame.className = `flip-player-frame source-backed ${state.viewOrientation === 'reel' ? 'mode-9-16' : 'mode-16-9'}`;
  els.flipPlayerFrame.dataset.listingId = listing.id;
  els.flipZipBadge.textContent = `#${state.activeFlipIndex + 1} · 94404 · ${listing.city}`;
  els.flipDurationBadge.textContent = listing.model ? '3D walkthrough available' : 'Original photos';
  els.flipTickerText.textContent = listing.model ? 'Explore the floor-plan model, then compare the original photos.' : 'Explore original photos and listing sources. A 3D model needs a floor plan.';
  els.flipNeighborhood.textContent = `${listing.city} · ${listing.listing_status === 'coming_soon' ? 'Coming soon' : 'For sale'}`;
  els.flipHookTitle.textContent = listing.title;
  els.flipSubtleSpecs.textContent = `${listing.price} · ${listing.beds} bd · ${listing.baths} ba · ${listing.sqft.toLocaleString()} sq ft`;
  els.flipCommentsCount.textContent = 'Sources';
  els.btnLaunchFullscreenWalk.textContent = listing.model ? '🧭 3D walkthrough & research' : 'Explore this home';
  els.btnFlipEnter3d.querySelector('span').textContent = listing.model ? '3D Walk' : 'Research';
  els.btnFlipEnter3d.title = listing.model ? 'Open the 3D walkthrough and in-depth research' : 'Open photos, sources and model availability';
  els.btnFlipSaveUp.classList.toggle('is-saved', state.savedIds.has(listing.id));
  els.flipSaveLabel.textContent = state.savedIds.has(listing.id) ? 'Saved 💛' : 'Save ▲';
  if (sourcePhotoListingId !== listing.id) { sourcePhotoIndex = 0; sourcePhotoListingId = listing.id; }
  showSourcePhoto(listing, sourcePhotoIndex);
  startSourcePhotos(listing);
}

function renderSourceCard(listing, index) {
  const card = document.createElement('article');
  card.className = `feed-house-card source-house-card${index === state.activeFlipIndex ? ' active-flip-card' : ''}`;
  card.dataset.listingId = listing.id;
  const image = document.createElement('img');
  image.className = 'feed-card-poster'; image.src = sourceAssetURL(listing.photos[0]); image.alt = listing.address;
  const shade = document.createElement('div'); shade.className = 'feed-card-shade';
  const top = document.createElement('div'); top.className = 'feed-card-top';
  const badge = document.createElement('span'); badge.className = 'feed-zip-badge'; badge.textContent = `#${index + 1} · 94404 · Source photos`;
  top.append(badge);
  const bottom = document.createElement('div'); bottom.className = 'feed-card-bottom';
  const title = document.createElement('h3'); title.className = 'feed-card-hook'; title.textContent = listing.title;
  const specs = document.createElement('p'); specs.className = 'feed-card-subtle-meta'; specs.textContent = `${listing.price} · ${listing.beds} bd · ${listing.sqft.toLocaleString()} sq ft`;
  const action = document.createElement('button'); action.className = 'btn-3d-explore source-research-button';
  action.textContent = listing.model ? '🧭 3D walkthrough + research' : 'Photos + research';
  action.onclick = event => { event.stopPropagation(); state.activeFlipIndex = index; renderFlipReelPlayer(); highlightActiveCardInGrid(); openSourceResearch(listing, listing.model ? 'model' : 'photos'); };
  bottom.append(title, specs, action);card.append(image, shade, top, bottom);
  card.onclick = () => {
    if (state.activeFlipIndex === index) { openSourceResearch(listing, listing.model ? 'model' : 'photos'); return; }
    state.activeFlipIndex = index;renderFlipReelPlayer();highlightActiveCardInGrid();
  };
  card.tabIndex = 0;card.setAttribute('aria-label', `${listing.title}, ${listing.price}. Explore home`);
  card.onkeydown = event => { if (event.target === card && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); card.click(); } };
  els.zipFeedGrid.append(card);
}

function openSourceResearch(listing, requestedView = 'model') {
  const dialog = document.getElementById('source-research-dialog');
  const frame = document.getElementById('source-research-frame');
  researchReturnFocus = document.activeElement;
  els.flipPlayerFrame.style.transform = '';
  researchResumeVideos = [...document.querySelectorAll('#zip-feed-stage video')].filter(video => !video.paused);
  els.walkthroughVideo.pause();
  els.voAudioPlayer.pause();
  researchResumeVideos.forEach(video => video.pause());
  clearInterval(sourceSlideTimer);stopAutoTour();
  state.stageMode = 'research';state.currentListing = listing;
  const supportedView = ['model','photos','plan','evidence'].includes(requestedView) ? requestedView : 'model';
  const view = supportedView === 'model' && !listing.model ? 'evidence' : supportedView;
  const standalone = `/94404?view=${view}#${encodeURIComponent(listing.id)}`;
  document.getElementById('research-heading').textContent = listing.title;
  document.getElementById('research-new-tab').href = standalone;
  frame.src = `/94404?embed=1&view=${view}#${encodeURIComponent(listing.id)}`;
  if (!dialog.open) dialog.showModal();
  document.getElementById('research-back').focus();
}

function closeSourceResearch() {
  const dialog = document.getElementById('source-research-dialog');
  if (dialog.open) dialog.close();
}

function setupSourceResearch() {
  const dialog = document.getElementById('source-research-dialog');
  document.getElementById('research-back').onclick = closeSourceResearch;
  document.getElementById('btn-open-available-3d').onclick = () => {
    const index = state.filteredListings.findIndex(home => home.source_backed && home.model);
    if (index < 0) return;
    state.activeFlipIndex = index;renderFlipReelPlayer();highlightActiveCardInGrid();
    openSourceResearch(state.filteredListings[index], 'model');
  };
  dialog.addEventListener('close', () => {
    document.getElementById('source-research-frame').src = 'about:blank';
    const url = new URL(location.href);url.searchParams.delete('home');url.searchParams.delete('view');history.replaceState(null, '', url);
    state.stageMode = 'feed';
    els.walkthroughStage.classList.add('hidden');
    els.zipFeedStage.classList.remove('hidden');
    state.currentListing = getActiveFlipListing();
    renderFlipReelPlayer();
    researchResumeVideos.forEach(video => { if (video.isConnected) video.play().catch(() => {}); });
    const active = getActiveFlipListing();if (active?.source_backed) startSourcePhotos(active);
    if (researchReturnFocus?.isConnected) researchReturnFocus.focus();
  });
  window.addEventListener('message', event => {
    if (event.origin === location.origin && event.source === document.getElementById('source-research-frame').contentWindow && event.data?.type === 'homi-research-close') closeSourceResearch();
  });
}
