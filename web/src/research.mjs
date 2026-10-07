import { readFileSync } from 'node:fs';

export const researchCatalog = JSON.parse(readFileSync(new URL('../data/catalog-research.v1.json', import.meta.url), 'utf8'));
if (researchCatalog.schemaVersion !== 'catalog-research.v1' || researchCatalog.build !== '0.9.1 #717') throw new Error('Unsupported research catalog');
export const moduleKinds = { chassis:'Ходовая', engine:'Двигатель', radio:'Радиостанция', turret:'Башня', gun:'Орудие', vehicle:'Следующая машина' };
const kindOrder = Object.keys(moduleKinds);

function lines(name, maximum = 23) {
  const words = name.split(/\s+/), result = [''];
  for (const word of words) {
    if ((result.at(-1) + ' ' + word).trim().length > maximum && result.at(-1)) result.push('');
    result[result.length - 1] = (result.at(-1) + ' ' + word).trim();
  }
  const clipped = result.length <= 2 ? result : [result[0], result.slice(1).join(' ')];
  return clipped.map(line=>line.length>maximum?line.slice(0,maximum-1)+'…':line);
}

export function researchView(vehicle, selectedId) {
  const tree = researchCatalog.vehicles[vehicle.id];
  if (!tree || !tree.nodes.length) throw new Error('Missing research data');
  const nodes = tree.nodes.map(node => ({...node, rank:0, incoming:[], outgoing:[], nameLines:lines(node.name)}));
  const byId = new Map(nodes.map(node => [node.id,node]));
  for (const edge of tree.edges) {
    const from = byId.get(edge.from), to = byId.get(edge.to);
    if (!from || !to || !Number.isSafeInteger(edge.xp) || edge.xp < 0) throw new Error('Invalid research edge');
    from.outgoing.push({...edge,node:to}); to.incoming.push({...edge,node:from});
  }
  const pending = new Map(nodes.map(node => [node.id,node.incoming.length]));
  const queue = nodes.filter(node => !pending.get(node.id));
  let visited = 0;
  for (let i=0; i<queue.length; i++) {
    const node = queue[i]; visited++;
    for (const edge of node.outgoing) {
      edge.node.rank = Math.max(edge.node.rank,node.rank+1);
      pending.set(edge.to,pending.get(edge.to)-1);
      if (!pending.get(edge.to)) queue.push(edge.node);
    }
  }
  if (visited !== nodes.length) throw new Error('Cyclic research data');
  const fixed = tree.edges.length === 0;
  const ranks = fixed ? [] : Array.from({length:Math.max(...nodes.map(node=>node.rank))+1},()=>[]);
  if (!fixed) for (const node of nodes) ranks[node.rank].push(node);
  const sort = (a,b)=>kindOrder.indexOf(a.kind)-kindOrder.indexOf(b.kind)||a.level-b.level||a.name.localeCompare(b.name,'ru');
  if (fixed) {
    nodes.sort(sort).forEach((node,index)=>{node.x=22+(index%3)*220;node.y=25+Math.floor(index/3)*118;});
  } else {
    // Put the armament progression first and align upgrades with their parents.
    // A distinct routing channel per source avoids merging unrelated branches.
    const rootOrder=['gun','turret','chassis','engine','radio','vehicle'];
    ranks[0].sort((a,b)=>rootOrder.indexOf(a.kind)-rootOrder.indexOf(b.kind)||b.outgoing.length-a.outgoing.length||sort(a,b));
    for (const [rank,column] of ranks.entries()) {
      const preferred=node=>node.incoming.length?node.incoming.reduce((sum,edge)=>sum+edge.node.y,0)/node.incoming.length:36;
      if (rank) column.sort((a,b)=>preferred(a)-preferred(b)||b.outgoing.length-a.outgoing.length||sort(a,b));
      let previousY=-82;
      for (const node of column) {
        node.x=22+rank*220;node.y=Math.max(rank?preferred(node):36,previousY+118);previousY=node.y;
      }
    }
  }
  const width=fixed?Math.min(3,nodes.length)*220+20:ranks.length*220+20;
  const nodeBottom=Math.max(...nodes.map(node=>node.y))+110;
  let longEdgeCount=0;
  const selected=byId.get(selectedId)||nodes.find(node=>node.kind==='gun')||nodes[0];
  const edges=tree.edges.map(edge=>{
    const from=byId.get(edge.from),to=byId.get(edge.to),x1=from.x+188,y1=from.y+46,x2=to.x,y2=to.y+46;
    const sources=ranks[from.rank],channel=8+20*(sources.indexOf(from)+1)/(sources.length+1);
    const rail=nodeBottom+18*(++longEdgeCount);
    const path=to.rank>from.rank+1?`M${x1} ${y1}H${x1+channel}V${rail}H${x2-10}V${y2}H${x2}`:`M${x1} ${y1}H${x1+channel}V${y2}H${x2}`;
    if(to.rank===from.rank+1)longEdgeCount--;
    return {...edge,path,selected:edge.from===selected.id||edge.to===selected.id};
  });
  const height=nodeBottom+18*longEdgeCount;
  const selectedTurret=selected.kind==='turret'?vehicle.turrets.find(t=>t.key===selected.key):null;
  const gunVariants=selected.kind==='gun'?vehicle.turrets.flatMap(t=>t.guns.filter(g=>g.key===selected.key).map(g=>({turret:t,gun:g}))):[];
  const moduleCount=nodes.filter(n=>n.kind!=='vehicle').length;
  return {nodes,edges,width,height,fixed,selected,selectedTurret,gunVariants,moduleCount,price:tree.price,
    nextVehicles:nodes.filter(n=>n.kind==='vehicle'),byId};
}

export function validModuleQuery(query, vehicleId) {
  if (Object.keys(query).some(key=>key!=='module')) return false;
  if (query.module===undefined) return true;
  return typeof query.module==='string' && query.module.length<=100
    && researchCatalog.vehicles[vehicleId]?.nodes.some(node=>node.id===query.module);
}
