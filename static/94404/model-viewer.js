import * as THREE from '/static/vendor/three-0.170.0.module.min.js';

export class PlanViewer {
  constructor(container,minimap){
    this.container=container;this.minimap=minimap;this.active=false;this.keys=new Set();
    this.renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));container.replaceChildren(this.renderer.domElement);
    this.scene=new THREE.Scene();this.scene.background=new THREE.Color('#dfe8f2');
    this.camera=new THREE.PerspectiveCamera(48,1,1,6000);
    this.scene.add(new THREE.HemisphereLight(0xffffff,0x7891a8,2.5));
    const sun=new THREE.DirectionalLight(0xffffff,2);sun.position.set(-200,900,500);this.scene.add(sun);
    this.group=new THREE.Group();this.scene.add(this.group);
    this.pointer=null;
    container.addEventListener('pointerdown',event=>{this.pointer={x:event.clientX,y:event.clientY};container.setPointerCapture(event.pointerId);container.focus();});
    container.addEventListener('pointermove',event=>{
      if(!this.pointer)return;const dx=event.clientX-this.pointer.x,dy=event.clientY-this.pointer.y;
      this.yaw-=dx*.007;
      if(this.navigation==='walk')this.pitch=THREE.MathUtils.clamp(this.pitch-dy*.005,-1.1,1.1);
      else this.elevation=THREE.MathUtils.clamp(this.elevation+dy*.005,.15,1.5);
      this.pointer={x:event.clientX,y:event.clientY};this.updateCamera();
    });
    const release=()=>{this.pointer=null;};container.addEventListener('pointerup',release);container.addEventListener('pointercancel',release);
    container.addEventListener('wheel',event=>{if(this.navigation!=='orbit')return;event.preventDefault();this.distance=THREE.MathUtils.clamp(this.distance*Math.exp(event.deltaY*.001),150,2800);this.updateCamera();},{passive:false});
    container.addEventListener('keydown',event=>{if(['w','a','s','d','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();this.keys.add(event.key);}});
    container.addEventListener('keyup',event=>this.keys.delete(event.key));container.addEventListener('blur',()=>this.keys.clear());
    window.addEventListener('blur',()=>this.keys.clear());
    minimap.addEventListener('click',event=>{
      if(!this.model)return;const rect=minimap.getBoundingClientRect();
      const x=(event.clientX-rect.left)*this.model.width/rect.width,z=(event.clientY-rect.top)*this.model.height/rect.height;
      if(this.canStand(x,z)){this.guided=false;this.position.set(x,this.model.eye_height_pixels,z);this.navigation='walk';this.pitch=0;this.updateCamera();}
    });
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(container);
    this.lastTime=performance.now();this.renderer.setAnimationLoop(time=>{
      const delta=Math.min((time-this.lastTime)/1000,.04);this.lastTime=time;
      if(!this.active||!this.model)return;
      if(this.guided){this.advanceGuide(delta);}
      if(this.navigation==='walk'&&!this.guided){
        let forward=Number(this.keys.has('w')||this.keys.has('ArrowUp'))-Number(this.keys.has('s')||this.keys.has('ArrowDown'));
        let side=Number(this.keys.has('d'))-Number(this.keys.has('a'));
        if(this.keys.has('ArrowLeft'))this.yaw+=delta*1.6;if(this.keys.has('ArrowRight'))this.yaw-=delta*1.6;
        if(forward||side){const norm=Math.hypot(forward,side);forward/=norm;side/=norm;this.move((Math.sin(this.yaw)*forward+Math.cos(this.yaw)*side)*80*delta,(-Math.cos(this.yaw)*forward+Math.sin(this.yaw)*side)*80*delta);}
        this.updateCamera();
      }
      this.renderer.render(this.scene,this.camera);
    });
  }
  resize(){const w=this.container.clientWidth,h=this.container.clientHeight;if(!w||!h)return;this.renderer.setSize(w,h,false);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();if(this.model&&this.position)this.updateCamera();}
  setActive(active){this.active=active;if(active)this.resize();else this.keys.clear();}
  async load(listing){
    if(this.listingId===listing.id){this.resize();return;}
    const response=await fetch(listing.model.url);if(!response.ok)throw new Error('Model download failed');
    const model=await response.json();this.model=model;this.listingId=listing.id;
    this.group.traverse(object=>{object.geometry?.dispose();if(object.material){object.material.map?.dispose();object.material.dispose();}});this.group.clear();
    const geometry=new THREE.BoxGeometry(1,1,1),material=new THREE.MeshStandardMaterial({color:'#ebeff5',roughness:.85});
    const walls=new THREE.InstancedMesh(geometry,material,model.wall_rectangles.length);const transform=new THREE.Object3D();
    model.wall_rectangles.forEach(([x,z,w,d],i)=>{transform.position.set(x+w/2,model.wall_height_pixels/2,z+d/2);transform.scale.set(w,model.wall_height_pixels,d);transform.updateMatrix();walls.setMatrixAt(i,transform.matrix);});
    walls.instanceMatrix.needsUpdate=true;this.group.add(walls);
    const photo=listing.photos[listing.model.floor_plan_index];const image=new Image();image.src=`/api/faithful/assets/${photo.path.split('/').at(-1)}`;await image.decode();
    const crop=document.createElement('canvas');crop.width=model.width;crop.height=model.height;
    crop.getContext('2d').drawImage(image,model.crop[0],model.crop[1],model.width,model.height,0,0,model.width,model.height);
    this.planCanvas=crop;this.minimap.width=model.width;this.minimap.height=model.height;
    const texture=new THREE.CanvasTexture(crop);texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=this.renderer.capabilities.getMaxAnisotropy();
    const floor=new THREE.Mesh(new THREE.PlaneGeometry(model.width,model.height),new THREE.MeshBasicMaterial({map:texture,side:THREE.DoubleSide}));floor.rotation.x=-Math.PI/2;floor.position.set(model.width/2,-.5,model.height/2);this.group.add(floor);
    this.container.dataset.modelState='ready';this.container.dataset.wallBoxes=String(model.wall_rectangles.length);
    this.reset();
  }
  reset(){if(!this.model)return;this.yaw=.65;this.pitch=0;this.elevation=.95;this.distance=Math.max(this.model.width,this.model.height)*1.6;this.position=new THREE.Vector3(420,this.model.eye_height_pixels,385);this.guided=false;this.navigation='orbit';this.updateCamera();this.resize();}
  orbit(){this.guided=false;this.navigation='orbit';this.elevation=.95;this.updateCamera();}
  walk(){this.guided=false;this.navigation='walk';this.pitch=0;this.yaw=0;this.updateCamera();}
  guide(){
    this.walk();this.position.set(420,this.model.eye_height_pixels,385);
    this.waypoints=[[330,290],[260,290],[260,220],[300,180],[300,100],[420,100],[450,110]];
    this.guided=true;this.container.dataset.guideState='playing';
  }
  advanceGuide(delta){
    const [x,z]=this.waypoints[0],dx=x-this.position.x,dz=z-this.position.z,distance=Math.hypot(dx,dz);
    if(distance<2){this.waypoints.shift();if(!this.waypoints.length){this.guided=false;this.container.dataset.guideState='complete';}return;}
    const step=Math.min(distance,75*delta);this.yaw=Math.atan2(dx,-dz);
    const before=this.position.clone();this.move(dx/distance*step,dz/distance*step);
    if(before.distanceTo(this.position)<.001){this.guided=false;this.container.dataset.guideState='blocked';}
    this.updateCamera();
  }
  updateCamera(){
    if(!this.model)return;
    if(this.navigation==='walk'){
      this.camera.position.copy(this.position);const direction=new THREE.Vector3(Math.sin(this.yaw)*Math.cos(this.pitch),Math.sin(this.pitch),-Math.cos(this.yaw)*Math.cos(this.pitch));this.camera.lookAt(this.position.clone().add(direction));
    }else{
      const target=new THREE.Vector3(this.model.width/2,15,this.model.height/2);
      const viewDistance=this.distance/Math.min(1,this.camera.aspect);
      this.camera.position.set(target.x+Math.sin(this.yaw)*viewDistance*Math.cos(this.elevation),Math.sin(this.elevation)*viewDistance,target.z+Math.cos(this.yaw)*viewDistance*Math.cos(this.elevation));this.camera.lookAt(target);
    }
    const context=this.minimap.getContext('2d');if(this.planCanvas)context.drawImage(this.planCanvas,0,0);
    if(this.navigation==='walk'){
      context.fillStyle='#145db2';context.beginPath();context.arc(this.position.x,this.position.z,8,0,Math.PI*2);context.fill();context.strokeStyle='#145db2';context.lineWidth=3;context.beginPath();context.moveTo(this.position.x,this.position.z);context.lineTo(this.position.x+Math.sin(this.yaw)*25,this.position.z-Math.cos(this.yaw)*25);context.stroke();
    }
    this.container.dataset.navigation=this.navigation;this.container.dataset.cameraX=this.camera.position.x.toFixed(2);this.container.dataset.cameraZ=this.camera.position.z.toFixed(2);
  }
  canStand(x,z){
    // Inspected outer footprint of the same source plan, in source-image pixels.
    const outline=[[384,83],[774,83],[774,31],[897,31],[897,583],[812,583],[812,614],[735,614],[735,481],[662,481],[662,568],[620,568],[620,814],[384,814]].map(([px,py])=>[px-this.model.crop[0],py-this.model.crop[1]]);
    let inside=false;
    for(let i=0,j=outline.length-1;i<outline.length;j=i++){
      const [xi,zi]=outline[i],[xj,zj]=outline[j];if((zi>z)!==(zj>z)&&x<(xj-xi)*(z-zi)/(zj-zi)+xi)inside=!inside;
    }
    if(!inside)return false;
    return !this.model.wall_rectangles.some(([wx,wz,w,d])=>x>wx-4&&x<wx+w+4&&z>wz-4&&z<wz+d+4);
  }
  move(dx,dz){
    const steps=Math.ceil(Math.hypot(dx,dz)/2)||1;
    for(let i=0;i<steps;i++){
      const nx=this.position.x+dx/steps,nz=this.position.z+dz/steps;
      if(this.canStand(nx,this.position.z))this.position.x=nx;
      if(this.canStand(this.position.x,nz))this.position.z=nz;
    }
  }
  nudge(direction){if(!this.model)return;if(this.navigation!=='walk')this.walk();if(direction==='left')this.yaw+=.2;else if(direction==='right')this.yaw-=.2;else{const distance=direction==='forward'?14:-14;this.move(Math.sin(this.yaw)*distance,-Math.cos(this.yaw)*distance);}this.updateCamera();}
  downloadGLTF(){
    // Explicit node transforms produce a portable glTF without generated textures.
    const m=this.model;if(!m)return;
    const vertices=new Float32Array([-0.5,-0.5,-0.5,.5,-.5,-.5,.5,.5,-.5,-.5,.5,-.5,-.5,-.5,.5,.5,-.5,.5,.5,.5,.5,-.5,.5,.5]);
    const indices=new Uint16Array([0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,3,7,6,3,6,2,1,2,6,1,6,5,0,4,7,0,7,3]);
    const bytes=new Uint8Array(vertices.byteLength+indices.byteLength);bytes.set(new Uint8Array(vertices.buffer));bytes.set(new Uint8Array(indices.buffer),vertices.byteLength);
    let binary='';for(const value of bytes)binary+=String.fromCharCode(value);
    const nodes=m.wall_rectangles.map(([x,z,w,d])=>({mesh:0,translation:[x+w/2,m.wall_height_pixels/2,z+d/2],scale:[w,m.wall_height_pixels,d]}));
    const gltf={asset:{version:'2.0',generator:'homi source-plan schematic'},extras:{source:m.source_image,assumptions:m.assumptions,units:'source plan pixels; uncalibrated'},scene:0,scenes:[{nodes:nodes.map((_,i)=>i)}],nodes,
      meshes:[{primitives:[{attributes:{POSITION:0},indices:1,material:0}]}],materials:[{pbrMetallicRoughness:{baseColorFactor:[.92,.94,.97,1],metallicFactor:0,roughnessFactor:.85},doubleSided:true}],
      buffers:[{uri:`data:application/octet-stream;base64,${btoa(binary)}`,byteLength:bytes.length}],bufferViews:[{buffer:0,byteOffset:0,byteLength:vertices.byteLength,target:34962},{buffer:0,byteOffset:vertices.byteLength,byteLength:indices.byteLength,target:34963}],
      accessors:[{bufferView:0,componentType:5126,count:8,type:'VEC3',min:[-.5,-.5,-.5],max:[.5,.5,.5]},{bufferView:1,componentType:5123,count:36,type:'SCALAR'}]};
    const url=URL.createObjectURL(new Blob([JSON.stringify(gltf)],{type:'model/gltf+json'}));const a=document.createElement('a');a.href=url;a.download='140-spinnaker-schematic.gltf';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
}
