import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { researchCatalog, researchView, validModuleQuery, moduleKinds } from './research.mjs';

export const catalog = JSON.parse(readFileSync(new URL('../data/catalog.v1.json', import.meta.url), 'utf8'));
if (catalog.schemaVersion !== 'static-catalog.v1' || catalog.build !== '0.9.1 #717') throw new Error('Unsupported catalog build');
export const catalogMedia = JSON.parse(readFileSync(new URL('../data/catalog-media.v1.json', import.meta.url), 'utf8'));
if (catalogMedia.schemaVersion !== 'catalog-media.v1' || catalogMedia.build !== catalog.build) throw new Error('Unsupported catalog media');
export const modernMedia = JSON.parse(readFileSync(new URL('../data/catalog-modern.v1.json', import.meta.url), 'utf8'));
if (modernMedia.schemaVersion !== 'catalog-modern.v1' || modernMedia.statsBuild !== catalog.build) throw new Error('Unsupported modern artwork manifest');
export const artOverrides = JSON.parse(readFileSync(new URL('../data/catalog-art-overrides.v1.json', import.meta.url), 'utf8'));
if (artOverrides.schemaVersion !== 'catalog-art-overrides.v1' || artOverrides.statsBuild !== catalog.build) throw new Error('Unsupported artwork overrides');
const mediaFiles = new Map();
for (const kind of ['vehicles','maps','nations']) {
  for (const entry of kind==='nations' ? Object.keys(catalogMedia.nations).map(id=>({id})) : catalog[kind]) {
    const media = catalogMedia[kind][entry.id];
    if (!media) continue;
    const url = `/catalog-media/v1/${kind}/${entry.id}.png`;
    if (media.url !== url || !/^[a-z0-9_-]+$/.test(entry.id)) throw new Error('Invalid catalog media path');
    mediaFiles.set(`v1/${kind}/${entry.id}.png`, fileURLToPath(new URL(`../../local/web/catalog-assets/v1/${kind}/${entry.id}.png`, import.meta.url)));
  }
}
for (const vehicle of catalog.vehicles) {
  const media=modernMedia.vehicles[vehicle.id];
  if(!media) continue;
  if(media.url!==`/catalog-media/v2/vehicles/${vehicle.id}.png` || media.viewBox?.length!==4 || !media.viewBox.every(Number.isFinite)) throw new Error('Invalid modern artwork record');
  mediaFiles.set(`v2/vehicles/${vehicle.id}.png`,fileURLToPath(new URL(`../../local/web/catalog-assets/v2/vehicles/${vehicle.id}.png`,import.meta.url)));
}
for (const [id,media] of Object.entries(artOverrides.vehicles)) {
  if(!catalog.vehicles.some(vehicle=>vehicle.id===id) || !/^[a-z0-9-]+$/.test(id)
    || !['modern-render','upscaled-render'].includes(media.kind)
    || media.url!==`/catalog-media/v3/vehicles/${id}.png`
    || !Number.isFinite(media.width) || !Number.isFinite(media.height) || media.width<=0 || media.height<=0
    || media.viewBox?.length!==4 || !media.viewBox.every(Number.isFinite)
    || media.viewBox.some(n=>n<0) || media.viewBox[2]===0 || media.viewBox[3]===0
    || media.viewBox[0]+media.viewBox[2]>media.width || media.viewBox[1]+media.viewBox[3]>media.height) throw new Error('Invalid artwork override');
  mediaFiles.set(`v3/vehicles/${id}.png`,fileURLToPath(new URL(`../../local/web/catalog-assets/v3/vehicles/${id}.png`,import.meta.url)));
}
export const vehicleImage = vehicle => artOverrides.vehicles[vehicle.id] || modernMedia.vehicles[vehicle.id] || catalogMedia.vehicles[vehicle.id];
export const mapImage = map => catalogMedia.maps[map.id];
export const nationImage = nation => catalogMedia.nations[nation];
export const nations = { ussr:'СССР', germany:'Германия', usa:'США', france:'Франция', uk:'Великобритания', china:'Китай', japan:'Япония' };
export const classes = { lightTank:'Лёгкий танк', mediumTank:'Средний танк', heavyTank:'Тяжёлый танк', 'AT-SPG':'ПТ-САУ', SPG:'САУ' };
export const catalogClassIcons = JSON.parse(readFileSync(new URL('../data/catalog-class-icons.v1.json', import.meta.url), 'utf8'));
if (catalogClassIcons.schemaVersion !== 'catalog-class-icons.v1' || catalogClassIcons.build !== catalog.build
  || Object.keys(catalogClassIcons.classes).length !== Object.keys(classes).length) throw new Error('Unsupported class icon manifest');
