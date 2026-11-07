const $ = (id) => document.getElementById(id);
let manifest, current, photoIndex = 0, mode = 'photos', timer, modelViewer;
const money = new Intl.NumberFormat('en-US', {style:'currency', currency:'USD', maximumFractionDigits:0});
const assetURL = (photo) => `/api/faithful/assets/${photo.path.split('/').at(-1)}`;
const make = (tag, text, cls) => { const node = document.createElement(tag); if (text) node.textContent=text; if (cls) node.className=cls; return node; };
function stop(){clearInterval(timer);timer=undefined;$('play').textContent='Play photo sequence';}
function showPhoto(index){
  photoIndex=(index+current.photos.length)%current.photos.length;
  const photo=current.photos[photoIndex];
  $('photo-error').hidden=true;$('photo').hidden=false;
  $('photo').src=assetURL(photo);$('photo').alt=`${current.address}, original listing photo ${photoIndex+1}`;
  $('counter').textContent=`${photoIndex+1} / ${current.photos.length}`;
  $('source-image').href=photo.source_url;
  document.querySelectorAll('.thumbnail').forEach((button,i)=>button.setAttribute('aria-current',String(i===photoIndex)));
  $('prev').disabled=$('next').disabled=$('play').disabled=current.photos.length<2;
}
function evidence(){
  const root=$('evidence');root.replaceChildren();
  const block=(title, paragraphs)=>{const section=make('div',null,'evidence-block');section.append(make('h3',title));for(const text of paragraphs)section.append(make('p',text));root.append(section);return section;};
  block('Selection coverage',[manifest.selection, `${manifest.summary.unfilled_selection_slots} of ${manifest.requested_count} requested selection slots remain unfilled. Pending, sold, condo and townhouse properties are excluded.`]);
  block('Conversion status',[current.blocker, 'A preserved photo and a plan extrusion do not establish the fidelity of a photorealistic 3D walkthrough. No home in this batch has passed that verification.']);
  block('Original-photo integrity',[`${current.photos.length} images retain their acquisition SHA-256 hashes. The viewer serves the same files; no retouching, generative replacement, warping or morphing is applied.`, 'Display resizing preserves aspect ratio and includes the full image. Hash checks prove integrity since acquisition, not ownership, room adjacency or the absence of staging in the listing itself.']);
  if(current.model){
    const section=block('Floor-plan model',[...current.model.assumptions, 'The exported box footprint matches the extracted raster mask. This export check is not an independent validation of the mask against the building.', 'Magenta marks extracted linework over the source plan; inspect fixtures and omitted thin lines before relying on the model.']);
    const image=make('img');image.src=current.model.overlay_url;image.alt='Extracted wall mask in magenta over the source plan';section.append(image);
  }
  block('Evidence needed to complete 3D verification',['A measured floor plan (all floors), camera-to-room correspondences, calibrated reference views, and review of doors, windows, materials and novel views. Unseen surfaces must remain unknown until supported by evidence.']);
  const provenance=block('Source and capture',[manifest.selection, `Snapshot date: ${manifest.snapshot_date} (${manifest.snapshot_timezone}). Prices and availability may change.`]);
  const link=make('a','Open this Redfin listing');link.href=current.redfin_url;link.target='_blank';link.rel='noopener';provenance.append(link);
  const details=make('details');details.append(make('summary','Asset hashes and original URLs'));
  for(const photo of current.photos){const p=make('p',`Photo ${photo.index+1} `);const a=make('a','Source');a.href=photo.source_url;a.target='_blank';a.rel='noopener';p.append(a,make('br'),make('code',photo.sha256));details.append(p);}provenance.append(details);
}
async function view(next){
  stop();mode=next;
  document.querySelectorAll('[role=tabpanel]').forEach(panel=>panel.hidden=panel.id!==mode);
  document.querySelectorAll('[role=tab]').forEach(tab=>tab.setAttribute('aria-selected',String(tab.dataset.view===mode)));
  if(mode==='model'&&current.model){
    if(!modelViewer){try{const module=await import('./model-viewer.js');modelViewer=new module.PlanViewer($('canvas-wrap'),$('minimap'));}catch(error){$('canvas-wrap').textContent='3D rendering is unavailable in this browser. Open the source plan or try a browser with WebGL support.';return;}}
    try{await modelViewer.load(current);}catch(error){$('model-help').textContent=`Model could not load: ${error.message}`;}
  }
  modelViewer?.setActive(mode==='model');
}
function choose(listing){
  stop();current=listing;photoIndex=0;location.hash=listing.id;
  $('tour').hidden=false;$('address').textContent=listing.address.split(',')[0];
  $('specs').textContent=`${money.format(listing.price)}   ·   ${listing.beds} beds   ·   ${listing.baths} baths   ·   ${listing.sqft.toLocaleString()} sq ft   ·   ${listing.listing_status==='coming_soon'?'Coming soon':'For sale'}`;
  $('listing-link').href=listing.redfin_url;
  $('notice').textContent=listing.model?'Plan-based 3D schematic available. Photorealistic reconstruction is unverified.':'Photo sequence available. 3D conversion is blocked until a usable floor plan is supplied.';
  $('model-tab').disabled=$('plan-tab').disabled=!listing.model;
  if(listing.model)$('plan-image').src=assetURL(listing.photos[listing.model.floor_plan_index]);
  document.querySelectorAll('.home').forEach(button=>button.setAttribute('aria-current',String(button.dataset.id===listing.id)));
  $('thumbnails').replaceChildren(...listing.photos.map((photo,i)=>{const button=make('button',null,'thumbnail');button.setAttribute('aria-label',`View original photo ${i+1}`);const img=make('img');img.src=assetURL(photo);img.alt='';img.loading='lazy';button.append(img);button.onclick=()=>{stop();showPhoto(i);};return button;}));
  showPhoto(0);evidence();view('photos');
}
$('photo').onerror=()=>{$('photo').hidden=true;$('photo-error').hidden=false;};
$('prev').onclick=()=>{stop();showPhoto(photoIndex-1);};$('next').onclick=()=>{stop();showPhoto(photoIndex+1);};
$('play').onclick=()=>{if(timer){stop();return;}$('play').textContent='Pause photo sequence';timer=setInterval(()=>showPhoto(photoIndex+1),5000);};
document.querySelectorAll('[role=tab]').forEach(button=>button.onclick=()=>view(button.dataset.view));
$('orbit').onclick=()=>modelViewer?.orbit();$('walk').onclick=()=>{modelViewer?.walk();$('canvas-wrap').focus();};$('reset').onclick=()=>modelViewer?.reset();
$('guide').onclick=()=>modelViewer?.guide();
$('export-model').onclick=()=>modelViewer?.downloadGLTF();
document.querySelectorAll('[data-move]').forEach(button=>button.onclick=()=>modelViewer?.nudge(button.dataset.move));
document.addEventListener('keydown',event=>{if(mode==='photos'&&!['INPUT','TEXTAREA','BUTTON'].includes(document.activeElement.tagName)){if(event.key==='ArrowRight')showPhoto(photoIndex+1);if(event.key==='ArrowLeft')showPhoto(photoIndex-1);}});
try{
  const response=await fetch('/api/faithful/94404');if(!response.ok)throw new Error(`Server returned ${response.status}`);manifest=await response.json();
  $('selection-note').textContent=`Target: ${manifest.requested_count} highest-priced single-family houses. ${manifest.summary.homes} eligible listings verified; full market ranking remains unverified.`;
  $('batch-summary').textContent=`${manifest.summary.original_images} source images preserved · ${manifest.summary.schematic_models} schematic model · ${manifest.summary.needs_floor_plan} homes need plans · ${manifest.summary.unfilled_selection_slots} selection slots unfilled · 0 verified photorealistic conversions`;
  for(const listing of manifest.listings){const button=make('button',null,'home');button.dataset.id=listing.id;const img=make('img');img.src=assetURL(listing.photos[0]);img.alt='';const text=make('span');text.append(make('strong',listing.address.split(',')[0]),make('small',`${money.format(listing.price)} · ${listing.model?'3D schematic':'Needs floor plan'}`));button.append(make('span',String(listing.rank),'rank'),img,text);button.onclick=()=>choose(listing);$('homes').append(button);}
  $('loading').hidden=true;choose(manifest.listings.find(l=>`#${l.id}`===location.hash)||manifest.listings[0]);
}catch(error){$('loading').textContent=`Tours could not load. ${error.message}. Run python scripts/build_94404.py --download, then reload.`;}
