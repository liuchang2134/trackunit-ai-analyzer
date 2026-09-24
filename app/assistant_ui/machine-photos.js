/* Official model illustrations, independent of machine telemetry and diagnosis. */
const MachinePhotos = (() => {
  const catalog = Object.freeze({
    XC948U: {file:'xc948u-cutout.png',type:'轮式装载机',page:'wheel-loaders/xc948u/',width:1504,height:1046},
    XE55U: {file:'xe55u-cutout.png',type:'履带式挖掘机',page:'excavators/xe55u/',width:1504,height:1046},
    XE80U: {file:'xe80u-cutout.png',type:'履带式挖掘机',page:'excavators/xe80u/',width:1505,height:1045},
    XE135U: {file:'xe135u.png',type:'履带式挖掘机',page:'excavators/xe135u-2/',width:771,height:1024},
  });
  function lookup(model) {
    const key=String(model ?? '').normalize('NFKC').trim().toUpperCase();
    return Object.prototype.hasOwnProperty.call(catalog,key)?{...catalog[key],model:key}:null;
  }
  function create(model,{thumbnail=false,onError=()=>{}}={}) {
    const photo=lookup(model);
    if(!photo)return null;
    const figure=document.createElement('figure');
    figure.className=thumbnail?'machine-photo machine-photo-thumb':'machine-photo';
    const img=document.createElement('img');
    img.src=`assets/machines/${photo.file}`;
    img.alt=`${photo.model} ${photo.type} · 基于官网机型图的透明背景展示图`;
    img.width=photo.width;img.height=photo.height;
    img.decoding='async';img.loading=thumbnail?'lazy':'eager';
    img.addEventListener('error',()=>{
      if(!figure.isConnected)return;
      figure.hidden=true;onError();
    });
    figure.append(img);
    if(!thumbnail){
      const caption=document.createElement('figcaption'),link=document.createElement('a');
      link.href=`https://xcmg-usa.com/products/${photo.page}`;
      link.target='_blank';link.rel='noopener noreferrer';link.referrerPolicy='no-referrer';
      link.textContent='官网机型图 ↗';
      link.setAttribute('aria-label',`查看徐工官网 ${photo.model} 产品页`);
      caption.append(link);figure.append(caption);
    }
    return figure;
  }
  function renderDevice(machine) {
    const host=document.getElementById('device-photo');
    if(!host)return;
    host.replaceChildren();host.hidden=true;
    host.parentElement.dataset.photo='false';
    const figure=create(machine?.model,{onError:()=>{
      host.hidden=true;host.parentElement.dataset.photo='false';
    }});
    if(!figure)return;
    host.append(figure);host.hidden=false;host.parentElement.dataset.photo='true';
  }
  return {lookup,create,renderDevice};
})();
if(typeof window!=='undefined')window.MachinePhotos=MachinePhotos;
if(typeof module!=='undefined')module.exports=MachinePhotos;