for (const kind of Object.keys(classes)) {
  const icon = catalogClassIcons.classes[kind];
  if (!icon || icon.url !== `/catalog-media/v1/classes/${kind}.png` || icon.width !== 27 || icon.height !== 17) throw new Error('Invalid class icon');
  mediaFiles.set(`v1/classes/${kind}.png`, fileURLToPath(new URL(`../../local/web/catalog-assets/v1/classes/${kind}.png`, import.meta.url)));
}
export const vehicleClassImage = kind => Object.hasOwn(catalogClassIcons.classes, kind) ? catalogClassIcons.classes[kind] : null;
const vehicleStatuses = {
  premium:{kind:'premium',label:'Премиумная техника',short:'Премиум',wreath:true,description:'Готовая комплектация: дополнительные модули исследовать не нужно.'},
  reward:{kind:'reward',label:'Акционная техника',short:'Акционная',wreath:true,description:'Специальная машина вне обычной ветки развития. Исследование модулей не требуется.'},
  elite:{kind:'elite',label:'Элитная техника',short:'Элитная',wreath:true,description:'Машина X уровня без дополнительных модулей и следующей техники для исследования.'},
  researchable:{kind:'researchable',label:'Исследуемая техника',short:'Исследуемая',wreath:false,description:'Комплектация и путь развития показаны в дереве модулей.'},
  event:{kind:'event',label:'Событийная техника',short:'Событийная',wreath:false,description:'Машина для специальных событий версии 0.9.1.'},
};
export function vehicleStatus(vehicle) {
  // The special tag takes priority over the gold-price flag used by this old build.
  if (vehicle.special) return vehicleStatuses.reward;
  if (vehicle.premium) return vehicleStatuses.premium;
  if (vehicle.event) return vehicleStatuses.event;
  if (vehicle.tier === 10) {
    const tree = researchCatalog.vehicles[vehicle.id];
    if (!tree) throw new Error('Missing vehicle research status');
    const kinds = Object.keys(moduleKinds).filter(kind=>kind!=='vehicle');
    // Public catalog rule requested by the owner; never pretend to know player unlocks.
    const fixed = tree.edges.length === 0 && tree.nodes.length === kinds.length
      && kinds.every(kind=>tree.nodes.filter(node=>node.kind===kind).length===1);
    if (fixed) return vehicleStatuses.elite;
  }
  return vehicleStatuses.researchable;
}
export const classShort = { lightTank:'ЛТ', mediumTank:'СТ', heavyTank:'ТТ', 'AT-SPG':'ПТ', SPG:'САУ' };
export const classRoles = {
  lightTank:'Разведка, быстрые перемещения и помощь команде в обнаружении противника. Подвижность полезна, пока у машины есть путь отхода.',
  mediumTank:'Поддержка союзников и смена направления атаки. Сочетание подвижности и вооружения помогает использовать открывшийся фланг.',
  heavyTank:'Борьба за важные направления и огневая поддержка вблизи линии столкновения. Используй укрытия и особенности бронирования конкретной машины.',
  'AT-SPG':'Огневая поддержка и противодействие бронетехнике. Выбор позиции зависит от подвижности, защиты и доступных углов наведения.',
  SPG:'Артиллерийская поддержка с удалённых позиций. После выстрела учитывай длительность перезарядки и опасность появления разведки противника.',
};
export const terrains = {city:'Городская',open:'Открытая',mixed:'Смешанная',training:'Учебная',event:'Событийная'};
export const climates = {summer:'Летний',winter:'Зимний',desert:'Пустынный'};
export const modes = {ctf:'Стандартный бой',domination:'Встречный бой',assault:'Штурм'};
export const shellKinds = {ARMOR_PIERCING:'ББ',ARMOR_PIERCING_CR:'БП',ARMOR_PIERCING_HE:'ББ',HIGH_EXPLOSIVE:'ОФ',HOLLOW_CHARGE:'КС'};
export const roman = ['','I','II','III','IV','V','VI','VII','VIII','IX','X'];
export const counts = { vehicles:catalog.vehicles.filter(v=>!v.archived).length, archive:catalog.vehicles.filter(v=>v.archived).length, maps:catalog.maps.filter(m=>m.registered&&!m.special).length, mapsAll:catalog.maps.length };
const vehicleById = new Map(catalog.vehicles.map(v=>[v.id,v]));
const mapById = new Map(catalog.maps.map(m=>[m.id,m]));
export const normalizeSearch = value => value.normalize('NFD').replace(/\p{M}/gu,'').toLowerCase().replaceAll('ё','е');
const vehicleSearch = new Map(catalog.vehicles.map(v=>[v.id,normalizeSearch(`${v.name} ${v.key} ${nations[v.nation]}`)]));
const mapSearch = new Map(catalog.maps.map(m=>[m.id,normalizeSearch(`${m.name} ${m.originalName}`)]));
export const format = value => value === null || value === undefined ? '—' : new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(value);
export function range(values) {
  const valid = values.filter(v=>Number.isFinite(v));
  if (!valid.length) return '—';
  const min=Math.min(...valid),max=Math.max(...valid);
  return min===max ? format(min) : `${format(min)}–${format(max)}`;
}
export const armorText = values => values.length ? values.map(format).join(' / ') : '—';
export const vehicleSummary = vehicle => ({hp:range(vehicle.turrets.map(t=>t.hitPoints)),view:range(vehicle.turrets.map(t=>t.viewRange)),power:range(vehicle.engines.map(e=>e.power)),gunCount:new Set(vehicle.turrets.flatMap(t=>t.guns.map(g=>g.key))).size});
export function readFilters(query, kind) {
  const schema = kind==='vehicles' ? {q:null,nation:['',...Object.keys(nations)],class:['',...Object.keys(classes)],tier:['',...Array.from({length:10},(_,i)=>String(i+1))],scope:['main','archive','all'],sort:['tier','name'],page:null} : {q:null,climate:['',...Object.keys(climates)],terrain:['',...Object.keys(terrains)],mode:['',...Object.keys(modes)],scope:['main','reserve','special','all'],page:null};
  if (Object.keys(query).some(key=>!(key in schema))) return null;
  const filters=kind==='vehicles' ? {q:'',nation:'',class:'',tier:'',scope:'main',sort:'tier',page:'1'} : {q:'',climate:'',terrain:'',mode:'',scope:'main',page:'1'};
  for (const [key,value] of Object.entries(query)) {
    if(typeof value!=='string'||value.length>80||/[\u0000-\u001f\u007f]/.test(value)) return null;
    if(schema[key]&&!schema[key].includes(value)) return null;
    if(key==='page'&&!/^[1-9][0-9]{0,3}$/.test(value)) return null;
    filters[key]=value.trim();
  }
  return filters;
}
export function filterVehicles(filters) {
  const query=normalizeSearch(filters.q);
  return catalog.vehicles.filter(v=>(filters.scope==='all'||(filters.scope==='archive'?v.archived:!v.archived))
    &&(!filters.nation||v.nation===filters.nation)&&(!filters.class||v.class===filters.class)
    &&(!filters.tier||v.tier===Number(filters.tier))&&(!query||vehicleSearch.get(v.id).includes(query)))
    .sort((a,b)=>(filters.sort==='tier'?b.tier-a.tier:0)||a.name.localeCompare(b.name,'ru')||a.id.localeCompare(b.id));
}
export function filterMaps(filters) {
  const query=normalizeSearch(filters.q);
  return catalog.maps.filter(m=>(filters.scope==='all'||(filters.scope==='special'?m.special:filters.scope==='reserve'?!m.registered:m.registered&&!m.special))
    &&(!filters.climate||m.camouflage===filters.climate)&&(!filters.terrain||m.terrain===filters.terrain)
    &&(!filters.mode||m.modes.some(mode=>mode.id===filters.mode))&&(!query||mapSearch.get(m.id).includes(query)))
    .sort((a,b)=>a.name.localeCompare(b.name,'ru'));
}
const common = { nations, classes, classShort, classRoles, terrains, climates, modes, shellKinds, roman, counts, format, range, armorText, vehicleSummary, vehicleImage, vehicleClassImage, vehicleStatus, mapImage, nationImage, catalogBuild:catalog.build, nextVehicle:id=>vehicleById.get(id) };
function pagination(items, filters, path, perPage) {
  const pages=Math.max(1,Math.ceil(items.length/perPage)),page=Math.min(Number(filters.page),pages);
  return {items:items.slice((page-1)*perPage,page*perPage),total:items.length,page,pages,
    pageUrl:number=>`${path}?${new URLSearchParams({...filters,page:String(number)})}`};
}
export function registerCatalogRoutes(app, problem) {
  app.get('/catalog-media/:version/:kind/:file',(req,res)=>{
    const file=mediaFiles.get(`${req.params.version}/${req.params.kind}/${req.params.file}`);
    if(!file) return problem(res,404,'Изображение не найдено.');
    res.sendFile(file,{dotfiles:'deny',maxAge:0});
  });
  app.get('/vehicles',(req,res)=>{
    const filters=readFilters(req.query,'vehicles');
    if(!filters) return problem(res,400,'Проверь параметры поиска в каталоге техники.');
    res.render('vehicles',{...common,title:'Каталог техники',filters,...pagination(filterVehicles(filters),filters,'/vehicles',24)});
  });
  app.get('/vehicles/:id',(req,res)=>{
    const vehicle=vehicleById.get(req.params.id);
    if(!vehicle) return problem(res,404,'Такой машины в каталоге 0.9.1 нет.');
    if(!validModuleQuery(req.query,vehicle.id)) return problem(res,400,'Такого модуля в дереве этой машины нет.');
    const research=researchView(vehicle,req.query.module);
    res.render('vehicle',{...common,title:vehicle.name,vehicle,summary:vehicleSummary(vehicle),research,moduleKinds,
      nextVehicle:id=>vehicleById.get(id)});
  });
  app.get('/maps',(req,res)=>{
    const filters=readFilters(req.query,'maps');
    if(!filters) return problem(res,400,'Проверь параметры поиска в каталоге карт.');
    res.render('maps',{...common,title:'Атлас карт',filters,...pagination(filterMaps(filters),filters,'/maps',12)});
  });
  app.get('/maps/:id',(req,res)=>{
    const map=mapById.get(req.params.id);
    if(!map) return problem(res,404,'Такой карты в каталоге 0.9.1 нет.');
    if(Object.keys(req.query).some(key=>key!=='mode')||(req.query.mode!==undefined&&(typeof req.query.mode!=='string'||!map.modes.some(mode=>mode.id===req.query.mode)))) return problem(res,400,'Этот режим не указан для выбранной карты.');
    const mode=map.modes.find(mode=>mode.id===req.query.mode)||map.modes[0];
    const point=position=>({x:40+(position[0]-map.bounds.min[0])/map.size[0]*420,y:460-(position[1]-map.bounds.min[1])/map.size[1]*420});
    res.render('map',{...common,title:map.name,map,mode,point});
  });
}
